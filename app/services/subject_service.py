from app.core.splits import parse_pattern_list
from app.database.models import Curriculum, CurriculumItem, Subject
from app.services.base import CrudService


class SubjectService(CrudService):
    table = "subjects"
    model = Subject

    def _validate(self, obj: Subject):
        super()._validate(obj)
        if obj.default_hours < 0:
            raise ValueError("Haftalık ders saati negatif olamaz.")
        if obj.min_block < 1 or obj.max_block < obj.min_block:
            raise ValueError("Blok uzunlukları hatalı: en az 1 olmalı ve en büyük blok en küçükten küçük olamaz.")
        for label, text in (("İzin verilen", obj.allowed_splits), ("Yasaklı", obj.forbidden_splits),
                            ("Tercih edilen", obj.preferred_split)):
            try:
                parse_pattern_list(text)
            except ValueError:
                raise ValueError(f"{label} bölünme biçimi hatalı: '{text}'. Örnek: 3+3+3; 2+2+2+3")

    def teacher_ids(self, subject_id: int) -> list[int]:
        rows = self.db.query("SELECT teacher_id FROM teacher_subjects WHERE subject_id = ?", (subject_id,))
        return [r["teacher_id"] for r in rows]

    def set_teachers(self, subject_id: int, teacher_ids):
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM teacher_subjects WHERE subject_id = ?", (subject_id,))
            conn.executemany("INSERT INTO teacher_subjects(teacher_id, subject_id) VALUES (?, ?)",
                             [(t, subject_id) for t in set(teacher_ids)])

    def room_ids(self, subject_id: int) -> list[int]:
        rows = self.db.query("SELECT room_id FROM room_subjects WHERE subject_id = ?", (subject_id,))
        return [r["room_id"] for r in rows]

    def set_rooms(self, subject_id: int, room_ids):
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM room_subjects WHERE subject_id = ?", (subject_id,))
            conn.executemany("INSERT INTO room_subjects(room_id, subject_id) VALUES (?, ?)",
                             [(r, subject_id) for r in set(room_ids)])


class CurriculumService(CrudService):
    table = "curricula"
    model = Curriculum
    order_by = "grade, name COLLATE NOCASE"

    def items(self, curriculum_id: int) -> list[CurriculumItem]:
        rows = self.db.query(
            "SELECT ci.* FROM curriculum_items ci JOIN subjects s ON s.id = ci.subject_id "
            "WHERE ci.curriculum_id = ? ORDER BY ci.id", (curriculum_id,))
        return [CurriculumItem.from_row(r) for r in rows]

    def total_hours(self, curriculum_id: int) -> int:
        row = self.db.query_one("SELECT COALESCE(SUM(hours), 0) AS n FROM curriculum_items WHERE curriculum_id = ?",
                                (curriculum_id,))
        return row["n"]

    def set_item(self, curriculum_id: int, subject_id: int, hours: int):
        if hours < 0:
            raise ValueError("Ders saati negatif olamaz.")
        with self.db.transaction() as conn:
            if hours == 0:
                conn.execute("DELETE FROM curriculum_items WHERE curriculum_id = ? AND subject_id = ?",
                             (curriculum_id, subject_id))
            else:
                conn.execute(
                    "INSERT INTO curriculum_items(curriculum_id, subject_id, hours) VALUES (?, ?, ?) "
                    "ON CONFLICT(curriculum_id, subject_id) DO UPDATE SET hours = excluded.hours",
                    (curriculum_id, subject_id, hours))

    def remove_item(self, curriculum_id: int, subject_id: int):
        self.set_item(curriculum_id, subject_id, 0)

    def duplicate(self, curriculum_id: int, new_name: str) -> Curriculum:
        src = self.get(curriculum_id)
        copy = Curriculum(name=new_name, grade=src.grade, alan=src.alan, dal=src.dal,
                          program_type=src.program_type, notes=src.notes)
        self.save(copy)
        for item in self.items(curriculum_id):
            self.set_item(copy.id, item.subject_id, item.hours)
        return copy
