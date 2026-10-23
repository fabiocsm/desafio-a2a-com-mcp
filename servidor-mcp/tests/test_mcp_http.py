"""Suporte e testes de integração HTTP real para o servidor MCP de salas."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterator
import unittest
import urllib.error
import urllib.request

ROOT_DIR = Path(__file__).resolve().parents[2]
WIRE_DIR = ROOT_DIR / "exemplos" / "wire"
DADOS_DIR = ROOT_DIR / "dados"

PROTOCOL_VERSION = "2026-07-28"
DEFAULT_CAPABILITIES: dict[str, Any] = {"elicitation": {"form": {}}}
VALID_SECRET_HEX = "a1" * 32


def find_free_port(host: str = "127.0.0.1") -> int:
    """Encontra uma porta TCP livre em loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def load_wire_example(filename: str) -> dict[str, Any]:
    """Lê um exemplo de wire preservando o arquivo original."""
    path = WIRE_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def load_wire_request_body(filename: str) -> dict[str, Any]:
    """Retorna uma cópia profunda apenas de request.body do exemplo."""
    example = load_wire_example(filename)
    return json.loads(json.dumps(example["request"]["body"]))


def build_mcp_headers(
    method: str | None = None,
    name: str | None = None,
    protocol_version: str | None = PROTOCOL_VERSION,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Monta cabeçalhos HTTP completos para Streamable HTTP MCP."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if protocol_version is not None:
        headers["MCP-Protocol-Version"] = protocol_version
    if method is not None:
        headers["Mcp-Method"] = method
    if name is not None:
        headers["Mcp-Name"] = name
    if extra:
        headers.update(extra)
    return headers


def build_mcp_meta(
    *,
    protocol_version: str | None = PROTOCOL_VERSION,
    client_capabilities: dict[str, Any] | None = DEFAULT_CAPABILITIES,
    traceparent: str | None = None,
    client_info: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Monta o bloco _meta de um request MCP."""
    meta: dict[str, Any] = {}
    if protocol_version is not None:
        meta["io.modelcontextprotocol/protocolVersion"] = protocol_version
    if client_info is not None:
        meta["io.modelcontextprotocol/clientInfo"] = client_info
    if client_capabilities is not None:
        meta["io.modelcontextprotocol/clientCapabilities"] = client_capabilities
    if traceparent is not None:
        meta["traceparent"] = traceparent
    return meta


def post_raw_json(
    url: str,
    body: dict[str, Any] | bytes | str,
    headers: dict[str, str],
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any], str]:
    """Envia POST HTTP com corpo JSON e retorna (status_http, json_decodificado, texto_bruto)."""
    if isinstance(body, dict):
        payload = json.dumps(body).encode("utf-8")
    elif isinstance(body, str):
        payload = body.encode("utf-8")
    else:
        payload = body

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            status = int(resp.status)
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8")
        status = int(err.code)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"_raw": raw}
    return status, parsed, raw


class MCPServerSubprocess:
    """Gerencia um subprocesso real de `python -m ponte_mcp` com captura de stderr."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int | None = None,
        secret: str | None = VALID_SECRET_HEX,
        cwd: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.host = host
        self.port = port if port is not None else find_free_port(host)
        self.secret = secret
        self.cwd = cwd or ROOT_DIR
        self.extra_env = extra_env or {}
        self._stderr_file: tempfile.NamedTemporaryFile[str] | None = None
        self._stdout_file: tempfile.NamedTemporaryFile[str] | None = None
        self.proc: subprocess.Popen[bytes] | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/mcp"

    def start(self, timeout: float = 10.0) -> None:
        self._stderr_file = tempfile.NamedTemporaryFile(
            mode="w+", encoding="utf-8", prefix="ponte_mcp_stderr_", delete=False
        )
        self._stdout_file = tempfile.NamedTemporaryFile(
            mode="w+", encoding="utf-8", prefix="ponte_mcp_stdout_", delete=False
        )
        env = os.environ.copy()
        env["MCP_HOST"] = self.host
        env["MCP_PORT"] = str(self.port)
        env["PYTHONUNBUFFERED"] = "1"
        if self.secret is None:
            env.pop("REQUEST_STATE_SECRET", None)
        else:
            env["REQUEST_STATE_SECRET"] = self.secret
        env.update(self.extra_env)

        self.proc = subprocess.Popen(
            [sys.executable, "-m", "ponte_mcp"],
            cwd=str(self.cwd),
            env=env,
            stdout=self._stdout_file,
            stderr=self._stderr_file,
        )
        self.wait_ready(timeout=timeout)

    def wait_ready(self, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError(
                    f"Processo MCP encerrou prematuramente (code={self.proc.returncode}). "
                    f"stderr:\n{self.read_stderr()}"
                )
            try:
                with socket.create_connection((self.host, self.port), timeout=0.2):
                    return
            except OSError as err:
                last_err = err
                time.sleep(0.05)
        raise TimeoutError(
            f"Servidor MCP não ficou pronto em {self.host}:{self.port} após {timeout}s "
            f"(último erro: {last_err}). stderr:\n{self.read_stderr()}"
        )

    def read_stderr(self) -> str:
        if self._stderr_file is None:
            return ""
        self._stderr_file.flush()
        Path(self._stderr_file.name)
        return Path(self._stderr_file.name).read_text(encoding="utf-8", errors="replace")

    def stop(self, timeout: float = 5.0) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=timeout)
        for tmp in (self._stderr_file, self._stdout_file):
            if tmp is not None:
                try:
                    tmp.close()
                except Exception:
                    pass
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
        self._stderr_file = None
        self._stdout_file = None

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        name: str | None = None,
        req_id: int | str | None = None,
        meta: dict[str, Any] | None = None,
        include_meta: bool = True,
        headers: dict[str, str] | None = None,
        traceparent: str | None = None,
        capabilities: dict[str, Any] | None = DEFAULT_CAPABILITIES,
    ) -> tuple[int, dict[str, Any], str]:
        actual_id = secrets.token_hex(6) if req_id is None else req_id
        full_params: dict[str, Any] = dict(params or {})
        if include_meta:
            if meta is None:
                full_params["_meta"] = build_mcp_meta(
                    client_capabilities=capabilities,
                    traceparent=traceparent,
                )
            else:
                full_params["_meta"] = meta
        body: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": actual_id,
            "method": method,
            "params": full_params,
        }
        actual_headers = (
            headers
            if headers is not None
            else build_mcp_headers(method=method, name=name)
        )
        return post_raw_json(self.url, body, actual_headers)


