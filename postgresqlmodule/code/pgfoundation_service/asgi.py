"""ASGI entrypoint (async) — plain Django wrapped with a lifespan handler.

Startup builds the DataFoundation **on the serving event loop** (so pools bind to
the right loop) from ``PGF_CONFIG``; shutdown drains it. Django's ASGI handler
does not implement the ``lifespan`` scope, so we handle it here and delegate
``http``/``websocket`` to Django.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Nothing here is pip-installable; the code root (this file's grandparent) holds
# both `pgfoundation` and `pgfoundation_service`. Putting it on sys.path lets the
# service start straight from a checkout, whatever the cwd or ASGI server.
_CODE_ROOT = str(Path(__file__).resolve().parents[1])
if _CODE_ROOT not in sys.path:
    sys.path.insert(0, _CODE_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pgfoundation_service.settings")

# psycopg async needs a SelectorEventLoop on Windows (ProactorEventLoop is
# unsupported). Set it before any loop is created. The local runner sets this
# too, before uvicorn starts, for belt-and-suspenders.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from django.conf import settings  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

_django_app = get_asgi_application()


async def _lifespan(scope, receive, send) -> None:
    from . import bootstrap

    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            try:
                config = getattr(settings, "PGF_CONFIG", None)
                if config:
                    await bootstrap.startup_from_config(config)
                await send({"type": "lifespan.startup.complete"})
            except Exception as exc:  # noqa: BLE001
                await send({"type": "lifespan.startup.failed", "message": str(exc)})
                return
        elif message["type"] == "lifespan.shutdown":
            try:
                from .bootstrap import _foundation  # type: ignore[attr-defined]

                if _foundation is not None:
                    await _foundation.aclose()
            finally:
                await send({"type": "lifespan.shutdown.complete"})
            return


async def application(scope, receive, send) -> None:
    if scope["type"] == "lifespan":
        await _lifespan(scope, receive, send)
    else:
        await _django_app(scope, receive, send)
