import customtkinter as ctk

from app import config
from app.database.database import Database
from app.ui.classes import ClassesPage
from app.ui.dashboard import DashboardPage
from app.ui.reports import ReportsPage
from app.ui.rooms import RoomsPage
from app.ui.settings import SettingsPage
from app.ui.subjects import CurriculaPage, SubjectsPage
from app.ui.teachers import TeachersPage
from app.ui.timetable import TimetablePage
from app.ui.widgets import configure_treeview_style, show_error

PAGES = [
    ("dashboard", "🏠  Ana Panel", DashboardPage),
    ("classes", "🏫  Sınıflar", ClassesPage),
    ("teachers", "👩‍🏫  Öğretmenler", TeachersPage),
    ("rooms", "🚪  Derslikler", RoomsPage),
    ("subjects", "📘  Dersler", SubjectsPage),
    ("curricula", "📋  Öğretim Planları", CurriculaPage),
    ("timetable", "🗓  Ders Programı", TimetablePage),
    ("reports", "📊  Raporlar", ReportsPage),
    ("settings", "⚙  Ayarlar", SettingsPage),
]


class MainWindow(ctk.CTk):
    def __init__(self, db: Database):
        self.db = db
        self.reload_settings()
        ctk.set_appearance_mode(self.settings["appearance"])
        ctk.set_default_color_theme("blue")
        ctk.set_widget_scaling(self.scaling)
        super().__init__()
        self.title(f"{config.APP_NAME} – {self.settings['school_name']}")
        self.geometry("1400x860")
        self.minsize(1100, 680)
        try:
            self.state("zoomed")
        except Exception:  # noqa: BLE001
            pass
        configure_treeview_style(self, self.scaling, ctk.get_appearance_mode() == "Dark")
        self.report_callback_exception = self._on_error

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        side = ctk.CTkFrame(self, width=220, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        ctk.CTkLabel(side, text="Otomatik\nDers Dağılımı", font=ctk.CTkFont(size=20, weight="bold"),
                     justify="left").pack(anchor="w", padx=16, pady=(20, 4))
        ctk.CTkLabel(side, text=f"MTAL · v{config.APP_VERSION}", text_color="gray").pack(anchor="w", padx=16,
                                                                                         pady=(0, 16))
        self.nav = {}
        for key, label, _ in PAGES:
            b = ctk.CTkButton(side, text=label, anchor="w", fg_color="transparent", text_color=("gray10", "gray90"),
                              hover_color=("gray75", "gray25"), height=38, command=lambda k=key: self.show_page(k))
            b.pack(fill="x", padx=8, pady=2)
            self.nav[key] = b

        ctk.CTkLabel(side, text="Yazar: Ramzan 25053 10 A", text_color="gray",
                     font=ctk.CTkFont(size=11)).pack(side="bottom", anchor="w", padx=16, pady=12)

        self.container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.container.grid(row=0, column=1, sticky="nsew")
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(self, text="Hazır", anchor="w", text_color="gray")
        self.status.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 4))

        self.pages = {}
        for key, _, cls in PAGES:
            page = cls(self.container, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page
        self.current = None
        self.dirty = set()
        self.show_page("dashboard")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ settings helpers
    def reload_settings(self):
        self.settings = self.db.all_settings()
        self.scaling = float(self.settings.get("ui_scaling", 1.0))
        self.day_names = config.ALL_DAY_NAMES[:int(self.settings["days_count"])]
        self.periods = int(self.settings["periods_per_day"])
        self.period_times = list(self.settings.get("period_times", []))[:self.periods]

    def apply_appearance(self):
        self.reload_settings()
        ctk.set_appearance_mode(self.settings["appearance"])
        ctk.set_widget_scaling(self.scaling)
        configure_treeview_style(self, self.scaling, ctk.get_appearance_mode() == "Dark")
        self.title(f"{config.APP_NAME} – {self.settings['school_name']}")

    # ------------------------------------------------------------------ navigation
    def show_page(self, key: str, run: bool = False):
        page = self.pages[key]
        for k, b in self.nav.items():
            b.configure(fg_color=("gray75", "gray25") if k == key else "transparent")
        getattr(page, "_parent_frame", page).tkraise()
        self.current = key
        if hasattr(page, "refresh"):
            try:
                page.refresh()
            except Exception as exc:  # noqa: BLE001
                self._on_error(type(exc), exc, exc.__traceback__)
        self.dirty.discard(key)
        if run and key == "timetable":
            self.after(100, page.run_solver)

    def data_changed(self, rebuild_only: bool = False):
        """Mark every page as stale and refresh the visible one (all edits are saved to SQLite immediately)."""
        self.reload_settings()
        self.dirty = set(self.pages)
        if self.current:
            self.show_page(self.current)
        self.set_status("Değişiklikler kaydedildi.")

    def set_status(self, text: str):
        self.status.configure(text=text)

    def _on_error(self, exc_type, exc, tb):
        import traceback
        from datetime import datetime
        traceback.print_exception(exc_type, exc, tb)
        try:
            with open(config.DATA_DIR / "hata_kaydi.log", "a", encoding="utf-8") as fh:
                fh.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n"
                         + "".join(traceback.format_exception(exc_type, exc, tb)))
        except OSError:
            pass
        show_error(self, f"Beklenmeyen bir hata oluştu:\n{exc}\n\nVerileriniz kaydedildi.")

    def on_close(self):
        try:
            self.db.close()
        finally:
            self.destroy()
