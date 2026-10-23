"""Host MCP moderno (SDK v2.3.0, revisão 2026-07-28) para o agente A2A."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from mcp import Client
from mcp.client.session import ClientRequestContext, ClientSession, ElicitationFnT
import mcp_types as types

from ponte_agente.tasks import RequestTrace

DEFAULT_MCP_URL = "http://127.0.0.1:7301/mcp"
MCP_PROTOCOL_VERSION = "2026-07-28"
POLICY_RESOURCE_URI = "politica://uso"
RESERVATION_TOOL_NAME = "reservar_sala"
REQUIRED_RESERVATION_ARGS = ("sala", "inicio", "fim", "responsavel")
MAX_TOOL_LIST_PAGES = 100

CLIENT_INFO = types.Implementation(name="agente-central-de-salas", version="1.0.0")


class DefensiveElicitationCalledError(RuntimeError):
    """Erro disparado caso o callback de elicitation seja acionado automaticamente."""


class MCPDiscoveryError(RuntimeError):
    """Erro disparado quando a descoberta MCP ou leitura da política falha."""


@dataclass(frozen=True, slots=True)
class HostSnapshot:
    """Catálogo de tools descoberto e política/versão lidas explicitamente do servidor MCP."""

    tools_by_name: dict[str, types.Tool]
    reservation_tool: types.Tool
    policy_text: str
    policy_version: str


async def defensive_elicitation_callback(
    context: ClientRequestContext,
    params: types.ElicitRequestParams,
) -> types.ElicitResult | types.ErrorData:
    """Callback defensivo: garante anúncio de elicitation sem jamais auto-responder."""
    raise DefensiveElicitationCalledError(
        "Callback de elicitation não deve ser executado automaticamente; "
        "o agente deve receber InputRequiredResult cru via session.call_tool(..., allow_input_required=True)."
    )


def build_trace_meta(trace: RequestTrace | str | None = None) -> types.RequestParamsMeta | None:
    """Monta RequestParamsMeta por operação sem mutar estado global do cliente."""
    if trace is None:
        return None
    if isinstance(trace, RequestTrace):
        meta_dict = trace.to_mcp_meta()
    else:
        cleaned = trace.strip()
        meta_dict = RequestTrace(cleaned).to_mcp_meta() if cleaned else {}
    if not meta_dict:
        return None
    return cast(types.RequestParamsMeta, dict(meta_dict))


def extract_policy_version(policy_text: str) -> str:
    """Extrai a versão da política a partir da primeira linha do resource politica://uso."""
    lines = policy_text.splitlines()
    if not lines:
        raise MCPDiscoveryError("Resource politica://uso retornou texto vazio")
    first_line = lines[0].strip()
    if not first_line:
        raise MCPDiscoveryError("Primeira linha de politica://uso está vazia")
    if ":" in first_line:
        prefix, _, value = first_line.partition(":")
        if prefix.strip().lower() in ("versao", "versão", "version"):
            version = value.strip()
            if version:
                return version
            raise MCPDiscoveryError("Primeira linha de politica://uso não possui valor de versão")
    return first_line


def select_reservation_tool(tools_by_name: dict[str, types.Tool]) -> types.Tool:
    """Seleciona a tool de reserva a partir do catálogo descoberto, sem fallback local."""
    tool = tools_by_name.get(RESERVATION_TOOL_NAME)
    if tool is None:
        raise MCPDiscoveryError(
            f"Tool '{RESERVATION_TOOL_NAME}' ausente no catálogo descoberto via tools/list"
        )
    schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not all(arg in properties for arg in REQUIRED_RESERVATION_ARGS):
        raise MCPDiscoveryError(
            f"Schema descoberto de '{RESERVATION_TOOL_NAME}' não declara os parâmetros necessários"
        )
    return tool


