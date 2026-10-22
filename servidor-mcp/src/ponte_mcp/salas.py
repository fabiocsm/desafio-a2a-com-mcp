"""Domínio de salas, política de uso e reservas em memória do servidor MCP."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re

from ponte_mcp.modelos import (
    ConflitoOut,
    Disponibilidade,
    ListaDeSalas,
    Politica,
    Reserva,
    ReservaOut,
    SalaOut,
)

OFFSET_SAO_PAULO = timezone(timedelta(hours=-3))
DADOS_DIR = Path(__file__).resolve().parents[3] / "dados"

ERRO_JANELA_MSG = "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"
ERRO_DURACAO_MSG = "Duracao acima do limite: a politica permite no maximo 2 horas"
ERRO_INTERVALO_MSG = "Intervalo invalido: fim deve ser posterior a inicio"
ERRO_SEM_ALTERNATIVA_MSG = "Sem alternativas disponiveis no intervalo"


def erro_sala_inexistente(sala_id: str) -> str:
    """Retorna a mensagem exata de erro para sala inexistente."""
    return f"Sala inexistente: {sala_id}"


class ErroDominio(ValueError):
    """Erro de negócio nas regras de sala ou política de uso."""


def _extrair_versao_politica(texto: str) -> str:
    primeira_linha = texto.splitlines()[0].strip() if texto else ""
    prefixo = "versao:"
    if not primeira_linha.lower().startswith(prefixo):
        raise ValueError("Primeira linha da política não contém 'versao:'")
    versao = primeira_linha[len(prefixo) :].strip()
    if not versao:
        raise ValueError("Versão da política vazia")
    return versao


def _parse_iso_com_tz(valor: str) -> datetime:
    dt = datetime.fromisoformat(valor)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"Data/hora sem timezone explícito: {valor}")
    return dt.astimezone(OFFSET_SAO_PAULO)


class EstadoSalas:
    """Mantém catálogo, política e coleção de reservas em memória."""

    def __init__(
        self,
        salas: list[SalaOut],
        reservas: list[Reserva],
        politica: Politica,
    ) -> None:
        if len(salas) != 5:
            raise ValueError(f"Catálogo inválido: esperadas 5 salas, encontradas {len(salas)}")
        ids_salas = [s.id for s in salas]
        if len(set(ids_salas)) != len(ids_salas):
            raise ValueError("Catálogo inválido: IDs de salas duplicados")

        self._salas: list[SalaOut] = list(salas)
        self._salas_por_id: dict[str, SalaOut] = {s.id: s for s in salas}
        self._politica: Politica = politica

        ids_reservas: set[str] = set()
        max_num = 0
        reservas_normalizadas: list[Reserva] = []
        for r in reservas:
            if r.sala not in self._salas_por_id:
                raise ValueError(f"Reserva inicial referencia sala inexistente: {r.sala}")
            if r.id in ids_reservas:
                raise ValueError(f"ID de reserva inicial duplicado: {r.id}")
            ids_reservas.add(r.id)
            m = re.fullmatch(r"res-(\d+)", r.id)
            if m:
                max_num = max(max_num, int(m.group(1)))
            reservas_normalizadas.append(
                Reserva(
                    id=r.id,
                    sala=r.sala,
                    inicio=r.inicio.astimezone(OFFSET_SAO_PAULO),
                    fim=r.fim.astimezone(OFFSET_SAO_PAULO),
                    responsavel=r.responsavel,
                )
            )

        self._reservas: list[Reserva] = reservas_normalizadas
        self._ids_reservas: set[str] = ids_reservas
        self._proximo_numero: int = max_num + 1

    @classmethod
    def carregar(cls, dados_dir: Path = DADOS_DIR) -> EstadoSalas:
        """Carrega salas, reservas iniciais e política a partir de dados/."""
        salas_raw = json.loads((dados_dir / "salas.json").read_text(encoding="utf-8"))
        salas = [SalaOut.model_validate(item) for item in salas_raw]

        texto_politica = (dados_dir / "politica-de-uso.md").read_text(encoding="utf-8")
        politica = Politica(
            texto=texto_politica,
            versao=_extrair_versao_politica(texto_politica),
        )

        reservas_raw = json.loads((dados_dir / "reservas.json").read_text(encoding="utf-8"))
        reservas = [
            Reserva(
                id=item["id"],
                sala=item["sala"],
                inicio=_parse_iso_com_tz(item["inicio"]),
                fim=_parse_iso_com_tz(item["fim"]),
                responsavel=item["responsavel"],
            )
            for item in reservas_raw
        ]
        return cls(salas=salas, reservas=reservas, politica=politica)

    def proximo_id_reserva(self) -> str:
        """Gera um novo ID de reserva sem colisão com os existentes."""
        while True:
            candidato = f"res-{self._proximo_numero:04d}"
            self._proximo_numero += 1
            if candidato not in self._ids_reservas:
                self._ids_reservas.add(candidato)
                return candidato

    def listar_salas(self) -> ListaDeSalas:
        """Retorna cópia do catálogo das cinco salas sem mutar o estado."""
        return ListaDeSalas(salas=[s.model_copy(deep=True) for s in self._salas])

    def ler_politica_texto(self) -> str:
        """Retorna o texto integral de dados/politica-de-uso.md."""
        return self._politica.texto

    def versao_politica(self) -> str:
        """Retorna a versão extraída da primeira linha da política."""
        return self._politica.versao

    def validar_sala_e_intervalo(
        self,
        sala: str,
        inicio: str,
        fim: str,
    ) -> tuple[SalaOut, datetime, datetime]:
        """Valida sala e intervalo na ordem: formato -> sala -> intervalo -> janela -> duração."""
        dt_inicio = _parse_iso_com_tz(inicio)
        dt_fim = _parse_iso_com_tz(fim)

        sala_obj = self._salas_por_id.get(sala)
        if sala_obj is None:
            raise ErroDominio(erro_sala_inexistente(sala))

        if dt_fim <= dt_inicio:
            raise ErroDominio(ERRO_INTERVALO_MSG)

        abertura = dt_inicio.replace(hour=8, minute=0, second=0, microsecond=0)
        fechamento = dt_inicio.replace(hour=20, minute=0, second=0, microsecond=0)
        if (
            dt_inicio.date() != dt_fim.date()
            or dt_inicio < abertura
            or dt_fim > fechamento
        ):
            raise ErroDominio(ERRO_JANELA_MSG)

        if (dt_fim - dt_inicio) > timedelta(hours=2):
            raise ErroDominio(ERRO_DURACAO_MSG)

        return sala_obj, dt_inicio, dt_fim

    def calcular_conflitos(
        self,
        sala_id: str,
        dt_inicio: datetime,
        dt_fim: datetime,
    ) -> list[ConflitoOut]:
        """Retorna projeções das reservas da mesma sala onde inicio < reserva.fim e fim > reserva.inicio."""
        conflitos: list[ConflitoOut] = []
        for r in self._reservas:
            if r.sala == sala_id and dt_inicio < r.fim and dt_fim > r.inicio:
                conflitos.append(
                    ConflitoOut(
                        id=r.id,
                        inicio=r.inicio.isoformat(timespec="seconds"),
                        fim=r.fim.isoformat(timespec="seconds"),
                        responsavel=r.responsavel,
                    )
                )
        return conflitos

    def consultar_disponibilidade(
        self,
        sala: str,
        inicio: str,
        fim: str,
    ) -> Disponibilidade:
        """Valida sala/intervalo e informa disponibilidade e conflitos sem mutar estado."""
        sala_obj, dt_inicio, dt_fim = self.validar_sala_e_intervalo(sala, inicio, fim)
        conflitos = self.calcular_conflitos(sala_obj.id, dt_inicio, dt_fim)
        return Disponibilidade(
            sala=sala_obj.id,
            livre=(len(conflitos) == 0),
            conflitos=conflitos,
        )

    def reservar_sala_livre(
        self,
        sala: str,
        inicio: str,
        fim: str,
        responsavel: str,
    ) -> ReservaOut:
        """Valida sala/intervalo e confirma reserva em horário livre antes de retornar."""
        sala_obj, dt_inicio, dt_fim = self.validar_sala_e_intervalo(sala, inicio, fim)
        conflitos = self.calcular_conflitos(sala_obj.id, dt_inicio, dt_fim)
        if conflitos:
            raise NotImplementedError("Negociação MRTR sob conflito pertence à feature 002")

        novo_id = self.proximo_id_reserva()
        inicio_iso = dt_inicio.isoformat(timespec="seconds")
        fim_iso = dt_fim.isoformat(timespec="seconds")
        nova_reserva = Reserva(
            id=novo_id,
            sala=sala_obj.id,
            inicio=dt_inicio,
            fim=dt_fim,
            responsavel=responsavel,
        )
        self._reservas.append(nova_reserva)
        return ReservaOut(
            reserva=novo_id,
            reservado=True,
            sala=sala_obj.id,
            inicio=inicio_iso,
            fim=fim_iso,
            responsavel=responsavel,
            politica=self._politica.versao,
            motivo=None,
        )


ESTADO_PROCESSO: EstadoSalas = EstadoSalas.carregar()
