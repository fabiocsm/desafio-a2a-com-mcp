"""Suporte e testes de integração HTTP real entre os processos ponte_mcp e ponte_agente."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Iterator
import unittest
import urllib.error
import urllib.request

import httpx

from ponte_agente.app import AgenteSettings, create_app
from ponte_agente.tasks import TaskStore

ROOT_DIR = Path(__file__).resolve().parents[2]
WIRE_DIR = ROOT_DIR / "exemplos" / "wire"
DADOS_DIR = ROOT_DIR / "dados"

PROTOCOL_VERSION = "2026-07-28"
DEFAULT_CAPABILITIES: dict[str, Any] = {"elicitation": {"form": {}}}


def find_free_port(host: str = "127.0.0.1") -> int:
    """Encontra uma porta TCP livre em loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def generate_secret_hex() -> str:
    """Gera segredo hexadecimal de 32 bytes exclusivamente para o processo MCP."""
    return secrets.token_hex(32)


def load_wire_example(filename: str) -> dict[str, Any]:
    """Lê um exemplo de wire em modo somente leitura."""
    path = WIRE_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def load_wire_request_body(filename: str) -> dict[str, Any]:
    """Retorna uma cópia profunda apenas de request.body do exemplo."""
    example = load_wire_example(filename)
    return json.loads(json.dumps(example["request"]["body"]))


def get_raw_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any], str]:
    """Envia GET HTTP e retorna (status_http, json_decodificado, texto_bruto)."""
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
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


def post_raw_json(
    url: str,
    body: dict[str, Any] | bytes | str,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any], str]:
    """Envia POST HTTP com corpo JSON e retorna (status_http, json_decodificado, texto_bruto)."""
    if isinstance(body, dict):
        payload = json.dumps(body).encode("utf-8")
    elif isinstance(body, str):
        payload = body.encode("utf-8")
    else:
        payload = body

    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=payload, headers=req_headers, method="POST")
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


def build_mcp_headers(
    method: str,
    name: str | None = None,
    protocol_version: str = PROTOCOL_VERSION,
) -> dict[str, str]:
    """Monta cabeçalhos HTTP espelhados para consultas diretas ao servidor MCP."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": protocol_version,
        "Mcp-Method": method,
    }
    if name is not None:
        headers["Mcp-Name"] = name
    return headers


def build_mcp_meta(
    *,
    protocol_version: str = PROTOCOL_VERSION,
    client_capabilities: dict[str, Any] | None = DEFAULT_CAPABILITIES,
    traceparent: str | None = None,
) -> dict[str, Any]:
    """Monta o bloco _meta de um request MCP de verificação."""
    meta: dict[str, Any] = {
        "io.modelcontextprotocol/protocolVersion": protocol_version,
        "io.modelcontextprotocol/clientCapabilities": (
            DEFAULT_CAPABILITIES if client_capabilities is None else client_capabilities
        ),
    }
    if traceparent is not None:
        meta["traceparent"] = traceparent
    return meta


class MCPServerSubprocess:
    """Gerencia um subprocesso real de `python -m ponte_mcp` com captura de stderr."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int | None = None,
        secret: str | None = None,
        cwd: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.host = host
        self.port = port if port is not None else find_free_port(host)
        self.secret = secret if secret is not None else generate_secret_hex()
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

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        req_id: str | int = "mcp-check-1",
        traceparent: str | None = None,
    ) -> tuple[int, dict[str, Any], str]:
        """Executa um tools/call HTTP direto para conferência independente de estado."""
        body = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
                "_meta": build_mcp_meta(traceparent=traceparent),
            },
        }
        return post_raw_json(self.url, body, build_mcp_headers("tools/call", name=name))