class MCPHost:
    """Cliente host MCP reutilizável sobre Streamable HTTP em mode='2026-07-28'."""

    def __init__(
        self,
        mcp_url: str = DEFAULT_MCP_URL,
        *,
        elicitation_callback: ElicitationFnT | None = None,
    ) -> None:
        self.mcp_url = mcp_url
        self._elicitation_callback: ElicitationFnT = (
            elicitation_callback if elicitation_callback is not None else defensive_elicitation_callback
        )
        self._client: Client | None = None
        self._snapshot: HostSnapshot | None = None

    @property
    def snapshot(self) -> HostSnapshot | None:
        """Retorna o HostSnapshot em cache de aplicação, se já descoberto."""
        return self._snapshot

    async def open(self) -> MCPHost:
        """Abre explicitamente o cliente MCP moderno sem fallback legacy/probe."""
        if self._client is not None:
            return self
        client = Client(
            self.mcp_url,
            mode=MCP_PROTOCOL_VERSION,
            client_info=CLIENT_INFO,
            elicitation_callback=self._elicitation_callback,
            cache=None,
        )
        await client.__aenter__()
        self._client = client
        return self

    async def close(self) -> None:
        """Fecha explicitamente o cliente MCP."""
        client = self._client
        self._client = None
        self._snapshot = None
        if client is not None:
            await client.__aexit__(None, None, None)

    async def __aenter__(self) -> MCPHost:
        return await self.open()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    @property
    def session(self) -> ClientSession:
        """Retorna a ClientSession conectada do SDK oficial."""
        if self._client is None:
            raise RuntimeError("MCPHost não está aberto")
        return self._client.session

    async def list_tools_page(
        self,
        *,
        cursor: str | None = None,
        trace: RequestTrace | str | None = None,
    ) -> types.ListToolsResult:
        """Executa uma página de tools/list com metadados de rastreamento explícitos."""
        meta = build_trace_meta(trace)
        params = types.PaginatedRequestParams(cursor=cursor, _meta=meta)
        return await self.session.list_tools(params=params)

    async def discover_all_tools(
        self,
        *,
        trace: RequestTrace | str | None = None,
    ) -> dict[str, types.Tool]:
        """Percorre todas as páginas de tools/list até nextCursor ausente."""
        tools_by_name: dict[str, types.Tool] = {}
        cursor: str | None = None
        for _ in range(MAX_TOOL_LIST_PAGES):
            page = await self.list_tools_page(cursor=cursor, trace=trace)
            for tool in page.tools:
                tools_by_name[tool.name] = tool
            if page.next_cursor is None:
                return tools_by_name
            cursor = page.next_cursor
        raise MCPDiscoveryError("Paginação de tools/list excedeu o limite máximo de páginas")

    async def read_resource(
        self,
        uri: str,
        *,
        trace: RequestTrace | str | None = None,
    ) -> types.ReadResourceResult:
        """Executa resources/read na sessão raw sem auto-responder a elicitation."""
        meta = build_trace_meta(trace)
        return await self.session.read_resource(
            uri,
            meta=meta,
            allow_input_required=False,
        )

    async def read_policy_resource(
        self,
        *,
        trace: RequestTrace | str | None = None,
    ) -> tuple[str, str]:
        """Lê politica://uso explicitamente e extrai texto completo e versão da primeira linha."""
        result = await self.read_resource(POLICY_RESOURCE_URI, trace=trace)
        if not result.contents:
            raise MCPDiscoveryError("Resource politica://uso retornou contents vazio")
        first = result.contents[0]
        text = getattr(first, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise MCPDiscoveryError("Resource politica://uso não contém texto markdown válido")
        version = extract_policy_version(text)
        return text, version

    async def ensure_discovered(
        self,
        *,
        trace: RequestTrace | str | None = None,
        force_refresh: bool = False,
    ) -> HostSnapshot:
        """Garante tools/list explícito e leitura de politica://uso antes do primeiro tools/call."""
        if self._snapshot is not None and not force_refresh:
            return self._snapshot
        tools_by_name = await self.discover_all_tools(trace=trace)
        reservation_tool = select_reservation_tool(tools_by_name)
        policy_text, policy_version = await self.read_policy_resource(trace=trace)
        snapshot = HostSnapshot(
            tools_by_name=tools_by_name,
            reservation_tool=reservation_tool,
            policy_text=policy_text,
            policy_version=policy_version,
        )
        self._snapshot = snapshot
        return snapshot

    async def call_tool_raw(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        trace: RequestTrace | str | None = None,
        input_responses: types.InputResponses | None = None,
        request_state: str | None = None,
    ) -> types.CallToolResult | types.InputRequiredResult:
        """Executa tools/call via session.call_tool(..., allow_input_required=True)."""
        meta = build_trace_meta(trace)
        result = await self.session.call_tool(
            name,
            arguments,
            input_responses=input_responses,
            request_state=request_state,
            meta=meta,
            allow_input_required=True,
        )
        return result

    async def call_discovered_reservation_tool(
        self,
        arguments: dict[str, Any],
        *,
        trace: RequestTrace | str | None = None,
        input_responses: types.InputResponses | None = None,
        request_state: str | None = None,
    ) -> tuple[HostSnapshot, types.CallToolResult | types.InputRequiredResult]:
        """Descobre catálogo/política (se necessário) e executa a tool de reserva descoberta."""
        snapshot = await self.ensure_discovered(trace=trace)
        result = await self.call_tool_raw(
            snapshot.reservation_tool.name,
            arguments,
            trace=trace,
            input_responses=input_responses,
            request_state=request_state,
        )
        return snapshot, result
