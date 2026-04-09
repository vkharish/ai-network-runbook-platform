"""add chunk_version to runbooks

Revision ID: f4c1682db574
Revises: 
Create Date: 2026-03-21 15:35:48.642363

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f4c1682db574'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('runbooks', sa.Column('chunk_version', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('runbooks', 'chunk_version')
    op.create_table('audit_logs',
    sa.Column('user_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('action', sa.VARCHAR(length=64), autoincrement=False, nullable=False),
    sa.Column('resource_type', sa.VARCHAR(length=32), autoincrement=False, nullable=False),
    sa.Column('resource_id', sa.VARCHAR(length=64), autoincrement=False, nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='audit_logs_user_id_fkey', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name='audit_logs_pkey')
    )
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'], unique=False)
    op.create_index('ix_audit_logs_resource_type', 'audit_logs', ['resource_type'], unique=False)
    op.create_index('ix_audit_logs_id', 'audit_logs', ['id'], unique=False)
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'], unique=False)
    # ### end Alembic commands ###
