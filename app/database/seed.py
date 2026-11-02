"""Demonstration data based on the MEB weekly course schedule (Bilişim Teknolojileri alanı).

These data are only an example and can be edited completely from the user interface.
"""
from app.database.database import Database
from app.database.models import Room, SchoolClass, Subject, Teacher
from app.services import meb_catalog
from app.services.class_service import ClassService
from app.services.room_service import RoomService
from app.services.subject_service import CurriculumService, SubjectService
from app.services.teacher_service import TeacherService

LAB = "Bilgisayar Laboratuvarı"
WORKSHOP = "Atölye"
GYM = "Spor Salonu"

SUBJECTS = [
    dict(name="Türk Dili ve Edebiyatı", short_name="TDE", brans="Türk Dili ve Edebiyatı", default_hours=4),
    dict(name="Din Kültürü ve Ahlak Bilgisi", short_name="DKAB", brans="Din Kültürü", default_hours=2),
    dict(name="Tarih", short_name="TAR", brans="Tarih", default_hours=2),
    dict(name="T.C. İnkılap Tarihi ve Atatürkçülük", short_name="İNK", brans="Tarih", default_hours=2),
    dict(name="Coğrafya", short_name="COĞ", brans="Coğrafya", default_hours=2),
    dict(name="Matematik", short_name="MAT", brans="Matematik", default_hours=5, difficulty=2),
    dict(name="Fizik", short_name="FİZ", brans="Fizik", default_hours=2, difficulty=1),
    dict(name="Kimya", short_name="KİM", brans="Kimya", default_hours=2, difficulty=1),
    dict(name="Biyoloji", short_name="BİY", brans="Biyoloji", default_hours=2),
    dict(name="Yabancı Dil", short_name="İNG", brans="İngilizce", default_hours=2),
    dict(name="Beden Eğitimi ve Spor / Görsel Sanatlar / Müzik", short_name="BED", brans="Beden Eğitimi",
         default_hours=2, physical=1, room_type=GYM, room_required=1),
    dict(name="Felsefe", short_name="FEL", brans="Felsefe", default_hours=2),
    dict(name="Sağlık Bilgisi ve Trafik Kültürü", short_name="SAĞ", brans="Biyoloji", default_hours=1),
    dict(name="Rehberlik ve Yönlendirme", short_name="REH", brans="Rehberlik", default_hours=1),
    dict(name="Mesleki Gelişim Atölyesi", short_name="MGA", default_hours=2, vocational=1),
    dict(name="Programlama Temelleri", short_name="PRG", brans="Bilişim", default_hours=4, difficulty=1,
         room_type=LAB, room_required=1, vocational=1),
    dict(name="Bilişim Teknolojilerinin Temelleri", short_name="BTT", brans="Bilişim", default_hours=4,
         room_type=LAB, room_required=1, vocational=1),
    dict(name="Bilgisayarlı Tasarım Uygulamaları", short_name="BTU", brans="Bilişim", default_hours=2,
         room_type=LAB, room_required=1, vocational=1),
    dict(name="Nesne Tabanlı Programlama", short_name="NTP", brans="Bilişim", default_hours=7, difficulty=1,
         room_type=LAB, room_required=1, vocational=1, max_block=4, allowed_splits="3+2+2; 4+3; 2+2+2+1",
         preferred_split="3+2+2"),
    dict(name="Veri Tabanı Yönetimi", short_name="VTY", brans="Bilişim", default_hours=3, room_type=LAB,
         room_required=1, vocational=1, max_block=3),
    dict(name="Robotik ve Kodlama", short_name="ROB", brans="Bilişim", default_hours=3, room_type=LAB,
         room_required=1, vocational=1, max_block=3),
    dict(name="Web Tabanlı Uygulama Geliştirme", short_name="WEB", brans="Bilişim", default_hours=9, difficulty=1,
         room_type=LAB, room_required=1, vocational=1, max_block=3, allowed_splits="3+3+3; 3+2+2+2",
         preferred_split="3+3+3"),
    dict(name="Mobil Uygulamalar", short_name="MOB", brans="Bilişim", default_hours=4, room_type=LAB,
         room_required=1, vocational=1),
    dict(name="Grafik ve Canlandırma", short_name="GRF", brans="Bilişim", default_hours=4, room_type=LAB,
         room_required=1, vocational=1),
    dict(name="İşletmelerde Mesleki Eğitim", short_name="İME", brans="Bilişim", default_hours=2, vocational=1),
    dict(name="Temel Elektrik-Elektronik", short_name="TEE", brans="Elektrik", default_hours=8, difficulty=1,
         room_type=WORKSHOP, room_required=1, vocational=1, min_block=2, max_block=4),
    dict(name="Teknik Resim", short_name="TRS", brans="Elektrik", default_hours=2, vocational=1),
    dict(name="Seçmeli Dersler", short_name="SEÇ", default_hours=4, elective=1),
    dict(name="Seçmeli Meslek Dersleri", short_name="SMD", brans="Bilişim", default_hours=4, elective=1,
         vocational=1, min_block=2, max_block=4),
]

