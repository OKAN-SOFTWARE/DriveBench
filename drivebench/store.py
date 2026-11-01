from __future__ import annotations
import json
from pathlib import Path
import sqlite3
import threading
from .protocol import utc_now


class RunStore:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False, timeout=5)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, status TEXT NOT NULL, started_at TEXT NOT NULL, payload TEXT NOT NULL)")
        with self.lock, self.connection:
            for identifier, payload in self.connection.execute("SELECT id,payload FROM runs WHERE status='running'").fetchall():
                run = json.loads(payload)
                run.update(status="interrupted", finished_at=utc_now(), error="Application stopped before this run completed")
                self.connection.execute("UPDATE runs SET status=?,payload=? WHERE id=?", ("interrupted", json.dumps(run), identifier))

    def save(self, run):
        payload = json.dumps(run, allow_nan=False)
        if len(payload.encode()) > 2 * 1024 * 1024:
            raise ValueError("Run report exceeds the 2 MiB storage limit")
        with self.lock, self.connection:
            self.connection.execute("INSERT INTO runs(id,status,started_at,payload) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,payload=excluded.payload", (run["id"],run["status"],run["started_at"],payload))
            self.connection.execute("DELETE FROM runs WHERE status!='running' AND id NOT IN (SELECT id FROM runs WHERE status!='running' ORDER BY started_at DESC LIMIT 50)")

    def get(self, identifier):
        with self.lock:
            row = self.connection.execute("SELECT payload FROM runs WHERE id=?", (identifier,)).fetchone()
        return json.loads(row[0]) if row else None

    def history(self):
        with self.lock:
            rows = self.connection.execute("SELECT payload FROM runs ORDER BY started_at DESC LIMIT 50").fetchall()
        result = []
        for row in rows:
            run = json.loads(row[0])
            result.append({k: run.get(k) for k in ["id","scenario","name","status","started_at","finished_at","duration_ms","passed","failed","current_scenario"]})
        return result

    def close(self):
        with self.lock: self.connection.close()
