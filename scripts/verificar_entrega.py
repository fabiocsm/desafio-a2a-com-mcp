"""Provas HTTP adicionais da entrega. Não importa tools nem encerra processos.

O operador sobe e reinicia MCP e agente. Este script só fala HTTP e lê o log
indicado. O token de continuação é gravado no arquivo externo e não é impresso.
O segredo permanece no ambiente do servidor, não nesse arquivo.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import re
import secrets
import sys
import urllib.error
import urllib.request
from typing import Any

PROTOCOL_VERSION = "2026-07-28"
AGENTE_PADRAO = "http://localhost:7300"
MCP_PADRAO = "http://localhost:7301/mcp"
TIMEOUT_PADRAO = 20.0
LIMITE_RETOMADA = timedelta(seconds=600)
PEDIDO_CONFLITO = {
    "sala": "sala-garagem",
    "inicio": "2026-11-03T14:00:00-03:00",
    "fim": "2026-11-03T15:00:00-03:00",
    "responsavel": "Marty",
}
CHAVES_PRIVADAS = {
    "requestState",
    "request_state",
    "inputResponses",
    "inputRequests",
    "elicitation",
    "elicitationKey",
    "elicitation_key",
    "requestedSchema",
}
CAMPOS_ESTADO = ("pedido", "chave", "id", "instante", "alternativa", "requestState")
CAMPOS_PEDIDO = ("sala", "inicio", "fim", "responsavel")
_LOG_RE = re.compile(
    r"\[mcp\] method=(?P<method>\S+) id=(?P<id>\S+)(?: traceparent=(?P<traceparent>\S+))?"
)


class EntregaFalha(Exception):
    """Falha de verificação que pode ser relatada sem corpo privado."""


class ErroHttpJsonRpc(urllib.error.HTTPError):
    """HTTPError com o código JSON-RPC inspecionável e o corpo fora do diagnóstico."""

    def __init__(self, url: str, status: int, parsed: dict[str, Any], raw: str) -> None:
        super().__init__(url, status, "erro json-rpc", hdrs=None, fp=None)
        self.parsed = parsed
        self.raw_body = raw
        erro = parsed.get("error") if isinstance(parsed, dict) else None
        self.codigo_jsonrpc = erro.get("code") if isinstance(erro, dict) else None


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def diagnostico_publico(erro: ErroHttpJsonRpc) -> str:
    """Status e código JSON-RPC, sem body, token ou mensagem do servidor."""
    return f"http={erro.code} jsonrpc={erro.codigo_jsonrpc}"


def montar_meta(*, traceparent: str | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientInfo": {
            "name": "verificador-entrega",
            "version": "1.0.0",
        },
        "io.modelcontextprotocol/clientCapabilities": {"elicitation": {"form": {}}},
    }
    if traceparent:
        meta["traceparent"] = traceparent
    return meta


def montar_headers(method: str, name: str | None) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
        "Mcp-Method": method,
    }
    if name is not None:
        headers["Mcp-Name"] = name
    return headers


def post_json(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> tuple[int, dict[str, Any], str]:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            status = int(resp.status)
    except ErroHttpJsonRpc:
        raise
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        try:
            parsed: dict[str, Any] = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {}
        raise ErroHttpJsonRpc(url, int(err.code), parsed, raw) from None
    except (TimeoutError, urllib.error.URLError) as err:
        motivo = getattr(err, "reason", err)
        if isinstance(err, TimeoutError) or isinstance(motivo, (TimeoutError, OSError)):
            if isinstance(err, TimeoutError) or "timed out" in str(motivo).lower() or isinstance(motivo, TimeoutError):
                raise EntregaFalha("timeout de rede") from None
        if isinstance(err, TimeoutError):
            raise EntregaFalha("timeout de rede") from None
        raise EntregaFalha("falha de rede") from None
    try:
        parsed_ok = json.loads(raw) if raw else {}
    except json.JSONDecodeError as err:
        raise EntregaFalha("resposta HTTP sem JSON") from err
    if not isinstance(parsed_ok, dict):
        raise EntregaFalha("resposta HTTP sem objeto JSON")
    return status, parsed_ok, raw


class ClienteHttp:
    """POST JSON com timeout. Não registra corpos."""

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    def post(
        self,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
        timeout: float | None = None,
    ) -> tuple[int, dict[str, Any], str]:
        return post_json(url, body, headers, timeout if timeout is not None else self.timeout)


def _novo_id(prefixo: str) -> str:
    return f"{prefixo}-{secrets.token_hex(4)}"


def _exigir_resultado(parsed: dict[str, Any]) -> dict[str, Any]:
    if "error" in parsed:
        codigo = (parsed.get("error") or {}).get("code")
        raise EntregaFalha(f"jsonrpc={codigo}")
    result = parsed.get("result")
    if not isinstance(result, dict):
        raise EntregaFalha("resposta sem result")
    return result


def chamar_mcp(
    cliente: Any,
    mcp_url: str,
    method: str,
    params: dict[str, Any],
    *,
    name: str | None,
    req_id: str,
    traceparent: str | None = None,
) -> dict[str, Any]:
    corpo = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": {**params, "_meta": montar_meta(traceparent=traceparent)},
    }
    status, parsed, _raw = cliente.post(mcp_url, corpo, montar_headers(method, name))
    if status >= 400:
        raise EntregaFalha(f"http={status}")
    return _exigir_resultado(parsed)


def descobrir_tools(cliente: Any, mcp_url: str) -> list[str]:
    result = chamar_mcp(cliente, mcp_url, "tools/list", {}, name=None, req_id=_novo_id("list"))
    tools = result.get("tools") or []
    nomes = [item.get("name") for item in tools if isinstance(item, dict)]
    if "reservar_sala" not in nomes or "consultar_disponibilidade" not in nomes:
        raise EntregaFalha("catalogo MCP sem as tools de reserva")
    return [nome for nome in nomes if isinstance(nome, str)]


def versao_politica(cliente: Any, mcp_url: str) -> str:
    result = chamar_mcp(
        cliente,
        mcp_url,
        "resources/read",
        {"uri": "politica://uso"},
        name="politica://uso",
        req_id=_novo_id("pol"),
    )
    contents = result.get("contents") or []
    if not contents or not isinstance(contents[0], dict):
        raise EntregaFalha("resource de politica vazio")
    texto = str(contents[0].get("text") or "")
    primeira = texto.splitlines()[0].strip() if texto else ""
    if not primeira.lower().startswith("versao:"):
        raise EntregaFalha("primeira linha da politica sem versao")
    return primeira.split(":", 1)[1].strip()


def _alternativas(result: dict[str, Any]) -> tuple[str, list[str], str]:
    if result.get("resultType") != "input_required":
        raise EntregaFalha("conflito inicial nao pausou")
    pedidos = result.get("inputRequests")
    if not isinstance(pedidos, dict) or len(pedidos) != 1:
        raise EntregaFalha("elicitation ausente")
    chave, pergunta = next(iter(pedidos.items()))
    params = (pergunta or {}).get("params") if isinstance(pergunta, dict) else None
    schema = (params or {}).get("requestedSchema") if isinstance(params, dict) else None
    sala = ((schema or {}).get("properties") or {}).get("sala") if isinstance(schema, dict) else None
    enum = sala.get("enum") if isinstance(sala, dict) else None
    if not isinstance(enum, list) or not enum:
        raise EntregaFalha("schema sem alternativas")
    token = result.get("requestState")
    if not isinstance(token, str) or not token:
        raise EntregaFalha("estado de continuacao ausente")
    return str(chave), [str(item) for item in enum], token


def emitir_reinicio(cliente: Any, mcp_url: str, caminho: str) -> None:
    descobrir_tools(cliente, mcp_url)
    req_id = _novo_id("emit")
    result = chamar_mcp(
        cliente,
        mcp_url,
        "tools/call",
        {"name": "reservar_sala", "arguments": dict(PEDIDO_CONFLITO)},
        name="reservar_sala",
        req_id=req_id,
    )
    chave, alternativas, token = _alternativas(result)
    instante = agora_utc().isoformat()
    estado = {
        "pedido": dict(PEDIDO_CONFLITO),
        "chave": chave,
        "id": req_id,
        "instante": instante,
        "alternativa": alternativas[0],
        "requestState": token,
    }
    publico = {chave_estado: valor for chave_estado, valor in estado.items() if chave_estado != "requestState"}
    if "REQUEST_STATE_SECRET" in json.dumps(publico):
        raise EntregaFalha("estado tentou gravar segredo")
    with open(caminho, "w", encoding="utf-8") as handle:
        json.dump(estado, handle)
        handle.write("\n")
    print(
        f"emitido alternativa={alternativas[0]} chave={chave} instante={instante}",
        flush=True,
    )


def carregar_estado(caminho: str) -> dict[str, Any]:
    try:
        with open(caminho, encoding="utf-8") as handle:
            dados = json.load(handle)
    except (OSError, json.JSONDecodeError) as err:
        raise EntregaFalha("arquivo de estado incompleto ou ilegivel") from err
    if not isinstance(dados, dict):
        raise EntregaFalha("arquivo de estado incompleto")
    for campo in CAMPOS_ESTADO:
        if campo not in dados or dados[campo] in (None, ""):
            raise EntregaFalha("arquivo de estado incompleto")
    pedido = dados["pedido"]
    if not isinstance(pedido, dict) or any(not pedido.get(campo) for campo in CAMPOS_PEDIDO):
        raise EntregaFalha("arquivo de estado incompleto")
    if not isinstance(dados["requestState"], str):
        raise EntregaFalha("arquivo de estado incompleto")
    return dados


def retomar_reinicio(cliente: Any, mcp_url: str, caminho: str) -> None:
    estado = carregar_estado(caminho)
    emitido = datetime.fromisoformat(estado["instante"])
    if emitido.tzinfo is None:
        emitido = emitido.replace(tzinfo=timezone.utc)
    if agora_utc() - emitido >= LIMITE_RETOMADA:
        raise EntregaFalha("retomada fora da janela de 600s")
    novo = _novo_id("retry")
    if novo == estado["id"]:
        novo = _novo_id("retry")
    result = chamar_mcp(
        cliente,
        mcp_url,
        "tools/call",
        {
            "name": "reservar_sala",
            "arguments": dict(estado["pedido"]),
            "inputResponses": {
                estado["chave"]: {"action": "accept", "content": {"sala": estado["alternativa"]}}
            },
            "requestState": estado["requestState"],
        },
        name="reservar_sala",
        req_id=novo,
    )
    if result.get("isError") is True or result.get("resultType") not in (None, "complete"):
        raise EntregaFalha("retomada nao concluiu")
    conteudo = result.get("structuredContent") or {}
    if conteudo.get("reservado") is not True or conteudo.get("sala") != estado["alternativa"]:
        raise EntregaFalha("retomada nao confirmou a alternativa")
    consulta = chamar_mcp(
        cliente,
        mcp_url,
        "tools/call",
        {
            "name": "consultar_disponibilidade",
            "arguments": {
                "sala": estado["alternativa"],
                "inicio": estado["pedido"]["inicio"],
                "fim": estado["pedido"]["fim"],
            },
        },
        name="consultar_disponibilidade",
        req_id=_novo_id("disp"),
    )
    livre = (consulta.get("structuredContent") or {}).get("livre")
    if livre is not False:
        raise EntregaFalha("consulta posterior nao viu a reserva")
    print(
        f"retomada confirmada sala={estado['alternativa']} id_novo={novo} id_original={estado['id']}",
        flush=True,
    )


def avaliar_rastreamento(linhas: list[str], trace_id: str) -> dict[str, Any]:
    eventos: list[dict[str, str]] = []
    for linha in linhas:
        match = _LOG_RE.search(linha)
        if match is None:
            continue
        traceparent = match.group("traceparent") or ""
        partes = traceparent.split("-")
        trace_esperado = len(partes) == 4 and partes[1].lower() == trace_id.lower()
        # O log é exclusivo deste cenário; ponte-* identifica também requests
        # do agente que perderam o trace e não podem desaparecer do gate.
        if not match.group("id").startswith("ponte-") and not trace_esperado:
            continue
        if not trace_esperado:
            raise EntregaFalha("request do agente sem o trace-id A2A esperado")
        eventos.append(
            {
                "method": match.group("method"),
                "id": match.group("id"),
                "traceparent": traceparent,
            }
        )
    if not eventos:
        raise EntregaFalha("nenhum request do trace-id no log")
    primeira_call = next((i for i, ev in enumerate(eventos) if ev["method"] == "tools/call"), None)
    if primeira_call is None:
        raise EntregaFalha("tools/call ausente no trace")
    anteriores = eventos[:primeira_call]
    if not any(ev["method"] == "tools/list" for ev in anteriores):
        raise EntregaFalha("tools/list ausente antes da primeira tools/call")
    if not any(ev["method"] == "resources/read" for ev in anteriores):
        raise EntregaFalha("resources/read ausente antes da primeira tools/call")
    ids_call = [ev["id"] for ev in eventos if ev["method"] == "tools/call"]
    if len(ids_call) < 2 or ids_call[0] == ids_call[1]:
        raise EntregaFalha("ids da chamada e do retry nao sao distintos")
    return {"ids_tools_call": ids_call, "descoberta_antes": True, "eventos": len(eventos)}


def _traceparent_exclusivo() -> tuple[str, str]:
    trace_id = secrets.token_hex(16)
    span_id = secrets.token_hex(8)
    return trace_id, f"00-{trace_id}-{span_id}-01"


def _get(url: str, timeout: float) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            status = int(resp.status)
    except (TimeoutError, urllib.error.URLError) as err:
        if isinstance(err, TimeoutError) or isinstance(getattr(err, "reason", None), TimeoutError):
            raise EntregaFalha("timeout de rede") from None
        raise EntregaFalha("falha de rede") from None
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise EntregaFalha("card sem objeto JSON")
    return status, parsed


def enviar_a2a(
    cliente: Any,
    base: str,
    method: str,
    params: dict[str, Any],
    *,
    traceparent: str | None = None,
) -> tuple[dict[str, Any], str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if traceparent:
        headers["traceparent"] = traceparent
    corpo = {"jsonrpc": "2.0", "id": _novo_id("a2a"), "method": method, "params": params}
    try:
        _status, parsed, raw = cliente.post(f"{base.rstrip('/')}/a2a", corpo, headers)
    except ErroHttpJsonRpc as err:
        # Erros HTTP também são respostas públicas. Inspecione o corpo sem
        # transformar uma falha de transporte em prova de terminalidade.
        if chaves_privadas(err.parsed):
            raise EntregaFalha("estrutura privada em resposta A2A") from None
        raise
    if chaves_privadas(parsed):
        raise EntregaFalha("estrutura privada em resposta A2A")
    return parsed, raw


def extrair_task(parsed: dict[str, Any]) -> dict[str, Any]:
    if "error" in parsed:
        codigo = (parsed.get("error") or {}).get("code")
        raise EntregaFalha(f"jsonrpc={codigo}")
    result = parsed.get("result")
    if isinstance(result, dict) and "status" in result and "id" in result:
        return result
    if isinstance(result, dict) and isinstance(result.get("task"), dict):
        return result["task"]
    raise EntregaFalha("resposta A2A sem Task")


def texto_partes(mensagem: dict[str, Any] | None) -> str:
    if not isinstance(mensagem, dict):
        return ""
    return "".join(
        part.get("text", "") for part in (mensagem.get("parts") or []) if isinstance(part, dict)
    )


def estado_task(task: dict[str, Any]) -> str:
    return str((task.get("status") or {}).get("state") or "")


def artifact_reserva(task: dict[str, Any]) -> dict[str, Any]:
    for artifact in task.get("artifacts") or []:
        if not isinstance(artifact, dict) or artifact.get("name") != "reserva":
            continue
        texto = texto_partes({"parts": artifact.get("parts")})
        dados = json.loads(texto)
        if isinstance(dados, dict):
            return dados
    raise EntregaFalha("artifact reserva ausente")


def chaves_privadas(valor: Any, prefixo: str = "") -> list[str]:
    achados: list[str] = []
    if isinstance(valor, dict):
        for chave, item in valor.items():
            caminho = f"{prefixo}.{chave}" if prefixo else str(chave)
            if chave in CHAVES_PRIVADAS:
                achados.append(caminho)
            achados.extend(chaves_privadas(item, caminho))
    elif isinstance(valor, list):
        for indice, item in enumerate(valor):
            achados.extend(chaves_privadas(item, f"{prefixo}[{indice}]"))
    elif isinstance(valor, str) and valor.lstrip().startswith(("{", "[")):
        try:
            embutido = json.loads(valor)
        except json.JSONDecodeError:
            pass
        else:
            achados.extend(chaves_privadas(embutido, prefixo))
    return achados


def mensagem_usuario(texto: str, task_id: str | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "messageId": _novo_id("msg"),
        "role": "ROLE_USER",
        "parts": [{"text": texto}],
    }
    if task_id:
        msg["taskId"] = task_id
    return msg


def reservar(
    cliente: Any,
    base: str,
    texto: str,
    *,
    task_id: str | None = None,
    traceparent: str | None = None,
) -> dict[str, Any]:
    parsed, _raw = enviar_a2a(
        cliente,
        base,
        "SendMessage",
        {"message": mensagem_usuario(texto, task_id)},
        traceparent=traceparent,
    )
    return extrair_task(parsed)


def consultar_task(cliente: Any, base: str, task_id: str) -> dict[str, Any]:
    parsed, _raw = enviar_a2a(cliente, base, "GetTask", {"id": task_id})
    return extrair_task(parsed)


def rejeita_terminal(cliente: Any, base: str, task_id: str) -> None:
    parsed, _raw = enviar_a2a(
        cliente,
        base,
        "SendMessage",
        {"message": mensagem_usuario("escolha=sala-mirante", task_id)},
    )
    if "error" not in parsed:
        raise EntregaFalha(f"task terminal {task_id} aceitou nova mensagem")


def sala_livre(cliente: Any, mcp_url: str, sala: str, inicio: str, fim: str) -> bool:
    result = chamar_mcp(
        cliente,
        mcp_url,
        "tools/call",
        {
            "name": "consultar_disponibilidade",
            "arguments": {"sala": sala, "inicio": inicio, "fim": fim},
        },
        name="consultar_disponibilidade",
        req_id=_novo_id("livre"),
    )
    return (result.get("structuredContent") or {}).get("livre") is True


def _varrer(rotulo: str, payload: Any, acumulado: list[str]) -> None:
    achados = chaves_privadas(payload)
    if achados:
        acumulado.append(rotulo)


def conferir_reserva(
    task: dict[str, Any],
    original: dict[str, Any],
    pedido: dict[str, str],
    sala: str,
    politica: str | None = None,
) -> None:
    for campo in ("id", "contextId"):
        if not original.get(campo) or task.get(campo) != original[campo]:
            raise EntregaFalha("aceite trocou a identidade ou contexto da task")
    if estado_task(task) != "TASK_STATE_COMPLETED":
        raise EntregaFalha("aceite nao concluiu")
    dados = artifact_reserva(task)
    esperado = {**pedido, "sala": sala}
    if any(dados.get(campo) != esperado[campo] for campo in CAMPOS_PEDIDO):
        raise EntregaFalha("aceite misturou sala, responsavel ou intervalo")
    if politica is not None and dados.get("politica") != politica:
        raise EntregaFalha("politica do artifact difere da versao do resource")


def executar_rastreamento(cliente: Any, base: str, log_path: str) -> None:
    try:
        with open(log_path, encoding="utf-8", errors="replace") as handle:
            antes = handle.read()
    except OSError as err:
        raise EntregaFalha("log MCP ilegivel") from err
    trace_id, traceparent = _traceparent_exclusivo()
    texto = (
        "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 "
        "fim=2026-11-03T15:00:00-03:00 responsavel=Trace"
    )
    task = reservar(cliente, base, texto, traceparent=traceparent)
    if estado_task(task) != "TASK_STATE_INPUT_REQUIRED":
        raise EntregaFalha("rastreamento nao obteve pausa")
    linha = texto_partes((task.get("status") or {}).get("message"))
    if not linha.startswith("alternativas: "):
        raise EntregaFalha("pausa sem lista de alternativas")
    alternativa = linha.removeprefix("alternativas: ").split(",")[0].strip()
    retomada = reservar(cliente, base, f"escolha={alternativa}", task_id=task["id"], traceparent=traceparent)
    conferir_reserva(retomada, task, {**PEDIDO_CONFLITO, "responsavel": "Trace"}, alternativa)
    with open(log_path, encoding="utf-8", errors="replace") as handle:
        depois = handle.read()
    novas = depois[len(antes):] if depois.startswith(antes) else depois
    resumo = avaliar_rastreamento(novas.splitlines(), trace_id)
    print(
        f"rastreamento trace_id={trace_id} ids={','.join(resumo['ids_tools_call'][:2])}",
        flush=True,
    )


def executar_privacidade(cliente: Any, base: str, mcp_url: str) -> None:
    vazamentos: list[str] = []
    status_card, card = _get(f"{base.rstrip('/')}/.well-known/agent-card.json", cliente.timeout)
    if status_card != 200:
        raise EntregaFalha(f"http={status_card}")
    _varrer("card", card, vazamentos)
    politica = versao_politica(cliente, mcp_url)

    pausa_a = reservar(
        cliente,
        base,
        "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 "
        "fim=2026-11-03T15:00:00-03:00 responsavel=Doc",
    )
    _varrer("pausa-a", pausa_a, vazamentos)
    if estado_task(pausa_a) != "TASK_STATE_INPUT_REQUIRED":
        raise EntregaFalha("conflito inicial nao pausou")
    if texto_partes((pausa_a.get("status") or {}).get("message")) != "alternativas: sala-fusca, sala-mirante":
        raise EntregaFalha("lista inicial diferente do schema")
    invalida = reservar(cliente, base, "escolha=sala-porao", task_id=pausa_a["id"])
    _varrer("escolha-invalida", invalida, vazamentos)
    if invalida["id"] != pausa_a["id"] or estado_task(invalida) != "TASK_STATE_INPUT_REQUIRED":
        raise EntregaFalha("escolha invalida nao manteve a pausa")
    if texto_partes((invalida.get("status") or {}).get("message")) != "alternativas: sala-fusca, sala-mirante":
        raise EntregaFalha("escolha invalida alterou a lista")
    if not sala_livre(cliente, mcp_url, "sala-fusca", "2026-11-03T14:00:00-03:00", "2026-11-03T15:00:00-03:00"):
        raise EntregaFalha("escolha invalida criou reserva")

    pausa_b = reservar(
        cliente,
        base,
        "reservar sala=sala-fusca inicio=2026-11-03T16:00:00-03:00 "
        "fim=2026-11-03T17:00:00-03:00 responsavel=Biff",
    )
    _varrer("pausa-b", pausa_b, vazamentos)
    if estado_task(pausa_b) != "TASK_STATE_INPUT_REQUIRED":
        raise EntregaFalha("segunda pausa nao ocorreu")
    if texto_partes((pausa_b.get("status") or {}).get("message")) != "alternativas: sala-garagem, sala-mirante":
        raise EntregaFalha("lista da segunda pausa inesperada")

    aceite_b = reservar(cliente, base, "escolha=sala-garagem", task_id=pausa_b["id"])
    _varrer("aceite-b", aceite_b, vazamentos)
    aceite_a = reservar(cliente, base, "escolha=sala-fusca", task_id=pausa_a["id"])
    _varrer("aceite-a", aceite_a, vazamentos)
    for task, original, sala, responsavel, inicio, fim in (
        (aceite_b, pausa_b, "sala-garagem", "Biff", "2026-11-03T16:00:00-03:00", "2026-11-03T17:00:00-03:00"),
        (aceite_a, pausa_a, "sala-fusca", "Doc", "2026-11-03T14:00:00-03:00", "2026-11-03T15:00:00-03:00"),
    ):
        pedido = {"sala": sala, "responsavel": responsavel, "inicio": inicio, "fim": fim}
        conferir_reserva(task, original, pedido, sala, politica)
        consultada = consultar_task(cliente, base, original["id"])
        conferir_reserva(consultada, original, pedido, sala, politica)
        if artifact_reserva(consultada) != artifact_reserva(task):
            raise EntregaFalha("GetTask alterou a reserva da task retomada")

    direta = reservar(
        cliente,
        base,
        "reservar sala=sala-aquario inicio=2026-11-03T09:00:00-03:00 "
        "fim=2026-11-03T10:00:00-03:00 responsavel=Lorraine",
    )
    _varrer("direta", direta, vazamentos)
    if estado_task(direta) != "TASK_STATE_COMPLETED":
        raise EntregaFalha("reserva direta nao concluiu")
    if artifact_reserva(direta).get("politica") != politica:
        raise EntregaFalha("politica do artifact difere da versao do resource")

    recusa = reservar(
        cliente,
        base,
        "reservar sala=sala-fusca inicio=2026-11-03T16:00:00-03:00 "
        "fim=2026-11-03T17:00:00-03:00 responsavel=Jennifer",
    )
    _varrer("pre-recusa", recusa, vazamentos)
    if estado_task(recusa) != "TASK_STATE_INPUT_REQUIRED":
        raise EntregaFalha("recusa nao partiu de pausa")
    cancelada = reservar(cliente, base, "escolha=recusar", task_id=recusa["id"])
    _varrer("recusa", cancelada, vazamentos)
    if estado_task(cancelada) != "TASK_STATE_CANCELED":
        raise EntregaFalha("recusa nao cancelou")
    if sala_livre(cliente, mcp_url, "sala-mirante", "2026-11-03T16:00:00-03:00", "2026-11-03T17:00:00-03:00") is not True:
        raise EntregaFalha("recusa reservou alternativa")

    falha = reservar(
        cliente,
        base,
        "reservar sala=sala-delorean inicio=2026-11-03T10:00:00-03:00 "
        "fim=2026-11-03T11:00:00-03:00 responsavel=Doc",
    )
    _varrer("falha", falha, vazamentos)
    if estado_task(falha) != "TASK_STATE_FAILED":
        raise EntregaFalha("erro de dominio nao falhou a task")
    historico = " ".join(texto_partes(msg) for msg in (falha.get("history") or []) if isinstance(msg, dict))
    if "Sala inexistente: sala-delorean" not in historico:
        raise EntregaFalha("historico sem a mensagem exata de dominio")

    for rotulo, task_id, esperado in (
        ("get-completa", direta["id"], "TASK_STATE_COMPLETED"),
        ("get-cancelada", cancelada["id"], "TASK_STATE_CANCELED"),
        ("get-falha", falha["id"], "TASK_STATE_FAILED"),
    ):
        consultada = consultar_task(cliente, base, task_id)
        _varrer(rotulo, consultada, vazamentos)
        if consultada["id"] != task_id or estado_task(consultada) != esperado:
            raise EntregaFalha("GetTask nao refletiu a task")
        rejeita_terminal(cliente, base, task_id)

    if vazamentos:
        raise EntregaFalha("estrutura privada em resposta A2A: " + "; ".join(vazamentos))
    print(
        "privacidade ok direta pausa invalida aceite recusa falha get terminal isolamento",
        flush=True,
    )


def _validar_url(url: str, *, mcp: bool) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise EntregaFalha("URL invalida")
    if mcp and not parsed.path.rstrip("/").endswith("/mcp"):
        raise EntregaFalha("URL MCP invalida")
    if not mcp and parsed.path.rstrip("/").endswith("/a2a"):
        raise EntregaFalha("URL do agente deve ser a base, sem /a2a")
    return url.rstrip("/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verifica evidências HTTP da entrega.")
    parser.add_argument("--agente", default=AGENTE_PADRAO)
    parser.add_argument("--mcp", default=MCP_PADRAO)
    parser.add_argument("--caso", required=True, choices=("reinicio-mcp", "rastreamento", "privacidade"))
    parser.add_argument("--fase", choices=("emitir", "retomar"))
    parser.add_argument("--estado")
    parser.add_argument("--log-mcp")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_PADRAO)
    try:
        args = parser.parse_args(argv)
        if args.timeout <= 0:
            raise EntregaFalha("timeout invalido")
        agente = _validar_url(args.agente, mcp=False)
        mcp = _validar_url(args.mcp, mcp=True)
        cliente = ClienteHttp(args.timeout)
        if args.caso == "reinicio-mcp":
            if args.fase is None or not args.estado:
                raise EntregaFalha("reinicio-mcp exige --fase e --estado")
            if args.fase == "emitir":
                emitir_reinicio(cliente, mcp, args.estado)
            else:
                retomar_reinicio(cliente, mcp, args.estado)
        elif args.caso == "rastreamento":
            if not args.log_mcp:
                raise EntregaFalha("rastreamento exige --log-mcp")
            executar_rastreamento(cliente, agente, args.log_mcp)
        else:
            executar_privacidade(cliente, agente, mcp)
    except EntregaFalha as err:
        print(f"falha: {err}", file=sys.stderr)
        return 1
    except ErroHttpJsonRpc as err:
        print(f"falha: {diagnostico_publico(err)}", file=sys.stderr)
        return 1
    except SystemExit as err:
        code = err.code
        return int(code) if isinstance(code, int) else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
