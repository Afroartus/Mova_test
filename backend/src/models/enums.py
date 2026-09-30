from enum import StrEnum

from sqlalchemy.dialects.postgresql import ENUM


class SalesStatus(StrEnum):
    """Estado persistido de una venta. `approved` y `declined` son terminales."""

    CREATED = "created"
    APPROVED = "approved"
    DECLINED = "declined"


class SaleOutcome(StrEnum):
    """Lo que reporta el cliente en `/:id/pay`. NO es un estado persistido.

    `created` forma parte del vocabulario pero no revierte nada: como `approved`
    y `declined` son terminales, mandar `created` siempre es un no-op.

    `timeout` (se tardo mucho, fallo de red) tampoco se persiste: la venta se
    queda en `created` y no se escribe nada, asi que no genera evento ni mueve
    el dashboard.
    """

    CREATED = "created"
    APPROVED = "approved"
    DECLINED = "declined"
    TIMEOUT = "timeout"


# Solo los outcomes que cambian el estado. `created` es identidad y `timeout`
# es no-op: los dos se resuelven en la logica, no con un mapeo.
OUTCOME_TO_STATUS: dict[SaleOutcome, SalesStatus] = {
    SaleOutcome.APPROVED: SalesStatus.APPROVED,
    SaleOutcome.DECLINED: SalesStatus.DECLINED,
}


# Se pasa la CLASE del enum, no los strings: SQLAlchemy solo convierte la fila
# a `SalesStatus` si conoce la clase. Con los labels sueltos devuelve el valor
# crudo de Postgres y cualquier `.value` revienta.
#
# `values_callable` es obligatorio: sin el, SQLAlchemy usa los NOMBRES del enum
# (CREATED) como labels en vez de los valores (created), que es como esta
# creado el tipo en Postgres.
sales_status_enum = ENUM(
    SalesStatus,
    name="SALES_STATUS",
    create_type=True,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)