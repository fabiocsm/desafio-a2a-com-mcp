"""Modelos de domínio e contratos de entrada/saída do servidor MCP."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class SalaOut(BaseModel):
    """Representação de uma sala de reunião no catálogo."""

    id: str
    nome: str
    capacidade: int
    recursos: list[str]


Sala = SalaOut


class ListaDeSalas(BaseModel):
    """Contrato de saída da tool listar_salas."""

    salas: list[SalaOut]


class Reserva(BaseModel):
    """Registro em memória de uma reserva de sala."""

    id: str
    sala: str
    inicio: datetime
    fim: datetime
    responsavel: str


class Politica(BaseModel):
    """Política de uso carregada do arquivo original."""

    texto: str
    versao: str


Política = Politica


class ConflitoOut(BaseModel):
    """Projeção de reserva conflitante em consultar_disponibilidade."""

    id: str
    inicio: str
    fim: str
    responsavel: str


Conflito = ConflitoOut


class Disponibilidade(BaseModel):
    """Contrato de saída da tool consultar_disponibilidade."""

    sala: str
    livre: bool
    conflitos: list[ConflitoOut]


class ReservaOut(BaseModel):
    """Contrato de saída completo da tool reservar_sala."""

    reserva: str | None = None
    reservado: bool = True
    sala: str | None = None
    inicio: str | None = None
    fim: str | None = None
    responsavel: str | None = None
    politica: str | None = None
    motivo: str | None = None


class ArgumentosReservaOriginais(BaseModel):
    """Argumentos originais selados na emissão do MRTR (sala, inicio, fim, responsavel originais)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    sala: str = Field(min_length=1, description="sala original solicitada")
    inicio: str = Field(min_length=1, description="inicio original solicitado")
    fim: str = Field(min_length=1, description="fim original solicitado")
    responsavel: str = Field(min_length=1, description="responsavel original solicitado")

    @model_validator(mode="after")
    def _validar_campos_nao_vazios(self) -> ArgumentosReservaOriginais:
        for nome in ("sala", "inicio", "fim", "responsavel"):
            valor = getattr(self, nome)
            if not isinstance(valor, str) or not valor.strip():
                raise ValueError(f"Campo original_arguments.{nome} inválido ou vazio")
        return self


class PayloadRetomadaMRTR(BaseModel):
    """Payload interno serializado em requestState (data-model.md)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: int = Field(
        default=1,
        description="inteiro fixo 1, validado ao reconstruir",
    )
    tool_name: str = Field(
        default="reservar_sala",
        description="reservar_sala",
    )
    original_arguments: ArgumentosReservaOriginais = Field(
        description="sala, inicio, fim, responsavel originais",
    )
    alternatives: list[str] = Field(
        min_length=1,
        max_length=3,
        description="lista ordenada de até três ids oferecidos",
    )
    elicitation_key: str = Field(
        min_length=1,
        description="identificador atribuído pelo servidor, criado ao emitir a pergunta",
    )
    politica: str = Field(
        min_length=1,
        description="versão extraída da política original",
    )

    @model_validator(mode="after")
    def _validar_invariantes(self) -> PayloadRetomadaMRTR:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("schema_version inválido: esperado inteiro fixo 1")
        if self.tool_name != "reservar_sala":
            raise ValueError("tool_name inválido: esperado 'reservar_sala'")
        if not (1 <= len(self.alternatives) <= 3):
            raise ValueError("alternatives deve conter entre 1 e 3 ids")
        if any(not isinstance(alt, str) or not alt.strip() for alt in self.alternatives):
            raise ValueError("alternatives contém id inválido ou vazio")
        if len(set(self.alternatives)) != len(self.alternatives):
            raise ValueError("alternatives contém ids duplicados")
        if not self.elicitation_key.strip():
            raise ValueError("elicitation_key vazio")
        if not self.politica.strip():
            raise ValueError("politica vazia")
        return self

    def serializar(self) -> str:
        """Serializa o payload para JSON compacto de dados puros."""
        return json.dumps(
            self.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def reconstruir(cls, raw_state: str) -> PayloadRetomadaMRTR:
        """Reconstrói e valida estritamente o payload a partir do JSON autenticado pelo SDK."""
        if not isinstance(raw_state, str) or not raw_state.strip():
            raise ValueError("requestState vazio ou não textual")
        try:
            decoded: Any = json.loads(raw_state)
        except ValueError as err:
            raise ValueError("requestState não contém JSON válido") from err
        if not isinstance(decoded, dict):
            raise ValueError("requestState deve representar um objeto JSON")
        try:
            return cls.model_validate(decoded, strict=True)
        except ValidationError as err:
            raise ValueError(f"Payload de retomada incompatível: {err}") from err
