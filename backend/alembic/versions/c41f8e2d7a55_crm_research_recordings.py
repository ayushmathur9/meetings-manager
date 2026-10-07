"""Bigin CRM sync, business research and meeting recordings

Revision ID: c41f8e2d7a55
Revises: b7e2c41d9a10
Create Date: 2026-10-08 00:00:00.000000

Additive only: nullable CRM columns on companies/contacts and new tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c41f8e2d7a55'
down_revision: Union[str, None] = 'b7e2c41d9a10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TZ = sa.DateTime(timezone=True)


def _timestamps():
    return [
        sa.Column('created_at', TZ, server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', TZ, server_default=sa.text('now()'), nullable=False),
    ]


def upgrade() -> None:
    # ------------------------------------------------------------- CRM columns
    op.add_column('companies', sa.Column('bigin_account_id', sa.String(64), nullable=True))
    op.add_column('companies', sa.Column('crm_owner_id', sa.String(64), nullable=True))
    op.add_column('companies', sa.Column('crm_owner_name', sa.String(255), nullable=True))
    op.add_column('companies', sa.Column('crm_owner_email', sa.String(255), nullable=True))
    op.add_column('companies', sa.Column('crm_status', sa.String(100), nullable=True))
    op.add_column('companies', sa.Column('crm_modified_at', TZ, nullable=True))
    op.add_column('companies', sa.Column('crm_synced_at', TZ, nullable=True))
    op.add_column('companies', sa.Column('crm_deleted_at', TZ, nullable=True))
    op.create_unique_constraint('uq_companies_bigin_account_id', 'companies', ['bigin_account_id'])

    op.add_column('contacts', sa.Column('bigin_contact_id', sa.String(64), nullable=True))
    op.add_column('contacts', sa.Column('crm_owner_id', sa.String(64), nullable=True))
    op.add_column('contacts', sa.Column('crm_owner_name', sa.String(255), nullable=True))
    op.add_column('contacts', sa.Column('crm_modified_at', TZ, nullable=True))
    op.add_column('contacts', sa.Column('crm_synced_at', TZ, nullable=True))
    op.add_column('contacts', sa.Column('crm_deleted_at', TZ, nullable=True))
    op.create_unique_constraint('uq_contacts_bigin_contact_id', 'contacts', ['bigin_contact_id'])

    # -------------------------------------------------------------- Bigin sync
    op.create_table(
        'bigin_sync_state',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('accounts_watermark', TZ, nullable=True),
        sa.Column('contacts_watermark', TZ, nullable=True),
        sa.Column('last_full_sync_at', TZ, nullable=True),
        sa.Column('last_success_at', TZ, nullable=True),
        sa.Column('last_attempt_at', TZ, nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('connection_ok', sa.Boolean(), nullable=False),
        sa.Column('connection_checked_at', TZ, nullable=True),
        sa.Column('connection_error', sa.Text(), nullable=True),
        sa.Column('channel_id', sa.String(32), nullable=True),
        sa.Column('channel_token', sa.String(64), nullable=True),
        sa.Column('channel_expires_at', TZ, nullable=True),
        sa.Column('channel_error', sa.Text(), nullable=True),
        sa.Column('last_notification_at', TZ, nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
    )

    sync_trigger = postgresql.ENUM('MANUAL', 'SCHEDULED', 'WEBHOOK', name='sync_trigger', create_type=False)
    sync_run_status = postgresql.ENUM('RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED', name='sync_run_status', create_type=False)
    sync_trigger.create(op.get_bind(), checkfirst=True)
    sync_run_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'bigin_sync_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('trigger', sync_trigger, nullable=False),
        sa.Column('full', sa.Boolean(), nullable=False),
        sa.Column('status', sync_run_status, nullable=False),
        sa.Column('triggered_by_id', sa.UUID(), nullable=True),
        sa.Column('started_at', TZ, server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', TZ, nullable=True),
        sa.Column('companies_created', sa.Integer(), nullable=False),
        sa.Column('companies_updated', sa.Integer(), nullable=False),
        sa.Column('contacts_created', sa.Integer(), nullable=False),
        sa.Column('contacts_updated', sa.Integer(), nullable=False),
        sa.Column('records_deleted', sa.Integer(), nullable=False),
        sa.Column('records_skipped', sa.Integer(), nullable=False),
        sa.Column('addresses_changed', sa.Integer(), nullable=False),
        sa.Column('locations_verified', sa.Integer(), nullable=False),
        sa.Column('locations_needs_review', sa.Integer(), nullable=False),
        sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['triggered_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ----------------------------------------------------- Business research
    research_status = postgresql.ENUM(
        'PENDING', 'RESEARCHING', 'SUMMARIZING', 'COMPLETED', 'FAILED', name='research_status', create_type=False
    )
    research_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'company_research',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('status', research_status, nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('sam_it_relevance', sa.Text(), nullable=True),
        sa.Column('industry', sa.String(255), nullable=True),
        sa.Column('confidence', sa.String(20), nullable=True),
        sa.Column('summary_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('research_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('provider', sa.String(50), nullable=True),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('requested_by_id', sa.UUID(), nullable=True),
        sa.Column('researched_at', TZ, nullable=True),
        sa.Column('generated_at', TZ, nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requested_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id'),
    )
    op.create_table(
        'company_research_sources',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('research_id', sa.UUID(), nullable=False),
        sa.Column('ref', sa.String(10), nullable=False),
        sa.Column('source_type', sa.String(30), nullable=False),
        sa.Column('url', sa.String(2000), nullable=True),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('fetched_at', TZ, nullable=True),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(['research_id'], ['company_research.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_company_research_sources_research_id', 'company_research_sources', ['research_id'])

    # ---------------------------------------------------- Meeting recordings
    recording_status = postgresql.ENUM(
        'UPLOADING', 'PROCESSING', 'COMPLETED', 'FAILED', name='recording_status', create_type=False
    )
    recording_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'meeting_recordings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('meeting_id', sa.UUID(), nullable=False),
        sa.Column('created_by_id', sa.UUID(), nullable=True),
        sa.Column('status', recording_status, nullable=False),
        sa.Column('storage_backend', sa.String(20), nullable=True),
        sa.Column('storage_key', sa.String(500), nullable=True),
        sa.Column('content_type', sa.String(100), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('provider', sa.String(50), nullable=True),
        sa.Column('provider_job_id', sa.String(255), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('uploaded_at', TZ, nullable=True),
        sa.Column('submitted_at', TZ, nullable=True),
        sa.Column('completed_at', TZ, nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_meeting_recordings_meeting_id', 'meeting_recordings', ['meeting_id'])
    op.create_table(
        'meeting_transcripts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('recording_id', sa.UUID(), nullable=False),
        sa.Column('meeting_id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('language', sa.String(20), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('segments', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('speaker_count', sa.Integer(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(['recording_id'], ['meeting_recordings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('recording_id'),
    )
    op.create_index('ix_meeting_transcripts_meeting_id', 'meeting_transcripts', ['meeting_id'])


def downgrade() -> None:
    op.drop_index('ix_meeting_transcripts_meeting_id', table_name='meeting_transcripts')
    op.drop_table('meeting_transcripts')
    op.drop_index('ix_meeting_recordings_meeting_id', table_name='meeting_recordings')
    op.drop_table('meeting_recordings')
    op.drop_index('ix_company_research_sources_research_id', table_name='company_research_sources')
    op.drop_table('company_research_sources')
    op.drop_table('company_research')
    op.drop_table('bigin_sync_runs')
    op.drop_table('bigin_sync_state')
    for enum_name in ('recording_status', 'research_status', 'sync_run_status', 'sync_trigger'):
        postgresql.ENUM(name=enum_name).drop(op.get_bind(), checkfirst=True)

    op.drop_constraint('uq_contacts_bigin_contact_id', 'contacts', type_='unique')
    for col in ('crm_deleted_at', 'crm_synced_at', 'crm_modified_at', 'crm_owner_name', 'crm_owner_id', 'bigin_contact_id'):
        op.drop_column('contacts', col)
    op.drop_constraint('uq_companies_bigin_account_id', 'companies', type_='unique')
    for col in ('crm_deleted_at', 'crm_synced_at', 'crm_modified_at', 'crm_status', 'crm_owner_email',
                'crm_owner_name', 'crm_owner_id', 'bigin_account_id'):
        op.drop_column('companies', col)
