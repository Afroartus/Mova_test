"""Hub de eventos en proceso para SSE.

Cada suscriptor SSE tiene su propia cola y recibe unicamente los eventos de su
tenant. Es concurrencia dentro del mismo proceso, no un broker externo.
"""

import asyncio
import logging
from collections import defaultdict
from uuid import UUID

logger = logging.getLogger(__name__)

MAX_QUEUE_SIZE = 100


class DashboardHub:
    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[asyncio.Queue[dict]]] = defaultdict(set)

    def subscribe(self, tenant_id: UUID) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._subscribers[tenant_id].add(queue)
        return queue

    def unsubscribe(self, tenant_id: UUID, queue: asyncio.Queue[dict]) -> None:
        self._subscribers[tenant_id].discard(queue)
        if not self._subscribers[tenant_id]:
            self._subscribers.pop(tenant_id, None)

    def publish(self, tenant_id: UUID, event: dict) -> None:
        for queue in self._subscribers.get(tenant_id, set()):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Un cliente lento nunca bloquea al worker: se descarta su
                # evento y ese cliente se resincroniza con el proximo snapshot.
                logger.warning("sse suscriptor lento, evento descartado")

    def subscriber_count(self, tenant_id: UUID) -> int:
        return len(self._subscribers.get(tenant_id, set()))

    def total_subscribers(self) -> int:
        return sum(len(queues) for queues in self._subscribers.values())


hub = DashboardHub()
