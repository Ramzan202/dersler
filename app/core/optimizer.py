"""Soft constraints (preferences) and the weighted objective of the timetabling model."""
from collections import defaultdict
from dataclasses import dataclass

from app.core.constraints import TimetableModel

TERM_LABELS = {
    "hard_early": "Zor derslerin geç saatlere düşmesi",
    "physical_late": "Beden eğitiminin erken saatlere düşmesi",
    "preferred_time": "Dersin tercih edilen zamanı dışında olması",
    "class_gaps": "Sınıf boş saatleri (pencere)",
    "teacher_gaps": "Öğretmen boş pencereleri",
    "teacher_balance": "Aynı branştaki öğretmenler arası yük farkı",
    "hard_per_day": "Bir güne yığılan zor ders fazlası",
    "class_day_balance": "Sınıfların günlük yük farkı",
    "teacher_day_balance": "Öğretmenlerin en yoğun gün yükü",
    "teacher_consecutive": "Öğretmenin art arda ders fazlası",
    "teacher_preferred_days": "Öğretmenin tercih etmediği günlerdeki dersleri",
    "split_preference": "Tercih edilen bölünmenin kullanılmaması",
}

MULTIPLIERS = {
    "hard_early": 2,
    "physical_late": 2,
    "preferred_time": 2,
    "class_gaps": 30,
    "teacher_gaps": 12,
    "teacher_balance": 25,
    "hard_per_day": 15,
    "class_day_balance": 8,
    "teacher_day_balance": 3,
    "teacher_consecutive": 10,
    "teacher_preferred_days": 4,
    "split_preference": 20,
}


@dataclass
class ObjectiveTerm:
    key: str
    weight: int
    expr: object

    @property
    def label(self) -> str:
        return TERM_LABELS.get(self.key, self.key)


def _last_period(problem, class_id: int, day: int) -> int:
    periods = [p for (d, p) in problem.classes[class_id].available if d == day]
    return max(periods) if periods else problem.periods - 1


def _gap_penalty(m, busy: list, periods: int):
    """busy[p] is a 0/1 expression; returns the number of idle periods between the first and last busy period."""
    if len(busy) < 3:
        return []
    pre = [m.NewBoolVar("") for _ in range(periods)]
    suf = [m.NewBoolVar("") for _ in range(periods)]
    for p in range(periods):
        m.Add(pre[p] >= busy[p])
        m.Add(suf[p] >= busy[p])
        if p > 0:
            m.Add(pre[p] >= pre[p - 1])
            m.Add(pre[p] <= pre[p - 1] + busy[p])
        else:
            m.Add(pre[p] <= busy[p])
        if p < periods - 1:
            m.Add(suf[p] >= suf[p + 1])
            m.Add(suf[p] <= suf[p + 1] + busy[p])
        else:
            m.Add(suf[p] <= busy[p])
    gaps = []
    for p in range(1, periods - 1):
        g = m.NewBoolVar("")
        m.Add(g >= pre[p - 1] + suf[p + 1] - busy[p] - 1)
        gaps.append(g)
    return gaps


