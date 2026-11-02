from dataclasses import dataclass, field

from app.database.models import SchoolClass, parse_int_list
from app.services.base import AvailabilityMixin, CrudService


@dataclass
class ClassLesson:
    class_id: int
    subject_id: int
    hours: int
    source: str
    fixed_teacher_id: int | None = None
    teachers: list[int] = field(default_factory=list)
    rooms: list[int] = field(default_factory=list)
    room_mode: str = "any"
    link: str = ""
    split: str = ""

    @property
    def team(self) -> list[int]:
        """Teachers who all teach this lesson together (empty = chosen automatically)."""
        if self.teachers:
            return self.teachers
        return [self.fixed_teacher_id] if self.fixed_teacher_id else []


def parse_int_list_ordered(text) -> list[int]:
    out = []
    for x in str(text or "").replace(";", ",").split(","):
        x = x.strip()
        if x and int(x) not in out:
            out.append(int(x))
    return out


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
        for r in self.db.query("SELECT * FROM class_lesson_settings WHERE class_id = ?", (class_id,)):
            lesson = result.get(r["subject_id"])
            if lesson is not None:
                lesson.teachers = parse_int_list_ordered(r["teachers"])
                lesson.rooms = parse_int_list_ordered(r["rooms"])
                lesson.room_mode = r["room_mode"] or "any"
                lesson.link = r["link"] or ""
                lesson.split = r["split"] or ""
        return list(result.values())

    def set_lesson_settings(self, class_id: int, subject_id: int, teachers=(), rooms=(), room_mode: str = "any",
                            link: str = "", split: str = ""):
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO class_lesson_settings(class_id, subject_id, teachers, rooms, room_mode, link, split) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(class_id, subject_id) DO UPDATE SET "
                "teachers = excluded.teachers, rooms = excluded.rooms, room_mode = excluded.room_mode, "
                "link = excluded.link, split = excluded.split",
                (class_id, subject_id, ",".join(str(t) for t in teachers), ",".join(str(r) for r in rooms),
                 room_mode, link, split))

    def clear_lesson_settings(self, class_id: int, subject_id: int):
        self.db.execute("DELETE FROM class_lesson_settings WHERE class_id = ? AND subject_id = ?",
                        (class_id, subject_id))

    def groups(self, class_id: int) -> list[SchoolClass]:
        rows = self.db.query("SELECT * FROM classes WHERE parent_id = ? ORDER BY name", (class_id,))
        return [SchoolClass.from_row(r) for r in rows]

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
