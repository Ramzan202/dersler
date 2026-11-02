from dataclasses import asdict, fields

from app.database.database import Database


class CrudService:
    table: str = ""
    model = None
    extra_fields: set[str] = set()
    order_by: str = "name COLLATE NOCASE"

    def __init__(self, db: Database):
        self.db = db

    def _columns(self) -> list[str]:
        return [f.name for f in fields(self.model) if f.name not in ("id",) and f.name not in self.extra_fields]

    def list(self):
        rows = self.db.query(f"SELECT * FROM {self.table} ORDER BY {self.order_by}")
        return [self._load(self.model.from_row(r)) for r in rows]

    def get(self, item_id: int):
        row = self.db.query_one(f"SELECT * FROM {self.table} WHERE id = ?", (item_id,))
        return self._load(self.model.from_row(row)) if row else None

    def get_by_name(self, name: str):
        row = self.db.query_one(f"SELECT * FROM {self.table} WHERE name = ?", (name,))
        return self._load(self.model.from_row(row)) if row else None

    def _load(self, obj):
        return obj

    def _validate(self, obj):
        if not str(getattr(obj, "name", "")).strip():
            raise ValueError("Ad alanı boş bırakılamaz.")

    def save(self, obj):
        self._validate(obj)
        obj.name = obj.name.strip()
        cols = self._columns()
        data = asdict(obj)
        values = [data[c] for c in cols]
        with self.db.transaction() as conn:
            existing = conn.execute(f"SELECT id FROM {self.table} WHERE name = ?", (obj.name,)).fetchone()
            if existing and existing["id"] != obj.id:
                raise ValueError(f"'{obj.name}' adında bir kayıt zaten var.")
            if obj.id is None:
                cur = conn.execute(
                    f"INSERT INTO {self.table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", values
                )
                obj.id = cur.lastrowid
            else:
                conn.execute(
                    f"UPDATE {self.table} SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?", values + [obj.id]
                )
            self._save_relations(conn, obj)
        return obj

    def _save_relations(self, conn, obj):
        pass

    def delete(self, item_id: int):
        with self.db.transaction() as conn:
            self._delete_relations(conn, item_id)
            conn.execute(f"DELETE FROM {self.table} WHERE id = ?", (item_id,))

    def _delete_relations(self, conn, item_id):
        pass

    def count(self) -> int:
        return self.db.query_one(f"SELECT COUNT(*) AS n FROM {self.table}")["n"]


class AvailabilityMixin:
    entity_type: str = ""

    def get_unavailable(self, entity_id: int) -> set[tuple[int, int]]:
        rows = self.db.query(
            "SELECT day, period FROM unavailability WHERE entity_type = ? AND entity_id = ?",
            (self.entity_type, entity_id),
        )
        return {(r["day"], r["period"]) for r in rows}

    def set_unavailable(self, entity_id: int, slots):
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM unavailability WHERE entity_type = ? AND entity_id = ?", (self.entity_type, entity_id)
            )
            conn.executemany(
                "INSERT INTO unavailability(entity_type, entity_id, day, period) VALUES (?, ?, ?, ?)",
                [(self.entity_type, entity_id, d, p) for d, p in sorted(set(slots))],
            )

    def _delete_relations(self, conn, item_id):
        conn.execute("DELETE FROM unavailability WHERE entity_type = ? AND entity_id = ?", (self.entity_type, item_id))
