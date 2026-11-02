"""Excel import of master data. The workbook format is identical to the data export (excel_export.export_data),
so a user can export, edit in Excel and import again. Records are matched by name (insert or update)."""
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from app.config import ALL_DAY_NAMES, PROGRAM_TYPES, SHORT_DAY_NAMES
from app.database.database import Database
from app.database.models import Curriculum, Room, SchoolClass, Subject, Teacher, format_int_list
from app.services.class_service import ClassService
from app.services.room_service import RoomService
from app.services.subject_service import CurriculumService, SubjectService
from app.services.teacher_service import TeacherService

SHEETS = {
    "Dersler": ["Ad", "Kısa Ad", "Varsayılan Saat", "Sınıf Düzeyi", "Alan", "Dal", "Branş", "Zorluk (0-2)",
                "Fiziksel Etkinlik", "Tercih Edilen Zaman", "Derslik Türü", "Derslik Zorunlu", "En Küçük Blok",
                "En Büyük Blok", "İzin Verilen Bölünmeler", "Yasaklı Bölünmeler", "Tercih Edilen Bölünme",
                "Aynı Gün Birden Fazla Blok", "Seçmeli", "Mesleki", "Renk"],
    "Derslikler": ["Ad", "Tür", "Kapasite", "Donanım", "Alan", "Uygun Dersler", "Notlar"],
    "Öğretmenler": ["Ad Soyad", "Branş", "Günlük En Fazla", "Haftalık En Fazla", "Haftalık En Az",
                    "Art Arda En Fazla", "Tercih Edilen Günler", "Dersler", "Notlar"],
    "Öğretim Planları": ["Plan", "Sınıf Düzeyi", "Alan", "Dal", "Program", "Ders", "Saat"],
    "Sınıflar": ["Ad", "Sınıf Düzeyi", "Alan", "Dal", "Program", "Öğretim Planı", "Sınıf Dersliği",
                 "Öğrenci Sayısı", "Haftalık Saat", "Günlük En Fazla", "Okul Günleri", "Notlar"],
    "Sınıf Ek Dersleri": ["Sınıf", "Ders", "Saat", "Sabit Öğretmen"],
    "Müsaitlik": ["Tür", "Ad", "Gün", "Kapalı Saatler"],
}

TIME_WORDS = {"farketmez": "any", "any": "any", "sabah": "morning", "morning": "morning",
              "öğleden sonra": "afternoon", "ogleden sonra": "afternoon", "afternoon": "afternoon", "akşam": "afternoon"}
ENTITY_WORDS = {"öğretmen": "teacher", "ogretmen": "teacher", "teacher": "teacher", "derslik": "room",
                "room": "room", "sınıf": "class", "sinif": "class", "class": "class"}


@dataclass
class ImportReport:
    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def add(self, sheet: str):
        self.counts[sheet] = self.counts.get(sheet, 0) + 1

    def text(self) -> str:
        lines = [f"{sheet}: {n} kayıt" for sheet, n in self.counts.items()] or ["Hiç kayıt içe aktarılmadı."]
        if self.errors:
            lines.append("")
            lines.append(f"{len(self.errors)} satır atlandı:")
            lines.extend(self.errors[:50])
        return "\n".join(lines)


