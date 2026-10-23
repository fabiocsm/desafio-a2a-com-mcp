"""Tradução entre InputRequiredResult do MCP e a pausa/retomada A2A.

O agente não abre o requestState, não reordena alternativas e não decide a reserva.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal, Mapping

import mcp_types as types

from ponte_agente.tasks import OriginalArguments, PendingContinuation

_ESCOLHA_RE = re.compile(r"^escolha=(\S+)$")


class PonteFormatoError(ValueError):
    """O InputRequiredResult não tem o formulário único esperado pela ponte."""


@dataclass(frozen=True, slots=True)
class ClientDecision:
    """Decisão do cliente: escolha com sala ou recusa sem sala."""

    tipo: Literal["escolha", "recusa"]
    sala: str | None = None

    def __post_init__(self) -> None:
        if self.tipo == "escolha":
            if not isinstance(self.sala, str) or not self.sala:
                raise ValueError("escolha exige sala")
            return
        if self.tipo == "recusa":
            if self.sala is not None:
                raise ValueError("recusa nao tem sala")
            return
        raise ValueError("tipo de decisao invalido")


def pause_text_for(alternatives: list[str]) -> str:
    """Monta a linha pública exatamente como `alternativas: id1, id2`."""
    return "alternativas: " + ", ".join(alternatives)


def continuation_from_input_required(
    result: types.InputRequiredResult,
    *,
    tool_name: str,
    original_arguments: Mapping[str, str],
) -> PendingContinuation:
    """Lê uma única elicitation form e guarda chave, ordem e token sem interpretá-los."""
    if not isinstance(tool_name, str) or not tool_name:
        raise PonteFormatoError("nome da tool ausente na chamada original")

    try:
        arguments = OriginalArguments(
            sala=original_arguments["sala"],
            inicio=original_arguments["inicio"],
            fim=original_arguments["fim"],
            responsavel=original_arguments["responsavel"],
        )
    except (KeyError, TypeError) as exc:
        raise PonteFormatoError("argumentos originais incompletos") from exc

    requests = result.input_requests
    if not isinstance(requests, dict) or len(requests) != 1:
        raise PonteFormatoError("era esperada uma unica pergunta de elicitation")

    key, request = next(iter(requests.items()))
    if not isinstance(key, str) or not key:
        raise PonteFormatoError("chave de elicitation ausente")
    if getattr(request, "method", None) != "elicitation/create":
        raise PonteFormatoError("pergunta MCP nao e elicitation/create")

    params = getattr(request, "params", None)
    if getattr(params, "mode", None) != "form":
        raise PonteFormatoError("elicitation nao esta em mode form")

    schema = getattr(params, "requested_schema", None)
    alternatives = _alternatives_from_schema(schema)
    request_state = result.request_state
    if not isinstance(request_state, str) or request_state == "":
        raise PonteFormatoError("requestState ausente")

    return PendingContinuation(
        tool_name=tool_name,
        original_arguments=arguments,
        elicitation_key=key,
        ordered_alternatives=tuple(alternatives),
        pause_text=pause_text_for(alternatives),
        request_state=request_state,
    )


def interpret_client_decision(text: str) -> ClientDecision | None:
    """Interpreta `escolha=<id>` ou `escolha=recusar`. Texto fora do formato não é decisão."""
    if not isinstance(text, str):
        return None
    match = _ESCOLHA_RE.match(text.strip())
    if match is None:
        return None
    value = match.group(1)
    if value == "recusar":
        return ClientDecision(tipo="recusa")
    return ClientDecision(tipo="escolha", sala=value)


def decision_is_acceptable(decision: ClientDecision, pending: PendingContinuation) -> bool:
    """Aceita recusa ou sala presente na lista recebida, sem recalcular disponibilidade."""
    if decision.tipo == "recusa":
        return decision.sala is None
    return isinstance(decision.sala, str) and decision.sala in pending.ordered_alternatives


def build_retry_input_responses(
    pending: PendingContinuation,
    decision: ClientDecision,
) -> dict[str, types.ElicitResult]:
    """Monta inputResponses na chave original. A sala escolhida vai em content, não nos arguments."""
    if decision.tipo == "recusa":
        response = types.ElicitResult(action="decline")
    else:
        response = types.ElicitResult(action="accept", content={"sala": decision.sala})
    return {pending.elicitation_key: response}


def _alternatives_from_schema(schema: Any) -> list[str]:
    """Extrai a ordem de enum, ou a única opção const, do schema plano da propriedade sala."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise PonteFormatoError("requestedSchema nao e um objeto plano")
    properties = schema.get("properties")
    if not isinstance(properties, dict) or "sala" not in properties:
        raise PonteFormatoError("requestedSchema nao declara sala")
    required = schema.get("required")
    if not isinstance(required, list) or "sala" not in required:
        raise PonteFormatoError("sala nao e obrigatoria no schema")

    sala_schema = properties.get("sala")
    if not isinstance(sala_schema, dict) or sala_schema.get("type") != "string":
        raise PonteFormatoError("sala nao e string")

    enum_values = sala_schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        if not all(isinstance(item, str) and item for item in enum_values):
            raise PonteFormatoError("enum de sala invalido")
        return list(enum_values)

    if "const" in sala_schema:
        const_value = sala_schema.get("const")
        if not isinstance(const_value, str) or not const_value:
            raise PonteFormatoError("const de sala invalido")
        return [const_value]

    raise PonteFormatoError("schema de sala sem enum nem const")
