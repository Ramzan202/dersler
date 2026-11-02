import customtkinter as ctk

from app.config import PROGRAM_TYPES
from app.database.models import SchoolClass, format_int_list, parse_int_list
from app.services.class_service import ClassService
from app.services.room_service import RoomService
from app.services.subject_service import CurriculumService, SubjectService
from app.services.teacher_service import TeacherService
from app.ui.widgets import (AvailabilityDialog, DataTable, EntityPage, FormDialog, ask_yes_no, guarded, show_info)


class ClassesPage(EntityPage):
    title = "Sınıflar"
    columns = [("name", "Sınıf", 90), ("grade", "Düzey", 55), ("alan", "Alan", 180), ("dal", "Dal", 140),
               ("program", "Program", 170), ("plan", "Öğretim Planı", 220), ("room", "Derslik", 80),
               ("days", "Okul Günleri", 170), ("hours", "Haftalık Saat", 90)]

    def __init__(self, master, app):
        self.svc = ClassService(app.db)
        super().__init__(master, app)

    def build_toolbar(self):
        super().build_toolbar()
        self.tool("🗓 Müsaitlik", self.on_availability, "#6A1B9A")
        self.tool("📚 Dersleri", self.on_lessons, "#00695C")

    def load_rows(self):
        plans = {c.id: c.name for c in CurriculumService(self.app.db).list()}
        rooms = {r.id: r.name for r in RoomService(self.app.db).list()}
        days = self.app.day_names
        rows = []
        for c in self.svc.list():
            day_text = ", ".join(days[d][:3] for d in c.day_list if d < len(days))
            if len([d for d in c.day_list if d < len(days)]) < len(days):
                day_text += "  (işletmede eğitim)"
            rows.append((c.id, (c.name, c.grade, c.alan, c.dal, c.program_type, plans.get(c.curriculum_id, "—"),
                                rooms.get(c.home_room_id, "—"), day_text, self.svc.total_hours(c.id))))
        return rows

    def _form(self, c: SchoolClass, title: str):
        plans = [(p.id, p.name) for p in CurriculumService(self.app.db).list()]
        rooms = [(r.id, f"{r.name} ({r.room_type})") for r in RoomService(self.app.db).list()]
        fields = [
            dict(key="name", label="Sınıf adı", value=c.name, help="Örn. AMP9A"),
            dict(key="grade", label="Sınıf düzeyi", kind="combo", options=[9, 10, 11, 12], value=c.grade),
            dict(key="alan", label="Alan", kind="combo", options=self.svc.alans(), value=c.alan, editable=True),
            dict(key="dal", label="Dal", value=c.dal),
            dict(key="program_type", label="Program", kind="combo", options=PROGRAM_TYPES, value=c.program_type),
            dict(key="curriculum_id", label="Öğretim planı", kind="combo_id", options=plans, value=c.curriculum_id),
            dict(key="home_room_id", label="Sınıf dersliği", kind="combo_id", options=rooms, value=c.home_room_id),
            dict(key="available_days", label="Okul günleri", kind="days", days=self.app.day_names,
                 value=c.day_list, help="İşletmede eğitim günleri işaretlenmez."),
            dict(key="student_count", label="Öğrenci sayısı", kind="int", value=c.student_count),
            dict(key="weekly_hours", label="Haftalık ders saati (kontrol)", kind="int", value=c.weekly_hours,
                 help="0 = plandan hesaplanır"),
            dict(key="max_daily", label="Günlük en fazla ders", kind="int", value=c.max_daily,
                 help="0 = okulun günlük ders saati"),
            dict(key="notes", label="Notlar", kind="textarea", value=c.notes),
        ]
        vals = FormDialog(self, title, fields).show()
        if vals is None:
            return None
        vals["grade"] = int(vals["grade"])
        vals["available_days"] = format_int_list(vals["available_days"])
        for k, v in vals.items():
            setattr(c, k, v)
        return self.svc.save(c)

    def on_add(self):
        days = list(range(len(self.app.day_names)))
        if self._form(SchoolClass(available_days=format_int_list(days)), "Yeni sınıf"):
            self.app.data_changed()

    def on_edit(self):
        ident = self.require_selection()
        if ident and self._form(self.svc.get(ident), "Sınıfı düzenle"):
            self.app.data_changed()

    def on_delete(self):
        ids = self.table.selected_ids()
        if not ids:
            return show_info(self, "Lütfen silinecek sınıfı seçin.")
        if ask_yes_no(self, f"{len(ids)} sınıf silinecek. Programlardaki dersleri de silinir. Emin misiniz?"):
            for i in ids:
                self.svc.delete(i)
            self.app.data_changed()

    def on_availability(self):
        ident = self.require_selection()
        if not ident:
            return
        c = self.svc.get(ident)
        n_days, periods = len(self.app.day_names), self.app.periods
        blocked = set(self.svc.get_unavailable(ident))
        for d in range(n_days):
            if d not in c.day_list:
                blocked |= {(d, p) for p in range(periods)}
        result = AvailabilityDialog(self, f"{c.name} – okul günleri ve saatleri", self.app.day_names, periods,
                                    blocked, self.app.period_times,
                                    note="Tüm günü kapalı olan günler okul günü sayılmaz (işletmede eğitim). "
                                         "Kısmen kapalı saatlerde de ders konmaz.").show()
        if result is None:
            return
        full_days = {d for d in range(n_days) if all((d, p) in result for p in range(periods))}
        c.available_days = format_int_list([d for d in range(n_days) if d not in full_days]
                                           + [d for d in c.day_list if d >= n_days])
        if not parse_int_list(c.available_days):
            raise ValueError("Sınıfın en az bir okul günü olmalıdır.")
        self.svc.save(c)
        self.svc.set_unavailable(ident, {(d, p) for d, p in result if d not in full_days})
        self.app.data_changed()

    def on_lessons(self):
        ident = self.require_selection()
        if ident:
            ClassLessonsDialog(self, self.app, ident)
            self.app.data_changed()


