from collections import defaultdict
from dataclasses import dataclass, field

from app.config import ALL_DAY_NAMES
from app.core.splits import Pattern, candidate_patterns, choose_preferred, format_pattern, parse_pattern
from app.database.database import Database
from app.database.models import Entry, Room, SchoolClass, Subject, Teacher, parse_int_list
from app.services.class_service import ClassService
from app.services.room_service import RoomService
from app.services.subject_service import SubjectService
from app.services.teacher_service import TeacherService

Slot = tuple[int, int]


@dataclass
class Lesson:
    index: int
    class_id: int
    subject_id: int
    hours: int
    teacher_candidates: list[int]
    room_candidates: list[int]
    room_required: bool
    patterns: list[Pattern]
    preferred_pattern: Pattern | None
    allow_same_day: bool
    difficulty: int
    physical: bool
    preferred_time: str
    fixed_teacher: int | None = None
    class_ids: list[int] = field(default_factory=list)
    team: bool = False
    room_mode: str = "any"
    external: bool = False

    def __post_init__(self):
        if not self.class_ids:
            self.class_ids = [self.class_id]

    @property
    def block_lengths(self) -> list[int]:
        return sorted({part for pat in self.patterns for part in pat})


@dataclass
class ClassData:
    id: int
    name: str
    grade: int
    days: list[int]
    available: set[Slot]
    max_daily: int
    student_count: int
    home_room_id: int | None
    parent_id: int | None = None


@dataclass
class TeacherData:
    id: int
    name: str
    brans: str
    max_daily: int
    max_weekly: int
    min_weekly: int
    max_consecutive: int
    preferred_days: list[int]
    unavailable: set[Slot]
    subject_ids: set[int]


@dataclass
class RoomData:
    id: int
    name: str
    room_type: str
    capacity: int
    unavailable: set[Slot]
    max_parallel: int = 1


@dataclass
class Problem:
    days: list[str]
    periods: int
    lessons: list[Lesson]
    classes: dict[int, ClassData]
    teachers: dict[int, TeacherData]
    rooms: dict[int, RoomData]
    subjects: dict[int, Subject]
    weights: dict[str, int]
    hard_per_day_limit: int = 4
    issues: list[str] = field(default_factory=list)

    @property
    def num_days(self) -> int:
        return len(self.days)

    def all_slots(self) -> list[Slot]:
        return [(d, p) for d in range(self.num_days) for p in range(self.periods)]

    def lesson_label(self, lesson: Lesson) -> str:
        names = "+".join(self.classes[c].name for c in lesson.class_ids if c in self.classes)
        return f"{names} – {self.subjects[lesson.subject_id].name}"

    def lesson_by_key(self) -> dict[tuple[int, int], Lesson]:
        return {(c, l.subject_id): l for l in self.lessons for c in l.class_ids}

    def slot_label(self, slot: Slot) -> str:
        d, p = slot
        return f"{self.days[d]} {p + 1}. saat"


def qualified_teachers(subject: Subject, teachers: list[Teacher]) -> list[int]:
    result = []
    for t in teachers:
        if subject.id in t.subject_ids:
            result.append(t.id)
        elif subject.brans and t.brans and subject.brans.strip().lower() == t.brans.strip().lower():
            result.append(t.id)
    return result


def suitable_rooms(subject: Subject, cls: SchoolClass, rooms: list[Room], room_subject_ids: dict[int, set[int]]):
    explicit = [r for r in rooms if subject.id in room_subject_ids.get(r.id, set())]
    typed = [r for r in rooms if subject.room_type and r.room_type == subject.room_type]
    special = {r.id: r for r in explicit + typed}
    if special:
        candidates = list(special.values())
        required = bool(subject.room_required)
        if not required:
            candidates += [r for r in rooms if r.id == cls.home_room_id and r.id not in special]
    else:
        candidates = [r for r in rooms if r.id == cls.home_room_id]
        required = bool(subject.room_required)
    if cls.student_count:
        candidates = [r for r in candidates if not r.capacity or r.capacity >= cls.student_count]
    if not special and not subject.room_required:
        required = False
    return sorted(r.id for r in candidates), required


