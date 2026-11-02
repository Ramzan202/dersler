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
    columns = [("name", "Sınıf", 90), ("parent", "Ana Sınıf", 80), ("grade", "Düzey", 55), ("alan", "Alan", 180), ("dal", "Dal", 140),
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
        all_classes = self.svc.list()
        for c in all_classes:
            day_text = ", ".join(days[d][:3] for d in c.day_list if d < len(days))
            if len([d for d in c.day_list if d < len(days)]) < len(days):
                day_text += "  (işletmede eğitim)"
            parent = next((x.name for x in all_classes if x.id == c.parent_id), "")
            rows.append((c.id, (c.name, parent, c.grade, c.alan, c.dal, c.program_type, plans.get(c.curriculum_id, "—"),
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
            dict(key="parent_id", label="Grubu olduğu sınıf", kind="combo_id",
                 options=[(x.id, x.name) for x in self.svc.list() if x.id != c.id and x.parent_id is None],
                 value=c.parent_id, help="Şube grubu ise (ör. ATP10A-1 → ATP10A). Grup dersi sırasında ana "
                                         "sınıfın başka dersi olamaz."),
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


ROOM_MODES = {"any": "Birini seç (her blokta biri)", "all": "Hepsi aynı anda (gruplar)"}


class ClassLessonsDialog(ctk.CTkToplevel):
    """All per-class lesson settings: hours, teacher team, rooms, room usage, combined lesson code, split."""

    def __init__(self, master, app, class_id: int):
        super().__init__(master)
        self.app, self.class_id = app, class_id
        self.svc = ClassService(app.db)
        cls = self.svc.get(class_id)
        self.title(f"{cls.name} – dersleri")
        self.geometry("1180x600")
        ctk.CTkLabel(self, text=f"{cls.name} sınıfının haftalık dersleri",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=12, pady=(12, 0))
        ctk.CTkLabel(self, text="Bir derse çift tıklayın veya 'Düzenle' ile saat, öğretmen ekibi, derslikler, "
                                "birleştirme kodu ve bölünme kuralını değiştirin. Öğretmen seçilmezse program uygun "
                                "öğretmeni kendisi seçer.",
                     text_color="gray", wraplength=1100, justify="left").pack(anchor="w", padx=12)
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=8)
        g = guarded(self)
        ctk.CTkButton(bar, text="✏️ Düzenle", command=g(self.on_edit)).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="➕ Ek ders", command=g(self.on_extra)).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="↩ Plana döndür", command=g(self.on_reset), fg_color="gray").pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Kapat", command=self.destroy).pack(side="right", padx=4)
        self.total = ctk.CTkLabel(self, text="")
        self.total.pack(anchor="w", padx=12)
        self.table = DataTable(self, [("subject", "Ders", 260), ("hours", "Saat", 45), ("source", "Kaynak", 80),
                                      ("teacher", "Öğretmen(ler)", 260), ("rooms", "Derslik(ler)", 160),
                                      ("mode", "Derslik kullanımı", 150), ("link", "Birleştirme", 85),
                                      ("split", "Bölünme", 90)], selectmode="browse")
        self.table.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.table.bind_double_click(g(self.on_edit))
        self.refresh()
        self.transient(master)
        self.after(150, lambda: (self.lift(), self.grab_set()))
        self.wait_window()

    def refresh(self):
        subjects = {s.id: s.name for s in SubjectService(self.app.db).list()}
        teachers = {t.id: t.name for t in TeacherService(self.app.db).list()}
        rooms = {r.id: r.name for r in RoomService(self.app.db).list()}
        lessons = self.svc.lessons(self.class_id)
        rows = []
        for l in lessons:
            team = ", ".join(teachers.get(t, "?") for t in l.team) or "otomatik"
            rows.append((l.subject_id, (subjects.get(l.subject_id, "?"), l.hours,
                                        "Plan" if l.source == "plan" else "Sınıfa özel", team,
                                        ", ".join(rooms.get(r, "?") for r in l.rooms) or "otomatik",
                                        ROOM_MODES.get(l.room_mode, l.room_mode) if l.rooms else "—",
                                        l.link or "—", l.split or "otomatik")))
        self.table.set_rows(rows)
        self.total.configure(text=f"Toplam: {sum(l.hours for l in lessons)} saat / hafta")

    def on_edit(self):
        sel = self.table.selected_id()
        if sel is None:
            return show_info(self, "Önce bir ders seçin.")
        lesson = next(l for l in self.svc.lessons(self.class_id) if l.subject_id == sel)
        subject = SubjectService(self.app.db).get(sel)
        teachers = [(t.id, f"{t.name} ({t.brans})") for t in TeacherService(self.app.db).list()]
        rooms = [(r.id, f"{r.name} ({r.room_type})") for r in RoomService(self.app.db).list()]
        vals = FormDialog(self, f"{subject.name} – ayarlar", [
            dict(key="hours", label="Haftalık saat", kind="int", value=lesson.hours,
                 help="0 = bu sınıfın programından çıkar"),
            dict(key="teachers", label="Öğretmen(ler)", kind="multi", options=teachers, value=lesson.team,
                 help="Birden fazla seçilirse hepsi bu derse aynı anda girer (ekip). Boş = otomatik seçim."),
            dict(key="rooms", label="Derslik(ler)", kind="multi", options=rooms, value=lesson.rooms, height=120,
                 help="Boş = dersin ve sınıfın ayarlarına göre otomatik."),
            dict(key="room_mode", label="Derslik kullanımı", kind="combo", options=list(ROOM_MODES.values()),
                 value=ROOM_MODES.get(lesson.room_mode, ROOM_MODES["any"])),
            dict(key="link", label="Birleştirme kodu", value=lesson.link,
                 help="Aynı kodu taşıyan sınıfların/grupların bu dersi birlikte, aynı saatte ve aynı öğretmenle "
                      "yapılır (ör. B1)."),
            dict(key="split", label="Bölünme (bu sınıf)", value=lesson.split,
                 help="Ör. 2+2+1. Boş = dersin genel kuralı."),
        ], width=820, height=700).show()
        if vals is None:
            return
        from app.core.splits import parse_pattern
        if vals["split"]:
            pat = parse_pattern(vals["split"])
            if sum(pat) != (vals["hours"] or lesson.hours):
                raise ValueError(f"Bölünmenin toplamı ({sum(pat)}) haftalık saate ({vals['hours']}) eşit olmalı.")
        if vals["hours"] < 0:
            raise ValueError("Saat negatif olamaz.")
        if vals["hours"] != lesson.hours:
            self.svc.set_extra_lesson(self.class_id, sel, vals["hours"])
        mode = next(k for k, v in ROOM_MODES.items() if v == vals["room_mode"])
        self.svc.set_lesson_settings(self.class_id, sel, teachers=vals["teachers"], rooms=vals["rooms"],
                                     room_mode=mode, link=vals["link"].strip(), split=vals["split"].strip())
        self.svc.set_fixed_teacher(self.class_id, sel, None)
        self.refresh()

    def on_extra(self):
        subjects = [(s.id, s.name) for s in SubjectService(self.app.db).list()]
        vals = FormDialog(self, "Ek ders", [
            dict(key="subject_id", label="Ders", kind="combo_id", options=subjects, allow_none=False),
            dict(key="hours", label="Haftalık saat", kind="int", value=2),
        ], height=240).show()
        if vals:
            if vals["hours"] < 0:
                raise ValueError("Saat negatif olamaz.")
            self.svc.set_extra_lesson(self.class_id, vals["subject_id"], vals["hours"])
            self.refresh()

    def on_reset(self):
        sel = self.table.selected_id()
        if sel is None:
            return show_info(self, "Önce bir ders seçin.")
        self.svc.set_extra_lesson(self.class_id, sel, None)
        self.svc.set_fixed_teacher(self.class_id, sel, None)
        self.svc.clear_lesson_settings(self.class_id, sel)
        self.refresh()