class ClassLessonsDialog(ctk.CTkToplevel):
    def __init__(self, master, app, class_id: int):
        super().__init__(master)
        self.app, self.class_id = app, class_id
        self.svc = ClassService(app.db)
        cls = self.svc.get(class_id)
        self.title(f"{cls.name} – dersleri")
        self.geometry("820x520")
        ctk.CTkLabel(self, text=f"{cls.name} sınıfının haftalık dersleri",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=12, pady=(12, 0))
        ctk.CTkLabel(self, text="Dersler öğretim planından gelir. Bu sınıfa özel ek ders (seçmeli/mesleki) "
                                "ekleyebilir, saat değiştirebilir veya dersi sabit bir öğretmene atayabilirsiniz.",
                     text_color="gray", wraplength=780, justify="left").pack(anchor="w", padx=12)
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=8)
        g = guarded(self)
        ctk.CTkButton(bar, text="➕ Ek ders / saat değiştir", command=g(self.on_extra)).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="👤 Sabit öğretmen", command=g(self.on_teacher)).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="↩ Plana döndür", command=g(self.on_reset), fg_color="gray").pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Kapat", command=self.destroy).pack(side="right", padx=4)
        self.total = ctk.CTkLabel(self, text="")
        self.total.pack(anchor="w", padx=12)
        self.table = DataTable(self, [("subject", "Ders", 330), ("hours", "Saat", 60), ("source", "Kaynak", 110),
                                      ("teacher", "Sabit öğretmen", 200)], selectmode="browse")
        self.table.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.refresh()
        self.transient(master)
        self.after(150, lambda: (self.lift(), self.grab_set()))
        self.wait_window()

    def refresh(self):
        subjects = {s.id: s.name for s in SubjectService(self.app.db).list()}
        teachers = {t.id: t.name for t in TeacherService(self.app.db).list()}
        lessons = self.svc.lessons(self.class_id)
        self.table.set_rows([(l.subject_id, (subjects.get(l.subject_id, "?"), l.hours,
                                             "Plan" if l.source == "plan" else "Sınıfa özel",
                                             teachers.get(l.fixed_teacher_id, "—"))) for l in lessons])
        self.total.configure(text=f"Toplam: {sum(l.hours for l in lessons)} saat / hafta")

    def on_extra(self):
        subjects = [(s.id, s.name) for s in SubjectService(self.app.db).list()]
        sel = self.table.selected_id()
        current = {l.subject_id: l.hours for l in self.svc.lessons(self.class_id)}
        vals = FormDialog(self, "Ek ders / saat", [
            dict(key="subject_id", label="Ders", kind="combo_id", options=subjects, value=sel, allow_none=False),
            dict(key="hours", label="Haftalık saat", kind="int", value=current.get(sel, 2),
                 help="0 girilirse ders bu sınıfın programından çıkarılır."),
        ], height=260).show()
        if vals:
            if vals["hours"] < 0:
                raise ValueError("Saat negatif olamaz.")
            self.svc.set_extra_lesson(self.class_id, vals["subject_id"], vals["hours"])
            self.refresh()

    def on_teacher(self):
        sel = self.table.selected_id()
        if sel is None:
            return show_info(self, "Önce bir ders seçin.")
        teachers = [(t.id, f"{t.name} ({t.brans})") for t in TeacherService(self.app.db).list()]
        current = self.svc.fixed_teachers(self.class_id).get(sel)
        vals = FormDialog(self, "Sabit öğretmen", [
            dict(key="teacher_id", label="Öğretmen", kind="combo_id", options=teachers, value=current,
                 help="Boş bırakılırsa öğretmen otomatik seçilir."),
        ], height=220).show()
        if vals is not None:
            self.svc.set_fixed_teacher(self.class_id, sel, vals["teacher_id"])
            self.refresh()

    def on_reset(self):
        sel = self.table.selected_id()
        if sel is None:
            return show_info(self, "Önce bir ders seçin.")
        self.svc.set_extra_lesson(self.class_id, sel, None)
        self.svc.set_fixed_teacher(self.class_id, sel, None)
        self.refresh()
