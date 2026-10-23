"""Testes unitários de parser determinístico, identidades e transições de Task A2A v1 (T009)."""

from __future__ import annotations

import json
from typing import Any
import unittest

from a2a.server.context import ServerCallContext
from a2a.types import a2a_pb2
from a2a.utils.errors import InvalidParamsError, TaskNotFoundError
from google.protobuf.json_format import MessageToDict
from mcp.shared.exceptions import MCPError
import mcp_types as types

from ponte_agente.handler import (
    TECHNICAL_MCP_FAILURE_MESSAGE,
    AgenteRequestHandler,
    ParsedReservation,
    parse_reservation_command,
)
from ponte_agente.mcp_host import HostSnapshot
from ponte_agente.tasks import TerminalTaskStateError, TaskStore, build_message


class FakeMCPHostForTasks:
    """Stub controlado de MCPHost para observar transições de Task antes e depois do await MCP."""

    def __init__(self, *, policy_version: str = "2026-11-01") -> None:
        self.policy_version = policy_version
        self.calls: list[tuple[str, dict[str, Any], str | None]] = []
        self.observed_task_states_during_call: list[int] = []
        self.observed_transitions_during_call: list[list[int]] = []
        self.store_ref: TaskStore | None = None
        self.last_task_id: str | None = None

    async def ensure_discovered(self, *, trace: Any = None) -> HostSnapshot:
        tool = types.Tool(
            name="reservar_sala",
            description="Reserva uma sala.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sala": {"type": "string"},
                    "inicio": {"type": "string"},
                    "fim": {"type": "string"},
                    "responsavel": {"type": "string"},
                },
                "required": ["sala", "inicio", "fim", "responsavel"],
            },
        )
        return HostSnapshot(
            tools_by_name={"reservar_sala": tool},
            reservation_tool=tool,
            policy_text=f"versao: {self.policy_version}\n",
            policy_version=self.policy_version,
        )

    async def call_tool_raw(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        trace: Any = None,
        input_responses: Any = None,
        request_state: str | None = None,
    ) -> types.CallToolResult:
        tp = trace.next_mcp_traceparent() if hasattr(trace, "next_mcp_traceparent") else None
        self.calls.append((name, dict(arguments or {}), tp))
        if self.store_ref is not None and self.last_task_id is not None:
            rec = self.store_ref.get_record(self.last_task_id)
            if rec is not None:
                self.observed_task_states_during_call.append(rec.public_task.status.state)
                self.observed_transitions_during_call.append(list(rec.state_transitions))
        args = arguments or {}
        payload = {
            "reserva": f"res-000{len(self.calls) + 2}",
            "reservado": True,
            "sala": args.get("sala", "sala-porao"),
            "inicio": args.get("inicio", "2026-11-03T09:00:00-03:00"),
            "fim": args.get("fim", "2026-11-03T10:00:00-03:00"),
            "responsavel": args.get("responsavel", "Doc"),
            "politica": self.policy_version,
        }
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(payload))],
            structuredContent=payload,
            isError=False,
        )


