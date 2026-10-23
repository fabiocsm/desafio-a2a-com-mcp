"""Aplicação ASGI, AgentCard e rotas oficiais A2A v1.0 do agente."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import os

from a2a.server.context import ServerCallContext
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.common import DefaultServerCallContextBuilder
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.types import a2a_pb2
from a2a.utils import constants
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route

from ponte_agente.handler import AgenteRequestHandler
from ponte_agente.mcp_host import DEFAULT_MCP_URL, MCPHost
from ponte_agente.tasks import TaskStore

DEFAULT_AGENTE_HOST = "127.0.0.1"
DEFAULT_AGENTE_PORT = 7300
DEFAULT_A2A_BASE_URL = "http://127.0.0.1:7300"


@dataclass(frozen=True, slots=True)
class AgenteSettings:
    """Configurações de rede e integração do processo do agente."""

    host: str = DEFAULT_AGENTE_HOST
    port: int = DEFAULT_AGENTE_PORT
    mcp_url: str = DEFAULT_MCP_URL
    a2a_base_url: str = DEFAULT_A2A_BASE_URL

    @classmethod
    def from_env(cls) -> AgenteSettings:
        host = os.environ.get("AGENTE_HOST", DEFAULT_AGENTE_HOST).strip() or DEFAULT_AGENTE_HOST
        port_raw = os.environ.get("AGENTE_PORT", str(DEFAULT_AGENTE_PORT)).strip()
        port = int(port_raw) if port_raw else DEFAULT_AGENTE_PORT
        mcp_url = os.environ.get("MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL
        default_base = (
            f"http://{host}:{port}"
            if ("AGENTE_HOST" in os.environ or "AGENTE_PORT" in os.environ)
            else DEFAULT_A2A_BASE_URL
        )
        a2a_base_url = os.environ.get("A2A_BASE_URL", default_base).strip() or default_base
        return cls(
            host=host,
            port=port,
            mcp_url=mcp_url,
            a2a_base_url=a2a_base_url.rstrip("/"),
        )


class StarterProfileContextBuilder(DefaultServerCallContextBuilder):
    """ServerCallContextBuilder público: aplica versão 1.0 somente quando A2A-Version está ausente."""

    def build(self, request: Request) -> ServerCallContext:
        context = super().build(request)
        raw_headers = dict(request.headers)
        lower_headers = {k.lower(): v for k, v in raw_headers.items()}
        version_key_lower = constants.VERSION_HEADER.lower()

        if version_key_lower not in lower_headers:
            raw_headers[version_key_lower] = constants.PROTOCOL_VERSION_1_0
        else:
            explicit = lower_headers[version_key_lower].strip()
            raw_headers[version_key_lower] = explicit if explicit else "invalid-empty-version"

        context.state["headers"] = raw_headers
        raw_traceparent = lower_headers.get("traceparent")
        context.state["traceparent"] = (
            raw_traceparent.strip() if raw_traceparent and raw_traceparent.strip() else None
        )
        return context


def build_agent_card(settings: AgenteSettings) -> a2a_pb2.AgentCard:
    """Constrói o AgentCard A2A v1.0 público conforme o exemplo 07 do starter."""
    rpc_endpoint_url = f"{settings.a2a_base_url.rstrip('/')}/a2a"
    return a2a_pb2.AgentCard(
        name="Central de Salas",
        description="Reserva salas de reuniao da Hill Valley Tech.",
        provider=a2a_pb2.AgentProvider(
            organization="Hill Valley Tech",
            url="https://hillvalley.example",
        ),
        version="1.0.0",
        supported_interfaces=[
            a2a_pb2.AgentInterface(
                url=rpc_endpoint_url,
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            )
        ],
        capabilities=a2a_pb2.AgentCapabilities(
            streaming=False,
            push_notifications=False,
            extended_agent_card=False,
        ),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            a2a_pb2.AgentSkill(
                id="reservar-sala",
                name="Reservar sala",
                description="Reserva uma sala em um intervalo. Se houver conflito, pergunta qual alternativa usar.",
                tags=["salas", "agenda"],
                input_modes=["text/plain"],
                output_modes=["text/plain"],
                examples=[
                    "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty"
                ],
            )
        ],
    )


def create_app(
    settings: AgenteSettings | None = None,
    *,
    mcp_host: MCPHost | None = None,
    task_store: TaskStore | None = None,
    request_handler: AgenteRequestHandler | None = None,
) -> Starlette:
    """Cria a aplicação Starlette do agente com rotas A2A v1.0 e gerenciamento exclusivo do cliente MCP."""
    cfg = settings or AgenteSettings.from_env()
    host_client = mcp_host or MCPHost(cfg.mcp_url)
    store = task_store or TaskStore()
    handler = request_handler or AgenteRequestHandler(mcp_host=host_client, task_store=store)
    agent_card = build_agent_card(cfg)
    context_builder = StarterProfileContextBuilder()

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        app.state.settings = cfg
        app.state.mcp_host = host_client
        app.state.task_store = store
        app.state.request_handler = handler
        await host_client.open()
        try:
            yield
        finally:
            await host_client.close()

    routes: list[Route] = [
        *create_agent_card_routes(agent_card, card_url="/.well-known/agent-card.json"),
        *create_jsonrpc_routes(
            handler,
            rpc_url="/a2a",
            context_builder=context_builder,
            enable_v0_3_compat=False,
        ),
    ]
    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.settings = cfg
    app.state.mcp_host = host_client
    app.state.task_store = store
    app.state.request_handler = handler
    return app
