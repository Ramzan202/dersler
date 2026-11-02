import customtkinter as ctk

from app.core.problem import build_problem
from app.core.validator import validate
from app.services.class_service import ClassService
from app.services.room_service import RoomService
from app.services.subject_service import CurriculumService, SubjectService
from app.services.teacher_service import TeacherService
from app.services.timetable_service import TimetableService
from app.ui.widgets import DataTable, guarded


class DashboardPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.title = ctk.CTkLabel(self, text="Ana Panel", font=ctk.CTkFont(size=22, weight="bold"))
        self.title.pack(anchor="w", padx=16, pady=(16, 0))
        self.subtitle = ctk.CTkLabel(self, text="", text_color="gray")
        self.subtitle.pack(anchor="w", padx=16)
        self.cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.cards_frame.pack(fill="x", padx=12, pady=10)
        self.cards = {}
        for i, (key, label, color) in enumerate((
                ("classes", "Sınıf", "#1565C0"), ("teachers", "Öğretmen", "#2E7D32"), ("rooms", "Derslik", "#6A1B9A"),
                ("subjects", "Ders", "#EF6C00"), ("plans", "Öğretim Planı", "#00838F"),
                ("load", "Haftalık Toplam Ders Saati", "#AD1457"))):
            card = ctk.CTkFrame(self.cards_frame, fg_color=color, corner_radius=10)
            card.grid(row=0, column=i, padx=4, sticky="nsew")
            self.cards_frame.grid_columnconfigure(i, weight=1)
            value = ctk.CTkLabel(card, text="0", font=ctk.CTkFont(size=28, weight="bold"), text_color="white")
            value.pack(padx=12, pady=(10, 0))
            ctk.CTkLabel(card, text=label, text_color="white").pack(padx=12, pady=(0, 10))
            self.cards[key] = value

        status = ctk.CTkFrame(self)
        status.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(status, text="Son dağıtım:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10,
                                                                                         pady=8, sticky="w")
        self.last_run = ctk.CTkLabel(status, text="—", anchor="w", justify="left", wraplength=900)
        self.last_run.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(status, text="Etkin program:", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, padx=10,
                                                                                           pady=(0, 8), sticky="w")
        self.active = ctk.CTkLabel(status, text="—", anchor="w")
        self.active.grid(row=1, column=1, sticky="w")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=4)
        g = guarded(self)
        ctk.CTkButton(actions, text="▶ Otomatik Ders Dağılımı", fg_color="#2E7D32", height=36,
                      command=g(lambda: app.show_page("timetable", run=True))).pack(side="left")
        ctk.CTkButton(actions, text="↻ Verileri kontrol et", command=g(self.refresh)).pack(side="left", padx=8)

        self.issue_title = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=15, weight="bold"), anchor="w")
        self.issue_title.pack(fill="x", padx=16, pady=(10, 2))
        self.issues = DataTable(self, [("level", "Düzey", 80), ("cat", "Bölüm", 110), ("msg", "Açıklama", 900)])
        self.issues.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    def refresh(self):
        db = self.app.db
        s = self.app.settings
        self.subtitle.configure(text=f"{s['school_name']} · {s['academic_year']} · {len(self.app.day_names)} gün × "
                                     f"{self.app.periods} ders saati")
        class_svc = ClassService(db)
        classes = class_svc.list()
        self.cards["classes"].configure(text=str(len(classes)))
        self.cards["teachers"].configure(text=str(TeacherService(db).count()))
        self.cards["rooms"].configure(text=str(RoomService(db).count()))
        self.cards["subjects"].configure(text=str(SubjectService(db).count()))
        self.cards["plans"].configure(text=str(CurriculumService(db).count()))
        self.cards["load"].configure(text=str(sum(class_svc.total_hours(c.id) for c in classes)))
        last = db.get_setting("last_run")
        if last:
            text = f"{last.get('time', '')} – {last.get('text', '')}"
            if last.get("details"):
                text += "\n" + "\n".join("• " + d for d in last["details"][:5])
            color = "#2E7D32" if last.get("status") in ("optimal", "feasible", "cancelled") else "#C62828"
            self.last_run.configure(text=text, text_color=color)
        else:
            self.last_run.configure(text="Henüz otomatik dağıtım yapılmadı.", text_color=("black", "white"))
        active = TimetableService(db).active()
        self.active.configure(text=f"{active.name} ({active.created_at}, {active.source})" if active else "—")
        problem = build_problem(db)
        issues = validate(db, problem)
        errors = sum(1 for i in issues if i.is_error)
        warnings = len(issues) - errors
        if not issues:
            self.issue_title.configure(text="✔ Veriler dağıtıma hazır, sorun bulunmadı.", text_color="#2E7D32")
        else:
            self.issue_title.configure(text=f"Uyarılar ve sorunlar: {errors} hata, {warnings} uyarı",
                                       text_color="#C62828" if errors else "#EF6C00")
        self.issues.set_rows([(i, ("Hata" if x.is_error else "Uyarı", x.category, x.message),
                               "error" if x.is_error else "warning") for i, x in enumerate(issues)])
