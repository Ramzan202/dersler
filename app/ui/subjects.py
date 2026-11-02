import customtkinter as ctk

from app.config import DIFFICULTY_LABELS, PREFERRED_TIME_LABELS, PROGRAM_TYPES
from app.database.models import Curriculum, Subject
from app.services.room_service import RoomService
from app.services.subject_service import CurriculumService, SubjectService
from app.services.teacher_service import TeacherService
from app.ui.widgets import DataTable, EntityPage, FormDialog, ask_yes_no, guarded, show_info

TIME_BY_LABEL = {v: k for k, v in PREFERRED_TIME_LABELS.items()}
DIFF_BY_LABEL = {v: k for k, v in DIFFICULTY_LABELS.items()}


class SubjectsPage(EntityPage):
    title = "Dersler"
    columns = [("name", "Ders", 260), ("short", "Kısa", 55), ("hours", "Saat", 45), ("brans", "Branş", 130),
               ("diff", "Zorluk", 70), ("time", "Tercih Zamanı", 120), ("room", "Derslik", 170),
               ("split", "Blok / Bölünme", 170), ("teachers", "Öğretmen", 70), ("kind", "Tür", 110)]

    def __init__(self, master, app):
        self.svc = SubjectService(app.db)
        super().__init__(master, app)

    def load_rows(self):
        teachers = TeacherService(self.app.db).list()
        rows = []
        for s in self.svc.list():
            n_teachers = sum(1 for t in teachers if s.id in t.subject_ids or
                             (s.brans and t.brans and s.brans.lower() == t.brans.lower()))
            split = f"{s.min_block}–{s.max_block} saat"
            if s.allowed_splits:
                split += f"; {s.allowed_splits}"
            if s.preferred_split:
                split += f" (tercih {s.preferred_split})"
            room = (s.room_type or "Sınıf dersliği") + (" (zorunlu)" if s.room_required else "")
            kind = ", ".join(x for x, f in (("Mesleki", s.vocational), ("Seçmeli", s.elective),
                                            ("Fiziksel", s.physical)) if f) or "Ortak"
            tag = "error" if n_teachers == 0 else ""
            rows.append((s.id, (s.name, s.short_name, s.default_hours, s.brans or "—",
                                DIFFICULTY_LABELS.get(s.difficulty, ""), PREFERRED_TIME_LABELS.get(s.preferred_time, ""),
                                room, split, n_teachers, kind), tag))
        return rows

    def _form(self, s: Subject, title: str):
        teachers = [(t.id, f"{t.name} ({t.brans})") for t in TeacherService(self.app.db).list()]
        rooms_svc = RoomService(self.app.db)
        rooms = [(r.id, f"{r.name} ({r.room_type})") for r in rooms_svc.list()]
        fields = [
            dict(key="name", label="Ders adı (Türkçe)", value=s.name),
            dict(key="short_name", label="Kısa ad", value=s.short_name, help="Programda gösterilir. Örn. MAT"),
            dict(key="default_hours", label="Varsayılan haftalık saat", kind="int", value=s.default_hours,
                 help="Plana eklenirken önerilir; asıl saat öğretim planındadır."),
            dict(key="grade", label="Sınıf düzeyi", kind="combo", options=["", 9, 10, 11, 12],
                 value=s.grade or ""),
            dict(key="alan", label="Alan", value=s.alan),
            dict(key="dal", label="Dal", value=s.dal),
            dict(key="brans", label="Öğretmen branşı", kind="combo", options=TeacherService(self.app.db).branches(),
                 value=s.brans, editable=True, help="Bu branştaki tüm öğretmenler dersi verebilir."),
            dict(key="teacher_ids", label="Ayrıca verebilecek öğretmenler", kind="multi", options=teachers,
                 value=self.svc.teacher_ids(s.id) if s.id else []),
            dict(key="difficulty", label="Zorluk", kind="combo", options=list(DIFFICULTY_LABELS.values()),
                 value=DIFFICULTY_LABELS.get(s.difficulty), help="Zor dersler ilk saatlere konmaya çalışılır."),
            dict(key="physical", label="Fiziksel etkinlik", kind="check", value=s.physical,
                 help="Son saatlere konmaya çalışılır (Beden Eğitimi)."),
            dict(key="preferred_time", label="Tercih edilen zaman", kind="combo",
                 options=list(PREFERRED_TIME_LABELS.values()), value=PREFERRED_TIME_LABELS.get(s.preferred_time)),
            dict(key="room_type", label="Derslik türü", kind="combo", options=[""] + rooms_svc.room_types(),
                 value=s.room_type, editable=True),
            dict(key="room_required", label="Bu derslik türü zorunlu", kind="check", value=s.room_required),
            dict(key="room_ids", label="Uygun derslikler (ek)", kind="multi", options=rooms,
                 value=self.svc.room_ids(s.id) if s.id else [], height=110),
            dict(key="min_block", label="En kısa blok (saat)", kind="int", value=s.min_block, default=1),
            dict(key="max_block", label="En uzun blok (saat)", kind="int", value=s.max_block, default=2,
                 help="Bir günde art arda yapılabilecek en fazla saat."),
            dict(key="allowed_splits", label="İzin verilen bölünmeler", value=s.allowed_splits,
                 help="Örn. 3+3+3; 2+2+2+3. Boş = blok sınırlarına uyan tüm bölünmeler."),
            dict(key="forbidden_splits", label="Yasaklı bölünmeler", value=s.forbidden_splits, help="Örn. 4+1+1+1"),
            dict(key="preferred_split", label="Tercih edilen bölünme", value=s.preferred_split, help="Örn. 3+3+3"),
            dict(key="allow_same_day", label="Aynı güne birden fazla blok", kind="check", value=s.allow_same_day,
                 help="Kapalıysa her gün en fazla bir blok olur."),
            dict(key="vocational", label="Mesleki ders", kind="check", value=s.vocational),
            dict(key="elective", label="Seçmeli ders", kind="check", value=s.elective),
            dict(key="color", label="Renk (#RRGGBB)", value=s.color, help="Boş = otomatik"),
        ]
        vals = FormDialog(self, title, fields, width=760, height=720).show()
        if vals is None:
            return None
        teacher_ids, room_ids = vals.pop("teacher_ids"), vals.pop("room_ids")
        vals["grade"] = int(vals["grade"]) if str(vals["grade"]).strip() else None
        vals["difficulty"] = DIFF_BY_LABEL.get(vals["difficulty"], 0)
        vals["preferred_time"] = TIME_BY_LABEL.get(vals["preferred_time"], "any")
        for k, v in vals.items():
            setattr(s, k, v)
        self.svc.save(s)
        self.svc.set_teachers(s.id, teacher_ids)
        self.svc.set_rooms(s.id, room_ids)
        return s

    def on_add(self):
        if self._form(Subject(), "Yeni ders"):
            self.app.data_changed()

    def on_edit(self):
        ident = self.require_selection()
        if ident and self._form(self.svc.get(ident), "Dersi düzenle"):
            self.app.data_changed()

    def on_delete(self):
        ids = self.table.selected_ids()
        if not ids:
            return show_info(self, "Lütfen silinecek dersi seçin.")
        if ask_yes_no(self, f"{len(ids)} ders silinecek; öğretim planlarından da çıkarılır. Emin misiniz?"):
            for i in ids:
                self.svc.delete(i)
            self.app.data_changed()


class CurriculaPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.svc = CurriculumService(app.db)
        self.subjects = SubjectService(app.db)
        ctk.CTkLabel(self, text="Öğretim Planları", font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 0))
        ctk.CTkLabel(self, text="Her alan/dal ve sınıf düzeyi için haftalık ders çizelgesi. Kaynak: "
                                "meslek.meb.gov.tr çerçeve öğretim programları. Excel'den de aktarılabilir.",
                     text_color="gray").pack(anchor="w", padx=16)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=10)
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(1, weight=1)
        g = guarded(self)
        left_bar = ctk.CTkFrame(body, fg_color="transparent")
        left_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        for text, cmd, color in (("➕ Plan", self.add_plan, None), ("✏️", self.edit_plan, None),
                                 ("⧉ Kopyala", self.copy_plan, "#00695C"), ("🗑", self.delete_plan, "#C62828"),
                                 ("📥 MEB", self.import_meb, "#1565C0")):
            ctk.CTkButton(left_bar, text=text, command=g(cmd), width=70,
                          **({"fg_color": color} if color else {})).pack(side="left", padx=(0, 4))
        self.plans = DataTable(body, [("name", "Plan", 240), ("grade", "Düzey", 50), ("alan", "Alan", 160),
                                      ("hours", "Saat", 50)], selectmode="browse")
        self.plans.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.plans.tree.bind("<<TreeviewSelect>>", lambda _e: self.refresh_items())
        right_bar = ctk.CTkFrame(body, fg_color="transparent")
        right_bar.grid(row=0, column=1, sticky="ew", pady=(0, 6))
        ctk.CTkButton(right_bar, text="➕ Ders ekle", command=g(self.add_item), width=110).pack(side="left", padx=(0, 4))
        ctk.CTkButton(right_bar, text="✏️ Saat", command=g(self.edit_item), width=80).pack(side="left", padx=(0, 4))
        ctk.CTkButton(right_bar, text="🗑 Çıkar", command=g(self.remove_item), width=80, fg_color="#C62828").pack(
            side="left", padx=(0, 4))
        self.total_label = ctk.CTkLabel(right_bar, text="")
        self.total_label.pack(side="right")
        self.items = DataTable(body, [("subject", "Ders", 330), ("hours", "Haftalık Saat", 100),
                                      ("split", "Bölünme", 160)], selectmode="browse")
        self.items.grid(row=1, column=1, sticky="nsew")
        self.items.bind_double_click(g(self.edit_item))
        self.plans.bind_double_click(g(self.edit_plan))

    def refresh(self):
        self.plans.set_rows([(c.id, (c.name, c.grade or "", c.alan, self.svc.total_hours(c.id)))
                             for c in self.svc.list()])
        if not self.plans.tree.selection() and self.plans.tree.get_children():
            self.plans.tree.selection_set(self.plans.tree.get_children()[0])
        self.refresh_items()

    def refresh_items(self):
        pid = self.plans.selected_id()
        if pid is None:
            self.items.set_rows([])
            self.total_label.configure(text="")
            return
        subjects = {s.id: s for s in self.subjects.list()}
        rows = []
        for item in self.svc.items(pid):
            s = subjects[item.subject_id]
            split = s.preferred_split or s.allowed_splits or f"en fazla {s.max_block} saatlik bloklar"
            rows.append((item.subject_id, (s.name, item.hours, split)))
        self.items.set_rows(rows)
        self.total_label.configure(text=f"Toplam {sum(r[1][1] for r in rows)} saat / hafta")

    def _plan_form(self, c: Curriculum, title):
        vals = FormDialog(self, title, [
            dict(key="name", label="Plan adı", value=c.name),
            dict(key="grade", label="Sınıf düzeyi", kind="combo", options=["", 9, 10, 11, 12], value=c.grade or ""),
            dict(key="alan", label="Alan", value=c.alan),
            dict(key="dal", label="Dal", value=c.dal),
            dict(key="program_type", label="Program", kind="combo", options=PROGRAM_TYPES,
                 value=c.program_type or PROGRAM_TYPES[0]),
            dict(key="notes", label="Notlar", kind="textarea", value=c.notes),
        ], height=460).show()
        if vals is None:
            return None
        vals["grade"] = int(vals["grade"]) if str(vals["grade"]).strip() else None
        for k, v in vals.items():
            setattr(c, k, v)
        return self.svc.save(c)

    def import_meb(self):
        from app.ui.meb_import import MebImportDialog
        MebImportDialog(self, self.app).show()
        self.app.data_changed()

    def add_plan(self):
        if self._plan_form(Curriculum(), "Yeni öğretim planı"):
            self.app.data_changed()

    def edit_plan(self):
        pid = self.plans.selected_id()
        if pid and self._plan_form(self.svc.get(pid), "Planı düzenle"):
            self.app.data_changed()

    def copy_plan(self):
        pid = self.plans.selected_id()
        if pid is None:
            return show_info(self, "Önce bir plan seçin.")
        vals = FormDialog(self, "Planı kopyala", [dict(key="name", label="Yeni plan adı",
                                                       value=self.svc.get(pid).name + " (kopya)")], height=200).show()
        if vals:
            self.svc.duplicate(pid, vals["name"])
            self.app.data_changed()

    def delete_plan(self):
        pid = self.plans.selected_id()
        if pid and ask_yes_no(self, "Plan silinecek. Bu planı kullanan sınıfların planı boşalır. Emin misiniz?"):
            self.svc.delete(pid)
            self.app.data_changed()

    def add_item(self):
        pid = self.plans.selected_id()
        if pid is None:
            return show_info(self, "Önce bir plan seçin.")
        existing = {i.subject_id for i in self.svc.items(pid)}
        subjects = [(s.id, s.name) for s in self.subjects.list() if s.id not in existing]
        if not subjects:
            return show_info(self, "Eklenebilecek ders yok. Önce 'Dersler' bölümünden ders tanımlayın.")
        vals = FormDialog(self, "Plana ders ekle", [
            dict(key="subject_id", label="Ders", kind="combo_id", options=subjects, allow_none=False),
            dict(key="hours", label="Haftalık saat", kind="int", value="", help="Boş = dersin varsayılan saati"),
        ], height=240).show()
        if vals:
            hours = vals["hours"] or self.subjects.get(vals["subject_id"]).default_hours
            self.svc.set_item(pid, vals["subject_id"], hours)
            self.app.data_changed()

    def edit_item(self):
        pid, sid = self.plans.selected_id(), self.items.selected_id()
        if pid is None or sid is None:
            return show_info(self, "Önce bir ders seçin.")
        current = next(i.hours for i in self.svc.items(pid) if i.subject_id == sid)
        vals = FormDialog(self, "Haftalık saat", [dict(key="hours", label=self.subjects.get(sid).name, kind="int",
                                                       value=current)], height=200).show()
        if vals:
            self.svc.set_item(pid, sid, vals["hours"])
            self.app.data_changed()

    def remove_item(self):
        pid, sid = self.plans.selected_id(), self.items.selected_id()
        if pid and sid and ask_yes_no(self, "Ders plandan çıkarılsın mı?"):
            self.svc.remove_item(pid, sid)
            self.app.data_changed()
