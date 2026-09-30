"""quantity en las lineas de venta

Revision ID: d81f3c6a2e10
Revises: c4e7a1b93d52
Create Date: 2026-09-30 18:00:00.000000

La PK de `SALES_PRODUCTS` es `(sale_id, product_id)`: una venta no puede
repetir producto, asi que "2 cafes" necesita una cantidad en la linea. `price`
sigue siendo el precio UNITARIO congelado; el total de la linea es
`price * quantity`.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd81f3c6a2e10'
down_revision: Union[str, Sequence[str], None] = 'c4e7a1b93d52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tablas en mayusculas: siempre entrecomilladas en SQL crudo.
LINES = '"SALES_PRODUCTS"'


def upgrade() -> None:
    # Con DEFAULT 1 las lineas existentes quedan como una unidad, que es lo que
    # representaban.
    op.execute(f'ALTER TABLE {LINES} ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1')
    op.execute(
        f'ALTER TABLE {LINES} ADD CONSTRAINT ck_sales_products_quantity_positive '
        'CHECK (quantity > 0)'
    )


def downgrade() -> None:
    op.execute(f'ALTER TABLE {LINES} DROP CONSTRAINT ck_sales_products_quantity_positive')
    op.execute(f'ALTER TABLE {LINES} DROP COLUMN quantity')
