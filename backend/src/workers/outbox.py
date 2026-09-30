"""Worker del outbox: reactividad dentro del mismo proceso.

No es un segundo servicio ni un broker externo: es un `asyncio.Task` que
comparte el event loop de FastAPI. La app sigue atendiendo requests mientras
este loop corre.

Diseno: la tabla `sales_outbox` es la fuente de verdad y el stream de Redis
solo despierta al worker. Se eligio el stream y no `LISTEN/NOTIFY` porque
NOTIFY tiene un limite duro de 8000 bytes por payload, no tiene consumer group
y pierde despertares; el stream ademas es compatible con Dragonfly.

Entrega at-least-once. El poll periodico cubre la ventana entre el commit y el
`XADD`, o un worker que muere a mitad de camino.
"""

import asyncio
import contextlib
import json
import logging
from uuid import UUID

from sqlalchemy import select

from ..cache import cache_set_json, get_cache
from ..config import settings
from ..database import SessionLocal
from ..events import hub
from ..models import SaleOutbox
from ..models.base import utcnow
from ..routers import dashboard as dashboard_router

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
CONSUMER = "dashboard-worker"
STREAM_GROUP = "dashboard-workers"


class OutboxWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        # Ultimo agregado publicado por tenant, para no emitir si no cambio.
        self._last_published: dict[tuple[UUID, str], str] = {}

    async def start(self) -> None:
        await self._ensure_group()
        self._task = asyncio.create_task(self._run(), name="outbox-worker")
        logger.info("outbox worker arrancado")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("outbox worker detenido")

    async def _ensure_group(self) -> None:
        """Crea el consumer group si no existe. Falla sin Redis, y esta bien."""
        try:
            await get_cache().xgroup_create(
                settings.outbox_stream,
                STREAM_GROUP,
                id="0",
                mkstream=True,
            )
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                logger.warning(
                    "no se pudo crear el consumer group del stream", exc_info=True
                )

    async def _run(self) -> None:
        while True:
            try:
                await self._drain_stream()
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # El worker nunca muere por un fallo puntual. Sin traceback: que
                # Postgres este caido es un estado operativo esperado y no
                # debe llenar el log cada 5 segundos.
                logger.warning(
                    "ciclo del outbox worker fallo (%s): %s",
                    type(exc).__name__,
                    exc,
                )
                await asyncio.sleep(settings.outbox_poll_seconds)

    async def _drain_stream(self) -> None:
        """Espera una señal del stream y consume la tabla.

        No procesa el mensaje del stream en si: la fila de `sales_outbox` es
        la que manda, el stream solo reduce la latencia.
        """
        try:
            await get_cache().xreadgroup(
                STREAM_GROUP,
                CONSUMER,
                {settings.outbox_stream: ">"},
                count=1,
                block=int(settings.outbox_poll_seconds * 1000),
            )
        except Exception as exc:
            if "NOGROUP" in str(exc):
                # Redis se reinicio y el stream no persistia: se recrea.
                await self._ensure_group()
            await asyncio.sleep(settings.outbox_poll_seconds)

    async def _poll_once(self) -> None:
        """Consume eventos pendientes. `SKIP LOCKED` permite varios workers."""
        aggregates: dict[UUID, dict] = {}
        # Eventos por tenant, para publicar un frame por venta.
        events_by_tenant: dict[UUID, list[tuple[int, dict]]] = {}

        async with SessionLocal() as session:
            async with session.begin():
                events = (
                    await session.execute(
                        select(SaleOutbox)
                        .where(SaleOutbox.processed_at.is_(None))
                        .order_by(SaleOutbox.id)
                        .limit(BATCH_SIZE)
                        .with_for_update(skip_locked=True)
                    )
                ).scalars().all()

                if not events:
                    return

                for event in events:
                    # El tenant se toma SIEMPRE del propio evento. Si se usara
                    # una variable del bucle, una venta podria publicarse en el
                    # stream de otro tenant.
                    tenant_id = event.tenant_id
                    events_by_tenant.setdefault(tenant_id, []).append(
                        (event.id, event.payload)
                    )
                    # Un solo recalculo por tenant, aunque traiga varios eventos.
                    if tenant_id not in aggregates:
                        aggregates[tenant_id] = (
                            await dashboard_router.compute_from_db(session, tenant_id)
                        )
                    event.processed_at = utcnow()
            # El commit ya ocurrio: recien ahora se toca la cache y el SSE.

        for tenant_id, aggregate in aggregates.items():
            await self._cache_if_changed(tenant_id, aggregate)

        for tenant_id, pending in events_by_tenant.items():
            for event_id, payload in pending:
                hub.publish(tenant_id, {"id": event_id, "data": payload})

    async def _cache_if_changed(self, tenant_id: UUID, aggregate: dict) -> None:
        _, _, date = dashboard_router.today_bounds()
        payload = json.dumps(aggregate, sort_keys=True)

        if self._last_published.get((tenant_id, date)) == payload:
            return
        self._last_published[(tenant_id, date)] = payload

        await cache_set_json(dashboard_router.cache_key(tenant_id, date), aggregate)


worker = OutboxWorker()
