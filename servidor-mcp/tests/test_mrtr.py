"""Suporte de consumidor MCP direto e testes de integração MRTR (spec 002)."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from typing import Any
import unittest
from unittest.mock import patch

from mcp.server.request_state import AESGCMRequestStateCodec, compact_json

from ponte_mcp.app import DEFAULT_STATE_TTL, SERVER_NAME

from test_mcp_http import (
    DADOS_DIR,
    DEFAULT_CAPABILITIES,
    PROTOCOL_VERSION,
    ROOT_DIR,
    VALID_SECRET_HEX,
    MCPServerSubprocess,
    build_mcp_headers,
    build_mcp_meta,
    find_free_port,
    load_wire_request_body,
    post_raw_json,
    running_mcp_server,
)

EXEMPLO_03_CONFLITO = "03-tools-call-conflito-input-required.json"
EXEMPLO_04_RETRY_ACCEPT = "04-tools-call-retry.json"
EXEMPLO_06_SEM_CAPABILITY = "06-erro-32021-sem-elicitation.json"
EXEMPLO_11_RETRY_DECLINE = "11-tools-call-retry-recusa.json"


@dataclass(frozen=True)
class NegociacaoCapturada:
    """Dados capturados na resposta input_required mantendo requestState opaco."""

    initial_id: int | str
    tool_name: str
    original_arguments: dict[str, Any]
    elicitation_key: str
    elicitation_request: dict[str, Any]
    request_state: str
    traceparent: str | None = None


def build_retry_request_body(
    negociacao: NegociacaoCapturada,
    *,
    input_responses: dict[str, Any] | None = None,
    action: str | None = None,
    content: dict[str, Any] | None = None,
    request_state: str | None = None,
    include_input_responses: bool = True,
    include_request_state: bool = True,
    override_arguments: dict[str, Any] | None = None,
    override_tool_name: str | None = None,
    retry_id: int | str | None = None,
    capabilities: dict[str, Any] | None = DEFAULT_CAPABILITIES,
    traceparent: str | None = None,
    meta: dict[str, Any] | None = None,
    include_meta: bool = True,
    headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Constrói corpo JSON-RPC e cabeçalhos HTTP espelhados para retry MRTR com id novo."""
    if retry_id is None:
        candidate_id: int | str = f"retry-{secrets.token_hex(6)}"
        while candidate_id == negociacao.initial_id:
            candidate_id = f"retry-{secrets.token_hex(6)}"
    else:
        if retry_id == negociacao.initial_id:
            raise ValueError("O retry MRTR deve usar um id JSON-RPC diferente do request inicial")
        candidate_id = retry_id

    tool_name = override_tool_name if override_tool_name is not None else negociacao.tool_name
    arguments = (
        dict(override_arguments)
        if override_arguments is not None
        else dict(negociacao.original_arguments)
    )
    tp = traceparent if traceparent is not None else negociacao.traceparent
    actual_meta = (
        meta
        if meta is not None
        else build_mcp_meta(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=capabilities,
            traceparent=tp,
        )
    )

    params: dict[str, Any] = {
        "name": tool_name,
        "arguments": arguments,
    }
    if include_meta:
        params["_meta"] = actual_meta

    if include_input_responses:
        if input_responses is not None:
            params["inputResponses"] = input_responses
        else:
            resp_entry: dict[str, Any] = {"action": action or "accept"}
            if content is not None:
                resp_entry["content"] = content
            params["inputResponses"] = {negociacao.elicitation_key: resp_entry}

    if include_request_state:
        params["requestState"] = (
            negociacao.request_state if request_state is None else request_state
        )

    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": candidate_id,
        "method": "tools/call",
        "params": params,
    }
    actual_headers = (
        headers
        if headers is not None
        else build_mcp_headers(
            method="tools/call",
            name=tool_name,
            protocol_version=PROTOCOL_VERSION,
        )
    )
    return body, actual_headers


class ConsumidorMCPDireto:
    """Consumidor HTTP direto de teste para MRTR sem callback automático e sem abrir tokens."""

    def __init__(self, server: MCPServerSubprocess) -> None:
        self.server = server
        self.discovered_tools: dict[str, dict[str, Any]] = {}
        self.politica_versao: str | None = None

    def descobrir_e_ler_politica(
        self,
        *,
        traceparent: str | None = None,
    ) -> tuple[dict[str, dict[str, Any]], str]:
        """Executa tools/list e resources/read (politica://uso) antes da negociação."""
        st_list, resp_list, _ = self.server.request(
            "tools/list",
            req_id=f"disc-{secrets.token_hex(4)}",
            traceparent=traceparent,
        )
        if st_list != 200:
            raise AssertionError(f"tools/list falhou com status {st_list}: {resp_list}")
        tools_list = (resp_list.get("result") or {}).get("tools", [])
        self.discovered_tools = {t["name"]: t for t in tools_list}

        st_pol, resp_pol, _ = self.server.request(
            "resources/read",
            {"uri": "politica://uso"},
            name="politica://uso",
            req_id=f"pol-{secrets.token_hex(4)}",
            traceparent=traceparent,
        )
        if st_pol != 200:
            raise AssertionError(f"resources/read falhou com status {st_pol}: {resp_pol}")
        contents = (resp_pol.get("result") or {}).get("contents", [])
        texto_politica = contents[0]["text"]
        self.politica_versao = texto_politica.splitlines()[0].split(":", 1)[1].strip()
        return self.discovered_tools, self.politica_versao

    def consultar_disponibilidade(
        self,
        sala: str,
        inicio: str,
        fim: str,
        *,
        traceparent: str | None = None,
    ) -> dict[str, Any]:
        """Consulta disponibilidade via HTTP e retorna structuredContent."""
        if not self.discovered_tools:
            self.descobrir_e_ler_politica(traceparent=traceparent)
        tool_name = self.discovered_tools["consultar_disponibilidade"]["name"]
        st, resp, _ = self.server.request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": {"sala": sala, "inicio": inicio, "fim": fim},
            },
            name=tool_name,
            traceparent=traceparent,
        )
        if st != 200:
            raise AssertionError(f"consultar_disponibilidade falhou ({st}): {resp}")
        return resp["result"]["structuredContent"]

    def snapshot_conflitos(
        self,
        salas: list[str],
        inicio: str,
        fim: str,
    ) -> dict[str, list[dict[str, Any]]]:
        """Retorna mapa sala -> lista de conflitos no intervalo para comparar antes/depois."""
        snap: dict[str, list[dict[str, Any]]] = {}
        for s in salas:
            disp = self.consultar_disponibilidade(s, inicio, fim)
            snap[s] = disp["conflitos"]
        return snap

    def iniciar_negociacao_conflito(
        self,
        *,
        sala: str = "sala-garagem",
        inicio: str = "2026-11-03T14:00:00-03:00",
        fim: str = "2026-11-03T15:00:00-03:00",
        responsavel: str = "Marty",
        req_id: int | str | None = None,
        capabilities: dict[str, Any] | None = DEFAULT_CAPABILITIES,
        traceparent: str | None = None,
    ) -> tuple[int, dict[str, Any], NegociacaoCapturada]:
        """Envia tools/call reservar_sala e captura chave e requestState opaco do input_required."""
        if not self.discovered_tools:
            self.descobrir_e_ler_politica(traceparent=traceparent)
        tool_name = self.discovered_tools["reservar_sala"]["name"]
        actual_id: int | str = req_id if req_id is not None else f"init-{secrets.token_hex(6)}"
        arguments = {
            "sala": sala,
            "inicio": inicio,
            "fim": fim,
            "responsavel": responsavel,
        }
        status, resp, _ = self.server.request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
            name=tool_name,
            req_id=actual_id,
            capabilities=capabilities,
            traceparent=traceparent,
        )
        result = resp.get("result") or {}
        input_requests = result.get("inputRequests") or {}
        if len(input_requests) != 1:
            raise AssertionError(f"Esperada 1 entrada em inputRequests, recebido: {resp}")
        elicitation_key = next(iter(input_requests.keys()))
        request_state = result.get("requestState")
        if not isinstance(request_state, str) or not request_state:
            raise AssertionError(f"requestState ausente ou inválido: {resp}")
        negociacao = NegociacaoCapturada(
            initial_id=actual_id,
            tool_name=tool_name,
            original_arguments=arguments,
            elicitation_key=elicitation_key,
            elicitation_request=input_requests[elicitation_key],
            request_state=request_state,
            traceparent=traceparent,
        )
        return status, resp, negociacao

    def enviar_retry(
        self,
        negociacao: NegociacaoCapturada,
        **kwargs: Any,
    ) -> tuple[int, dict[str, Any], dict[str, Any]]:
        """Envia o retry HTTP para o servidor atual e retorna (status_http, resposta_json, request_body)."""
        body, headers = build_retry_request_body(negociacao, **kwargs)
        status, resp, _ = post_raw_json(self.server.url, body, headers)
        return status, resp, body


