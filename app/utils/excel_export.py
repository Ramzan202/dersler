from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.config import ALL_DAY_NAMES
from app.core.problem import Problem
from app.core.workload import build_report
from app.database.database import Database
from app.database.models import Entry, parse_int_list
from app.services.class_service import ClassService
from app.services.room_service import RoomService
from app.services.subject_service import CurriculumService, SubjectService
from app.services.teacher_service import TeacherService
from app.utils.colors import subject_color
from app.utils.excel_import import SHEETS

THIN = Side(style="thin", color="999999")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(bold=True, color="FFFFFF")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _style_header(ws, row: int = 1):
    for cell in ws[row]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = BORDER


def _autowidth(ws, minimum: int = 8, maximum: int = 45):
    widths = defaultdict(int)
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None:
                longest = max(len(line) for line in str(cell.value).split("\n"))
                widths[cell.column_letter] = max(widths[cell.column_letter], longest)
    for col, w in widths.items():
        ws.column_dimensions[col].width = max(minimum, min(maximum, w + 2))


def safe_sheet_title(title: str, used: set[str]) -> str:
    for ch in '[]:*?/\\':
        title = title.replace(ch, "-")
    base = title[:31]
    candidate, n = base, 2
    while candidate in used:
        suffix = f" ({n})"
        candidate = base[:31 - len(suffix)] + suffix
        n += 1
    used.add(candidate)
    return candidate


def _ranges(values: list[int]) -> str:
    values = sorted(values)
    parts, start, prev = [], None, None
    for v in values:
        if start is None:
            start = prev = v
        elif v == prev + 1:
            prev = v
        else:
            parts.append(f"{start + 1}-{prev + 1}" if start != prev else f"{start + 1}")
            start = prev = v
    if start is not None:
        parts.append(f"{start + 1}-{prev + 1}" if start != prev else f"{start + 1}")
    return ", ".join(parts)


def export_data(db: Database, path: Path | str, template_only: bool = False) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    sheets = {name: wb.create_sheet(name) for name in SHEETS}
    for name, ws in sheets.items():
        ws.append(SHEETS[name])
        _style_header(ws)
        ws.freeze_panes = "A2"
    if not template_only:
        subj_svc, cur_svc = SubjectService(db), CurriculumService(db)
        room_svc, teacher_svc, class_svc = RoomService(db), TeacherService(db), ClassService(db)
        subjects = {s.id: s for s in subj_svc.list()}
        rooms = {r.id: r for r in room_svc.list()}
        teachers = {t.id: t for t in teacher_svc.list()}
        curricula = {c.id: c for c in cur_svc.list()}
        time_text = {"any": "Farketmez", "morning": "Sabah", "afternoon": "Öğleden sonra"}
        yn = lambda v: "Evet" if v else "Hayır"  # noqa: E731
        for s in subjects.values():
            sheets["Dersler"].append([s.name, s.short_name, s.default_hours, s.grade or "", s.alan, s.dal, s.brans,
                                      s.difficulty, yn(s.physical), time_text.get(s.preferred_time, "Farketmez"),
                                      s.room_type, yn(s.room_required), s.min_block, s.max_block, s.allowed_splits,
                                      s.forbidden_splits, s.preferred_split, yn(s.allow_same_day), yn(s.elective),
                                      yn(s.vocational), s.color, yn(s.external)])
        for r in rooms.values():
            sheets["Derslikler"].append([r.name, r.room_type, r.capacity, r.equipment, r.alan,
                                         "; ".join(subjects[i].name for i in r.subject_ids if i in subjects), r.notes,
                                         r.max_parallel])
        for t in teachers.values():
            sheets["Öğretmenler"].append([t.name, t.brans, t.max_daily, t.max_weekly, t.min_weekly,
                                          t.max_consecutive, ", ".join(ALL_DAY_NAMES[d] for d in t.preferred_day_list),
                                          "; ".join(subjects[i].name for i in t.subject_ids if i in subjects),
                                          t.notes])
        for c in curricula.values():
            for item in cur_svc.items(c.id):
                sheets["Öğretim Planları"].append([c.name, c.grade or "", c.alan, c.dal, c.program_type,
                                                   subjects[item.subject_id].name, item.hours])
        class_names = {c.id: c.name for c in class_svc.list()}
        for c in class_svc.list():
            sheets["Sınıflar"].append([c.name, c.grade, c.alan, c.dal, c.program_type,
                                       curricula[c.curriculum_id].name if c.curriculum_id in curricula else "",
                                       rooms[c.home_room_id].name if c.home_room_id in rooms else "",
                                       c.student_count, c.weekly_hours, c.max_daily,
                                       ", ".join(ALL_DAY_NAMES[d] for d in parse_int_list(c.available_days)),
                                       c.notes, class_names.get(c.parent_id, "")])
            fixed = class_svc.fixed_teachers(c.id)
            extras = class_svc.extra_lessons(c.id)
            settings = {r["subject_id"]: r for r in db.query("SELECT * FROM class_lesson_settings WHERE class_id = ?",
                                                             (c.id,))}
            for sid in sorted(set(fixed) | set(extras) | set(settings)):
                st = settings.get(sid)
                team = rooms_txt = mode = link = split = ""
                if st is not None:
                    team = "; ".join(teachers[int(t)].name for t in st["teachers"].split(",") if t and int(t) in teachers)
                    rooms_txt = "; ".join(rooms[int(r)].name for r in st["rooms"].split(",") if r and int(r) in rooms)
                    mode = "Hepsi aynı anda" if st["room_mode"] == "all" else "Birini seç"
                    link, split = st["link"], st["split"]
                sheets["Sınıf Ek Dersleri"].append([
                    c.name, subjects[sid].name, extras.get(sid, ""),
                    teachers[fixed[sid]].name if fixed.get(sid) in teachers else "", team, rooms_txt, mode, link,
                    split])
        for kind, label, svc, items in (("teacher", "Öğretmen", teacher_svc, teachers.values()),
                                        ("room", "Derslik", room_svc, rooms.values()),
                                        ("class", "Sınıf", class_svc, class_svc.list())):
            for obj in items:
                by_day = defaultdict(list)
                for d, p in svc.get_unavailable(obj.id):
                    by_day[d].append(p)
                for d in sorted(by_day):
                    sheets["Müsaitlik"].append([label, obj.name, ALL_DAY_NAMES[d], _ranges(by_day[d])])
    for ws in sheets.values():
        _autowidth(ws)
    path = Path(path)
    wb.save(path)
    return path


