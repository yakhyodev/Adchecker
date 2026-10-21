"""initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-21 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. administrators table
    op.create_table(
        'administrators',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=True),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('role', sa.String(length=50), nullable=False, server_default='admin'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_administrators_telegram_user_id', 'administrators', ['telegram_user_id'], unique=True)

    # 2. channels table
    op.create_table(
        'channels',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('telegram_channel_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('url', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('cpm_price', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('last_scanned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_scanned_message_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_channels_telegram_channel_id', 'channels', ['telegram_channel_id'], unique=True)
    op.create_index('ix_channels_username', 'channels', ['username'], unique=False)

    # 3. advertisements table
    op.create_table(
        'advertisements',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('post_url', sa.String(length=255), nullable=False),
        sa.Column('post_text', sa.Text(), nullable=True),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('media_type', sa.String(length=50), nullable=True),
        sa.Column('views', sa.Integer(), nullable=True),
        sa.Column('reactions', sa.Integer(), nullable=True),
        sa.Column('forwards', sa.Integer(), nullable=True),
        sa.Column('cost', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('is_deleted_from_tg', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('first_detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('channel_id', 'message_id', name='uq_channel_message'),
    )
    op.create_index('ix_advertisements_channel_id', 'advertisements', ['channel_id'], unique=False)
    op.create_index('ix_advertisements_message_id', 'advertisements', ['message_id'], unique=False)
    op.create_index('ix_advertisements_posted_at', 'advertisements', ['posted_at'], unique=False)

    # 4. view_snapshots table
    op.create_table(
        'view_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('advertisement_id', sa.Integer(), nullable=False),
        sa.Column('views', sa.Integer(), nullable=True),
        sa.Column('reactions', sa.Integer(), nullable=True),
        sa.Column('forwards', sa.Integer(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['advertisement_id'], ['advertisements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_view_snapshots_advertisement_id', 'view_snapshots', ['advertisement_id'], unique=False)
    op.create_index('ix_view_snapshots_recorded_at', 'view_snapshots', ['recorded_at'], unique=False)

    # 5. monitoring_jobs table
    op.create_table(
        'monitoring_jobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_type', sa.String(length=50), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('posts_scanned', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ads_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_monitoring_jobs_channel_id', 'monitoring_jobs', ['channel_id'], unique=False)

    # 6. settings table
    op.create_table(
        'settings',
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    op.drop_table('settings')
    op.drop_table('monitoring_jobs')
    op.drop_table('view_snapshots')
    op.drop_table('advertisements')
    op.drop_table('channels')
    op.drop_table('administrators')