@contextmanager
def running_mcp_server(**kwargs: Any) -> Iterator[MCPServerSubprocess]:
    """Context manager que sobe e encerra um subprocesso real do servidor MCP."""
    server = MCPServerSubprocess(**kwargs)
    try:
        server.start()
        yield server
    finally:
        server.stop()


class TestHarnessSupport(unittest.TestCase):
    """Sanidade básica dos utilitários de fixture e leitura de exemplos de wire."""

    def test_load_wire_request_body_only_extracts_request_body(self) -> None:
        body = load_wire_request_body("01-tools-list.json")
        self.assertEqual(body["jsonrpc"], "2.0")
        self.assertEqual(body["method"], "tools/list")
        self.assertNotIn("descricao", body)
        self.assertNotIn("response", body)


class TestUS2ConsultaEReservaLivreHTTP(unittest.TestCase):
    """Testes de integração HTTP real para US2 (T010)."""

    def test_jornada_consultar_reservar_consultar_e_descoberta_us2(self) -> None:
        politica_original = (DADOS_DIR / "politica-de-uso.md").read_text(encoding="utf-8")
        versao_esperada = politica_original.splitlines()[0].split(":", 1)[1].strip()
        exemplo_02_body = load_wire_request_body("02-tools-call-livre.json")
        args_02 = exemplo_02_body["params"]["arguments"]

        with running_mcp_server() as srv:
            # 1. Conferir em tools/list as duas tools de US2 e seus schemas
            status_list, resp_list, _ = srv.request("tools/list")
            self.assertEqual(status_list, 200)
            tools = {
                t["name"]: t
                for t in (resp_list.get("result") or {}).get("tools", [])
            }
            self.assertIn("consultar_disponibilidade", tools)
            self.assertIn("reservar_sala", tools)

            schema_consulta = tools["consultar_disponibilidade"]["inputSchema"]
            self.assertEqual(schema_consulta.get("type"), "object")
            self.assertEqual(
                set(schema_consulta.get("required", [])),
                {"sala", "inicio", "fim"},
            )

            schema_reserva = tools["reservar_sala"]["inputSchema"]
            self.assertEqual(schema_reserva.get("type"), "object")
            self.assertEqual(
                set(schema_reserva.get("required", [])),
                {"sala", "inicio", "fim", "responsavel"},
            )

            # 2. Consultar sala-aquario 09h-10h (livre antes da reserva)
            status_c1, resp_c1, _ = srv.request(
                "tools/call",
                {
                    "name": "consultar_disponibilidade",
                    "arguments": {
                        "sala": args_02["sala"],
                        "inicio": args_02["inicio"],
                        "fim": args_02["fim"],
                    },
                },
                name="consultar_disponibilidade",
            )
            self.assertEqual(status_c1, 200)
            res_c1 = resp_c1["result"]
            self.assertEqual(res_c1.get("resultType"), "complete")
            self.assertFalse(res_c1.get("isError", False))
            sc_c1 = res_c1["structuredContent"]
            self.assertEqual(sc_c1["sala"], "sala-aquario")
            self.assertTrue(sc_c1["livre"])
            self.assertEqual(sc_c1["conflitos"], [])

            # 3. Reservar usando request.body do exemplo 02
            status_r, resp_r, _ = post_raw_json(
                srv.url,
                exemplo_02_body,
                build_mcp_headers(method="tools/call", name="reservar_sala"),
            )
            self.assertEqual(status_r, 200)
            res_r = resp_r["result"]
            self.assertEqual(res_r.get("resultType"), "complete")
            self.assertFalse(res_r.get("isError", False))
            sc_r = res_r["structuredContent"]
            self.assertTrue(sc_r["reservado"])
            self.assertIsInstance(sc_r["reserva"], str)
            self.assertTrue(sc_r["reserva"])
            self.assertEqual(sc_r["sala"], args_02["sala"])
            self.assertEqual(sc_r["inicio"], args_02["inicio"])
            self.assertEqual(sc_r["fim"], args_02["fim"])
            self.assertEqual(sc_r["responsavel"], args_02["responsavel"])
            self.assertEqual(sc_r["politica"], versao_esperada)

            # 4. Consultar novamente o mesmo intervalo -> ocupado com a reserva recém-criada
            status_c2, resp_c2, _ = srv.request(
                "tools/call",
                {
                    "name": "consultar_disponibilidade",
                    "arguments": {
                        "sala": args_02["sala"],
                        "inicio": args_02["inicio"],
                        "fim": args_02["fim"],
                    },
                },
                name="consultar_disponibilidade",
            )
            self.assertEqual(status_c2, 200)
            sc_c2 = resp_c2["result"]["structuredContent"]
            self.assertFalse(sc_c2["livre"])
            self.assertEqual(len(sc_c2["conflitos"]), 1)
            self.assertEqual(sc_c2["conflitos"][0]["id"], sc_r["reserva"])
            self.assertEqual(sc_c2["conflitos"][0]["responsavel"], "Doc")

            # 5. Consultar reserva inicial de Marty sem alterar estado
            status_m, resp_m, _ = srv.request(
                "tools/call",
                {
                    "name": "consultar_disponibilidade",
                    "arguments": {
                        "sala": "sala-garagem",
                        "inicio": "2026-11-03T14:00:00-03:00",
                        "fim": "2026-11-03T15:00:00-03:00",
                    },
                },
                name="consultar_disponibilidade",
            )
            self.assertEqual(status_m, 200)
            sc_m = resp_m["result"]["structuredContent"]
            self.assertFalse(sc_m["livre"])
            self.assertEqual(len(sc_m["conflitos"]), 1)
            self.assertEqual(sc_m["conflitos"][0]["id"], "res-0001")
            self.assertEqual(sc_m["conflitos"][0]["responsavel"], "Marty")

    def test_restart_real_recarrega_reservas_originais_e_preserva_arquivos(self) -> None:
        """T015: reserva livre visível no processo atual; restart recarrega base original sem tocar dados/."""
        salas_bytes_antes = (DADOS_DIR / "salas.json").read_bytes()
        reservas_bytes_antes = (DADOS_DIR / "reservas.json").read_bytes()
        politica_bytes_antes = (DADOS_DIR / "politica-de-uso.md").read_bytes()

        port = find_free_port()
        args = {
            "sala": "sala-porao",
            "inicio": "2026-11-03T11:00:00-03:00",
            "fim": "2026-11-03T12:00:00-03:00",
            "responsavel": "Lorraine",
        }
        args_consulta = {
            "sala": args["sala"],
            "inicio": args["inicio"],
            "fim": args["fim"],
        }

        with running_mcp_server(port=port) as srv1:
            st_r, resp_r, _ = srv1.request(
                "tools/call",
                {"name": "reservar_sala", "arguments": args},
                name="reservar_sala",
            )
            self.assertEqual(st_r, 200)
            self.assertTrue(resp_r["result"]["structuredContent"]["reservado"])

            st_c1, resp_c1, _ = srv1.request(
                "tools/call",
                {"name": "consultar_disponibilidade", "arguments": args_consulta},
                name="consultar_disponibilidade",
            )
            self.assertEqual(st_c1, 200)
            self.assertFalse(resp_c1["result"]["structuredContent"]["livre"])

        with running_mcp_server(port=port) as srv2:
            # Horário transitório volta a ficar livre após restart
            st_c2, resp_c2, _ = srv2.request(
                "tools/call",
                {"name": "consultar_disponibilidade", "arguments": args_consulta},
                name="consultar_disponibilidade",
            )
            self.assertEqual(st_c2, 200)
            self.assertTrue(resp_c2["result"]["structuredContent"]["livre"])

            # Reserva inicial de Marty permanece carregada
            st_m, resp_m, _ = srv2.request(
                "tools/call",
                {
                    "name": "consultar_disponibilidade",
                    "arguments": {
                        "sala": "sala-garagem",
                        "inicio": "2026-11-03T14:00:00-03:00",
                        "fim": "2026-11-03T15:00:00-03:00",
                    },
                },
                name="consultar_disponibilidade",
            )
            self.assertEqual(st_m, 200)
            self.assertFalse(resp_m["result"]["structuredContent"]["livre"])
            self.assertEqual(
                resp_m["result"]["structuredContent"]["conflitos"][0]["id"],
                "res-0001",
            )

        self.assertEqual((DADOS_DIR / "salas.json").read_bytes(), salas_bytes_antes)
        self.assertEqual((DADOS_DIR / "reservas.json").read_bytes(), reservas_bytes_antes)
        self.assertEqual((DADOS_DIR / "politica-de-uso.md").read_bytes(), politica_bytes_antes)

    def test_equivalencia_structured_content_e_texto_json_us2(self) -> None:
        """T016: equivalência entre content[].text e structuredContent em consulta e reserva."""
        with running_mcp_server() as srv:
            # 1. Consulta com conflito
            st_c, resp_c, _ = srv.request(
                "tools/call",
                {
                    "name": "consultar_disponibilidade",
                    "arguments": {
                        "sala": "sala-garagem",
                        "inicio": "2026-11-03T14:00:00-03:00",
                        "fim": "2026-11-03T15:00:00-03:00",
                    },
                },
                name="consultar_disponibilidade",
            )
            self.assertEqual(st_c, 200)
            res_c = resp_c["result"]
            sc_c = res_c["structuredContent"]
            texto_c = " ".join(p.get("text", "") for p in res_c.get("content", []))
            self.assertEqual(json.loads(texto_c), sc_c)
            self.assertEqual(set(sc_c.keys()), {"sala", "livre", "conflitos"})
            self.assertIsInstance(sc_c["sala"], str)
            self.assertIsInstance(sc_c["livre"], bool)
            self.assertIsInstance(sc_c["conflitos"], list)
            self.assertEqual(
                set(sc_c["conflitos"][0].keys()),
                {"id", "inicio", "fim", "responsavel"},
            )

            # 2. Reserva livre concluída
            st_r, resp_r, _ = srv.request(
                "tools/call",
                {
                    "name": "reservar_sala",
                    "arguments": {
                        "sala": "sala-aquario",
                        "inicio": "2026-11-03T09:00:00-03:00",
                        "fim": "2026-11-03T10:00:00-03:00",
                        "responsavel": "Doc",
                    },
                },
                name="reservar_sala",
            )
            self.assertEqual(st_r, 200)
            res_r = resp_r["result"]
            sc_r = res_r["structuredContent"]
            texto_r = " ".join(p.get("text", "") for p in res_r.get("content", []))
            self.assertEqual(json.loads(texto_r), sc_r)
            for campo in ("reserva", "reservado", "sala", "inicio", "fim", "responsavel", "politica"):
                self.assertIn(campo, sc_r)
            self.assertIsInstance(sc_r["reserva"], str)
            self.assertTrue(sc_r["reserva"])
            self.assertIs(sc_r["reservado"], True)
            self.assertEqual(sc_r["sala"], "sala-aquario")
            self.assertEqual(sc_r["inicio"], "2026-11-03T09:00:00-03:00")
            self.assertEqual(sc_r["fim"], "2026-11-03T10:00:00-03:00")
            self.assertEqual(sc_r["responsavel"], "Doc")
            self.assertEqual(sc_r["politica"], "2026-11-01")