class TestSuporteConsumidorMRTRT002(unittest.TestCase):
    """Sanidade do consumidor direto de teste e extração de exemplos (T002)."""

    def test_extrai_apenas_request_body_dos_exemplos_03_04_06_11(self) -> None:
        for filename in (
            EXEMPLO_03_CONFLITO,
            EXEMPLO_04_RETRY_ACCEPT,
            EXEMPLO_06_SEM_CAPABILITY,
            EXEMPLO_11_RETRY_DECLINE,
        ):
            with self.subTest(exemplo=filename):
                body = load_wire_request_body(filename)
                self.assertEqual(body["jsonrpc"], "2.0")
                self.assertEqual(body["method"], "tools/call")
                self.assertNotIn("descricao", body)
                self.assertNotIn("response", body)
                self.assertEqual(body["params"]["name"], "reservar_sala")

    def test_construcao_retry_usa_id_novo_preserva_argumentos_e_ecoa_token_opaco(self) -> None:
        neg = NegociacaoCapturada(
            initial_id=3,
            tool_name="reservar_sala",
            original_arguments={
                "sala": "sala-garagem",
                "inicio": "2026-11-03T14:00:00-03:00",
                "fim": "2026-11-03T15:00:00-03:00",
                "responsavel": "Marty",
            },
            elicitation_key="chave-servidor",
            elicitation_request={"method": "elicitation/create"},
            request_state="v1.token_opaco_inalterado",
            traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        )
        body, headers = build_retry_request_body(
            neg,
            action="accept",
            content={"sala": "sala-fusca"},
        )
        self.assertNotEqual(body["id"], neg.initial_id)
        self.assertEqual(body["params"]["name"], "reservar_sala")
        self.assertEqual(body["params"]["arguments"], neg.original_arguments)
        self.assertEqual(body["params"]["requestState"], "v1.token_opaco_inalterado")
        self.assertEqual(
            body["params"]["inputResponses"],
            {"chave-servidor": {"action": "accept", "content": {"sala": "sala-fusca"}}},
        )
        self.assertEqual(
            body["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"],
            PROTOCOL_VERSION,
        )
        self.assertEqual(
            body["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"],
            {"elicitation": {"form": {}}},
        )
        self.assertEqual(headers["MCP-Protocol-Version"], PROTOCOL_VERSION)
        self.assertEqual(headers["Mcp-Method"], "tools/call")
        self.assertEqual(headers["Mcp-Name"], "reservar_sala")
        with self.assertRaises(ValueError):
            build_retry_request_body(neg, retry_id=3)

    def test_descoberta_tools_e_leitura_politica_antes_da_negociacao(self) -> None:
        with running_mcp_server() as srv:
            consumidor = ConsumidorMCPDireto(srv)
            tools, versao = consumidor.descobrir_e_ler_politica(
                traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
            )
            self.assertIn("reservar_sala", tools)
            self.assertIn("consultar_disponibilidade", tools)
            self.assertEqual(versao, "2026-11-01")


