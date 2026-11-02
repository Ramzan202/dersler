from app.database.models import Room
from app.services.room_service import RoomService
from app.services.subject_service import SubjectService
from app.ui.widgets import AvailabilityDialog, EntityPage, FormDialog, ask_yes_no, show_info


class RoomsPage(EntityPage):
    title = "Derslikler"
    columns = [("name", "Derslik", 140), ("type", "Tür", 170), ("cap", "Kapasite", 70), ("par", "Aynı anda", 75),
               ("equip", "Donanım", 200), ("cls", "Atanan Sınıf", 100), ("subjects", "Uygun Dersler", 300),
               ("blocked", "Kapalı Saat", 85)]

    def __init__(self, master, app):
        self.svc = RoomService(app.db)
        super().__init__(master, app)

    def build_toolbar(self):
        super().build_toolbar()
        self.tool("🗓 Müsaitlik", self.on_availability, "#6A1B9A")

    def load_rows(self):
        subjects = {s.id: s for s in SubjectService(self.app.db).list()}
        rows = []
        for r in self.svc.list():
            names = [subjects[i].label for i in r.subject_ids if i in subjects]
            names += [s.label for s in subjects.values() if s.room_type and s.room_type == r.room_type
                      and s.id not in r.subject_ids]
            rows.append((r.id, (r.name, r.room_type, r.capacity, r.max_parallel, r.equipment, self.svc.assigned_class(r.id),
                                ", ".join(names) or "Genel dersler", len(self.svc.get_unavailable(r.id)))))
        return rows

    def _form(self, r: Room, title: str):
        subjects = [(s.id, s.name) for s in SubjectService(self.app.db).list()]
        fields = [
            dict(key="name", label="Derslik adı", value=r.name),
            dict(key="room_type", label="Tür", kind="combo", options=self.svc.room_types(), value=r.room_type,
                 editable=True, help="Dersin 'derslik türü' bu türle eşleşirse ders burada yapılabilir."),
            dict(key="capacity", label="Kapasite (öğrenci)", kind="int", value=r.capacity, help="0 = sınırsız"),
            dict(key="max_parallel", label="Aynı anda en fazla ders", kind="int", value=r.max_parallel, default=1,
                 help="Büyük atölyede aynı saatte birden fazla sınıf/grup ders yapabiliyorsa 2, 3…"),
            dict(key="equipment", label="Donanım", value=r.equipment),
            dict(key="alan", label="Alan", value=r.alan),
            dict(key="subject_ids", label="Uygun dersler (ek)", kind="multi", options=subjects, value=r.subject_ids),
            dict(key="notes", label="Notlar", kind="textarea", value=r.notes),
        ]
        vals = FormDialog(self, title, fields).show()
        if vals is None:
            return None
        for k, v in vals.items():
            setattr(r, k, v)
        return self.svc.save(r)

    def on_add(self):
        if self._form(Room(), "Yeni derslik"):
            self.app.data_changed()

    def on_edit(self):
        ident = self.require_selection()
        if ident and self._form(self.svc.get(ident), "Dersliği düzenle"):
            self.app.data_changed()

    def on_delete(self):
        ids = self.table.selected_ids()
        if not ids:
            return show_info(self, "Lütfen silinecek dersliği seçin.")
        if ask_yes_no(self, f"{len(ids)} derslik silinecek. Emin misiniz?"):
            for i in ids:
                self.svc.delete(i)
            self.app.data_changed()

    def on_availability(self):
        ident = self.require_selection()
        if not ident:
            return
        r = self.svc.get(ident)
        result = AvailabilityDialog(self, f"{r.name} – kapalı gün ve saatler", self.app.day_names, self.app.periods,
                                    self.svc.get_unavailable(ident), self.app.period_times).show()
        if result is not None:
            self.svc.set_unavailable(ident, result)
            self.app.data_changed()
