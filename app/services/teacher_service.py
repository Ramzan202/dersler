from app.database.models import Teacher
from app.services.base import AvailabilityMixin, CrudService


class TeacherService(AvailabilityMixin, CrudService):
    table = "teachers"
    model = Teacher
    entity_type = "teacher"
    extra_fields = {"subject_ids"}

    def _load(self, obj: Teacher):
        rows = self.db.query("SELECT subject_id FROM teacher_subjects WHERE teacher_id = ?", (obj.id,))
        obj.subject_ids = [r["subject_id"] for r in rows]
        return obj

    def _validate(self, obj: Teacher):
        super()._validate(obj)
        if obj.max_daily < 1 or obj.max_weekly < 1:
            raise ValueError("Günlük ve haftalık en fazla ders sayısı en az 1 olmalıdır.")
        if obj.min_weekly > obj.max_weekly:
            raise ValueError("Haftalık en az ders sayısı, en fazla ders sayısından büyük olamaz.")
        if obj.max_consecutive < 1:
            raise ValueError("Art arda en fazla ders sayısı en az 1 olmalıdır.")

    def _save_relations(self, conn, obj: Teacher):
        conn.execute("DELETE FROM teacher_subjects WHERE teacher_id = ?", (obj.id,))
        conn.executemany("INSERT INTO teacher_subjects(teacher_id, subject_id) VALUES (?, ?)",
                         [(obj.id, s) for s in set(obj.subject_ids)])

    def branches(self) -> list[str]:
        rows = self.db.query("SELECT DISTINCT brans FROM teachers WHERE brans <> '' ORDER BY brans")
        return [r["brans"] for r in rows]