def _s(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _i(value, default=0) -> int:
    text = _s(value)
    if not text:
        return default
    return int(float(text.replace(",", ".")))


def _b(value) -> int:
    return 1 if _s(value).lower() in ("1", "e", "evet", "x", "true", "doğru", "var", "yes") else 0


def _tr_lower(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


def parse_days(text) -> list[int]:
    text = _s(text)
    if not text:
        return []
    if _tr_lower(text) in ("tümü", "hepsi", "*", "tüm hafta"):
        return list(range(len(ALL_DAY_NAMES)))
    days = []
    names = [_tr_lower(n) for n in ALL_DAY_NAMES]
    shorts = [_tr_lower(n) for n in SHORT_DAY_NAMES]
    for token in text.replace(";", ",").split(","):
        tok = _tr_lower(token.strip())
        if not tok:
            continue
        if tok.isdigit():
            days.append(int(tok) - 1)
        elif tok in names:
            days.append(names.index(tok))
        elif tok[:3] in shorts:
            days.append(shorts.index(tok[:3]))
        else:
            raise ValueError(f"gün anlaşılamadı: '{token.strip()}'")
    return sorted(set(days))


def parse_periods(text, periods: int) -> list[int]:
    text = _s(text)
    if not text or _tr_lower(text) in ("tümü", "hepsi", "*", "tüm gün"):
        return list(range(periods))
    result = []
    for token in text.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            result.extend(range(int(a) - 1, int(b)))
        else:
            result.append(int(token) - 1)
    return sorted({p for p in result if 0 <= p < periods})


def _rows(wb, sheet: str):
    if sheet not in wb.sheetnames:
        return []
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [_s(h) for h in rows[0]]
    out = []
    for idx, row in enumerate(rows[1:], start=2):
        if row is None or all(_s(v) == "" for v in row):
            continue
        out.append((idx, {header[i]: row[i] for i in range(min(len(header), len(row))) if header[i]}))
    return out


def import_workbook(db: Database, path: Path | str) -> ImportReport:
    wb = load_workbook(str(path), data_only=True)
    report = ImportReport()
    periods = int(db.get_setting("periods_per_day"))
    subj_svc, cur_svc = SubjectService(db), CurriculumService(db)
    room_svc, teacher_svc, class_svc = RoomService(db), TeacherService(db), ClassService(db)

    def subject_id(name: str) -> int:
        s = subj_svc.get_by_name(name.strip())
        if s is None:
            raise ValueError(f"ders bulunamadı: '{name}'")
        return s.id

    def run(sheet, handler):
        for line, row in _rows(wb, sheet):
            try:
                handler(row)
                report.add(sheet)
            except Exception as exc:
                report.errors.append(f"{sheet}, satır {line}: {exc}")

    def subject_row(r):
        name = _s(r.get("Ad"))
        existing = subj_svc.get_by_name(name)
        s = existing or Subject(name=name)
        s.short_name = _s(r.get("Kısa Ad"))
        s.default_hours = _i(r.get("Varsayılan Saat"), 2)
        s.grade = _i(r.get("Sınıf Düzeyi"), 0) or None
        s.alan, s.dal, s.brans = _s(r.get("Alan")), _s(r.get("Dal")), _s(r.get("Branş"))
        s.difficulty = max(0, min(2, _i(r.get("Zorluk (0-2)"), 0)))
        s.physical = _b(r.get("Fiziksel Etkinlik"))
        s.preferred_time = TIME_WORDS.get(_tr_lower(_s(r.get("Tercih Edilen Zaman"))), "any")
        s.room_type = _s(r.get("Derslik Türü"))
        s.room_required = _b(r.get("Derslik Zorunlu"))
        s.min_block = _i(r.get("En Küçük Blok"), 1)
        s.max_block = _i(r.get("En Büyük Blok"), 2)
        s.allowed_splits = _s(r.get("İzin Verilen Bölünmeler"))
        s.forbidden_splits = _s(r.get("Yasaklı Bölünmeler"))
        s.preferred_split = _s(r.get("Tercih Edilen Bölünme"))
        s.allow_same_day = _b(r.get("Aynı Gün Birden Fazla Blok"))
        s.elective = _b(r.get("Seçmeli"))
        s.vocational = _b(r.get("Mesleki"))
        s.color = _s(r.get("Renk"))
        subj_svc.save(s)

    def room_row(r):
        name = _s(r.get("Ad"))
        room = room_svc.get_by_name(name) or Room(name=name)
        room.room_type = _s(r.get("Tür")) or "Derslik"
        room.capacity = _i(r.get("Kapasite"), 0)
        room.equipment, room.alan, room.notes = _s(r.get("Donanım")), _s(r.get("Alan")), _s(r.get("Notlar"))
        names = [x for x in _s(r.get("Uygun Dersler")).split(";") if x.strip()]
        room.subject_ids = [subject_id(n) for n in names]
        room_svc.save(room)

    def teacher_row(r):
        name = _s(r.get("Ad Soyad"))
        t = teacher_svc.get_by_name(name) or Teacher(name=name)
        t.brans = _s(r.get("Branş"))
        t.max_daily = _i(r.get("Günlük En Fazla"), 8)
        t.max_weekly = _i(r.get("Haftalık En Fazla"), 30)
        t.min_weekly = _i(r.get("Haftalık En Az"), 0)
        t.max_consecutive = _i(r.get("Art Arda En Fazla"), 6)
        t.preferred_days = format_int_list(parse_days(r.get("Tercih Edilen Günler")))
        names = [x for x in _s(r.get("Dersler")).split(";") if x.strip()]
        t.subject_ids = [subject_id(n) for n in names]
        t.notes = _s(r.get("Notlar"))
        teacher_svc.save(t)

    def plan_row(r):
        name = _s(r.get("Plan"))
        cur = cur_svc.get_by_name(name)
        if cur is None:
            cur = cur_svc.save(Curriculum(name=name, grade=_i(r.get("Sınıf Düzeyi"), 0) or None,
                                          alan=_s(r.get("Alan")), dal=_s(r.get("Dal")),
                                          program_type=_s(r.get("Program")) or PROGRAM_TYPES[0]))
        subj = _s(r.get("Ders"))
        if subj:
            cur_svc.set_item(cur.id, subject_id(subj), _i(r.get("Saat"), 0))

    def class_row(r):
        name = _s(r.get("Ad"))
        c = class_svc.get_by_name(name) or SchoolClass(name=name)
        c.grade = _i(r.get("Sınıf Düzeyi"), 9)
        c.alan, c.dal = _s(r.get("Alan")), _s(r.get("Dal"))
        c.program_type = _s(r.get("Program")) or PROGRAM_TYPES[0]
        plan = _s(r.get("Öğretim Planı"))
        if plan:
            cur = cur_svc.get_by_name(plan)
            if cur is None:
                raise ValueError(f"öğretim planı bulunamadı: '{plan}'")
            c.curriculum_id = cur.id
        room = _s(r.get("Sınıf Dersliği"))
        if room:
            rr = room_svc.get_by_name(room)
            if rr is None:
                raise ValueError(f"derslik bulunamadı: '{room}'")
            c.home_room_id = rr.id
        c.student_count = _i(r.get("Öğrenci Sayısı"), 0)
        c.weekly_hours = _i(r.get("Haftalık Saat"), 0)
        c.max_daily = _i(r.get("Günlük En Fazla"), 0)
        days = parse_days(r.get("Okul Günleri"))
        c.available_days = format_int_list(days or range(int(db.get_setting("days_count"))))
        c.notes = _s(r.get("Notlar"))
        class_svc.save(c)

    def extra_row(r):
        c = class_svc.get_by_name(_s(r.get("Sınıf")))
        if c is None:
            raise ValueError(f"sınıf bulunamadı: '{_s(r.get('Sınıf'))}'")
        sid = subject_id(_s(r.get("Ders")))
        hours_text = _s(r.get("Saat"))
        if hours_text:
            class_svc.set_extra_lesson(c.id, sid, _i(hours_text))
        teacher = _s(r.get("Sabit Öğretmen"))
        if teacher:
            t = teacher_svc.get_by_name(teacher)
            if t is None:
                raise ValueError(f"öğretmen bulunamadı: '{teacher}'")
            class_svc.set_fixed_teacher(c.id, sid, t.id)

    cleared: set[tuple[str, int]] = set()

    def avail_row(r):
        kind = ENTITY_WORDS.get(_tr_lower(_s(r.get("Tür"))))
        if kind is None:
            raise ValueError("Tür 'Öğretmen', 'Derslik' veya 'Sınıf' olmalı")
        svc = {"teacher": teacher_svc, "room": room_svc, "class": class_svc}[kind]
        obj = svc.get_by_name(_s(r.get("Ad")))
        if obj is None:
            raise ValueError(f"kayıt bulunamadı: '{_s(r.get('Ad'))}'")
        days = parse_days(r.get("Gün"))
        if not days:
            raise ValueError("gün belirtilmemiş")
        pers = parse_periods(r.get("Kapalı Saatler"), periods)
        current = set() if (kind, obj.id) not in cleared else svc.get_unavailable(obj.id)
        cleared.add((kind, obj.id))
        current |= {(d, p) for d in days for p in pers}
        svc.set_unavailable(obj.id, current)

    run("Dersler", subject_row)
    run("Derslikler", room_row)
    run("Öğretmenler", teacher_row)
    run("Öğretim Planları", plan_row)
    run("Sınıflar", class_row)
    run("Sınıf Ek Dersleri", extra_row)
    run("Müsaitlik", avail_row)
    return report
