"""weather cache: hourly conditions and per-session conditions

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-24 10:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weather_hours",
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("humidity", sa.Float(), nullable=True),
        sa.Column("dew_point", sa.Float(), nullable=True),
        sa.Column("apparent", sa.Float(), nullable=True),
        sa.Column("wind", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("lat", "lon", "ts"),
    )
    op.create_table(
        "activity_weather",
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("source_record_id", sa.String(length=64), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("humidity", sa.Float(), nullable=True),
        sa.Column("dew_point", sa.Float(), nullable=True),
        sa.Column("apparent", sa.Float(), nullable=True),
        sa.Column("wind", sa.Float(), nullable=True),
        sa.Column("final", sa.Boolean(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("source_id", "source_record_id"),
    )


def downgrade() -> None:
    op.drop_table("activity_weather")
    op.drop_table("weather_hours")
