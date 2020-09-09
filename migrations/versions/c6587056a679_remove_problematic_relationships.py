"""remove problematic relationships

Revision ID: c6587056a679
Revises: adbec6151036
Create Date: 2020-09-09 02:55:24.533883

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6587056a679'
down_revision = 'adbec6151036'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'nutrition', type_='foreignkey')
    op.drop_column('nutrition', 'meal_id')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('nutrition', sa.Column('meal_id', sa.INTEGER(), nullable=True))
    op.create_foreign_key(None, 'nutrition', 'meals', ['meal_id'], ['id'])
    # ### end Alembic commands ###