# Öğretim planları MEB çerçeve öğretim programlarından alınır (app/data/meb_cerceve_2026.json).
MEB_PLANS = [
    ("Bilişim Teknolojileri", "Anadolu Meslek Programı", "Yazılım Geliştirme", ["9", "10", "11", "12"]),
    ("Elektrik-Elektronik Teknolojisi", "Anadolu Meslek Programı", "Elektrik Tesisatları ve Dağıtımı", ["9"]),
]

SEC = "Seçmeli Dersler"
SMD = "Seçmeli Meslek Dersleri"
MGA = "Mesleki Gelişim Atölyesi"
TEACHERS = [
    ("Ayşe Yılmaz", "Türk Dili ve Edebiyatı", [SEC]),
    ("Mehmet Öztürk", "Türk Dili ve Edebiyatı", [SEC]),
    ("Fatma Çelik", "Din Kültürü", []),
    ("Ali Şahin", "Tarih", [SEC]),
    ("Zeynep Aydın", "Coğrafya", [SEC]),
    ("Mustafa Kılıç", "Matematik", [SEC]),
    ("Elif Doğan", "Matematik", [SEC]),
    ("Hüseyin Arslan", "Fizik", []),
    ("Emine Koç", "Kimya", []),
    ("İbrahim Kurt", "Biyoloji", []),
    ("Hatice Özdemir", "İngilizce", [SEC]),
    ("Ömer Güneş", "İngilizce", [SEC]),
    ("Gülşen Erdoğan", "Beden Eğitimi", []),
    ("Murat Aksoy", "Felsefe", [SEC]),
    ("Şule İnce", "Rehberlik", []),
    ("Burak Yıldız", "Bilişim", [MGA]),
    ("Cansu Polat", "Bilişim", [MGA]),
    ("Deniz Uçar", "Bilişim", []),
    ("Görkem Taş", "Bilişim", []),
    ("Emre Şen", "Bilişim", []),
    ("Selin Avcı", "Bilişim", []),
    ("Erkan Bulut", "Elektrik", [MGA]),
    ("Özlem Çakır", "Elektrik", [MGA]),
]

BT = ("Bilişim Teknolojileri", "Anadolu Meslek Programı", "Yazılım Geliştirme")
EL = ("Elektrik-Elektronik Teknolojisi", "Anadolu Meslek Programı", "Elektrik Tesisatları ve Dağıtımı")
ALL_DAYS = "0,1,2,3,4"
CLASSES = [
    ("AMP9A", 9, BT, "A101", ALL_DAYS), ("AMP9B", 9, BT, "A102", ALL_DAYS),
    ("AMP9C", 9, EL, "A103", ALL_DAYS), ("AMP9D", 9, EL, "A104", ALL_DAYS),
    ("AMP10A", 10, BT, "A105", ALL_DAYS), ("AMP10B", 10, BT, "A106", ALL_DAYS),
    ("AMP11A", 11, BT, "A107", ALL_DAYS), ("AMP11B", 11, BT, "A108", ALL_DAYS),
    # 12. sınıf: haftada 24 saat İşletmelerde Mesleki Eğitim, okulda yalnızca 3 gün
    ("AMP12A", 12, BT, "A109", "0,1,2"), ("AMP12B", 12, BT, "A110", "0,1,2"),
]


