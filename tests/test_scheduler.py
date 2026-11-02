from collections import Counter, defaultdict

from app.core.conflicts import check_timetable, hard_conflicts
from app.core.problem import build_problem
from app.core.scheduler import Scheduler
from app.core.validator import has_errors, validate
from app.services.class_service import ClassService
from app.services.room_service import RoomService
from app.services.subject_service import CurriculumService, SubjectService
from app.services.teacher_service import TeacherService


def solve(db, **kw):
    problem = build_problem(db)
    return problem, Scheduler(problem).solve(time_limit=kw.pop("time_limit", 30), **kw)


def test_feasible_schedule_satisfies_all_hard_constraints(small_school):
    problem, res = solve(small_school)
    assert res.ok, res.explanations
    assert hard_conflicts(check_timetable(problem, res.entries)) == []
    counts = Counter((e.class_id, e.subject_id) for e in res.entries)
    for lesson in problem.lessons:
        assert counts[(lesson.class_id, lesson.subject_id)] == lesson.hours


def test_class_days_and_split_rules(small_school):
    problem, res = solve(small_school)
    cls12 = ClassService(small_school).get_by_name("AMP12A")
    assert {e.day for e in res.entries if e.class_id == cls12.id} <= {0, 1}
    web = SubjectService(small_school).get_by_name("Web Tabanlı Uygulama Geliştirme")
    for cls in ("AMP11A", "AMP11B"):
        cid = ClassService(small_school).get_by_name(cls).id
        per_day = defaultdict(list)
        for e in res.entries:
            if e.class_id == cid and e.subject_id == web.id:
                per_day[e.day].append(e.period)
        assert sorted(len(v) for v in per_day.values()) == [3, 3]
        for periods in per_day.values():
            assert max(periods) - min(periods) == 2


def test_teacher_unavailability_respected(small_school):
    ts = TeacherService(small_school)
    t = ts.get_by_name("Gül Çınar")
    blocked = {(d, p) for d in (2, 3) for p in range(6)}
    ts.set_unavailable(t.id, blocked)
    problem, res = solve(small_school)
    assert res.ok
    assert not any(e.teacher_id == t.id and (e.day, e.period) in blocked for e in res.entries)


def test_room_unavailability_and_required_room(small_school):
    rs = RoomService(small_school)
    lab = rs.get_by_name("Lab-1")
    rs.set_unavailable(lab.id, {(0, p) for p in range(6)})
    problem, res = solve(small_school)
    assert res.ok
    web = SubjectService(small_school).get_by_name("Web Tabanlı Uygulama Geliştirme")
    web_entries = [e for e in res.entries if e.subject_id == web.id]
    assert all(e.room_id == lab.id and e.day != 0 for e in web_entries)


def test_qualification_and_load_limits(small_school):
    ts = TeacherService(small_school)
    for t in ts.list():
        t.max_daily = 4
        ts.save(t)
    problem, res = solve(small_school)
    assert res.ok
    for lesson in problem.lessons:
        teachers = {e.teacher_id for e in res.entries if (e.class_id, e.subject_id) == (lesson.class_id, lesson.subject_id)}
        assert len(teachers) == 1 and teachers <= set(lesson.teacher_candidates)
    daily = Counter((e.teacher_id, e.day) for e in res.entries)
    assert max(daily.values()) <= 4


def test_teacher_balance_within_branch(small_school):
    small_school.set_setting("weights", {"teacher_balance": 10})
    problem, res = solve(small_school)
    loads = Counter(e.teacher_id for e in res.entries)
    ts = TeacherService(small_school)
    a, b = ts.get_by_name("Ayşe Yılmaz").id, ts.get_by_name("Şükrü Öz").id
    assert abs(loads[a] - loads[b]) <= 2


def test_infeasible_is_reported_with_reason(small_school):
    ts = TeacherService(small_school)
    t = ts.get_by_name("Gül Çınar")
    ts.set_unavailable(t.id, {(d, p) for d in (0, 1) for p in range(6)})
    problem = build_problem(small_school)
    assert not has_errors(validate(small_school, problem))
    res = Scheduler(problem).solve(time_limit=20)
    assert res.status == "infeasible"
    assert not res.entries
    text = " ".join(res.explanations)
    assert "Gül Çınar" in text and "AMP12A" in text


def test_validator_detects_data_errors(small_school):
    subj = SubjectService(small_school)
    s = subj.get_by_name("Beden Eğitimi")
    s.brans = "Yok"
    subj.save(s)
    cs = ClassService(small_school)
    c = cs.get_by_name("AMP12A")
    c.available_days = "0"
    c.max_daily = 3
    cs.save(c)
    issues = validate(small_school, build_problem(small_school))
    msgs = " ".join(i.message for i in issues if i.is_error)
    assert "Beden Eğitimi" in msgs and "öğretmen yok" in msgs
    assert "AMP12A" in msgs


def test_locked_entries_are_kept(small_school):
    problem, res = solve(small_school)
    locked = [e for e in res.entries if e.class_id == problem.lessons[0].class_id][:2]
    problem2 = build_problem(small_school)
    res2 = Scheduler(problem2).solve(time_limit=20, locked=locked, hints=res.entries)
    assert res2.ok
    got = {(e.class_id, e.subject_id, e.day, e.period, e.teacher_id) for e in res2.entries}
    for e in locked:
        assert (e.class_id, e.subject_id, e.day, e.period, e.teacher_id) in got


def test_conflict_checker_detects_manual_errors(small_school):
    problem, res = solve(small_school)
    entries = res.entries
    a = entries[0]
    other = next(e for e in entries if e.class_id != a.class_id and e.teacher_id != a.teacher_id
                 and (e.day, e.period) != (a.day, a.period))
    other.teacher_id = a.teacher_id
    other.day, other.period = a.day, a.period
    kinds = {c.kind for c in check_timetable(problem, entries)}
    assert "teacher_clash" in kinds


def test_full_demo_school_is_solved():
    from app.database.database import Database
    from app.database.seed import load_demo_data
    db = Database(":memory:")
    db.set_setting("periods_per_day", 9)
    load_demo_data(db)
    problem = build_problem(db)
    assert not has_errors(validate(db, problem))
    res = Scheduler(problem).solve(time_limit=150)
    assert res.ok, res.explanations
    assert hard_conflicts(check_timetable(problem, res.entries)) == []
    assert len(res.entries) == sum(l.hours for l in problem.lessons)
