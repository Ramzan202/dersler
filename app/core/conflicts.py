"""Independent verification of a timetable against all hard constraints (used after manual edits)."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from app.core.problem import Problem
from app.database.models import Entry


@dataclass
class Conflict:
    kind: str
    message: str
    entry_ids: list[int] = field(default_factory=list)
    severity: str = "error"


def check_timetable(problem: Problem, entries: list[Entry]) -> list[Conflict]:
    p = problem
    out: list[Conflict] = []
    lessons = p.lesson_by_key()

    def name_c(cid):
        return p.classes[cid].name if cid in p.classes else f"#{cid}"

    def name_t(tid):
        return p.teachers[tid].name if tid in p.teachers else "—"

    def name_r(rid):
        return p.rooms[rid].name if rid in p.rooms else "—"

    def name_s(sid):
        return p.subjects[sid].name if sid in p.subjects else f"#{sid}"

    def eids(items):
        return [e.id for e in items if e.id is not None]

    for e in entries:
        where = p.slot_label((e.day, e.period)) if e.day < p.num_days else f"{e.day + 1}. gün {e.period + 1}. saat"
        if not (0 <= e.day < p.num_days and 0 <= e.period < p.periods):
            out.append(Conflict("bounds", f"{name_c(e.class_id)} – {name_s(e.subject_id)}: okulun çalışma saatleri "
                                          f"dışında ({where}).", eids([e])))
            continue
        cls = p.classes.get(e.class_id)
        if cls and (e.day, e.period) not in cls.available:
            out.append(Conflict("class_avail", f"{cls.name}: {where} sınıf için kapalı (işletmede/okul dışı).",
                                eids([e])))
        if e.teacher_id is None:
            out.append(Conflict("no_teacher", f"{name_c(e.class_id)} – {name_s(e.subject_id)} ({where}): öğretmen "
                                              f"atanmamış.", eids([e])))
        else:
            t = p.teachers.get(e.teacher_id)
            if t and (e.day, e.period) in t.unavailable:
                out.append(Conflict("teacher_avail", f"{t.name}: {where} öğretmen için kapalı saat.", eids([e])))
            lesson = lessons.get((e.class_id, e.subject_id))
            if lesson and e.teacher_id not in lesson.teacher_candidates:
                out.append(Conflict("qualification", f"{name_t(e.teacher_id)}, {name_s(e.subject_id)} dersini vermeye "
                                                     f"yetkili değil ({name_c(e.class_id)}).", eids([e])))
        if e.room_id is not None:
            r = p.rooms.get(e.room_id)
            if r and (e.day, e.period) in r.unavailable:
                out.append(Conflict("room_avail", f"{r.name}: {where} derslik kapalı.", eids([e])))
        lesson = lessons.get((e.class_id, e.subject_id))
        if lesson and lesson.room_required:
            if e.room_id is None or e.room_id not in lesson.room_candidates:
                out.append(Conflict("room_type", f"{name_c(e.class_id)} – {name_s(e.subject_id)}: uygun derslikte "
                                                 f"değil ({name_r(e.room_id)}).", eids([e])))

    for key_fn, kind, label in (
        (lambda e: ("c", e.class_id), "class_clash", "sınıfının aynı saatte birden fazla dersi var"),
        (lambda e: ("t", e.teacher_id), "teacher_clash", "aynı saatte birden fazla derse girer"),
        (lambda e: ("r", e.room_id), "room_clash", "aynı saatte birden fazla sınıf tarafından kullanılıyor"),
    ):
        groups = defaultdict(list)
        for e in entries:
            k = key_fn(e)
            if k[1] is None:
                continue
            groups[(k, e.day, e.period)].append(e)
        for ((typ, ident), d, per), items in groups.items():
            if len(items) > 1:
                who = {"c": name_c, "t": name_t, "r": name_r}[typ](ident)
                prefix = {"c": "", "t": "Öğretmen ", "r": "Derslik "}[typ]
                detail = ", ".join(f"{name_c(x.class_id)}/{name_s(x.subject_id)}" for x in items)
                out.append(Conflict(kind, f"{prefix}{who} {label}: {p.slot_label((d, per))} ({detail}).", eids(items)))

    counts = Counter((e.class_id, e.subject_id) for e in entries)
    for (cid, sid), lesson in lessons.items():
        have = counts.get((cid, sid), 0)
        if have != lesson.hours:
            kind = "missing_hours" if have < lesson.hours else "extra_hours"
            verb = "eksik" if have < lesson.hours else "fazla"
            out.append(Conflict(kind, f"{name_c(cid)} – {name_s(sid)}: {abs(lesson.hours - have)} saat {verb} "
                                      f"({have}/{lesson.hours}).",
                                eids([e for e in entries if e.class_id == cid and e.subject_id == sid])))
    for (cid, sid), n in counts.items():
        if (cid, sid) not in lessons:
            out.append(Conflict("unknown_lesson", f"{name_c(cid)} – {name_s(sid)}: bu ders sınıfın planında yok.",
                                eids([e for e in entries if e.class_id == cid and e.subject_id == sid])))

    teacher_lesson_teachers = defaultdict(set)
    for e in entries:
        if e.teacher_id is not None:
            teacher_lesson_teachers[(e.class_id, e.subject_id)].add(e.teacher_id)
    for (cid, sid), ts in teacher_lesson_teachers.items():
        if len(ts) > 1:
            out.append(Conflict("teacher_split", f"{name_c(cid)} – {name_s(sid)}: dersin saatleri farklı öğretmenlere "
                                                 f"dağıtılmış ({', '.join(name_t(t) for t in ts)}).",
                                eids([e for e in entries if e.class_id == cid and e.subject_id == sid]),
                                severity="warning"))

    daily_t = Counter((e.teacher_id, e.day) for e in entries if e.teacher_id is not None)
    for (tid, d), n in daily_t.items():
        t = p.teachers.get(tid)
        if t and n > t.max_daily:
            out.append(Conflict("teacher_daily", f"{t.name}: {p.days[d] if d < p.num_days else d} günü {n} ders "
                                                 f"(sınır {t.max_daily}).",
                                eids([e for e in entries if e.teacher_id == tid and e.day == d])))
    weekly_t = Counter(e.teacher_id for e in entries if e.teacher_id is not None)
    for tid, n in weekly_t.items():
        t = p.teachers.get(tid)
        if t and n > t.max_weekly:
            out.append(Conflict("teacher_weekly", f"{t.name}: haftada {n} ders (sınır {t.max_weekly}).",
                                eids([e for e in entries if e.teacher_id == tid])))
    daily_c = Counter((e.class_id, e.day) for e in entries)
    for (cid, d), n in daily_c.items():
        cls = p.classes.get(cid)
        if cls and n > cls.max_daily:
            out.append(Conflict("class_daily", f"{cls.name}: {p.days[d] if d < p.num_days else d} günü {n} ders "
                                               f"(sınır {cls.max_daily}).",
                                eids([e for e in entries if e.class_id == cid and e.day == d])))
    return out


def hard_conflicts(conflicts: list[Conflict]) -> list[Conflict]:
    return [c for c in conflicts if c.severity == "error"]
