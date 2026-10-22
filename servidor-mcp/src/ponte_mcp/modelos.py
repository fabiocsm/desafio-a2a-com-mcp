"""Modelos de domínio e contratos de entrada/saída do servidor MCP."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


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