class TestUS1JornadaAcceptEAlternativasHTTP(unittest.TestCase):
    """Testes de integração HTTP real para US1 (T009): jornada 03/04, sem alternativas, fora do schema e ocupação pós-oferta."""

    def test_jornada_conflito_input_required_e_retry_accept_exemplos_03_04(self) -> None:
        req_03 = load_wire_request_body(EXEMPLO_03_CONFLITO)
        args_03 = req_03["params"]["arguments"]
        tp_03 = req_03["params"]["_meta"]["traceparent"]

        with running_mcp_server() as srv:
            consumidor = ConsumidorMCPDireto(srv)
            _, versao_politica = consumidor.descobrir_e_ler_politica(traceparent=tp_03)

            # 1. Enviar request.body do exemplo 03
            st_init, resp_init, neg = consumidor.iniciar_negociacao_conflito(
                sala=args_03["sala"],
                inicio=args_03["inicio"],
                fim=args_03["fim"],
                responsavel=args_03["responsavel"],
                req_id=req_03["id"],
                traceparent=tp_03,
            )
            self.assertEqual(st_init, 200)
            res_init = resp_init["result"]
            self.assertEqual(res_init["resultType"], "input_required")
            self.assertEqual(len(res_init["inputRequests"]), 1)
            self.assertIsInstance(neg.request_state, str)
            self.assertTrue(neg.request_state)

            elicit = neg.elicitation_request
            self.assertEqual(elicit["method"], "elicitation/create")
            params_elicit = elicit["params"]
            self.assertEqual(params_elicit["mode"], "form")
            self.assertTrue(params_elicit.get("message"))

            req_schema = params_elicit["requestedSchema"]
            self.assertEqual(req_schema.get("type"), "object")
            self.assertEqual(req_schema.get("required"), ["sala"])
            props = req_schema.get("properties", {})
            self.assertEqual(set(props.keys()), {"sala"})
            prop_sala = props["sala"]
            self.assertEqual(prop_sala.get("type"), "string")
            self.assertEqual(prop_sala.get("enum"), ["sala-fusca", "sala-mirante"])

            # 2. Confirmar que nenhuma reserva foi criada na emissão
            for s in ("sala-fusca", "sala-mirante"):
                disp = consumidor.consultar_disponibilidade(
                    s, args_03["inicio"], args_03["fim"], traceparent=tp_03
                )
                self.assertTrue(disp["livre"])

            # 3. Enviar retry accept com id diferente, chave capturada e token literalmente igual
            st_retry, resp_retry, body_retry = consumidor.enviar_retry(
                neg,
                action="accept",
                content={"sala": "sala-fusca"},
                retry_id=4,
            )
            self.assertEqual(st_retry, 200)
            self.assertNotEqual(body_retry["id"], req_03["id"])
            self.assertEqual(body_retry["params"]["requestState"], neg.request_state)

            res_retry = resp_retry["result"]
            self.assertEqual(res_retry.get("resultType"), "complete")
            self.assertFalse(res_retry.get("isError", False))
            sc = res_retry["structuredContent"]
            texto_json = " ".join(p.get("text", "") for p in res_retry.get("content", []))
            self.assertEqual(json.loads(texto_json), sc)

            self.assertIs(sc["reservado"], True)
            self.assertIsInstance(sc["reserva"], str)
            self.assertTrue(sc["reserva"])
            self.assertNotIn(sc["reserva"], {"res-0001", "res-0002"})
            self.assertEqual(sc["sala"], "sala-fusca")
            self.assertEqual(sc["inicio"], args_03["inicio"])
            self.assertEqual(sc["fim"], args_03["fim"])
            self.assertEqual(sc["responsavel"], args_03["responsavel"])
            self.assertEqual(sc["politica"], versao_politica)
            self.assertIsNone(sc.get("motivo"))

            # 4. Consulta posterior mostra sala-fusca ocupada com a nova reserva e sala-mirante livre
            disp_fusca = consumidor.consultar_disponibilidade(
                "sala-fusca", args_03["inicio"], args_03["fim"], traceparent=tp_03
            )
            self.assertFalse(disp_fusca["livre"])
            self.assertEqual(len(disp_fusca["conflitos"]), 1)
            self.assertEqual(disp_fusca["conflitos"][0]["id"], sc["reserva"])
            self.assertEqual(disp_fusca["conflitos"][0]["responsavel"], "Marty")

            disp_mirante = consumidor.consultar_disponibilidade(
                "sala-mirante", args_03["inicio"], args_03["fim"], traceparent=tp_03
            )
            self.assertTrue(disp_mirante["livre"])

            # 5. Conferir stderr: tools/list antes de tools/call, traceparent propagado e ids distintos
            stderr = srv.read_stderr()
            pos_list = stderr.find("method=tools/list")
            pos_call_init = stderr.find(f"method=tools/call id={req_03['id']} traceparent={tp_03}")
            pos_call_retry = stderr.find(f"method=tools/call id=4 traceparent={tp_03}")
            self.assertNotEqual(pos_list, -1)
            self.assertNotEqual(pos_call_init, -1)
            self.assertNotEqual(pos_call_retry, -1)
            self.assertLess(pos_list, pos_call_init)
            self.assertLess(pos_call_init, pos_call_retry)
            self.assertNotIn(VALID_SECRET_HEX, stderr)
            self.assertNotIn(neg.request_state, stderr)

    def test_conflito_sem_alternativas_escolha_fora_do_schema_e_ocupacao_pos_oferta(self) -> None:
        with running_mcp_server() as srv:
            consumidor = ConsumidorMCPDireto(srv)
            consumidor.descobrir_e_ler_politica()

            # 1. Conflito sem alternativas: ocupar sala-mirante (cap 20) e pedir novamente no mesmo intervalo
            st_m1, resp_m1, _ = srv.request(
                "tools/call",
                {
                    "name": "reservar_sala",
                    "arguments": {
                        "sala": "sala-mirante",
                        "inicio": "2026-11-03T11:00:00-03:00",
                        "fim": "2026-11-03T12:00:00-03:00",
                        "responsavel": "Doc",
                    },
                },
                name="reservar_sala",
            )
            self.assertEqual(st_m1, 200)
            self.assertTrue(resp_m1["result"]["structuredContent"]["reservado"])

            st_m2, resp_m2, _ = srv.request(
                "tools/call",
                {
                    "name": "reservar_sala",
                    "arguments": {
                        "sala": "sala-mirante",
                        "inicio": "2026-11-03T11:00:00-03:00",
                        "fim": "2026-11-03T12:00:00-03:00",
                        "responsavel": "Marty",
                    },
                },
                name="reservar_sala",
            )
            self.assertEqual(st_m2, 200)
            res_m2 = resp_m2["result"]
            self.assertEqual(res_m2.get("resultType"), "complete")
            self.assertIs(res_m2.get("isError"), True)
            self.assertNotIn("inputRequests", res_m2)
            texto_m2 = " ".join(p.get("text", "") for p in res_m2.get("content", []))
            self.assertIn("Sem alternativas disponiveis no intervalo", texto_m2)

            # 2. Escolha fora do schema (ex.: sala-aquario quando enum é [sala-fusca, sala-mirante])
            _, _, neg = consumidor.iniciar_negociacao_conflito()
            salas_monitoradas = ["sala-aquario", "sala-porao", "sala-garagem", "sala-fusca", "sala-mirante"]
            snap_antes = consumidor.snapshot_conflitos(
                salas_monitoradas,
                "2026-11-03T14:00:00-03:00",
                "2026-11-03T15:00:00-03:00",
            )
            _, resp_fora, _ = consumidor.enviar_retry(
                neg,
                action="accept",
                content={"sala": "sala-aquario"},
            )
            rejeitou_fora = (
                "error" in resp_fora
                or (resp_fora.get("result") or {}).get("isError") is True
            )
            self.assertTrue(rejeitou_fora)
            snap_depois_fora = consumidor.snapshot_conflitos(
                salas_monitoradas,
                "2026-11-03T14:00:00-03:00",
                "2026-11-03T15:00:00-03:00",
            )
            self.assertEqual(snap_depois_fora, snap_antes)

            # 3. Ocupar sala-fusca por reserva válida após a oferta e tentar aceitá-la
            st_ocupa, resp_ocupa, _ = srv.request(
                "tools/call",
                {
                    "name": "reservar_sala",
                    "arguments": {
                        "sala": "sala-fusca",
                        "inicio": "2026-11-03T14:00:00-03:00",
                        "fim": "2026-11-03T15:00:00-03:00",
                        "responsavel": "Biff",
                    },
                },
                name="reservar_sala",
            )
            self.assertEqual(st_ocupa, 200)
            self.assertTrue(resp_ocupa["result"]["structuredContent"]["reservado"])

            snap_pos_ocupacao = consumidor.snapshot_conflitos(
                salas_monitoradas,
                "2026-11-03T14:00:00-03:00",
                "2026-11-03T15:00:00-03:00",
            )

            st_tardia, resp_tardia, _ = consumidor.enviar_retry(
                neg,
                action="accept",
                content={"sala": "sala-fusca"},
            )
            self.assertEqual(st_tardia, 200)
            res_tardia = resp_tardia.get("result") or {}
            self.assertEqual(res_tardia.get("resultType"), "complete")
            self.assertIs(res_tardia.get("isError"), True)
            self.assertNotIn("inputRequests", res_tardia)

            snap_final = consumidor.snapshot_conflitos(
                salas_monitoradas,
                "2026-11-03T14:00:00-03:00",
                "2026-11-03T15:00:00-03:00",
            )
            self.assertEqual(snap_final, snap_pos_ocupacao)


