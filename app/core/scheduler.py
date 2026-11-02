"""Orchestrates building, solving and diagnosing the CP-SAT timetabling model."""
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from ortools.sat.python import cp_model

from app.core.constraints import TimetableModel
from app.core.optimizer import add_objective
from app.core.problem import Problem
from app.core.splits import format_pattern
from app.database.models import Entry

STATUS_TEXT = {
    "optimal": "En iyi (optimal) çözüm bulundu",
    "feasible": "Geçerli çözüm bulundu (süre sınırında en iyisi)",
    "infeasible": "Tüm zorunlu kısıtları sağlayan bir program yok",
    "unknown": "Süre içinde çözüm bulunamadı",
    "cancelled": "İşlem kullanıcı tarafından durduruldu",
    "invalid": "Model hatası",
    "empty": "Dağıtılacak ders yok",
}


@dataclass
class Progress:
    elapsed: float
    objective: float | None = None
    bound: float | None = None
    solutions: int = 0
    message: str = ""


@dataclass
class SolveResult:
    status: str
    entries: list[Entry] = field(default_factory=list)
    objective: float | None = None
    bound: float | None = None
    wall_time: float = 0.0
    term_values: dict[str, tuple[str, int, int]] = field(default_factory=dict)
    explanations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in ("optimal", "feasible") or (self.status == "cancelled" and bool(self.entries))

    @property
    def status_text(self) -> str:
        return STATUS_TEXT.get(self.status, self.status)


class _Callback(cp_model.CpSolverSolutionCallback):
    def __init__(self, on_progress, start):
        super().__init__()
        self.on_progress = on_progress
        self.start = start
        self.count = 0

    def on_solution_callback(self):
        self.count += 1
        if self.on_progress:
            self.on_progress(Progress(time.time() - self.start, self.ObjectiveValue(), self.BestObjectiveBound(),
                                      self.count, f"{self.count}. çözüm bulundu"))