class AgenteServerSubprocess:
    """Gerencia um subprocesso real de `python -m ponte_agente` sem REQUEST_STATE_SECRET."""

    def __init__(
        self,
        *,
        mcp_url: str,
        host: str = "127.0.0.1",
        port: int | None = None,
        base_url: str | None = None,
        cwd: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.mcp_url = mcp_url
        self.host = host
        self.port = port if port is not None else find_free_port(host)
        self.base_url = base_url if base_url is not None else f"http://{self.host}:{self.port}"
        self.cwd = cwd or ROOT_DIR
        self.extra_env = extra_env or {}
        self._stderr_file: tempfile.NamedTemporaryFile[str] | None = None
        self._stdout_file: tempfile.NamedTemporaryFile[str] | None = None
        self.proc: subprocess.Popen[bytes] | None = None

    @property
    def card_url(self) -> str:
        return f"http://{self.host}:{self.port}/.well-known/agent-card.json"

    @property
    def rpc_url(self) -> str:
        return f"http://{self.host}:{self.port}/a2a"

    def start(self, timeout: float = 10.0) -> None:
        self._stderr_file = tempfile.NamedTemporaryFile(
            mode="w+", encoding="utf-8", prefix="ponte_agente_stderr_", delete=False
        )
        self._stdout_file = tempfile.NamedTemporaryFile(
            mode="w+", encoding="utf-8", prefix="ponte_agente_stdout_", delete=False
        )
        env = os.environ.copy()
        # O segredo de requestState pertence exclusivamente ao servidor MCP.
        env.pop("REQUEST_STATE_SECRET", None)
        env["AGENTE_HOST"] = self.host
        env["AGENTE_PORT"] = str(self.port)
        env["MCP_URL"] = self.mcp_url
        env["A2A_BASE_URL"] = self.base_url
        env["PYTHONUNBUFFERED"] = "1"
        env.update(self.extra_env)

        self.proc = subprocess.Popen(
            [sys.executable, "-m", "ponte_agente"],
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
                    f"Processo Agente encerrou prematuramente (code={self.proc.returncode}). "
                    f"stderr:\n{self.read_stderr()}"
                )
            try:
                with socket.create_connection((self.host, self.port), timeout=0.2):
                    return
            except OSError as err:
                last_err = err
                time.sleep(0.05)
        raise TimeoutError(
            f"Agente A2A não ficou pronto em {self.host}:{self.port} após {timeout}s "
            f"(último erro: {last_err}). stderr:\n{self.read_stderr()}"
        )

    def read_stderr(self) -> str:
        if self._stderr_file is None:
            return ""
        self._stderr_file.flush()
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

    def get_card(self, headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any], str]:
        return get_raw_json(self.card_url, headers=headers)

    def rpc(
        self,
        method: str,
        params: dict[str, Any],
        *,
        req_id: str | int = 1,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any], str]:
        body = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        return post_raw_json(self.rpc_url, body, headers=headers)

    def send_message(
        self,
        text: str,
        *,
        message_id: str | None = None,
        task_id: str | None = None,
        req_id: str | int = 1,
        traceparent: str | None = None,
        a2a_version: str | None = None,
    ) -> tuple[int, dict[str, Any], str]:
        msg: dict[str, Any] = {
            "messageId": message_id or f"msg-{secrets.token_hex(6)}",
            "role": "ROLE_USER",
            "parts": [{"text": text}],
        }
        if task_id is not None:
            msg["taskId"] = task_id

        headers: dict[str, str] = {}
        if traceparent is not None:
            headers["traceparent"] = traceparent
        if a2a_version is not None:
            headers["A2A-Version"] = a2a_version

        return self.rpc("SendMessage", {"message": msg}, req_id=req_id, headers=headers)

    def get_task(
        self,
        task_id: str,
        *,
        req_id: str | int = 2,
        traceparent: str | None = None,
        a2a_version: str | None = None,
    ) -> tuple[int, dict[str, Any], str]:
        headers: dict[str, str] = {}
        if traceparent is not None:
            headers["traceparent"] = traceparent
        if a2a_version is not None:
            headers["A2A-Version"] = a2a_version

        return self.rpc("GetTask", {"id": task_id}, req_id=req_id, headers=headers)


@contextmanager
def running_mcp_and_agent(
    *,
    mcp_cwd: Path | None = None,
    agent_cwd: Path | None = None,
    agent_extra_env: dict[str, str] | None = None,
) -> Iterator[tuple[MCPServerSubprocess, AgenteServerSubprocess]]:
    """Inicia MCP e Agente em processos independentes recém-iniciados e encerra ao sair."""
    mcp_proc = MCPServerSubprocess(cwd=mcp_cwd)
    mcp_proc.start()
    agent_proc = AgenteServerSubprocess(
        mcp_url=mcp_proc.url,
        cwd=agent_cwd,
        extra_env=agent_extra_env,
    )
    try:
        agent_proc.start()
        yield mcp_proc, agent_proc
    finally:
        agent_proc.stop()
        mcp_proc.stop()


