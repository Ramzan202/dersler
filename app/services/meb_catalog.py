"""MEB framework curricula (Çerçeve Öğretim Programları, haftalık ders çizelgeleri) for MTAL.

The data were extracted from the official PDFs listed at
https://meslek.meb.gov.tr/cercevelistele.aspx?sinif_kodu=9&kurum_id=1 (see scripts/meb/).
'İşletmelerde Mesleki Eğitim' hours are done at enterprises, so they are stored separately and not scheduled.
"""
import json
from dataclasses import dataclass
from functools import lru_cache

from app import config
from app.database.database import Database
from app.database.models import Curriculum, Subject
from app.services.subject_service import CurriculumService, SubjectService

DATA_FILE = config.resource_path("app", "data", "meb_cerceve_2026.json")

COMMON_BRANS = {
    "Türk Dili ve Edebiyatı": "Türk Dili ve Edebiyatı",
    "Din Kültürü ve Ahlak Bilgisi": "Din Kültürü",
    "Tarih": "Tarih",
    "T.C. İnkılap Tarihi ve Atatürkçülük": "Tarih",
    "Coğrafya": "Coğrafya",
    "Matematik": "Matematik",
    "Fizik": "Fizik",
    "Kimya": "Kimya",
    "Biyoloji": "Biyoloji",
    "Felsefe": "Felsefe",
    "Yabancı Dil": "İngilizce",
    "Beden Eğitimi ve Spor / Görsel Sanatlar / Müzik": "Beden Eğitimi",
    "Sağlık Bilgisi ve Trafik Kültürü": "Biyoloji",
    "Rehberlik ve Yönlendirme": "Rehberlik",
}
DIFFICULTY = {"Matematik": 2, "Fizik": 1, "Kimya": 1}
PROGRAM_SHORT = {"Anadolu Meslek Programı": "AMP", "Anadolu Teknik Programı": "ATP"}


@dataclass
class MebPlan:
    alan: str
    dal: str
    program: str
    variant: str
    pdf: str
    grades: dict[str, list[list]]
    ime: dict[str, int]
    skipped_grades: list[str]

    @property
    def program_label(self) -> str:
        return self.program + (f" – {self.variant}" if self.variant else "")

    def hours(self, grade: str) -> int:
        return sum(h for _, h in self.grades.get(grade, []))


@lru_cache(maxsize=1)
def load_catalog() -> tuple[list[MebPlan], dict[str, str], dict]:
    with open(DATA_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    plans = [MebPlan(p["alan"], p["dal"], p["program"], p["variant"], p["pdf"], p["grades"], p["ime"],
                     p.get("skipped_grades", [])) for p in data["plans"]]
    meta = {k: data[k] for k in ("source", "title", "retrieved")}
    return plans, data["subject_kinds"], meta


def alans() -> list[str]:
    return sorted({p.alan for p in load_catalog()[0]}, key=lambda s: s.replace("İ", "I").replace("Ç", "C~"))


def programs(alan: str) -> list[str]:
    return sorted({p.program_label for p in load_catalog()[0] if p.alan == alan})


def dals(alan: str, program_label: str) -> list[str]:
    return sorted({p.dal for p in load_catalog()[0] if p.alan == alan and p.program_label == program_label})


def find(alan: str, program_label: str, dal: str) -> MebPlan | None:
    return next((p for p in load_catalog()[0]
                 if p.alan == alan and p.program_label == program_label and p.dal == dal), None)


def subject_defaults(name: str, kind: str, alan: str) -> Subject:
    s = Subject(name=name, default_hours=2)
    if name in COMMON_BRANS:
        s.brans = COMMON_BRANS[name]
    elif kind in ("meslek", "secmeli_meslek") or name == "Mesleki Gelişim Atölyesi":
        s.brans = alan
    s.difficulty = DIFFICULTY.get(name, 0)
    if name.startswith("Beden Eğitimi"):
        s.physical = 1
        s.room_type = "Spor Salonu"
    if kind in ("meslek", "secmeli_meslek") or name == "Mesleki Gelişim Atölyesi":
        s.vocational = 1
        s.min_block, s.max_block = 2, 4
        s.alan = alan
    if kind in ("secmeli", "secmeli_meslek"):
        s.elective = 1
    return s


def curriculum_name(plan: MebPlan, grade: str) -> str:
    prog = PROGRAM_SHORT.get(plan.program, plan.program)
    if plan.variant:
        prog += f", {plan.variant}"
    dal = plan.dal or "Alan ortak"
    return f"{grade}. Sınıf {plan.alan} – {dal} ({prog})"


def import_plan(db: Database, plan: MebPlan, grades: list[str]) -> list[Curriculum]:
    """Create or update curricula (and missing subjects) for the chosen grades. Existing subjects keep their
    settings; an existing curriculum with the same name gets exactly the MEB hours."""
    _, kinds, meta = load_catalog()
    subj_svc, cur_svc = SubjectService(db), CurriculumService(db)
    created = []
    for grade in grades:
        items = plan.grades.get(grade)
        if not items:
            continue
        name = curriculum_name(plan, grade)
        ime = plan.ime.get(grade)
        notes = f"MEB {meta['title']}. Kaynak: {plan.pdf}"
        if ime:
            notes += f"\nİşletmelerde Mesleki Eğitim: haftada {ime} saat (işletmede; okul programına dahil değildir)."
        cur = cur_svc.get_by_name(name) or Curriculum(name=name)
        cur.grade, cur.alan, cur.dal, cur.program_type, cur.notes = int(grade), plan.alan, plan.dal, plan.program, notes
        cur_svc.save(cur)
        wanted = {}
        for subj_name, hours in items:
            subject = subj_svc.get_by_name(subj_name)
            if subject is None:
                subject = subject_defaults(subj_name, kinds.get(subj_name, "meslek"), plan.alan)
                subject.default_hours = hours
                subj_svc.save(subject)
            wanted[subject.id] = hours
        for item in cur_svc.items(cur.id):
            if item.subject_id not in wanted:
                cur_svc.remove_item(cur.id, item.subject_id)
        for sid, hours in wanted.items():
            cur_svc.set_item(cur.id, sid, hours)
        created.append(cur)
    return created
