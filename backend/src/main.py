"""Punto de entrada.

El worker del outbox corre como `asyncio.Task` dentro de este mismo proceso:
es reactividad, no un segundo servicio.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .cache import close_cache, get_cache, init_cache
from .config import settings
from .database import SessionLocal, dispose_engine
from .events import hub
from .routers import dashboard, products, sales, tenants
from .workers import worker as outbox_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_cache()
    await outbox_worker.start()
    logger.info("%s lista", settings.app_name)
    try:
        yield
    finally:
        await outbox_worker.stop()
        await close_cache()
        await dispose_engine()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    # X-Tenant-Id es un header no simple: sin permitirlo el preflight falla.
    allow_headers=["Content-Type", "X-Tenant-Id"],
)

app.include_router(tenants.router)
app.include_router(products.router)
app.include_router(sales.router)
app.include_router(dashboard.router)


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str | int]:
    """Postgres es obligatorio; Redis es opcional, por eso se degrada."""
    db_state = "down"
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_state = "up"
    except Exception:
        logger.warning("health: postgres no responde", exc_info=True)

    cache_state = "down"
    try:
        await get_cache().ping()
        cache_state = "up"
    except Exception:
        logger.warning("health: redis no responde", exc_info=True)

    return {
        "status": "ok" if db_state == "up" else "degraded",
        "postgres": db_state,
        "redis": cache_state,
        "sse_subscribers": hub.total_subscribers(),
    }
