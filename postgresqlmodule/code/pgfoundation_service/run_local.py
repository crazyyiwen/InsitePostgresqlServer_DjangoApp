"""Local dev launcher for the Django (ASGI) service.

    python -m pgfoundation_service.run_local

Honors env: PGF_HOST (127.0.0.1), PGF_PORT (8000), PGF_CONFIG (config file),
DJANGO_SETTINGS_MODULE (defaulted). The ``.vscode/launch.json`` target sets these.

On Windows, uvicorn's own ``run()`` forces a ProactorEventLoop, which async
psycopg cannot use. So we build the uvicorn Server and run ``serve()`` inside a
SelectorEventLoop *we* create, bypassing uvicorn's loop setup.
"""
from __future__ import annotations

import asyncio
import os
import selectors
import sys
from pathlib import Path

# See asgi.py — no installable package, so put the code root on sys.path. This
# also lets the file be run directly (``python pgfoundation_service/run_local.py``)
# and not only as ``python -m pgfoundation_service.run_local``.
_CODE_ROOT = str(Path(__file__).resolve().parents[1])
if _CODE_ROOT not in sys.path:
    sys.path.insert(0, _CODE_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pgfoundation_service.settings")


def main() -> None:
    import uvicorn

    host = os.environ.get("PGF_HOST", "127.0.0.1")
    port = int(os.environ.get("PGF_PORT", "8600"))

    config = uvicorn.Config(
        "pgfoundation_service.asgi:application",
        host=host,
        port=port,
        log_level="info",
        lifespan="on",
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    def _selector_loop() -> asyncio.AbstractEventLoop:
        return asyncio.SelectorEventLoop(selectors.SelectSelector())

    loop_factory = _selector_loop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(server.serve())


if __name__ == "__main__":
    main()
