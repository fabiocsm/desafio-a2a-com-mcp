"""Regressões para validação, limites e capabilities na fronteira MCP."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from mcp.server.transport_security import DEFAULT_MAX_REQUEST_BODY_SIZE

from ponte_mcp.app import criar_asgi_app, criar_mcp_server
from test_mcp_http import (
    PROTOCOL_VERSION,
    VALID_SECRET_HEX,
    build_mcp_headers,
    build_mcp_meta,
    post_raw_json,
    running_mcp_server,
)


class TestHeadersHTTP(unittest.TestCase):
    def test_headers_ausentes_legados_e_divergentes_nao_executam_reserva(self) -> None:
        args = {
            "sala": "sala-aquario",
            "inicio": "2026-11-03T09:00:00-03:00",
            "fim": "2026-11-03T10:00:00-03:00",
        }
        operations = (
            ("tools/list", {}, None),
            ("tools/call", {"name": "reservar_sala", "arguments": {**args, "responsavel": "Doc"}}, "reservar_sala"),
            ("resources/read", {"uri": "politica://uso"}, "politica://uso"),
        )
        with running_mcp_server() as srv:
            for method, params, name in operations:
                for version in (None, "2025-03-26", PROTOCOL_VERSION):
                    for mismatch in ("version", "method", "name", "method_missing", "name_missing"):
                        if mismatch.startswith("name") and name is None:
                            continue
                        with self.subTest(method=method, version=version, mismatch=mismatch):
                            headers = build_mcp_headers(method, name, version)
                            if mismatch == "version" and version == PROTOCOL_VERSION:
                                headers.pop("MCP-Protocol-Version")
                            elif mismatch == "method":
                                headers["Mcp-Method"] = "resources/list"
                            elif mismatch == "name":
                                headers["Mcp-Name"] = "divergente"
                            elif mismatch == "method_missing":
                                headers.pop("Mcp-Method")
                            elif mismatch == "name_missing":
                                headers.pop("Mcp-Name")
                            status, response, _ = srv.request(method, params, headers=headers)
                            self.assertEqual(status, 400)
                            self.assertEqual(response["error"]["code"], -32020)

            status, response, _ = srv.request(
                "tools/call", {"name": "consultar_disponibilidade", "arguments": args},
                name="consultar_disponibilidade",
            )
            self.assertEqual(status, 200)
            self.assertTrue(response["result"]["structuredContent"]["livre"])

    def test_metadados_ausentes_precedem_headers_e_envelope_invalido_nao_crasha(self) -> None:
        with running_mcp_server() as srv:
            for version in (None, "2025-03-26", PROTOCOL_VERSION):
                status, response, _ = srv.request(
                    "tools/list", include_meta=False,
                    headers=build_mcp_headers("resources/list", protocol_version=version),
                )
                self.assertEqual(status, 400)
                self.assertEqual(response["error"]["code"], -32602)
            for method in ([], {}):
                status, response, _ = post_raw_json(
                    srv.url,
                    {"jsonrpc": "2.0", "id": "invalido", "method": method, "params": {"_meta": build_mcp_meta()}},
                    build_mcp_headers("tools/list"),
                )
                self.assertEqual(status, 400)
                self.assertIn("error", response)


class TestSubscriptions(unittest.TestCase):
    def test_capabilities_modernas_mantem_tools_resources_sem_subscriptions(self) -> None:
        server = criar_mcp_server(secret_hex=VALID_SECRET_HEX)
        # Inspeção do SDK: MCPServer não publica a projeção de capabilities.
        capabilities = server._lowlevel_server.get_capabilities(protocol_version=PROTOCOL_VERSION)
        self.assertIsNotNone(capabilities.tools)
        self.assertIsNotNone(capabilities.resources)
        self.assertFalse(capabilities.tools.list_changed)
        self.assertFalse(capabilities.resources.list_changed)
        self.assertFalse(capabilities.resources.subscribe)

    def test_subscriptions_listen_rejeitado_sem_stream(self) -> None:
        with running_mcp_server() as srv:
            status, response, _ = post_raw_json(
                srv.url,
                {"jsonrpc": "2.0", "id": "listen", "method": "subscriptions/listen", "params": {"notifications": {}, "_meta": build_mcp_meta()}},
                build_mcp_headers("subscriptions/listen"),
                timeout=1,
            )
            self.assertEqual(status, 404)
            self.assertEqual(response["error"]["code"], -32601)


class TestBodyLimit(unittest.IsolatedAsyncioTestCase):
    async def check_limit(self, *, declared: bool) -> None:
        app = criar_asgi_app(secret_hex=VALID_SECRET_HEX)
        scope = {
            "type": "http", "method": "POST", "path": "/mcp",
            "headers": [(b"content-length", str(DEFAULT_MAX_REQUEST_BODY_SIZE + 1).encode())] if declared else [],
        }
        reads = 0
        messages = []

        async def receive():
            nonlocal reads
            reads += 1
            if declared or reads > 2:
                raise AssertionError("Corpo excedente não deve ser recebido")
            return {
                "type": "http.request",
                "body": b"x" * (DEFAULT_MAX_REQUEST_BODY_SIZE if reads == 1 else 1),
                "more_body": True,
            }

        async def send(message):
            messages.append(message)

        with patch("ponte_mcp.entrada.json.loads", side_effect=AssertionError("Não deve fazer parse")):
            await app(scope, receive, send)
        self.assertEqual(reads, 0 if declared else 2)
        self.assertEqual(messages[0]["status"], 413)

    async def test_content_length_rejeitado_antes_receive(self) -> None:
        await self.check_limit(declared=True)

    async def test_chunks_interrompidos_ao_cruzar_limite(self) -> None:
        await self.check_limit(declared=False)