class TestAgenteUS1DescobertaEReservaLivre(unittest.TestCase):
    """Testes HTTP reais de descoberta do Agent Card e reserva direta livre (T008)."""

    def test_agent_card_e_reserva_livre_sem_header_versao_e_efeito_no_mcp(self) -> None:
        with running_mcp_and_agent() as (mcp_proc, agent_proc):
            status, card, _ = agent_proc.get_card()
            self.assertEqual(status, 200)
            self.assertEqual(card.get("name"), "Central de Salas")
            self.assertEqual(card.get("version"), "1.0.0")
            self.assertEqual(card.get("defaultInputModes"), ["text/plain"])
            self.assertEqual(card.get("defaultOutputModes"), ["text/plain"])

            capabilities = card.get("capabilities") or {}
            self.assertFalse(capabilities.get("streaming", True))
            self.assertFalse(capabilities.get("pushNotifications", True))
            self.assertFalse(capabilities.get("extendedAgentCard", True))
            self.assertNotIn("securitySchemes", card)

            interfaces = card.get("supportedInterfaces") or []
            self.assertEqual(len(interfaces), 1)
            iface = interfaces[0]
            self.assertEqual(iface.get("url"), f"{agent_proc.base_url}/a2a")
            self.assertEqual(iface.get("protocolBinding"), "JSONRPC")
            self.assertEqual(iface.get("protocolVersion"), "1.0")

            skills = card.get("skills") or []
            self.assertEqual(len(skills), 1)
            skill = skills[0]
            self.assertEqual(skill.get("id"), "reservar-sala")
            self.assertIn("tags", skill)
            self.assertIn("examples", skill)

            # Reserva livre sem header A2A-Version (perfil do starter)
            wire_body = load_wire_request_body("08-a2a-send-message.json")
            wire_body["params"]["message"]["parts"][0]["text"] = (
                "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 "
                "fim=2026-11-03T10:00:00-03:00 responsavel=Doc"
            )
            http_status, rpc_resp, _ = post_raw_json(
                agent_proc.rpc_url,
                wire_body,
                headers={"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"},
            )
            self.assertEqual(http_status, 200)
            self.assertNotIn("error", rpc_resp, f"Erro inesperado: {rpc_resp}")
            result = rpc_resp.get("result") or {}
            self.assertIn("task", result)
            task = result["task"]

            task_id = task.get("id")
            context_id = task.get("contextId")
            self.assertIsInstance(task_id, str)
            self.assertTrue(task_id)
            self.assertIsInstance(context_id, str)
            self.assertTrue(context_id)
            self.assertNotEqual(task_id, context_id)

            status_obj = task.get("status") or {}
            self.assertEqual(status_obj.get("state"), "TASK_STATE_COMPLETED")

            history = task.get("history") or []
            self.assertGreaterEqual(len(history), 2)
            for msg in history:
                self.assertIn(msg.get("role"), ("ROLE_USER", "ROLE_AGENT"))
                for part in msg.get("parts") or []:
                    self.assertIn("text", part)
                    self.assertNotIn("kind", part)

            artifacts = task.get("artifacts") or []
            self.assertEqual(len(artifacts), 1)
            artifact = artifacts[0]
            self.assertEqual(artifact.get("name"), "reserva")
            self.assertTrue(artifact.get("artifactId"))
            art_parts = artifact.get("parts") or []
            self.assertEqual(len(art_parts), 1)
            self.assertNotIn("kind", art_parts[0])
            reserva_json = json.loads(art_parts[0]["text"])
            self.assertEqual(reserva_json.get("sala"), "sala-porao")
            self.assertEqual(reserva_json.get("inicio"), "2026-11-03T09:00:00-03:00")
            self.assertEqual(reserva_json.get("fim"), "2026-11-03T10:00:00-03:00")
            self.assertEqual(reserva_json.get("responsavel"), "Doc")
            self.assertEqual(reserva_json.get("politica"), "2026-11-01")
            self.assertTrue(str(reserva_json.get("reserva", "")).startswith("res-"))

            # Confirma diretamente no servidor MCP que a reserva criada afeta a consulta seguinte
            mcp_status, mcp_resp, _ = mcp_proc.call_tool(
                "consultar_disponibilidade",
                {
                    "sala": "sala-porao",
                    "inicio": "2026-11-03T09:00:00-03:00",
                    "fim": "2026-11-03T10:00:00-03:00",
                },
            )
            self.assertEqual(mcp_status, 200)
            sc = ((mcp_resp.get("result") or {}).get("structuredContent")) or {}
            self.assertIs(sc.get("livre"), False)
            conflitos = sc.get("conflitos") or []
            self.assertEqual(len(conflitos), 1)
            self.assertEqual(conflitos[0].get("id"), reserva_json["reserva"])

    def test_reserva_livre_com_a2a_version_1_0_e_rejeicao_de_versao_incompativel(self) -> None:
        with running_mcp_and_agent() as (_, agent_proc):
            # Com A2A-Version: 1.0 explícito em processo recém-iniciado
            http_status, rpc_resp, _ = agent_proc.send_message(
                "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 "
                "fim=2026-11-03T10:00:00-03:00 responsavel=Doc",
                a2a_version="1.0",
            )
            self.assertEqual(http_status, 200)
            self.assertNotIn("error", rpc_resp)
            task = rpc_resp["result"]["task"]
            self.assertEqual(task["status"]["state"], "TASK_STATE_COMPLETED")

            # Versão explícita incompatível (0.3 e 2.0) deve ser recusada pelo SDK
            for bad_version in ("0.3", "2.0", "invalid"):
                _, bad_resp, _ = agent_proc.send_message(
                    "reservar sala=sala-aquario inicio=2026-11-03T09:00:00-03:00 "
                    "fim=2026-11-03T10:00:00-03:00 responsavel=Doc",
                    a2a_version=bad_version,
                )
                self.assertIn("error", bad_resp, f"Versão {bad_version} deveria falhar: {bad_resp}")


def extract_task_from_get_task(rpc_resp: dict[str, Any]) -> dict[str, Any]:
    """Extrai o objeto Task de GetTask aceitando Task direta em result ou wrapper result.task."""
    result = rpc_resp.get("result") or {}
    if "task" in result and isinstance(result["task"], dict):
        return result["task"]
    return result


