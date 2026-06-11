"""SQLite state for Ad Studio (jobs, tracker, activity log).

Single connection in WAL mode guarded by a lock — request handlers are sync
(FastAPI runs them in a threadpool) and the job worker writes from the event
loop thread, so cross-thread access is real.
"""
from __future__ import annotations

import sqlite3
import threading

from .config import STATE_DIR

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  kind          TEXT NOT NULL DEFAULT 'generate',
  mode          TEXT NOT NULL DEFAULT 'full',
  pipeline      TEXT NOT NULL,
  competitor    TEXT NOT NULL,
  ad_id         TEXT NOT NULL,
  media_type    TEXT,
  status        TEXT NOT NULL DEFAULT 'queued',
  current_step  TEXT,
  step_attempt  INTEGER NOT NULL DEFAULT 0,
  requested_by  TEXT,
  force_regen   INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  started_at    TEXT,
  finished_at   TEXT,
  cost_estimate_usd REAL,
  estimate_json TEXT,
  rewrite_short_id  TEXT,
  error         TEXT,
  stderr_tail   TEXT,
  rewrite_gdoc_url  TEXT,
  analysis_gdoc_url TEXT,
  rewrite_html_url  TEXT,
  needs_push    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_jobs_ad ON jobs (pipeline, competitor, ad_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);

CREATE TABLE IF NOT EXISTS job_events (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id  INTEGER NOT NULL,
  ts      TEXT NOT NULL DEFAULT (datetime('now')),
  step    TEXT,
  line    TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events (job_id, id);

CREATE TABLE IF NOT EXISTS tracker (
  pipeline    TEXT NOT NULL,
  competitor  TEXT NOT NULL,
  ad_id       TEXT NOT NULL,
  status      TEXT NOT NULL,
  claimed_by  TEXT,
  requested_by TEXT,
  verdict_at_shortlist TEXT,
  notes       TEXT,
  final_video_url TEXT,
  rewrite_gdoc_url  TEXT,
  analysis_gdoc_url TEXT,
  rewrite_html_url  TEXT,
  imported    INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
  script_ready_at TEXT,
  PRIMARY KEY (pipeline, competitor, ad_id)
);

CREATE TABLE IF NOT EXISTS activity (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  ts     TEXT NOT NULL DEFAULT (datetime('now')),
  pipeline TEXT, competitor TEXT, ad_id TEXT,
  who    TEXT,
  action TEXT,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_activity_ad ON activity (pipeline, competitor, ad_id, id);
"""

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(STATE_DIR / "studio.db", check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(_SCHEMA)
        # migrate older DBs that predate the `kind` column
        cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)").fetchall()}
        if "kind" not in cols:
            c.execute("ALTER TABLE jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'generate'")
            c.commit()
        if "mode" not in cols:
            c.execute("ALTER TABLE jobs ADD COLUMN mode TEXT NOT NULL DEFAULT 'full'")
            c.commit()
        _conn = c
    return _conn


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    with _lock:
        cur = conn().execute(sql, params)
        conn().commit()
        return cur


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        return conn().execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    rows = query(sql, params)
    return rows[0] if rows else None
