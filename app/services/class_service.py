from dataclasses import dataclass

from app.database.models import SchoolClass, parse_int_list
from app.services.base import AvailabilityMixin, CrudService


@dataclass
class ClassLesson:
    class_id: int
    subject_id: int
    hours: int
    source: str
    fixed_teacher_id: int | None = None


class ClassService(AvailabilityMixin, CrudService):
    table = "classes"
    model = SchoolClass
    entity_type = "class"
    order_by = "grade, name COLLATE NOCASE"

    def _validate(self, obj: SchoolClass):
        super()._validate(obj)
        if not parse_int_list(obj.available_days):
            raise ValueError("Sınıf için en az bir okul günü seçilmelidir.")
        if obj.max_daily < 0 or obj.student_count < 0 or obj.weekly_hours < 0:
            raise ValueError("Sayısal alanlar negatif olamaz.")

    def _delete_relations(self, conn, item_id):
        super()._delete_relations(conn, item_id)

    def lessons(self, class_id: int) -> list[ClassLesson]:
        cls = self.get(class_id)
        if cls is None:
            return []
        result: dict[int, ClassLesson] = {}
        if cls.curriculum_id:
            for r in self.db.query("SELECT subject_id, hours FROM curriculum_items WHERE curriculum_id = ? ORDER BY id",
                                   (cls.curriculum_id,)):
                result[r["subject_id"]] = ClassLesson(class_id, r["subject_id"], r["hours"], "plan")
        for r in self.db.query("SELECT subject_id, hours FROM class_extra_lessons WHERE class_id = ?", (class_id,)):
            if r["hours"] <= 0:
                result.pop(r["subject_id"], None)
            else:
                result[r["subject_id"]] = ClassLesson(class_id, r["subject_id"], r["hours"], "ek")
        for r in self.db.query("SELECT subject_id, teacher_id FROM class_fixed_teachers WHERE class_id = ?", (class_id,)):
            if r["subject_id"] in result:
                result[r["subject_id"]].fixed_teacher_id = r["teacher_id"]
        return list(result.values())

    def total_hours(self, class_id: int) -> int:
        return sum(lesson.hours for lesson in self.lessons(class_id))

    def set_extra_lesson(self, class_id: int, subject_id: int, hours: int | None):
        with self.db.transaction() as conn:
            if hours is None:
                conn.execute("DELETE FROM class_extra_lessons WHERE class_id = ? AND subject_id = ?",
                             (class_id, subject_id))
            else:
                conn.execute(
                    "INSERT INTO class_extra_lessons(class_id, subject_id, hours) VALUES (?, ?, ?) "
                    "ON CONFLICT(class_id, subject_id) DO UPDATE SET hours = excluded.hours",
                    (class_id, subject_id, hours))

    def extra_lessons(self, class_id: int) -> dict[int, int]:
        rows = self.db.query("SELECT subject_id, hours FROM class_extra_lessons WHERE class_id = ?", (class_id,))
        return {r["subject_id"]: r["hours"] for r in rows}

    def set_fixed_teacher(self, class_id: int, subject_id: int, teacher_id: int | None):
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM class_fixed_teachers WHERE class_id = ? AND subject_id = ?",
                         (class_id, subject_id))
            if teacher_id:
                conn.execute("INSERT INTO class_fixed_teachers(class_id, subject_id, teacher_id) VALUES (?, ?, ?)",
                             (class_id, subject_id, teacher_id))

    def fixed_teachers(self, class_id: int) -> dict[int, int]:
        rows = self.db.query("SELECT subject_id, teacher_id FROM class_fixed_teachers WHERE class_id = ?", (class_id,))
        return {r["subject_id"]: r["teacher_id"] for r in rows}

    def alans(self) -> list[str]:
        rows = self.db.query("SELECT DISTINCT alan FROM classes WHERE alan <> '' UNION "
                             "SELECT DISTINCT alan FROM curricula WHERE alan <> '' ORDER BY 1")
        return [r[0] for r in rows]
