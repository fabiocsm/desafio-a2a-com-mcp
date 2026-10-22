"""Coordenação do ciclo MRTR (Multi-Round-Trip Request) para reservar_sala."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mcp.server.mcpserver import Context
from mcp.shared.exceptions import MCPError
from mcp.types import (
    INVALID_PARAMS,
    MISSING_REQUIRED_CLIENT_CAPABILITY,
    ClientCapabilities,
    ElicitationCapability,
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitResult,
    FormElicitationCapability,
    InputRequiredResult,
    MissingRequiredClientCapabilityErrorData,
)

from ponte_mcp.modelos import ArgumentosReservaOriginais, PayloadRetomadaMRTR, ReservaOut
from ponte_mcp.salas import ErroDominio, EstadoSalas

ELICITATION_KEY_PADRAO = "__main__:escolha_de_sala"
MENSAGEM_CONFLITO_PADRAO = (
    "A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa."
)


def _erro_parametros_invalidos(mensagem: str) -> MCPError:
    """Cria erro JSON-RPC -32602 oficial sem expor segredos."""
    return MCPError(
        code=INVALID_PARAMS,
        message=mensagem,
        data={"reason": "invalid_request_state"},
    )


def _tem_campo_continuacao(ctx: Context[Any, Any]) -> tuple[bool, bool]:
    """Informa se requestState e inputResponses foram enviados na chamada atual."""
    raw_params: Mapping[str, Any] = {}
    try:
        req_ctx = ctx.request_context
        if isinstance(req_ctx.params, Mapping):
            raw_params = req_ctx.params
    except ValueError:
        raw_params = {}

    has_state = ctx.request_state is not None or "requestState" in raw_params
    has_responses = ctx.input_responses is not None or "inputResponses" in raw_params
    return has_state, has_responses


def verificar_capability_elicitation_form(
    ctx: Context[Any, Any],
    *,
    elicitation_key: str = ELICITATION_KEY_PADRAO,
) -> None:
    """Exige explicitamente clientCapabilities.elicitation.form no request corrente."""
    # Confere tanto o modelo tipado do contexto corrente quanto o envelope _meta bruto do request
    # para impedir qualquer inferência de chamada anterior ou aceitação de elicitation vazia/url-only.
    raw_has_form = True
    try:
        req_ctx = ctx.request_context
        if isinstance(req_ctx.params, Mapping):
            meta = req_ctx.params.get("_meta")
            if isinstance(meta, Mapping):
                raw_caps = meta.get("io.modelcontextprotocol/clientCapabilities")
                raw_elic = raw_caps.get("elicitation") if isinstance(raw_caps, Mapping) else None
                raw_form = raw_elic.get("form") if isinstance(raw_elic, Mapping) else None
                raw_has_form = isinstance(raw_form, Mapping)
            else:
                raw_has_form = False
    except ValueError:
        raw_has_form = True

    capabilities = ctx.client_capabilities
    elicitation = capabilities.elicitation if capabilities is not None else None
    if raw_has_form and elicitation is not None and elicitation.form is not None:
        return

    required = ClientCapabilities(
        elicitation=ElicitationCapability(form=FormElicitationCapability())
    )
    data = MissingRequiredClientCapabilityErrorData(required_capabilities=required)
    raise MCPError(
        code=MISSING_REQUIRED_CLIENT_CAPABILITY,
        message=(
            "Client did not declare the form elicitation capability "
            f"required by resolver {elicitation_key!r}"
        ),
        data=data.model_dump(by_alias=True, mode="json", exclude_none=True),
    )


def construir_schema_alternativas(alternativas: list[str]) -> dict[str, Any]:
    """Constrói requestedSchema plano para a escolha da sala alternativa."""
    return {
        "type": "object",
        "properties": {
            "sala": {
                "title": "Sala",
                "description": "Sala alternativa escolhida",
                "type": "string",
                "enum": list(alternativas),
            }
        },
        "required": ["sala"],
    }


def emitir_input_required(
    *,
    ctx: Context[Any, Any],
    sala: str,
    inicio: str,
    fim: str,
    responsavel: str,
    alternativas: list[str],
    politica: str,
    elicitation_key: str = ELICITATION_KEY_PADRAO,
) -> InputRequiredResult:
    """Confere capability form e emite InputRequiredResult com uma única pergunta e payload selado pelo SDK."""
    verificar_capability_elicitation_form(ctx, elicitation_key=elicitation_key)

    payload = PayloadRetomadaMRTR(
        schema_version=1,
        tool_name="reservar_sala",
        original_arguments=ArgumentosReservaOriginais(
            sala=sala,
            inicio=inicio,
            fim=fim,
            responsavel=responsavel,
        ),
        alternatives=list(alternativas),
        elicitation_key=elicitation_key,
        politica=politica,
    )

    elicit_req = ElicitRequest(
        params=ElicitRequestFormParams(
            mode="form",
            message=MENSAGEM_CONFLITO_PADRAO,
            requested_schema=construir_schema_alternativas(alternativas),
        )
    )
    return InputRequiredResult(
        input_requests={elicitation_key: elicit_req},
        request_state=payload.serializar(),
    )


def validar_continuacao(
    ctx: Context[Any, Any],
) -> tuple[PayloadRetomadaMRTR, ElicitResult]:
    """Valida presença simultânea de requestState/inputResponses, payload e correlação da chave."""
    raw_state = ctx.request_state
    responses = ctx.input_responses
    if raw_state is None or responses is None:
        raise _erro_parametros_invalidos(
            "Invalid continuation: both requestState and inputResponses are required"
        )

    try:
        payload = PayloadRetomadaMRTR.reconstruir(raw_state)
    except ValueError as err:
        raise _erro_parametros_invalidos(str(err)) from err

    if not isinstance(responses, Mapping) or len(responses) != 1:
        raise _erro_parametros_invalidos(
            "Invalid inputResponses: expected a single entry matching the sealed elicitation key"
        )

    if payload.elicitation_key not in responses:
        raise _erro_parametros_invalidos(
            "Invalid inputResponses: response key does not match the sealed elicitation key"
        )

    resposta = responses[payload.elicitation_key]
    if not isinstance(resposta, ElicitResult):
        raise _erro_parametros_invalidos(
            "Invalid inputResponses: expected an elicitation response"
        )

    return payload, resposta


def executar_reservar_sala(
    *,
    dominio: EstadoSalas,
    sala: str,
    inicio: str,
    fim: str,
    responsavel: str,
    ctx: Context[Any, Any],
) -> ReservaOut | InputRequiredResult:
    """Coordena chamada inicial ou retomada MRTR de reservar_sala sem estado de sessão no servidor."""
    has_state, has_responses = _tem_campo_continuacao(ctx)
    if has_state or has_responses:
        return _processar_retomada(
            dominio=dominio,
            sala=sala,
            inicio=inicio,
            fim=fim,
            responsavel=responsavel,
            ctx=ctx,
        )

    return _processar_chamada_inicial(
        dominio=dominio,
        sala=sala,
        inicio=inicio,
        fim=fim,
        responsavel=responsavel,
        ctx=ctx,
    )


def _processar_chamada_inicial(
    *,
    dominio: EstadoSalas,
    sala: str,
    inicio: str,
    fim: str,
    responsavel: str,
    ctx: Context[Any, Any],
) -> ReservaOut | InputRequiredResult:
    """Executa chamada inicial de reservar_sala: reserva direta se livre ou emite input_required se houver alternativas."""
    sala_obj, dt_inicio, dt_fim = dominio.validar_sala_e_intervalo(sala, inicio, fim)
    conflitos = dominio.calcular_conflitos(sala_obj.id, dt_inicio, dt_fim)
    if not conflitos:
        return dominio.reservar_sala_livre(
            sala=sala,
            inicio=inicio,
            fim=fim,
            responsavel=responsavel,
        )

    alternativas = dominio.selecionar_alternativas(
        sala=sala,
        inicio=inicio,
        fim=fim,
    )
    return emitir_input_required(
        ctx=ctx,
        sala=sala,
        inicio=inicio,
        fim=fim,
        responsavel=responsavel,
        alternativas=alternativas,
        politica=dominio.versao_politica(),
    )


def _processar_retomada(
    *,
    dominio: EstadoSalas,
    sala: str,
    inicio: str,
    fim: str,
    responsavel: str,
    ctx: Context[Any, Any],
) -> ReservaOut:
    """Valida e executa retomada MRTR de reservar_sala a partir do estado autenticado."""
    payload, resposta = validar_continuacao(ctx)
    orig = payload.original_arguments
    if (
        sala != orig.sala
        or inicio != orig.inicio
        or fim != orig.fim
        or responsavel != orig.responsavel
    ):
        raise _erro_parametros_invalidos(
            "Invalid continuation: request arguments do not match sealed original arguments"
        )

    if resposta.action == "accept":
        content = resposta.content
        if not isinstance(content, Mapping) or set(content.keys()) != {"sala"}:
            raise ErroDominio(
                "Resposta de elicitation invalida: content deve conter exclusivamente a chave 'sala'"
            )
        sala_escolhida = content.get("sala")
        if not isinstance(sala_escolhida, str) or sala_escolhida not in payload.alternatives:
            raise ErroDominio(
                f"Escolha de sala fora do schema permitido: {sala_escolhida!r}"
            )
        return dominio.confirmar_reserva_alternativa(
            sala_original=orig.sala,
            sala_escolhida=sala_escolhida,
            inicio=orig.inicio,
            fim=orig.fim,
            responsavel=orig.responsavel,
            alternativas_oferecidas=payload.alternatives,
            politica=payload.politica,
        )

    if resposta.action in ("decline", "cancel"):
        motivo = "recusado" if resposta.action == "decline" else "cancelado"
        return ReservaOut(
            reserva=None,
            reservado=False,
            sala=None,
            inicio=None,
            fim=None,
            responsavel=None,
            politica=None,
            motivo=motivo,
        )

    raise _erro_parametros_invalidos(
        f"Invalid inputResponses: unsupported elicitation action {resposta.action!r}"
    )