class TransparentMCPObserverProxy:
    """Observador HTTP transparente entre o agente e o servidor MCP real, com barreira opcional."""

    def __init__(self, target_url: str, *, host: str = "127.0.0.1") -> None:
        self.target_url = target_url
        self.host = host
        self.port = find_free_port(host)
        self.captured_requests: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self.hold_next_tool_call = False
        self.tool_call_entered = threading.Event()
        self.tool_call_release = threading.Event()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/mcp"

    def start(self) -> None:
        proxy = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def _forward(self, method: str) -> None:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                raw_body = self.rfile.read(content_length) if content_length > 0 else b""
                headers_orig = {k: v for k, v in self.headers.items()}
                headers_lower = {k.lower(): v for k, v in self.headers.items()}
                parsed_json: dict[str, Any] | None = None
                if raw_body:
                    try:
                        decoded = json.loads(raw_body.decode("utf-8"))
                        if isinstance(decoded, dict):
                            parsed_json = decoded
                    except Exception:
                        parsed_json = None

                with proxy._lock:
                    proxy.captured_requests.append(
                        {
                            "http_method": method,
                            "path": self.path,
                            "headers": headers_orig,
                            "headers_lower": headers_lower,
                            "raw_body": raw_body,
                            "json": parsed_json,
                        }
                    )
                    should_hold = (
                        proxy.hold_next_tool_call
                        and isinstance(parsed_json, dict)
                        and parsed_json.get("method") == "tools/call"
                    )
                    if should_hold:
                        proxy.hold_next_tool_call = False

                if should_hold:
                    proxy.tool_call_entered.set()
                    proxy.tool_call_release.wait(timeout=10.0)

                forward_headers = {
                    k: v
                    for k, v in headers_orig.items()
                    if k.lower() not in ("host", "content-length", "connection")
                }
                req = urllib.request.Request(
                    proxy.target_url,
                    data=raw_body if method == "POST" else None,
                    headers=forward_headers,
                    method=method,
                )
                try:
                    with urllib.request.urlopen(req, timeout=10.0) as resp:
                        resp_status = int(resp.status)
                        resp_headers = list(resp.headers.items())
                        resp_body = resp.read()
                except urllib.error.HTTPError as err:
                    resp_status = int(err.code)
                    resp_headers = list(err.headers.items()) if err.headers else []
                    resp_body = err.read()

                self.send_response(resp_status)
                for hk, hv in resp_headers:
                    if hk.lower() in ("transfer-encoding", "connection", "content-length", "server", "date"):
                        continue
                    self.send_header(hk, hv)
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                if resp_body:
                    self.wfile.write(resp_body)

            def do_POST(self) -> None:  # noqa: N802
                self._forward("POST")

            def do_GET(self) -> None:  # noqa: N802
                self._forward("GET")

            def do_DELETE(self) -> None:  # noqa: N802
                self._forward("DELETE")

        self._server = ThreadingHTTPServer((self.host, self.port), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.tool_call_release.set()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None


class TestAgenteUS2ConsultaFalhasETerminalidade(unittest.TestCase):
    """Testes HTTP reais de GetTask, matriz de falhas de domínio e estados terminais (T018)."""

    def test_get_task_sucesso_sala_inexistente_matriz_politica_e_terminalidade(self) -> None:
        mcp_proc = MCPServerSubprocess()
        mcp_proc.start()
        proxy = TransparentMCPObserverProxy(mcp_proc.url)
        proxy.start()
        agent_proc = AgenteServerSubprocess(mcp_url=proxy.url)
        try:
            agent_proc.start()

            # 1. Sucesso + GetTask (aceitando Task direta em result)
            status, send_resp, _ = agent_proc.send_message(
                "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 "
                "fim=2026-11-03T10:00:00-03:00 responsavel=Doc",
                req_id="us2-ok-1",
            )
            self.assertEqual(status, 200)
            created_task = send_resp["result"]["task"]
            ok_task_id = created_task["id"]
            ok_context_id = created_task["contextId"]
            self.assertEqual(created_task["status"]["state"], "TASK_STATE_COMPLETED")

            get_status, get_resp, _ = agent_proc.get_task(ok_task_id, req_id="us2-get-ok-1")
            self.assertEqual(get_status, 200)
            self.assertNotIn("error", get_resp)
            fetched_ok = extract_task_from_get_task(get_resp)
            self.assertEqual(fetched_ok["id"], ok_task_id)
            self.assertEqual(fetched_ok["contextId"], ok_context_id)
            self.assertEqual(fetched_ok["status"]["state"], "TASK_STATE_COMPLETED")
            self.assertEqual(len(fetched_ok.get("artifacts") or []), 1)
            self.assertEqual(fetched_ok["artifacts"][0]["name"], "reserva")

            # 2. Sala inexistente: Sala inexistente: sala-delorean
            status_12, resp_12, _ = agent_proc.send_message(
                "reservar sala=sala-delorean inicio=2026-11-03T09:00:00-03:00 "
                "fim=2026-11-03T10:00:00-03:00 responsavel=Doc",
                req_id="us2-delorean-1",
            )
            self.assertEqual(status_12, 200)
            self.assertNotIn("error", resp_12)
            task_12 = resp_12["result"]["task"]
            delorean_task_id = task_12["id"]
            self.assertEqual(task_12["status"]["state"], "TASK_STATE_FAILED")
            status_text_12 = task_12["status"]["message"]["parts"][0]["text"]
            self.assertIn("Sala inexistente: sala-delorean", status_text_12)
            self.assertTrue(status_text_12.endswith("Sala inexistente: sala-delorean"))
            self.assertFalse(task_12.get("artifacts"))
            agent_msgs_12 = [m for m in task_12.get("history", []) if m.get("role") == "ROLE_AGENT"]
            self.assertEqual(len(agent_msgs_12), 1)
            self.assertEqual(agent_msgs_12[0]["parts"][0]["text"], status_text_12)

            # GetTask na Task falha preserva estado FAILED, mensagem e ausência de artifact
            _, get_12, _ = agent_proc.get_task(delorean_task_id, req_id="us2-get-12")
            fetched_12 = extract_task_from_get_task(get_12)
            self.assertEqual(fetched_12["id"], delorean_task_id)
            self.assertEqual(fetched_12["status"]["state"], "TASK_STATE_FAILED")
            self.assertFalse(fetched_12.get("artifacts"))
            self.assertEqual(
                fetched_12["status"]["message"]["parts"][0]["text"],
                status_text_12,
            )

            # 3. Matriz de erros de política da constituição
            # Prepara ocupação da maior sala (sala-mirante, cap 20) em 11:00–12:00 para testar sem alternativas
            _, prep_mirante, _ = agent_proc.send_message(
                "reservar sala=sala-mirante inicio=2026-11-03T11:00:00-03:00 "
                "fim=2026-11-03T12:00:00-03:00 responsavel=Biff",
                req_id="us2-prep-mirante",
            )
            self.assertEqual(prep_mirante["result"]["task"]["status"]["state"], "TASK_STATE_COMPLETED")

            policy_matrix = [
                (
                    "reservar sala=sala-aquario inicio=2026-11-03T07:00:00-03:00 "
                    "fim=2026-11-03T08:00:00-03:00 responsavel=Marty",
                    "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00",
                ),
                (
                    "reservar sala=sala-aquario inicio=2026-11-03T09:00:00-03:00 "
                    "fim=2026-11-03T11:30:00-03:00 responsavel=Marty",
                    "Duracao acima do limite: a politica permite no maximo 2 horas",
                ),
                (
                    "reservar sala=sala-aquario inicio=2026-11-03T10:00:00-03:00 "
                    "fim=2026-11-03T09:00:00-03:00 responsavel=Marty",
                    "Intervalo invalido: fim deve ser posterior a inicio",
                ),
                (
                    "reservar sala=sala-mirante inicio=2026-11-03T11:00:00-03:00 "
                    "fim=2026-11-03T12:00:00-03:00 responsavel=Marty",
                    "Sem alternativas disponiveis no intervalo",
                ),
            ]
            for idx, (cmd_text, expected_error_msg) in enumerate(policy_matrix, start=1):
                _, p_resp, _ = agent_proc.send_message(cmd_text, req_id=f"us2-pol-{idx}")
                self.assertNotIn("error", p_resp, f"Falha de domínio deve virar Task FAILED: {p_resp}")
                p_task = p_resp["result"]["task"]
                self.assertEqual(p_task["status"]["state"], "TASK_STATE_FAILED")
                self.assertFalse(p_task.get("artifacts"))
                p_msg = p_task["status"]["message"]["parts"][0]["text"]
                self.assertIn(expected_error_msg, p_msg)
                self.assertTrue(p_msg.endswith(expected_error_msg))

                _, gp_resp, _ = agent_proc.get_task(p_task["id"], req_id=f"us2-get-pol-{idx}")
                gp_task = extract_task_from_get_task(gp_resp)
                self.assertEqual(gp_task["status"]["state"], "TASK_STATE_FAILED")
                self.assertFalse(gp_task.get("artifacts"))
                self.assertEqual(gp_task["status"]["message"]["parts"][0]["text"], p_msg)

            # 4. Task desconhecida em GetTask -> TaskNotFoundError (-32001)
            _, unknown_resp, _ = agent_proc.get_task("task-inexistente-999", req_id="us2-unknown")
            self.assertIn("error", unknown_resp)
            self.assertEqual(unknown_resp["error"]["code"], -32001)

            # 5. Formato malformado em SendMessage -> InvalidParamsError (-32602) sem chamada MCP adicional
            calls_before_malformed = len(
                [r for r in proxy.captured_requests if (r.get("json") or {}).get("method") == "tools/call"]
            )
            _, bad_cmd_resp, _ = agent_proc.send_message(
                "quero reservar a sala aquario amanha cedo",
                req_id="us2-malformed",
            )
            self.assertIn("error", bad_cmd_resp)
            self.assertEqual(bad_cmd_resp["error"]["code"], -32602)
            calls_after_malformed = len(
                [r for r in proxy.captured_requests if (r.get("json") or {}).get("method") == "tools/call"]
            )
            self.assertEqual(calls_before_malformed, calls_after_malformed)

            # 6. Terminalidade: SendMessage dirigido a Task COMPLETED ou FAILED é rejeitado sem chamada MCP e sem mutação
            for term_task_id, expected_state in (
                (ok_task_id, "TASK_STATE_COMPLETED"),
                (delorean_task_id, "TASK_STATE_FAILED"),
            ):
                _, before_get, _ = agent_proc.get_task(term_task_id)
                snapshot_before = extract_task_from_get_task(before_get)
                mcp_calls_before = len(
                    [r for r in proxy.captured_requests if (r.get("json") or {}).get("method") == "tools/call"]
                )

                _, term_send_resp, _ = agent_proc.send_message(
                    "reservar sala=sala-aquario inicio=2026-11-03T15:00:00-03:00 "
                    "fim=2026-11-03T16:00:00-03:00 responsavel=Doc",
                    task_id=term_task_id,
                    req_id=f"us2-term-{term_task_id}",
                )
                self.assertIn("error", term_send_resp)
                mcp_calls_after = len(
                    [r for r in proxy.captured_requests if (r.get("json") or {}).get("method") == "tools/call"]
                )
                self.assertEqual(mcp_calls_before, mcp_calls_after)

                _, after_get, _ = agent_proc.get_task(term_task_id)
                snapshot_after = extract_task_from_get_task(after_get)
                self.assertEqual(snapshot_after["status"]["state"], expected_state)
                self.assertEqual(len(snapshot_after.get("history", [])), len(snapshot_before.get("history", [])))
                self.assertEqual(snapshot_after.get("artifacts", []), snapshot_before.get("artifacts", []))
        finally:
            agent_proc.stop()
            proxy.stop()
            mcp_proc.stop()

    def test_get_task_durante_working_enquanto_http_mcp_bloqueado_por_barreira(self) -> None:
        mcp_proc = MCPServerSubprocess()
        mcp_proc.start()
        proxy = TransparentMCPObserverProxy(mcp_proc.url)
        proxy.hold_next_tool_call = True
        proxy.start()

        async def _run_barrier_scenario() -> None:
            store = TaskStore()
            settings = AgenteSettings(mcp_url=proxy.url)
            app = create_app(settings, task_store=store)
            await app.state.mcp_host.open()
            try:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:7300") as client:
                    send_payload = {
                        "jsonrpc": "2.0",
                        "id": "working-send-1",
                        "method": "SendMessage",
                        "params": {
                            "message": {
                                "messageId": "msg-working-1",
                                "role": "ROLE_USER",
                                "parts": [
                                    {
                                        "text": (
                                            "reservar sala=sala-porao "
                                            "inicio=2026-11-03T09:00:00-03:00 "
                                            "fim=2026-11-03T10:00:00-03:00 "
                                            "responsavel=Doc"
                                        )
                                    }
                                ],
                            }
                        },
                    }
                    send_future = asyncio.create_task(client.post("/a2a", json=send_payload))

                    entered = await asyncio.to_thread(proxy.tool_call_entered.wait, 5.0)
                    self.assertTrue(entered, "A chamada HTTP tools/call não atingiu a barreira no tempo esperado")

                    # Descobre o id da Task criada antes do retorno de SendMessage e consulta via GetTask
                    task_ids = list(store._records.keys())
                    self.assertEqual(len(task_ids), 1)
                    in_flight_task_id = task_ids[0]

                    get_payload = {
                        "jsonrpc": "2.0",
                        "id": "working-get-1",
                        "method": "GetTask",
                        "params": {"id": in_flight_task_id},
                    }
                    get_http_resp = await client.post("/a2a", json=get_payload)
                    self.assertEqual(get_http_resp.status_code, 200)
                    working_task = extract_task_from_get_task(get_http_resp.json())
                    self.assertEqual(working_task["id"], in_flight_task_id)
                    self.assertTrue(working_task.get("contextId"))
                    self.assertEqual(working_task["status"]["state"], "TASK_STATE_WORKING")
                    self.assertFalse(working_task.get("artifacts"))
                    self.assertEqual(len(working_task.get("history") or []), 1)
                    self.assertEqual(working_task["history"][0]["role"], "ROLE_USER")

                    # Libera a barreira HTTP MCP e aguarda a conclusão do SendMessage
                    proxy.tool_call_release.set()
                    send_http_resp = await send_future
                    self.assertEqual(send_http_resp.status_code, 200)
                    completed_task = send_http_resp.json()["result"]["task"]
                    self.assertEqual(completed_task["id"], in_flight_task_id)
                    self.assertEqual(completed_task["status"]["state"], "TASK_STATE_COMPLETED")
                    self.assertEqual(len(completed_task.get("artifacts") or []), 1)
            finally:
                await app.state.mcp_host.close()

        try:
            asyncio.run(_run_barrier_scenario())
        finally:
            proxy.stop()
            mcp_proc.stop()


class TestAgenteUS3DescobertaWireTraceparentEStderr(unittest.TestCase):
    """Testes HTTP reais de descoberta, headers/metadata no wire, stderr MCP e isolamento de trace (T026)."""

    def test_wire_http_e_stderr_mcp_com_trace_a_trace_b_e_sem_trace(self) -> None:
        mcp_proc = MCPServerSubprocess()
        mcp_proc.start()
        proxy = TransparentMCPObserverProxy(mcp_proc.url)
        proxy.start()
        agent_proc = AgenteServerSubprocess(mcp_url=proxy.url)
        try:
            agent_proc.start()

            trace_a = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
            trace_b = "00-99999999999999999999999999999999-1111111111111111-01"

            # Task 1 com trace A
            st_a, resp_a, _ = agent_proc.send_message(
                "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 "
                "fim=2026-11-03T10:00:00-03:00 responsavel=Doc",
                req_id="us3-task-a",
                traceparent=trace_a,
            )
            self.assertEqual(st_a, 200)
            self.assertEqual(resp_a["result"]["task"]["status"]["state"], "TASK_STATE_COMPLETED")

            # Task 2 com trace B
            st_b, resp_b, _ = agent_proc.send_message(
                "reservar sala=sala-aquario inicio=2026-11-03T10:00:00-03:00 "
                "fim=2026-11-03T11:00:00-03:00 responsavel=Marty",
                req_id="us3-task-b",
                traceparent=trace_b,
            )
            self.assertEqual(st_b, 200)
            self.assertEqual(resp_b["result"]["task"]["status"]["state"], "TASK_STATE_COMPLETED")

            # Task 3 sem header traceparent (não pode herdar trace A nem trace B)
            st_none, resp_none, _ = agent_proc.send_message(
                "reservar sala=sala-fusca inicio=2026-11-03T11:00:00-03:00 "
                "fim=2026-11-03T12:00:00-03:00 responsavel=Lorraine",
                req_id="us3-task-none",
                traceparent=None,
            )
            self.assertEqual(st_none, 200)
            self.assertEqual(resp_none["result"]["task"]["status"]["state"], "TASK_STATE_COMPLETED")

            # Verifica a sequência capturada no wire HTTP entre agente e servidor MCP
            post_reqs = [
                r
                for r in proxy.captured_requests
                if r["http_method"] == "POST" and isinstance(r.get("json"), dict)
            ]
            methods = [r["json"].get("method") for r in post_reqs]
            self.assertEqual(
                methods,
                ["tools/list", "resources/read", "tools/list", "tools/call",
                 "tools/list", "tools/call", "tools/list", "tools/call"],
            )

            expected_names = [
                None, "politica://uso", None, "reservar_sala",
                None, "reservar_sala", None, "reservar_sala",
            ]
            for req, exp_method, exp_name in zip(post_reqs, methods, expected_names, strict=True):
                headers_lower = req["headers_lower"]
                body = req["json"]
                params = body.get("params") or {}
                meta = params.get("_meta") or {}

                self.assertEqual(headers_lower.get("mcp-protocol-version"), "2026-07-28")
                self.assertEqual(headers_lower.get("mcp-method"), exp_method)
                if exp_name is None:
                    self.assertNotIn("mcp-name", headers_lower)
                else:
                    self.assertEqual(headers_lower.get("mcp-name"), exp_name)

                self.assertEqual(meta.get("io.modelcontextprotocol/protocolVersion"), "2026-07-28")
                self.assertIn("io.modelcontextprotocol/clientCapabilities", meta)
                caps = meta["io.modelcontextprotocol/clientCapabilities"]
                self.assertIn("elicitation", caps)
                self.assertEqual(caps["elicitation"].get("form"), {})

            # Conferência de isolamento de traceparent no wire HTTP
            for req in post_reqs[:4]:
                meta = (req["json"].get("params") or {}).get("_meta") or {}
                self.assertTrue(
                    str(meta.get("traceparent", "")).startswith("00-4bf92f3577b34da6a3ce929d0e0e4736-")
                )

            for req in post_reqs[4:6]:
                meta_task_b = (req["json"].get("params") or {}).get("_meta") or {}
                self.assertTrue(
                    str(meta_task_b.get("traceparent", "")).startswith("00-99999999999999999999999999999999-")
                )

            for req in post_reqs[6:]:
                meta_task_none = (req["json"].get("params") or {}).get("_meta") or {}
                self.assertNotIn("traceparent", meta_task_none)

            # Conferência do stderr real do servidor MCP: método, id e traceparent registrados
            stderr_text = mcp_proc.read_stderr()
            self.assertIn("method=tools/list", stderr_text)
            self.assertIn("method=resources/read", stderr_text)
            self.assertIn("method=tools/call", stderr_text)
            self.assertIn("4bf92f3577b34da6a3ce929d0e0e4736", stderr_text)
            self.assertIn("99999999999999999999999999999999", stderr_text)
            for req in post_reqs:
                req_id_str = str(req["json"].get("id"))
                self.assertIn(f"id={req_id_str}", stderr_text)
        finally:
            agent_proc.stop()
            proxy.stop()
            mcp_proc.stop()


class TestAgentePolishStartupCwdEnvIsolamento(unittest.TestCase):
    """Testes de regressão de startup em outro cwd, env overrides, isolamento e manifesto (T033)."""

    def test_startup_em_outro_cwd_sem_request_state_secret_overrides_e_desligamento_limpo(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ponte_agente_empty_cwd_") as empty_dir:
            custom_base = "https://salas.hillvalley.example:8443"
            with running_mcp_and_agent(
                agent_cwd=Path(empty_dir),
                agent_extra_env={"A2A_BASE_URL": custom_base},
            ) as (_, agent_proc):
                # Verifica que o diretório de trabalho do agente não possui dados/
                self.assertFalse((Path(empty_dir) / "dados").exists())

                status, card, _ = agent_proc.get_card()
                self.assertEqual(status, 200)
                interfaces = card.get("supportedInterfaces") or []
                self.assertEqual(len(interfaces), 1)
                self.assertEqual(interfaces[0].get("url"), f"{custom_base}/a2a")

                st_send, resp_send, _ = agent_proc.send_message(
                    "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 "
                    "fim=2026-11-03T10:00:00-03:00 responsavel=Doc",
                    req_id="polish-cwd-1",
                )
                self.assertEqual(st_send, 200)
                self.assertEqual(resp_send["result"]["task"]["status"]["state"], "TASK_STATE_COMPLETED")

                # Desligamento limpo do processo do agente
                agent_proc.stop()
                self.assertIsNotNone(agent_proc.proc)
                assert agent_proc.proc is not None
                self.assertIsNotNone(agent_proc.proc.poll())

    def test_padroes_settings_isolamento_de_codigo_e_manifesto_sem_llm_ou_extras(self) -> None:
        # 1. Padrões de AgenteSettings
        defaults = AgenteSettings()
        self.assertEqual(defaults.host, "127.0.0.1")
        self.assertEqual(defaults.port, 7300)
        self.assertEqual(defaults.mcp_url, "http://127.0.0.1:7301/mcp")
        self.assertEqual(defaults.a2a_base_url, "http://127.0.0.1:7300")

        # 2. Overrides por ambiente
        saved_env = os.environ.copy()
        try:
            for k in ("AGENTE_HOST", "AGENTE_PORT", "MCP_URL", "A2A_BASE_URL"):
                os.environ.pop(k, None)
            env_defaults = AgenteSettings.from_env()
            self.assertEqual(env_defaults, defaults)

            os.environ["AGENTE_HOST"] = "0.0.0.0"
            os.environ["AGENTE_PORT"] = "7400"
            os.environ["MCP_URL"] = "http://127.0.0.1:7401/mcp"
            os.environ["A2A_BASE_URL"] = "http://localhost:7400/"
            overridden = AgenteSettings.from_env()
            self.assertEqual(overridden.host, "0.0.0.0")
            self.assertEqual(overridden.port, 7400)
            self.assertEqual(overridden.mcp_url, "http://127.0.0.1:7401/mcp")
            self.assertEqual(overridden.a2a_base_url, "http://localhost:7400")
        finally:
            os.environ.clear()
            os.environ.update(saved_env)

        # 3. Isolamento do código do agente: sem importar ponte_mcp nem carregar JSON de dados/
        agente_src = ROOT_DIR / "agente" / "src" / "ponte_agente"
        for py_file in agente_src.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            self.assertNotIn("ponte_mcp", source, f"{py_file.name} não pode referenciar ponte_mcp")
            self.assertNotIn("salas.json", source, f"{py_file.name} não pode ler salas.json")
            self.assertNotIn("reservas.json", source, f"{py_file.name} não pode ler reservas.json")
            self.assertNotIn("politica-de-uso.md", source, f"{py_file.name} não pode ler arquivo local de política")
            self.assertNotIn("REQUEST_STATE_SECRET", source, f"{py_file.name} não pode ler REQUEST_STATE_SECRET")

        # 4. Manifesto pyproject.toml: pins exatos, sem LLM e sem extras fora de escopo
        pyproject_text = (ROOT_DIR / "agente" / "pyproject.toml").read_text(encoding="utf-8").lower()
        for expected_pin in (
            "mcp==2.3.0",
            "a2a-sdk[http-server]==1.2.3",
            "starlette==0.48.0",
            "uvicorn==0.31.1",
            "sse-starlette==3.0.3",
            "pydantic==2.12.0",
            "hatchling==1.27.0",
        ):
            self.assertIn(expected_pin, pyproject_text)

        for forbidden in (
            "openai",
            "anthropic",
            "google-genai",
            "vertexai",
            "langchain",
            "litellm",
            "a2a-sdk[all]",
            "opentelemetry-sdk",
            "sqlalchemy",
            "fastapi",
        ):
            self.assertNotIn(forbidden, pyproject_text)


if __name__ == "__main__":
    unittest.main()
