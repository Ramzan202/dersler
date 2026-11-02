from datetime import datetime
from pathlib import Path

from app import config
from app.database.database import Database

KEEP_AUTO_BACKUPS = 20


def create_backup(db: Database, label: str = "manuel", directory: Path | None = None) -> Path:
    directory = Path(directory or config.BACKUP_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)
    path = directory / f"yedek_{stamp}_{safe}.db"
    n = 1
    while path.exists():
        path = directory / f"yedek_{stamp}_{safe}_{n}.db"
        n += 1
    db.backup_to(path)
    return path


def list_backups(directory: Path | None = None) -> list[Path]:
    directory = Path(directory or config.BACKUP_DIR)
    if not directory.exists():
        return []
    return sorted(directory.glob("yedek_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)


def restore_backup(db: Database, path: Path | str, directory: Path | None = None) -> Path:
    safety = create_backup(db, "geri_yukleme_oncesi", directory)
    db.restore_from(path)
    return safety


def auto_backup(db: Database, directory: Path | None = None) -> Path | None:
    if db.is_empty():
        return None
    today = datetime.now().strftime("%Y%m%d")
    existing = [p for p in list_backups(directory) if p.name.startswith(f"yedek_{today}") and "otomatik" in p.name]
    if existing:
        return None
    path = create_backup(db, "otomatik", directory)
    autos = [p for p in list_backups(directory) if "otomatik" in p.name]
    for old in autos[KEEP_AUTO_BACKUPS:]:
        try:
            old.unlink()
        except OSError:
            pass
    return path
