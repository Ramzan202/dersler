import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.database import Database  # noqa: E402
from app.database.models import Curriculum, Room, SchoolClass, Subject, Teacher  # noqa: E402
from app.services.class_service import ClassService  # noqa: E402
from app.services.room_service import RoomService  # noqa: E402
from app.services.subject_service import CurriculumService, SubjectService  # noqa: E402
from app.services.teacher_service import TeacherService  # noqa: E402


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def small_school(db):
    """Two classes, a computer lab subject with 3+3 split, a gym subject and a class that attends only two days."""
    db.set_setting("days_count", 5)
    db.set_setting("periods_per_day", 6)
    subj, cur = SubjectService(db), CurriculumService(db)
    rooms, teachers, classes = RoomService(db), TeacherService(db), ClassService(db)
    mat = subj.save(Subject(name="Matematik", brans="Matematik", difficulty=2, max_block=2))
    tde = subj.save(Subject(name="Türk Dili ve Edebiyatı", brans="Türkçe", max_block=2))
    web = subj.save(Subject(name="Web Tabanlı Uygulama Geliştirme", brans="Bilişim", max_block=3,
                            room_type="Bilgisayar Laboratuvarı", room_required=1, allowed_splits="3+3",
                            preferred_split="3+3"))
    bed = subj.save(Subject(name="Beden Eğitimi", brans="Beden", physical=1, room_type="Spor Salonu",
                            room_required=1))
    plan = cur.save(Curriculum(name="Plan A", grade=11))
    for s, h in ((mat, 4), (tde, 4), (web, 6), (bed, 2)):
        cur.set_item(plan.id, s.id, h)
    short = cur.save(Curriculum(name="Plan 12", grade=12))
    for s, h in ((mat, 2), (tde, 2)):
        cur.set_item(short.id, s.id, h)
    a101 = rooms.save(Room(name="A101"))
    a102 = rooms.save(Room(name="A102"))
    a103 = rooms.save(Room(name="A103"))
    rooms.save(Room(name="Lab-1", room_type="Bilgisayar Laboratuvarı"))
    rooms.save(Room(name="Spor Salonu", room_type="Spor Salonu"))
    for name, brans in (("Ayşe Yılmaz", "Matematik"), ("Şükrü Öz", "Matematik"), ("Gül Çınar", "Türkçe"),
                        ("İlker Ağaoğlu", "Bilişim"), ("Ümit Işık", "Beden")):
        teachers.save(Teacher(name=name, brans=brans, max_daily=6, max_weekly=30))
    classes.save(SchoolClass(name="AMP11A", grade=11, curriculum_id=plan.id, home_room_id=a101.id))
    classes.save(SchoolClass(name="AMP11B", grade=11, curriculum_id=plan.id, home_room_id=a102.id))
    classes.save(SchoolClass(name="AMP12A", grade=12, curriculum_id=short.id, home_room_id=a103.id,
                             available_days="0,1"))
    return db
