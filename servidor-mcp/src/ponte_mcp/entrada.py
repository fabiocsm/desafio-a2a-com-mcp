"""Observação ASGI de entrada e guarda estrita de metadados MCP por request."""

from __future__ import annotations

from collections.abc import Mapping
import json
import sys
from typing import Any

from mcp.types import ErrorData, INVALID_PARAMS, JSONRPCError
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

PROTOCOL_VERSION_META_KEY = "io.modelcontextprotocol/protocolVersion"
CLIENT_CAPABILITIES_META_KEY = "io.modelcontextprotocol/clientCapabilities"
REQUIRED_META_KEYS = (PROTOCOL_VERSION_META_KEY, CLIENT_CAPABILITIES_META_KEY)


def _log_request_stderr(
    method: Any,
    req_id: Any,
    traceparent: Any,
) -> None:
    """Registra em stderr método, id e traceparent quando presente em _meta."""
    parts = [f"method={method}", f"id={req_id}"]
    if isinstance(traceparent, str) and traceparent:
        parts.append(f"traceparent={traceparent}")
    print(f"[mcp] {' '.join(parts)}", file=sys.stderr, flush=True)


def _build_invalid_params_response(req_id: Any, message: str) -> Response:
    """Constrói resposta HTTP 400 com JSONRPCError/ErrorData oficiais (-32602)."""
    valid_id: str | int | None = req_id if isinstance(req_id, (str, int)) and not isinstance(req_id, bool) else None
    err = JSONRPCError(
        jsonrpc="2.0",
        id=valid_id,
        error=ErrorData(code=INVALID_PARAMS, message=message),
    )
    payload = err.model_dump(mode="json", by_alias=True, exclude_none=True)
    if valid_id is None:
        payload["id"] = None
    return Response(
        content=json.dumps(payload),
        status_code=400,
        media_type="application/json",
    )


class EntradaMCPMiddleware:
    """Envolve o app ASGI do SDK para registrar cada request e exigir params._meta."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return

        chunks: list[bytes] = []
        more_body = True
        disconnect_message: Message | None = None

        while more_body:
            message = await receive()
            msg_type = message.get("type")
            if msg_type == "http.request":
                body_chunk = message.get("body", b"")
                if body_chunk:
                    chunks.append(body_chunk)
                more_body = bool(message.get("more_body", False))
            elif msg_type == "http.disconnect":
                disconnect_message = message
                more_body = False
            else:
                more_body = False

        body_bytes = b"".join(chunks)

        try:
            decoded = json.loads(body_bytes)
        except (ValueError, RecursionError):
            decoded = None

        if isinstance(decoded, Mapping):
            method = decoded.get("method")
            req_id = decoded.get("id")
            params = decoded.get("params")
            meta = params.get("_meta") if isinstance(params, Mapping) else None
            traceparent = meta.get("traceparent") if isinstance(meta, Mapping) else None

            _log_request_stderr(method, req_id, traceparent)

            if "method" in decoded and "id" in decoded:
                if not isinstance(meta, Mapping):
                    resp = _build_invalid_params_response(
                        req_id,
                        "params._meta must be an object carrying the required "
                        f"{PROTOCOL_VERSION_META_KEY!r} and {CLIENT_CAPABILITIES_META_KEY!r} envelope keys",
                    )
                    await resp(scope, receive, send)
                    return

                missing = [
                    key
                    for key in REQUIRED_META_KEYS
                    if key not in meta or meta[key] is None
                ]
                if missing or not isinstance(meta.get(CLIENT_CAPABILITIES_META_KEY), Mapping):
                    missing_desc = ", ".join(missing) if missing else CLIENT_CAPABILITIES_META_KEY
                    resp = _build_invalid_params_response(
                        req_id,
                        f"params._meta is missing the required envelope key(s): {missing_desc}",
                    )
                    await resp(scope, receive, send)
                    return

        body_replayed = False

        async def replay_receive() -> Message:
            nonlocal body_replayed, disconnect_message
            if not body_replayed:
                body_replayed = True
                return {
                    "type": "http.request",
                    "body": body_bytes,
                    "more_body": False,
                }
            if disconnect_message is not None:
                msg = disconnect_message
                disconnect_message = None
                return msg
            return await receive()

        await self.app(scope, replay_receive, send)