class Scheduler:
    def __init__(self, problem: Problem):
        self.problem = problem
        self._solver: cp_model.CpSolver | None = None
        self._cancelled = threading.Event()

    def cancel(self):
        self._cancelled.set()
        solver = self._solver
        if solver is not None:
            solver.stop_search()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def solve(self, time_limit: float = 60, workers: int = 8, on_progress: Callable[[Progress], None] | None = None,
              hints: list[Entry] | None = None, locked: list[Entry] | None = None, diagnose_on_fail: bool = True,
              seed: int = 0) -> SolveResult:
        start = time.time()
        if not any(l.hours > 0 for l in self.problem.lessons):
            return SolveResult("empty", wall_time=0.0, explanations=["Hiçbir sınıfa ders atanmamış."])
        if on_progress:
            on_progress(Progress(0.0, message="Model oluşturuluyor…"))
        tm = TimetableModel(self.problem, locked=locked, hints=hints)
        terms = add_objective(tm)
        if self.cancelled:
            return SolveResult("cancelled", wall_time=time.time() - start)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)
        solver.parameters.num_search_workers = max(1, int(workers))
        solver.parameters.random_seed = seed
        self._solver = solver
        if on_progress:
            on_progress(Progress(time.time() - start, message="Çözücü çalışıyor…"))
        callback = _Callback(on_progress, start)
        status = solver.Solve(tm.m, callback)
        self._solver = None
        wall = time.time() - start

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            entries = self._extract(tm, solver)
            values = {t.key: (t.label, t.weight, int(solver.Value(t.expr)) if not isinstance(t.expr, int) else t.expr)
                      for t in terms}
            label = "optimal" if status == cp_model.OPTIMAL else ("cancelled" if self.cancelled else "feasible")
            return SolveResult(label, entries, solver.ObjectiveValue() if terms else 0.0,
                               solver.BestObjectiveBound() if terms else 0.0, wall, values)
        if self.cancelled:
            return SolveResult("cancelled", wall_time=wall)
        if status == cp_model.MODEL_INVALID:
            return SolveResult("invalid", wall_time=wall, explanations=[tm.m.Validate()])
        if status == cp_model.INFEASIBLE:
            explanations = []
            if diagnose_on_fail:
                if on_progress:
                    on_progress(Progress(wall, message="Çakışmanın nedeni araştırılıyor…"))
                explanations = self.diagnose(locked=locked, time_limit=max(20.0, time_limit / 2))
            return SolveResult("infeasible", wall_time=time.time() - start, explanations=explanations)
        return SolveResult("unknown", wall_time=wall, explanations=[
            "Belirlenen süre içinde geçerli bir program bulunamadı. Süre sınırını artırmayı veya kısıtları "
            "gevşetmeyi deneyin."])

    def _extract(self, tm: TimetableModel, solver: cp_model.CpSolver) -> list[Entry]:
        entries = []
        block_id = 0

        def chosen(options):
            return [r for r, v in options.items() if (v if isinstance(v, int) else solver.Value(v))]

        for lesson in self.problem.lessons:
            k = lesson.index
            teachers = chosen(tm.y[k])
            rooms = chosen(tm.r.get(k, {}))
            link = k + 1 if len(lesson.class_ids) > 1 else 0
            for (length, d, start), var in sorted(tm.starts[k].items(), key=lambda kv: (kv[0][1], kv[0][2])):
                if solver.Value(var):
                    block_id += 1
                    if k in tm.room_blocks:
                        rooms = chosen(tm.room_blocks[k].get((length, d, start), {}))
                    for i in range(length):
                        for cid in lesson.class_ids:
                            entries.append(Entry(class_id=cid, subject_id=lesson.subject_id,
                                                 teacher_id=teachers[0] if teachers else None,
                                                 room_id=rooms[0] if rooms else None, day=d, period=start + i,
                                                 block=block_id, extra_teachers=",".join(map(str, teachers[1:])),
                                                 extra_rooms=",".join(map(str, rooms[1:])), link=link))
        return entries

    def diagnose(self, locked: list[Entry] | None = None, time_limit: float = 30.0) -> list[str]:
        tm = TimetableModel(self.problem, diagnose=True, locked=locked)
        if not tm.groups:
            return ["Model, kısıt gruplarına ayrılamadı; veri doğrulama raporunu kontrol edin."]
        keys = list(tm.groups.keys())
        core = self._core(tm, keys, time_limit)
        if core is None:
            return ["Çakışmanın kesin nedeni süre sınırı içinde belirlenemedi. Öğretmen/derslik müsaitliklerini ve "
                    "sınıfların ders saatlerini kontrol edin."]
        core = self._minimize_core(core, locked, deadline=time.time() + time_limit)
        return self.explain(core)

    def _solve_with(self, keys_on: list[tuple], locked, time_limit: float):
        tm = TimetableModel(self.problem, diagnose=True, locked=locked)
        for key, lit in tm.groups.items():
            tm.m.Add(lit == (1 if key in keys_on else 0))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(1.0, time_limit)
        solver.parameters.num_search_workers = 8
        self._solver = solver
        status = solver.Solve(tm.m)
        self._solver = None
        return status

    def _core(self, tm: TimetableModel, keys: list[tuple], time_limit: float):
        lits = [tm.groups[k] for k in keys]
        tm.m.AddAssumptions(lits)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_search_workers = 1
        self._solver = solver
        status = solver.Solve(tm.m)
        self._solver = None
        if status != cp_model.INFEASIBLE:
            return None
        index_to_key = {tm.groups[k].Index(): k for k in keys}
        core = [index_to_key[i] for i in solver.SufficientAssumptionsForInfeasibility() if i in index_to_key]
        return core or None

    def _minimize_core(self, core: list[tuple], locked, deadline: float) -> list[tuple]:
        if len(core) > 25:
            return core
        current = list(core)
        for key in list(core):
            if time.time() > deadline or self.cancelled:
                break
            trial = [k for k in current if k != key]
            if not trial:
                continue
            status = self._solve_with(trial, locked, min(5.0, deadline - time.time()))
            if status == cp_model.INFEASIBLE:
                current = trial
        return current

    def explain(self, core: list[tuple]) -> list[str]:
        p = self.problem
        msgs = []
        lessons_in_core = []
        for key in core:
            kind, ident = key
            if kind in ("hours", "split", "locked", "teacher_missing", "room_missing"):
                lesson = p.lessons[ident]
                lessons_in_core.append(lesson)
                cls = "+".join(p.classes[c].name for c in lesson.class_ids)
                subj = p.subjects[lesson.subject_id].name
                if kind == "hours":
                    msgs.append(f"{cls} sınıfının {subj} dersi için {lesson.hours} saat yerleştirilemiyor.")
                elif kind == "split":
                    pats = ", ".join(format_pattern(x) for x in lesson.patterns[:5]) or "uygun bölünme yok"
                    rule = "aynı güne birden fazla blok konamaz" if not lesson.allow_same_day else "bloklar bitişik olamaz"
                    msgs.append(f"{cls} – {subj}: bölünme kuralları ({pats}; {rule}) sınıfın müsait günleriyle "
                                f"karşılanamıyor.")
                elif kind == "locked":
                    msgs.append(f"{cls} – {subj}: kilitli (sabitlenmiş) saatler diğer kısıtlarla çakışıyor.")
                elif kind == "teacher_missing":
                    msgs.append(f"{cls} – {subj}: bu dersi verebilecek öğretmen tanımlı değil.")
                else:
                    msgs.append(f"{cls} – {subj}: zorunlu derslik türüne uygun derslik yok.")
            elif kind == "class_avail":
                cls = p.classes[ident]
                msgs.append(f"{cls.name} sınıfının okul günleri/saatleri ({len(cls.available)} saat müsait) yetersiz.")
            elif kind == "class_daily":
                cls = p.classes[ident]
                msgs.append(f"{cls.name} sınıfı için günlük en fazla {cls.max_daily} ders sınırı çok dar.")
            elif kind == "teacher_avail":
                t = p.teachers[ident]
                msgs.append(f"Öğretmen {t.name}: kapalı saatleri ({len(t.unavailable)} saat) ders yerleştirmeyi "
                            f"engelliyor.")
            elif kind == "teacher_daily":
                t = p.teachers[ident]
                msgs.append(f"Öğretmen {t.name}: günlük en fazla {t.max_daily} ders sınırı yetersiz.")
            elif kind == "teacher_weekly":
                t = p.teachers[ident]
                msgs.append(f"Öğretmen {t.name}: haftalık en fazla {t.max_weekly} ders sınırı aşılmak zorunda.")
            elif kind == "teacher_min_weekly":
                t = p.teachers[ident]
                msgs.append(f"Öğretmen {t.name}: haftalık en az {t.min_weekly} ders şartı karşılanamıyor.")
            elif kind == "room_avail":
                r = p.rooms[ident]
                msgs.append(f"{r.name} dersliği kalan boş saatlerde kullanılamıyor (kapalı saatleri: "
                            f"{len(r.unavailable)}).")
        msgs.extend(self._shared_resource_hints(lessons_in_core))
        if not msgs:
            msgs.append("Zorunlu kısıtlar birbiriyle çelişiyor.")
        return msgs

    def _shared_resource_hints(self, lessons) -> list[str]:
        p = self.problem
        hints = []
        if len(lessons) < 1:
            return hints
        teacher_users = defaultdict(list)
        room_users = defaultdict(list)
        for l in lessons:
            for t in l.teacher_candidates:
                teacher_users[t].append(l)
            for r in l.room_candidates:
                room_users[r].append(l)
        for l in lessons:
            if l.teacher_candidates and all(len(teacher_users[t]) > 1 for t in l.teacher_candidates) and len(lessons) > 1:
                names = ", ".join(p.teachers[t].name for t in l.teacher_candidates if t in p.teachers)
                hints.append(f"{p.lesson_label(l)}: uygun öğretmenlerin tamamı ({names}) uygun saatlerde başka "
                             f"derslerle dolu.")
        shared_rooms = [r for r, ls in room_users.items() if len({x.class_id for x in ls}) > 1]
        for r in shared_rooms:
            ls = room_users[r]
            demand = sum(x.hours for x in ls)
            free = p.num_days * p.periods - len(p.rooms[r].unavailable)
            hints.append(f"{p.rooms[r].name} dersliği birden fazla sınıf tarafından paylaşılıyor "
                         f"(ihtiyaç {demand} saat, müsait {free} saat).")
        total_by_teacher = {t: sum(x.hours for x in ls) for t, ls in teacher_users.items()}
        for t, demand in total_by_teacher.items():
            td = p.teachers.get(t)
            if td is None:
                continue
            free = sum(1 for d in range(p.num_days) for per in range(p.periods) if (d, per) not in td.unavailable)
            if demand > free or demand > td.max_weekly:
                hints.append(f"Öğretmen {td.name}: bu derslerin toplamı {demand} saat, ancak müsait saat {free}, "
                             f"haftalık sınır {td.max_weekly}.")
        return list(dict.fromkeys(hints))
