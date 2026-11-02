import pytest

from app.core.problem import build_problem
from app.database.models import Subject
from app.database.seed import load_demo_data
from app.services.class_service import ClassService
from app.services.subject_service import CurriculumService, SubjectService
from app.services.teacher_service import TeacherService
from app.services.timetable_service import TimetableService
from app.utils.backup import create_backup, restore_backup
from app.utils.excel_export import export_data, export_timetable
from app.utils.excel_import import import_workbook, parse_days, parse_periods
from app.utils.pdf_export import export_pdf


def test_crud_and_validation(db):
    svc = SubjectService(db)
    s = svc.save(Subject(name="Kimya", default_hours=2))
    assert svc.get(s.id).name == "Kimya"
    with pytest.raises(ValueError):
        svc.save(Subject(name="Kimya"))
    with pytest.raises(ValueError):
        svc.save(Subject(name="X", allowed_splits="3+a"))
    svc.delete(s.id)
    assert svc.count() == 0


def test_demo_curricula_hours(db):
    load_demo_data(db)
    cur = CurriculumService(db)
    totals = {c.name: cur.total_hours(c.id) for c in cur.list()}
    bt = "Bilişim Teknolojileri – Yazılım Geliştirme (AMP)"
    assert totals[f"9. Sınıf {bt}"] == 45
    assert totals[f"10. Sınıf {bt}"] == 45
    assert totals[f"11. Sınıf {bt}"] == 45
    assert totals[f"12. Sınıf {bt}"] == 20


def test_meb_catalog_matches_pdf(db):
    from app.services import meb_catalog
    plans, kinds, meta = meb_catalog.load_catalog()
    assert len(plans) > 300 and len(meb_catalog.alans()) >= 55
    plan = meb_catalog.find("Bilişim Teknolojileri", "Anadolu Meslek Programı", "Yazılım Geliştirme")
    nine = dict(plan.grades["9"])
    assert nine["Türk Dili ve Edebiyatı"] == 5 and nine["Matematik"] == 5 and nine["Programlama Temelleri"] == 4
    assert nine["Seçmeli Dersler"] == 4 and plan.hours("9") == 45
    assert plan.ime == {"12": 24}
    assert "İşletmelerde Mesleki Eğitim" not in dict(plan.grades["12"])
    el = meb_catalog.dals("Elektrik-Elektronik Teknolojisi", "Anadolu Meslek Programı")
    assert "Elektrik Tesisatları ve Dağıtımı" in el and len(el) >= 5
    created = meb_catalog.import_plan(db, plan, ["9", "12"])
    assert [c.grade for c in created] == [9, 12]
    assert CurriculumService(db).total_hours(created[0].id) == 45
    assert "24 saat" in created[1].notes
    again = meb_catalog.import_plan(db, plan, ["9"])
    assert again[0].id == created[0].id


def test_class_extra_and_fixed_teacher(db):
    load_demo_data(db)
    cs, ss, ts = ClassService(db), SubjectService(db), TeacherService(db)
    c = cs.get_by_name("AMP11A")
    fel = ss.get_by_name("Felsefe")
    cs.set_extra_lesson(c.id, fel.id, 0)
    assert fel.id not in {l.subject_id for l in cs.lessons(c.id)}
    kim = ss.get_by_name("Kimya")
    cs.set_extra_lesson(c.id, kim.id, 2)
    t = ts.get_by_name("Emine Koç")
    cs.set_fixed_teacher(c.id, kim.id, t.id)
    lesson = next(l for l in build_problem(db).lessons if l.class_id == c.id and l.subject_id == kim.id)
    assert lesson.teacher_candidates == [t.id]


def test_parse_helpers():
    assert parse_days("Pazartesi, Salı") == [0, 1]
    assert parse_days("pzt;CUMA") == [0, 4]
    assert parse_periods("1-3, 5", 9) == [0, 1, 2, 4]
    assert parse_periods("tümü", 3) == [0, 1, 2]


def test_excel_roundtrip(db, tmp_path):
    from app.database.database import Database
    load_demo_data(db)
    path = export_data(db, tmp_path / "veri.xlsx")
    other = Database(":memory:")
    report = import_workbook(other, path)
    assert not report.errors, report.errors
    for table in ("subjects", "teachers", "rooms", "classes", "curricula", "curriculum_items", "unavailability",
                  "teacher_subjects", "class_fixed_teachers"):
        a = db.query_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
        b = other.query_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
        assert a == b, table
    p1, p2 = build_problem(db), build_problem(other)
    assert sum(l.hours for l in p1.lessons) == sum(l.hours for l in p2.lessons)


def test_timetable_variants_and_exports(small_school, tmp_path):
    from app.core.scheduler import Scheduler
    problem = build_problem(small_school)
    res = Scheduler(problem).solve(time_limit=20)
    svc = TimetableService(small_school)
    tt = svc.create("Program №1", res.entries)
    copy = svc.duplicate(tt.id, "Program №2")
    assert svc.active().id == copy.id
    assert len(svc.entries(copy.id)) == len(res.entries)
    entry = svc.entries(copy.id)[0]
    entry.locked = 1
    svc.update_entry(entry)
    assert "manuel" in svc.get(copy.id).source
    xlsx = export_timetable(problem, res.entries, tmp_path / "program.xlsx", period_times=["08:30-09:10"])
    assert xlsx.stat().st_size > 0
    for mode in ("class", "teacher", "room"):
        pdf = export_pdf(problem, res.entries, tmp_path / f"p_{mode}.pdf", mode=mode)
        assert pdf.read_bytes()[:4] == b"%PDF"


def test_backup_and_restore(tmp_path):
    from app.database.database import Database
    db = Database(tmp_path / "db.sqlite")
    load_demo_data(db)
    backup = create_backup(db, "test", tmp_path / "b")
    SubjectService(db).delete(SubjectService(db).get_by_name("Fizik").id)
    assert SubjectService(db).get_by_name("Fizik") is None
    restore_backup(db, backup, tmp_path / "b")
    assert SubjectService(db).get_by_name("Fizik") is not None
    db.close()
