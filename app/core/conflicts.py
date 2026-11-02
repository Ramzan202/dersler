"""Independent verification of a timetable against all hard constraints (used after manual edits and imports).

An entry is one class hour. It may carry a team of teachers (teacher_id + extra_teachers) and several rooms
(room_id + extra_rooms). Entries of a combined lesson (several classes/groups taught together) share the same
non-zero `link` and are counted once for teachers and rooms.
"""
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


def instance_key(e: Entry):
    """Entries that are the same lesson instance (combined classes) share a key."""
    return ("link", e.link, e.subject_id) if e.link else ("entry", id(e))


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
        lesson = lessons.get((e.class_id, e.subject_id))
        if cls and (e.day, e.period) not in cls.available:
            out.append(Conflict("class_avail", f"{cls.name}: {where} sınıf için kapalı (işletmede/okul dışı).",
                                eids([e])))
        external = bool(lesson and lesson.external) or bool(p.subjects.get(e.subject_id) and
                                                            p.subjects[e.subject_id].external)
        teachers = e.teacher_ids
        if not teachers and not external:
            out.append(Conflict("no_teacher", f"{name_c(e.class_id)} – {name_s(e.subject_id)} ({where}): öğretmen "
                                              f"atanmamış.", eids([e])))
        for tid in teachers:
            t = p.teachers.get(tid)
            if t and (e.day, e.period) in t.unavailable:
                out.append(Conflict("teacher_avail", f"{t.name}: {where} öğretmen için kapalı saat.", eids([e])))
            if lesson and not external and tid not in lesson.teacher_candidates:
                out.append(Conflict("qualification", f"{name_t(tid)}, {name_s(e.subject_id)} dersini vermeye "
                                                     f"yetkili değil ({name_c(e.class_id)}).", eids([e])))
        if lesson and lesson.team and set(lesson.teacher_candidates) - set(teachers):
            missing = ", ".join(name_t(t) for t in lesson.teacher_candidates if t not in teachers)
            out.append(Conflict("team", f"{name_c(e.class_id)} – {name_s(e.subject_id)} ({where}): ekipteki "
                                        f"öğretmen eksik ({missing}).", eids([e]), severity="warning"))
        rooms = e.room_ids
        for rid in rooms:
            r = p.rooms.get(rid)
            if r and (e.day, e.period) in r.unavailable:
                out.append(Conflict("room_avail", f"{r.name}: {where} derslik kapalı.", eids([e])))
        if lesson and lesson.room_required and lesson.room_candidates:
            if not rooms or not set(rooms) & set(lesson.room_candidates):
                out.append(Conflict("room_type", f"{name_c(e.class_id)} – {name_s(e.subject_id)}: uygun derslikte "
                                                 f"değil ({', '.join(name_r(r) for r in rooms) or 'derslik yok'}).",
                                    eids([e])))

    # classes (and a group with its parent class) cannot have two lessons at once
    by_class = defaultdict(list)
    for e in entries:
        by_class[(e.class_id, e.day, e.period)].append(e)
    for (cid, d, per), items in by_class.items():
        if len(items) > 1:
            detail = ", ".join(name_s(x.subject_id) for x in items)
            out.append(Conflict("class_clash", f"{name_c(cid)} sınıfının aynı saatte birden fazla dersi var: "
                                               f"{p.slot_label((d, per))} ({detail}).", eids(items)))
    for cid, cls in p.classes.items():
        if cls.parent_id is None:
            continue
        for (gid, d, per), items in list(by_class.items()):
            if gid != cid:
                continue
            parent_items = by_class.get((cls.parent_id, d, per), [])
            parent_items = [x for x in parent_items if not (x.link and any(x.link == i.link for i in items))]
            if parent_items:
                out.append(Conflict("group_clash", f"{cls.name} grubu ile {name_c(cls.parent_id)} sınıfının aynı "
                                                   f"saatte dersi var: {p.slot_label((d, per))}.",
                                    eids(items + parent_items)))

    for kind, label, resources, cap_of, name in (
        ("teacher_clash", "aynı saatte birden fazla derse girer", lambda e: e.teacher_ids, lambda r: 1, name_t),
        ("room_clash", "aynı saatte kapasitesinden fazla sınıf tarafından kullanılıyor", lambda e: e.room_ids,
         lambda r: p.rooms[r].max_parallel if r in p.rooms else 1, name_r),
    ):
        groups = defaultdict(list)
        for e in entries:
            for res in resources(e):
                groups[(res, e.day, e.period)].append(e)
        for (res, d, per), items in groups.items():
            instances = {instance_key(x) for x in items}
            if len(instances) > cap_of(res):
                prefix = "Öğretmen " if kind == "teacher_clash" else "Derslik "
                detail = ", ".join(f"{name_c(x.class_id)}/{name_s(x.subject_id)}" for x in items)
                out.append(Conflict(kind, f"{prefix}{name(res)} {label}: {p.slot_label((d, per))} ({detail}).",
                                    eids(items)))

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

    lesson_teachers = defaultdict(set)
    for e in entries:
        if e.teacher_id is not None:
            lesson_teachers[(e.class_id, e.subject_id)].add(tuple(sorted(e.teacher_ids)))
    for (cid, sid), teams in lesson_teachers.items():
        if len(teams) > 1:
            names = "; ".join(", ".join(name_t(t) for t in team) for team in teams)
            out.append(Conflict("teacher_split", f"{name_c(cid)} – {name_s(sid)}: dersin saatleri farklı öğretmenlere "
                                                 f"dağıtılmış ({names}).",
                                eids([e for e in entries if e.class_id == cid and e.subject_id == sid]),
                                severity="warning"))

    teacher_slots = defaultdict(set)
    for e in entries:
        for tid in e.teacher_ids:
            teacher_slots[tid].add((e.day, e.period))
    for tid, slots in teacher_slots.items():
        t = p.teachers.get(tid)
        if t is None:
            continue
        per_day = Counter(d for d, _ in slots)
        for d, n in per_day.items():
            if n > t.max_daily:
                out.append(Conflict("teacher_daily", f"{t.name}: {p.days[d] if d < p.num_days else d} günü {n} ders "
                                                     f"(sınır {t.max_daily}).",
                                    eids([e for e in entries if tid in e.teacher_ids and e.day == d])))
        if len(slots) > t.max_weekly:
            out.append(Conflict("teacher_weekly", f"{t.name}: haftada {len(slots)} ders (sınır {t.max_weekly}).",
                                eids([e for e in entries if tid in e.teacher_ids])))
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
