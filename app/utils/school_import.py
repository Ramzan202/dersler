"""Import class timetables exported by the school's ders dağıtım program ("Sınıf Programları" Excel layout).

Each workbook contains blocks like:

    Sınıf Kodu ATP9A
    [header row: "1\\n08:00 08:30", "2\\n08:30 09:00", ...]
    Pazartesi | MAT_9\\nŞ.AKT\\nZ_1 | ... (merged cells = consecutive lesson hours)
    ...
    Toplam Saat: 45      Sınıf Öğretmeni: ...
    Sıra | Ders | HDS | Mekan | Öğretmen Adı   (teachers and rooms separated by commas)

From these we create: bell schedule, classes and groups (e.g. "ATP10A 1" is a group of ATP10A), subjects (by code),
teachers, rooms, per-class lessons (hours, teacher team, rooms, split pattern), combined lessons and the current
timetable as a locked-free variant. Everything stays editable in the application afterwards.
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from app.database.database import Database
from app.database.models import Curriculum, Entry, Room, SchoolClass, Subject, Teacher
from app.services.class_service import ClassService
from app.services.room_service import RoomService
from app.services.subject_service import CurriculumService, SubjectService
from app.services.teacher_service import TeacherService
from app.services.timetable_service import TimetableService

DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"]

# code prefix -> (subject name, teacher branch, difficulty, physical, elective)
KNOWN = [
    (r"^TDE", "Türk Dili ve Edebiyatı", "Türk Dili ve Edebiyatı", 0, 0, 0),
    (r"^MAT", "Matematik", "Matematik", 2, 0, 0),
    (r"^FİZ", "Fizik", "Fizik", 1, 0, 0),
    (r"^KİM", "Kimya", "Kimya", 1, 0, 0),
    (r"^BİY", "Biyoloji", "Biyoloji", 0, 0, 0),
    (r"^COĞ", "Coğrafya", "Coğrafya", 0, 0, 0),
    (r"^TAR", "Tarih", "Tarih", 0, 0, 0),
    (r"^INK", "T.C. İnkılap Tarihi ve Atatürkçülük", "Tarih", 0, 0, 0),
    (r"^DİN", "Din Kültürü ve Ahlak Bilgisi", "Din Kültürü ve Ahlak Bilgisi", 0, 0, 0),
    (r"^YDL", "Yabancı Dil", "İngilizce", 0, 0, 0),
    (r"^FEL", "Felsefe", "Felsefe", 0, 0, 0),
    (r"^(BED|B/M)", "Beden Eğitimi ve Spor / Görsel Sanatlar / Müzik", "Beden Eğitimi", 0, 1, 0),
    (r"^(\d+)?REH", "Rehberlik ve Yönlendirme", "Rehberlik", 0, 0, 0),
    (r"^SPH", "Seçmeli Peygamberimizin Hayatı", "Din Kültürü ve Ahlak Bilgisi", 0, 0, 1),
    (r"^SMT", "Seçmeli Matematik", "Matematik", 2, 0, 1),
    (r"^SKM", "Seçmeli Kimya", "Kimya", 1, 0, 1),
    (r"^SBT", "Seçmeli Biyoloji", "Biyoloji", 0, 0, 1),
    (r"^SCĞ", "Seçmeli Coğrafya", "Coğrafya", 0, 0, 1),
    (r"^\d?MGA", "Mesleki Gelişim Atölyesi", "", 0, 0, 0),
    (r"^\d?(TRES|TRS)", "Teknik Resim", "", 0, 0, 0),
    (r"^\d?TEE", "Temel Elektrik-Elektronik", "Elektrik-Elektronik Teknolojisi", 1, 0, 0),
    (r"^\d?PRT", "Programlama Temelleri", "Bilişim Teknolojileri", 1, 0, 0),
    (r"^\d?BTT", "Bilişim Teknolojilerinin Temelleri", "Bilişim Teknolojileri", 0, 0, 0),
    (r"^\d?BTU", "Bilgisayarlı Tasarım Uygulamaları", "Bilişim Teknolojileri", 0, 0, 0),
    (r"^NETP", "Nesne Tabanlı Programlama", "Bilişim Teknolojileri", 1, 0, 0),
    (r"^RKOD", "Robotik ve Kodlama", "Bilişim Teknolojileri", 0, 0, 0),
    (r"^WTU", "Web Tabanlı Uygulama Geliştirme", "Bilişim Teknolojileri", 1, 0, 0),
    (r"^GCN", "Grafik ve Canlandırma", "Bilişim Teknolojileri", 0, 0, 0),
    (r"^\d?MOU", "Mobil Uygulamalar", "Bilişim Teknolojileri", 0, 0, 0),
    (r"^AHİ", "Ahilik Kültürü ve Girişimcilik", "", 0, 0, 0),
    (r"İME$", "İşletmelerde Mesleki Eğitim", "", 0, 0, 0),
]

ROOM_TYPES = [
    (r"^(SPOR|SPR)", "Spor Salonu"),
    (r"^(BT\d|YG|AĞ)", "Bilgisayar Laboratuvarı"),
    (r"^(\dK_|Z_)", "Derslik"),
    (r"^AİME", "İşletme (okul dışı)"),
]


@dataclass
class ParsedClass:
    code: str
    grade: int
    total: int | None = None
    class_teacher: str | None = None
    grid: list[dict] = field(default_factory=list)
    courses: list[dict] = field(default_factory=list)


@dataclass
class ImportResult:
    classes: int = 0
    groups: int = 0
    subjects: int = 0
    teachers: int = 0
    rooms: int = 0
    lessons: int = 0
    entries: int = 0
    combined: int = 0
    timetable_id: int | None = None
    warnings: list[str] = field(default_factory=list)

    def text(self) -> str:
        lines = [f"Sınıf: {self.classes} (+{self.groups} grup)", f"Ders (kod): {self.subjects}",
                 f"Öğretmen: {self.teachers}", f"Derslik: {self.rooms}", f"Sınıf dersi: {self.lessons}",
                 f"Birleştirilmiş ders: {self.combined}", f"Mevcut programdaki ders saati: {self.entries}"]
        if self.warnings:
            lines += ["", "Uyarılar:"] + [f"• {w}" for w in self.warnings[:30]]
        return "\n".join(lines)


def _clean(v) -> str:
    return " ".join(str(v).split()) if v is not None else ""


def parse_workbook(path) -> tuple[list[ParsedClass], list[str]]:
    wb = openpyxl.load_workbook(str(path))
    ws = wb.worksheets[0]
    span = {(r.min_row, r.min_col): r.max_col - r.min_col + 1 for r in ws.merged_cells.ranges}
    grade_match = re.search(r"(9|10|11|12)\s*s", Path(path).name)
    times: list[str] = []
    classes: list[ParsedClass] = []
    r = 1
    while r <= ws.max_row:
        v = ws.cell(r, 1).value
        if not (isinstance(v, str) and v.startswith("Sınıf Kodu")):
            r += 1
            continue
        code = _clean(v.replace("Sınıf Kodu", ""))
        grade = int(grade_match.group(1)) if grade_match else int(re.search(r"(9|10|11|12)", code).group(1))
        pc = ParsedClass(code=code, grade=grade)
        rr = r + 1
        while rr <= ws.max_row and ws.cell(rr, 1).value != "Sıra":
            a = ws.cell(rr, 1).value
            if isinstance(a, str) and a.startswith("Sınıf Kodu"):
                break
            b = ws.cell(rr, 2).value
            if a is None and isinstance(b, str) and re.match(r"^\s*1\s*\n", b):
                times = []
                for c in range(2, ws.max_column + 1):
                    cell = ws.cell(rr, c).value
                    if cell is None:
                        break
                    parts = str(cell).split("\n")
                    times.append(parts[1].strip().replace(" ", "-") if len(parts) > 1 else "")
            if a in DAYS:
                for c in range(2, ws.max_column + 1):
                    val = ws.cell(rr, c).value
                    if val:
                        parts = str(val).split("\n")
                        pc.grid.append({"day": DAYS.index(a), "slot": c - 2, "len": span.get((rr, c), 1),
                                        "code": parts[0].strip(),
                                        "rooms": [x.strip() for x in (parts[2] if len(parts) > 2 else "").split(",")
                                                  if x.strip()]})
            if a == "Toplam Saat:":
                pc.total = ws.cell(rr, 3).value
            if a == "Sınıf Öğretmeni:":
                pc.class_teacher = _clean(ws.cell(rr, 3).value) or None
            rr += 1
        if rr <= ws.max_row and ws.cell(rr, 1).value == "Sıra":
            rr += 1
            while rr <= ws.max_row and isinstance(ws.cell(rr, 1).value, (int, float)):
                pc.courses.append({
                    "code": _clean(ws.cell(rr, 2).value), "hours": int(ws.cell(rr, 3).value or 0),
                    "rooms": [x.strip() for x in str(ws.cell(rr, 4).value or "").split(",") if x.strip()],
                    "teachers": [_clean(x) for x in str(ws.cell(rr, 5).value or "").split(",") if x.strip()]})
                rr += 1
        classes.append(pc)
        r = rr
    return classes, times


def subject_info(code: str):
    for pattern, name, brans, diff, phys, elective in KNOWN:
        if re.search(pattern, code):
            return name, brans, diff, phys, elective
    return None, "", 0, 0, 0


def room_type(code: str) -> str:
    for pattern, kind in ROOM_TYPES:
        if re.search(pattern, code):
            return kind
    return "Atölye"


def class_names(code: str) -> tuple[str, str | None]:
    """'ATP10A   2' -> ('ATP10A-2', 'ATP10A'); '12AMPE   1' -> ('AMP12E-1', 'AMP12E')."""
    m = re.match(r"^(\S+)\s+(\d+)$", code)
    if not m:
        return code, None
    base, num = m.group(1), m.group(2)
    flipped = re.match(r"^(\d+)([A-ZÇĞİÖŞÜ]+?)([A-ZÇĞİÖŞÜ])$", base)
    if flipped:
        base = f"{flipped.group(2)}{flipped.group(1)}{flipped.group(3)}"
    return f"{base}-{num}", base


def blocks_of(grid_items) -> list[tuple[int, int, int]]:
    """Contiguous runs (day, start, length) of one lesson in the grid."""
    slots = sorted({(g["day"], g["slot"] + i) for g in grid_items for i in range(g["len"])})
    runs = []
    for d, s in slots:
        if runs and runs[-1][0] == d and runs[-1][1] + runs[-1][2] == s:
            runs[-1] = (d, runs[-1][1], runs[-1][2] + 1)
        else:
            runs.append((d, s, 1))
    return runs


def import_school(db: Database, paths, timetable_name: str = "Mevcut program (okul)",
                  replace: bool = True) -> ImportResult:
    from app.database.seed import clear_all
    parsed: list[ParsedClass] = []
    times: list[str] = []
    for path in paths:
        cls, t = parse_workbook(path)
        parsed += cls
        times = times or t
    if not parsed:
        raise ValueError("Seçilen dosyalarda 'Sınıf Kodu' ile başlayan sınıf programı bulunamadı.")
    res = ImportResult()
    if replace:
        clear_all(db)
    max_slot = max((g["slot"] + g["len"] for pc in parsed for g in pc.grid), default=len(times))
    periods = max(len(times), max_slot)
    days_used = max((g["day"] for pc in parsed for g in pc.grid), default=4) + 1
    db.set_setting("periods_per_day", periods)
    db.set_setting("days_count", max(5, days_used))
    if times:
        db.set_setting("period_times", times[:periods])

    subj_svc, cur_svc = SubjectService(db), CurriculumService(db)
    teacher_svc, room_svc, class_svc = TeacherService(db), RoomService(db), ClassService(db)

    def is_external_teacher(name: str) -> bool:
        return name.replace("İ", "i").replace("I", "ı").lower().startswith("işletme")

    # ---- rooms (max_parallel = how many lessons the current timetable runs there at once)
    room_occ = defaultdict(Counter)
    lesson_by = {}
    for pc in parsed:
        for c in pc.courses:
            lesson_by[(pc.code, c["code"])] = c
    for pc in parsed:
        for g in pc.grid:
            course = lesson_by.get((pc.code, g["code"]), {})
            for room in g["rooms"] or course.get("rooms", []):
                for i in range(g["len"]):
                    room_occ[room][(g["day"], g["slot"] + i, g["code"], tuple(course.get("teachers", [])))] += 1
    rooms = {}
    for code in sorted({r for pc in parsed for c in pc.courses for r in c["rooms"]} |
                       {r for pc in parsed for g in pc.grid for r in g["rooms"]}):
        if code.startswith("AİME"):
            continue
        per_slot = Counter()
        for (d, s, _, _), _n in room_occ[code].items():
            per_slot[(d, s)] += 1
        parallel = max(per_slot.values(), default=1)
        rooms[code] = room_svc.save(Room(name=code, room_type=room_type(code), max_parallel=max(1, parallel),
                                         notes="Okul programından aktarıldı"))
    res.rooms = len(rooms)

    # ---- subjects
    observed = defaultdict(list)
    for pc in parsed:
        for c in pc.courses:
            runs = blocks_of([g for g in pc.grid if g["code"] == c["code"]])
            observed[c["code"]].append(runs)
    subjects = {}
    for code in sorted({c["code"] for pc in parsed for c in pc.courses}):
        name, brans, diff, phys, elective = subject_info(code)
        runs_list = observed[code]
        max_block = max((r[2] for runs in runs_list for r in runs), default=2)
        same_day = any(len({r[0] for r in runs}) < len(runs) for runs in runs_list)
        external = bool(re.search(r"İME$", code))
        hours = Counter(c["hours"] for pc in parsed for c in pc.courses if c["code"] == code).most_common(1)[0][0]
        grade = Counter(pc.grade for pc in parsed for c in pc.courses if c["code"] == code).most_common(1)[0][0]
        full = f"{name} ({code})" if name else code
        subjects[code] = subj_svc.save(Subject(
            name=full, short_name=code, default_hours=hours, grade=grade, brans=brans, difficulty=diff,
            physical=phys, elective=elective, vocational=0 if name and brans in (
                "Türk Dili ve Edebiyatı", "Matematik", "Fizik", "Kimya", "Biyoloji", "Coğrafya", "Tarih",
                "Din Kültürü ve Ahlak Bilgisi", "İngilizce", "Felsefe", "Beden Eğitimi", "Rehberlik") else 1,
            min_block=1, max_block=max(2, max_block), allow_same_day=1 if same_day else 0, external=1 if external else 0,
            room_type="Spor Salonu" if phys else ""))
    res.subjects = len(subjects)

    # ---- teachers
    teacher_names = sorted({t for pc in parsed for c in pc.courses for t in c["teachers"] if not is_external_teacher(t)})
    teacher_slots = defaultdict(set)
    teacher_codes = defaultdict(Counter)
    for pc in parsed:
        for c in pc.courses:
            for t in c["teachers"]:
                teacher_codes[t][c["code"]] += c["hours"]
        for g in pc.grid:
            course = lesson_by.get((pc.code, g["code"]), {})
            for t in course.get("teachers", []):
                for i in range(g["len"]):
                    teacher_slots[t].add((g["day"], g["slot"] + i))
    teachers = {}
    for name in teacher_names:
        branch_votes = Counter()
        for code, hours in teacher_codes[name].items():
            b = subject_info(code)[1]
            if b:
                branch_votes[b] += hours
        brans = branch_votes.most_common(1)[0][0] if branch_votes else ""
        slots = teacher_slots[name]
        weekly = len(slots)
        daily = max(Counter(d for d, _ in slots).values(), default=0)
        days = sorted({d for d, _ in slots})
        teachers[name] = teacher_svc.save(Teacher(
            name=name, brans=brans, max_daily=max(10, daily), max_weekly=max(30, weekly), min_weekly=0,
            max_consecutive=max(8, daily), preferred_days=",".join(map(str, days)) if 0 < len(days) < 5 else "",
            notes=f"Mevcut programda haftalık {weekly} ders saati."))
    res.teachers = len(teachers)

    # ---- classes and groups
    class_objs = {}
    parsed_sorted = sorted(parsed, key=lambda pc: (class_names(pc.code)[1] is not None, pc.code))
    for pc in parsed_sorted:
        name, parent = class_names(pc.code)
        parent_obj = class_objs.get(parent) if parent else None
        days = sorted({g["day"] for g in pc.grid}) or list(range(5))
        room_counter = Counter(r for g in pc.grid for r in g["rooms"] if r in rooms)
        home = rooms[room_counter.most_common(1)[0][0]].id if room_counter else None
        cur = cur_svc.save(Curriculum(name=f"{name} dersleri", grade=pc.grade,
                                      notes="Okul programından aktarılan sınıf planı"))
        obj = class_svc.save(SchoolClass(
            name=name, grade=pc.grade, program_type="Anadolu Teknik Programı" if name.startswith("ATP")
            else "Anadolu Meslek Programı", curriculum_id=cur.id, home_room_id=home,
            weekly_hours=int(pc.total or 0), available_days=",".join(map(str, range(max(5, days_used)))),
            parent_id=parent_obj.id if parent_obj else None,
            notes=(f"Sınıf öğretmeni: {pc.class_teacher}" if pc.class_teacher else "")))
        class_objs[name] = obj
        last = max((g["slot"] + g["len"] - 1 for g in pc.grid), default=periods - 1)
        if parent_obj is None:
            last = max([last] + [g["slot"] + g["len"] - 1 for other in parsed if class_names(other.code)[1] == name
                                 for g in other.grid])
        else:
            parent_last = max((g["slot"] + g["len"] - 1 for other in parsed if class_names(other.code)[0] == parent
                               for g in other.grid), default=last)
            last = max(last, parent_last)
        blocked = [(d, p) for d in range(max(5, days_used)) for p in range(last + 1, periods)]
        if blocked:
            class_svc.set_unavailable(obj.id, blocked)
        if parent_obj:
            res.groups += 1
        else:
            res.classes += 1
        for c in pc.courses:
            subject = subjects[c["code"]]
            cur_svc.set_item(cur.id, subject.id, c["hours"])
            team = [teachers[t].id for t in c["teachers"] if t in teachers]
            grid_items = [g for g in pc.grid if g["code"] == c["code"]]
            grid_room_sets = {tuple(g["rooms"]) for g in grid_items}
            names = list(dict.fromkeys(c["rooms"] + [r for rs in grid_room_sets for r in rs]))
            room_ids = [rooms[r].id for r in names if r in rooms]
            mode = "all" if len(room_ids) > 1 and all(set(rs) == set(names) for rs in grid_room_sets) else "any"
            runs = blocks_of(grid_items)
            split = "+".join(str(n) for n in sorted((r[2] for r in runs), reverse=True))
            class_svc.set_lesson_settings(obj.id, subject.id, teachers=team, rooms=room_ids, room_mode=mode,
                                          split=split)
            res.lessons += 1

    # ---- combined lessons: same subject, same teacher team, same hours in several classes/groups
    occurrences = defaultdict(list)
    for pc in parsed:
        name, _ = class_names(pc.code)
        for c in pc.courses:
            slots = tuple(sorted((g["day"], g["slot"] + i) for g in pc.grid if g["code"] == c["code"]
                                 for i in range(g["len"])))
            if c["teachers"] and not all(is_external_teacher(t) for t in c["teachers"]):
                occurrences[(c["code"], tuple(sorted(c["teachers"])), slots)].append(name)
    link_no = 0
    link_of = {}
    for (code, team, slots), names in occurrences.items():
        if len(names) > 1 and slots:
            link_no += 1
            subject = subjects[code]
            members = [(n, next(l for l in class_svc.lessons(class_objs[n].id) if l.subject_id == subject.id))
                       for n in names]
            all_rooms = list(dict.fromkeys(r for _, lesson in members for r in lesson.rooms))
            differ = len({tuple(lesson.rooms) for _, lesson in members}) > 1
            for n, lesson in members:
                class_svc.set_lesson_settings(class_objs[n].id, subject.id, teachers=lesson.teachers,
                                              rooms=all_rooms if differ else lesson.rooms,
                                              room_mode="all" if differ else lesson.room_mode,
                                              link=f"B{link_no}", split=lesson.split)
                link_of[(n, code)] = link_no
    res.combined = link_no

    # ---- current timetable as a variant
    entries = []
    block = 0
    for pc in parsed:
        name, _ = class_names(pc.code)
        obj = class_objs[name]
        previous = {}
        for g in sorted(pc.grid, key=lambda g: (g["day"], g["slot"])):
            c = lesson_by[(pc.code, g["code"])]
            team = [teachers[t].id for t in c["teachers"] if t in teachers]
            used_rooms = [rooms[r].id for r in (g["rooms"] or c["rooms"]) if r in rooms]
            prev = previous.get(g["code"])
            if not (prev and prev[0] == g["day"] and prev[1] == g["slot"]):
                block += 1
            previous[g["code"]] = (g["day"], g["slot"] + g["len"])
            for i in range(g["len"]):
                entries.append(Entry(class_id=obj.id, subject_id=subjects[g["code"]].id,
                                     teacher_id=team[0] if team else None,
                                     room_id=used_rooms[0] if used_rooms else None, day=g["day"],
                                     period=g["slot"] + i, block=block,
                                     extra_teachers=",".join(map(str, team[1:])),
                                     extra_rooms=",".join(map(str, used_rooms[1:])),
                                     link=link_of.get((name, g["code"]), 0)))
    tt = TimetableService(db).create(timetable_name, entries, source="excel", status="imported",
                                     notes="Okulun mevcut ders programı (Excel'den aktarıldı)")
    res.timetable_id = tt.id
    res.entries = len(entries)
    for pc in parsed:
        hours = sum(c["hours"] for c in pc.courses)
        if pc.total is not None and hours != pc.total:
            res.warnings.append(f"{pc.code}: ders saatleri toplamı {hours}, dosyadaki toplam {pc.total}.")
    unknown = [code for code in subjects if subject_info(code)[0] is None]
    if unknown:
        res.warnings.append(f"{len(unknown)} dersin tam adı bilinmiyor, kod olarak eklendi (Dersler bölümünden "
                            f"adlandırabilirsiniz): " + ", ".join(unknown[:25]) + (" …" if len(unknown) > 25 else ""))
    return res
