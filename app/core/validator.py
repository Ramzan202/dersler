"""Pre-flight validation of input data, run before the optimizer.

Errors are problems in the input data that make scheduling impossible or meaningless (they block the run).
Warnings are suspicious situations that the user should review, but the optimizer may still succeed.
"""
from collections import defaultdict
from dataclasses import dataclass

from app.core.problem import Problem, describe_patterns
from app.database.database import Database


@dataclass
class Issue:
    level: str
    category: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.level == "error"


def validate(db: Database, problem: Problem) -> list[Issue]:
    p = problem
    issues: list[Issue] = []

    def err(cat, msg):
        issues.append(Issue("error", cat, msg))

    def warn(cat, msg):
        issues.append(Issue("warning", cat, msg))

    if not p.classes:
        err("Genel", "Hiç sınıf tanımlanmamış.")
    if not p.teachers:
        err("Genel", "Hiç öğretmen tanımlanmamış.")
    if p.periods < 1 or p.num_days < 1:
        err("Genel", "Okulun gün veya ders saati sayısı hatalı.")

    class_rows = {r["id"]: r for r in db.query("SELECT id, curriculum_id, weekly_hours FROM classes")}
    lessons_by_class = defaultdict(list)
    for lesson in p.lessons:
        lessons_by_class[lesson.class_id].append(lesson)

    for cid, cls in p.classes.items():
        row = class_rows.get(cid)
        lessons = lessons_by_class.get(cid, [])
        total = sum(l.hours for l in lessons)
        if row is not None and not row["curriculum_id"] and not lessons:
            err("Sınıflar", f"{cls.name}: sınıfa öğretim planı atanmamış.")
            continue
        if not lessons:
            err("Sınıflar", f"{cls.name}: öğretim planında hiç ders yok.")
            continue
        if not cls.days:
            err("Sınıflar", f"{cls.name}: hiçbir okul günü seçilmemiş.")
            continue
        capacity = sum(min(cls.max_daily, sum(1 for (d, _) in cls.available if d == day)) for day in cls.days)
        if total > capacity:
            err("Sınıflar", f"{cls.name}: haftalık {total} saat ders var, ancak sınıfın müsait zamanı {capacity} saat "
                            f"({len(cls.days)} gün). Okul günlerini veya günlük ders saatini artırın.")
        if row is not None and row["weekly_hours"] and row["weekly_hours"] != total:
            warn("Sınıflar", f"{cls.name}: tanımlı haftalık saat ({row['weekly_hours']}) ile plandaki toplam "
                             f"({total}) farklı.")
        for lesson in lessons:
            subj = p.subjects[lesson.subject_id].name
            if not lesson.teacher_candidates:
                err("Dersler", f"{cls.name} – {subj}: bu dersi verebilecek öğretmen yok. Öğretmenin ders listesine "
                               f"ekleyin veya dersin branşını belirleyin.")
            if lesson.room_required and not lesson.room_candidates:
                err("Derslikler", f"{cls.name} – {subj}: ders özel derslik gerektiriyor, ancak uygun derslik yok "
                                  f"(tür veya kapasite).")
            if not lesson.patterns:
                err("Dersler", f"{cls.name} – {subj}: {lesson.hours} saat, izin verilen blok kurallarıyla "
                               f"{len(cls.days)} güne bölünemiyor. Bölünme kurallarını kontrol edin.")
            if lesson.patterns and min(len(pt) for pt in lesson.patterns) > len(cls.days) and not lesson.allow_same_day:
                err("Dersler", f"{cls.name} – {subj}: bölünmeler ({describe_patterns(lesson)}) sınıfın {len(cls.days)} "
                               f"okul gününe sığmıyor.")
            if lesson.patterns and max(max(pt) for pt in lesson.patterns) > cls.max_daily:
                warn("Dersler", f"{cls.name} – {subj}: bazı bloklar sınıfın günlük ders sınırından uzun.")

    demand = defaultdict(int)
    sole_demand = defaultdict(int)
    for lesson in p.lessons:
        for t in lesson.teacher_candidates:
            demand[t] += lesson.hours
        if len(lesson.teacher_candidates) == 1:
            sole_demand[lesson.teacher_candidates[0]] += lesson.hours
    for tid, t in p.teachers.items():
        free = p.num_days * p.periods - len(t.unavailable)
        if sole_demand[tid] > t.max_weekly:
            err("Öğretmenler", f"{t.name}: yalnızca bu öğretmenin verebileceği dersler haftada {sole_demand[tid]} saat, "
                               f"ancak haftalık sınırı {t.max_weekly}.")
        if sole_demand[tid] > free:
            err("Öğretmenler", f"{t.name}: zorunlu ders yükü ({sole_demand[tid]} saat) müsait saatlerinden ({free}) "
                               f"fazla.")
        if t.max_daily * p.num_days < sole_demand[tid]:
            err("Öğretmenler", f"{t.name}: günlük sınır ({t.max_daily}) × gün sayısı, zorunlu {sole_demand[tid]} saatlik "
                               f"yüke yetmiyor.")
        if demand[tid] == 0:
            warn("Öğretmenler", f"{t.name}: verebileceği hiçbir ders planlarda yok.")
        if t.min_weekly and demand[tid] < t.min_weekly:
            err("Öğretmenler", f"{t.name}: haftalık en az {t.min_weekly} ders isteniyor, ancak verebileceği derslerin "
                               f"toplamı {demand[tid]} saat.")

    total_demand = sum(l.hours for l in p.lessons)
    total_capacity = sum(min(t.max_weekly, p.num_days * p.periods - len(t.unavailable)) for t in p.teachers.values())
    if total_demand > total_capacity:
        err("Öğretmenler", f"Toplam ders yükü {total_demand} saat, öğretmenlerin toplam kapasitesi {total_capacity} saat.")

    by_branch_demand = defaultdict(int)
    for lesson in p.lessons:
        if lesson.teacher_candidates:
            branches = {p.teachers[t].brans for t in lesson.teacher_candidates if t in p.teachers}
            if len(branches) == 1:
                by_branch_demand[branches.pop()] += lesson.hours
    for branch, need in by_branch_demand.items():
        cap = sum(t.max_weekly for t in p.teachers.values() if t.brans == branch)
        if branch and need > cap:
            err("Öğretmenler", f"{branch} branşında ihtiyaç {need} saat, branş öğretmenlerinin toplam sınırı {cap} saat.")

    room_need = defaultdict(int)
    for lesson in p.lessons:
        if len(lesson.room_candidates) == 1:
            room_need[lesson.room_candidates[0]] += lesson.hours
    for rid, need in room_need.items():
        r = p.rooms[rid]
        free = p.num_days * p.periods - len(r.unavailable)
        if need > free:
            err("Derslikler", f"{r.name}: yalnızca bu derslikte yapılabilecek dersler {need} saat, dersliğin müsait "
                              f"zamanı {free} saat. Ek derslik tanımlayın.")
    type_need = defaultdict(int)
    type_rooms = defaultdict(set)
    for lesson in p.lessons:
        if lesson.room_required and len(lesson.room_candidates) > 1:
            key = tuple(lesson.room_candidates)
            type_need[key] += lesson.hours
            type_rooms[key] = set(lesson.room_candidates)
    for key, need in type_need.items():
        free = sum(p.num_days * p.periods - len(p.rooms[r].unavailable) for r in type_rooms[key])
        if need > free:
            names = ", ".join(p.rooms[r].name for r in key)
            err("Derslikler", f"{names} derslikleri için ihtiyaç {need} saat, müsait zaman {free} saat.")

    home = defaultdict(list)
    for cls in p.classes.values():
        if cls.home_room_id:
            home[cls.home_room_id].append(cls.name)
    for rid, names in home.items():
        if len(names) > 1 and rid in p.rooms:
            warn("Derslikler", f"{p.rooms[rid].name} birden fazla sınıfın sınıf dersliği: {', '.join(names)}.")
    for cls in p.classes.values():
        if not cls.home_room_id:
            warn("Sınıflar", f"{cls.name}: sınıf dersliği atanmamış; genel dersler dersliksiz planlanacak.")
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.is_error for i in issues)