def _mint_custom_inner_state_token(
    *,
    secret_hex: str,
    arguments: dict[str, Any],
    inner_payload: dict[str, Any] | str,
    tool_name: str = "reservar_sala",
    audience: str = SERVER_NAME,
    iat: float | None = None,
    ttl: float = DEFAULT_STATE_TTL,
) -> str:
    """Gera fixture de teste selada pelo codec oficial do SDK para testar validação de payload interno."""
    import base64

    now = time.time() if iat is None else iat
    args_digest_bytes = hashlib.sha256(
        compact_json(arguments, sort_keys=True).encode("utf-8")
    ).digest()[:16]
    args_digest = base64.urlsafe_b64encode(args_digest_bytes).decode("ascii").rstrip("=")
    inner_str = (
        inner_payload
        if isinstance(inner_payload, str)
        else compact_json(inner_payload, sort_keys=True)
    )
    claims = {
        "v": 1,
        "iat": now,
        "exp": now + ttl,
        "m": "tools/call",
        "t": tool_name,
        "a": args_digest,
        "s": inner_str,
        "aud": audience,
    }
    codec = AESGCMRequestStateCodec([bytes.fromhex(secret_hex)])
    return codec.seal(compact_json(claims).encode("utf-8"))


def _alterar_um_caractere_token(token: str) -> str:
    """Altera um caractere na parte base64url do token sem decodificar seu conteúdo."""
    ultimo = token[-2]
    substituto = "A" if ultimo != "A" else "B"
    return token[:-2] + substituto + token[-1]


