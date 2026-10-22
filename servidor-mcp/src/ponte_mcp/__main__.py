"""Entrypoint de linha de comando para `python -m ponte_mcp`."""

from __future__ import annotations

import os
import sys

import uvicorn

from ponte_mcp.app import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ErroConfiguracaoSegredo,
    criar_asgi_app,
)


def main() -> int:
    host = os.environ.get("MCP_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    raw_port = os.environ.get("MCP_PORT", str(DEFAULT_PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError:
        print(f"MCP_PORT inválida: {raw_port!r}", file=sys.stderr, flush=True)
        return 1

    try:
        app = criar_asgi_app(host=host)
    except ErroConfiguracaoSegredo as err:
        print(str(err), file=sys.stderr, flush=True)
        return 1

    uvicorn.run(
        app,
        host=host,
        port=port,
        workers=1,
        lifespan="on",
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
