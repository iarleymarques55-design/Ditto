"""criar tarefa com IA

Revision ID: 7c41d2a9e5b3
Revises: 0ff65df947d2
Create Date: 2026-11-17 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7c41d2a9e5b3'
down_revision: Union[str, Sequence[str], None] = '0ff65df947d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ai_drafts',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('start_url', sa.Text(), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=True),
        sa.Column(
            'status',
            sa.Enum(
                'queued', 'running', 'waiting_answer', 'done', 'failed', 'canceled',
                name='aidraftstatus', native_enum=False, create_constraint=True, length=32,
            ),
            nullable=False,
        ),
        sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('events', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('allowed_hosts', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('question', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('flow_id', sa.Uuid(), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['flow_id'], ['flows.id'], name=op.f('fk_ai_drafts_flow_id_flows'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_ai_drafts_owner_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_drafts')),
    )
    op.create_index(op.f('ix_ai_drafts_owner_id'), 'ai_drafts', ['owner_id'], unique=False)
    op.create_index(op.f('ix_ai_drafts_status'), 'ai_drafts', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_ai_drafts_status'), table_name='ai_drafts')
    op.drop_index(op.f('ix_ai_drafts_owner_id'), table_name='ai_drafts')
    op.drop_table('ai_drafts')
