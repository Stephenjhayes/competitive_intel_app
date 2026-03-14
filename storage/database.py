"""
SQLite persistence layer.

Schema keeps 24 months of rolling competitive intelligence signals:
  - raw_events      : every scraped article / press release / filing
  - daily_snapshots : Claude-generated insight summaries per competitor per day
  - comparisons     : cross-competitor comparison reports
"""

import sqlite3
import json
from datetime import datetime, timedelta
from contextlib import contextmanager
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import DB_PATH, RETENTION_MONTHS


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist yet."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS raw_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_id   TEXT    NOT NULL,
            source_type     TEXT    NOT NULL,   -- press_room | blog | news | sec | careers
            url             TEXT,
            title           TEXT,
            content         TEXT,
            published_at    TEXT,               -- ISO-8601
            scraped_at      TEXT    NOT NULL,
            metadata        TEXT                -- JSON blob for extra fields
        );

        CREATE INDEX IF NOT EXISTS idx_raw_competitor ON raw_events(competitor_id, scraped_at);
        CREATE INDEX IF NOT EXISTS idx_raw_published  ON raw_events(published_at);

        CREATE TABLE IF NOT EXISTS daily_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date   TEXT    NOT NULL,   -- YYYY-MM-DD
            competitor_id   TEXT    NOT NULL,
            summary         TEXT    NOT NULL,   -- Claude-generated prose
            key_signals     TEXT    NOT NULL,   -- JSON list of bullet strings
            sentiment_score REAL,               -- -1.0 to 1.0
            created_at      TEXT    NOT NULL,
            UNIQUE(snapshot_date, competitor_id)
        );

        CREATE TABLE IF NOT EXISTS comparisons (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date     TEXT    NOT NULL,   -- YYYY-MM-DD
            period_months   INTEGER NOT NULL,   -- months of data covered
            narrative       TEXT    NOT NULL,   -- Claude-generated narrative
            insights        TEXT    NOT NULL,   -- JSON list of insight objects
            html_path       TEXT,               -- path to saved HTML report
            created_at      TEXT    NOT NULL,
            UNIQUE(report_date, period_months)
        );
        """)


def insert_raw_event(
    competitor_id: str,
    source_type: str,
    url: str,
    title: str,
    content: str,
    published_at: str | None = None,
    metadata: dict | None = None,
) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO raw_events
               (competitor_id, source_type, url, title, content,
                published_at, scraped_at, metadata)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                competitor_id,
                source_type,
                url,
                title,
                content,
                published_at,
                datetime.utcnow().isoformat(),
                json.dumps(metadata or {}),
            ),
        )
        return cursor.lastrowid


def upsert_daily_snapshot(
    snapshot_date: str,
    competitor_id: str,
    summary: str,
    key_signals: list[str],
    sentiment_score: float | None = None,
) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO daily_snapshots
               (snapshot_date, competitor_id, summary, key_signals,
                sentiment_score, created_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(snapshot_date, competitor_id)
               DO UPDATE SET
                   summary         = excluded.summary,
                   key_signals     = excluded.key_signals,
                   sentiment_score = excluded.sentiment_score,
                   created_at      = excluded.created_at""",
            (
                snapshot_date,
                competitor_id,
                summary,
                json.dumps(key_signals),
                sentiment_score,
                datetime.utcnow().isoformat(),
            ),
        )


def upsert_comparison(
    report_date: str,
    period_months: int,
    narrative: str,
    insights: list[dict],
    html_path: str | None = None,
) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO comparisons
               (report_date, period_months, narrative, insights, html_path, created_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(report_date, period_months)
               DO UPDATE SET
                   narrative  = excluded.narrative,
                   insights   = excluded.insights,
                   html_path  = excluded.html_path,
                   created_at = excluded.created_at""",
            (
                report_date,
                period_months,
                narrative,
                json.dumps(insights),
                html_path,
                datetime.utcnow().isoformat(),
            ),
        )


def get_events_since(
    competitor_id: str,
    days: int = 1,
    source_types: list[str] | None = None,
) -> list[sqlite3.Row]:
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    with get_db() as conn:
        if source_types:
            placeholders = ",".join("?" * len(source_types))
            rows = conn.execute(
                f"""SELECT * FROM raw_events
                    WHERE competitor_id=? AND scraped_at>=?
                      AND source_type IN ({placeholders})
                    ORDER BY scraped_at DESC""",
                [competitor_id, cutoff, *source_types],
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM raw_events
                   WHERE competitor_id=? AND scraped_at>=?
                   ORDER BY scraped_at DESC""",
                (competitor_id, cutoff),
            ).fetchall()
    return rows


def get_snapshots_range(
    competitor_id: str,
    start_date: str,
    end_date: str,
) -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            """SELECT * FROM daily_snapshots
               WHERE competitor_id=? AND snapshot_date BETWEEN ? AND ?
               ORDER BY snapshot_date""",
            (competitor_id, start_date, end_date),
        ).fetchall()


def get_all_snapshots_range(
    start_date: str,
    end_date: str,
) -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            """SELECT * FROM daily_snapshots
               WHERE snapshot_date BETWEEN ? AND ?
               ORDER BY competitor_id, snapshot_date""",
            (start_date, end_date),
        ).fetchall()


def purge_old_records() -> None:
    """Delete records older than RETENTION_MONTHS to keep the DB lean."""
    cutoff = (
        datetime.utcnow() - timedelta(days=RETENTION_MONTHS * 30)
    ).isoformat()
    with get_db() as conn:
        conn.execute("DELETE FROM raw_events WHERE scraped_at < ?", (cutoff,))
        conn.execute(
            "DELETE FROM daily_snapshots WHERE snapshot_date < ?",
            (cutoff[:10],),
        )
