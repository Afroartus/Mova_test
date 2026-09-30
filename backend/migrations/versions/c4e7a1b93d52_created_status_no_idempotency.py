"""drop idempotency key, created as default status, outbox payload

Revision ID: c4e7a1b93d52
Revises: a9bc2f43f378
Create Date: 2026-09-30 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c4e7a1b93d52'
down_revision: Union[str, Sequence[str], None] = 'a9bc2f43f378'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_LABELS = ('created', 'approved', 'declined')
OLD_LABELS = ('approved', 'declined', 'unknown')

# Tablas en mayusculas: siempre entrecomilladas en SQL crudo.
SALES = '"SALES"'
OUTBOX = '"SALES_OUTBOX"'
# El enum tambien se creo en mayusculas y Postgres pliega los identificadores
# sin comillas a minusculas, asi que sin comillas no lo encontraria.
ENUM_NAME = '"SALES_STATUS"'


def _swap_enum(labels: Sequence[str], backfill_from: str | None = None) -> None:
    """Reemplaza `SALES_STATUS` por un juego de labels nuevo.

    Postgres no deja quitar un valor de un enum, asi que se crea el tipo nuevo
    y las columnas se castean contra el. Se hace en una sola transaccion en vez
    de `ALTER TYPE ... ADD VALUE`, que no deja usar el valor nuevo hasta
    confirmar la transaccion.

    `backfill_from` mapea ese label a `unknown` al castear, para el downgrade.
    """
    op.execute(f'ALTER TYPE {ENUM_NAME} RENAME TO "SALES_STATUS_old"')
    postgresql.ENUM(*labels, name='SALES_STATUS').create(
        op.get_bind(), checkfirst=True
    )

    cast = f'status::text::{ENUM_NAME}'
    if backfill_from is not None:
        cast = (
            f"(CASE WHEN status::text = '{backfill_from}' THEN 'unknown' "
            f"ELSE status::text END)::{ENUM_NAME}"
        )

    for table in (SALES, OUTBOX):
        op.execute(f'ALTER TABLE {table} ALTER COLUMN status TYPE {ENUM_NAME} USING {cast}')

    op.execute('DROP TYPE "SALES_STATUS_old"')


def upgrade() -> None:
    op.drop_index('ux_sales_tenant_idempotency_key', table_name='SALES')
    op.drop_column(table_name='SALES', column_name='idempotency_key')

    _swap_enum(NEW_LABELS)

    # Las ventas viejas sin estado pasan a created antes de tighten la columna.
    op.execute(f"UPDATE {SALES} SET status = 'created' WHERE status IS NULL")
    op.execute(f"ALTER TABLE {SALES} ALTER COLUMN status SET DEFAULT 'created'")
    op.execute(f"ALTER TABLE {SALES} ALTER COLUMN status SET NOT NULL")

    # Snapshot de la venta en el evento. Se agrega nullable y se tighten
    # despues para no romper si la tabla tuviera filas.
    op.execute(f'ALTER TABLE {OUTBOX} ADD COLUMN payload JSONB')
    op.execute(f"UPDATE {OUTBOX} SET payload = '{{}}'::jsonb WHERE payload IS NULL")
    op.execute(f'ALTER TABLE {OUTBOX} ALTER COLUMN payload SET NOT NULL')


def downgrade() -> None:
    op.drop_column(table_name='SALES_OUTBOX', column_name='payload')

    # El default va primero: con `DEFAULT 'created'` puesto, Postgres rechaza
    # castear la columna al enum viejo porque no sabe traducir ese default.
    op.execute(f'ALTER TABLE {SALES} ALTER COLUMN status DROP DEFAULT')

    # `created` no existia en el enum viejo: se degrada a unknown.
    _swap_enum(OLD_LABELS, backfill_from='created')

    op.execute(f'ALTER TABLE {SALES} ALTER COLUMN status DROP NOT NULL')

    op.add_column(
        table_name='SALES',
        column=sa.Column('idempotency_key', sa.String(), nullable=True),
    )
    op.create_index(
        'ux_sales_tenant_idempotency_key',
        'SALES',
        ['tenant_id', 'idempotency_key'],
        unique=True,
    )