"""Testes do host MCP moderno (SDK v2.3.0, revisão 2026-07-28, sessão raw e transporte HTTP observado)."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Any, Callable
import unittest

from a2a.server.context import ServerCallContext
from a2a.types import a2a_pb2
from google.protobuf.json_format import MessageToJson
import mcp_types as types

from ponte_agente.app import AgenteSettings, build_agent_card
from ponte_agente.handler import AgenteRequestHandler
from ponte_agente.mcp_host import (
    DefensiveElicitationCalledError,
    MCPDiscoveryError,
    MCPHost,
    defensive_elicitation_callback,
)
from ponte_agente.tasks import RequestTrace, TaskStore


class RecordedHTTPRequest:
    """Registro de uma requisição HTTP recebida pelo servidor MCP de teste."""

    def __init__(self, headers: dict[str, str], body: dict[str, Any]) -> None:
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.raw_headers = dict(headers)
        self.body = body


class ObservingMCPHTTPServer:
    """Servidor HTTP local que registra requests do SDK MCP e devolve respostas JSON-RPC controladas."""

    def __init__(self, responder: Callable[[RecordedHTTPRequest], tuple[int, dict[str, Any]]]) -> None:
        self._responder = responder
        self.requests: list[RecordedHTTPRequest] = []
        self._lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if self._httpd is None:
            raise RuntimeError("Servidor de observação não iniciado")
        host, port = self._httpd.server_address
        return f"http://{host}:{port}/mcp"

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8")
                payload = json.loads(raw) if raw else {}
                rec = RecordedHTTPRequest(dict(self.headers.items()), payload)
                with outer._lock:
                    outer.requests.append(rec)
                try:
                    status, response_body = outer._responder(rec)
                except ConnectionResetError:
                    self.close_connection = True
                    return
                encoded = json.dumps(response_body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            kwargs={"poll_interval": 0.02},
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None


def _default_mcp_responder(req: RecordedHTTPRequest) -> tuple[int, dict[str, Any]]:
    rpc_id = req.body.get("id")
    method = req.body.get("method")
    if method == "tools/list":
        return 200, {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "resultType": "complete",
                "cacheScope": "public",
                "ttlMs": 0,
                "tools": [
                    {
                        "name": "reservar_sala",
                        "description": "Reserva uma sala.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "sala": {"type": "string"},
                                "inicio": {"type": "string"},
                                "fim": {"type": "string"},
                                "responsavel": {"type": "string"},
                            },
                            "required": ["sala", "inicio", "fim", "responsavel"],
                        },
                    }
                ],
            },
        }
    if method == "resources/read":
        return 200, {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "resultType": "complete",
                "cacheScope": "public",
                "ttlMs": 0,
                "contents": [
                    {
                        "uri": "politica://uso",
                        "mimeType": "text/markdown",
                        "text": "versao: 2026-11-01\n\n- Regra 1\n",
                    }
                ],
            },
        }
    if method == "tools/call":
        params = req.body.get("params") or {}
        args = params.get("arguments") or {}
        if args.get("sala") == "sala-garagem":
            return 200, {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "resultType": "input_required",
                    "inputRequests": {
                        "elicit-1": {
                            "method": "elicitation/create",
                            "params": {
                                "mode": "form",
                                "message": "A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa.",
                                "requestedSchema": {
                                    "type": "object",
                                    "properties": {
                                        "sala": {
                                            "type": "string",
                                            "enum": ["sala-fusca", "sala-mirante"],
                                        }
                                    },
                                    "required": ["sala"],
                                },
                            },
                        }
                    },
                    "requestState": "v1.opaque-sentinel-token",
                },
            }
        return 200, {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "resultType": "complete",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "reserva": "res-0003",
                                "reservado": True,
                                "sala": args.get("sala", "sala-porao"),
                                "inicio": args.get("inicio", "2026-11-03T09:00:00-03:00"),
                                "fim": args.get("fim", "2026-11-03T10:00:00-03:00"),
                                "responsavel": args.get("responsavel", "Doc"),
                                "politica": "2026-11-01",
                            }
                        ),
                    }
                ],
                "structuredContent": {
                    "reserva": "res-0003",
                    "reservado": True,
                    "sala": args.get("sala", "sala-porao"),
                    "inicio": args.get("inicio", "2026-11-03T09:00:00-03:00"),
                    "fim": args.get("fim", "2026-11-03T10:00:00-03:00"),
                    "responsavel": args.get("responsavel", "Doc"),
                    "politica": "2026-11-01",
                },
            },
        }
    return 400, {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": -32601, "message": "Method not found"},
    }


class TestMCPHostFoundational(unittest.IsolatedAsyncioTestCase):
    """Testes da fundação do cliente MCP moderno (T005/T006)."""

    async def asyncSetUp(self) -> None:
        self.server = ObservingMCPHTTPServer(_default_mcp_responder)
        self.server.start()

    async def asyncTearDown(self) -> None:
        self.server.stop()

    async def test_metadados_obrigatorios_e_headers_espelhados_em_cada_request(self) -> None:
        trace = RequestTrace("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        async with MCPHost(self.server.url) as host:
            await host.list_tools_page(trace=trace)
            await host.read_resource("politica://uso", trace=trace)
            await host.call_tool_raw(
                "reservar_sala",
                {
                    "sala": "sala-porao",
                    "inicio": "2026-11-03T09:00:00-03:00",
                    "fim": "2026-11-03T10:00:00-03:00",
                    "responsavel": "Doc",
                },
                trace=trace,
            )

        self.assertEqual(len(self.server.requests), 4)
        expected_methods = ["tools/list", "resources/read", "tools/list", "tools/call"]
        expected_names = [None, "politica://uso", None, "reservar_sala"]

        for req, exp_method, exp_name in zip(self.server.requests, expected_methods, expected_names, strict=True):
            self.assertEqual(req.body.get("method"), exp_method)
            params = req.body.get("params") or {}
            meta = params.get("_meta") or {}
            self.assertEqual(meta.get("io.modelcontextprotocol/protocolVersion"), "2026-07-28")
            self.assertIn("io.modelcontextprotocol/clientCapabilities", meta)
            caps = meta["io.modelcontextprotocol/clientCapabilities"]
            self.assertIn("elicitation", caps)
            self.assertEqual(caps["elicitation"].get("form"), {})

            tp = meta.get("traceparent", "")
            self.assertTrue(tp.startswith("00-4bf92f3577b34da6a3ce929d0e0e4736-"))

            self.assertEqual(req.headers.get("mcp-protocol-version"), "2026-07-28")
            self.assertEqual(req.headers.get("mcp-method"), exp_method)
            if exp_name is None:
                self.assertNotIn("mcp-name", req.headers)
            else:
                self.assertEqual(req.headers.get("mcp-name"), exp_name)

    async def test_callback_defensivo_nunca_executado_e_input_required_cru(self) -> None:
        callback_calls: list[Any] = []

        async def _instrumented_callback(ctx: Any, params: Any) -> Any:
            callback_calls.append((ctx, params))
            return await defensive_elicitation_callback(ctx, params)

        async with MCPHost(self.server.url, elicitation_callback=_instrumented_callback) as host:
            result = await host.call_tool_raw(
                "reservar_sala",
                {
                    "sala": "sala-garagem",
                    "inicio": "2026-11-03T14:00:00-03:00",
                    "fim": "2026-11-03T15:00:00-03:00",
                    "responsavel": "Marty",
                },
            )

        self.assertEqual(callback_calls, [])
        self.assertEqual([req.body["method"] for req in self.server.requests], ["tools/list", "tools/call"])
        self.assertIsInstance(result, types.InputRequiredResult)
        assert isinstance(result, types.InputRequiredResult)
        self.assertEqual(result.result_type, "input_required")
        self.assertEqual(result.request_state, "v1.opaque-sentinel-token")
        self.assertIn("elicit-1", result.input_requests)

        with self.assertRaises(DefensiveElicitationCalledError):
            await defensive_elicitation_callback(None, None)  # type: ignore[arg-type]

    async def test_gate_fr008_declara_form_em_cada_request_com_capabilities_adicionais(self) -> None:
        """Exige form no wire de cada operação sem restringir capabilities adicionais (FR-008)."""
        async with MCPHost(self.server.url) as host:
            await host.list_tools_page()
            await host.read_resource("politica://uso")
            await host.call_tool_raw(
                "reservar_sala",
                {
                    "sala": "sala-porao",
                    "inicio": "2026-11-03T09:00:00-03:00",
                    "fim": "2026-11-03T10:00:00-03:00",
                    "responsavel": "Doc",
                },
            )

        self.assertEqual(
            [req.body.get("method") for req in self.server.requests],
            ["tools/list", "resources/read", "tools/list", "tools/call"],
        )
        for req in self.server.requests:
            with self.subTest(method=req.body.get("method")):
                meta = (req.body.get("params") or {}).get("_meta") or {}
                capabilities = meta.get("io.modelcontextprotocol/clientCapabilities")
                self.assertIsInstance(capabilities, dict)
                elicitation = capabilities.get("elicitation")
                self.assertIsInstance(elicitation, dict)
                self.assertIn("form", elicitation)
                self.assertIsInstance(elicitation["form"], dict)


class TestMCPHostDiscoveryTraceAndBoundaryUS3(unittest.IsolatedAsyncioTestCase):
    """Testes US3 de descoberta paginada, política dinâmica, isolamento de trace e input_required (T025/T027)."""

    async def test_ordem_tools_list_paginado_resources_read_e_tools_call_com_headers_e_meta(self) -> None:
        def _paginated_responder(req: RecordedHTTPRequest) -> tuple[int, dict[str, Any]]:
            rpc_id = req.body.get("id")
            method = req.body.get("method")
            params = req.body.get("params") or {}
            if method == "tools/list":
                cursor = params.get("cursor")
                if cursor is None:
                    return 200, {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "result": {
                            "resultType": "complete",
                            "cacheScope": "public",
                            "ttlMs": 0,
                            "nextCursor": "cursor-pagina-2",
                            "tools": [
                                {
                                    "name": "listar_salas",
                                    "description": "Lista salas.",
                                    "inputSchema": {"type": "object", "properties": {}},
                                }
                            ],
                        },
                    }
                if cursor == "cursor-pagina-2":
                    return 200, {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "result": {
                            "resultType": "complete",
                            "cacheScope": "public",
                            "ttlMs": 0,
                            "tools": [
                                {
                                    "name": "reservar_sala",
                                    "description": "Reserva sala.",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "sala": {"type": "string"},
                                            "inicio": {"type": "string"},
                                            "fim": {"type": "string"},
                                            "responsavel": {"type": "string"},
                                        },
                                        "required": ["sala", "inicio", "fim", "responsavel"],
                                    },
                                }
                            ],
                        },
                    }
            return _default_mcp_responder(req)

        server = ObservingMCPHTTPServer(_paginated_responder)
        server.start()
        try:
            trace = RequestTrace("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
            async with MCPHost(server.url) as host:
                snapshot, result = await host.call_discovered_reservation_tool(
                    {
                        "sala": "sala-porao",
                        "inicio": "2026-11-03T09:00:00-03:00",
                        "fim": "2026-11-03T10:00:00-03:00",
                        "responsavel": "Doc",
                    },
                    trace=trace,
                )

            self.assertIn("listar_salas", snapshot.tools_by_name)
            self.assertIn("reservar_sala", snapshot.tools_by_name)
            self.assertEqual(snapshot.reservation_tool.name, "reservar_sala")
            self.assertIsInstance(result, types.CallToolResult)

            # A operação de tool redescobre as páginas para validar seu outputSchema no SDK.
            self.assertEqual(len(server.requests), 6)
            observed_methods = [r.body.get("method") for r in server.requests]
            self.assertEqual(
                observed_methods,
                ["tools/list", "tools/list", "resources/read", "tools/list", "tools/list", "tools/call"],
            )
            self.assertIsNone((server.requests[0].body.get("params") or {}).get("cursor"))
            self.assertEqual(
                (server.requests[1].body.get("params") or {}).get("cursor"),
                "cursor-pagina-2",
            )

            expected_names = [None, None, "politica://uso", None, None, "reservar_sala"]
            for req, exp_method, exp_name in zip(server.requests, observed_methods, expected_names, strict=True):
                meta = (req.body.get("params") or {}).get("_meta") or {}
                self.assertEqual(meta.get("io.modelcontextprotocol/protocolVersion"), "2026-07-28")
                self.assertIn("io.modelcontextprotocol/clientCapabilities", meta)
                self.assertTrue(
                    str(meta.get("traceparent", "")).startswith("00-4bf92f3577b34da6a3ce929d0e0e4736-")
                )
                self.assertEqual(req.headers.get("mcp-protocol-version"), "2026-07-28")
                self.assertEqual(req.headers.get("mcp-method"), exp_method)
                if exp_name is None:
                    self.assertNotIn("mcp-name", req.headers)
                else:
                    self.assertEqual(req.headers.get("mcp-name"), exp_name)
        finally:
            server.stop()

    async def test_tool_de_reserva_ausente_falha_sem_fallback_local(self) -> None:
        def _missing_tool_responder(req: RecordedHTTPRequest) -> tuple[int, dict[str, Any]]:
            rpc_id = req.body.get("id")
            if req.body.get("method") == "tools/list":
                return 200, {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "resultType": "complete",
                        "cacheScope": "public",
                        "ttlMs": 0,
                        "tools": [
                            {
                                "name": "listar_salas",
                                "description": "Lista salas.",
                                "inputSchema": {"type": "object", "properties": {}},
                            }
                        ],
                    },
                }
            return _default_mcp_responder(req)

        server = ObservingMCPHTTPServer(_missing_tool_responder)
        server.start()
        try:
            async with MCPHost(server.url) as host:
                with self.assertRaises(MCPDiscoveryError):
                    await host.call_discovered_reservation_tool(
                        {
                            "sala": "sala-porao",
                            "inicio": "2026-11-03T09:00:00-03:00",
                            "fim": "2026-11-03T10:00:00-03:00",
                            "responsavel": "Doc",
                        }
                    )

            # Nenhum tools/call ou resources/read deve ocorrer após falha na descoberta da tool
            self.assertEqual([r.body.get("method") for r in server.requests], ["tools/list"])
        finally:
            server.stop()

    async def test_versao_da_politica_vem_da_primeira_linha_do_resource_e_nao_do_resultado_da_tool(self) -> None:
        def _custom_policy_responder(req: RecordedHTTPRequest) -> tuple[int, dict[str, Any]]:
            rpc_id = req.body.get("id")
            method = req.body.get("method")
            if method == "resources/read":
                return 200, {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "resultType": "complete",
                        "cacheScope": "public",
                        "ttlMs": 0,
                        "contents": [
                            {
                                "uri": "politica://uso",
                                "mimeType": "text/markdown",
                                "text": "versao: 2027-08-15-fixture\n\n- Regra de teste sem tocar em dados/\n",
                            }
                        ],
                    },
                }
            if method == "tools/call":
                params = req.body.get("params") or {}
                args = params.get("arguments") or {}
                payload = {
                    "reserva": "res-0099",
                    "reservado": True,
                    "sala": args.get("sala", "sala-porao"),
                    "inicio": args.get("inicio", "2026-11-03T09:00:00-03:00"),
                    "fim": args.get("fim", "2026-11-03T10:00:00-03:00"),
                    "responsavel": args.get("responsavel", "Doc"),
                    "politica": "1999-01-01-valor-ignorado-da-tool",
                }
                return 200, {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "resultType": "complete",
                        "content": [{"type": "text", "text": json.dumps(payload)}],
                        "structuredContent": payload,
                    },
                }
            return _default_mcp_responder(req)

        server = ObservingMCPHTTPServer(_custom_policy_responder)
        server.start()
        try:
            store = TaskStore()
            async with MCPHost(server.url) as host:
                handler = AgenteRequestHandler(mcp_host=host, task_store=store)
                req_pb = a2a_pb2.SendMessageRequest(
                    message=a2a_pb2.Message(
                        message_id="msg-pol-1",
                        role=a2a_pb2.Role.ROLE_USER,
                        parts=[
                            a2a_pb2.Part(
                                text=(
                                    "reservar sala=sala-porao "
                                    "inicio=2026-11-03T09:00:00-03:00 "
                                    "fim=2026-11-03T10:00:00-03:00 "
                                    "responsavel=Doc"
                                )
                            )
                        ],
                    )
                )
                ctx = ServerCallContext(state={"traceparent": None})
                task = await handler.on_message_send(req_pb, ctx)

            assert isinstance(task, a2a_pb2.Task)
            self.assertEqual(task.status.state, a2a_pb2.TaskState.TASK_STATE_COMPLETED)
            self.assertEqual(len(task.artifacts), 1)
            artifact_payload = json.loads(task.artifacts[0].parts[0].text)
            self.assertEqual(artifact_payload["politica"], "2027-08-15-fixture")
            self.assertNotEqual(artifact_payload["politica"], "1999-01-01-valor-ignorado-da-tool")
        finally:
            server.stop()

    async def test_mesmo_cliente_multiplas_chamadas_com_traces_diferentes_e_ausente_sem_heranca(self) -> None:
        server = ObservingMCPHTTPServer(_default_mcp_responder)
        server.start()
        try:
            trace_a = RequestTrace("00-11111111111111111111111111111111-aaaaaaaaaaaaaaaa-01")
            trace_b = RequestTrace("00-22222222222222222222222222222222-bbbbbbbbbbbbbbbb-01")

            async with MCPHost(server.url) as host:
                await host.call_discovered_reservation_tool(
                    {
                        "sala": "sala-porao",
                        "inicio": "2026-11-03T09:00:00-03:00",
                        "fim": "2026-11-03T10:00:00-03:00",
                        "responsavel": "Doc",
                    },
                    trace=trace_a,
                )
                await host.call_discovered_reservation_tool(
                    {
                        "sala": "sala-aquario",
                        "inicio": "2026-11-03T10:00:00-03:00",
                        "fim": "2026-11-03T11:00:00-03:00",
                        "responsavel": "Marty",
                    },
                    trace=trace_b,
                )
                await host.call_discovered_reservation_tool(
                    {
                        "sala": "sala-fusca",
                        "inicio": "2026-11-03T11:00:00-03:00",
                        "fim": "2026-11-03T12:00:00-03:00",
                        "responsavel": "Lorraine",
                    },
                    trace=None,
                )

            # 1ª operação: catálogo + política + catálogo da sessão + tool (trace_a)
            # 2ª operação: catálogo da sessão + tool (trace_b, HostSnapshot em cache)
            # 3ª operação: catálogo da sessão + tool (sem herdar trace_a nem trace_b)
            self.assertEqual(len(server.requests), 8)
            for req in server.requests[:4]:
                meta = (req.body.get("params") or {}).get("_meta") or {}
                self.assertTrue(
                    str(meta.get("traceparent", "")).startswith("00-11111111111111111111111111111111-")
                )

            meta_second = (server.requests[5].body.get("params") or {}).get("_meta") or {}
            self.assertTrue(
                str(meta_second.get("traceparent", "")).startswith("00-22222222222222222222222222222222-")
            )

            meta_third = (server.requests[7].body.get("params") or {}).get("_meta") or {}
            self.assertNotIn("traceparent", meta_third)
        finally:
            server.stop()

    async def test_input_required_com_marcador_opaco_sem_callback_e_sem_exposicao_publica(self) -> None:
        opaque_marker = "v1.OPAQUE_SENTINEL_MARKER_NOT_BASE64_!@#$%^&*()"

        def _opaque_input_required_responder(req: RecordedHTTPRequest) -> tuple[int, dict[str, Any]]:
            rpc_id = req.body.get("id")
            if req.body.get("method") == "tools/call":
                return 200, {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "resultType": "input_required",
                        "inputRequests": {
                            "elicit-opaque-1": {
                                "method": "elicitation/create",
                                "params": {
                                    "mode": "form",
                                    "message": "Escolha uma sala alternativa.",
                                    "requestedSchema": {
                                        "type": "object",
                                        "properties": {
                                            "sala": {
                                                "type": "string",
                                                "enum": ["sala-fusca", "sala-mirante"],
                                            }
                                        },
                                        "required": ["sala"],
                                    },
                                },
                            }
                        },
                        "requestState": opaque_marker,
                    },
                }
            return _default_mcp_responder(req)

        server = ObservingMCPHTTPServer(_opaque_input_required_responder)
        server.start()
        try:
            callback_invocations: list[Any] = []

            async def _instrumented_cb(ctx: Any, params: Any) -> Any:
                callback_invocations.append((ctx, params))
                return await defensive_elicitation_callback(ctx, params)

            store = TaskStore()
            async with MCPHost(server.url, elicitation_callback=_instrumented_cb) as host:
                handler = AgenteRequestHandler(mcp_host=host, task_store=store)
                req_pb = a2a_pb2.SendMessageRequest(
                    message=a2a_pb2.Message(
                        message_id="msg-opaque-1",
                        role=a2a_pb2.Role.ROLE_USER,
                        parts=[
                            a2a_pb2.Part(
                                text=(
                                    "reservar sala=sala-garagem "
                                    "inicio=2026-11-03T14:00:00-03:00 "
                                    "fim=2026-11-03T15:00:00-03:00 "
                                    "responsavel=Marty"
                                )
                            )
                        ],
                    )
                )
                ctx = ServerCallContext(state={"traceparent": None})
                public_task = await handler.on_message_send(req_pb, ctx)
                assert isinstance(public_task, a2a_pb2.Task)
                fetched_task = await handler.on_get_task(
                    a2a_pb2.GetTaskRequest(id=public_task.id),
                    ctx,
                )

            # 1. Nenhum callback automático nem retry automático ocorreu
            self.assertEqual(callback_invocations, [])
            tool_calls = [r for r in server.requests if r.body.get("method") == "tools/call"]
            self.assertEqual(len(tool_calls), 1)

            # 2. O resultado cru InputRequiredResult permanece intacto internamente no registro privado para a 004
            record = store.get_record(public_task.id)
            self.assertIsNotNone(record)
            assert record is not None
            self.assertIsInstance(record.raw_input_required, types.InputRequiredResult)
            assert isinstance(record.raw_input_required, types.InputRequiredResult)
            self.assertEqual(record.raw_input_required.request_state, opaque_marker)

            # 3. Nenhum serializer público (Task de SendMessage, Task de GetTask, AgentCard) contém o marcador opaco
            serialized_send_task = MessageToJson(public_task)
            serialized_get_task = MessageToJson(fetched_task) if fetched_task is not None else ""
            serialized_card = MessageToJson(build_agent_card(AgenteSettings()))

            for public_json in (serialized_send_task, serialized_get_task, serialized_card):
                self.assertNotIn(opaque_marker, public_json)
                self.assertNotIn("OPAQUE_SENTINEL_MARKER", public_json)
                self.assertNotIn("requestState", public_json)
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