def add_objective(tm: TimetableModel) -> list[ObjectiveTerm]:
    m, problem = tm.m, tm.p
    weights = problem.weights
    raw: dict[str, list] = defaultdict(list)
    P = problem.periods

    for lesson in problem.lessons:
        k = lesson.index
        for (d, per), vars_ in tm.occ[k].items():
            expr = sum(vars_)
            if lesson.difficulty > 0:
                raw["hard_early"].append(per * lesson.difficulty * expr)
            last = _last_period(problem, lesson.class_id, d)
            if lesson.physical:
                raw["physical_late"].append(max(0, last - per) * expr)
            if lesson.preferred_time == "morning":
                raw["preferred_time"].append(per * expr)
            elif lesson.preferred_time == "afternoon":
                raw["preferred_time"].append(max(0, last - per) * expr)
        zvars = tm.z.get(k, {})
        if lesson.preferred_pattern is not None and len(zvars) > 1 and lesson.preferred_pattern in zvars:
            raw["split_preference"].append(1 - zvars[lesson.preferred_pattern])

    groups_of = defaultdict(list)
    for gid, g in problem.classes.items():
        if g.parent_id is not None:
            groups_of[g.parent_id].append(gid)
    for cid, slots in tm.class_occ.items():
        cls = problem.classes[cid]
        if cls.parent_id is not None:
            continue
        daily_loads = []
        hard_lessons = [l for l in problem.lessons if cid in l.class_ids and l.difficulty > 0]
        for d in cls.days:
            busy = [slots.get((d, p), 0) for p in range(P)]
            group_busy = [[tm.class_occ.get(g, {}).get((d, p), 0) for g in groups_of.get(cid, [])] for p in range(P)]
            for p in range(P):
                parts = [x for x in [busy[p]] + group_busy[p] if not isinstance(x, int)]
                if len(parts) > 1:
                    b = m.NewBoolVar("")
                    for x in parts:
                        m.Add(b >= x)
                    m.Add(b <= sum(parts))
                    busy[p] = b
                elif parts:
                    busy[p] = parts[0]
            if any(not isinstance(b, int) for b in busy):
                raw["class_gaps"].extend(_gap_penalty(m, busy, P))
            daily_loads.append(sum(busy))
            hard = [v for l in hard_lessons for (dd, _), vars_ in tm.occ[l.index].items() if dd == d for v in vars_]
            if len(hard) > problem.hard_per_day_limit:
                excess = m.NewIntVar(0, P, "")
                m.Add(excess >= sum(hard) - problem.hard_per_day_limit)
                raw["hard_per_day"].append(excess)
        if len(daily_loads) > 1:
            hi, lo = m.NewIntVar(0, P, ""), m.NewIntVar(0, P, "")
            for load in daily_loads:
                m.Add(hi >= load)
                m.Add(lo <= load)
            raw["class_day_balance"].append(hi - lo)

    by_branch = defaultdict(list)
    for tid, slots in tm.teacher_occ.items():
        t = problem.teachers.get(tid)
        if t is None:
            continue
        by_branch[t.brans.strip().lower()].append(tid)
        max_day = m.NewIntVar(0, P, "")
        for d in range(problem.num_days):
            busy = [sum(slots.get((d, p), [])) for p in range(P)]
            if all(isinstance(b, int) for b in busy):
                continue
            raw["teacher_gaps"].extend(_gap_penalty(m, busy, P))
            m.Add(max_day >= sum(busy))
            window = t.max_consecutive + 1
            if window <= P:
                for start in range(P - window + 1):
                    seg = busy[start:start + window]
                    if all(isinstance(b, int) for b in seg):
                        continue
                    excess = m.NewIntVar(0, window, "")
                    m.Add(excess >= sum(seg) - t.max_consecutive)
                    raw["teacher_consecutive"].append(excess)
            if t.preferred_days and d not in t.preferred_days:
                raw["teacher_preferred_days"].append(sum(busy))
        raw["teacher_day_balance"].append(max_day)

    for branch, tids in by_branch.items():
        if not branch or len(tids) < 2:
            continue
        loads = [tm.teacher_load(t) for t in tids]
        if all(isinstance(x, int) for x in loads):
            continue
        cap = max(problem.teachers[t].max_weekly for t in tids)
        hi, lo = m.NewIntVar(0, cap, ""), m.NewIntVar(0, cap, "")
        for load in loads:
            m.Add(hi >= load)
            m.Add(lo <= load)
        raw["teacher_balance"].append(hi - lo)

    terms = []
    objective = []
    for key, items in raw.items():
        weight = int(weights.get(key, 0))
        if not items:
            continue
        expr = sum(items)
        terms.append(ObjectiveTerm(key, weight, expr))
        if weight > 0:
            objective.append(weight * MULTIPLIERS.get(key, 1) * expr)
    if objective:
        m.Minimize(sum(objective))
    return terms