def build_problem(db: Database) -> Problem:
    settings = db.all_settings()
    days_count = int(settings["days_count"])
    periods = int(settings["periods_per_day"])
    day_names = ALL_DAY_NAMES[:days_count]

    class_svc, teacher_svc, room_svc, subject_svc = (ClassService(db), TeacherService(db), RoomService(db),
                                                     SubjectService(db))
    subjects = {s.id: s for s in subject_svc.list()}
    teachers = teacher_svc.list()
    rooms = room_svc.list()
    room_subject_ids = {r.id: set(r.subject_ids) for r in rooms}
    all_slots = {(d, p) for d in range(days_count) for p in range(periods)}

    classes: dict[int, ClassData] = {}
    lessons: list[Lesson] = []
    links: dict[tuple[int, str], list[Lesson]] = defaultdict(list)
    issues: list[str] = []
    for cls in class_svc.list():
        days = [d for d in parse_int_list(cls.available_days) if d < days_count]
        blocked = class_svc.get_unavailable(cls.id)
        available = {(d, p) for (d, p) in all_slots if d in days and (d, p) not in blocked}
        classes[cls.id] = ClassData(cls.id, cls.name, cls.grade, days, available,
                                    cls.max_daily if cls.max_daily else periods, cls.student_count, cls.home_room_id,
                                    cls.parent_id)
        for cl in class_svc.lessons(cls.id):
            subject = subjects[cl.subject_id]
            external = bool(subject.external)
            team = bool(cl.team) and not external
            if external:
                cands = []
            elif cl.team:
                cands = list(cl.team)
            else:
                cands = qualified_teachers(subject, teachers)
            if cl.rooms:
                room_cands, room_required, room_mode = list(cl.rooms), True, cl.room_mode or "any"
            elif external:
                room_cands, room_required, room_mode = [], False, "any"
            else:
                room_cands, room_required = suitable_rooms(subject, cls, rooms, room_subject_ids)
                room_mode = "any"
            max_parts = len(days) if not subject.allow_same_day else 99
            patterns = candidate_patterns(cl.hours, subject.min_block, subject.max_block, subject.allowed_splits,
                                          subject.forbidden_splits, max_parts)
            preferred_text = subject.preferred_split
            if cl.split:
                try:
                    own = parse_pattern(cl.split)
                except ValueError:
                    own = None
                if own and sum(own) == cl.hours:
                    if own not in patterns:
                        patterns.append(own)
                    preferred_text = cl.split
            preferred = choose_preferred(cl.hours, patterns, preferred_text, subject.min_block, subject.max_block)
            lessons.append(Lesson(
                index=len(lessons), class_id=cls.id, subject_id=subject.id, hours=cl.hours,
                teacher_candidates=cands, room_candidates=room_cands, room_required=room_required,
                patterns=patterns, preferred_pattern=preferred,
                allow_same_day=bool(subject.allow_same_day) or (preferred is not None and len(preferred) > len(days)),
                difficulty=int(subject.difficulty or 0), physical=bool(subject.physical),
                preferred_time=subject.preferred_time or "any", fixed_teacher=cl.fixed_teacher_id,
                team=team, room_mode=room_mode, external=external))
            if cl.link:
                links[(subject.id, cl.link)].append(lessons[-1])

    for group in links.values():
        if len(group) < 2:
            continue
        head = group[0]
        for other in group[1:]:
            head.class_ids.extend(c for c in other.class_ids if c not in head.class_ids)
            head.room_candidates.extend(r for r in other.room_candidates if r not in head.room_candidates)
            if other.room_mode == "all":
                head.room_mode = "all"
            head.teacher_candidates.extend(t for t in other.teacher_candidates if t not in head.teacher_candidates)
            lessons.remove(other)
    for i, lesson in enumerate(lessons):
        lesson.index = i

    teacher_data = {
        t.id: TeacherData(t.id, t.name, t.brans or "", t.max_daily, t.max_weekly, t.min_weekly, t.max_consecutive,
                          [d for d in t.preferred_day_list if d < days_count],
                          {s for s in teacher_svc.get_unavailable(t.id) if s in all_slots}, set(t.subject_ids))
        for t in teachers
    }
    room_data = {r.id: RoomData(r.id, r.name, r.room_type, r.capacity,
                                {s for s in room_svc.get_unavailable(r.id) if s in all_slots},
                                max(1, int(r.max_parallel or 1))) for r in rooms}
    return Problem(day_names, periods, lessons, classes, teacher_data, room_data, subjects,
                   dict(settings["weights"]), int(settings.get("hard_per_day_limit", 4)), issues)


def describe_patterns(lesson: Lesson) -> str:
    return ", ".join(format_pattern(p) for p in lesson.patterns[:6]) + (" …" if len(lesson.patterns) > 6 else "")


def entries_by_lesson(entries: list[Entry]) -> dict[tuple[int, int], list[Entry]]:
    result: dict[tuple[int, int], list[Entry]] = {}
    for e in entries:
        result.setdefault((e.class_id, e.subject_id), []).append(e)
    return result
