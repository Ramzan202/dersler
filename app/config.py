import os
import sys
from pathlib import Path

APP_NAME = "Otomatik Ders Dağılım Programı"
APP_VERSION = "1.0.0"

BASE_DIR = Path(os.environ.get("ODD_BASE_DIR", Path(__file__).resolve().parent.parent))
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
BACKUP_DIR = BASE_DIR / "backups"
DB_PATH = Path(os.environ.get("ODD_DB_PATH", DATA_DIR / "database.db"))

for _d in (DATA_DIR, EXPORT_DIR, BACKUP_DIR):
    _d.mkdir(parents=True, exist_ok=True)

ALL_DAY_NAMES = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
SHORT_DAY_NAMES = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

PROGRAM_TYPES = ["Anadolu Meslek Programı", "Anadolu Teknik Programı"]
ROOM_TYPES = ["Derslik", "Bilgisayar Laboratuvarı", "Atölye", "Fen Laboratuvarı", "Spor Salonu", "Diğer"]
DIFFICULTY_LABELS = {0: "Normal", 1: "Zor", 2: "Çok zor"}
PREFERRED_TIME_LABELS = {"any": "Farketmez", "morning": "Sabah (ilk saatler)", "afternoon": "Öğleden sonra (son saatler)"}

WEIGHT_DEFINITIONS = [
    ("teacher_balance", "Öğretmen yük dengesi (aynı branş)", 8),
    ("teacher_gaps", "Öğretmen boş pencerelerini azalt", 8),
    ("class_gaps", "Sınıf boş saatlerini azalt", 10),
    ("hard_early", "Zor dersler ilk saatlerde", 7),
    ("physical_late", "Beden eğitimi son saatlerde", 5),
    ("preferred_time", "Dersin tercih edilen zamanı", 5),
    ("hard_per_day", "Bir günde çok fazla zor ders olmasın", 6),
    ("class_day_balance", "Sınıfın günlük yük dengesi", 6),
    ("teacher_day_balance", "Öğretmenin günlük yük dengesi", 3),
    ("teacher_consecutive", "Öğretmen için art arda çok ders olmasın", 5),
    ("teacher_preferred_days", "Öğretmenin tercih ettiği günler", 4),
    ("split_preference", "Tercih edilen blok bölünmesi", 6),
]

DEFAULT_SETTINGS = {
    "school_name": "Mesleki ve Teknik Anadolu Lisesi",
    "academic_year": "2026-2027",
    "days_count": 5,
    "periods_per_day": 6,
    "period_times": [
        "08:00-09:00", "09:15-10:15", "10:25-11:25", "11:35-12:35", "12:45-13:15", "13:15-13:50",
    ],
    "solver_time_limit": 90,
    "solver_workers": 8,
    "hard_per_day_limit": 4,
    "weights": {key: default for key, _, default in WEIGHT_DEFINITIONS},
    "ui_scaling": 1.0,
    "appearance": "light",
    "auto_backup": True,
    "last_run": None,
}

SUBJECT_PALETTE = [
    "#F8B4B4", "#FCD9A8", "#FDF2A2", "#C7EBC0", "#A8E0E0", "#B4CFF8", "#D2C1F5", "#F5C1E4",
    "#E3D5C3", "#C9E4A6", "#A6D8F0", "#F0B7A6", "#D9D9F3", "#BFE6D0", "#F3E0B5", "#E6B8C9",
]


def resource_path(*parts: str) -> Path:
    base = getattr(sys, "_MEIPASS", BASE_DIR)
    return Path(base, *parts)
