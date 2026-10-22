"""Construção do MCPServer oficial e da aplicação ASGI do servidor de salas."""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.request_state import RequestStateSecurity
from starlette.types import ASGIApp

from ponte_mcp.entrada import EntradaMCPMiddleware
from ponte_mcp.modelos import Disponibilidade, ListaDeSalas, ReservaOut
from ponte_mcp.salas import ESTADO_PROCESSO, ErroDominio, EstadoSalas

SERVER_NAME = "ponte-salas"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7301
DEFAULT_STATE_TTL = 600.0


class ErroConfiguracaoSegredo(RuntimeError):
    """Erro de validação da chave REQUEST_STATE_SECRET no startup."""


def ler_segredo_estado(valor_env: str | None = None) -> bytes:
    """Lê e valida REQUEST_STATE_SECRET em hexadecimal (>= 32 bytes) sem expor o valor."""
    bruto = valor_env if valor_env is not None else os.environ.get("REQUEST_STATE_SECRET")
    if bruto is None or not bruto.strip():
        raise ErroConfiguracaoSegredo(
            "REQUEST_STATE_SECRET ausente: defina uma chave hexadecimal com pelo menos 32 bytes."
        )
    try:
        decodificado = bytes.fromhex(bruto.strip())
    except ValueError as err:
        raise ErroConfiguracaoSegredo(
            "REQUEST_STATE_SECRET inválido: o valor deve estar em hexadecimal válido."
        ) from err

    if len(decodificado) < 32:
        raise ErroConfiguracaoSegredo(
            f"REQUEST_STATE_SECRET insuficiente: esperados pelo menos 32 bytes, recebidos {len(decodificado)}."
        )
    return decodificado


def criar_mcp_server(
    estado: EstadoSalas | None = None,
    *,
    secret_hex: str | None = None,
) -> MCPServer:
    """Cria instância configurada do MCPServer oficial com nome estável `ponte-salas`."""
    dominio = estado or ESTADO_PROCESSO
    secret_bytes = ler_segredo_estado(secret_hex)
    security = RequestStateSecurity(
        keys=[secret_bytes],
        ttl=DEFAULT_STATE_TTL,
        audience=SERVER_NAME,
    )
    server = MCPServer(
        name=SERVER_NAME,
        version="1.0.0",
        request_state_security=security,
    )

    @server.tool(
        name="listar_salas",
        description="Lista todas as salas com capacidade e recursos.",
    )
    def listar_salas() -> ListaDeSalas:
        return dominio.listar_salas()

    @server.tool(
        name="consultar_disponibilidade",
        description="Diz se uma sala esta livre no intervalo, e quais reservas conflitam.",
    )
    def consultar_disponibilidade(sala: str, inicio: str, fim: str) -> Disponibilidade:
        try:
            return dominio.consultar_disponibilidade(sala=sala, inicio=inicio, fim=fim)
        except (ErroDominio, ValueError) as err:
            raise ToolError(str(err)) from err

    @server.tool(
        name="reservar_sala",
        description="Reserva uma sala. Se o intervalo estiver ocupado, pergunta qual alternativa usar.",
    )
    def reservar_sala(sala: str, inicio: str, fim: str, responsavel: str) -> ReservaOut:
        try:
            return dominio.reservar_sala_livre(
                sala=sala,
                inicio=inicio,
                fim=fim,
                responsavel=responsavel,
            )
        except (ErroDominio, ValueError) as err:
            raise ToolError(str(err)) from err

    @server.resource(
        "politica://uso",
        name="politica-de-uso",
        description="Politica de uso das salas de reuniao da Hill Valley Tech.",
        mime_type="text/markdown",
    )
    def ler_politica_uso() -> str:
        return dominio.ler_politica_texto()

    return server


def criar_asgi_app(
    estado: EstadoSalas | None = None,
    *,
    host: str = DEFAULT_HOST,
    secret_hex: str | None = None,
) -> ASGIApp:
    """Cria a aplicação Streamable HTTP oficial envolvida pela observação/guarda ASGI."""
    server = criar_mcp_server(estado=estado, secret_hex=secret_hex)
    sdk_app = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        host=host,
    )
    return EntradaMCPMiddleware(sdk_app)
