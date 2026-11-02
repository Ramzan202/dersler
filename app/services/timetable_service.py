from datetime import datetime

from app.database.models import Entry, Timetable
from app.services.base import CrudService


class TimetableService(CrudService):
    table = "timetables"
    model = Timetable
    order_by = "id DESC"

    def save(self, obj: Timetable):
        if not obj.created_at:
            obj.created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        cols = [c for c in self._columns()]
        values = [getattr(obj, c) for c in cols]
        with self.db.transaction() as conn:
            if obj.id is None:
                cur = conn.execute(
                    f"INSERT INTO timetables ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", values)
                obj.id = cur.lastrowid
            else:
                conn.execute(f"UPDATE timetables SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?",
                             values + [obj.id])
        return obj

    def create(self, name: str, entries: list[Entry], source: str = "auto", status: str = "",
               objective=None, solve_seconds=None, notes: str = "", activate: bool = True) -> Timetable:
        tt = Timetable(name=name, source=source, status=status, objective=objective,
                       solve_seconds=solve_seconds, notes=notes)
        self.save(tt)
        self.replace_entries(tt.id, entries)
        if activate:
            self.set_active(tt.id)
            tt.is_active = 1
        return tt

    def entries(self, timetable_id: int) -> list[Entry]:
        rows = self.db.query("SELECT * FROM timetable_entries WHERE timetable_id = ? ORDER BY day, period, class_id",
                             (timetable_id,))
        return [Entry.from_row(r) for r in rows]

    def replace_entries(self, timetable_id: int, entries: list[Entry]):
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM timetable_entries WHERE timetable_id = ?", (timetable_id,))
            conn.executemany(
                "INSERT INTO timetable_entries(timetable_id, class_id, subject_id, teacher_id, room_id, day, period, "
                "block, locked) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(timetable_id, e.class_id, e.subject_id, e.teacher_id, e.room_id, e.day, e.period, e.block,
                  e.locked) for e in entries])

    def add_entry(self, entry: Entry) -> Entry:
        entry.id = self.db.execute(
            "INSERT INTO timetable_entries(timetable_id, class_id, subject_id, teacher_id, room_id, day, period, "
            "block, locked) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry.timetable_id, entry.class_id, entry.subject_id, entry.teacher_id, entry.room_id, entry.day,
             entry.period, entry.block, entry.locked))
        self._mark_manual(entry.timetable_id)
        return entry

    def update_entry(self, entry: Entry):
        self.db.execute(
            "UPDATE timetable_entries SET class_id = ?, subject_id = ?, teacher_id = ?, room_id = ?, day = ?, "
            "period = ?, block = ?, locked = ? WHERE id = ?",
            (entry.class_id, entry.subject_id, entry.teacher_id, entry.room_id, entry.day, entry.period, entry.block,
             entry.locked, entry.id))
        self._mark_manual(entry.timetable_id)

    def delete_entry(self, entry_id: int, timetable_id: int | None = None):
        self.db.execute("DELETE FROM timetable_entries WHERE id = ?", (entry_id,))
        if timetable_id:
            self._mark_manual(timetable_id)

    def _mark_manual(self, timetable_id):
        if timetable_id:
            self.db.execute("UPDATE timetables SET source = CASE WHEN source LIKE '%+manuel' THEN source "
                            "ELSE source || '+manuel' END WHERE id = ?", (timetable_id,))

    def set_active(self, timetable_id: int):
        with self.db.transaction() as conn:
            conn.execute("UPDATE timetables SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END", (timetable_id,))

    def active(self) -> Timetable | None:
        row = self.db.query_one("SELECT * FROM timetables WHERE is_active = 1 ORDER BY id DESC LIMIT 1")
        if row is None:
            row = self.db.query_one("SELECT * FROM timetables ORDER BY id DESC LIMIT 1")
        return Timetable.from_row(row) if row else None

    def duplicate(self, timetable_id: int, new_name: str) -> Timetable:
        src = self.get(timetable_id)
        entries = self.entries(timetable_id)
        for e in entries:
            e.id = None
        return self.create(new_name, entries, source=src.source, status=src.status, objective=src.objective,
                           notes=f"'{src.name}' varyantından kopyalandı", activate=True)

    def rename(self, timetable_id: int, name: str):
        if not name.strip():
            raise ValueError("Varyant adı boş olamaz.")
        self.db.execute("UPDATE timetables SET name = ? WHERE id = ?", (name.strip(), timetable_id))

    def next_name(self, prefix: str = "Ders Programı") -> str:
        n = self.db.query_one("SELECT COUNT(*) AS n FROM timetables")["n"] + 1
        return f"{prefix} №{n}"
