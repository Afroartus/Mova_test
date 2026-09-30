"""Ventas: ciclo de vida de la orden, outbox transaccional y HTTP.

Este modulo vive entero en `routers/`: el `APIRouter`, los schemas Pydantic y
la logica de negocio. Los endpoints usan el nombre de la ruta; las funciones de
persistencia usan un verbo de dominio (`fetch_*`, `insert_*`) para no chocar con
ellos.

Invariantes de este modulo:

1. `tenant_id` siempre viene de la dependencia del header, nunca del payload.
2. Una venta nace `created`. `approved` y `declined` son terminales: una vez
   escritos, ningun reporte posterior los reinterpreta.
3. `timeout` no se persiste nunca. La venta se queda en `created` y no se
   escribe nada, asi que no hay evento ni movimiento en el dashboard.
4. El evento de outbox se inserta en la MISMA transaccion que el cambio de
   estado y lleva el snapshot de la venta. Si la transaccion falla, no hay
   evento ni venta.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import get_cache
from ..config import settings
from ..deps import get_session, get_tenant_id
from ..models import (
    OUTCOME_TO_STATUS,
    Product,
    Sale,
    SaleOutcome,
    SaleOutbox,
    SaleProduct,
    SalesStatus,
)
from ..models.base import utcnow
from .products import get_owned_products

logger = logging.getLogger(__name__)

CENTS = Decimal("0.01")


# --------------------------------------------------------------------------
# Logica
# --------------------------------------------------------------------------


class SaleLinesError(Exception):
    """Lineas invalidas: producto inexistente o de otro tenant."""

    def __init__(self, missing: list[UUID]) -> None:
        self.missing = missing
        super().__init__(f"productos no disponibles: {missing}")


def sale_total(sale: Sale) -> Decimal:
    return sum((line.price * line.quantity for line in sale.lines), Decimal("0.00"))


def sale_event_payload(sale: Sale) -> dict:
    """Snapshot JSON-serializable de la venta para el outbox y el SSE.

    El `total` y los precios van como string porque son `Numeric(12,2)`: en
    JSON un Decimal sale como `"10.50"`, no como numero.
    """
    return {
        "id": str(sale.id),
        "status": sale.status.value,
        "total": str(sale_total(sale)),
        "lines": [
            {
                "product_id": str(line.product_id),
                "price": str(line.price),
                "quantity": line.quantity,
            }
            for line in sale.lines
        ],
        "created_at": sale.created_at.isoformat(),
    }


async def wake_worker(tenant_id: UUID, outbox_id: int, status: SalesStatus) -> None:
    """Despierta al worker por el stream de Redis.

    Best effort: si falla, la fila de `sales_outbox` sigue ahi y el poll de
    seguridad del worker la encuentra igual. Por eso va fuera de la
    transaccion y nunca propaga el error.

    El `tenant_id` del mensaje es solo informacion: el worker no lo usa para
    decidir nada, siempre relee las filas de la base.
    """
    try:
        await get_cache().xadd(
            settings.outbox_stream,
            {
                "outbox_id": str(outbox_id),
                "tenant_id": str(tenant_id),
                "status": status.value,
            },
            maxlen=1000,
        )
    except Exception:
        logger.warning(
            "no se pudo publicar en %s, el poll de seguridad lo recuperara",
            settings.outbox_stream,
            exc_info=True,
        )


async def fetch_sales(
    session: AsyncSession, tenant_id: UUID, limit: int, offset: int
) -> list[Sale]:
    result = await session.execute(
        select(Sale)
        .where(Sale.tenant_id == tenant_id, Sale.delete_at.is_(None))
        .order_by(Sale.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().unique().all())


async def fetch_sale(
    session: AsyncSession, tenant_id: UUID, sale_id: UUID
) -> Sale | None:
    result = await session.execute(
        select(Sale).where(
            Sale.id == sale_id,
            Sale.tenant_id == tenant_id,
            Sale.delete_at.is_(None),
        )
    )
    return result.scalars().unique().one_or_none()


async def insert_sale(
    session: AsyncSession,
    tenant_id: UUID,
    lines: list[tuple[UUID, Decimal | None, int]],
) -> Sale:
    """Crea la orden en estado `created`.

    El evento de outbox va en la MISMA transaccion que el INSERT de la venta, y
    no solo al cambiar el estado: `created` es un bucket del dashboard, asi que
    sin este evento la orden nueva no se veria hasta que otro cambio disparara
    un recalculo.
    """
    product_ids = [product_id for product_id, _, _ in lines]
    products = await get_owned_products(session, tenant_id, product_ids)
    missing = [pid for pid in product_ids if pid not in products]
    if missing:
        raise SaleLinesError(missing)

    sale = Sale(tenant_id=tenant_id, status=SalesStatus.CREATED)
    for product_id, price, quantity in lines:
        product: Product = products[product_id]
        # Sin precio explicito se congela el precio vigente del producto. Un
        # precio explicito de 0 es valido, por eso `is None` y no `or`.
        sale.lines.append(
            SaleProduct(
                product_id=product_id,
                price=product.price if price is None else price,
                quantity=quantity,
            )
        )

    session.add(sale)
    # Flush y no commit: el INSERT sale ya y con el `created_at` de servidor
    # resuelto, asi el payload del evento lleva la venta completa.
    await session.flush()

    outbox = SaleOutbox(
        sale_id=sale.id,
        tenant_id=tenant_id,
        status=SalesStatus.CREATED,
        payload=sale_event_payload(sale),
    )
    session.add(outbox)
    await session.commit()  # venta + lineas + evento, misma transaccion

    await wake_worker(tenant_id, outbox.id, sale.status)
    return sale


async def apply_payment_status(
    session: AsyncSession,
    tenant_id: UUID,
    sale_id: UUID,
    outcome: SaleOutcome,
) -> tuple[Sale | None, bool]:
    """Registra el estado de pago. Devuelve (venta, aplicado).

    No-ops, con `aplicado` False, sin escribir nada:

    - la venta ya esta `approved` o `declined` (terminales);
    - `created` sobre una venta que ya esta `created`;
    - `timeout`: es lo que reporta el cliente cuando se tardo o fallo la red,
      no un estado. La venta se queda en `created` y no genera evento, asi que
      el dashboard no se mueve.

    El resto escribe venta y evento en la misma transaccion.
    """
    sale = await fetch_sale(session, tenant_id, sale_id)
    if sale is None:
        return None, False

    if sale.status is not SalesStatus.CREATED:
        return sale, False  # approved y declined son terminales

    status = OUTCOME_TO_STATUS.get(outcome)
    if status is None:
        # created y timeout no cambian el estado persistido.
        return sale, False

    sale.status = status
    sale.update_at = utcnow()

    outbox = SaleOutbox(
        sale_id=sale.id,
        tenant_id=tenant_id,
        status=status,
        payload=sale_event_payload(sale),
    )
    session.add(outbox)
    await session.commit()  # venta + evento, misma transaccion

    await wake_worker(tenant_id, outbox.id, status)
    return sale, True


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class SaleLineIn(BaseModel):
    product_id: UUID
    # Opcional: si no viene se congela el precio vigente del producto.
    price: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )

    # Unidades de este producto. Un producto va una sola vez por venta.
    quantity: int = Field(default=1, ge=1, le=10_000)

    @field_validator("price")
    @classmethod
    def round_to_cents(cls, value: Decimal | None) -> Decimal | None:
        return value.quantize(CENTS) if value is not None else None


class SaleCreate(BaseModel):
    products: list[SaleLineIn] = Field(min_length=1)

    @field_validator("products")
    @classmethod
    def unique_products(cls, value: list[SaleLineIn]) -> list[SaleLineIn]:
        # La PK de SALES_PRODUCTS es (sale_id, product_id): repetir producto
        # reventaria el INSERT. Las unidades van en `quantity`.
        ids = [line.product_id for line in value]
        if len(ids) != len(set(ids)):
            raise ValueError("producto repetido: usa quantity para varias unidades")
        return value


class PaymentStatusIn(BaseModel):
    outcome: SaleOutcome = Field(
        description=(
            "approved = pago exitoso. declined = pago rechazado o cancelado. "
            "created y timeout son no-ops: la venta se queda en created."
        )
    )


class SaleLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: UUID
    price: Decimal
    quantity: int


class SaleOut(BaseModel):
    id: UUID
    status: str = Field(description="created, approved o declined.")
    total: Decimal
    lines: list[SaleLineOut]
    created_at: datetime
    applied: bool = Field(
        default=True,
        description=(
            "false cuando el estado no se registro porque la venta ya estaba "
            "en un estado terminal, o porque el outcome fue created o timeout. "
            "Los reintentos no reinterpretan el estado."
        ),
    )

    @classmethod
    def from_sale(cls, sale, *, applied: bool = True) -> "SaleOut":
        return cls(
            id=sale.id,
            status=sale.status.value,
            total=sale_total(sale),
            lines=[
                SaleLineOut(product_id=x.product_id, price=x.price, quantity=x.quantity)
                for x in sale.lines
            ],
            created_at=sale.created_at,
            applied=applied,
        )


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

router = APIRouter(prefix="/v1/sales", tags=["sales"])

Session = Annotated[AsyncSession, Depends(get_session)]
Tenant = Annotated[UUID, Depends(get_tenant_id)]
LIMIT = Annotated[int, Query(ge=1, le=200)]
OFFSET = Annotated[int, Query(ge=0)]


@router.get("", response_model=list[SaleOut])
async def list_sales(
    tenant_id: Tenant,
    session: Session,
    limit: LIMIT = 50,
    offset: OFFSET = 0,
) -> list[SaleOut]:
    sales = await fetch_sales(session, tenant_id, limit, offset)
    return [SaleOut.from_sale(sale) for sale in sales]


@router.get("/{sale_id}", response_model=SaleOut)
async def get_sale(sale_id: UUID, tenant_id: Tenant, session: Session) -> SaleOut:
    sale = await fetch_sale(session, tenant_id, sale_id)
    if sale is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "venta no encontrada")
    return SaleOut.from_sale(sale)


@router.post("", response_model=SaleOut, status_code=status.HTTP_201_CREATED)
async def create_sale(
    payload: SaleCreate,
    tenant_id: Tenant,
    session: Session,
) -> SaleOut:
    """Crea la orden en estado `created`.

    `tenant_id` sale del header `X-Tenant-Id`, nunca del body. Un producto de
    otro tenant no existe para quien llama: 404, no 403.
    """
    lines = [(line.product_id, line.price, line.quantity) for line in payload.products]
    try:
        sale = await insert_sale(session, tenant_id, lines)
    except SaleLinesError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"productos no encontrados: {[str(x) for x in exc.missing]}",
        )

    return SaleOut.from_sale(sale)


@router.post("/{sale_id}/pay", response_model=SaleOut)
async def pay_sale(
    sale_id: UUID,
    payload: PaymentStatusIn,
    tenant_id: Tenant,
    session: Session,
) -> SaleOut:
    """Registra el estado de pago de la orden.

    `approved` y `declined` son terminales. `timeout` no se persiste: la venta
    se queda en `created` y no se genera evento. Cuando el estado no se cambia,
    la respuesta trae `applied: false` con la venta tal como estaba.
    """
    sale, applied = await apply_payment_status(
        session, tenant_id, sale_id, payload.outcome
    )
    if sale is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "venta no encontrada")
    return SaleOut.from_sale(sale, applied=applied)