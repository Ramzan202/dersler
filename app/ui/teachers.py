from app.database.models import Teacher, format_int_list
from app.services.subject_service import SubjectService
from app.services.teacher_service import TeacherService
from app.ui.widgets import AvailabilityDialog, EntityPage, FormDialog, ask_yes_no, show_info


class TeachersPage(EntityPage):
    title = "Öğretmenler"
    columns = [("name", "Ad Soyad", 180), ("brans", "Branş", 150), ("subjects", "Verebildiği Dersler", 330),
               ("daily", "Günlük", 60), ("weekly", "Haftalık", 70), ("pref", "Tercih Günleri", 140),
               ("blocked", "Kapalı Saat", 85)]

    def __init__(self, master, app):
        self.svc = TeacherService(app.db)
        super().__init__(master, app)

    def build_toolbar(self):
        super().build_toolbar()
        self.tool("🗓 Müsaitlik", self.on_availability, "#6A1B9A")

    def load_rows(self):
        subjects = {s.id: s for s in SubjectService(self.app.db).list()}
        days = self.app.day_names
        rows = []
        for t in self.svc.list():
            names = [subjects[i].label for i in t.subject_ids if i in subjects]
            by_brans = [s.label for s in subjects.values()
                        if s.brans and t.brans and s.brans.lower() == t.brans.lower() and s.id not in t.subject_ids]
            text = ", ".join(names + by_brans)
            pref = ", ".join(days[d][:3] for d in t.preferred_day_list if d < len(days)) or "—"
            rows.append((t.id, (t.name, t.brans, text, t.max_daily, t.max_weekly, pref,
                                len(self.svc.get_unavailable(t.id)))))
        return rows

    def _form(self, t: Teacher, title: str):
        subjects = [(s.id, f"{s.name}" + (f"  [{s.brans}]" if s.brans else "")) for s in
                    SubjectService(self.app.db).list()]
        fields = [
            dict(key="name", label="Ad Soyad", value=t.name),
            dict(key="brans", label="Branş", kind="combo", options=self.svc.branches(), value=t.brans, editable=True,
                 help="Aynı branştaki dersler otomatik olarak verilebilir sayılır."),
            dict(key="subject_ids", label="Ek olarak verebildiği dersler", kind="multi", options=subjects,
                 value=t.subject_ids),
            dict(key="max_daily", label="Günlük en fazla ders", kind="int", value=t.max_daily, default=8),
            dict(key="max_weekly", label="Haftalık en fazla ders", kind="int", value=t.max_weekly, default=30),
            dict(key="min_weekly", label="Haftalık en az ders", kind="int", value=t.min_weekly,
                 help="Zorunlu (ör. maaş karşılığı). 0 = yok"),
            dict(key="max_consecutive", label="Art arda en fazla ders (tercih)", kind="int", value=t.max_consecutive,
                 default=6),
            dict(key="preferred_days", label="Tercih ettiği günler", kind="days", days=self.app.day_names,
                 value=t.preferred_day_list, help="Boş = farketmez"),
            dict(key="notes", label="Ek kısıtlar / notlar", kind="textarea", value=t.notes),
        ]
        vals = FormDialog(self, title, fields, height=680).show()
        if vals is None:
            return None
        vals["preferred_days"] = format_int_list(vals["preferred_days"])
        for k, v in vals.items():
            setattr(t, k, v)
        return self.svc.save(t)

    def on_add(self):
        if self._form(Teacher(), "Yeni öğretmen"):
            self.app.data_changed()

    def on_edit(self):
        ident = self.require_selection()
        if ident and self._form(self.svc.get(ident), "Öğretmeni düzenle"):
            self.app.data_changed()

    def on_delete(self):
        ids = self.table.selected_ids()
        if not ids:
            return show_info(self, "Lütfen silinecek öğretmeni seçin.")
        if ask_yes_no(self, f"{len(ids)} öğretmen silinecek. Emin misiniz?"):
            for i in ids:
                self.svc.delete(i)
            self.app.data_changed()

    def on_availability(self):
        ident = self.require_selection()
        if not ident:
            return
        t = self.svc.get(ident)
        result = AvailabilityDialog(self, f"{t.name} – kapalı gün ve saatler", self.app.day_names, self.app.periods,
                                    self.svc.get_unavailable(ident), self.app.period_times).show()
        if result is not None:
            self.svc.set_unavailable(ident, result)
            self.app.data_changed()