class TestUS2SegurancaIntegridadeExpiracaoERestartHTTP(unittest.TestCase):
    """Testes de integração HTTP real para US2 (T016, T017): matriz negativa completa e restart real."""

    def test_matriz_negativa_integridade_argumentos_incompletos_correlacao_e_payload_t016(self) -> None:
        salas_todas = ["sala-aquario", "sala-porao", "sala-garagem", "sala-fusca", "sala-mirante"]
        intervalo_ini = "2026-11-03T14:00:00-03:00"
        intervalo_fim = "2026-11-03T15:00:00-03:00"

        with running_mcp_server(secret=VALID_SECRET_HEX) as srv:
            consumidor = ConsumidorMCPDireto(srv)
            consumidor.descobrir_e_ler_politica()
            _, _, neg = consumidor.iniciar_negociacao_conflito(
                sala="sala-garagem",
                inicio=intervalo_ini,
                fim=intervalo_fim,
                responsavel="Marty",
            )
            snap_inicial = consumidor.snapshot_conflitos(salas_todas, intervalo_ini, intervalo_fim)

            # 1. Estado adulterado: (a) trocar 1 caractere dos bytes do token, (b) truncar o token
            token_1char = _alterar_um_caractere_token(neg.request_state)
            token_truncado = neg.request_state[:-10]
            for rotulo, token_invalido in (
                ("um_caractere_alterado", token_1char),
                ("token_truncado", token_truncado),
            ):
                with self.subTest(caso="estado_adulterado", variante=rotulo):
                    st, resp, _ = consumidor.enviar_retry(
                        neg,
                        action="accept",
                        content={"sala": "sala-fusca"},
                        request_state=token_invalido,
                    )
                    self.assertEqual(st, 400)
                    self.assertEqual((resp.get("error") or {}).get("code"), -32602)
                    self.assertNotIn("result", resp)
                    self.assertEqual(
                        consumidor.snapshot_conflitos(salas_todas, intervalo_ini, intervalo_fim),
                        snap_inicial,
                    )

            # 2. Argumentos adulterados separadamente: sala, inicio, fim, responsavel
            variacoes_args = [
                ("sala", {**neg.original_arguments, "sala": "sala-fusca"}),
                ("inicio", {**neg.original_arguments, "inicio": "2026-11-03T13:30:00-03:00"}),
                ("fim", {**neg.original_arguments, "fim": "2026-11-03T15:30:00-03:00"}),
                ("responsavel", {**neg.original_arguments, "responsavel": "Biff"}),
            ]
            for campo, args_adulterados in variacoes_args:
                with self.subTest(caso="argumento_adulterado", campo=campo):
                    st, resp, _ = consumidor.enviar_retry(
                        neg,
                        action="accept",
                        content={"sala": "sala-fusca"},
                        override_arguments=args_adulterados,
                    )
                    self.assertEqual(st, 400)
                    self.assertEqual((resp.get("error") or {}).get("code"), -32602)
                    self.assertNotIn("result", resp)
                    self.assertEqual(
                        consumidor.snapshot_conflitos(salas_todas, intervalo_ini, intervalo_fim),
                        snap_inicial,
                    )

            # Confirmar também que o horário adulterado (13h30-15h30) permanece livre em sala-fusca
            disp_1330 = consumidor.consultar_disponibilidade(
                "sala-fusca",
                "2026-11-03T13:30:00-03:00",
                "2026-11-03T15:30:00-03:00",
            )
            self.assertTrue(disp_1330["livre"])

            # 3. Continuação incompleta: omitir somente requestState ou somente inputResponses
            # Testar tanto no argumento original (em conflito) quanto em sala livre (para provar que não faz fallback para pedido inicial!)
            for rotulo_inc, inc_kwargs in (
                (
                    "sem_requestState_conflito",
                    {"include_request_state": False, "include_input_responses": True},
                ),
                (
                    "sem_requestState_sala_livre",
                    {
                        "include_request_state": False,
                        "include_input_responses": True,
                        "override_arguments": {
                            "sala": "sala-aquario",
                            "inicio": "2026-11-03T09:00:00-03:00",
                            "fim": "2026-11-03T10:00:00-03:00",
                            "responsavel": "Doc",
                        },
                    },
                ),
                (
                    "sem_inputResponses",
                    {"include_request_state": True, "include_input_responses": False},
                ),
            ):
                with self.subTest(caso="continuacao_incompleta", variante=rotulo_inc):
                    st, resp, _ = consumidor.enviar_retry(
                        neg,
                        action="accept",
                        content={"sala": "sala-fusca"},
                        **inc_kwargs,
                    )
                    self.assertEqual(st, 400)
                    self.assertEqual((resp.get("error") or {}).get("code"), -32602)
                    self.assertNotIn("result", resp)
                    self.assertEqual(
                        consumidor.snapshot_conflitos(salas_todas, intervalo_ini, intervalo_fim),
                        snap_inicial,
                    )

            # Confirmar que sala-aquario 09h-10h continua livre (não houve fallback para chamada inicial)
            self.assertTrue(
                consumidor.consultar_disponibilidade(
                    "sala-aquario",
                    "2026-11-03T09:00:00-03:00",
                    "2026-11-03T10:00:00-03:00",
                )["livre"]
            )

            # 4. Correlação inválida: mapa vazio, chave divergente, entrada adicional
            casos_correlacao: list[tuple[str, dict[str, Any]]] = [
                ("mapa_vazio", {}),
                (
                    "chave_divergente",
                    {"outra:chave": {"action": "accept", "content": {"sala": "sala-fusca"}}},
                ),
                (
                    "entrada_adicional",
                    {
                        neg.elicitation_key: {"action": "accept", "content": {"sala": "sala-fusca"}},
                        "extra:chave": {"action": "accept", "content": {"sala": "sala-mirante"}},
                    },
                ),
            ]
            for rotulo_corr, mapa_respostas in casos_correlacao:
                with self.subTest(caso="correlacao_invalida", variante=rotulo_corr):
                    st, resp, _ = consumidor.enviar_retry(
                        neg,
                        input_responses=mapa_respostas,
                    )
                    self.assertEqual(st, 400)
                    self.assertEqual((resp.get("error") or {}).get("code"), -32602)
                    self.assertNotIn("result", resp)
                    self.assertEqual(
                        consumidor.snapshot_conflitos(salas_todas, intervalo_ini, intervalo_fim),
                        snap_inicial,
                    )

            # 5. Payload incompatível por fixture interna protegida: schema_version != 1, tool_name inválido, campo obrigatório ausente
            base_payload = {
                "schema_version": 1,
                "tool_name": "reservar_sala",
                "original_arguments": neg.original_arguments,
                "alternatives": ["sala-fusca", "sala-mirante"],
                "elicitation_key": neg.elicitation_key,
                "politica": "2026-11-01",
            }
            payload_sem_politica = dict(base_payload)
            payload_sem_politica.pop("politica")
            payload_sem_args = dict(base_payload)
            payload_sem_args.pop("original_arguments")

            for rotulo_pay, inner in (
                ("schema_version_2", {**base_payload, "schema_version": 2}),
                ("tool_name_invalido", {**base_payload, "tool_name": "listar_salas"}),
                ("sem_politica", payload_sem_politica),
                ("sem_original_arguments", payload_sem_args),
                ("alternatives_vazias", {**base_payload, "alternatives": []}),
            ):
                with self.subTest(caso="payload_incompativel", variante=rotulo_pay):
                    token_fixture = _mint_custom_inner_state_token(
                        secret_hex=VALID_SECRET_HEX,
                        arguments=neg.original_arguments,
                        inner_payload=inner,
                    )
                    st, resp, _ = consumidor.enviar_retry(
                        neg,
                        action="accept",
                        content={"sala": "sala-fusca"},
                        request_state=token_fixture,
                    )
                    self.assertEqual(st, 400)
                    self.assertEqual((resp.get("error") or {}).get("code"), -32602)
                    self.assertNotIn("result", resp)
                    self.assertEqual(
                        consumidor.snapshot_conflitos(salas_todas, intervalo_ini, intervalo_fim),
                        snap_inicial,
                    )

    def test_expiracao_com_relogio_controlado_mantendo_ttl_600s_t016(self) -> None:
        """Verifica expiração exata de 600s com unittest.mock no relógio do SDK sem reduzir TTL de produção."""
        self.assertEqual(DEFAULT_STATE_TTL, 600)
        t_emissao = 1_760_000_000.0

        # Emitir estado no instante t_emissao usando relógio controlado no worker de teste
        with self._running_mcp_server_with_clock_offset(0.0, base_time=t_emissao) as srv:
            consumidor = ConsumidorMCPDireto(srv)
            consumidor.descobrir_e_ler_politica()
            _, _, neg = consumidor.iniciar_negociacao_conflito()

        # Após 600.1s (além do TTL de 600s), o retry é rejeitado com -32602 e não cria reserva
        with self._running_mcp_server_with_clock_offset(600.1, base_time=t_emissao) as srv_exp:
            consumidor_exp = ConsumidorMCPDireto(srv_exp)
            consumidor_exp.descobrir_e_ler_politica()
            st_exp, resp_exp, _ = consumidor_exp.enviar_retry(
                neg,
                action="accept",
                content={"sala": "sala-fusca"},
            )
            self.assertEqual(st_exp, 400)
            self.assertEqual((resp_exp.get("error") or {}).get("code"), -32602)
            self.assertTrue(
                consumidor_exp.consultar_disponibilidade(
                    "sala-fusca",
                    "2026-11-03T14:00:00-03:00",
                    "2026-11-03T15:00:00-03:00",
                )["livre"]
            )

    def test_restart_real_preserva_retomada_rejeita_chave_trocada_e_mantem_expiracao_t017(self) -> None:
        """T017: restart real com mesma chave/nome conclui antes de 600s, rejeita chave trocada e não renova expiração."""
        port = find_free_port()
        tp = "00-99999999999999999999999999999999-8888888888888888-01"

        # 1. Subir instância 1, criar reserva transitória em sala-aquario e emitir negociação em sala-garagem
        with running_mcp_server(port=port, secret=VALID_SECRET_HEX) as srv1:
            cons1 = ConsumidorMCPDireto(srv1)
            cons1.descobrir_e_ler_politica(traceparent=tp)

            st_trans, resp_trans, _ = srv1.request(
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
                traceparent=tp,
            )
            self.assertEqual(st_trans, 200)
            self.assertTrue(resp_trans["result"]["structuredContent"]["reservado"])

            _, _, neg = cons1.iniciar_negociacao_conflito(
                sala="sala-garagem",
                inicio="2026-11-03T14:00:00-03:00",
                fim="2026-11-03T15:00:00-03:00",
                responsavel="Marty",
                req_id="init-restart-1",
                traceparent=tp,
            )

        # 2. Subir instância com chave diferente -> retry rejeitado com -32602 sem criar reserva
        with running_mcp_server(port=port, secret="b2" * 32) as srv_outra_chave:
            cons_outra = ConsumidorMCPDireto(srv_outra_chave)
            cons_outra.descobrir_e_ler_politica(traceparent=tp)
            st_key, resp_key, _ = cons_outra.enviar_retry(
                neg,
                action="accept",
                content={"sala": "sala-fusca"},
                retry_id="retry-wrong-key",
            )
            self.assertEqual(st_key, 400)
            self.assertEqual((resp_key.get("error") or {}).get("code"), -32602)
            self.assertTrue(
                cons_outra.consultar_disponibilidade(
                    "sala-fusca",
                    "2026-11-03T14:00:00-03:00",
                    "2026-11-03T15:00:00-03:00",
                )["livre"]
            )

        # 3. Subir nova instância com o MESMO REQUEST_STATE_SECRET, mas relógio após 601s da emissão original:
        # comprova que reiniciar o processo não renova o prazo do token emitido antes do restart
        with self._running_mcp_server_with_clock_offset(601.0, port=port, secret=VALID_SECRET_HEX) as srv_pos_ttl:
            cons_exp = ConsumidorMCPDireto(srv_pos_ttl)
            cons_exp.descobrir_e_ler_politica(traceparent=tp)
            st_exp, resp_exp, _ = cons_exp.enviar_retry(
                neg,
                action="accept",
                content={"sala": "sala-fusca"},
                retry_id="retry-expired-after-restart",
            )
            self.assertEqual(st_exp, 400)
            self.assertEqual((resp_exp.get("error") or {}).get("code"), -32602)
            self.assertTrue(
                cons_exp.consultar_disponibilidade(
                    "sala-fusca",
                    "2026-11-03T14:00:00-03:00",
                    "2026-11-03T15:00:00-03:00",
                )["livre"]
            )

        # 4. Subir nova instância normal com o MESMO REQUEST_STATE_SECRET antes dos 600s e concluir o retry
        with running_mcp_server(port=port, secret=VALID_SECRET_HEX) as srv2:
            cons2 = ConsumidorMCPDireto(srv2)
            cons2.descobrir_e_ler_politica(traceparent=tp)

            # Reserva transitória da instância 1 não sobreviveu ao restart
            disp_aquario = cons2.consultar_disponibilidade(
                "sala-aquario",
                "2026-11-03T09:00:00-03:00",
                "2026-11-03T10:00:00-03:00",
                traceparent=tp,
            )
            self.assertTrue(disp_aquario["livre"])

            # Retomar negociação emitida na instância 1 com id novo
            st_ok, resp_ok, body_ok = cons2.enviar_retry(
                neg,
                action="accept",
                content={"sala": "sala-fusca"},
                retry_id="retry-restart-2",
            )
            self.assertEqual(st_ok, 200)
            self.assertNotEqual(body_ok["id"], neg.initial_id)
            res_ok = resp_ok["result"]
            self.assertEqual(res_ok.get("resultType"), "complete")
            self.assertFalse(res_ok.get("isError", False))
            sc_ok = res_ok["structuredContent"]
            self.assertIs(sc_ok["reservado"], True)
            self.assertEqual(sc_ok["sala"], "sala-fusca")
            self.assertEqual(sc_ok["inicio"], "2026-11-03T14:00:00-03:00")
            self.assertEqual(sc_ok["fim"], "2026-11-03T15:00:00-03:00")
            self.assertEqual(sc_ok["responsavel"], "Marty")
            self.assertEqual(sc_ok["politica"], "2026-11-01")

            # Consulta seguinte na instância 2 enxerga a reserva criada
            disp_fusca = cons2.consultar_disponibilidade(
                "sala-fusca",
                "2026-11-03T14:00:00-03:00",
                "2026-11-03T15:00:00-03:00",
                traceparent=tp,
            )
            self.assertFalse(disp_fusca["livre"])
            self.assertEqual(disp_fusca["conflitos"][0]["id"], sc_ok["reserva"])

    @staticmethod
    def _running_mcp_server_with_clock_offset(
        offset_seconds: float,
        *,
        base_time: float | None = None,
        port: int | None = None,
        secret: str = VALID_SECRET_HEX,
    ) -> Any:
        """Inicia worker de teste aplicando unittest.mock.patch no relógio do SDK sem tocar código de produção."""
        from contextlib import contextmanager

        @contextmanager
        def _ctx() -> Any:
            actual_port = port if port is not None else find_free_port()
            code = (
                "import time\n"
                "from unittest.mock import patch\n"
                "import mcp.server.request_state as rs\n"
                "from ponte_mcp.__main__ import main\n"
                f"base = {base_time!r}\n"
                f"offset = {offset_seconds!r}\n"
                "real_time = time.time\n"
                "def fake_time():\n"
                "    return (base + offset) if base is not None else (real_time() + offset)\n"
                "with patch.object(rs.time, 'time', side_effect=fake_time):\n"
                "    raise SystemExit(main())\n"
            )
            srv = MCPServerSubprocess(port=actual_port, secret=secret)
            env = os.environ.copy()
            env["MCP_HOST"] = srv.host
            env["MCP_PORT"] = str(srv.port)
            env["PYTHONUNBUFFERED"] = "1"
            env["REQUEST_STATE_SECRET"] = secret
            import tempfile

            srv._stderr_file = tempfile.NamedTemporaryFile(
                mode="w+", encoding="utf-8", prefix="ponte_mcp_clock_stderr_", delete=False
            )
            srv._stdout_file = tempfile.NamedTemporaryFile(
                mode="w+", encoding="utf-8", prefix="ponte_mcp_clock_stdout_", delete=False
            )
            srv.proc = subprocess.Popen(
                [sys.executable, "-c", code],
                cwd=str(ROOT_DIR),
                env=env,
                stdout=srv._stdout_file,
                stderr=srv._stderr_file,
            )
            try:
                srv.wait_ready(timeout=10.0)
                yield srv
            finally:
                srv.stop()

        return _ctx()


