from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import SalesStatus, sales_status_enum
from .sale import Sale


class SaleOutbox(TimestampMixin, Base):
    """Evento de dominio durable.

    La fila se escribe en la MISMA transaccion que el cambio de estado de la
    venta, asi que nunca existe un evento sin su venta ni una venta sin su
    evento. Es la fuente de verdad: el stream de Redis solo despierta al worker.
    """

    __tablename__ = "SALES_OUTBOX"
    __table_args__ = (
        Index("ix_sales_outbox_unprocessed", "processed_at", "id"),
        Index("ix_sales_outbox_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    sale_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("SALES.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("TENANTS.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[SalesStatus] = mapped_column(sales_status_enum, nullable=False)

    # Snapshot de la venta en el momento del cambio. El evento se autodescribe
    # para que reprocesarlo mas tarde siga dando la verdad historica: si el
    # worker releyera la venta, un evento viejo de `created` publicaria el
    # `approved` actual y mentiria.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    sale: Mapped[Sale] = relationship()

    # NULL = el worker todavia no consumio este evento.
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
