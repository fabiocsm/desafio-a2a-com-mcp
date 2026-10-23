"""Testes da ponte A2A–MRTR: pausa, retomada, terminais, isolamento e trace por Task."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import asyncio
import json
import secrets
import threading
from typing import Any
import unittest
import urllib.error
import urllib.request

from a2a.server.context import ServerCallContext
from a2a.types import a2a_pb2
from google.protobuf.json_format import MessageToJson
from mcp.shared.exceptions import MCPError
import mcp_types as types

from ponte_agente.handler import TECHNICAL_MCP_FAILURE_MESSAGE, AgenteRequestHandler
from ponte_agente.mcp_host import HostSnapshot, MCPHost, defensive_elicitation_callback
from ponte_agente.ponte import (
    PonteFormatoError,
    build_retry_input_responses,
    continuation_from_input_required,
    interpret_client_decision,
    pause_text_for,
)
from ponte_agente.tasks import TaskStore, build_message
from test_agente_direto import (
    AgenteServerSubprocess,
    MCPServerSubprocess,
    ROOT_DIR,
    find_free_port,
)
from test_mcp_host import ObservingMCPHTTPServer, RecordedHTTPRequest

DADOS_DIR = ROOT_DIR / "dados"
DIA = "2026-11-03"
POLICY_VERSION = (DADOS_DIR / "politica-de-uso.md").read_text(encoding="utf-8").splitlines()[0].split(":", 1)[1].strip()
PAUSE_GARAGEM = "alternativas: sala-fusca, sala-mirante"
SENTINEL = "v1.SENTINEL_OPAQUE_NAO_PUBLICAR"
_DADOS_INICIAIS: dict[str, bytes] = {}


def setUpModule() -> None:
    global _DADOS_INICIAIS
    _DADOS_INICIAIS = {
        path.name: path.read_bytes() for path in sorted(DADOS_DIR.iterdir()) if path.is_file()
    }


def tearDownModule() -> None:
    for name, blob in _DADOS_INICIAIS.items():
        atual = (DADOS_DIR / name).read_bytes()
        if atual != blob:
            raise AssertionError(f"dados/{name} foi alterado durante os testes da ponte")


def instante(hora: str) -> str:
    return f"{DIA}T{hora}:00-03:00"


def comando_reserva(sala: str, inicio: str, fim: str, responsavel: str) -> str:
    return f"reservar sala={sala} inicio={inicio} fim={fim} responsavel={responsavel}"


def traceparent(trace_id: str, span: str | None = None) -> str:
    return f"00-{trace_id}-{span or secrets.token_hex(8)}-01"


def novo_trace_id() -> str:
    return secrets.token_hex(16)


def task_de(resposta: dict[str, Any]) -> dict[str, Any]:
    resultado = resposta.get("result") or {}
    tarefa = resultado.get("task")
    if isinstance(tarefa, dict):
        return tarefa
    return resultado


def texto_status(tarefa: dict[str, Any]) -> str:
    partes = ((tarefa.get("status") or {}).get("message") or {}).get("parts") or []
    if not partes:
        return ""
    return str(partes[0].get("text", ""))


def artefato_reserva(tarefa: dict[str, Any]) -> dict[str, Any]:
    artifacts = tarefa.get("artifacts") or []
    if not artifacts:
        return {}
    texto = "".join(part.get("text", "") for part in artifacts[0].get("parts") or [])
    return json.loads(texto)


def chamadas(proxy: PonteProxy, method: str) -> list[dict[str, Any]]:
    return [item for item in proxy.captured if (item.get("json") or {}).get("method") == method]


def trace_id_de(chamada: dict[str, Any]) -> str | None:
    meta = ((chamada.get("json") or {}).get("params") or {}).get("_meta") or {}
    bruto = meta.get("traceparent")
    if not isinstance(bruto, str):
        return None
    partes = bruto.split("-")
    if len(partes) >= 2 and len(partes[1]) == 32:
        return partes[1].lower()
    return None


def tokens_observados(proxy: PonteProxy) -> list[str]:
    tokens: list[str] = []
    for item in proxy.captured:
        resultado = ((item.get("response_json") or {}).get("result") or {})
        estado = resultado.get("requestState")
        if isinstance(estado, str) and estado:
            tokens.append(estado)
    return tokens


def sala_esta_livre(mcp: MCPServerSubprocess, sala: str, inicio: str, fim: str) -> bool:
    _status, body, _raw = mcp.call_tool(
        "consultar_disponibilidade",
        {"sala": sala, "inicio": inicio, "fim": fim},
        req_id=f"disp-{sala}",
    )
    dados = ((body.get("result") or {}).get("structuredContent")) or {}
    return dados.get("livre") is True


def assert_sem_segredo(caso: unittest.TestCase, texto: str, tokens: list[str]) -> None:
    caso.assertNotIn("requestState", texto)
    for token in tokens:
        caso.assertNotIn(token, texto)


class PonteProxy:
    """Proxy HTTP que grava pedidos e respostas MCP e pode segurar só o retry."""

    def __init__(self, target_url: str, *, host: str = "127.0.0.1") -> None:
        self.target_url = target_url
        self.host = host
        self.port = find_free_port(host)
        self.captured: list[dict[str, Any]] = []
        self.hold_retry = False
        self.retry_entered = threading.Event()
        self.retry_release = threading.Event()
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/mcp"

    def start(self) -> None:
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def do_POST(self) -> None:  # noqa: N802
                self._forward("POST")

            def do_GET(self) -> None:  # noqa: N802
                self._forward("GET")

            def do_DELETE(self) -> None:  # noqa: N802
                self._forward("DELETE")

            def _forward(self, method: str) -> None:
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw_body = self.rfile.read(length) if length else b""
                headers_orig = {key: value for key, value in self.headers.items()}
                headers_lower = {key.lower(): value for key, value in headers_orig.items()}
                parsed: dict[str, Any] | None = None
                if raw_body:
                    try:
                        decoded = json.loads(raw_body.decode("utf-8"))
                        if isinstance(decoded, dict):
                            parsed = decoded
                    except (UnicodeError, json.JSONDecodeError):
                        parsed = None

                record: dict[str, Any] = {
                    "http_method": method,
                    "headers_lower": headers_lower,
                    "json": parsed,
                    "response_json": None,
                }
                with proxy._lock:
                    proxy.captured.append(record)
                    params = (parsed or {}).get("params") or {}
                    should_hold = (
                        proxy.hold_retry
                        and isinstance(parsed, dict)
                        and parsed.get("method") == "tools/call"
                        and isinstance(params, dict)
                        and ("inputResponses" in params or "requestState" in params)
                    )
                    if should_hold:
                        proxy.hold_retry = False

                if should_hold:
                    proxy.retry_entered.set()
                    proxy.retry_release.wait(timeout=10.0)

                forward_headers = {
                    key: value
                    for key, value in headers_orig.items()
                    if key.lower() not in {"host", "content-length", "connection"}
                }
                request = urllib.request.Request(
                    proxy.target_url,
                    data=raw_body if method == "POST" else None,
                    headers=forward_headers,
                    method=method,
                )
                try:
                    with urllib.request.urlopen(request, timeout=10.0) as response:
                        status = int(response.status)
                        response_headers = list(response.headers.items())
                        response_body = response.read()
                except urllib.error.HTTPError as err:
                    status = int(err.code)
                    response_headers = list(err.headers.items()) if err.headers else []
                    response_body = err.read()
                except urllib.error.URLError:
                    status = 502
                    response_headers = []
                    response_body = b'{"jsonrpc":"2.0","error":{"code":-32000,"message":"upstream unavailable"}}'

                try:
                    decoded_response = json.loads(response_body.decode("utf-8"))
                    if isinstance(decoded_response, dict):
                        record["response_json"] = decoded_response
                except (UnicodeError, json.JSONDecodeError):
                    record["response_json"] = None

                self.send_response(status)
                for key, value in response_headers:
                    if key.lower() in {"transfer-encoding", "connection", "content-length", "server", "date"}:
                        continue
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                if response_body:
                    self.wfile.write(response_body)

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.retry_release.set()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None


class PonteStack:
    """MCP real, proxy observador e agente, cada um em processo próprio."""

    def __init__(self) -> None:
        self.mcp = MCPServerSubprocess()
        self.proxy: PonteProxy | None = None
        self.agent: AgenteServerSubprocess | None = None

    def __enter__(self) -> PonteStack:
        self.mcp.start()
        self.proxy = PonteProxy(self.mcp.url)
        self.proxy.start()
        self.agent = AgenteServerSubprocess(mcp_url=self.proxy.url)
        self.agent.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.agent is not None:
            self.agent.stop()
        if self.proxy is not None:
            self.proxy.stop()
        self.mcp.stop()

    @property
    def agente(self) -> AgenteServerSubprocess:
        assert self.agent is not None
        return self.agent

    @property
    def observador(self) -> PonteProxy:
        assert self.proxy is not None
        return self.proxy


def formulario(
    *,
    key: str,
    token: str,
    enum: list[str] | None = None,
    const: str | None = None,
) -> types.InputRequiredResult:
    sala: dict[str, Any] = {"type": "string"}
    if enum is not None:
        sala["enum"] = list(enum)
    if const is not None:
        sala["const"] = const
    return types.InputRequiredResult(
        input_requests={
            key: types.ElicitRequest(
                params=types.ElicitRequestFormParams(
                    mode="form",
                    message="A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa.",
                    requested_schema={
                        "type": "object",
                        "properties": {"sala": sala},
                        "required": ["sala"],
                    },
                )
            )
        },
        request_state=token,
    )


def argumentos_garagem() -> dict[str, str]:
    return {
        "sala": "sala-garagem",
        "inicio": instante("14:00"),
        "fim": instante("15:00"),
        "responsavel": "Marty",
    }


class ScriptedHost:
    """Host duplo: devolve resultados controlados e observa o estado da Task durante o await."""

    def __init__(self, resultados: list[Any], store: TaskStore) -> None:
        self.resultados = list(resultados)
        self.store = store
        self.calls: list[dict[str, Any]] = []
        self.states_during_call: list[int] = []

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
            policy_text=f"versao: {POLICY_VERSION}\n",
            policy_version=POLICY_VERSION,
        )

    async def call_tool_raw(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        trace: Any = None,
        input_responses: Any = None,
        request_state: str | None = None,
    ) -> Any:
        task_id = next(iter(self.store._records))
        record = self.store.get_record(task_id)
        self.states_during_call.append(record.public_task.status.state if record else -1)
        self.calls.append(
            {
                "name": name,
                "arguments": dict(arguments or {}),
                "input_responses": input_responses,
                "request_state": request_state,
                "trace": trace.original_traceparent if trace is not None else None,
            }
        )
        item = self.resultados.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def mensagem_reserva(texto: str, *, task_id: str = "") -> a2a_pb2.SendMessageRequest:
    message = build_message(role=a2a_pb2.ROLE_USER, text=texto, task_id=task_id or None)
    return a2a_pb2.SendMessageRequest(message=message)


class TestFormularioETraducao(unittest.TestCase):
    """Leitura do formulário MCP sem consultar domínio e sem fixar a chave."""

    def test_enum_preserva_ordem_chave_variavel_e_token_literal(self) -> None:
        chave = "pergunta-" + secrets.token_hex(4)
        token = SENTINEL + "-enum"
        pending = continuation_from_input_required(
            formulario(key=chave, token=token, enum=["sala-mirante", "sala-fusca"]),
            tool_name="reservar_sala",
            original_arguments=argumentos_garagem(),
        )
        self.assertEqual(pending.elicitation_key, chave)
        self.assertEqual(pending.request_state, token)
        self.assertEqual(pending.ordered_alternatives, ("sala-mirante", "sala-fusca"))
        self.assertEqual(pending.pause_text, "alternativas: sala-mirante, sala-fusca")
        self.assertNotIn("\n", pending.pause_text)
        self.assertEqual(pending.original_arguments.as_mcp_dict(), argumentos_garagem())
        self.assertNotEqual(pending.elicitation_key, "__main__:escolha_de_sala")

    def test_const_de_opcao_unica_e_recusa_sem_sala(self) -> None:
        pending = continuation_from_input_required(
            formulario(key="unica-9", token=SENTINEL, const="sala-fusca"),
            tool_name="reservar_sala",
            original_arguments=argumentos_garagem(),
        )
        self.assertEqual(pending.ordered_alternatives, ("sala-fusca",))
        self.assertEqual(pending.pause_text, pause_text_for(["sala-fusca"]))

        recusa = interpret_client_decision("escolha=recusar")
        assert recusa is not None
        self.assertEqual(recusa.tipo, "recusa")
        self.assertIsNone(recusa.sala)
        corpo = build_retry_input_responses(pending, recusa)["unica-9"].model_dump(exclude_none=True)
        self.assertEqual(corpo, {"action": "decline"})
        self.assertNotIn("sala", corpo)

        escolha = interpret_client_decision("escolha=sala-fusca")
        assert escolha is not None
        aceito = build_retry_input_responses(pending, escolha)["unica-9"].model_dump(exclude_none=True)
        self.assertEqual(aceito["action"], "accept")
        self.assertEqual(aceito["content"], {"sala": "sala-fusca"})

    def test_formulario_invalido_nao_inclui_o_token_na_excecao(self) -> None:
        with self.assertRaises(PonteFormatoError) as contexto:
            continuation_from_input_required(
                types.InputRequiredResult(
                    input_requests={
                        "a": types.ElicitRequest(
                            params=types.ElicitRequestFormParams(
                                mode="form",
                                message="duas",
                                requested_schema={"type": "object", "properties": {}, "required": []},
                            )
                        ),
                        "b": types.ElicitRequest(
                            params=types.ElicitRequestFormParams(
                                mode="form",
                                message="perguntas",
                                requested_schema={"type": "object", "properties": {}, "required": []},
                            )
                        ),
                    },
                    request_state=SENTINEL,
                ),
                tool_name="reservar_sala",
                original_arguments=argumentos_garagem(),
            )
        self.assertNotIn(SENTINEL, str(contexto.exception))


class TestPausaNoHandler(unittest.IsolatedAsyncioTestCase):
    """O callback defensivo não responde e a Task passa por SUBMITTED e WORKING."""

    async def test_callback_nunca_chamado_enum_fora_de_ordem_e_const(self) -> None:
        callbacks: list[Any] = []

        async def callback(ctx: Any, params: Any) -> Any:
            callbacks.append((ctx, params))
            return await defensive_elicitation_callback(ctx, params)

        chave = "chave-" + secrets.token_hex(3)
        token = SENTINEL + "-handler"

        def responder(req: RecordedHTTPRequest) -> tuple[int, dict[str, Any]]:
            if req.body.get("method") == "tools/call":
                params = req.body.get("params") or {}
                if "inputResponses" in params:
                    args = params.get("arguments") or {}
                    sala = params["inputResponses"][chave]["content"]["sala"]
                    payload = {
                        "reserva": "res-script",
                        "reservado": True,
                        "sala": sala,
                        "inicio": args["inicio"],
                        "fim": args["fim"],
                        "responsavel": args["responsavel"],
                        "politica": POLICY_VERSION,
                    }
                    return 200, {
                        "jsonrpc": "2.0",
                        "id": req.body.get("id"),
                        "result": {
                            "resultType": "complete",
                            "isError": False,
                            "content": [{"type": "text", "text": json.dumps(payload)}],
                            "structuredContent": payload,
                        },
                    }
                return 200, {
                    "jsonrpc": "2.0",
                    "id": req.body.get("id"),
                    "result": formulario(
                        key=chave,
                        token=token,
                        enum=["sala-mirante", "sala-fusca"],
                    ).model_dump(by_alias=True, mode="json", exclude_none=True),
                }
            from test_mcp_host import _default_mcp_responder

            return _default_mcp_responder(req)

        server = ObservingMCPHTTPServer(responder)
        server.start()
        try:
            store = TaskStore()
            async with MCPHost(server.url, elicitation_callback=callback) as host:
                handler = AgenteRequestHandler(mcp_host=host, task_store=store)
                texto = comando_reserva("sala-garagem", instante("14:00"), instante("15:00"), "Marty")
                tarefa = await handler.on_message_send(mensagem_reserva(texto), ServerCallContext())
                assert isinstance(tarefa, a2a_pb2.Task)
                registro = store.get_record(tarefa.id)
                assert registro is not None
                self.assertEqual(
                    registro.state_transitions[:2],
                    [a2a_pb2.TASK_STATE_SUBMITTED, a2a_pb2.TASK_STATE_WORKING],
                )
                self.assertEqual(tarefa.status.state, a2a_pb2.TASK_STATE_INPUT_REQUIRED)
                self.assertEqual(tarefa.status.message.parts[0].text, "alternativas: sala-mirante, sala-fusca")
                self.assertEqual(registro.pending.elicitation_key if registro.pending else "", chave)
                self.assertEqual(registro.pending.request_state if registro.pending else "", token)
                consultada = await handler.on_get_task(a2a_pb2.GetTaskRequest(id=tarefa.id), ServerCallContext())
                assert consultada is not None
                self.assertEqual(consultada.id, tarefa.id)
                self.assertEqual(consultada.context_id, tarefa.context_id)
                self.assertEqual(consultada.status.message.parts[0].text, tarefa.status.message.parts[0].text)
                self.assertIs(registro.pending, store.get_record(tarefa.id).pending)
                publico = MessageToJson(tarefa) + MessageToJson(consultada)
                self.assertNotIn(token, publico)
                self.assertNotIn("requestState", publico)
                self.assertEqual(callbacks, [])
                tool_calls = [item for item in server.requests if item.body.get("method") == "tools/call"]
                self.assertEqual(len(tool_calls), 1)
        finally:
            server.stop()

    async def test_retomada_controlada_fica_working_e_conclui_com_argumentos_originais(self) -> None:
        store = TaskStore()
        sucesso = {
            "reserva": "res-ponte",
            "reservado": True,
            "sala": "sala-fusca",
            "inicio": instante("14:00"),
            "fim": instante("15:00"),
            "responsavel": "Marty",
            "politica": "ignorada-pela-tool",
        }
        host = ScriptedHost(
            [
                formulario(key="k-retomada", token=SENTINEL, enum=["sala-fusca", "sala-mirante"]),
                types.CallToolResult(
                    isError=False,
                    content=[types.TextContent(type="text", text=json.dumps(sucesso))],
                    structuredContent=sucesso,
                ),
            ],
            store,
        )
        handler = AgenteRequestHandler(mcp_host=host, task_store=store)  # type: ignore[arg-type]
        texto = comando_reserva("sala-garagem", instante("14:00"), instante("15:00"), "Marty")
        pausada = await handler.on_message_send(mensagem_reserva(texto), ServerCallContext())
        assert isinstance(pausada, a2a_pb2.Task)
        self.assertEqual(host.states_during_call[0], a2a_pb2.TASK_STATE_WORKING)

        concluida = await handler.on_message_send(
            mensagem_reserva("escolha=sala-fusca", task_id=pausada.id),
            ServerCallContext(),
        )
        assert isinstance(concluida, a2a_pb2.Task)
        self.assertEqual(host.states_during_call[1], a2a_pb2.TASK_STATE_WORKING)
        self.assertEqual(concluida.status.state, a2a_pb2.TASK_STATE_COMPLETED)
        self.assertEqual(json.loads(concluida.artifacts[0].parts[0].text)["politica"], POLICY_VERSION)
        self.assertEqual(json.loads(concluida.artifacts[0].parts[0].text)["sala"], "sala-fusca")
        retry = host.calls[1]
        self.assertEqual(retry["arguments"]["sala"], "sala-garagem")
        self.assertEqual(retry["request_state"], SENTINEL)
        self.assertIn("k-retomada", retry["input_responses"])
        registro = store.get_record(pausada.id)
        assert registro is not None
        self.assertIsNone(registro.pending)


class TestErrosControlados(unittest.IsolatedAsyncioTestCase):
    """isError, protocolo e rede na retomada terminam FAILED sem vazar o token."""

    async def _pausar(self, host: ScriptedHost) -> a2a_pb2.Task:
        handler = AgenteRequestHandler(mcp_host=host, task_store=host.store)  # type: ignore[arg-type]
        texto = comando_reserva("sala-garagem", instante("14:00"), instante("15:00"), "Marty")
        tarefa = await handler.on_message_send(mensagem_reserva(texto), ServerCallContext(state={}))
        assert isinstance(tarefa, a2a_pb2.Task)
        self.handler = handler
        return tarefa

    async def test_queda_http_na_retomada_falha_sem_replay_e_nova_task_funciona(self) -> None:
        from test_mcp_host import _default_mcp_responder

        falhar = True
        efeitos: list[str] = []

        def responder(req: RecordedHTTPRequest) -> tuple[int, dict[str, Any]]:
            params = req.body.get("params") or {}
            if req.body.get("method") == "tools/call" and "inputResponses" in params:
                # Simula resposta perdida depois de o servidor efetivar a operação.
                efeitos.append(params["requestState"])
                if falhar:
                    raise ConnectionResetError("resposta perdida depois da reserva")
                req = RecordedHTTPRequest(req.raw_headers, {
                    **req.body, "params": {**params, "arguments": {
                        **params["arguments"], "sala": params["inputResponses"]["elicit-1"]["content"]["sala"],
                    }},
                })
            return _default_mcp_responder(req)

        server = ObservingMCPHTTPServer(responder)
        server.start()
        try:
            store = TaskStore()
            async with MCPHost(server.url) as host:
                handler = AgenteRequestHandler(mcp_host=host, task_store=store)
                pausada = await handler.on_message_send(
                    mensagem_reserva(comando_reserva("sala-garagem", instante("14:00"), instante("15:00"), "Marty")),
                    ServerCallContext(),
                )
                assert isinstance(pausada, a2a_pb2.Task)
                self.assertEqual(pausada.status.state, a2a_pb2.TASK_STATE_INPUT_REQUIRED)
                outra = await handler.on_message_send(
                    mensagem_reserva(comando_reserva("sala-garagem", instante("14:00"), instante("15:00"), "Doc")),
                    ServerCallContext(state={"traceparent": traceparent("1" * 32)}),
                )
                assert isinstance(outra, a2a_pb2.Task)
                # A requisição A2A não é a coroutine que abriu o lifespan do host.
                final = await asyncio.create_task(handler.on_message_send(
                    mensagem_reserva("escolha=sala-fusca", task_id=pausada.id), ServerCallContext(),
                ))
                assert isinstance(final, a2a_pb2.Task)
                self.assertEqual(final.status.state, a2a_pb2.TASK_STATE_FAILED)
                self.assertEqual(final.status.message.parts[0].text, TECHNICAL_MCP_FAILURE_MESSAGE)
                self.assertEqual(len(efeitos), 1, "uma operação com resposta perdida não pode ser repetida")
                registro = store.get_record(pausada.id)
                assert registro is not None
                self.assertIsNone(registro.pending)
                self.assertIsNone(registro.raw_input_required)
                consultada = await handler.on_get_task(a2a_pb2.GetTaskRequest(id=pausada.id), ServerCallContext())
                assert consultada is not None
                self.assertEqual(consultada.status.state, a2a_pb2.TASK_STATE_FAILED)
                self.assertNotIn(efeitos[0], MessageToJson(consultada))
                falhar = False
                nova = await asyncio.create_task(handler.on_message_send(
                    mensagem_reserva(comando_reserva("sala-aquario", instante("09:00"), instante("10:00"), "Doc")),
                    ServerCallContext(),
                ))
                assert isinstance(nova, a2a_pb2.Task)
                self.assertEqual(nova.status.state, a2a_pb2.TASK_STATE_COMPLETED)
                self.assertNotEqual(nova.id, pausada.id)
                self.assertEqual(len(efeitos), 1)
                retomada = await asyncio.create_task(handler.on_message_send(
                    mensagem_reserva("escolha=sala-mirante", task_id=outra.id), ServerCallContext(),
                ))
                assert isinstance(retomada, a2a_pb2.Task)
                self.assertEqual(retomada.status.state, a2a_pb2.TASK_STATE_COMPLETED)
                tool_calls = [req for req in server.requests if req.body.get("method") == "tools/call"]
                ids = [req.body["id"] for req in tool_calls]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertEqual(
                    tool_calls[-1].body["params"]["_meta"]["traceparent"].split("-")[1], "1" * 32,
                )
        finally:
            server.stop()

    async def test_is_error_com_reservado_false_nao_cancela(self) -> None:
        store = TaskStore()
        mensagem = "Erro controlado de retomada"
        host = ScriptedHost(
            [
                formulario(key="k-erro", token=SENTINEL, enum=["sala-fusca"]),
                types.CallToolResult(
                    isError=True,
                    content=[types.TextContent(type="text", text=mensagem)],
                    structuredContent={"reservado": False, "motivo": "nao-e-recusa"},
                ),
            ],
            store,
        )
        pausada = await self._pausar(host)
        final = await self.handler.on_message_send(
            mensagem_reserva("escolha=sala-fusca", task_id=pausada.id),
            ServerCallContext(),
        )
        assert isinstance(final, a2a_pb2.Task)
        self.assertEqual(final.status.state, a2a_pb2.TASK_STATE_FAILED)
        self.assertEqual(final.status.message.parts[0].text, mensagem)
        self.assertEqual(len(final.artifacts), 0)
        registro = store.get_record(pausada.id)
        assert registro is not None
        self.assertIsNone(registro.pending)
        self.assertNotIn(SENTINEL, MessageToJson(final))

    async def test_erro_jsonrpc_e_rede_limpam_continuacao_sem_token(self) -> None:
        for falha in (
            MCPError(-32602, f"estado expirado {SENTINEL}"),
            ConnectionError(f"falha de rede {SENTINEL}"),
        ):
            store = TaskStore()
            host = ScriptedHost(
                [formulario(key="k-tec", token=SENTINEL, const="sala-fusca"), falha],
                store,
            )
            pausada = await self._pausar(host)
            final = await self.handler.on_message_send(
                mensagem_reserva("escolha=sala-fusca", task_id=pausada.id),
                ServerCallContext(),
            )
            assert isinstance(final, a2a_pb2.Task)
            self.assertEqual(final.status.state, a2a_pb2.TASK_STATE_FAILED)
            self.assertEqual(final.status.message.parts[0].text, TECHNICAL_MCP_FAILURE_MESSAGE)
            self.assertEqual(len(final.artifacts), 0)
            registro = store.get_record(pausada.id)
            assert registro is not None
            self.assertIsNone(registro.pending)
            self.assertNotIn(SENTINEL, MessageToJson(final))


class TestPonteHTTP(unittest.TestCase):
    """Fluxos com os dois processos HTTP reais e o proxy entre eles."""

    def _pausar_garagem(self, stack: PonteStack, *, trace_id: str | None) -> dict[str, Any]:
        headers_trace = traceparent(trace_id) if trace_id else None
        _status, resposta, bruto = stack.agente.send_message(
            comando_reserva("sala-garagem", instante("14:00"), instante("15:00"), "Marty"),
            traceparent=headers_trace,
            req_id="pausar-garagem",
        )
        self.assertNotIn("error", resposta, bruto)
        tarefa = task_de(resposta)
        self.assertEqual(tarefa["status"]["state"], "TASK_STATE_INPUT_REQUIRED")
        self.assertEqual(texto_status(tarefa), PAUSE_GARAGEM)
        self.assertFalse(tarefa.get("artifacts"))
        return tarefa

    def test_pausa_get_aceite_e_wire_real(self) -> None:
        trace_id = novo_trace_id()
        with PonteStack() as stack:
            pausada = self._pausar_garagem(stack, trace_id=trace_id)
            self.assertTrue(
                sala_esta_livre(stack.mcp, "sala-fusca", instante("14:00"), instante("15:00"))
            )
            _status, consulta, bruto_consulta = stack.agente.get_task(pausada["id"], req_id="get-pausa")
            self.assertNotIn("error", consulta, bruto_consulta)
            consultada = task_de(consulta)
            self.assertEqual(consultada["id"], pausada["id"])
            self.assertEqual(consultada["contextId"], pausada["contextId"])
            self.assertEqual(texto_status(consultada), PAUSE_GARAGEM)
            self.assertEqual(
                consultada["status"]["message"]["messageId"],
                pausada["status"]["message"]["messageId"],
            )

            stack.observador.hold_retry = True
            caixa: list[tuple[int, dict[str, Any], str]] = []

            def continuar() -> None:
                caixa.append(
                    stack.agente.send_message(
                        "escolha=sala-fusca",
                        task_id=pausada["id"],
                        req_id="aceite",
                    )
                )

            trabalhador = threading.Thread(target=continuar)
            trabalhador.start()
            self.assertTrue(stack.observador.retry_entered.wait(8), "retry MCP nao chegou a ser observado")
            _status, durante, _bruto = stack.agente.get_task(pausada["id"], req_id="get-working")
            self.assertEqual(task_de(durante)["status"]["state"], "TASK_STATE_WORKING")
            stack.observador.retry_release.set()
            trabalhador.join(10)
            self.assertEqual(len(caixa), 1)
            _status, resposta, bruto = caixa[0]
            self.assertNotIn("error", resposta, bruto)
            concluida = task_de(resposta)
            self.assertEqual(concluida["id"], pausada["id"])
            self.assertEqual(concluida["contextId"], pausada["contextId"])
            self.assertEqual(concluida["status"]["state"], "TASK_STATE_COMPLETED")
            corpo = artefato_reserva(concluida)
            self.assertEqual(concluida["artifacts"][0]["name"], "reserva")
            self.assertEqual(corpo["sala"], "sala-fusca")
            self.assertEqual(corpo["inicio"], instante("14:00"))
            self.assertEqual(corpo["fim"], instante("15:00"))
            self.assertEqual(corpo["responsavel"], "Marty")
            self.assertEqual(corpo["politica"], POLICY_VERSION)

            _status, final, bruto_final = stack.agente.get_task(pausada["id"], req_id="get-final")
            final_task = task_de(final)
            self.assertEqual(final_task["status"]["state"], "TASK_STATE_COMPLETED")
            self.assertEqual(artefato_reserva(final_task)["reserva"], corpo["reserva"])
            self.assertFalse(sala_esta_livre(stack.mcp, "sala-fusca", instante("14:00"), instante("15:00")))

            listas = chamadas(stack.observador, "tools/list")
            reservas = chamadas(stack.observador, "tools/call")
            self.assertGreaterEqual(len(listas), 1)
            self.assertEqual(len(reservas), 2)
            self.assertLess(stack.observador.captured.index(listas[0]), stack.observador.captured.index(reservas[0]))
            inicial, retry = reservas
            self.assertNotEqual(inicial["json"]["id"], retry["json"]["id"])
            self.assertNotIn("inputResponses", inicial["json"]["params"])
            self.assertEqual(inicial["json"]["params"]["arguments"]["sala"], "sala-garagem")
            self.assertEqual(retry["json"]["params"]["arguments"], inicial["json"]["params"]["arguments"])
            resultado_pausa = (inicial.get("response_json") or {}).get("result") or {}
            chave = next(iter(resultado_pausa["inputRequests"]))
            token = resultado_pausa["requestState"]
            self.assertEqual(retry["json"]["params"]["requestState"], token)
            self.assertEqual(retry["json"]["params"]["inputResponses"][chave]["action"], "accept")
            self.assertEqual(retry["json"]["params"]["inputResponses"][chave]["content"]["sala"], "sala-fusca")
            for chamada in (inicial, retry):
                meta = chamada["json"]["params"]["_meta"]
                self.assertEqual(meta["io.modelcontextprotocol/protocolVersion"], "2026-07-28")
                self.assertIn("form", meta["io.modelcontextprotocol/clientCapabilities"]["elicitation"])
                self.assertEqual(trace_id_de(chamada), trace_id)
                headers = chamada["headers_lower"]
                self.assertEqual(headers.get("mcp-protocol-version"), "2026-07-28")
                self.assertEqual(headers.get("mcp-method"), "tools/call")
                self.assertEqual(headers.get("mcp-name"), "reservar_sala")
            stderr = stack.mcp.read_stderr()
            self.assertIn("method=tools/list", stderr)
            self.assertIn("method=tools/call", stderr)
            self.assertIn(trace_id, stderr)
            corpos = bruto_consulta + bruto + bruto_final + json.dumps(stack.agente.get_card()[1])
            assert_sem_segredo(self, corpos, [token])

    def test_escolha_invalida_repete_texto_e_depois_aceita(self) -> None:
        with PonteStack() as stack:
            pausada = self._pausar_garagem(stack, trace_id=None)
            antes = len(chamadas(stack.observador, "tools/call"))
            _status, invalida, bruto = stack.agente.send_message(
                "escolha=sala-aquario",
                task_id=pausada["id"],
                req_id="invalida",
            )
            self.assertNotIn("error", invalida, bruto)
            tarefa = task_de(invalida)
            self.assertEqual(tarefa["status"]["state"], "TASK_STATE_INPUT_REQUIRED")
            self.assertEqual(texto_status(tarefa), PAUSE_GARAGEM)
            self.assertEqual(len(chamadas(stack.observador, "tools/call")), antes)
            self.assertTrue(sala_esta_livre(stack.mcp, "sala-fusca", instante("14:00"), instante("15:00")))

            _status, valida, _bruto = stack.agente.send_message(
                "escolha=sala-fusca",
                task_id=pausada["id"],
                req_id="valida",
            )
            self.assertEqual(task_de(valida)["status"]["state"], "TASK_STATE_COMPLETED")
            self.assertEqual(artefato_reserva(task_de(valida))["sala"], "sala-fusca")
            self.assertEqual(len(chamadas(stack.observador, "tools/call")), antes + 1)

    def test_recusa_consome_mcp_e_nao_reserva(self) -> None:
        with PonteStack() as stack:
            pausada = self._pausar_garagem(stack, trace_id=novo_trace_id())
            _status, resposta, bruto = stack.agente.send_message(
                "escolha=recusar",
                task_id=pausada["id"],
                req_id="recusa",
            )
            self.assertNotIn("error", resposta, bruto)
            tarefa = task_de(resposta)
            self.assertEqual(tarefa["status"]["state"], "TASK_STATE_CANCELED")
            self.assertFalse(tarefa.get("artifacts"))
            self.assertTrue(sala_esta_livre(stack.mcp, "sala-fusca", instante("14:00"), instante("15:00")))
            self.assertTrue(sala_esta_livre(stack.mcp, "sala-mirante", instante("14:00"), instante("15:00")))
            reservas = chamadas(stack.observador, "tools/call")
            retry = reservas[-1]
            resultado = (reservas[0].get("response_json") or {}).get("result") or {}
            chave = next(iter(resultado["inputRequests"]))
            resposta_mcp = retry["json"]["params"]["inputResponses"][chave]
            self.assertEqual(resposta_mcp["action"], "decline")
            self.assertNotIn("content", resposta_mcp)
            self.assertEqual(retry["json"]["params"]["requestState"], resultado["requestState"])
            self.assertEqual(retry["json"]["params"]["arguments"]["sala"], "sala-garagem")
            self.assertNotEqual(reservas[0]["json"]["id"], retry["json"]["id"])
            _status, consulta, bruto_consulta = stack.agente.get_task(pausada["id"], req_id="get-cancel")
            self.assertEqual(task_de(consulta)["status"]["state"], "TASK_STATE_CANCELED")
            assert_sem_segredo(self, bruto + bruto_consulta, [resultado["requestState"]])

    def test_terminais_rejeitam_nova_mensagem_sem_tools_call(self) -> None:
        with PonteStack() as stack:
            _status, livre, _bruto = stack.agente.send_message(
                comando_reserva("sala-porao", instante("09:00"), instante("10:00"), "Doc"),
                req_id="livre",
            )
            completa = task_de(livre)
            self.assertEqual(completa["status"]["state"], "TASK_STATE_COMPLETED")

            _status, inexistente, _bruto = stack.agente.send_message(
                comando_reserva("sala-delorean", instante("09:00"), instante("10:00"), "Doc"),
                req_id="delorean",
            )
            falha = task_de(inexistente)
            self.assertEqual(falha["status"]["state"], "TASK_STATE_FAILED")
            self.assertTrue(texto_status(falha).endswith("Sala inexistente: sala-delorean"))

            pausada = self._pausar_garagem(stack, trace_id=None)
            _status, recusa, _bruto = stack.agente.send_message(
                "escolha=recusar",
                task_id=pausada["id"],
                req_id="recusa-terminal",
            )
            cancelada = task_de(recusa)
            self.assertEqual(cancelada["status"]["state"], "TASK_STATE_CANCELED")

            for tarefa, estado in (
                (completa, "TASK_STATE_COMPLETED"),
                (cancelada, "TASK_STATE_CANCELED"),
                (falha, "TASK_STATE_FAILED"),
            ):
                antes = len(chamadas(stack.observador, "tools/call"))
                _status, antes_get, _bruto = stack.agente.get_task(tarefa["id"], req_id=f"antes-{estado}")
                _status, rejeitada, bruto = stack.agente.send_message(
                    "escolha=sala-fusca",
                    task_id=tarefa["id"],
                    req_id=f"terminal-{estado}",
                )
                self.assertIn("error", rejeitada, bruto)
                self.assertEqual(len(chamadas(stack.observador, "tools/call")), antes)
                _status, depois, _bruto = stack.agente.get_task(tarefa["id"], req_id=f"depois-{estado}")
                self.assertEqual(task_de(depois)["status"]["state"], estado)
                self.assertEqual(task_de(depois).get("history"), task_de(antes_get).get("history"))
                self.assertEqual(task_de(depois).get("artifacts"), task_de(antes_get).get("artifacts"))

    def test_sem_alternativas_termina_failed(self) -> None:
        with PonteStack() as stack:
            for sala in ("sala-fusca", "sala-mirante"):
                _status, resposta, bruto = stack.agente.send_message(
                    comando_reserva(sala, instante("14:00"), instante("15:00"), "Doc"),
                    req_id=f"ocupa-{sala}",
                )
                self.assertEqual(task_de(resposta)["status"]["state"], "TASK_STATE_COMPLETED", bruto)
            _status, resposta, bruto = stack.agente.send_message(
                comando_reserva("sala-garagem", instante("14:00"), instante("15:00"), "Biff"),
                req_id="sem-alt",
            )
            tarefa = task_de(resposta)
            self.assertEqual(tarefa["status"]["state"], "TASK_STATE_FAILED", bruto)
            self.assertTrue(texto_status(tarefa).endswith("Sem alternativas disponiveis no intervalo"))
            self.assertFalse(tarefa.get("artifacts"))
            self.assertNotIn("alternativas:", texto_status(tarefa))

    def test_duas_tasks_em_ordem_inversa_preservam_trace_e_token(self) -> None:
        trace_a = novo_trace_id()
        trace_b = novo_trace_id()
        trace_alheio = novo_trace_id()
        with PonteStack() as stack:
            _status, resp_a, bruto_a = stack.agente.send_message(
                comando_reserva("sala-fusca", instante("16:00"), instante("17:00"), "Jennifer"),
                traceparent=traceparent(trace_a),
                req_id="task-a",
            )
            tarefa_a = task_de(resp_a)
            _status, resp_b, bruto_b = stack.agente.send_message(
                comando_reserva("sala-garagem", instante("14:00"), instante("15:00"), "Marty"),
                traceparent=traceparent(trace_b),
                req_id="task-b",
            )
            tarefa_b = task_de(resp_b)
            self.assertEqual(tarefa_a["status"]["state"], "TASK_STATE_INPUT_REQUIRED", bruto_a)
            self.assertEqual(tarefa_b["status"]["state"], "TASK_STATE_INPUT_REQUIRED", bruto_b)
            self.assertIn("sala-mirante", texto_status(tarefa_a))
            self.assertEqual(texto_status(tarefa_b), PAUSE_GARAGEM)

            _status, sem_trace, _bruto = stack.agente.send_message(
                comando_reserva("sala-fusca", instante("16:00"), instante("17:00"), "Doc"),
                req_id="sem-trace",
            )
            tarefa_sem = task_de(sem_trace)
            self.assertEqual(tarefa_sem["status"]["state"], "TASK_STATE_INPUT_REQUIRED")
            self.assertNotEqual(tarefa_sem["id"], tarefa_a["id"])

            _status, resp_b2, bruto_b2 = stack.agente.send_message(
                "escolha=sala-mirante",
                task_id=tarefa_b["id"],
                traceparent=traceparent(trace_alheio),
                req_id="retoma-b",
            )
            _status, resp_a2, bruto_a2 = stack.agente.send_message(
                "escolha=sala-mirante",
                task_id=tarefa_a["id"],
                req_id="retoma-a",
            )
            final_a = task_de(resp_a2)
            final_b = task_de(resp_b2)
            self.assertEqual(final_a["status"]["state"], "TASK_STATE_COMPLETED", bruto_a2)
            self.assertEqual(final_b["status"]["state"], "TASK_STATE_COMPLETED", bruto_b2)
            corpo_a = artefato_reserva(final_a)
            corpo_b = artefato_reserva(final_b)
            self.assertEqual(corpo_a["sala"], "sala-mirante")
            self.assertEqual(corpo_a["inicio"], instante("16:00"))
            self.assertEqual(corpo_a["responsavel"], "Jennifer")
            self.assertEqual(corpo_b["sala"], "sala-mirante")
            self.assertEqual(corpo_b["inicio"], instante("14:00"))
            self.assertEqual(corpo_b["responsavel"], "Marty")
            self.assertNotEqual(corpo_a["reserva"], corpo_b["reserva"])
            self.assertEqual(final_a["id"], tarefa_a["id"])
            self.assertEqual(final_b["id"], tarefa_b["id"])

            reservas = chamadas(stack.observador, "tools/call")
            iniciais = [item for item in reservas if "inputResponses" not in (item["json"].get("params") or {})]
            retries = [item for item in reservas if "inputResponses" in (item["json"].get("params") or {})]

            def por_pessoa(inicio: str, responsavel: str) -> dict[str, Any]:
                return next(
                    item
                    for item in iniciais
                    if item["json"]["params"]["arguments"]["inicio"] == inicio
                    and item["json"]["params"]["arguments"]["responsavel"] == responsavel
                )

            inicial_a = por_pessoa(instante("16:00"), "Jennifer")
            inicial_b = por_pessoa(instante("14:00"), "Marty")
            token_a = inicial_a["response_json"]["result"]["requestState"]
            token_b = inicial_b["response_json"]["result"]["requestState"]
            self.assertNotEqual(token_a, token_b)
            for retry in retries:
                inicio = retry["json"]["params"]["arguments"]["inicio"]
                if inicio == instante("16:00") and retry["json"]["params"]["arguments"]["responsavel"] == "Jennifer":
                    self.assertEqual(retry["json"]["params"]["requestState"], token_a)
                    self.assertEqual(trace_id_de(retry), trace_a)
                    self.assertNotEqual(retry["json"]["id"], inicial_a["json"]["id"])
                if inicio == instante("14:00"):
                    self.assertEqual(retry["json"]["params"]["requestState"], token_b)
                    self.assertEqual(trace_id_de(retry), trace_b)
                    self.assertNotIn(trace_alheio, json.dumps(retry["json"]["params"]["_meta"]))
            sem_trace_calls = [
                item
                for item in iniciais
                if item["json"]["params"]["arguments"]["responsavel"] == "Doc"
            ]
            self.assertEqual(len(sem_trace_calls), 1)
            self.assertIsNone(trace_id_de(sem_trace_calls[0]))
            self.assertNotIn(trace_a, json.dumps(sem_trace_calls[0]["json"]))
            self.assertNotIn(trace_b, json.dumps(sem_trace_calls[0]["json"]))
            publico = bruto_a + bruto_b + bruto_a2 + bruto_b2
            assert_sem_segredo(self, publico, [token_a, token_b])

    def test_dois_pedidos_iguais_pausam_com_o_mesmo_texto(self) -> None:
        trace_id = novo_trace_id()
        with PonteStack() as stack:
            _status, primeira, _bruto = stack.agente.send_message(
                comando_reserva("sala-garagem", instante("14:00"), instante("15:00"), "Marty"),
                traceparent=traceparent(trace_id),
                req_id="igual-1",
            )
            _status, segunda, _bruto = stack.agente.send_message(
                comando_reserva("sala-garagem", instante("14:00"), instante("15:00"), "Marty"),
                req_id="igual-2",
            )
            tarefa_1 = task_de(primeira)
            tarefa_2 = task_de(segunda)
            self.assertEqual(texto_status(tarefa_1), texto_status(tarefa_2))
            self.assertEqual(texto_status(tarefa_1), PAUSE_GARAGEM)
            self.assertNotEqual(tarefa_1["id"], tarefa_2["id"])
            self.assertNotEqual(tarefa_1["contextId"], tarefa_2["contextId"])
            reservas = chamadas(stack.observador, "tools/call")
            self.assertEqual(
                [item for item in reservas if "inputResponses" in (item["json"].get("params") or {})],
                [],
            )
            sem_trace = [item for item in reservas if trace_id_de(item) is None]
            com_trace = [item for item in reservas if trace_id_de(item) == trace_id]
            self.assertEqual(len(sem_trace), 1)
            self.assertEqual(len(com_trace), 1)
            self.assertNotIn(trace_id, json.dumps(sem_trace[0]["json"]))

    def test_restart_mcp_direto_sem_proxy_preserva_retomada_e_id(self) -> None:
        import re

        mcp = MCPServerSubprocess()
        agente: AgenteServerSubprocess | None = None
        try:
            mcp.start()
            agente = AgenteServerSubprocess(mcp_url=mcp.url)
            agente.start()
            trace_id = novo_trace_id()
            _status, resposta, bruto = agente.send_message(
                comando_reserva("sala-garagem", instante("14:00"), instante("15:00"), "Marty"),
                traceparent=traceparent(trace_id), req_id="direto-pausa",
            )
            pausada = task_de(resposta)
            self.assertEqual(pausada["status"]["state"], "TASK_STATE_INPUT_REQUIRED", bruto)
            antes = mcp.read_stderr()
            id_inicial = re.search(r"method=tools/call id=(\S+)", antes)
            assert id_inicial is not None
            mcp.stop()
            mcp.start()
            _status, resposta, bruto = agente.send_message(
                "escolha=sala-fusca", task_id=pausada["id"], req_id="direto-retry",
            )
            self.assertEqual(task_de(resposta)["status"]["state"], "TASK_STATE_COMPLETED", bruto)
            self.assertEqual(artefato_reserva(task_de(resposta))["sala"], "sala-fusca")
            depois = mcp.read_stderr()
            id_retry = re.search(r"method=tools/call id=(\S+)", depois)
            assert id_retry is not None
            self.assertNotEqual(id_inicial.group(1), id_retry.group(1))
            self.assertIn(trace_id, depois)
            self.assertNotIn("requestState", bruto)
        finally:
            if agente is not None:
                agente.stop()
            mcp.stop()

    def test_restart_do_mcp_preserva_retomada(self) -> None:
        trace_id = novo_trace_id()
        with PonteStack() as stack:
            pid_agente = stack.agente.proc.pid if stack.agente.proc else None
            pausada = self._pausar_garagem(stack, trace_id=trace_id)
            stack.mcp.stop()
            stack.mcp.start()
            self.assertEqual(stack.agente.proc.pid if stack.agente.proc else None, pid_agente)
            _status, resposta, bruto = stack.agente.send_message(
                "escolha=sala-fusca",
                task_id=pausada["id"],
                req_id="depois-restart",
            )
            self.assertNotIn("error", resposta, bruto)
            tarefa = task_de(resposta)
            self.assertEqual(tarefa["id"], pausada["id"])
            self.assertEqual(tarefa["status"]["state"], "TASK_STATE_COMPLETED")
            self.assertEqual(artefato_reserva(tarefa)["sala"], "sala-fusca")
            self.assertFalse(sala_esta_livre(stack.mcp, "sala-fusca", instante("14:00"), instante("15:00")))
            reservas = chamadas(stack.observador, "tools/call")
            inicial = next(item for item in reservas if "inputResponses" not in item["json"]["params"])
            retries = [item for item in reservas if "inputResponses" in item["json"]["params"]]
            self.assertGreaterEqual(len(retries), 1)
            token = inicial["response_json"]["result"]["requestState"]
            self.assertEqual(retries[-1]["json"]["params"]["requestState"], token)
            self.assertEqual(retries[-1]["json"]["params"]["arguments"]["sala"], "sala-garagem")
            self.assertNotEqual(inicial["json"]["id"], retries[-1]["json"]["id"])
            self.assertEqual(trace_id_de(retries[-1]), trace_id)
            assert_sem_segredo(self, bruto, [token])
            self.assertNotIn(token, stack.mcp.read_stderr())


class TestEscolhaInvalidaNaoChamaHost(unittest.IsolatedAsyncioTestCase):
    async def test_escolha_fora_da_lista_preserva_pending(self) -> None:
        store = TaskStore()
        host = ScriptedHost(
            [formulario(key="k-inv", token=SENTINEL, enum=["sala-fusca", "sala-mirante"])],
            store,
        )
        handler = AgenteRequestHandler(mcp_host=host, task_store=store)  # type: ignore[arg-type]
        texto = comando_reserva("sala-garagem", instante("14:00"), instante("15:00"), "Marty")
        pausada = await handler.on_message_send(mensagem_reserva(texto), ServerCallContext())
        assert isinstance(pausada, a2a_pb2.Task)
        repetida = await handler.on_message_send(
            mensagem_reserva("escolha=sala-aquario", task_id=pausada.id),
            ServerCallContext(),
        )
        assert isinstance(repetida, a2a_pb2.Task)
        self.assertEqual(repetida.status.state, a2a_pb2.TASK_STATE_INPUT_REQUIRED)
        self.assertEqual(repetida.status.message.parts[0].text, pausada.status.message.parts[0].text)
        self.assertEqual(len(host.calls), 1)
        registro = store.get_record(pausada.id)
        assert registro is not None and registro.pending is not None
        self.assertEqual(registro.pending.request_state, SENTINEL)
        self.assertEqual(registro.pending.pause_text, repetida.status.message.parts[0].text)
