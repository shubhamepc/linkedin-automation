import sqlite3
from datetime import datetime, timedelta

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    url           TEXT PRIMARY KEY,
    name          TEXT,
    headline      TEXT,
    niche         TEXT,
    source_query  TEXT,
    status        TEXT NOT NULL DEFAULT 'new',
    -- new | low_score | not_connectable | sent | accepted | withdrawn | error
    score         INTEGER,
    reason        TEXT,
    note          TEXT,
    discovered_at TEXT,
    visited_at    TEXT,
    sent_at       TEXT,
    updated_at    TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day         TEXT,
    started_at  TEXT,
    finished_at TEXT,
    quota       INTEGER,
    visited     INTEGER DEFAULT 0,
    sent        INTEGER DEFAULT 0,
    summary     TEXT
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ---- key/value ----
    def get(self, key, default=None):
        row = self.conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key, value):
        self.conn.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, str(value)))
        self.conn.commit()

    # ---- profiles ----
    def add_candidates(self, urls, source_query) -> int:
        added = 0
        for url in urls:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO profiles (url, source_query, discovered_at, updated_at) VALUES (?,?,?,?)",
                (url, source_query, now(), now()),
            )
            added += cur.rowcount
        self.conn.commit()
        return added

    def next_candidates(self, limit):
        return [r["url"] for r in self.conn.execute(
            "SELECT url FROM profiles WHERE status='new' ORDER BY discovered_at LIMIT ?", (limit,))]

    def update_profile(self, url, **fields):
        fields["updated_at"] = now()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE profiles SET {cols} WHERE url=?", (*fields.values(), url))
        self.conn.commit()

    def sent_in_last_days(self, days) -> int:
        since = (datetime.now() - timedelta(days=days)).isoformat()
        return self.conn.execute(
            "SELECT COUNT(*) FROM profiles WHERE sent_at >= ?", (since,)).fetchone()[0]

    def sent_since(self, iso_day: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM profiles WHERE sent_at >= ?", (iso_day,)).fetchone()[0]

    def first_sent_at(self):
        return self.conn.execute("SELECT MIN(sent_at) FROM profiles").fetchone()[0]

    def stale_pending(self, older_than_days, limit):
        cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat()
        return [r["url"] for r in self.conn.execute(
            "SELECT url FROM profiles WHERE status='sent' AND sent_at < ? ORDER BY sent_at LIMIT ?",
            (cutoff, limit))]

    def mark_accepted(self, urls) -> int:
        n = 0
        for url in urls:
            n += self.conn.execute(
                "UPDATE profiles SET status='accepted', updated_at=? WHERE url=? AND status IN ('sent','withdrawn')",
                (now(), url)).rowcount
        self.conn.commit()
        return n

    def acceptance_stats(self, min_age_days=7):
        """Only count invites at least min_age_days old (people have had time to respond)."""
        cutoff = (datetime.now() - timedelta(days=min_age_days)).isoformat()
        row = self.conn.execute(
            "SELECT COUNT(*) AS total, SUM(status='accepted') AS acc FROM profiles "
            "WHERE sent_at IS NOT NULL AND sent_at < ?", (cutoff,)).fetchone()
        return row["total"] or 0, row["acc"] or 0

    def status_counts(self):
        return {r["status"]: r["n"] for r in self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM profiles GROUP BY status")}

    # ---- runs ----
    def ran_today(self, day) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM runs WHERE day=? AND finished_at IS NOT NULL", (day,)).fetchone() is not None

    def start_run(self, day, quota) -> int:
        cur = self.conn.execute("INSERT INTO runs (day, started_at, quota) VALUES (?,?,?)",
                                (day, now(), quota))
        self.conn.commit()
        return cur.lastrowid

    def finish_run(self, run_id, visited, sent, summary, completed=True):
        """completed=False (login/AI/browser problem): record it, but today's run can still happen later."""
        self.conn.execute("UPDATE runs SET finished_at=?, visited=?, sent=?, summary=? WHERE id=?",
                          (now() if completed else None, visited, sent, summary, run_id))
        self.conn.commit()

    def recent_runs(self, n=10):
        return self.conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (n,)).fetchall()
