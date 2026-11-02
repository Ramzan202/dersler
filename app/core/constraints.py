"""CP-SAT model of the timetabling problem: decision variables and hard constraints.

Decision variables
  s[k][(L, d, p)]  lesson k has a block of length L starting at day d, period p
  z[k][pattern]    lesson k uses the given split pattern (e.g. 3+3+3)
  y[k][t]          teacher t teaches lesson k (all hours of k)
  r[k][room]       lesson k takes place in room
  a[(k, t)][slot]  teacher t teaches lesson k at slot (only when k has several teacher candidates)
  b[(k, room)][slot] same for rooms

occ[k][slot] is the linear expression "lesson k is taught at slot".

In diagnose mode every hard-constraint group is guarded by an assumption literal so that CP-SAT can return
an infeasible subset of groups, which is then translated into a human readable explanation.
"""
from collections import defaultdict

from ortools.sat.python import cp_model

from app.core.problem import Lesson, Problem, Slot
from app.database.models import Entry


class TimetableModel:
    def __init__(self, problem: Problem, diagnose: bool = False, locked: list[Entry] | None = None,
                 hints: list[Entry] | None = None):
        self.p = problem
        self.m = cp_model.CpModel()
        self.diagnose = diagnose
        self.groups: dict[tuple, cp_model.IntVar] = {}
        self.starts: dict[int, dict[tuple[int, int, int], cp_model.IntVar]] = {}
        self.occ: dict[int, dict[Slot, list]] = {}
        self.y: dict[int, dict[int, object]] = {}
        self.r: dict[int, dict[int, object]] = {}
        self.z: dict[int, dict[tuple, object]] = {}
        self.teacher_occ: dict[int, dict[Slot, list]] = defaultdict(lambda: defaultdict(list))
        self.room_occ: dict[int, dict[Slot, list]] = defaultdict(lambda: defaultdict(list))
        self.teacher_lessons: dict[int, list[int]] = defaultdict(list)
        self.locked = locked or []
        self.hints = hints or []
        self._zero = self.m.NewConstant(0)
        self._build()

    def guard(self, key: tuple) -> list:
        if not self.diagnose:
            return []
        if key not in self.groups:
            self.groups[key] = self.m.NewBoolVar(str(key))
        return [self.groups[key]]

    def add(self, constraint, key: tuple | None):
        if key is not None and self.diagnose:
            constraint.OnlyEnforceIf(self.guard(key))
        return constraint

    def occupancy(self, k: int, slot: Slot):
        return sum(self.occ[k].get(slot, []))

    def _slot_reasons(self, lesson: Lesson, slot: Slot) -> list[tuple]:
        reasons = []
        cls = self.p.classes[lesson.class_id]
        if slot not in cls.available:
            reasons.append(("class_avail", cls.id))
        if len(lesson.teacher_candidates) == 1:
            t = self.p.teachers.get(lesson.teacher_candidates[0])
            if t and slot in t.unavailable:
                reasons.append(("teacher_avail", t.id))
        if len(lesson.room_candidates) == 1:
            room = self.p.rooms.get(lesson.room_candidates[0])
            if room and slot in room.unavailable:
                reasons.append(("room_avail", room.id))
        return reasons

    def _build(self):
        p = self.p
        for lesson in p.lessons:
            self._build_lesson(lesson)
        self._resource_constraints()
        self._load_constraints()
        self._locked_constraints()
        self._apply_hints()

    def _build_lesson(self, lesson: Lesson):
        m, p, k = self.m, self.p, lesson.index
        starts: dict[tuple[int, int, int], cp_model.IntVar] = {}
        occ: dict[Slot, list] = defaultdict(list)
        missing = None
        if not lesson.teacher_candidates:
            missing = ("teacher_missing", k)
        elif lesson.room_required and not lesson.room_candidates:
            missing = ("room_missing", k)
        elif not lesson.patterns:
            missing = ("split", k)

        if lesson.hours > 0:
            for length in lesson.block_lengths:
                for d in range(p.num_days):
                    for start in range(p.periods - length + 1):
                        covered = [(d, start + i) for i in range(length)]
                        reasons = [r for slot in covered for r in self._slot_reasons(lesson, slot)]
                        if reasons and not self.diagnose:
                            continue
                        var = m.NewBoolVar("")
                        for reason in dict.fromkeys(reasons):
                            m.Add(var == 0).OnlyEnforceIf(self.guard(reason))
                        starts[(length, d, start)] = var
                        for slot in covered:
                            occ[slot].append(var)
        self.starts[k] = starts
        self.occ[k] = occ

        if missing is not None:
            impossible = m.NewIntVar(0, 0, "")
            self.add(m.Add(impossible == 1), missing)

        total = sum(length * var for (length, _, _), var in starts.items())
        self.add(m.Add(total == lesson.hours), ("hours", k))

        if lesson.patterns and lesson.hours > 0:
            counts = {length: sum(v for (L, _, _), v in starts.items() if L == length)
                      for length in lesson.block_lengths}
            if len(lesson.patterns) == 1:
                pat = lesson.patterns[0]
                self.z[k] = {pat: 1}
                for length, expr in counts.items():
                    self.add(m.Add(expr == pat.count(length)), ("split", k))
            else:
                zvars = {pat: m.NewBoolVar("") for pat in lesson.patterns}
                self.z[k] = zvars
                self.add(m.AddExactlyOne(zvars.values()), ("split", k))
                for length, expr in counts.items():
                    self.add(m.Add(expr == sum(pat.count(length) * z for pat, z in zvars.items())), ("split", k))
            for d in range(p.num_days):
                day_starts = [v for (L, dd, _), v in starts.items() if dd == d]
                if not day_starts:
                    continue
                if not lesson.allow_same_day:
                    self.add(m.Add(sum(day_starts) <= 1), ("split", k))
                else:
                    for (L, dd, st), v in starts.items():
                        if dd == d and st > 0 and occ.get((d, st - 1)):
                            self.add(m.Add(v + sum(occ[(d, st - 1)]) <= 1), ("split", k))

        self._assign_resource(lesson, occ, lesson.teacher_candidates, self.y, self.teacher_occ, "teacher_avail",
                              lambda t: self.p.teachers[t].unavailable if t in self.p.teachers else set())
        self._assign_resource(lesson, occ, lesson.room_candidates, self.r, self.room_occ, "room_avail",
                              lambda r: self.p.rooms[r].unavailable if r in self.p.rooms else set())
        for t in lesson.teacher_candidates:
            self.teacher_lessons[t].append(k)

    def _assign_resource(self, lesson, occ, candidates, choice, resource_occ, avail_key, unavailable_of):
        m, k = self.m, lesson.index
        if not candidates:
            choice[k] = {}
            return
        if len(candidates) == 1:
            res = candidates[0]
            choice[k] = {res: 1}
            for slot, vars_ in occ.items():
                resource_occ[res][slot].extend(vars_)
            return
        cvars = {res: m.NewBoolVar("") for res in candidates}
        choice[k] = cvars
        m.AddExactlyOne(cvars.values())
        for slot, vars_ in occ.items():
            parts = []
            for res in candidates:
                blocked = slot in unavailable_of(res)
                if blocked and not self.diagnose:
                    continue
                av = m.NewBoolVar("")
                m.AddImplication(av, cvars[res])
                if blocked:
                    m.Add(av == 0).OnlyEnforceIf(self.guard((avail_key, res)))
                parts.append(av)
                resource_occ[res][slot].append(av)
            m.Add(sum(parts) == sum(vars_))

    def _resource_constraints(self):
        m, p = self.m, self.p
        by_class = defaultdict(list)
        for lesson in p.lessons:
            by_class[lesson.class_id].append(lesson.index)
        self.class_occ: dict[int, dict[Slot, object]] = {}
        for cid, ks in by_class.items():
            self.class_occ[cid] = {}
            for slot in p.all_slots():
                vars_ = [v for k in ks for v in self.occ[k].get(slot, [])]
                if vars_:
                    m.Add(sum(vars_) <= 1)
                    self.class_occ[cid][slot] = sum(vars_)
        for resource_occ in (self.teacher_occ, self.room_occ):
            for res, slots in resource_occ.items():
                for slot, vars_ in slots.items():
                    if len(vars_) > 1:
                        m.Add(sum(vars_) <= 1)

    def _load_constraints(self):
        m, p = self.m, self.p
        for cid, slots in self.class_occ.items():
            cls = p.classes[cid]
            if cls.max_daily < p.periods:
                for d in range(p.num_days):
                    day = [expr for (dd, _), expr in slots.items() if dd == d]
                    if day:
                        self.add(m.Add(sum(day) <= cls.max_daily), ("class_daily", cid))
        for tid, slots in self.teacher_occ.items():
            t = p.teachers.get(tid)
            if t is None:
                continue
            if t.max_daily < p.periods:
                for d in range(p.num_days):
                    day = [v for (dd, _), vars_ in slots.items() if dd == d for v in vars_]
                    if len(day) > t.max_daily:
                        self.add(m.Add(sum(day) <= t.max_daily), ("teacher_daily", tid))
            load = self.teacher_load(tid)
            self.add_bound(load, None, t.max_weekly, ("teacher_weekly", tid))
            if t.min_weekly > 0:
                self.add_bound(load, t.min_weekly, None, ("teacher_min_weekly", tid))

    def add_bound(self, expr, lower, upper, key):
        m = self.m
        if isinstance(expr, int):
            ok = (lower is None or expr >= lower) and (upper is None or expr <= upper)
            if not ok:
                impossible = m.NewIntVar(0, 0, "")
                self.add(m.Add(impossible == 1), key)
            return
        if upper is not None:
            self.add(m.Add(expr <= upper), key)
        if lower is not None:
            self.add(m.Add(expr >= lower), key)

    def teacher_load(self, tid: int):
        return sum(self.p.lessons[k].hours * self.y[k][tid] for k in self.teacher_lessons.get(tid, []))

    def _locked_constraints(self):
        m = self.m
        lookup = self.p.lesson_by_key()
        for e in self.locked:
            lesson = lookup.get((e.class_id, e.subject_id))
            if lesson is None:
                continue
            k = lesson.index
            key = ("locked", k)
            vars_ = self.occ[k].get((e.day, e.period), [])
            if not vars_:
                impossible = m.NewIntVar(0, 0, "")
                self.add(m.Add(impossible == 1), key)
                continue
            self.add(m.Add(sum(vars_) == 1), key)
            if e.teacher_id in self.y[k] and not isinstance(self.y[k][e.teacher_id], int):
                self.add(m.Add(self.y[k][e.teacher_id] == 1), key)
            if e.room_id in self.r.get(k, {}) and not isinstance(self.r[k][e.room_id], int):
                self.add(m.Add(self.r[k][e.room_id] == 1), key)

    def _apply_hints(self):
        if not self.hints:
            return
        lookup = self.p.lesson_by_key()
        grouped = defaultdict(list)
        for e in self.hints:
            grouped[(e.class_id, e.subject_id)].append(e)
        for key, entries in grouped.items():
            lesson = lookup.get(key)
            if lesson is None:
                continue
            k = lesson.index
            blocks = _blocks_from_entries(entries)
            hinted = set()
            for d, start, length in blocks:
                var = self.starts[k].get((length, d, start))
                if var is not None:
                    hinted.add(var.Index())
                    self.m.AddHint(var, 1)
            for var in self.starts[k].values():
                if var.Index() not in hinted:
                    self.m.AddHint(var, 0)
            teacher = entries[0].teacher_id
            for t, v in self.y[k].items():
                if not isinstance(v, int):
                    self.m.AddHint(v, 1 if t == teacher else 0)
            room = entries[0].room_id
            for rid, v in self.r.get(k, {}).items():
                if not isinstance(v, int):
                    self.m.AddHint(v, 1 if rid == room else 0)


def _blocks_from_entries(entries: list[Entry]) -> list[tuple[int, int, int]]:
    by_block = defaultdict(list)
    for e in entries:
        by_block[(e.day, e.block)].append(e.period)
    result = []
    for (d, _), periods in by_block.items():
        periods.sort()
        start = periods[0]
        prev = start
        for per in periods[1:]:
            if per != prev + 1:
                result.append((d, start, prev - start + 1))
                start = per
            prev = per
        result.append((d, start, prev - start + 1))
    return result