class TestUS1DescobertaSalasEPoliticaHTTP(unittest.TestCase):
    """Testes de integração HTTP real para US1 (T019)."""

    def test_descoberta_tres_tools_listar_salas_politica_e_erros_inexistentes(self) -> None:
        salas_originais = json.loads((DADOS_DIR / "salas.json").read_text(encoding="utf-8"))
        politica_original = (DADOS_DIR / "politica-de-uso.md").read_text(encoding="utf-8")

        with running_mcp_server() as srv:
            # 1. tools/list usando request.body de 01-tools-list.json
            req_01 = load_wire_request_body("01-tools-list.json")
            st_list, resp_list, _ = post_raw_json(
                srv.url,
                req_01,
                build_mcp_headers(method="tools/list"),
            )
            self.assertEqual(st_list, 200)
            tools_list = (resp_list.get("result") or {}).get("tools", [])
            tools = {t["name"]: t for t in tools_list}
            self.assertEqual(
                set(tools.keys()),
                {"listar_salas", "consultar_disponibilidade", "reservar_sala"},
            )
            for t in tools.values():
                self.assertEqual(t.get("inputSchema", {}).get("type"), "object")

            self.assertEqual(
                tools["listar_salas"]["inputSchema"].get("properties"),
                {},
            )
            self.assertIn("outputSchema", tools["listar_salas"])
            out_schema = tools["listar_salas"]["outputSchema"]
            self.assertEqual(out_schema.get("type"), "object")
            self.assertIn("salas", out_schema.get("properties", {}))

            # 2. resources/list comprova capability resources ativa
            st_rlist, resp_rlist, _ = srv.request("resources/list")
            self.assertEqual(st_rlist, 200)
            uris = {
                r["uri"]
                for r in (resp_rlist.get("result") or {}).get("resources", [])
            }
            self.assertIn("politica://uso", uris)

            # 3. tools/call listar_salas sem argumentos
            st_salas, resp_salas, _ = srv.request(
                "tools/call",
                {"name": "listar_salas", "arguments": {}},
                name="listar_salas",
            )
            self.assertEqual(st_salas, 200)
            res_salas = resp_salas["result"]
            self.assertEqual(res_salas.get("resultType"), "complete")
            self.assertFalse(res_salas.get("isError", False))
            sc_salas = res_salas.get("structuredContent")
            texto_salas = " ".join(p.get("text", "") for p in res_salas.get("content", []))
            self.assertEqual(json.loads(texto_salas), sc_salas)
            self.assertEqual(sc_salas, {"salas": salas_originais})

            # 4. resources/read politica://uso usando request.body de 05-resources-read-politica.json
            req_05 = load_wire_request_body("05-resources-read-politica.json")
            st_pol, resp_pol, _ = post_raw_json(
                srv.url,
                req_05,
                build_mcp_headers(method="resources/read", name="politica://uso"),
            )
            self.assertEqual(st_pol, 200)
            contents = (resp_pol.get("result") or {}).get("contents", [])
            self.assertEqual(len(contents), 1)
            self.assertEqual(contents[0].get("uri"), "politica://uso")
            self.assertEqual(contents[0].get("mimeType"), "text/markdown")
            self.assertEqual(contents[0].get("text"), politica_original)

            versao_resource = contents[0]["text"].splitlines()[0].split(":", 1)[1].strip()

            # Confrontar versão do resource com a saída da reserva da US2
            st_res, resp_res, _ = srv.request(
                "tools/call",
                {
                    "name": "reservar_sala",
                    "arguments": {
                        "sala": "sala-aquario",
                        "inicio": "2026-11-03T09:00:00-03:00",
                        "fim": "2026-11-03T10:00:00-03:00",
                        "responsavel": "Doc",
                    },
                },
                name="reservar_sala",
            )
            self.assertEqual(st_res, 200)
            self.assertEqual(
                resp_res["result"]["structuredContent"]["politica"],
                versao_resource,
            )

            # 5. Tool inexistente recusada (-32602 ou complete com isError: true)
            _, resp_no_tool, _ = srv.request(
                "tools/call",
                {"name": "voar_delorean", "arguments": {}},
                name="voar_delorean",
            )
            recusou_tool = (
                (resp_no_tool.get("error") or {}).get("code") == -32602
                or (resp_no_tool.get("result") or {}).get("isError") is True
            )
            self.assertTrue(recusou_tool)

            # 6. URI de resource inexistente -> -32602 e nunca contents vazio
            st_no_uri, resp_no_uri, _ = srv.request(
                "resources/read",
                {"uri": "politica://inexistente"},
                name="politica://inexistente",
            )
            self.assertEqual(st_no_uri, 400)
            self.assertEqual((resp_no_uri.get("error") or {}).get("code"), -32602)
            self.assertNotIn("result", resp_no_uri)

            # 7. Conferir stderr das chamadas executadas (método, id e traceparent dos exemplos 01 e 05)
            stderr_log = srv.read_stderr()
            self.assertIn(
                "method=tools/list id=1 traceparent=00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
                stderr_log,
            )
            self.assertIn(
                "method=resources/read id=5 traceparent=00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
                stderr_log,
            )


