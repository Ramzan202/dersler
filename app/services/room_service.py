from app.database.models import Room
from app.services.base import AvailabilityMixin, CrudService


class RoomService(AvailabilityMixin, CrudService):
    table = "rooms"
    model = Room
    entity_type = "room"
    extra_fields = {"subject_ids"}

    def _load(self, obj: Room):
        rows = self.db.query("SELECT subject_id FROM room_subjects WHERE room_id = ?", (obj.id,))
        obj.subject_ids = [r["subject_id"] for r in rows]
        return obj

    def _validate(self, obj: Room):
        super()._validate(obj)
        if obj.capacity < 0:
            raise ValueError("Kapasite negatif olamaz.")
        if obj.max_parallel < 1:
            raise ValueError("'Aynı anda en fazla ders' en az 1 olmalıdır.")

    def _save_relations(self, conn, obj: Room):
        conn.execute("DELETE FROM room_subjects WHERE room_id = ?", (obj.id,))
        conn.executemany("INSERT INTO room_subjects(room_id, subject_id) VALUES (?, ?)",
                         [(obj.id, s) for s in set(obj.subject_ids)])

    def room_types(self) -> list[str]:
        from app.config import ROOM_TYPES
        rows = self.db.query("SELECT DISTINCT room_type FROM rooms ORDER BY room_type")
        return sorted(set(ROOM_TYPES) | {r["room_type"] for r in rows if r["room_type"]})

    def assigned_class(self, room_id: int) -> str:
        row = self.db.query_one("SELECT name FROM classes WHERE home_room_id = ? ORDER BY name", (room_id,))
        return row["name"] if row else ""
