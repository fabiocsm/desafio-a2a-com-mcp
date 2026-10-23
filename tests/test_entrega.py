"""Contratos de empacotamento, constraints e suporte HTTP da entrega.

Os testes de CLI e HTTP usam unittest.mock. Eles não substituem as provas
de protocolo executadas contra processos reais.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from email.message import Message
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest import mock

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python >= 3.11 no projeto
    import tomli as tomllib  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verificar_entrega.py"

PINS_COMUNS = {
    "mcp": "2.3.0",
    "starlette": "0.48.0",
    "uvicorn": "0.31.1",
    "sse-starlette": "3.0.3",
    "pydantic": "2.12.0",
}
PIN_A2A = "a2a-sdk[http-server]==1.2.3"
LLM_MARCAS = (
    "openai",
    "anthropic",
    "langchain",
    "litellm",
    "google-generativeai",
    "cohere",
    "mistralai",
    "groq",
)


def _carregar_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _deps(manifesto: dict) -> list[str]:
    return list(manifesto["project"]["dependencies"])


def carregar_verificador():
    """Carrega o script de entrega sem exigir que scripts/ seja um pacote."""
    spec = importlib.util.spec_from_file_location("verificar_entrega", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"script ausente: {SCRIPT}")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class TestManifestosInstalaveis(unittest.TestCase):
    """Pins, Python e entrypoints exigidos para instalação editável."""

    def test_servidor_python_pins_e_build(self) -> None:
        manifesto = _carregar_toml(ROOT / "servidor-mcp" / "pyproject.toml")
        self.assertEqual(manifesto["project"]["requires-python"], ">=3.12")
        deps = _deps(manifesto)
        for nome, versao in PINS_COMUNS.items():
            self.assertIn(f"{nome}=={versao}", deps)
        self.assertNotIn("a2a-sdk", " ".join(deps))
        self.assertEqual(manifesto["build-system"]["requires"], ["hatchling==1.27.0"])
        self.assertEqual(manifesto["build-system"]["build-backend"], "hatchling.build")
        pacotes = manifesto["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
        self.assertIn("src/ponte_mcp", pacotes)
        self.assertTrue((ROOT / "servidor-mcp" / "src" / "ponte_mcp" / "__main__.py").is_file())

    def test_agente_python_pins_sem_llm_e_build(self) -> None:
        manifesto = _carregar_toml(ROOT / "agente" / "pyproject.toml")
        self.assertEqual(manifesto["project"]["requires-python"], ">=3.12")
        deps = _deps(manifesto)
        for nome, versao in PINS_COMUNS.items():
            self.assertIn(f"{nome}=={versao}", deps)
        self.assertIn(PIN_A2A, deps)
        texto = " ".join(deps).lower()
        for marca in LLM_MARCAS:
            self.assertNotIn(marca, texto)
        self.assertEqual(manifesto["build-system"]["requires"], ["hatchling==1.27.0"])
        pacotes = manifesto["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
        self.assertIn("src/ponte_agente", pacotes)
        self.assertTrue((ROOT / "agente" / "src" / "ponte_agente" / "__main__.py").is_file())

    def test_nenhum_manifesto_declara_sdk_de_llm(self) -> None:
        for relativo in ("servidor-mcp/pyproject.toml", "agente/pyproject.toml"):
            bruto = (ROOT / relativo).read_text(encoding="utf-8").lower()
            for marca in LLM_MARCAS:
                self.assertNotIn(marca, bruto, relativo)


class TestConstraintsPortaveis(unittest.TestCase):
    """constraints.txt fixa a resolução sem paths locais nem pacotes editáveis."""

    def test_constraints_sem_editavel_ou_path_local(self) -> None:
        caminho = ROOT / "constraints.txt"
        self.assertTrue(caminho.is_file(), "constraints.txt ainda não foi gerado")
        linhas = []
        for bruta in caminho.read_text(encoding="utf-8").splitlines():
            linha = bruta.strip()
            if not linha or linha.startswith("#"):
                continue
            linhas.append(linha)
            self.assertNotIn("file://", linha.lower())
            self.assertNotIn("\\", linha)
            self.assertNotRegex(linha, r"@[^\s]+")
            self.assertNotIn("-e ", linha)
            self.assertRegex(linha, r"^[A-Za-z0-9_.\-]+==[^\s]+$")
            nome = linha.split("==", 1)[0].lower()
            self.assertNotIn("ponte-mcp", nome)
            self.assertNotIn("ponte-agente", nome)
        texto = "\n".join(linhas)
        for nome, versao in PINS_COMUNS.items():
            self.assertIn(f"{nome}=={versao}", texto)
        self.assertIn("a2a-sdk==1.2.3", texto)
        self.assertNotIn("hatchling==", texto)


class TestPadroesDePortaESegredo(unittest.TestCase):
    """Reaproveita os padrões de porta e segredo inválido das features 001 e 003."""

    def test_portas_e_endpoints_padrao(self) -> None:
        from ponte_agente.app import (
            DEFAULT_A2A_BASE_URL,
            DEFAULT_AGENTE_PORT,
        )
        from ponte_agente.mcp_host import DEFAULT_MCP_URL
        from ponte_mcp.app import DEFAULT_PORT

        self.assertEqual(DEFAULT_PORT, 7301)
        self.assertEqual(DEFAULT_AGENTE_PORT, 7300)
        self.assertEqual(DEFAULT_MCP_URL, "http://127.0.0.1:7301/mcp")
        self.assertEqual(DEFAULT_A2A_BASE_URL, "http://127.0.0.1:7300")

    def test_segredo_ausente_curto_ou_nao_hex_e_rejeitado(self) -> None:
        from ponte_mcp.app import ErroConfiguracaoSegredo, ler_segredo_estado

        for valor in (None, "", "abcd", "zz" * 32, "aa" * 16):
            with self.assertRaises(ErroConfiguracaoSegredo):
                ler_segredo_estado(valor)
        self.assertEqual(len(ler_segredo_estado("ab" * 32)), 32)


class TestSuporteHttpDaEntrega(unittest.TestCase):
    """Suporte do verificador: timeout, JSON-RPC, estado e diagnóstico público."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = carregar_verificador()

    def test_timeout_falha_sem_body(self) -> None:
        with mock.patch.object(self.mod.urllib.request, "urlopen", side_effect=TimeoutError("lento")):
            with self.assertRaises(self.mod.EntregaFalha) as ctx:
                self.mod.post_json("http://127.0.0.1:9/mcp", {"id": 1}, {}, timeout=0.01)
        self.assertIn("timeout", str(ctx.exception).lower())
        self.assertNotIn("requestState", str(ctx.exception))

    def test_httperror_preserva_codigo_esperado(self) -> None:
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32602, "message": "invalido"},
                "requestState": "TOKENSECRETO",
            }
        ).encode("utf-8")

        def levantar(*_args, **_kwargs):
            raise urllib.error.HTTPError(
                "http://127.0.0.1:7301/mcp",
                400,
                "bad",
                Message(),
                io.BytesIO(payload),
            )

        with mock.patch.object(self.mod.urllib.request, "urlopen", side_effect=levantar):
            with self.assertRaises(self.mod.ErroHttpJsonRpc) as ctx:
                self.mod.post_json("http://127.0.0.1:7301/mcp", {"id": 1}, {}, timeout=1)
        self.assertEqual(ctx.exception.code, 400)
        self.assertEqual(ctx.exception.codigo_jsonrpc, -32602)
        diag = self.mod.diagnostico_publico(ctx.exception)
        self.assertIn("400", diag)
        self.assertIn("-32602", diag)
        self.assertNotIn("TOKENSECRETO", diag)
        self.assertNotIn("requestState", diag)
        self.assertNotIn("invalido", diag)

    def test_meta_declara_form_como_objeto(self) -> None:
        meta = self.mod.montar_meta(traceparent="00-" + "ab" * 16 + "-" + "cd" * 8 + "-01")
        caps = meta["io.modelcontextprotocol/clientCapabilities"]
        self.assertIsInstance(caps["elicitation"]["form"], dict)
        self.assertIn("io.modelcontextprotocol/protocolVersion", meta)

    def test_headers_espelham_metodo_e_nome(self) -> None:
        headers = self.mod.montar_headers("tools/call", "reservar_sala")
        self.assertEqual(headers["MCP-Protocol-Version"], "2026-07-28")
        self.assertEqual(headers["Mcp-Method"], "tools/call")
        self.assertEqual(headers["Mcp-Name"], "reservar_sala")
        leitura = self.mod.montar_headers("resources/read", "politica://uso")
        self.assertEqual(leitura["Mcp-Name"], "politica://uso")
        lista = self.mod.montar_headers("tools/list", None)
        self.assertNotIn("Mcp-Name", lista)

    def test_cli_e_urls_invalidas_falham(self) -> None:
        self.assertNotEqual(self.mod.main(["--caso", "inexistente"]), 0)
        self.assertNotEqual(self.mod.main(["--agente", "ftp://localhost", "--caso", "privacidade"]), 0)
        self.assertNotEqual(self.mod.main(["--mcp", "http://localhost:7301", "--caso", "privacidade"]), 0)
        self.assertNotEqual(self.mod.main(["--timeout", "0", "--caso", "privacidade"]), 0)
        self.assertNotEqual(self.mod.main(["--caso", "reinicio-mcp", "--fase", "emitir"]), 0)
        self.assertNotEqual(self.mod.main(["--caso", "rastreamento"]), 0)

    def test_arquivo_temporario_incompleto_e_recusado(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            json.dump({"pedido": {"sala": "sala-garagem"}, "id": "1"}, handle)
            caminho = handle.name
        with self.assertRaises(self.mod.EntregaFalha):
            self.mod.carregar_estado(caminho)

    def test_emitir_nao_imprime_token(self) -> None:
        token = "v1.TOKENOPAQUEDETESTE"
        respostas = [
            (200, {"jsonrpc": "2.0", "id": "l", "result": {"tools": [{"name": "reservar_sala"}, {"name": "consultar_disponibilidade"}]}}, "{}"),
            (
                200,
                {
                    "jsonrpc": "2.0",
                    "id": "c",
                    "result": {
                        "resultType": "input_required",
                        "requestState": token,
                        "inputRequests": {
                            "__main__:escolha_de_sala": {
                                "method": "elicitation/create",
                                "params": {
                                    "mode": "form",
                                    "requestedSchema": {
                                        "type": "object",
                                        "properties": {"sala": {"type": "string", "enum": ["sala-fusca", "sala-mirante"]}},
                                        "required": ["sala"],
                                    },
                                },
                            }
                        },
                    },
                },
                "{}",
            ),
        ]
        cliente = _ClienteFalso(respostas)
        with tempfile.TemporaryDirectory() as pasta:
            destino = str(Path(pasta) / "estado.json")
            buffer = io.StringIO()
            with mock.patch("sys.stdout", buffer):
                self.mod.emitir_reinicio(cliente, "http://127.0.0.1:7301/mcp", destino)
            saida = buffer.getvalue()
            self.assertNotIn(token, saida)
            self.assertNotIn("REQUEST_STATE_SECRET", saida)
            gravado = json.loads(Path(destino).read_text(encoding="utf-8"))
        self.assertEqual(gravado["requestState"], token)
        self.assertEqual(gravado["alternativa"], "sala-fusca")
        self.assertEqual(gravado["chave"], "__main__:escolha_de_sala")
        self.assertNotIn("REQUEST_STATE_SECRET", json.dumps(gravado))
        metodos = [item["body"]["method"] for item in cliente.chamadas]
        self.assertEqual(metodos, ["tools/list", "tools/call"])
        caps = cliente.chamadas[1]["body"]["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"]
        self.assertIsInstance(caps["elicitation"]["form"], dict)

    def test_retomar_nao_imprime_token_e_confirma(self) -> None:
        token = "v1.OUTROTOKENOPAQUE"
        estado = {
            "pedido": {
                "sala": "sala-garagem",
                "inicio": "2026-11-03T14:00:00-03:00",
                "fim": "2026-11-03T15:00:00-03:00",
                "responsavel": "Marty",
            },
            "chave": "__main__:escolha_de_sala",
            "id": "emit-1",
            "instante": "2099-01-01T00:00:00+00:00",
            "alternativa": "sala-fusca",
            "requestState": token,
        }
        respostas = [
            (
                200,
                {
                    "jsonrpc": "2.0",
                    "id": "r",
                    "result": {
                        "resultType": "complete",
                        "isError": False,
                        "structuredContent": {
                            "reservado": True,
                            "sala": "sala-fusca",
                            "reserva": "res-9",
                        },
                    },
                },
                "{}",
            ),
            (
                200,
                {
                    "jsonrpc": "2.0",
                    "id": "d",
                    "result": {"structuredContent": {"livre": False, "sala": "sala-fusca"}},
                },
                "{}",
            ),
        ]
        cliente = _ClienteFalso(respostas)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            json.dump(estado, handle)
            caminho = handle.name
        agora = datetime(2099, 1, 1, 0, 1, tzinfo=timezone.utc)
        buffer = io.StringIO()
        with mock.patch("sys.stdout", buffer), mock.patch.object(self.mod, "agora_utc", return_value=agora):
            self.mod.retomar_reinicio(cliente, "http://127.0.0.1:7301/mcp", caminho)
        saida = buffer.getvalue()
        self.assertNotIn(token, saida)
        self.assertIn("sala-fusca", saida)
        retry = cliente.chamadas[0]["body"]
        self.assertNotEqual(retry["id"], "emit-1")
        self.assertEqual(retry["params"]["requestState"], token)
        self.assertEqual(retry["params"]["arguments"]["sala"], "sala-garagem")
        self.assertEqual(
            retry["params"]["inputResponses"]["__main__:escolha_de_sala"]["content"]["sala"],
            "sala-fusca",
        )

    def test_rastreamento_sem_descoberta_ou_id_igual_e_rejeitado(self) -> None:
        trace = "ab" * 16
        base = f"00-{trace}-{'cd' * 8}-01"
        sem_lista = [
            f"[mcp] method=tools/call id=1 traceparent={base}",
            f"[mcp] method=tools/call id=2 traceparent={base}",
        ]
        with self.assertRaises(self.mod.EntregaFalha):
            self.mod.avaliar_rastreamento(sem_lista, trace)
        mesmo_id = [
            f"[mcp] method=tools/list id=1 traceparent={base}",
            f"[mcp] method=resources/read id=2 traceparent={base}",
            f"[mcp] method=tools/call id=9 traceparent={base}",
            f"[mcp] method=tools/call id=9 traceparent={base}",
        ]
        with self.assertRaises(self.mod.EntregaFalha):
            self.mod.avaliar_rastreamento(mesmo_id, trace)

    def test_rastreamento_valido_exige_lista_antes_da_chamada(self) -> None:
        trace = "11" * 16
        outro = "22" * 16
        linhas = [
            f"[mcp] method=tools/list id=validador traceparent=00-{outro}-{'aa' * 8}-01",
            f"[mcp] method=tools/list id=a1 traceparent=00-{trace}-{'bb' * 8}-01",
            f"[mcp] method=resources/read id=a2 traceparent=00-{trace}-{'bc' * 8}-01",
            f"[mcp] method=tools/call id=a3 traceparent=00-{trace}-{'bd' * 8}-01",
            f"[mcp] method=tools/list id=a4 traceparent=00-{trace}-{'be' * 8}-01",
            f"[mcp] method=tools/call id=a5 traceparent=00-{trace}-{'bf' * 8}-01",
        ]
        resumo = self.mod.avaliar_rastreamento(linhas, trace)
        self.assertEqual(resumo["ids_tools_call"], ["a3", "a5"])
        self.assertTrue(resumo["descoberta_antes"])


class TestProvasA2aDaEntrega(unittest.TestCase):
    """Respostas públicas adversariais não podem aprovar as provas HTTP."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = carregar_verificador()

    def task(self, nome, estado="COMPLETED", sala="sala-fusca", responsavel="Doc", hora=14):
        dados = {
            "reserva": "res-" + nome, "reservado": True, "sala": sala,
            "responsavel": responsavel, "inicio": f"2026-11-03T{hora}:00:00-03:00",
            "fim": f"2026-11-03T{hora + 1}:00:00-03:00", "politica": "2026-11-01",
        }
        task = {"id": nome, "contextId": "ctx-" + nome, "status": {"state": "TASK_STATE_" + estado}}
        if estado == "COMPLETED":
            task["artifacts"] = [{"name": "reserva", "parts": [{"text": json.dumps(dados)}]}]
        elif estado == "INPUT_REQUIRED":
            salas = "sala-garagem, sala-mirante" if nome == "b" else "sala-fusca, sala-mirante"
            task["status"]["message"] = {"parts": [{"text": "alternativas: " + salas}]}
        elif estado == "FAILED":
            task["history"] = [{"parts": [{"text": "Sala inexistente: sala-delorean"}]}]
        return task

    def privacidade(self, mutacao=None):
        completas = {"a": self.task("a"), "b": self.task("b", sala="sala-garagem", responsavel="Biff", hora=16)}
        direta = self.task("direta")
        cancelada = self.task("recusa", "CANCELED")
        falha = self.task("falha", "FAILED")
        consultas = {**completas, "direta": direta, "recusa": cancelada, "falha": falha}
        envios = iter([
            ("pausa-a", self.task("a", "INPUT_REQUIRED")),
            ("invalida", self.task("a", "INPUT_REQUIRED")),
            ("pausa-b", self.task("b", "INPUT_REQUIRED")),
            ("aceite-b", completas["b"]), ("aceite-a", completas["a"]),
            ("direta", direta), ("pre-recusa", self.task("recusa", "INPUT_REQUIRED")),
            ("recusa", cancelada), ("falha", falha),
        ])
        cliente = mock.Mock(timeout=1)

        def post(url, body, headers):
            if body["method"] == "GetTask":
                rotulo = "get-" + body["params"]["id"]
                parsed = {"result": {"task": deepcopy(consultas[body["params"]["id"]])}}
            else:
                try:
                    rotulo, task = next(envios)
                    parsed = {"result": {"task": deepcopy(task)}}
                except StopIteration:
                    rotulo, parsed = "terminal", {"error": {"code": -32602}}
            if mutacao:
                mutacao(rotulo, parsed)
            return 200, parsed, json.dumps(parsed)

        cliente.post.side_effect = post
        with mock.patch.object(self.mod, "_get", return_value=(200, {})), \
             mock.patch.object(self.mod, "versao_politica", return_value="2026-11-01"), \
             mock.patch.object(self.mod, "sala_livre", return_value=True), \
             mock.patch("sys.stdout", io.StringIO()):
            self.mod.executar_privacidade(cliente, "http://agente", "http://mcp/mcp")
        return cliente

    def test_privacidade_legitima_consulta_as_duas_tasks_retomadas(self):
        cliente = self.privacidade()
        ids = [call.args[1]["params"]["id"] for call in cliente.post.call_args_list if call.args[1]["method"] == "GetTask"]
        self.assertIn("a", ids)
        self.assertIn("b", ids)

    def test_privacidade_rejeita_vazamentos_no_envelope_e_texto_json(self):
        for local in ("envelope", "result", "artifact", "erro"):
            with self.subTest(local=local):
                def vazar(rotulo, parsed):
                    if rotulo == "terminal" and local == "erro":
                        parsed["error"]["data"] = {"requestState": "SENTINELA-PRIVADA"}
                    elif rotulo == "aceite-b":
                        if local == "envelope":
                            parsed["requestState"] = "SENTINELA-PRIVADA"
                        elif local == "result":
                            parsed["result"]["requestState"] = "SENTINELA-PRIVADA"
                        elif local == "artifact":
                            part = parsed["result"]["task"]["artifacts"][0]["parts"][0]
                            dados = json.loads(part["text"])
                            dados["requestState"] = "SENTINELA-PRIVADA"
                            part["text"] = json.dumps(dados)
                with self.assertRaisesRegex(self.mod.EntregaFalha, "estrutura privada") as ctx:
                    self.privacidade(vazar)
                self.assertNotIn("SENTINELA-PRIVADA", str(ctx.exception))

    def test_privacidade_http_error_tambem_varre_erro(self):
        for status, vaza in ((400, False), (500, False), (400, True), (500, True)):
            with self.subTest(status=status, vaza=vaza):
                parsed = {"error": {"code": -32602 if status == 400 else -32603}}
                if vaza:
                    parsed["error"]["data"] = {"requestState": "SENTINELA-PRIVADA"}
                cliente = mock.Mock()
                cliente.post.side_effect = self.mod.ErroHttpJsonRpc("http://agente/a2a", status, parsed, json.dumps(parsed))
                if vaza:
                    with self.assertRaisesRegex(self.mod.EntregaFalha, "estrutura privada") as ctx:
                        self.mod.rejeita_terminal(cliente, "http://agente", "a")
                    self.assertNotIn("SENTINELA-PRIVADA", str(ctx.exception))
                else:
                    with self.assertRaises(self.mod.ErroHttpJsonRpc):
                        self.mod.rejeita_terminal(cliente, "http://agente", "a")

    def test_isolamento_rejeita_identidade_contexto_e_fim_trocados(self):
        for local in ("id-duplicado", "id-trocado", "contextId", "fim", "get-id", "get-contextId", "get-fim"):
            with self.subTest(local=local):
                def trocar(rotulo, parsed):
                    if rotulo == ("get-b" if local.startswith("get-") else "aceite-b"):
                        task = parsed["result"]["task"]
                        campo = local.removeprefix("get-")
                        if campo in ("id", "id-duplicado", "id-trocado"):
                            task["id"] = "a"
                        elif campo == "contextId":
                            task["contextId"] = "ctx-a"
                        else:
                            part = task["artifacts"][0]["parts"][0]
                            dados = json.loads(part["text"])
                            dados["fim"] = "2026-11-03T18:00:00-03:00"
                            part["text"] = json.dumps(dados)
                    elif local == "id-trocado" and rotulo == "aceite-a":
                        parsed["result"]["task"]["id"] = "b"
                with self.assertRaises(self.mod.EntregaFalha):
                    self.privacidade(trocar)

    def test_rastreamento_rejeita_request_extra_sem_trace_ou_divergente(self):
        trace = "ab" * 16
        base = f"00-{trace}-{'cd' * 8}-01"
        validas = [f"[mcp] method={method} id=ponte-{i} traceparent={base}" for i, method in enumerate(("tools/list", "resources/read", "tools/call", "tools/call"))]
        for sufixo in ("", f" traceparent=00-{'ef' * 16}-{'cd' * 8}-01"):
            with self.subTest(sufixo=sufixo):
                with self.assertRaises(self.mod.EntregaFalha):
                    self.mod.avaliar_rastreamento(validas[:3] + ["[mcp] method=tools/list id=ponte-extra" + sufixo] + validas[3:], trace)

    def test_rastreamento_exige_retomada_completa_e_identidade_reserva(self):
        trace = "ab" * 16
        base = f"00-{trace}-{'cd' * 8}-01"
        linhas = "\n".join(f"[mcp] method={method} id=ponte-{i} traceparent={base}" for i, method in enumerate(("tools/list", "resources/read", "tools/call", "tools/call")))
        for defeito in (None, "estado", "id", "contextId", "sala", "fim", "responsavel"):
            with self.subTest(defeito=defeito):
                pausa = self.task("trace", "INPUT_REQUIRED")
                retomada = self.task("trace", responsavel="Trace")
                if defeito == "estado":
                    retomada["status"]["state"] = "TASK_STATE_FAILED"
                elif defeito in ("id", "contextId"):
                    retomada[defeito] = "outra"
                elif defeito:
                    part = retomada["artifacts"][0]["parts"][0]
                    dados = json.loads(part["text"])
                    dados[defeito] = "outro"
                    part["text"] = json.dumps(dados)
                cliente = _ClienteFalso([(200, {"result": {"task": task}}, "{}") for task in (pausa, retomada)])
                arquivo = mock.mock_open()
                arquivo.return_value.read.side_effect = ["", linhas]
                with mock.patch("builtins.open", arquivo), mock.patch.object(self.mod, "_traceparent_exclusivo", return_value=(trace, base)), mock.patch("sys.stdout", io.StringIO()):
                    if defeito:
                        with self.assertRaises(self.mod.EntregaFalha):
                            self.mod.executar_rastreamento(cliente, "http://agente", "log")
                    else:
                        self.mod.executar_rastreamento(cliente, "http://agente", "log")


class _ClienteFalso:
    """Cliente HTTP de teste que devolve respostas na ordem programada."""

    def __init__(self, respostas: list[tuple[int, dict, str]]) -> None:
        self._respostas = list(respostas)
        self.chamadas: list[dict] = []

    def post(self, url: str, body: dict, headers: dict, timeout: float | None = None):
        self.chamadas.append({"url": url, "body": body, "headers": headers, "timeout": timeout})
        if not self._respostas:
            raise AssertionError("resposta falsa esgotada")
        return self._respostas.pop(0)


if __name__ == "__main__":
    unittest.main()
