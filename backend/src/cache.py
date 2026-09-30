"""Cache Redis.

Degrada en silencio: si Redis esta caido cada helper se comporta como un miss y
la API sigue respondiendo contra Postgres. Redis es una aceleracion, nunca la
unica copia de un dato.
"""

import json
import logging
from typing import Any

from redis.asyncio import Redis, from_url

from .config import settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


def init_cache() -> Redis:
    global _redis
    _redis = from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    return _redis


def get_cache() -> Redis:
    if _redis is None:
        raise RuntimeError("cache no inicializada: llamar init_cache() en el lifespan")
    return _redis


async def close_cache() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def cache_get_json(key: str) -> Any | None:
    try:
        raw = await get_cache().get(key)
    except Exception:
        logger.warning("redis GET %s fallo, se trata como miss", key, exc_info=True)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("redis GET %s devolvio json invalido", key)
        return None


async def cache_set_json(key: str, value: Any, ttl: int | None = None) -> None:
    try:
        await get_cache().set(
            key,
            json.dumps(value, default=str),
            ex=ttl or settings.cache_ttl_seconds,
        )
    except Exception:
        logger.warning("redis SET %s fallo, la cache se ignora", key, exc_info=True)


async def cache_delete(*keys: str) -> None:
    if not keys:
        return
    try:
        await get_cache().delete(*keys)
    except Exception:
        logger.warning("redis DEL fallo, la cache se ignora", exc_info=True)


async def cache_delete_prefix(prefix: str) -> None:
    """Invalida todas las claves de un tenant. SCAN, nunca KEYS."""
    try:
        client = get_cache()
        async for key in client.scan_iter(match=f"{prefix}*", count=200):
            await client.delete(key)
    except Exception:
        logger.warning("redis SCAN %s fallo, la cache se ignora", prefix, exc_info=True)
