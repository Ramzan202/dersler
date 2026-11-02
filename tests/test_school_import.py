"""School timetable import (Sınıf Programları Excel layout) with teams, groups, combined lessons and İME.
The workbook is synthetic: real school files contain personal data and are not stored in the repository."""
from collections import Counter

from openpyxl import Workbook

from app.core.conflicts import check_timetable, hard_conflicts
from app.core.problem import build_problem
from app.core.scheduler import Scheduler
from app.services.class_service import ClassService
from app.services.room_service import RoomService
from app.services.timetable_service import TimetableService
from app.utils.school_import import class_names, import_school

TIMES = ["08:00 08:30", "08:30 09:00", "09:15 09:45", "09:45 10:15", "10:25 10:55", "10:55 11:25",
         "11:35 12:05", "12:05 12:35", "12:45 13:15", "13:20 13:50"]
DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]


def _write_class(ws, row, code, grid, courses, class_teacher="Ali VELİ"):
    ws.cell(row, 1, f"Sınıf Kodu {code}")
    row += 1
    for i, t in enumerate(TIMES):
        ws.cell(row, 2 + i, f"{i + 1}\n{t}")
    row += 1
    for d, day in enumerate(DAYS):
        ws.cell(row, 1, day)
        for (gd, slot, length, text) in grid:
            if gd == d:
                ws.cell(row, 2 + slot, text)
                if length > 1:
                    ws.merge_cells(start_row=row, start_column=2 + slot, end_row=row, end_column=1 + slot + length)
        row += 1
    ws.cell(row, 1, "Toplam Saat:")
    ws.cell(row, 3, sum(c[1] for c in courses))
    row += 1
    ws.cell(row, 1, "Sınıf Öğretmeni:")
    ws.cell(row, 3, class_teacher)
    row += 1
    for i, h in enumerate(["Sıra", "Ders", "HDS", "Mekan", "Öğretmen Adı"]):
        ws.cell(row, 1 + i, h)
    row += 1
    for n, (code_, hours, rooms, teachers) in enumerate(courses, start=1):
        ws.cell(row, 1, n)
        ws.cell(row, 2, code_)
        ws.cell(row, 3, hours)
        ws.cell(row, 4, rooms)
        ws.cell(row, 5, teachers)
        row += 1
    return row + 2


def make_school(path):
    wb = Workbook()
    ws = wb.active
    ws.cell(1, 1, "T.C.")
    r = 3
    r = _write_class(ws, r, "AMP9A", [
        (0, 0, 2, "MAT_9\nA.VEL\nZ_1"), (2, 0, 1, "MAT_9\nA.VEL\nZ_1"),
        (0, 2, 2, "TDE_9\nA.KAY\nZ_1"), (1, 0, 2, "3BTT\nB.DMR\nBT1,BT2"), (3, 0, 2, "BED_9\nD.AKY\nSPOR"),
    ], [("MAT_9", 3, "Z_1", "Ali VELİ"), ("TDE_9", 2, "Z_1", "Ayşe KAYA"),
        ("3BTT", 2, "BT1,BT2", "Bora DEMİR,Cem SARI"), ("BED_9", 2, "SPOR", "Deniz AKAY")])
    r = _write_class(ws, r, "AMP9B", [
        (0, 0, 2, "TDE_9\nA.KAY\nZ_2"), (1, 0, 2, "MAT_9\nA.VEL\nZ_2"), (2, 2, 1, "MAT_9\nA.VEL\nZ_2"),
        (1, 2, 2, "3BTT\nB.DMR\nBT1,BT2"), (4, 0, 2, "BED_9\nD.AKY\nSPOR"),
    ], [("MAT_9", 3, "Z_2", "Ali VELİ"), ("TDE_9", 2, "Z_2", "Ayşe KAYA"),
        ("3BTT", 2, "BT1,BT2", "Bora DEMİR,Cem SARI"), ("BED_9", 2, "SPOR", "Deniz AKAY")])
    r = _write_class(ws, r, "ATP10A", [(0, 0, 2, "FİZ_10\nE.TAŞ\n1K_1"), (1, 0, 2, "FİZ_10\nE.TAŞ\n1K_1")],
                     [("FİZ_10", 4, "1K_1", "Emre TAŞ")])
    r = _write_class(ws, r, "ATP10A   1", [(2, 0, 3, "BDÇ10\nF.ÖZ\nCAD1"), (3, 0, 2, "MAK10\nG.YIL\nCAD4")],
                     [("BDÇ10", 3, "CAD1", "Fatma ÖZ"), ("MAK10", 2, "CAD4", "Gül YILDIZ")])
    r = _write_class(ws, r, "ATP10A   2", [(2, 0, 3, "BDÇ10\nF.ÖZ\nCAD2"), (3, 0, 2, "İİ10\nH.KAR\nİİF1A,İİT2")],
                     [("BDÇ10", 3, "CAD2", "Fatma ÖZ"), ("İİ10", 2, "İİF1A,İİT2", "Hakan KARA,İpek SU")])
    _write_class(ws, r, "AMP12E", [(0, 0, 8, "12İME\nİ.İŞL\nAİMEMT"), (1, 0, 2, "TDE_12\nA.KAY\n2K_1")],
                 [("12İME", 8, "AİMEMT", "İşletme 1 İşletme 1"), ("TDE_12", 2, "2K_1", "Ayşe KAYA")])
    wb.save(path)
    return path


