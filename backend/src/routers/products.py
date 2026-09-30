"""Productos: alta, consulta, edicion y resolucion para venta.

Este modulo vive entero en `routers/`: el `APIRouter`, los schemas Pydantic y
la logica de negocio. Los endpoints usan el nombre de la ruta; las funciones de
persistencia usan un verbo de dominio (`fetch_*`, `insert_*`, `patch_*`) para no
chocar con ellos.

El filtro por tenant va SIEMPRE en el `WHERE` de cada query, nunca en un `if`
posterior: un recurso de otro tenant devuelve 404 y no 403, para no revelar que
existe.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import cache_delete_prefix
from ..deps import get_session, get_tenant_id
from ..models import Product

CENTS = Decimal("0.01")

# En JSON un Decimal sale como string ("10.50"), no como numero.
MONEY = Field(ge=0, max_digits=12, decimal_places=2)


# --------------------------------------------------------------------------
# Logica
# --------------------------------------------------------------------------


async def fetch_products(
    session: AsyncSession, tenant_id: UUID, limit: int, offset: int
) -> list[Product]:
    result = await session.execute(
        select(Product)
        .where(
            Product.tenant_id == tenant_id,
            Product.delete_at.is_(None),
        )
        .order_by(Product.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def fetch_product(
    session: AsyncSession, tenant_id: UUID, product_id: UUID
) -> Product | None:
    """El aislamiento va en el WHERE, no en un if posterior."""
    result = await session.execute(
        select(Product).where(
            Product.id == product_id,
            Product.tenant_id == tenant_id,
            Product.delete_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def insert_product(
    session: AsyncSession,
    tenant_id: UUID,
    name: str,
    price: Decimal,
) -> Product:
    product = Product(tenant_id=tenant_id, name=name, price=price)
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def patch_product(
    session: AsyncSession,
    tenant_id: UUID,
    product_id: UUID,
    name: str | None,
    price: Decimal | None,
) -> Product | None:
    product = await fetch_product(session, tenant_id, product_id)
    if product is None:
        return None
    if name is not None:
        product.name = name
    if price is not None:
        product.price = price
    await session.commit()
    await session.refresh(product)
    return product


async def get_owned_products(
    session: AsyncSession, tenant_id: UUID, product_ids: list[UUID]
) -> dict[UUID, Product]:
    """Productos del tenant, indexados por id.

    Se usa para resolver los precios de las lineas de una venta: un producto
    de otro tenant simplemente no aparece, asi que no se puede vender.
    """
    result = await session.execute(
        select(Product).where(
            Product.id.in_(product_ids),
            Product.tenant_id == tenant_id,
            Product.delete_at.is_(None),
        )
    )
    return {p.id: p for p in result.scalars().all()}


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class ProductCreate(BaseModel):
    # Sin tenant_id: viene del header, nunca del body.
    name: str = Field(min_length=1, max_length=200)
    price: Decimal = MONEY

    @field_validator("price")
    @classmethod
    def round_to_cents(cls, value: Decimal) -> Decimal:
        return value.quantize(CENTS)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    price: Decimal | None = MONEY

    @field_validator("price")
    @classmethod
    def round_to_cents(cls, value: Decimal | None) -> Decimal | None:
        return value.quantize(CENTS) if value is not None else None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    price: Decimal
    created_at: datetime
    update_at: datetime | None


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

router = APIRouter(prefix="/v1/products", tags=["products"])

Session = Annotated[AsyncSession, Depends(get_session)]
Tenant = Annotated[UUID, Depends(get_tenant_id)]
LIMIT = Annotated[int, Query(ge=1, le=200)]
OFFSET = Annotated[int, Query(ge=0)]


@router.get("", response_model=list[ProductOut])
async def list_products(
    tenant_id: Tenant,
    session: Session,
    limit: LIMIT = 50,
    offset: OFFSET = 0,
) -> list[ProductOut]:
    return await fetch_products(session, tenant_id, limit, offset)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: UUID, tenant_id: Tenant, session: Session):
    product = await fetch_product(session, tenant_id, product_id)
    if product is None:
        # 404 y no 403: no se revela que el recurso existe en otro tenant.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "producto no encontrado")
    return product


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate, tenant_id: Tenant, session: Session
) -> ProductOut:
    product = await insert_product(session, tenant_id, payload.name, payload.price)
    await cache_delete_prefix(f"products:{tenant_id}")
    return product


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    tenant_id: Tenant,
    session: Session,
) -> ProductOut:
    product = await patch_product(
        session, tenant_id, product_id, payload.name, payload.price
    )
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "producto no encontrado")
    await cache_delete_prefix(f"products:{tenant_id}")
    return product