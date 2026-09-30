"""Dashboard: agregado del dia y stream reactivo por SSE.

Este modulo vive entero en `routers/`: el `APIRouter`, los schemas Pydantic y
la logica del agregado. El worker del outbox importa de aqui
(`compute_from_db`, `today_bounds`, `cache_key`), asi que esos tres nombres son
contrato: no se renombran sin tocar `src/workers/outbox.py`.

El agregado es siempre DERIVADO: Redis es la cache, Postgres es la verdad. Si
la clave no esta, se reconstruye con la query; si Redis esta caido, cada
llamada recalcula. Nunca hay dos copias que puedan divergir porque la cache no
se escribe a mano.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import cache_get_json, cache_set_json
from ..config import settings
from ..database import SessionLocal
from ..deps import get_session, get_tenant_id
from ..events import hub
from ..models import Sale, SaleProduct, SalesStatus

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")
STATES = (SalesStatus.CREATED, SalesStatus.APPROVED, SalesStatus.DECLINED)


# --------------------------------------------------------------------------
# Logica del agregado
# --------------------------------------------------------------------------


def today_bounds(now: datetime | None = None) -> tuple[datetime, datetime, str]:
    """Dia UTC calendario. Devuelve (inicio, fin, fecha_iso)."""
    now = now or datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1), start.date().isoformat()


def cache_key(tenant_id: UUID, date: str) -> str:
    return f"dashboard:today:{tenant_id}:{date}"


def _empty(date: str) -> dict:
    buckets = {state.value for state in STATES}
    return {
        "date": date,
        "timezone": "UTC",
        "total_sales": 0,
        "counts": dict.fromkeys(buckets, 0),
        "amounts": dict.fromkeys(buckets, "0.00"),
        "approved_amount": "0.00",
    }


async def compute_from_db(
    session: AsyncSession, tenant_id: UUID, now: datetime | None = None
) -> dict:
    """Reconstruye el agregado desde Postgres.

    El total de cada venta se calcula con un subquery sobre las lineas, no con
    una columna desnormalizada: asi el agregado no puede desviarse de lo que
    realmente se vendio.
    """
    start, end, date = today_bounds(now)

    line_totals = (
        select(
            SaleProduct.sale_id.label("sale_id"),
            func.sum(SaleProduct.price).label("total"),
        )
        .where(SaleProduct.delete_at.is_(None))
        .group_by(SaleProduct.sale_id)
        .subquery()
    )

    rows = (
        await session.execute(
            select(
                Sale.status,
                func.count().label("sale_count"),
                func.coalesce(func.sum(line_totals.c.total), ZERO).label("amount"),
            )
            .outerjoin(line_totals, line_totals.c.sale_id == Sale.id)
            .where(
                Sale.tenant_id == tenant_id,
                Sale.delete_at.is_(None),
                Sale.created_at >= start,
                Sale.created_at < end,
            )
            .group_by(Sale.status)
        )
    ).all()

    aggregate = _empty(date)
    for status, sale_count, amount in rows:
        # Agrupando por una columna suelta SQLAlchemy devuelve el valor crudo
        # del enum, no el miembro: por eso se normaliza con getattr.
        key = getattr(status, "value", status)
        if key is None or key not in aggregate["counts"]:
            continue
        aggregate["counts"][key] += sale_count
        aggregate["amounts"][key] = str(
            (Decimal(amount) if amount is not None else ZERO).quantize(ZERO)
        )

    # El total se DERIVA de los buckets, no se acumula en paralelo: por
    # construccion no puede desviarse de la suma por estado, ni aunque el
    # outbox entregue el mismo evento dos veces.
    aggregate["total_sales"] = sum(aggregate["counts"].values())
    aggregate["approved_amount"] = aggregate["amounts"][SalesStatus.APPROVED.value]
    return aggregate


async def get_today(session: AsyncSession, tenant_id: UUID) -> dict:
    """Cache-aside: Redis primero, Postgres si no esta."""
    _, _, date = today_bounds()
    key = cache_key(tenant_id, date)

    cached = await cache_get_json(key)
    if cached is not None:
        return cached

    aggregate = await compute_from_db(session, tenant_id)
    await cache_set_json(key, aggregate)
    return aggregate


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class StatusCounts(BaseModel):
    created: int = 0
    approved: int = 0
    declined: int = 0


class StatusAmounts(BaseModel):
    created: str = "0.00"
    approved: str = "0.00"
    declined: str = "0.00"


class TodayAggregate(BaseModel):
    date: str
    timezone: str = "UTC"
    # Derivado de los buckets: siempre igual a created + approved + declined.
    total_sales: int
    counts: StatusCounts
    amounts: StatusAmounts
    approved_amount: str


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])

Session = Annotated[AsyncSession, Depends(get_session)]
Tenant = Annotated[UUID, Depends(get_tenant_id)]


def _frame(event: str, data: dict, event_id: int) -> str:
    return f"id: {event_id}\nevent: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/today", response_model=TodayAggregate)
async def today(tenant_id: Tenant, session: Session) -> TodayAggregate:
    """Agregado del dia UTC, servido desde cache y reconstruible."""
    return TodayAggregate.model_validate(await get_today(session, tenant_id))


@router.get("/stream")
async def stream(request: Request, tenant_id: Tenant) -> StreamingResponse:
    """SSE: empuja las ventas del tenant en tiempo real.

    Al conectar se manda un `snapshot` con el agregado del dia; despues llega un
    frame `sale` por cada venta creada o cuyo estado de pago cambio.
    """
    return StreamingResponse(
        _events(request, tenant_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _events(request: Request, tenant_id: UUID) -> AsyncIterator[str]:
    queue = hub.subscribe(tenant_id)
    try:
        # Sesion propia: el stream vive mas alla del request que lo abrio.
        async with SessionLocal() as session:
            snapshot = await get_today(session, tenant_id)
        yield _frame("snapshot", snapshot, 0)

        while True:
            if await request.is_disconnected():
                return
            try:
                event = await asyncio.wait_for(
                    queue.get(),
                    timeout=settings.sse_heartbeat_seconds,
                )
            except TimeoutError:
                # Comentario SSE: mantiene viva la conexion sin inventar datos.
                yield ": ping\n\n"
                continue
            yield _frame("sale", event["data"], event["id"])
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("stream sse caido para tenant %s", tenant_id)
    finally:
        hub.unsubscribe(tenant_id, queue)