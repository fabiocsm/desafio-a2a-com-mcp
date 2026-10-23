"""Entrypoint CLI para execução do processo do agente (`python -m ponte_agente`)."""

from __future__ import annotations

import uvicorn

from ponte_agente.app import AgenteSettings, create_app


def main() -> None:
    """Inicia o servidor HTTP A2A do agente com um único worker em memória."""
    settings = AgenteSettings.from_env()
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        workers=1,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
