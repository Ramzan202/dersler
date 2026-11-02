"""Statistics and reports for a timetable variant."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from app.core.conflicts import Conflict, check_timetable
from app.core.problem import Problem
from app.database.models import Entry


@dataclass
class TeacherLoad:
    teacher_id: int
    name: str
    brans: str
    hours: int
    max_weekly: int
    days_worked: int
    gaps: int
    daily: list[int]


@dataclass
class Report:
    required_hours: int
    placed_hours: int
    unplaced: list[tuple[str, str, int]]
    conflicts: list[Conflict]
    teacher_loads: list[TeacherLoad]
    branch_stats: dict[str, tuple[float, int, int, int]]
    room_usage: list[tuple[str, int, int, float]]
    class_daily: dict[str, list[int]]
    class_gaps: int
    teacher_gaps: int
    hard_early_ratio: float
    physical_late_ratio: float
    notes: list[str] = field(default_factory=list)

    @property
    def conflict_count(self) -> int:
        return sum(1 for c in self.conflicts if c.severity == "error")

    def summary_rows(self) -> list[tuple[str, str]]:
        return [
            ("Gereken toplam ders saati", str(self.required_hours)),
            ("Yerleştirilen ders saati", str(self.placed_hours)),
            ("Yerleştirilemeyen saat", str(sum(x[2] for x in self.unplaced))),
            ("Zorunlu kısıt ihlali (çakışma)", str(self.conflict_count)),
            ("Öğretmen boş pencereleri (toplam)", str(self.teacher_gaps)),
            ("Sınıf boş saatleri (toplam)", str(self.class_gaps)),
            ("Zor derslerin ilk yarıda olma oranı", f"%{self.hard_early_ratio * 100:.0f}"),
            ("Beden eğitiminin son saatlerde olma oranı", f"%{self.physical_late_ratio * 100:.0f}"),
        ]


def _gaps(periods: list[int]) -> int:
    if not periods:
        return 0
    s = set(periods)
    return (max(s) - min(s) + 1) - len(s)


def build_report(problem: Problem, entries: list[Entry]) -> Report:
    p = problem
    keys = [(cid, l.subject_id, l.hours) for l in p.lessons for cid in l.class_ids]
    required = sum(h for _, _, h in keys)
    counts = Counter((e.class_id, e.subject_id) for e in entries)
    unplaced = []
    for cid, sid, hours in keys:
        have = counts.get((cid, sid), 0)
        if have < hours:
            unplaced.append((p.classes[cid].name, p.subjects[sid].name, hours - have))
    placed = sum(min(counts.get((cid, sid), 0), hours) for cid, sid, hours in keys)
    conflicts = check_timetable(p, entries)

    teacher_slots = defaultdict(set)
    for e in entries:
        for tid in e.teacher_ids:
            teacher_slots[(tid, e.day)].add(e.period)
    by_teacher_day = {k: sorted(v) for k, v in teacher_slots.items()}
    loads = []
    for tid, t in sorted(p.teachers.items(), key=lambda kv: (kv[1].brans, kv[1].name)):
        daily = [len(by_teacher_day.get((tid, d), [])) for d in range(p.num_days)]
        gaps = sum(_gaps(by_teacher_day.get((tid, d), [])) for d in range(p.num_days))
        loads.append(TeacherLoad(tid, t.name, t.brans, sum(daily), t.max_weekly, sum(1 for x in daily if x), gaps,
                                 daily))
    branch = defaultdict(list)
    for tl in loads:
        branch[tl.brans or "(branşsız)"].append(tl.hours)
    branch_stats = {b: (sum(h) / len(h), min(h), max(h), len(h)) for b, h in sorted(branch.items())}

    room_slots = defaultdict(set)
    for e in entries:
        for rid in e.room_ids:
            room_slots[rid].add((e.day, e.period))
    room_hours = {rid: len(v) for rid, v in room_slots.items()}
    room_usage = []
    for rid, r in sorted(p.rooms.items(), key=lambda kv: kv[1].name):
        avail = p.num_days * p.periods - len(r.unavailable)
        used = room_hours.get(rid, 0)
        room_usage.append((r.name, used, avail, used / avail if avail else 0.0))

    by_class_day = defaultdict(set)
    for e in entries:
        by_class_day[(e.class_id, e.day)].add(e.period)
        parent = p.classes[e.class_id].parent_id if e.class_id in p.classes else None
        if parent is not None:
            by_class_day[(parent, e.day)].add(e.period)
    class_daily = {}
    class_gaps = 0
    for cid, c in sorted(p.classes.items(), key=lambda kv: (kv[1].grade, kv[1].name)):
        class_daily[c.name] = [len(by_class_day.get((cid, d), ())) for d in range(p.num_days)]
        if c.parent_id is None:
            class_gaps += sum(_gaps(list(by_class_day.get((cid, d), ()))) for d in range(p.num_days))

    half = p.periods / 2
    hard = [e for e in entries if p.subjects.get(e.subject_id) and p.subjects[e.subject_id].difficulty > 0]
    used = [e.period for e in entries]
    half = (min(used) + max(used) + 1) / 2 if used else half
    phys = [e for e in entries if p.subjects.get(e.subject_id) and p.subjects[e.subject_id].physical]
    hard_ratio = sum(1 for e in hard if e.period < half) / len(hard) if hard else 1.0
    phys_ratio = sum(1 for e in phys if e.period >= half) / len(phys) if phys else 1.0

    return Report(required, placed, unplaced, conflicts, loads, branch_stats, room_usage, class_daily, class_gaps,
                  sum(t.gaps for t in loads), hard_ratio, phys_ratio)


def compare_entries(a: list[Entry], b: list[Entry]) -> int:
    def key(e):
        return (e.class_id, e.day, e.period, e.subject_id, e.teacher_id, e.room_id)
    sa, sb = Counter(key(e) for e in a), Counter(key(e) for e in b)
    return sum((sa - sb).values())
