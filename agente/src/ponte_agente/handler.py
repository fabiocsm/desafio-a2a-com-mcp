"""RequestHandler A2A v1.0 e parser determinístico de pedidos de reserva."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
import json
import re
from typing import Any, Mapping

from a2a.server.context import ServerCallContext
from a2a.server.events.event_queue import Event
from a2a.server.request_handlers.request_handler import RequestHandler
from a2a.types import a2a_pb2
from a2a.utils.errors import (
    InvalidParamsError,
    TaskNotFoundError,
    UnsupportedOperationError,
)
import mcp_types as types

from ponte_agente.mcp_host import DefensiveElicitationCalledError, MCPHost
from ponte_agente.ponte import (
    PonteFormatoError,
    build_retry_input_responses,
    continuation_from_input_required,
    decision_is_acceptable,
    interpret_client_decision,
)
from ponte_agente.tasks import TaskRecord, TaskStore

TECHNICAL_MCP_FAILURE_MESSAGE = "Falha ao executar pedido no servidor MCP"

_RESERVATION_GRAMMAR_RE = re.compile(
    r"^reservar\s+sala=(\S+)\s+inicio=(\S+)\s+fim=(\S+)\s+responsavel=(.+)$"
)


@dataclass(frozen=True, slots=True)
class ParsedReservation:
    """Pedido de reserva extraído por gramática fixa: sala, inicio, fim, responsavel."""

    sala: str
    inicio: str
    fim: str
    responsavel: str

    def to_mcp_arguments(self) -> dict[str, str]:
        """Converte para o dicionário de argumentos de reservar_sala."""
        return {
            "sala": self.sala,
            "inicio": self.inicio,
            "fim": self.fim,
            "responsavel": self.responsavel,
        }


def parse_reservation_command(text: str) -> ParsedReservation:
    """Extrai sala, inicio, fim e responsavel por gramática fixa sem LLM e sem validar domínio."""
    if not isinstance(text, str):
        raise InvalidParamsError(message="Pedido de reserva deve ser texto")
    cleaned = text.strip()
    if not cleaned or "\n" in cleaned or "\r" in cleaned:
        raise InvalidParamsError(
            message="Formato invalido: esperado 'reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>'"
        )
    # Verifica que nenhum prefixo chave= está vazio (ex.: 'sala= inicio=...')
    if re.search(r"\b(sala|inicio|fim|responsavel)=\s", cleaned):
        raise InvalidParamsError(
            message="Formato invalido: campos sala, inicio, fim e responsavel nao podem ser vazios"
        )
    match = _RESERVATION_GRAMMAR_RE.match(cleaned)
    if match is None:
        raise InvalidParamsError(
            message="Formato invalido: esperado 'reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>'"
        )
    sala, inicio, fim, responsavel_raw = match.groups()
    responsavel = responsavel_raw.strip()
    if not sala or not inicio or not fim or not responsavel:
        raise InvalidParamsError(
            message="Formato invalido: sala, inicio, fim e responsavel sao obrigatorios"
        )
    return ParsedReservation(
        sala=sala,
        inicio=inicio,
        fim=fim,
        responsavel=responsavel,
    )


def extract_message_text(params: a2a_pb2.SendMessageRequest) -> tuple[a2a_pb2.Message, str]:
    """Extrai o objeto Message e o texto do primeiro Part, rejeitando entradas vazias."""
    if not params.HasField("message"):
        raise InvalidParamsError(message="Campo 'message' e obrigatorio em SendMessage")
    msg = params.message
    if not msg.parts:
        raise InvalidParamsError(message="Campo 'message.parts' nao pode ser vazio")
    text = msg.parts[0].text
    if not isinstance(text, str) or not text.strip():
        raise InvalidParamsError(message="Parte de texto da mensagem nao pode ser vazia")
    return msg, text


def extract_tool_error_text(result: types.CallToolResult) -> str:
    """Extrai a mensagem textual exata de um CallToolResult com isError=True."""
    for item in result.content:
        text = getattr(item, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
    if isinstance(result.structured_content, Mapping):
        err = result.structured_content.get("error") or result.structured_content.get("message")
        if isinstance(err, str) and err.strip():
            return err.strip()
    return TECHNICAL_MCP_FAILURE_MESSAGE


def extract_reservation_payload(result: types.CallToolResult) -> Mapping[str, Any]:
    """Extrai os dados da reserva concluída do structuredContent ou do bloco de texto."""
    if isinstance(result.structured_content, Mapping):
        data: Mapping[str, Any] = result.structured_content
    else:
        parsed_text: Any = None
        for item in result.content:
            text = getattr(item, "text", None)
            if isinstance(text, str) and text.strip():
                parsed_text = json.loads(text)
                break
        if not isinstance(parsed_text, Mapping):
            raise ValueError("Resultado da tool de reserva não contém objeto JSON válido")
        data = parsed_text

    if data.get("reservado") is not True:
        raise ValueError("Resultado de reserva não indica reservado=True")
    for required_field in ("reserva", "sala", "inicio", "fim", "responsavel"):
        val = data.get(required_field)
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"Campo obrigatório '{required_field}' ausente na reserva concluída")
    return data


class AgenteRequestHandler(RequestHandler):
    """Implementação oficial de RequestHandler para SendMessage e GetTask."""

    def __init__(self, *, mcp_host: MCPHost, task_store: TaskStore) -> None:
        self._mcp_host = mcp_host
        self._task_store = task_store

    async def on_get_task(
        self,
        params: a2a_pb2.GetTaskRequest,
        context: ServerCallContext,
    ) -> a2a_pb2.Task | None:
        """Consulta Task existente sem mutar estado e sem aguardar operações externas."""
        task_id = params.id.strip() if params and params.id else ""
        if not task_id:
            raise InvalidParamsError(message="Parametro 'id' da Task e obrigatorio em GetTask")
        task = self._task_store.get_public_task(task_id)
        if task is None:
            raise TaskNotFoundError(message=f"Task '{task_id}' nao encontrada")
        return task

    async def on_message_send(
        self,
        params: a2a_pb2.SendMessageRequest,
        context: ServerCallContext,
    ) -> a2a_pb2.Task | a2a_pb2.Message:
        """Processa SendMessage novo ou a continuação da mesma Task, sem abrir outra identidade."""
        user_msg, text = extract_message_text(params)
        referenced_task_id = user_msg.task_id.strip() if user_msg.task_id else ""

        if referenced_task_id:
            record = self._task_store.get_record(referenced_task_id)
            if record is None:
                raise TaskNotFoundError(message=f"Task '{referenced_task_id}' nao encontrada")
            if record.is_terminal:
                state_name = a2a_pb2.TaskState.Name(record.public_task.status.state)
                raise InvalidParamsError(
                    message=f"Task '{referenced_task_id}' encontra-se em estado terminal definitivo ({state_name})"
                )
            return await self._resume_task(record, user_msg, text)

        parsed = parse_reservation_command(text)
        traceparent = (
            context.state.get("traceparent")
            if context is not None and isinstance(context.state, dict)
            else None
        )

        record = self._task_store.create_submitted_task(
            user_msg,
            text,
            traceparent=traceparent,
        )
        task_id = record.public_task.id
        self._task_store.transition_to_working(task_id)
        arguments = dict(parsed.to_mcp_arguments())

        try:
            snapshot = await self._mcp_host.ensure_discovered(trace=record.trace)
            mcp_result = await self._mcp_host.call_tool_raw(
                snapshot.reservation_tool.name,
                arguments,
                trace=record.trace,
            )
            if isinstance(mcp_result, types.InputRequiredResult):
                return self._pause_from_input_required(
                    task_id,
                    mcp_result,
                    tool_name=snapshot.reservation_tool.name,
                    arguments=arguments,
                )
            return self._apply_call_result(task_id, mcp_result, snapshot.policy_version)
        except DefensiveElicitationCalledError:
            raise
        except Exception:
            return self._task_store.fail_task(task_id, TECHNICAL_MCP_FAILURE_MESSAGE)

    def _pause_from_input_required(
        self,
        task_id: str,
        mcp_result: types.InputRequiredResult,
        *,
        tool_name: str,
        arguments: Mapping[str, str],
    ) -> a2a_pb2.Task:
        """Converte o resultado cru em pausa pública. O token fica só na continuação privada."""
        try:
            pending = continuation_from_input_required(
                mcp_result,
                tool_name=tool_name,
                original_arguments=arguments,
            )
        except PonteFormatoError:
            record = self._task_store.get_record(task_id)
            if record is not None:
                record.raw_input_required = mcp_result
            return self._task_store.fail_task(task_id, TECHNICAL_MCP_FAILURE_MESSAGE)
        return self._task_store.pause_for_input(
            task_id,
            pending,
            raw_input_required=mcp_result,
        )

    async def _resume_task(
        self,
        record: TaskRecord,
        user_msg: a2a_pb2.Message,
        text: str,
    ) -> a2a_pb2.Task:
        """Retoma a Task pelo taskId. O trace original não é substituído por header posterior."""
        task_id = record.public_task.id
        pending = record.pending
        if pending is None or record.public_task.status.state != a2a_pb2.TASK_STATE_INPUT_REQUIRED:
            raise InvalidParamsError(message=f"Task '{task_id}' nao esta aguardando escolha")

        decision = interpret_client_decision(text)
        if decision is None or not decision_is_acceptable(decision, pending):
            return self._task_store.repeat_pause(task_id, user_msg, text)

        self._task_store.begin_resume(task_id, user_msg, text)
        try:
            snapshot = await self._mcp_host.ensure_discovered(trace=record.trace)
            mcp_result = await self._mcp_host.call_tool_raw(
                pending.tool_name,
                pending.original_arguments.as_mcp_dict(),
                trace=record.trace,
                input_responses=build_retry_input_responses(pending, decision),
                request_state=pending.request_state,
            )
            if isinstance(mcp_result, types.InputRequiredResult):
                return self._task_store.fail_task(task_id, TECHNICAL_MCP_FAILURE_MESSAGE)
            return self._apply_call_result(task_id, mcp_result, snapshot.policy_version)
        except DefensiveElicitationCalledError:
            raise
        except Exception:
            return self._task_store.fail_task(task_id, TECHNICAL_MCP_FAILURE_MESSAGE)

    def _apply_call_result(
        self,
        task_id: str,
        mcp_result: types.CallToolResult,
        policy_version: str,
    ) -> a2a_pb2.Task:
        """Aplica o resultado MCP. isError precede sucesso e cancelamento."""
        if mcp_result.is_error:
            return self._task_store.fail_task(task_id, extract_tool_error_text(mcp_result))

        structured = mcp_result.structured_content
        reservado = structured.get("reservado") if isinstance(structured, Mapping) else None
        motivo = structured.get("motivo") if isinstance(structured, Mapping) else None
        if reservado is True:
            reservation_data = extract_reservation_payload(mcp_result)
            return self._task_store.complete_task(
                task_id,
                reservation_data,
                policy_version=policy_version,
            )
        if reservado is False and isinstance(motivo, str) and motivo.strip():
            return self._task_store.cancel_task(task_id, "Reserva recusada.")
        return self._task_store.fail_task(task_id, TECHNICAL_MCP_FAILURE_MESSAGE)

    async def on_list_tasks(
        self,
        params: a2a_pb2.ListTasksRequest,
        context: ServerCallContext,
    ) -> a2a_pb2.ListTasksResponse:
        raise UnsupportedOperationError

    async def on_cancel_task(
        self,
        params: a2a_pb2.CancelTaskRequest,
        context: ServerCallContext,
    ) -> a2a_pb2.Task | None:
        raise UnsupportedOperationError

    async def on_message_send_stream(
        self,
        params: a2a_pb2.SendMessageRequest,
        context: ServerCallContext,
    ) -> AsyncGenerator[Event]:
        raise UnsupportedOperationError
        yield

    async def on_create_task_push_notification_config(
        self,
        params: a2a_pb2.TaskPushNotificationConfig,
        context: ServerCallContext,
    ) -> a2a_pb2.TaskPushNotificationConfig:
        raise UnsupportedOperationError

    async def on_get_task_push_notification_config(
        self,
        params: a2a_pb2.GetTaskPushNotificationConfigRequest,
        context: ServerCallContext,
    ) -> a2a_pb2.TaskPushNotificationConfig:
        raise UnsupportedOperationError

    async def on_subscribe_to_task(
        self,
        params: a2a_pb2.SubscribeToTaskRequest,
        context: ServerCallContext,
    ) -> AsyncGenerator[Event]:
        raise UnsupportedOperationError
        yield

    async def on_list_task_push_notification_configs(
        self,
        params: a2a_pb2.ListTaskPushNotificationConfigsRequest,
        context: ServerCallContext,
    ) -> a2a_pb2.ListTaskPushNotificationConfigsResponse:
        raise UnsupportedOperationError

    async def on_delete_task_push_notification_config(
        self,
        params: a2a_pb2.DeleteTaskPushNotificationConfigRequest,
        context: ServerCallContext,
    ) -> None:
        raise UnsupportedOperationError

    async def on_get_extended_agent_card(
        self,
        params: a2a_pb2.GetExtendedAgentCardRequest,
        context: ServerCallContext,
    ) -> a2a_pb2.AgentCard:
        raise UnsupportedOperationError
