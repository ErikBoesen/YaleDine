"""add location codes

Revision ID: c8c3d310983b
Revises: e8c7ffd550e3
Create Date: 2020-10-13 20:55:54.489952

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8c3d310983b'
down_revision = 'e8c7ffd550e3'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('items', sa.Column('fish', sa.Boolean(), nullable=True))
    op.drop_column('items', 'seafood')
    op.add_column('locations', sa.Column('code', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('locations', 'code')
    op.add_column('items', sa.Column('seafood', sa.BOOLEAN(), nullable=True))
    op.drop_column('items', 'fish')
    # ### end Alembic commands ###