def clear_all(db: Database):
    with db.transaction() as conn:
        for table in ("timetable_entries", "timetables", "class_fixed_teachers", "class_extra_lessons",
                      "unavailability", "classes", "room_subjects", "rooms", "teacher_subjects", "teachers",
                      "curriculum_items", "curricula", "subjects"):
            conn.execute(f"DELETE FROM {table}")


def load_demo_data(db: Database, reset: bool = True):
    if reset:
        clear_all(db)
    subj_svc, cur_svc = SubjectService(db), CurriculumService(db)
    teacher_svc, room_svc, class_svc = TeacherService(db), RoomService(db), ClassService(db)

    subjects = {}
    for spec in SUBJECTS:
        s = subj_svc.save(Subject(**spec))
        subjects[s.name] = s

    curricula = {}
    for alan, program, dal, grades in MEB_PLANS:
        plan = meb_catalog.find(alan, program, dal)
        for cur in meb_catalog.import_plan(db, plan, grades):
            curricula[(alan, program, dal, str(cur.grade))] = cur

    rooms = {}
    for i in range(1, 11):
        rooms[f"A{100 + i}"] = room_svc.save(Room(name=f"A{100 + i}", room_type="Derslik", capacity=32,
                                                 equipment="Akıllı tahta"))
    for i in range(1, 4):
        rooms[f"BT Lab-{i}"] = room_svc.save(Room(name=f"BT Lab-{i}", room_type=LAB, capacity=32,
                                                 equipment="24 bilgisayar, projeksiyon", alan="Bilişim Teknolojileri"))
    rooms["Elektrik Atölyesi"] = room_svc.save(Room(name="Elektrik Atölyesi", room_type=WORKSHOP, capacity=32,
                                                    equipment="Deney setleri, ölçü aletleri",
                                                    alan="Elektrik-Elektronik Teknolojisi"))
    rooms["Spor Salonu"] = room_svc.save(Room(name="Spor Salonu", room_type=GYM, capacity=60,
                                              equipment="Spor malzemeleri"))
    rooms["Fen Laboratuvarı"] = room_svc.save(Room(name="Fen Laboratuvarı", room_type="Fen Laboratuvarı",
                                                   capacity=32, equipment="Deney malzemeleri"))

    teachers = {}
    for name, brans, extra in TEACHERS:
        t = Teacher(name=name, brans=brans, max_daily=8, max_weekly=30,
                    subject_ids=[subjects[s].id for s in extra])
        teachers[name] = teacher_svc.save(t)

    for name, grade, (alan, program, dal), room_name, days in CLASSES:
        cur = curricula[(alan, program, dal, str(grade))]
        class_svc.save(SchoolClass(name=name, grade=grade, alan=alan, dal=dal, program_type=program,
                                   curriculum_id=cur.id, home_room_id=rooms[room_name].id, student_count=28,
                                   available_days=days))

    for cls_name, teacher in (("AMP9A", "Burak Yıldız"), ("AMP9B", "Cansu Polat"),
                              ("AMP9C", "Erkan Bulut"), ("AMP9D", "Özlem Çakır")):
        cls = class_svc.get_by_name(cls_name)
        class_svc.set_fixed_teacher(cls.id, subjects["Mesleki Gelişim Atölyesi"].id, teachers[teacher].id)

    periods = int(db.get_setting("periods_per_day"))
    teacher_svc.set_unavailable(teachers["Hüseyin Arslan"].id, [(4, p) for p in range(periods)])
    teacher_svc.set_unavailable(teachers["Mustafa Kılıç"].id, [(0, 0), (0, 1)])
    room_svc.set_unavailable(rooms["Spor Salonu"].id, [(2, periods - 1)])