class TestUS3RejeicoesDominioProtocoloELogsHTTP(unittest.TestCase):
    """Testes de integração HTTP real para US3 (T025, T026, T027, T028, T029)."""

    def test_quatro_erros_dominio_em_consultar_e_reservar_via_http(self) -> None:
        """T027: os quatro erros exatos de domínio em ambas as tools via HTTP, sem criar reserva."""
        casos = [
            (
                "sala-delorean",
                "2026-11-03T09:00:00-03:00",
                "2026-11-03T10:00:00-03:00",
                "Sala inexistente: sala-delorean",
            ),
            (
                "sala-aquario",
                "2026-11-03T07:00:00-03:00",
                "2026-11-03T08:00:00-03:00",
                "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00",
            ),
            (
                "sala-aquario",
                "2026-11-03T09:00:00-03:00",
                "2026-11-03T12:00:00-03:00",
                "Duracao acima do limite: a politica permite no maximo 2 horas",
            ),
            (
                "sala-aquario",
                "2026-11-03T10:00:00-03:00",
                "2026-11-03T09:00:00-03:00",
                "Intervalo invalido: fim deve ser posterior a inicio",
            ),
        ]

        with running_mcp_server() as srv:
            for sala, inicio, fim, msg_esperada in casos:
                for tool_name, extra_args in (
                    ("consultar_disponibilidade", {}),
                    ("reservar_sala", {"responsavel": "Doc"}),
                ):
                    with self.subTest(tool=tool_name, msg=msg_esperada):
                        st, resp, _ = srv.request(
                            "tools/call",
                            {
                                "name": tool_name,
                                "arguments": {
                                    "sala": sala,
                                    "inicio": inicio,
                                    "fim": fim,
                                    **extra_args,
                                },
                            },
                            name=tool_name,
                        )
                        self.assertEqual(st, 200)
                        res = resp.get("result") or {}
                        self.assertEqual(res.get("resultType"), "complete")
                        self.assertIs(res.get("isError"), True)
                        texto = " ".join(p.get("text", "") for p in res.get("content", []))
                        self.assertIn(msg_esperada, texto)

            # Confirmar que sala-aquario continua livre após todas as falhas
            st_check, resp_check, _ = srv.request(
                "tools/call",
                {
                    "name": "consultar_disponibilidade",
                    "arguments": {
                        "sala": "sala-aquario",
                        "inicio": "2026-11-03T09:00:00-03:00",
                        "fim": "2026-11-03T10:00:00-03:00",
                    },
                },
                name="consultar_disponibilidade",
            )
            self.assertEqual(st_check, 200)
            self.assertTrue(resp_check["result"]["structuredContent"]["livre"])

    def test_matriz_metadados_ausentes_e_headers_divergentes(self) -> None:
        """T025: -32602/HTTP 400 sem metadados (com/sem header, sem herança) e -32020 em divergências de header."""
        with running_mcp_server() as srv:
            # 1. Request válido primeiro (com capabilities completas)
            st_ok, _, _ = srv.request(
                "tools/list",
                req_id="req-ok-1",
                capabilities={"elicitation": {"form": {}}},
            )
            self.assertEqual(st_ok, 200)

            # 2. Request válido com capabilities vazias {}
            st_ok2, _, _ = srv.request(
                "tools/list",
                req_id="req-ok-2",
                capabilities={},
            )
            self.assertEqual(st_ok2, 200)

            # 3. Matriz de ausência de metadados em _meta (com e sem header moderno MCP-Protocol-Version)
            variantes_meta = [
                ("sem_protocolVersion", {"io.modelcontextprotocol/clientCapabilities": {}}),
                ("sem_clientCapabilities", {"io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION}),
                ("ambos_ausentes", {}),
                ("meta_ausente", None),
            ]
            for rotulo, meta_obj in variantes_meta:
                for com_header_moderno in (True, False):
                    with self.subTest(caso=rotulo, header_moderno=com_header_moderno):
                        hdrs = build_mcp_headers(
                            method="tools/call",
                            name="listar_salas",
                            protocol_version=PROTOCOL_VERSION if com_header_moderno else None,
                        )
                        st, resp, _ = srv.request(
                            "tools/call",
                            {"name": "listar_salas", "arguments": {}},
                            name="listar_salas",
                            req_id=f"meta-{rotulo}-{com_header_moderno}",
                            meta=meta_obj,
                            include_meta=(meta_obj is not None),
                            headers=hdrs,
                        )
                        self.assertEqual(st, 400)
                        self.assertEqual((resp.get("error") or {}).get("code"), -32602)

            # 4. Divergências isoladas de headers (-32020)
            # 4a. MCP-Protocol-Version divergente do corpo
            st_pv, resp_pv, _ = srv.request(
                "tools/list",
                req_id="hdr-pv-div",
                headers=build_mcp_headers(
                    method="tools/list",
                    protocol_version="2026-01-01",
                ),
            )
            self.assertEqual(st_pv, 400)
            self.assertEqual((resp_pv.get("error") or {}).get("code"), -32020)

            # 4b. Mcp-Method divergente do corpo
            st_m, resp_m, _ = srv.request(
                "tools/list",
                req_id="hdr-method-div",
                headers=build_mcp_headers(method="resources/list"),
            )
            self.assertEqual(st_m, 400)
            self.assertEqual((resp_m.get("error") or {}).get("code"), -32020)

            # 4c. Mcp-Name divergente em tools/call
            st_nt, resp_nt, _ = srv.request(
                "tools/call",
                {"name": "listar_salas", "arguments": {}},
                req_id="hdr-name-tool-div",
                headers=build_mcp_headers(method="tools/call", name="reservar_sala"),
            )
            self.assertEqual(st_nt, 400)
            self.assertEqual((resp_nt.get("error") or {}).get("code"), -32020)

            # 4d. Mcp-Name divergente em resources/read
            st_nr, resp_nr, _ = srv.request(
                "resources/read",
                {"uri": "politica://uso"},
                req_id="hdr-name-res-div",
                headers=build_mcp_headers(
                    method="resources/read",
                    name="politica://outra",
                ),
            )
            self.assertEqual(st_nr, 400)
            self.assertEqual((resp_nr.get("error") or {}).get("code"), -32020)

    def test_logs_stderr_para_sucessos_e_rejeicoes_com_e_sem_traceparent(self) -> None:
        """T026: stderr registra método, id e traceparent exato quando presente, inclusive em rejeições."""
        tp1 = "00-11111111111111111111111111111111-2222222222222222-01"
        tp2 = "00-33333333333333333333333333333333-4444444444444444-01"
        tp_rej = "00-55555555555555555555555555555555-6666666666666666-01"

        with running_mcp_server() as srv:
            # tools/list com traceparent tp1
            srv.request("tools/list", req_id="log-list-1", traceparent=tp1)
            # tools/call sem traceparent
            srv.request(
                "tools/call",
                {"name": "listar_salas", "arguments": {}},
                name="listar_salas",
                req_id="log-call-2",
                traceparent=None,
            )
            # resources/read com traceparent tp2
            srv.request(
                "resources/read",
                {"uri": "politica://uso"},
                name="politica://uso",
                req_id="log-res-3",
                traceparent=tp2,
            )
            # Rejeição por metadata ausente com traceparent tp_rej
            srv.request(
                "tools/list",
                req_id="log-rej-meta",
                meta={"traceparent": tp_rej},
            )
            # Rejeição por header divergente
            srv.request(
                "tools/list",
                req_id="log-rej-hdr",
                headers=build_mcp_headers(method="tools/call"),
            )
            # Rejeição por tool inexistente
            srv.request(
                "tools/call",
                {"name": "tool_inexistente", "arguments": {}},
                name="tool_inexistente",
                req_id="log-rej-tool",
            )
            # Rejeição por URI inexistente
            srv.request(
                "resources/read",
                {"uri": "politica://nao-existe"},
                name="politica://nao-existe",
                req_id="log-rej-uri",
            )

            stderr = srv.read_stderr()
            self.assertIn(f"method=tools/list id=log-list-1 traceparent={tp1}", stderr)
            self.assertIn("method=tools/call id=log-call-2", stderr)
            self.assertNotIn("id=log-call-2 traceparent=", stderr)
            self.assertIn(f"method=resources/read id=log-res-3 traceparent={tp2}", stderr)
            self.assertIn(f"method=tools/list id=log-rej-meta traceparent={tp_rej}", stderr)
            self.assertIn("method=tools/list id=log-rej-hdr", stderr)
            self.assertIn("method=tools/call id=log-rej-tool", stderr)
            self.assertIn("method=resources/read id=log-rej-uri", stderr)
            self.assertNotIn(VALID_SECRET_HEX, stderr)


class TestStartupEConfiguracaoT032(unittest.TestCase):
    """Testes de startup, cwd externo, overrides e validação de REQUEST_STATE_SECRET (T032)."""

    def test_startup_a_partir_de_outro_cwd_e_override_host_porta(self) -> None:
        custom_secret = "cd" * 32
        with tempfile.TemporaryDirectory() as tmpdir:
            with running_mcp_server(
                host="127.0.0.1",
                secret=custom_secret,
                cwd=Path(tmpdir),
            ) as srv:
                st_s, resp_s, _ = srv.request(
                    "tools/call",
                    {"name": "listar_salas", "arguments": {}},
                    name="listar_salas",
                )
                self.assertEqual(st_s, 200)
                self.assertEqual(len(resp_s["result"]["structuredContent"]["salas"]), 5)

                st_p, resp_p, _ = srv.request(
                    "resources/read",
                    {"uri": "politica://uso"},
                    name="politica://uso",
                )
                self.assertEqual(st_p, 200)
                self.assertIn("versao: 2026-11-01", resp_p["result"]["contents"][0]["text"])
                self.assertNotIn(custom_secret, srv.read_stderr())

    def test_valores_padrao_e_rejeicao_segredo_invalido_sem_vazamento(self) -> None:
        from ponte_mcp.app import DEFAULT_HOST, DEFAULT_PORT

        self.assertEqual(DEFAULT_HOST, "127.0.0.1")
        self.assertEqual(DEFAULT_PORT, 7301)

        segredo_curto = "ef" * 31
        segredo_hex_invalido = "zz" * 32

        for rotulo, segredo in (
            ("ausente", None),
            ("hex_invalido", segredo_hex_invalido),
            ("menos_de_32_bytes", segredo_curto),
        ):
            with self.subTest(caso=rotulo):
                env = os.environ.copy()
                env["MCP_HOST"] = "127.0.0.1"
                env["MCP_PORT"] = str(find_free_port())
                if segredo is None:
                    env.pop("REQUEST_STATE_SECRET", None)
                else:
                    env["REQUEST_STATE_SECRET"] = segredo

                proc = subprocess.run(
                    [sys.executable, "-m", "ponte_mcp"],
                    cwd=str(ROOT_DIR),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("REQUEST_STATE_SECRET", proc.stderr)
                if segredo is not None:
                    self.assertNotIn(segredo, proc.stderr)
                    self.assertNotIn(segredo, proc.stdout)


if __name__ == "__main__":
    unittest.main()
