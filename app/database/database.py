import json
import sqlite3
import threading
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from app import config
from app.database.migrations import migrate


class Database:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else config.DB_PATH
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = self._connect()
        migrate(self.conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL" if str(self.path) != ":memory:" else "PRAGMA journal_mode = MEMORY")
        return conn

    def close(self):
        with self._lock:
            self.conn.close()

    def reopen(self):
        with self._lock:
            self.conn = self._connect()
            migrate(self.conn)

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params=()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params=()) -> int:
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid

    @contextmanager
    def transaction(self):
        with self._lock:
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    def get_setting(self, key: str, default=None):
        row = self.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        if row is None:
            if default is not None:
                return default
            return deepcopy(config.DEFAULT_SETTINGS.get(key))
        return json.loads(row["value"])

    def set_setting(self, key: str, value):
        self.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )

    def all_settings(self) -> dict:
        result = deepcopy(config.DEFAULT_SETTINGS)
        for row in self.query("SELECT key, value FROM settings"):
            result[row["key"]] = json.loads(row["value"])
        weights = deepcopy(config.DEFAULT_SETTINGS["weights"])
        weights.update(result.get("weights") or {})
        result["weights"] = weights
        return result

    def is_empty(self) -> bool:
        row = self.query_one(
            "SELECT (SELECT COUNT(*) FROM classes) + (SELECT COUNT(*) FROM teachers) + (SELECT COUNT(*) FROM subjects) AS n"
        )
        return row["n"] == 0

    def backup_to(self, target: Path | str):
        with self._lock:
            dest = sqlite3.connect(str(target))
            try:
                self.conn.backup(dest)
            finally:
                dest.close()

    def restore_from(self, source: Path | str):
        source = Path(source)
        src = sqlite3.connect(str(source))
        try:
            check = src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='subjects'").fetchone()
            if check is None:
                raise ValueError("Seçilen dosya geçerli bir ders dağılım veritabanı değil.")
            with self._lock:
                src.backup(self.conn)
                migrate(self.conn)
        finally:
            src.close()
