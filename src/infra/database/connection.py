import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from ...config import settings

logger = logging.getLogger(__name__)

DB_PATH = Path(settings.database_url.replace("sqlite:///", ""))


def init_db() -> None:
    """Cria as tabelas se não existirem. Chamado no startup da aplicação."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(_SCHEMA_SQL)
        # Migration: add status column if not exists
        try:
            conn.execute("ALTER TABLE groups ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
        except Exception:
            pass  # Column already exists
        # Migration: remove UNIQUE constraint workaround - allow multiple rows per phone
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_phone ON groups(whatsapp_number)")
        except Exception:
            pass
    logger.info("Database initialized at %s", DB_PATH)


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS groups (
    group_id        TEXT PRIMARY KEY,
    whatsapp_number TEXT NOT NULL,
    park_id         TEXT NOT NULL,
    visit_date      TEXT NOT NULL,
    language        TEXT NOT NULL DEFAULT 'pt-BR',
    profile_id      TEXT,
    setup_complete  INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
    member_id    TEXT PRIMARY KEY,
    group_id     TEXT NOT NULL REFERENCES groups(group_id),
    role         TEXT NOT NULL,
    age          INTEGER,
    height_cm    INTEGER,
    name         TEXT,
    fear_of_dark INTEGER NOT NULL DEFAULT 0,
    fear_of_heights INTEGER NOT NULL DEFAULT 0,
    motion_sickness INTEGER NOT NULL DEFAULT 0,
    mobility_restricted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS group_preferences (
    pref_id                TEXT PRIMARY KEY,
    group_id               TEXT NOT NULL UNIQUE REFERENCES groups(group_id),
    intensity_preference   TEXT NOT NULL DEFAULT 'moderate',
    priority_order         TEXT NOT NULL DEFAULT '[]',
    avoid_types            TEXT NOT NULL DEFAULT '[]',
    max_queue_minutes      INTEGER NOT NULL DEFAULT 45,
    must_do_attractions    TEXT NOT NULL DEFAULT '[]',
    skip_attractions       TEXT NOT NULL DEFAULT '[]',
    show_interest          INTEGER NOT NULL DEFAULT 1,
    meal_break_times       TEXT NOT NULL DEFAULT '[]',
    allow_group_split      INTEGER NOT NULL DEFAULT 0,
    updated_at             TEXT
);

CREATE TABLE IF NOT EXISTS operational_contexts (
    context_id            TEXT PRIMARY KEY,
    group_id              TEXT NOT NULL REFERENCES groups(group_id),
    current_park_id       TEXT NOT NULL,
    current_datetime      TEXT NOT NULL,
    current_location_area TEXT NOT NULL,
    queue_snapshot        TEXT NOT NULL DEFAULT '{}',
    queue_snapshot_at     TEXT,
    done_attractions      TEXT NOT NULL DEFAULT '[]',
    closed_attractions    TEXT NOT NULL DEFAULT '[]',
    active_states         TEXT NOT NULL DEFAULT '[]',
    filter_override       TEXT,
    weather               TEXT,
    crowd_level           TEXT,
    special_event         TEXT,
    expires_at            TEXT
);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id   TEXT PRIMARY KEY,
    group_id            TEXT NOT NULL REFERENCES groups(group_id),
    context_id          TEXT NOT NULL,
    generated_at        TEXT NOT NULL,
    primary_attraction  TEXT NOT NULL,
    primary_score       REAL NOT NULL,
    secondary_attraction TEXT,
    secondary_score     REAL,
    score_breakdown     TEXT,
    filters_applied     TEXT NOT NULL DEFAULT '[]',
    candidates_evaluated INTEGER NOT NULL DEFAULT 0,
    user_message        TEXT NOT NULL DEFAULT '',
    whatsapp_message    TEXT
);
"""
