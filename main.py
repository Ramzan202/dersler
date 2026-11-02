import sys
import traceback


def _log_error(text: str):
    try:
        from datetime import datetime

        from app import config
        with open(config.DATA_DIR / "hata_kaydi.log", "a", encoding="utf-8") as fh:
            fh.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{text}\n")
    except Exception:  # noqa: BLE001
        pass


def main():
    try:
        from app import config
        from app.database.database import Database
        from app.database.seed import load_demo_data
        from app.utils.backup import auto_backup
    except ImportError as exc:
        print(f"Gerekli kütüphane yüklenemedi: {exc}\nrun.bat dosyasını yeniden çalıştırın.")
        sys.exit(2)

    db = Database(config.DB_PATH)
    if db.is_empty() and db.get_setting("demo_loaded", False) is False:
        load_demo_data(db)
        db.set_setting("demo_loaded", True)
    if db.get_setting("auto_backup", True):
        try:
            auto_backup(db)
        except Exception:  # noqa: BLE001
            traceback.print_exc()

    from app.ui.main_window import MainWindow
    window = MainWindow(db)
    window.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        _log_error(traceback.format_exc())
        try:
            from tkinter import Tk, messagebox
            root = Tk()
            root.withdraw()
            messagebox.showerror("Otomatik Ders Dağılım Programı", f"Program başlatılamadı:\n{exc}")
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)
