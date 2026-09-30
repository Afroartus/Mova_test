"""Tenants: alta, consulta y renombrado.

Este modulo vive entero en `routers/`: el `APIRouter`, los schemas Pydantic y
la logica de negocio. Los endpoints usan el nombre de la ruta; las funciones de
persistencia usan un verbo de dominio (`fetch_*`, `insert_*`, `patch_*`) para no
chocar con ellos.

`POST /v1/tenants` es el unico endpoint sin `X-Tenant-Id`: es el que crea el
tenant, no puede depender de uno que todavia no existe.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_session
from ..models import Tenant


# --------------------------------------------------------------------------
# Logica
# --------------------------------------------------------------------------


async def insert_tenant(session: AsyncSession, name: str) -> Tenant:
    tenant = Tenant(name=name)
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def fetch_tenants(
    session: AsyncSession, limit: int, offset: int
) -> list[Tenant]:
    result = await session.execute(
        select(Tenant)
        .where(Tenant.delete_at.is_(None))
        .order_by(Tenant.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def fetch_tenant(session: AsyncSession, tenant_id: UUID) -> Tenant | None:
    result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.delete_at.is_(None))
    )
    return result.scalar_one_or_none()


async def patch_tenant(
    session: AsyncSession, tenant_id: UUID, name: str | None
) -> Tenant | None:
    tenant = await fetch_tenant(session, tenant_id)
    if tenant is None:
        return None
    if name is not None:
        tenant.name = name
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def tenant_exists(session: AsyncSession, tenant_id: UUID) -> bool:
    return await fetch_tenant(session, tenant_id) is not None


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    update_at: datetime | None


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

router = APIRouter(prefix="/v1/tenants", tags=["tenants"])

Session = Annotated[AsyncSession, Depends(get_session)]
LIMIT = Annotated[int, Query(ge=1, le=200)]
OFFSET = Annotated[int, Query(ge=0)]


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    session: Session, limit: LIMIT = 50, offset: OFFSET = 0
) -> list[TenantOut]:
    return await fetch_tenants(session, limit, offset)


@router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(tenant_id: UUID, session: Session) -> TenantOut:
    tenant = await fetch_tenant(session, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant no encontrado")
    return tenant


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(payload: TenantCreate, session: Session) -> TenantOut:
    return await insert_tenant(session, payload.name)


@router.patch("/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: UUID, payload: TenantUpdate, session: Session
) -> TenantOut:
    tenant = await patch_tenant(session, tenant_id, payload.name)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant no encontrado")
    return tenant