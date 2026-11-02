from dataclasses import dataclass, field, fields


def _parse_int_list(text) -> list[int]:
    if text is None:
        return []
    if isinstance(text, (list, tuple, set)):
        return sorted(int(x) for x in text)
    return sorted(int(x) for x in str(text).replace(";", ",").split(",") if str(x).strip() != "")


def _format_int_list(values) -> str:
    return ",".join(str(v) for v in sorted(set(values)))


class RowModel:
    @classmethod
    def from_row(cls, row):
        names = {f.name for f in fields(cls)}
        data = {k: row[k] for k in row.keys() if k in names}
        return cls(**data)


@dataclass
class Subject(RowModel):
    id: int | None = None
    name: str = ""
    short_name: str = ""
    default_hours: int = 2
    grade: int | None = None
    alan: str = ""
    dal: str = ""
    brans: str = ""
    difficulty: int = 0
    physical: int = 0
    preferred_time: str = "any"
    room_type: str = ""
    room_required: int = 0
    min_block: int = 1
    max_block: int = 2
    allowed_splits: str = ""
    forbidden_splits: str = ""
    preferred_split: str = ""
    allow_same_day: int = 0
    elective: int = 0
    vocational: int = 0
    color: str = ""
    external: int = 0

    @property
    def label(self) -> str:
        return self.short_name or self.name


@dataclass
class Curriculum(RowModel):
    id: int | None = None
    name: str = ""
    grade: int | None = None
    alan: str = ""
    dal: str = ""
    program_type: str = ""
    notes: str = ""


@dataclass
class CurriculumItem(RowModel):
    id: int | None = None
    curriculum_id: int = 0
    subject_id: int = 0
    hours: int = 0


@dataclass
class Teacher(RowModel):
    id: int | None = None
    name: str = ""
    brans: str = ""
    max_daily: int = 8
    max_weekly: int = 30
    min_weekly: int = 0
    max_consecutive: int = 6
    preferred_days: str = ""
    notes: str = ""
    subject_ids: list[int] = field(default_factory=list)

    @property
    def preferred_day_list(self) -> list[int]:
        return _parse_int_list(self.preferred_days)


@dataclass
class Room(RowModel):
    id: int | None = None
    name: str = ""
    room_type: str = "Derslik"
    capacity: int = 0
    equipment: str = ""
    alan: str = ""
    notes: str = ""
    max_parallel: int = 1
    subject_ids: list[int] = field(default_factory=list)


@dataclass
class SchoolClass(RowModel):
    id: int | None = None
    name: str = ""
    grade: int = 9
    alan: str = ""
    dal: str = ""
    program_type: str = "Anadolu Meslek Programı"
    curriculum_id: int | None = None
    home_room_id: int | None = None
    student_count: int = 0
    weekly_hours: int = 0
    max_daily: int = 0
    available_days: str = "0,1,2,3,4"
    notes: str = ""
    parent_id: int | None = None

    @property
    def day_list(self) -> list[int]:
        return _parse_int_list(self.available_days)


@dataclass
class Timetable(RowModel):
    id: int | None = None
    name: str = ""
    created_at: str = ""
    source: str = "auto"
    status: str = ""
    objective: float | None = None
    solve_seconds: float | None = None
    notes: str = ""
    is_active: int = 0


@dataclass
class Entry(RowModel):
    id: int | None = None
    timetable_id: int | None = None
    class_id: int = 0
    subject_id: int = 0
    teacher_id: int | None = None
    room_id: int | None = None
    day: int = 0
    period: int = 0
    block: int = 0
    locked: int = 0
    extra_teachers: str = ""
    extra_rooms: str = ""
    link: int = 0

    @property
    def teacher_ids(self) -> list[int]:
        ids = [self.teacher_id] if self.teacher_id is not None else []
        return ids + [i for i in _parse_int_list(self.extra_teachers) if i not in ids]

    @property
    def room_ids(self) -> list[int]:
        ids = [self.room_id] if self.room_id is not None else []
        return ids + [i for i in _parse_int_list(self.extra_rooms) if i not in ids]


parse_int_list = _parse_int_list
format_int_list = _format_int_list