def test_class_names():
    assert class_names("ATP10A   2") == ("ATP10A-2", "ATP10A")
    assert class_names("12AMPE   1") == ("AMP12E-1", "AMP12E")
    assert class_names("AMP9A") == ("AMP9A", None)


def test_import_builds_complete_model(db, tmp_path):
    res = import_school(db, [make_school(tmp_path / "10s_n_f_programlar_.xlsx")])
    assert (res.classes, res.groups, res.combined) == (4, 2, 1)
    assert res.teachers == 10  # the "İşletme" placeholder is not a teacher
    assert db.get_setting("periods_per_day") == 10 and db.get_setting("period_times")[0] == "08:00-08:30"
    classes = {c.name: c for c in ClassService(db).list()}
    assert classes["ATP10A-1"].parent_id == classes["ATP10A"].id
    problem = build_problem(db)
    lessons = {(problem.classes[l.class_id].name, problem.subjects[l.subject_id].short_name): l for l in problem.lessons}
    btt = lessons[("AMP9A", "3BTT")]
    assert btt.team and len(btt.teacher_candidates) == 2 and btt.room_mode == "all"
    bdc = next(l for l in problem.lessons if problem.subjects[l.subject_id].short_name == "BDÇ10")
    assert sorted(problem.classes[c].name for c in bdc.class_ids) == ["ATP10A-1", "ATP10A-2"]
    ime = lessons[("AMP12E", "12İME")]
    assert ime.external and not ime.teacher_candidates
    assert RoomService(db).get_by_name("BT1").max_parallel == 1


def test_current_timetable_is_valid_and_optimizable(db, tmp_path):
    res = import_school(db, [make_school(tmp_path / "9s_n_f_programlar_.xlsx")])
    problem = build_problem(db)
    current = TimetableService(db).entries(res.timetable_id)
    assert hard_conflicts(check_timetable(problem, current)) == []
    instances = {}
    for e in current:
        for t in e.teacher_ids:
            instances.setdefault((t, e.day, e.period), set()).add(e.link or ("entry", e.id))
    assert all(len(v) == 1 for v in instances.values())
    result = Scheduler(problem).solve(time_limit=30, hints=current)
    assert result.ok, result.explanations
    assert hard_conflicts(check_timetable(problem, result.entries)) == []
    assert len(result.entries) == len(current)
    bdc = [e for e in result.entries if problem.subjects[e.subject_id].short_name == "BDÇ10"]
    by_slot = Counter((e.day, e.period) for e in bdc)
    assert set(by_slot.values()) == {2} and all(e.link for e in bdc)
    group = {c.name: c for c in problem.classes.values()}
    parent_slots = {(e.day, e.period) for e in result.entries if e.class_id == group["ATP10A"].id}
    group_slots = {(e.day, e.period) for e in result.entries if e.class_id == group["ATP10A-1"].id}
    assert not parent_slots & group_slots


def test_team_and_room_rules_are_checked(db, tmp_path):
    res = import_school(db, [make_school(tmp_path / "9s_n_f_programlar_.xlsx")])
    problem = build_problem(db)
    entries = TimetableService(db).entries(res.timetable_id)
    a = next(e for e in entries if problem.subjects[e.subject_id].short_name == "3BTT")
    b = next(e for e in entries if problem.classes[e.class_id].name == "AMP9B"
             and problem.subjects[e.subject_id].short_name == "TDE_9")
    b.day, b.period = a.day, a.period
    b.extra_teachers = ",".join(str(t) for t in a.teacher_ids)
    kinds = {c.kind for c in check_timetable(problem, entries)}
    assert "teacher_clash" in kinds
