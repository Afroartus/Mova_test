from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import (
    Base,
    CreatedAtMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from .enums import SalesStatus, sales_status_enum


class Sale(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "SALES"
    __table_args__ = (Index("ix_sales_tenant_id", "tenant_id"),)

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("TENANTS.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Toda venta nace `created`. No hay null: `created` significa "el pago
    # todavia no se resolvio", e incluye las que dieron timeout.
    status: Mapped[SalesStatus] = mapped_column(
        sales_status_enum,
        nullable=False,
        default=SalesStatus.CREATED,
    )

    lines: Mapped[list["SaleProduct"]] = relationship(
        back_populates="sale",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SaleProduct(CreatedAtMixin, SoftDeleteMixin, Base):
    __tablename__ = "SALES_PRODUCTS"

    sale_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("SALES.id", ondelete="CASCADE"),
        primary_key=True,
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("PRODUCTS.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    # Snapshot del precio UNITARIO en el momento de la venta: no sigue al
    # producto. El total de la linea es `price * quantity`.
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # La PK (sale_id, product_id) impide repetir producto en una venta: varias
    # unidades del mismo producto van en una sola linea con su cantidad.
    quantity: Mapped[int] = mapped_column(
        nullable=False, default=1, server_default=text("1")
    )

    sale: Mapped[Sale] = relationship(back_populates="lines")

    __table_args__ = (
        Index("ix_sales_products_sale_id", "sale_id"),
        CheckConstraint("quantity > 0", name="ck_sales_products_quantity_positive"),
    )
