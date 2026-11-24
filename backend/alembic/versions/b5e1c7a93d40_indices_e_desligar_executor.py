"""índices nas chaves estrangeiras e desligar o executor

Revision ID: b5e1c7a93d40
Revises: 7c41d2a9e5b3
Create Date: 2026-11-24 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b5e1c7a93d40'
down_revision: Union[str, Sequence[str], None] = '7c41d2a9e5b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (nome do índice, tabela, colunas). Sem índice numa chave estrangeira, cada linha apagada na
# tabela de origem faz o Postgres varrer esta tabela inteira
_INDEXES = [
    ('ix_ai_drafts_flow_id', 'ai_drafts', ['flow_id']),
    ('ix_variables_step_id', 'variables', ['step_id']),
    ('ix_repairs_run_id', 'repairs', ['run_id']),
    ('ix_repairs_old_version_id', 'repairs', ['old_version_id']),
    ('ix_repairs_new_version_id', 'repairs', ['new_version_id']),
    ('ix_help_requests_run_item_id', 'help_requests', ['run_item_id']),
    ('ix_help_requests_step_id', 'help_requests', ['step_id']),
    ('ix_artifacts_created_at', 'artifacts', ['created_at']),
    ('ix_runs_owner_id_created_at', 'runs', ['owner_id', 'created_at']),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('runner_tokens_valid_after', sa.DateTime(timezone=True), nullable=True),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns, unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_column('users', 'runner_tokens_valid_after')