class TestParserAndTaskTransitionsUS1(unittest.IsolatedAsyncioTestCase):
    """Casos de parser fixo, responsável com espaços, entrada malformada e transições SUBMITTED → WORKING."""

    def test_parser_fixo_simples_e_responsavel_com_espacos(self) -> None:
        parsed = parse_reservation_command(
            "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 "
            "fim=2026-11-03T10:00:00-03:00 responsavel=Dr. Emmett Brown"
        )
        self.assertEqual(
            parsed,
            ParsedReservation(
                sala="sala-porao",
                inicio="2026-11-03T09:00:00-03:00",
                fim="2026-11-03T10:00:00-03:00",
                responsavel="Dr. Emmett Brown",
            ),
        )

    def test_parser_nao_valida_regras_de_horario_ou_dominio(self) -> None:
        # O parser apenas extrai a gramática fixa; regras de horário/sala pertencem ao servidor MCP.
        parsed = parse_reservation_command(
            "reservar sala=sala-delorean inicio=2026-11-03T22:00:00-03:00 "
            "fim=2026-11-03T07:00:00-03:00 responsavel=Doc"
        )
        self.assertEqual(parsed.sala, "sala-delorean")
        self.assertEqual(parsed.inicio, "2026-11-03T22:00:00-03:00")
        self.assertEqual(parsed.fim, "2026-11-03T07:00:00-03:00")
        self.assertEqual(parsed.responsavel, "Doc")

    async def test_entrada_malformada_rejeitada_sem_chamada_mcp_e_sem_criar_task(self) -> None:
        store = TaskStore()
        fake_host = FakeMCPHostForTasks()
        handler = AgenteRequestHandler(mcp_host=fake_host, task_store=store)  # type: ignore[arg-type]

        invalid_inputs = [
            "",
            "quero reservar a sala porao amanha as 9h",
            "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 fim=2026-11-03T10:00:00-03:00",
            "reservar sala= inicio=2026-11-03T09:00:00-03:00 fim=2026-11-03T10:00:00-03:00 responsavel=Doc",
            "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 fim=2026-11-03T10:00:00-03:00 responsavel=   ",
            "reservar inicio=2026-11-03T09:00:00-03:00 sala=sala-porao fim=2026-11-03T10:00:00-03:00 responsavel=Doc",
        ]
        for text in invalid_inputs:
            req = a2a_pb2.SendMessageRequest(
                message=build_message(role=a2a_pb2.ROLE_USER, text=text, message_id="msg-bad")
            )
            with self.assertRaises(InvalidParamsError):
                await handler.on_message_send(req, ServerCallContext())

        self.assertEqual(fake_host.calls, [])

    async def test_ids_context_ids_independentes_e_submitted_antes_de_working(self) -> None:
        store = TaskStore()
        fake_host = FakeMCPHostForTasks()
        fake_host.store_ref = store

        orig_create = store.create_submitted_task

        def _tracking_create(*args: Any, **kwargs: Any) -> Any:
            rec = orig_create(*args, **kwargs)
            fake_host.last_task_id = rec.public_task.id
            return rec

        store.create_submitted_task = _tracking_create  # type: ignore[method-assign]
        handler = AgenteRequestHandler(mcp_host=fake_host, task_store=store)  # type: ignore[arg-type]

        req1 = a2a_pb2.SendMessageRequest(
            message=build_message(
                role=a2a_pb2.ROLE_USER,
                text=(
                    "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 "
                    "fim=2026-11-03T10:00:00-03:00 responsavel=Doc Brown"
                ),
                message_id="msg-1",
            )
        )
        req2 = a2a_pb2.SendMessageRequest(
            message=build_message(
                role=a2a_pb2.ROLE_USER,
                text=(
                    "reservar sala=sala-aquario inicio=2026-11-03T11:00:00-03:00 "
                    "fim=2026-11-03T12:00:00-03:00 responsavel=Marty McFly"
                ),
                message_id="msg-2",
            )
        )

        task1 = await handler.on_message_send(req1, ServerCallContext())
        task2 = await handler.on_message_send(req2, ServerCallContext())

        assert isinstance(task1, a2a_pb2.Task)
        assert isinstance(task2, a2a_pb2.Task)
        self.assertNotEqual(task1.id, task2.id)
        self.assertNotEqual(task1.context_id, task2.context_id)
        self.assertNotEqual(task1.id, task1.context_id)
        self.assertNotEqual(task2.id, task2.context_id)

        # Durante a chamada MCP a Task estava em WORKING, tendo passado antes por SUBMITTED
        self.assertEqual(
            fake_host.observed_task_states_during_call,
            [a2a_pb2.TASK_STATE_WORKING, a2a_pb2.TASK_STATE_WORKING],
        )
        self.assertEqual(
            fake_host.observed_transitions_during_call[0],
            [a2a_pb2.TASK_STATE_SUBMITTED, a2a_pb2.TASK_STATE_WORKING],
        )

        rec1 = store.get_record(task1.id)
        assert rec1 is not None
        self.assertEqual(
            rec1.state_transitions,
            [
                a2a_pb2.TASK_STATE_SUBMITTED,
                a2a_pb2.TASK_STATE_WORKING,
                a2a_pb2.TASK_STATE_COMPLETED,
            ],
        )

        # A serialização pública não contém campos internos como state_transitions
        serialized = MessageToDict(task1)
        self.assertNotIn("stateTransitions", serialized)
        self.assertNotIn("traceparentOriginal", serialized)


