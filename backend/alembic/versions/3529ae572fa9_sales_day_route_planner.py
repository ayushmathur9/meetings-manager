"""sales day route planner

Adds prospect priority, planner configuration/snapshot columns on routes, and
lets a route stop reference a company/location directly (meeting optional).
Existing stops are backfilled from their meetings.

Revision ID: 3529ae572fa9
Revises: 84ab1f77445b
Create Date: 2026-10-07 21:58:33.169399

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '3529ae572fa9'
down_revision: Union[str, None] = '84ab1f77445b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    prospect_priority = postgresql.ENUM('HIGH', 'MEDIUM', 'LOW', name='prospect_priority')
    prospect_priority.create(op.get_bind(), checkfirst=True)
    op.add_column('prospects', sa.Column('priority', postgresql.ENUM('HIGH', 'MEDIUM', 'LOW', name='prospect_priority', create_type=False), server_default='MEDIUM', nullable=False))
    op.add_column('route_stops', sa.Column('company_id', sa.UUID(), nullable=True))
    op.add_column('route_stops', sa.Column('location_id', sa.UUID(), nullable=True))
    op.add_column('route_stops', sa.Column('meeting_start', sa.Time(), nullable=True))
    op.add_column('route_stops', sa.Column('meeting_end', sa.Time(), nullable=True))
    op.add_column('route_stops', sa.Column('duration_minutes', sa.Integer(), nullable=True))
    op.add_column('route_stops', sa.Column('wait_seconds', sa.Integer(), nullable=True))
    op.add_column('route_stops', sa.Column('priority', sa.String(length=10), nullable=True))
    op.add_column('route_stops', sa.Column('is_fixed_time', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('route_stops', sa.Column('outside_hours', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('route_stops', sa.Column('company_name', sa.String(length=500), nullable=True))
    op.add_column('route_stops', sa.Column('address', sa.String(length=1000), nullable=True))
    op.add_column('route_stops', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('route_stops', sa.Column('longitude', sa.Float(), nullable=True))
    op.alter_column('route_stops', 'meeting_id',
               existing_type=sa.UUID(),
               nullable=True)
    op.drop_constraint('route_stops_meeting_id_fkey', 'route_stops', type_='foreignkey')
    op.create_foreign_key('route_stops_location_id_fkey', 'route_stops', 'locations', ['location_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('route_stops_meeting_id_fkey', 'route_stops', 'meetings', ['meeting_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('route_stops_company_id_fkey', 'route_stops', 'companies', ['company_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_route_stops_company_id', 'route_stops', ['company_id'])
    op.create_index('ix_routes_salesperson_date', 'routes', ['salesperson_id', 'date'])

    # Backfill existing stops from their meetings so old routes keep working.
    op.execute(
        """
        UPDATE route_stops rs
        SET company_id = m.company_id,
            location_id = m.location_id,
            meeting_start = rs.arrival_time,
            meeting_end = rs.departure_time,
            duration_minutes = m.duration_minutes,
            company_name = c.name,
            latitude = l.latitude,
            longitude = l.longitude
        FROM meetings m
        JOIN companies c ON c.id = m.company_id
        LEFT JOIN locations l ON l.id = m.location_id
        WHERE rs.meeting_id = m.id
        """
    )
    op.add_column('routes', sa.Column('name', sa.String(length=255), nullable=True))
    op.add_column('routes', sa.Column('end_mode', sa.String(length=20), nullable=True))
    op.add_column('routes', sa.Column('radius_miles', sa.Float(), nullable=True))
    op.add_column('routes', sa.Column('working_hours_start', sa.Time(), nullable=True))
    op.add_column('routes', sa.Column('working_hours_end', sa.Time(), nullable=True))
    op.add_column('routes', sa.Column('meeting_duration_minutes', sa.Integer(), nullable=True))
    op.add_column('routes', sa.Column('travel_buffer_minutes', sa.Integer(), nullable=True))
    op.add_column('routes', sa.Column('allow_overtime', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('routes', sa.Column('total_meeting_seconds', sa.Integer(), nullable=True))
    op.add_column('routes', sa.Column('total_duration_seconds', sa.Integer(), nullable=True))
    op.add_column('routes', sa.Column('return_travel_seconds', sa.Integer(), nullable=True))
    op.add_column('routes', sa.Column('return_distance_meters', sa.Float(), nullable=True))
    op.add_column('routes', sa.Column('geometry', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('routes', sa.Column('unscheduled', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('routes', sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('routes', sa.Column('optimization_engine', sa.String(length=50), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('routes', 'optimization_engine')
    op.drop_column('routes', 'warnings')
    op.drop_column('routes', 'unscheduled')
    op.drop_column('routes', 'geometry')
    op.drop_column('routes', 'return_distance_meters')
    op.drop_column('routes', 'return_travel_seconds')
    op.drop_column('routes', 'total_duration_seconds')
    op.drop_column('routes', 'total_meeting_seconds')
    op.drop_column('routes', 'allow_overtime')
    op.drop_column('routes', 'travel_buffer_minutes')
    op.drop_column('routes', 'meeting_duration_minutes')
    op.drop_column('routes', 'working_hours_end')
    op.drop_column('routes', 'working_hours_start')
    op.drop_column('routes', 'radius_miles')
    op.drop_column('routes', 'end_mode')
    op.drop_column('routes', 'name')
    op.drop_index('ix_routes_salesperson_date', table_name='routes')
    op.drop_index('ix_route_stops_company_id', table_name='route_stops')
    op.drop_constraint('route_stops_company_id_fkey', 'route_stops', type_='foreignkey')
    op.drop_constraint('route_stops_meeting_id_fkey', 'route_stops', type_='foreignkey')
    op.drop_constraint('route_stops_location_id_fkey', 'route_stops', type_='foreignkey')
    op.execute("DELETE FROM route_stops WHERE meeting_id IS NULL")
    op.create_foreign_key('route_stops_meeting_id_fkey', 'route_stops', 'meetings', ['meeting_id'], ['id'])
    op.alter_column('route_stops', 'meeting_id',
               existing_type=sa.UUID(),
               nullable=False)
    op.drop_column('route_stops', 'longitude')
    op.drop_column('route_stops', 'latitude')
    op.drop_column('route_stops', 'address')
    op.drop_column('route_stops', 'company_name')
    op.drop_column('route_stops', 'outside_hours')
    op.drop_column('route_stops', 'is_fixed_time')
    op.drop_column('route_stops', 'priority')
    op.drop_column('route_stops', 'wait_seconds')
    op.drop_column('route_stops', 'duration_minutes')
    op.drop_column('route_stops', 'meeting_end')
    op.drop_column('route_stops', 'meeting_start')
    op.drop_column('route_stops', 'location_id')
    op.drop_column('route_stops', 'company_id')
    op.drop_column('prospects', 'priority')
    postgresql.ENUM(name='prospect_priority').drop(op.get_bind(), checkfirst=True)
    # ### end Alembic commands ###
