"""add device inventory tables

Revision ID: a1b2c3d4e5f6
Revises: f4c1682db574
Create Date: 2026-03-21 20:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f4c1682db574'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'devices',
        sa.Column('hostname', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(128), nullable=False),
        sa.Column('vendor', sa.String(32), nullable=False),
        sa.Column('os', sa.String(32), nullable=False),
        sa.Column('device_type', sa.String(64), nullable=False),
        sa.Column('host', sa.String(128), nullable=True),
        sa.Column('port', sa.Integer(), nullable=False, server_default='22'),
        sa.Column('live_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('topology_node_id', sa.String(64), nullable=True),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='devices_pkey'),
        sa.UniqueConstraint('hostname', name='devices_hostname_key'),
    )
    op.create_index('ix_devices_id', 'devices', ['id'], unique=False)
    op.create_index('ix_devices_hostname', 'devices', ['hostname'], unique=True)

    op.create_table(
        'device_credentials',
        sa.Column('device_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(128), nullable=False),
        sa.Column('password_encrypted', sa.Text(), nullable=False),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], name='device_credentials_device_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='device_credentials_pkey'),
        sa.UniqueConstraint('device_id', name='device_credentials_device_id_key'),
    )
    op.create_index('ix_device_credentials_id', 'device_credentials', ['id'], unique=False)
    op.create_index('ix_device_credentials_device_id', 'device_credentials', ['device_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_device_credentials_device_id', table_name='device_credentials')
    op.drop_index('ix_device_credentials_id', table_name='device_credentials')
    op.drop_table('device_credentials')
    op.drop_index('ix_devices_hostname', table_name='devices')
    op.drop_index('ix_devices_id', table_name='devices')
    op.drop_table('devices')