class TestUS3CapabilitiesRecusaECandidatoUnicoHTTP(unittest.TestCase):
    """T021 e T022: validação de clientCapabilities.elicitation.form por request, decline/cancel e candidato único."""

    def test_matriz_capabilities_por_request_conflito_reserva_livre_e_sem_alternativas_t021(self) -> None:
        """T021: exige form apenas quando há pergunta; não herda capability anterior; distingue -32602 de -32021."""
        tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        salas_todas = [
            "sala-aquario",
            "sala-fusca",
            "sala-garagem",
            "sala-mirante",
            "sala-porao",
        ]
        ini_14 = "2026-11-03T14:00:00-03:00"
        fim_15 = "2026-11-03T15:00:00-03:00"

        with running_mcp_server() as srv:
            consumidor = ConsumidorMCPDireto(srv)
            consumidor.descobrir_e_ler_politica(traceparent=tp)
            snap_14_15 = consumidor.snapshot_conflitos(salas_todas, ini_14, fim_15)

            # 1. Primeira chamada em conflito COM form declarado funciona (input_required)
            st_ok, resp_ok, neg_ok = consumidor.iniciar_negociacao_conflito(
                req_id=101,
                traceparent=tp,
            )
            self.assertEqual(st_ok, 200)
            self.assertEqual(resp_ok["result"]["resultType"], "input_required")

            # 1b. Retry também exige _meta completo (-32602) e headers espelhados (-32020)
            st_retry_no_meta, resp_retry_no_meta, _ = consumidor.enviar_retry(
                neg_ok,
                action="accept",
                content={"sala": "sala-fusca"},
                retry_id="retry-sem-meta",
                include_meta=False,
            )
            self.assertEqual(st_retry_no_meta, 400)
            self.assertEqual((resp_retry_no_meta.get("error") or {}).get("code"), -32602)

            st_retry_bad_hdr, resp_retry_bad_hdr, _ = consumidor.enviar_retry(
                neg_ok,
                action="accept",
                content={"sala": "sala-fusca"},
                retry_id="retry-header-divergente",
                headers=build_mcp_headers("tools/call", name="listar_salas"),
            )
            self.assertEqual(st_retry_bad_hdr, 400)
            self.assertEqual((resp_retry_bad_hdr.get("error") or {}).get("code"), -32020)

            # 2. Exemplo 06 literal (clientCapabilities: {}) logo após chamada com form -> -32021 / HTTP 400 (sem herança)
            body_06 = load_wire_request_body(EXEMPLO_06_SEM_CAPABILITY)
            st_06, resp_06, _ = post_raw_json(
                srv.url,
                body_06,
                build_mcp_headers("tools/call", name="reservar_sala"),
            )
            self.assertEqual(st_06, 400)
            err_06 = resp_06.get("error") or {}
            self.assertEqual(err_06.get("code"), -32021)
            self.assertEqual(
                err_06.get("data"),
                {"requiredCapabilities": {"elicitation": {"form": {}}}},
            )
            self.assertNotIn("result", resp_06)

            # 3. Variantes sem form explícito: {}, {"elicitation": {}}, {"elicitation": {"url": {}}}
            for rotulo_cap, cap_val in (
                ("capabilities_vazio", {}),
                ("elicitation_generica_vazia", {"elicitation": {}}),
                ("elicitation_somente_url", {"elicitation": {"url": {}}}),
            ):
                with self.subTest(caso="sem_form_capability", variante=rotulo_cap):
                    st_cap, resp_cap, _ = srv.request(
                        "tools/call",
                        {
                            "name": "reservar_sala",
                            "arguments": {
                                "sala": "sala-garagem",
                                "inicio": ini_14,
                                "fim": fim_15,
                                "responsavel": "Marty",
                            },
                        },
                        name="reservar_sala",
                        capabilities=cap_val,
                        traceparent=tp,
                    )
                    self.assertEqual(st_cap, 400)
                    err_cap = resp_cap.get("error") or {}
                    self.assertEqual(err_cap.get("code"), -32021)
                    self.assertEqual(
                        err_cap.get("data"),
                        {"requiredCapabilities": {"elicitation": {"form": {}}}},
                    )
                    self.assertNotIn("result", resp_cap)
                    self.assertEqual(
                        consumidor.snapshot_conflitos(salas_todas, ini_14, fim_15),
                        snap_14_15,
                    )

            # 4. Distinguir _meta sem clientCapabilities (-32602/HTTP 400 da 001) de clientCapabilities sem form (-32021/HTTP 400)
            st_meta, resp_meta, _ = srv.request(
                "tools/call",
                {
                    "name": "reservar_sala",
                    "arguments": {
                        "sala": "sala-garagem",
                        "inicio": ini_14,
                        "fim": fim_15,
                        "responsavel": "Marty",
                    },
                },
                name="reservar_sala",
                meta=build_mcp_meta(
                    client_capabilities=None,
                    traceparent=tp,
                ),
            )
            self.assertEqual(st_meta, 400)
            self.assertEqual((resp_meta.get("error") or {}).get("code"), -32602)

            # 5. Reserva em sala livre NÃO exige form capability (conclui normalmente com capabilities={})
            st_livre, resp_livre, _ = srv.request(
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
                capabilities={},
                traceparent=tp,
            )
            self.assertEqual(st_livre, 200)
            res_livre = resp_livre["result"]
            self.assertEqual(res_livre.get("resultType"), "complete")
            self.assertFalse(res_livre.get("isError", False))
            self.assertIs(res_livre["structuredContent"]["reservado"], True)

            # 6. Conflito SEM alternativas disponíveis retorna complete/isError: true mesmo com capabilities={}
            # Ocupar sala-mirante das 11h às 12h primeiro
            st_mir1, _, _ = srv.request(
                "tools/call",
                {
                    "name": "reservar_sala",
                    "arguments": {
                        "sala": "sala-mirante",
                        "inicio": "2026-11-03T11:00:00-03:00",
                        "fim": "2026-11-03T12:00:00-03:00",
                        "responsavel": "Doc",
                    },
                },
                name="reservar_sala",
                capabilities={},
                traceparent=tp,
            )
            self.assertEqual(st_mir1, 200)

            st_mir2, resp_mir2, _ = srv.request(
                "tools/call",
                {
                    "name": "reservar_sala",
                    "arguments": {
                        "sala": "sala-mirante",
                        "inicio": "2026-11-03T11:00:00-03:00",
                        "fim": "2026-11-03T12:00:00-03:00",
                        "responsavel": "Marty",
                    },
                },
                name="reservar_sala",
                capabilities={},
                traceparent=tp,
            )
            self.assertEqual(st_mir2, 200)
            res_mir2 = resp_mir2["result"]
            self.assertEqual(res_mir2.get("resultType"), "complete")
            self.assertIs(res_mir2.get("isError"), True)
            self.assertIn(
                "Sem alternativas disponiveis no intervalo",
                res_mir2["content"][0]["text"],
            )

            # 7. Conferir que stderr registrou método, id e traceparent inclusive nas rejeições (-32021, -32602, -32020)
            stderr_txt = srv.read_stderr()
            self.assertIn(f"[mcp] method=tools/call id=6 traceparent={tp}", stderr_txt)
            self.assertIn("[mcp] method=tools/call id=retry-sem-meta", stderr_txt)
            self.assertIn(
                f"[mcp] method=tools/call id=retry-header-divergente traceparent={tp}",
                stderr_txt,
            )

    def test_decline_cancel_sem_mutacao_e_candidato_unico_t022(self) -> None:
        """T022: negociações reais independentes para decline e cancel sem mutação, e candidato único restrito no schema."""
        tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        salas_todas = [
            "sala-aquario",
            "sala-fusca",
            "sala-garagem",
            "sala-mirante",
            "sala-porao",
        ]

        with running_mcp_server() as srv:
            consumidor = ConsumidorMCPDireto(srv)
            consumidor.descobrir_e_ler_politica(traceparent=tp)

            # Snapshot amplo do dia 2026-11-03 em dois intervalos (14h-15h e 16h-17h)
            snap_14_15 = consumidor.snapshot_conflitos(
                salas_todas,
                "2026-11-03T14:00:00-03:00",
                "2026-11-03T15:00:00-03:00",
            )
            snap_16_17 = consumidor.snapshot_conflitos(
                salas_todas,
                "2026-11-03T16:00:00-03:00",
                "2026-11-03T17:00:00-03:00",
            )

            # 1. Negociação independente para decline usando o cenário do exemplo 11 (sala-fusca 16h-17h Jennifer)
            body_11_template = load_wire_request_body(EXEMPLO_11_RETRY_DECLINE)
            args_11 = body_11_template["params"]["arguments"]
            _, _, neg_decline = consumidor.iniciar_negociacao_conflito(
                sala=args_11["sala"],
                inicio=args_11["inicio"],
                fim=args_11["fim"],
                responsavel=args_11["responsavel"],
                req_id=11,
                traceparent=tp,
            )
            st_dec, resp_dec, req_dec = consumidor.enviar_retry(
                neg_decline,
                action="decline",
                retry_id=12,
                traceparent=tp,
            )
            self.assertEqual(st_dec, 200)
            self.assertNotEqual(req_dec["id"], neg_decline.initial_id)
            res_dec = resp_dec["result"]
            self.assertEqual(res_dec.get("resultType"), "complete")
            self.assertFalse(res_dec.get("isError", False))
            sc_dec = res_dec["structuredContent"]
            self.assertIs(sc_dec.get("reservado"), False)
            self.assertIsNone(sc_dec.get("reserva"))
            self.assertIsInstance(sc_dec.get("motivo"), str)
            self.assertTrue(sc_dec["motivo"].strip())
            self.assertEqual(json.loads(res_dec["content"][0]["text"]), sc_dec)

            # 2. Negociação independente para cancel no cenário 14h-15h (sala-garagem Marty)
            _, _, neg_cancel = consumidor.iniciar_negociacao_conflito(
                sala="sala-garagem",
                inicio="2026-11-03T14:00:00-03:00",
                fim="2026-11-03T15:00:00-03:00",
                responsavel="Marty",
                req_id=21,
                traceparent=tp,
            )
            st_can, resp_can, req_can = consumidor.enviar_retry(
                neg_cancel,
                action="cancel",
                retry_id=22,
                traceparent=tp,
            )
            self.assertEqual(st_can, 200)
            self.assertNotEqual(req_can["id"], neg_cancel.initial_id)
            res_can = resp_can["result"]
            self.assertEqual(res_can.get("resultType"), "complete")
            self.assertFalse(res_can.get("isError", False))
            sc_can = res_can["structuredContent"]
            self.assertIs(sc_can.get("reservado"), False)
            self.assertIsNone(sc_can.get("reserva"))
            self.assertIsInstance(sc_can.get("motivo"), str)
            self.assertTrue(sc_can["motivo"].strip())
            self.assertEqual(json.loads(res_can["content"][0]["text"]), sc_can)

            # Nenhuma reserva criada ou removida em ambos os intervalos após decline e cancel
            self.assertEqual(
                consumidor.snapshot_conflitos(
                    salas_todas,
                    "2026-11-03T14:00:00-03:00",
                    "2026-11-03T15:00:00-03:00",
                ),
                snap_14_15,
            )
            self.assertEqual(
                consumidor.snapshot_conflitos(
                    salas_todas,
                    "2026-11-03T16:00:00-03:00",
                    "2026-11-03T17:00:00-03:00",
                ),
                snap_16_17,
            )

            # 3. Candidato único: ocupar sala-fusca das 14h às 15h via reserva válida antes de pedir sala-garagem
            st_oc, resp_oc, _ = srv.request(
                "tools/call",
                {
                    "name": "reservar_sala",
                    "arguments": {
                        "sala": "sala-fusca",
                        "inicio": "2026-11-03T14:00:00-03:00",
                        "fim": "2026-11-03T15:00:00-03:00",
                        "responsavel": "Biff",
                    },
                },
                name="reservar_sala",
                traceparent=tp,
            )
            self.assertEqual(st_oc, 200)
            self.assertTrue(resp_oc["result"]["structuredContent"]["reservado"])

            _, _, neg_unica = consumidor.iniciar_negociacao_conflito(
                sala="sala-garagem",
                inicio="2026-11-03T14:00:00-03:00",
                fim="2026-11-03T15:00:00-03:00",
                responsavel="Marty",
                req_id=31,
                traceparent=tp,
            )
            prop_sala = (
                neg_unica.elicitation_request["params"]["requestedSchema"]["properties"]["sala"]
            )
            opcoes_unicas = prop_sala.get("enum") or (
                [prop_sala["const"]] if "const" in prop_sala else []
            )
            self.assertEqual(opcoes_unicas, ["sala-mirante"])

            # Tentar aceitar sala-fusca (não oferecida) ou sala-aquario (capacidade menor) falha sem reservar
            for sala_invalida in ("sala-fusca", "sala-aquario"):
                st_inv, resp_inv, _ = consumidor.enviar_retry(
                    neg_unica,
                    action="accept",
                    content={"sala": sala_invalida},
                    retry_id=f"32-{sala_invalida}",
                    traceparent=tp,
                )
                if "error" in resp_inv:
                    self.assertEqual(resp_inv["error"]["code"], -32602)
                else:
                    self.assertIs(resp_inv["result"].get("isError"), True)

            # Confirmar que sala-mirante continua livre e pode ser aceita na mesma negociação
            self.assertTrue(
                consumidor.consultar_disponibilidade(
                    "sala-mirante",
                    "2026-11-03T14:00:00-03:00",
                    "2026-11-03T15:00:00-03:00",
                )["livre"]
            )
            st_mir_ok, resp_mir_ok, _ = consumidor.enviar_retry(
                neg_unica,
                action="accept",
                content={"sala": "sala-mirante"},
                retry_id=33,
                traceparent=tp,
            )
            self.assertEqual(st_mir_ok, 200)
            self.assertEqual(
                resp_mir_ok["result"]["structuredContent"]["sala"],
                "sala-mirante",
            )


if __name__ == "__main__":
    unittest.main()