def _cell_text(problem: Problem, e: Entry, mode: str) -> str:
    subj = problem.subjects[e.subject_id].label if e.subject_id in problem.subjects else "?"
    teacher = ", ".join(problem.teachers[t].name for t in e.teacher_ids if t in problem.teachers)
    room = ", ".join(problem.rooms[r].name for r in e.room_ids if r in problem.rooms)
    cls = problem.classes[e.class_id].name if e.class_id in problem.classes else ""
    if mode == "class":
        return "\n".join(x for x in (subj, teacher, room) if x)
    if mode == "teacher":
        return "\n".join(x for x in (cls, subj, room) if x)
    return "\n".join(x for x in (cls, subj, teacher) if x)


def _grid_sheet(ws, problem: Problem, title: str, entries: list[Entry], mode: str, period_times: list[str]):
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(["Saat"] + problem.days)
    _style_header(ws, 2)
    grid = {(e.day, e.period): e for e in entries}
    for p in range(problem.periods):
        label = f"{p + 1}. ders"
        if p < len(period_times) and period_times[p]:
            label += f"\n{period_times[p]}"
        row = [label]
        for d in range(problem.num_days):
            e = grid.get((d, p))
            row.append(_cell_text(problem, e, mode) if e else "")
        ws.append(row)
        r = ws.max_row
        ws.row_dimensions[r].height = 48
        for c, cell in enumerate(ws[r]):
            cell.alignment = CENTER
            cell.border = BORDER
            if c == 0:
                cell.font = Font(bold=True)
                continue
            e = grid.get((c - 1, p))
            if e and e.subject_id in problem.subjects:
                cell.fill = PatternFill("solid", fgColor=subject_color(problem.subjects[e.subject_id]).lstrip("#"))
    ws.column_dimensions["A"].width = 14
    for d in range(problem.num_days):
        ws.column_dimensions[get_column_letter(d + 2)].width = 24


