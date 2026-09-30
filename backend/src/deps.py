from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db

TENANT_HEADER = "X-Tenant-Id"


async def get_tenant_id(
    x_tenant_id: str | None = Header(
        default=None,
        alias=TENANT_HEADER,
        description="Tenant propietario de los datos solicitados.",
    ),
) -> UUID:
    """Identidad del tenant.

    Sin usuarios ni sesiones, el tenant viaja en cada request. Nunca se acepta
    desde el body: sale siempre de aqui, y las capas de abajo filtran por el.
    """
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"header {TENANT_HEADER} requerido",
        )
    try:
        return UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{TENANT_HEADER} debe ser un UUID valido",
        )


async def get_session() -> AsyncIterator[AsyncSession]:
    async for session in get_db():
        yield session


DbSession = Depends(get_session)
TenantId = Depends(get_tenant_id)
