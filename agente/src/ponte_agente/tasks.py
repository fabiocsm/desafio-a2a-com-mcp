"""Modelos, transições e registros em memória de Tasks A2A v1.0 para o agente."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import secrets
from typing import Any, Mapping
import uuid

from a2a.types import a2a_pb2
from google.protobuf.timestamp_pb2 import Timestamp

TERMINAL_TASK_STATES: frozenset[int] = frozenset(
    {
        a2a_pb2.TASK_STATE_COMPLETED,
        a2a_pb2.TASK_STATE_FAILED,
        a2a_pb2.TASK_STATE_CANCELED,
    }
)


class TerminalTaskStateError(RuntimeError):
    """Erro disparado quando se tenta reabrir ou enviar mensagem a uma Task em estado terminal."""


def is_terminal_state(state: int) -> bool:
    """Verifica se o estado Protobuf da Task é definitivo (COMPLETED, FAILED ou CANCELED)."""
    return state in TERMINAL_TASK_STATES


def utc_timestamp_proto(dt: datetime | None = None) -> Timestamp:
    """Cria um Timestamp Protobuf em UTC (serializado com sufixo Z em ProtoJSON)."""
    current = dt if dt is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    ts = Timestamp()
    ts.FromDatetime(current)
    return ts


def build_text_part(text: str) -> a2a_pb2.Part:
    """Cria um Part A2A v1 contendo apenas text, sem campo legado kind."""
    return a2a_pb2.Part(text=text)


def build_message(
    *,
    role: int,
    text: str,
    message_id: str | None = None,
    task_id: str | None = None,
    context_id: str | None = None,
) -> a2a_pb2.Message:
    """Cria uma Message A2A v1 com message_id próprio, role e parts de texto."""
    msg = a2a_pb2.Message(
        message_id=message_id or str(uuid.uuid4()),
        role=role,
        parts=[build_text_part(text)],
    )
    if task_id:
        msg.task_id = task_id
    if context_id:
        msg.context_id = context_id
    return msg


def normalize_user_message(user_message: a2a_pb2.Message, text: str) -> a2a_pb2.Message:
    """Normaliza a mensagem de entrada do usuário garantindo message_id próprio e Part textual v1."""
    return build_message(
        role=a2a_pb2.ROLE_USER,
        text=text,
        message_id=user_message.message_id or str(uuid.uuid4()),
        task_id=user_message.task_id or None,
        context_id=user_message.context_id or None,
    )


def build_task_status(
    state: int,
    *,
    message: a2a_pb2.Message | None = None,
    emit_timestamp: bool = False,
) -> a2a_pb2.TaskStatus:
    """Cria um TaskStatus com state TASK_STATE_*, message opcional e timestamp UTC opcional."""
    status = a2a_pb2.TaskStatus(state=state)
    if message is not None:
        status.message.CopyFrom(message)
    if emit_timestamp:
        status.timestamp.CopyFrom(utc_timestamp_proto())
    return status


def build_reservation_artifact(
    reservation_data: Mapping[str, Any],
    *,
    policy_version: str,
) -> a2a_pb2.Artifact:
    """Constrói o Artifact público 'reserva' com os campos devolvidos pelo MCP e a política do resource."""
    required_keys = ("reserva", "sala", "inicio", "fim", "responsavel")
    for key in required_keys:
        value = reservation_data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Campo obrigatório '{key}' ausente no resultado de reserva MCP")
    if not isinstance(policy_version, str) or not policy_version.strip():
        raise ValueError("Versão da política ausente para construção do artifact")

    payload = {
        "reserva": reservation_data["reserva"],
        "sala": reservation_data["sala"],
        "inicio": reservation_data["inicio"],
        "fim": reservation_data["fim"],
        "responsavel": reservation_data["responsavel"],
        "politica": policy_version.strip(),
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    return a2a_pb2.Artifact(
        artifact_id=str(uuid.uuid4()),
        name="reserva",
        parts=[build_text_part(serialized)],
    )


def clone_public_task(task: a2a_pb2.Task) -> a2a_pb2.Task:
    """Retorna uma cópia isolada do objeto Protobuf público Task."""
    copied = a2a_pb2.Task()
    copied.CopyFrom(task)
    return copied


@dataclass(frozen=True, slots=True)
class RequestTrace:
    """Contexto de rastreamento por Task: valor original por Task; mesmo trace-id em cada request MCP."""

    original_traceparent: str | None = None

    @property
    def trace_id(self) -> str | None:
        """Extrai o trace-id quando original_traceparent segue o formato W3C."""
        if not self.original_traceparent:
            return None
        parts = self.original_traceparent.strip().split("-")
        if len(parts) == 4 and len(parts[1]) == 32:
            return parts[1].lower()
        return None

    def next_mcp_traceparent(self) -> str | None:
        """Gera traceparent para chamada MCP mantendo o mesmo trace-id e renovando o span-id."""
        if not self.original_traceparent:
            return None
        raw = self.original_traceparent.strip()
        parts = raw.split("-")
        if len(parts) == 4 and len(parts[0]) == 2 and len(parts[1]) == 32 and len(parts[3]) == 2:
            new_span_id = secrets.token_hex(8)
            return f"{parts[0]}-{parts[1]}-{new_span_id}-{parts[3]}"
        return raw

    def to_mcp_meta(self) -> dict[str, Any]:
        """Monta o dicionário de metadados de rastreamento para um request MCP."""
        tp = self.next_mcp_traceparent()
        if not tp:
            return {}
        return {"traceparent": tp}


@dataclass(slots=True)
class TaskRecord:
    """Registro interno por Task: Task pública e traceparent original opcional; sem regras de sala."""

    public_task: a2a_pb2.Task
    traceparent_original: str | None = None
    trace: RequestTrace = field(init=False)
    state_transitions: list[int] = field(default_factory=list)
    raw_input_required: Any = None

    def __post_init__(self) -> None:
        if self.traceparent_original is not None:
            cleaned = self.traceparent_original.strip() or None
            self.traceparent_original = cleaned
        self.trace = RequestTrace(original_traceparent=self.traceparent_original)
        if self.public_task.status.state and not self.state_transitions:
            self.state_transitions.append(self.public_task.status.state)

    @property
    def is_terminal(self) -> bool:
        return is_terminal_state(self.public_task.status.state)


class TaskStore:
    """Mapa em memória de TaskRecord indexado exclusivamente por taskId."""

    def __init__(self) -> None:
        self._records: dict[str, TaskRecord] = {}

    def get_record(self, task_id: str) -> TaskRecord | None:
        """Recupera o TaskRecord interno pelo taskId."""
        if not task_id:
            return None
        return self._records.get(task_id)

    def get_public_task(self, task_id: str) -> a2a_pb2.Task | None:
        """Retorna snapshot público (Task Protobuf) sem expor TaskRecord interno e sem mutar o estado."""
        record = self.get_record(task_id)
        if record is None:
            return None
        return clone_public_task(record.public_task)

    def ensure_not_terminal(self, task_id: str) -> TaskRecord:
        """Verifica se a Task existe e não está em estado terminal (COMPLETED, FAILED ou CANCELED)."""
        record = self.get_record(task_id)
        if record is None:
            raise KeyError(task_id)
        if record.is_terminal:
            state_name = a2a_pb2.TaskState.Name(record.public_task.status.state)
            raise TerminalTaskStateError(
                f"Task {task_id} já se encontra em estado terminal definitivo ({state_name})"
            )
        return record

    def create_submitted_task(
        self,
        user_message: a2a_pb2.Message,
        text: str,
        *,
        traceparent: str | None = None,
    ) -> TaskRecord:
        """Cria Task com id e context_id UUID próprios em TASK_STATE_SUBMITTED e registra no mapa."""
        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        normalized_msg = normalize_user_message(user_message, text)
        task = a2a_pb2.Task(
            id=task_id,
            context_id=context_id,
            status=build_task_status(a2a_pb2.TASK_STATE_SUBMITTED),
            history=[normalized_msg],
        )
        record = TaskRecord(
            public_task=task,
            traceparent_original=traceparent,
            state_transitions=[a2a_pb2.TASK_STATE_SUBMITTED],
        )
        self._records[task_id] = record
        return record

    def transition_to_working(self, task_id: str) -> TaskRecord:
        """Transita a Task de SUBMITTED (ou estado não-terminal) para TASK_STATE_WORKING antes do HTTP MCP."""
        record = self.ensure_not_terminal(task_id)
        record.public_task.status.CopyFrom(build_task_status(a2a_pb2.TASK_STATE_WORKING))
        record.state_transitions.append(a2a_pb2.TASK_STATE_WORKING)
        return record

    def complete_task(
        self,
        task_id: str,
        reservation_data: Mapping[str, Any],
        *,
        policy_version: str,
    ) -> a2a_pb2.Task:
        """Conclui a Task em TASK_STATE_COMPLETED com Artifact 'reserva' e mensagem ROLE_AGENT no histórico."""
        record = self.ensure_not_terminal(task_id)
        artifact = build_reservation_artifact(reservation_data, policy_version=policy_version)
        task = record.public_task
        del task.artifacts[:]
        task.artifacts.append(artifact)

        reserva_id = reservation_data["reserva"]
        sala_id = reservation_data["sala"]
        agent_msg = build_message(
            role=a2a_pb2.ROLE_AGENT,
            text=f"Reserva {reserva_id} confirmada na {sala_id}.",
            task_id=task.id,
            context_id=task.context_id,
        )
        task.history.append(agent_msg)
        task.status.CopyFrom(
            build_task_status(a2a_pb2.TASK_STATE_COMPLETED, message=agent_msg)
        )
        record.raw_input_required = None
        record.state_transitions.append(a2a_pb2.TASK_STATE_COMPLETED)
        return clone_public_task(task)

    def fail_task(
        self,
        task_id: str,
        error_text: str,
    ) -> a2a_pb2.Task:
        """Encerra a Task em TASK_STATE_FAILED com mensagem ROLE_AGENT no histórico e sem artifacts."""
        record = self.ensure_not_terminal(task_id)
        task = record.public_task
        del task.artifacts[:]
        agent_msg = build_message(
            role=a2a_pb2.ROLE_AGENT,
            text=error_text,
            task_id=task.id,
            context_id=task.context_id,
        )
        task.history.append(agent_msg)
        task.status.CopyFrom(
            build_task_status(a2a_pb2.TASK_STATE_FAILED, message=agent_msg)
        )
        record.raw_input_required = None
        record.state_transitions.append(a2a_pb2.TASK_STATE_FAILED)
        return clone_public_task(task)

    def cancel_task(
        self,
        task_id: str,
        reason_text: str = "Reserva cancelada pelo usuario.",
    ) -> a2a_pb2.Task:
        """Encerra a Task em TASK_STATE_CANCELED com mensagem ROLE_AGENT no histórico e sem artifacts."""
        record = self.ensure_not_terminal(task_id)
        task = record.public_task
        del task.artifacts[:]
        agent_msg = build_message(
            role=a2a_pb2.ROLE_AGENT,
            text=reason_text,
            task_id=task.id,
            context_id=task.context_id,
        )
        task.history.append(agent_msg)
        task.status.CopyFrom(
            build_task_status(a2a_pb2.TASK_STATE_CANCELED, message=agent_msg)
        )
        record.raw_input_required = None
        record.state_transitions.append(a2a_pb2.TASK_STATE_CANCELED)
        return clone_public_task(task)