class TestTaskTerminalGuardAndFailuresUS2(unittest.IsolatedAsyncioTestCase):
    """Testes unitários de GetTask sem mutação, estados terminais imutáveis e falhas técnicas (T019)."""

    async def test_get_task_retorna_copia_sem_mutar_registro_e_erro_para_desconhecida(self) -> None:
        store = TaskStore()
        fake_host = FakeMCPHostForTasks()
        handler = AgenteRequestHandler(mcp_host=fake_host, task_store=store)  # type: ignore[arg-type]

        send_req = a2a_pb2.SendMessageRequest(
            message=build_message(
                role=a2a_pb2.ROLE_USER,
                text=(
                    "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 "
                    "fim=2026-11-03T10:00:00-03:00 responsavel=Doc"
                ),
                message_id="msg-get-1",
            )
        )
        created = await handler.on_message_send(send_req, ServerCallContext())
        assert isinstance(created, a2a_pb2.Task)

        fetched = await handler.on_get_task(a2a_pb2.GetTaskRequest(id=created.id), ServerCallContext())
        assert fetched is not None
        self.assertEqual(fetched.id, created.id)
        self.assertEqual(fetched.context_id, created.context_id)
        self.assertEqual(fetched.status.state, a2a_pb2.TASK_STATE_COMPLETED)
        self.assertEqual(len(fetched.artifacts), 1)

        # Mutar a cópia retornada por GetTask não altera o registro interno
        fetched.status.state = a2a_pb2.TASK_STATE_WORKING
        del fetched.artifacts[:]
        del fetched.history[:]

        fetched_again = await handler.on_get_task(a2a_pb2.GetTaskRequest(id=created.id), ServerCallContext())
        assert fetched_again is not None
        self.assertEqual(fetched_again.status.state, a2a_pb2.TASK_STATE_COMPLETED)
        self.assertEqual(len(fetched_again.artifacts), 1)
        self.assertEqual(len(fetched_again.history), 2)

        with self.assertRaises(TaskNotFoundError):
            await handler.on_get_task(a2a_pb2.GetTaskRequest(id="task-inexistente"), ServerCallContext())

    async def test_estados_terminais_imutaveis_recusam_send_message_sem_chamar_mcp(self) -> None:
        store = TaskStore()
        fake_host = FakeMCPHostForTasks()
        handler = AgenteRequestHandler(mcp_host=fake_host, task_store=store)  # type: ignore[arg-type]

        # 1. Task COMPLETED
        send_req = a2a_pb2.SendMessageRequest(
            message=build_message(
                role=a2a_pb2.ROLE_USER,
                text=(
                    "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 "
                    "fim=2026-11-03T10:00:00-03:00 responsavel=Doc"
                ),
            )
        )
        completed_task = await handler.on_message_send(send_req, ServerCallContext())
        assert isinstance(completed_task, a2a_pb2.Task)
        self.assertEqual(len(fake_host.calls), 1)

        # 2. Task FAILED e Task CANCELED criadas no store
        failed_rec = store.create_submitted_task(
            build_message(role=a2a_pb2.ROLE_USER, text="reservar ..."),
            "reservar ...",
        )
        store.transition_to_working(failed_rec.public_task.id)
        store.fail_task(failed_rec.public_task.id, "Sala inexistente: sala-delorean")

        canceled_rec = store.create_submitted_task(
            build_message(role=a2a_pb2.ROLE_USER, text="reservar ..."),
            "reservar ...",
        )
        store.transition_to_working(canceled_rec.public_task.id)
        store.cancel_task(canceled_rec.public_task.id, "Reserva recusada pelo usuario.")

        for terminal_id in (
            completed_task.id,
            failed_rec.public_task.id,
            canceled_rec.public_task.id,
        ):
            with self.assertRaises(TerminalTaskStateError):
                store.transition_to_working(terminal_id)
            with self.assertRaises(InvalidParamsError):
                await handler.on_message_send(
                    a2a_pb2.SendMessageRequest(
                        message=build_message(
                            role=a2a_pb2.ROLE_USER,
                            text=(
                                "reservar sala=sala-aquario inicio=2026-11-03T10:00:00-03:00 "
                                "fim=2026-11-03T11:00:00-03:00 responsavel=Doc"
                            ),
                            task_id=terminal_id,
                        )
                    ),
                    ServerCallContext(),
                )

        # Nenhuma chamada MCP adicional foi feita nas tentativas de reabrir Tasks terminais
        self.assertEqual(len(fake_host.calls), 1)

    async def test_falha_tecnica_ou_protocolo_apos_criar_task_vira_failed_sem_artifact_e_sem_vazar_segredo(
        self,
    ) -> None:
        class FailingMCPHost(FakeMCPHostForTasks):
            async def call_tool_raw(self, *args: Any, **kwargs: Any) -> types.CallToolResult:
                self.calls.append(("reservar_sala", {}, None))
                raise MCPError(
                    code=-32602,
                    message="Invalid requestState token: v1.secret-opaque-token-should-never-leak",
                )

        store = TaskStore()
        failing_host = FailingMCPHost()
        handler = AgenteRequestHandler(mcp_host=failing_host, task_store=store)  # type: ignore[arg-type]

        req = a2a_pb2.SendMessageRequest(
            message=build_message(
                role=a2a_pb2.ROLE_USER,
                text=(
                    "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 "
                    "fim=2026-11-03T10:00:00-03:00 responsavel=Doc"
                ),
            )
        )
        task = await handler.on_message_send(req, ServerCallContext())
        assert isinstance(task, a2a_pb2.Task)
        self.assertEqual(task.status.state, a2a_pb2.TASK_STATE_FAILED)
        self.assertEqual(len(task.artifacts), 0)
        self.assertEqual(task.status.message.parts[0].text, TECHNICAL_MCP_FAILURE_MESSAGE)

        serialized_json = json.dumps(MessageToDict(task))
        self.assertIn(TECHNICAL_MCP_FAILURE_MESSAGE, serialized_json)
        self.assertNotIn("v1.secret-opaque-token-should-never-leak", serialized_json)


if __name__ == "__main__":
    unittest.main()