def export_timetable(problem: Problem, entries: list[Entry], path: Path | str, title: str = "",
                     period_times: list[str] | None = None, parts=("school", "class", "teacher", "room", "load")) -> Path:
    period_times = period_times or []
    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()

    if "school" in parts:
        ws = wb.create_sheet(safe_sheet_title("Okul Programı", used))
        header = ["Sınıf"] + [f"{problem.days[d][:3]} {p + 1}" for d in range(problem.num_days)
                              for p in range(problem.periods)]
        ws.append([title or "Okul Ders Programı"])
        ws["A1"].font = Font(bold=True, size=14)
        ws.append(header)
        _style_header(ws, 2)
        by_class = defaultdict(dict)
        for e in entries:
            by_class[e.class_id][(e.day, e.period)] = e
        for cid, cls in sorted(problem.classes.items(), key=lambda kv: (kv[1].grade, kv[1].name)):
            row = [cls.name]
            for d in range(problem.num_days):
                for p in range(problem.periods):
                    e = by_class[cid].get((d, p))
                    if e:
                        subj = problem.subjects[e.subject_id].label
                        t = ", ".join(problem.teachers[x].name for x in e.teacher_ids if x in problem.teachers)
                        row.append(f"{subj}\n{t}")
                    else:
                        row.append("")
            ws.append(row)
            r = ws.max_row
            ws.row_dimensions[r].height = 36
            for i, cell in enumerate(ws[r]):
                cell.border = BORDER
                cell.alignment = CENTER
                if i > 0:
                    d, p = divmod(i - 1, problem.periods)
                    e = by_class[cid].get((d, p))
                    if e:
                        cell.fill = PatternFill("solid",
                                                fgColor=subject_color(problem.subjects[e.subject_id]).lstrip("#"))
        ws.freeze_panes = "B3"
        ws.column_dimensions["A"].width = 12
        for i in range(2, len(header) + 1):
            ws.column_dimensions[get_column_letter(i)].width = 13

    groups = []
    if "class" in parts:
        groups.append(("class", "S", sorted(problem.classes.values(), key=lambda c: (c.grade, c.name)),
                       lambda e, obj: e.class_id == obj.id, "Sınıf"))
    if "teacher" in parts:
        groups.append(("teacher", "Ö", sorted(problem.teachers.values(), key=lambda t: t.name),
                       lambda e, obj: obj.id in e.teacher_ids, "Öğretmen"))
    if "room" in parts:
        groups.append(("room", "D", sorted(problem.rooms.values(), key=lambda r: r.name),
                       lambda e, obj: obj.id in e.room_ids, "Derslik"))
    for mode, prefix, objs, pred, label in groups:
        for obj in objs:
            items = [e for e in entries if pred(e, obj)]
            if mode != "class":
                seen, unique = set(), []
                for e in items:
                    key = (e.day, e.period, e.link, e.subject_id) if e.link else ("id", id(e))
                    if key not in seen:
                        seen.add(key)
                        unique.append(e)
                items = unique
            if not items and mode != "class":
                continue
            ws = wb.create_sheet(safe_sheet_title(f"{prefix}-{obj.name}", used))
            _grid_sheet(ws, problem, f"{label}: {obj.name}" + (f"  ({len(items)} saat)" if mode != "class" else ""),
                        items, mode, period_times)

    if "load" in parts:
        report = build_report(problem, entries)
        ws = wb.create_sheet(safe_sheet_title("Öğretmen Yükleri", used))
        ws.append(["Öğretmen", "Branş", "Haftalık Ders", "Haftalık Sınır", "Çalıştığı Gün", "Boş Pencere"]
                  + problem.days)
        _style_header(ws)
        for tl in report.teacher_loads:
            ws.append([tl.name, tl.brans, tl.hours, tl.max_weekly, tl.days_worked, tl.gaps] + tl.daily)
        ws.append([])
        ws.append(["Branş", "Ortalama", "En az", "En çok", "Öğretmen sayısı"])
        _style_header(ws, ws.max_row)
        for b, (avg, lo, hi, n) in report.branch_stats.items():
            ws.append([b, round(avg, 1), lo, hi, n])
        _autowidth(ws)
    path = Path(path)
    wb.save(path)
    return path


