import tkinter as tk
from collections import Counter
from tkinter import filedialog

import customtkinter as ctk

from app import config
from app.core.conflicts import check_timetable
from app.core.problem import build_problem
from app.core.workload import build_report, compare_entries
from app.database.models import Entry
from app.services.timetable_service import TimetableService
from app.ui.solve_dialog import SolveDialog
from app.ui.widgets import DataTable, FormDialog, ask_yes_no, guarded, show_info
from app.utils.colors import subject_color, text_color_for
from app.utils.excel_export import export_timetable
from app.utils.pdf_export import export_pdf

MODES = {"Sınıf": "class", "Öğretmen": "teacher", "Derslik": "room", "Gün": "day"}


class TimetablePage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.svc = TimetableService(app.db)
        self.problem = None
        self.tt = None
        self.entries: list[Entry] = []
        self.conflicts = []
        self.conflict_ids: set[int] = set()
        self.mode = "class"
        self.entity_id = None
        self.selected: Entry | None = None
        self.cells: dict[tuple[int, int], tk.Label] = {}
        g = guarded(self)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 4))
        ctk.CTkLabel(top, text="Ders Programı", font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text="▶ Otomatik Ders Dağılımı", fg_color="#2E7D32", hover_color="#1B5E20", height=36,
                      font=ctk.CTkFont(size=14, weight="bold"), command=g(self.run_solver)).pack(side="right")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(bar, text="Varyant:").pack(side="left")
        self.variant_var = tk.StringVar()
        self.variant_box = ctk.CTkComboBox(bar, variable=self.variant_var, width=300, state="readonly",
                                           command=lambda _v: g(self.on_variant)())
        self.variant_box.pack(side="left", padx=6)
        for text, cmd, color in (("⧉ Kopyala", self.copy_variant, None), ("✏️ Ad", self.rename_variant, None),
                                 ("🗑 Sil", self.delete_variant, "#C62828"), ("⇄ Karşılaştır", self.compare, "#00695C"),
                                 ("📊 Excel", self.export_excel, "#1565C0"), ("📄 PDF", self.export_pdf, "#1565C0")):
            ctk.CTkButton(bar, text=text, width=96, command=g(cmd), **({"fg_color": color} if color else {})).pack(
                side="left", padx=3)

        view = ctk.CTkFrame(self, fg_color="transparent")
        view.pack(fill="x", padx=16, pady=4)
        self.mode_btn = ctk.CTkSegmentedButton(view, values=list(MODES), command=lambda v: g(self.on_mode)(v))
        self.mode_btn.set("Sınıf")
        self.mode_btn.pack(side="left")
        ctk.CTkButton(view, text="◀", width=32, command=g(lambda: self.step(-1))).pack(side="left", padx=(12, 2))
        self.entity_var = tk.StringVar()
        self.entity_box = ctk.CTkComboBox(view, variable=self.entity_var, width=260, state="readonly",
                                          command=lambda _v: g(self.on_entity)())
        self.entity_box.pack(side="left", padx=2)
        ctk.CTkButton(view, text="▶", width=32, command=g(lambda: self.step(1))).pack(side="left", padx=2)
        ctk.CTkButton(view, text="✔ Kontrol et", width=110, command=g(self.check)).pack(side="left", padx=12)
        self.info = ctk.CTkLabel(view, text="", text_color="gray")
        self.info.pack(side="left", padx=6)

        ctk.CTkLabel(self, text="Taşımak için: derse tıklayın, sonra hedef saate tıklayın (dolu ise yer değiştirir). "
                                "Sağ tık: öğretmen/derslik değiştir, kilitle, sil, ders ekle. Esc: seçimi bırak.",
                     text_color="gray", anchor="w").pack(fill="x", padx=16)

        self.grid_frame = ctk.CTkScrollableFrame(self, orientation="vertical")
        self.grid_frame.pack(fill="both", expand=True, padx=16, pady=6)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=(0, 12))
        self.conflict_title = ctk.CTkLabel(bottom, text="", font=ctk.CTkFont(weight="bold"), anchor="w")
        self.conflict_title.pack(fill="x")
        self.conflict_table = DataTable(bottom, [("kind", "Tür", 140), ("msg", "Açıklama", 900)], height=5,
                                        selectmode="browse")
        self.conflict_table.pack(fill="x")
        self.conflict_table.tree.bind("<<TreeviewSelect>>", lambda _e: self.focus_conflict())
        self.winfo_toplevel().bind("<Escape>", lambda _e: self.clear_selection(), add="+")

    # ------------------------------------------------------------------ data
    def refresh(self):
        self.problem = build_problem(self.app.db)
        variants = self.svc.list()
        self.variant_labels = {f"{t.name}  ·  {t.created_at}" + ("  ★" if t.is_active else ""): t.id
                               for t in variants}
        labels = list(self.variant_labels)
        self.variant_box.configure(values=labels or ["— program yok —"])
        active = self.svc.active()
        self.tt = active
        if active:
            self.variant_var.set(next(lbl for lbl, i in self.variant_labels.items() if i == active.id))
        else:
            self.variant_var.set("— program yok —")
        self.reload_entries()
        self.fill_entities()
        self.render()

    def reload_entries(self):
        self.entries = self.svc.entries(self.tt.id) if self.tt else []
        self.conflicts = check_timetable(self.problem, self.entries) if self.tt else []
        self.conflict_ids = {i for c in self.conflicts if c.severity == "error" for i in c.entry_ids}
        self.show_conflicts()

    def entity_options(self):
        p = self.problem
        if self.mode == "class":
            return [(c.id, c.name) for c in sorted(p.classes.values(), key=lambda c: (c.grade, c.name))]
        if self.mode == "teacher":
            return [(t.id, f"{t.name} ({t.brans})") for t in sorted(p.teachers.values(), key=lambda t: t.name)]
        if self.mode == "room":
            return [(r.id, r.name) for r in sorted(p.rooms.values(), key=lambda r: r.name)]
        return [(d, name) for d, name in enumerate(p.days)]

    def fill_entities(self):
        options = self.entity_options()
        self.entity_map = {label: ident for ident, label in options}
        self.entity_box.configure(values=list(self.entity_map) or ["—"])
        if self.entity_id not in self.entity_map.values():
            self.entity_id = options[0][0] if options else None
        label = next((lbl for lbl, i in self.entity_map.items() if i == self.entity_id), "—")
        self.entity_var.set(label)

    def on_variant(self):
        tid = self.variant_labels.get(self.variant_var.get())
        if tid:
            self.svc.set_active(tid)
            self.app.data_changed(rebuild_only=True)

    def on_mode(self, value):
        self.mode = MODES[value]
        self.entity_id = None
        self.selected = None
        self.fill_entities()
        self.render()

    def on_entity(self):
        self.entity_id = self.entity_map.get(self.entity_var.get())
        self.selected = None
        self.render()

    def step(self, delta):
        ids = list(self.entity_map.values())
        if not ids:
            return
        idx = ids.index(self.entity_id) if self.entity_id in ids else 0
        self.entity_id = ids[(idx + delta) % len(ids)]
        self.fill_entities()
        self.render()

    def view_entries(self) -> list[Entry]:
        if self.mode == "class":
            return [e for e in self.entries if e.class_id == self.entity_id]
        if self.mode == "teacher":
            return self._dedupe([e for e in self.entries if self.entity_id in e.teacher_ids])
        if self.mode == "room":
            return self._dedupe([e for e in self.entries if self.entity_id in e.room_ids])
        return [e for e in self.entries if e.day == self.entity_id]

    @staticmethod
    def _dedupe(items: list[Entry]) -> list[Entry]:
        """A combined lesson appears once per slot in teacher/room views."""
        seen, out = set(), []
        for e in items:
            key = (e.day, e.period, e.link, e.subject_id) if e.link else ("id", e.id)
            if key not in seen:
                seen.add(key)
                out.append(e)
        return out

    def _partners(self, entry: Entry) -> list[Entry]:
        if not entry.link:
            return []
        return [x for x in self.entries if x.id != entry.id and x.link == entry.link and x.day == entry.day
                and x.period == entry.period and x.subject_id == entry.subject_id]

    @staticmethod
    def _short_name(name: str) -> str:
        parts = name.split()
        if len(parts) < 2:
            return name
        first = [w for w in parts if not w.isupper()] or parts[:1]
        last = [w for w in parts if w.isupper()] or parts[-1:]
        return "".join(w[0] + "." for w in first) + " ".join(last)

    def _group_entries(self, class_id) -> dict:
        """Lessons of the class's groups (şube grupları), shown read-only in the parent's grid."""
        p = self.problem
        groups = [cid for cid, c in p.classes.items() if c.parent_id == class_id]
        out = {}
        for e in self.entries:
            if e.class_id in groups:
                out.setdefault((e.day, e.period), []).append(e)
        return out

    def _class_names(self, entry: Entry) -> str:
        p = self.problem
        ids = [entry.class_id] + [x.class_id for x in self._partners(entry)]
        return "+".join(p.classes[c].name for c in ids if c in p.classes) or "?"

    # ------------------------------------------------------------------ rendering
    def cell_text(self, e: Entry) -> str:
        p = self.problem
        subj = p.subjects[e.subject_id].label if e.subject_id in p.subjects else "?"
        external = e.subject_id in p.subjects and p.subjects[e.subject_id].external
        names = [p.teachers[t].name for t in e.teacher_ids if t in p.teachers]
        if len(names) > 1:
            names = [self._short_name(n) for n in names]
        if len(names) > 3:
            names = names[:2] + [f"+{len(names) - 2}"]
        teacher = ", ".join(names) or ("işletmede" if external else "— öğretmen yok —")
        room = ", ".join(p.rooms[r].name for r in e.room_ids if r in p.rooms)
        cls = self._class_names(e)
        lock = "🔒 " if e.locked else ""
        if self.mode == "class":
            parts = [lock + subj, teacher, room]
        elif self.mode == "teacher":
            parts = [lock + cls, subj, room]
        elif self.mode == "room":
            parts = [lock + cls, subj, teacher]
        else:
            parts = [lock + subj, teacher.split(" ")[0] if teacher else "", room]
        return "\n".join(x for x in parts if x)

    def render(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.cells = {}
        p = self.problem
        if p is None:
            return
        if self.tt is None:
            ctk.CTkLabel(self.grid_frame, text="Henüz program yok. 'Otomatik Ders Dağılımı' ile oluşturun.",
                         font=ctk.CTkFont(size=15)).pack(pady=40)
            self.info.configure(text="")
            return
        times = self.app.period_times
        items = self.view_entries()
        font = ("Segoe UI", max(8, int(9 * self.app.scaling)))
        head_font = ("Segoe UI", max(8, int(10 * self.app.scaling)), "bold")
        frame = tk.Frame(self.grid_frame, bg="#B0BEC5")
        frame.pack(fill="both", expand=True)

        if self.mode == "day":
            day = self.entity_id or 0
            rows = sorted(p.classes.values(), key=lambda c: (c.grade, c.name))
            tk.Label(frame, text="Sınıf", font=head_font, bg="#1F4E79", fg="white", padx=4, pady=4).grid(
                row=0, column=0, sticky="nsew", padx=1, pady=1)
            for per in range(p.periods):
                tk.Label(frame, text=f"{per + 1}." + (f"\n{times[per]}" if per < len(times) else ""), font=head_font,
                         bg="#1F4E79", fg="white").grid(row=0, column=per + 1, sticky="nsew", padx=1, pady=1)
                frame.grid_columnconfigure(per + 1, weight=1, uniform="c")
            by_cell = {(e.class_id, e.period): e for e in items}
            for r, cls in enumerate(rows, start=1):
                tk.Label(frame, text=cls.name, font=head_font, bg="#ECEFF1").grid(row=r, column=0, sticky="nsew",
                                                                                  padx=1, pady=1)
                for per in range(p.periods):
                    e = by_cell.get((cls.id, per))
                    closed = (day, per) not in cls.available
                    self._make_cell(frame, r, per + 1, e, font, closed, slot=None)
            self.info.configure(text=f"{p.days[day] if day < len(p.days) else ''}: {len(items)} ders saati")
            return

        tk.Label(frame, text="Saat", font=head_font, bg="#1F4E79", fg="white", padx=6, pady=6).grid(
            row=0, column=0, sticky="nsew", padx=1, pady=1)
        for d, name in enumerate(p.days):
            tk.Label(frame, text=name, font=head_font, bg="#1F4E79", fg="white", pady=6).grid(
                row=0, column=d + 1, sticky="nsew", padx=1, pady=1)
            frame.grid_columnconfigure(d + 1, weight=1, uniform="c")
        grid = {}
        for e in items:
            grid.setdefault((e.day, e.period), []).append(e)
        closed_slots = self._closed_slots()
        group_cells = self._group_entries(self.entity_id) if self.mode == "class" else {}
        for per in range(p.periods):
            label = f"{per + 1}. ders" + (f"\n{times[per]}" if per < len(times) else "")
            tk.Label(frame, text=label, font=head_font, bg="#ECEFF1", padx=6).grid(row=per + 1, column=0,
                                                                                  sticky="nsew", padx=1, pady=1)
            for d in range(p.num_days):
                cell_entries = grid.get((d, per), [])
                e = cell_entries[0] if cell_entries else None
                if e is None and (d, per) in group_cells:
                    self._group_cell(frame, per + 1, d + 1, group_cells[(d, per)], font, slot=(d, per))
                    continue
                self._make_cell(frame, per + 1, d + 1, e, font, (d, per) in closed_slots, slot=(d, per),
                                clash=len(cell_entries) > 1)
        hours = len(items)
        extra = ""
        if self.mode == "class":
            missing = self._missing_for_class(self.entity_id)
            if missing:
                extra = " · Eksik: " + ", ".join(f"{p.subjects[s].label} {n}" for s, n in missing)
        elif self.mode == "teacher" and self.entity_id in p.teachers:
            t = p.teachers[self.entity_id]
            extra = f" / sınır {t.max_weekly}"
        self.info.configure(text=f"{hours} ders saati{extra}")

    def _closed_slots(self) -> set:
        p = self.problem
        if self.mode == "class" and self.entity_id in p.classes:
            cls = p.classes[self.entity_id]
            return {(d, per) for d in range(p.num_days) for per in range(p.periods) if (d, per) not in cls.available}
        if self.mode == "teacher" and self.entity_id in p.teachers:
            return set(p.teachers[self.entity_id].unavailable)
        if self.mode == "room" and self.entity_id in p.rooms:
            return set(p.rooms[self.entity_id].unavailable)
        return set()

    def _make_cell(self, frame, row, col, e, font, closed, slot, clash=False):
        p = self.problem
        if e is not None:
            bg = subject_color(p.subjects.get(e.subject_id))
            text = self.cell_text(e) + (f"\n(+{1} çakışma)" if clash else "")
        else:
            bg = "#D7CCC8" if closed else "#FFFFFF"
            text = "kapalı" if closed else ""
        is_conflict = e is not None and (e.id in self.conflict_ids or clash)
        is_selected = e is not None and self.selected is not None and e.id == self.selected.id
        border = "#D50000" if is_conflict else ("#0D47A1" if is_selected else bg)
        holder = tk.Frame(frame, bg=border, padx=3 if (is_conflict or is_selected) else 0,
                          pady=3 if (is_conflict or is_selected) else 0)
        holder.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
        lbl = tk.Label(holder, text=text, bg=bg, fg=text_color_for(bg) if e else "#9E9E9E", font=font,
                       justify="center", height=3, width=16, wraplength=int(210 * self.app.scaling))
        lbl.pack(fill="both", expand=True)
        if slot is not None:
            lbl.bind("<Button-1>", lambda _ev, s=slot, en=e: guarded(self)(self.on_click)(s, en))
            lbl.bind("<Button-3>", lambda ev, s=slot, en=e: guarded(self)(self.on_menu)(ev, s, en))
            lbl.bind("<Button-2>", lambda ev, s=slot, en=e: guarded(self)(self.on_menu)(ev, s, en))
        self.cells[slot or (row, col)] = lbl

    def _group_cell(self, frame, row, col, items, font, slot):
        p = self.problem
        seen = []
        for e in items:
            label = f"{p.classes[e.class_id].name.split('-')[-1]}: {p.subjects[e.subject_id].label}"
            if label not in seen:
                seen.append(label)
        text = "Gruplarda:\n" + " · ".join(seen)
        lbl = tk.Label(frame, text=text, bg="#ECEFF1", fg="#546E7A", font=font, justify="center", height=3, width=16,
                       wraplength=int(210 * self.app.scaling))
        lbl.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
        lbl.bind("<Button-1>", lambda _ev, s=slot: guarded(self)(self.on_click)(s, None))
        self.cells[slot] = lbl

    def _missing_for_class(self, cid):
        counts = Counter(e.subject_id for e in self.entries if e.class_id == cid)
        out = []
        for lesson in self.problem.lessons:
            if lesson.class_id == cid and counts.get(lesson.subject_id, 0) < lesson.hours:
                out.append((lesson.subject_id, lesson.hours - counts.get(lesson.subject_id, 0)))
        return out

    def show_conflicts(self):
        errors = [c for c in self.conflicts if c.severity == "error"]
        warnings = [c for c in self.conflicts if c.severity != "error"]
        if not self.tt:
            self.conflict_title.configure(text="")
        elif errors:
            self.conflict_title.configure(text=f"⚠ {len(errors)} zorunlu kısıt ihlali (çakışma) var",
                                          text_color="#C62828")
        else:
            self.conflict_title.configure(text="✔ Zorunlu kısıt ihlali yok" +
                                               (f" · {len(warnings)} uyarı" if warnings else ""),
                                          text_color="#2E7D32")
        labels = {"class_clash": "Sınıf çakışması", "teacher_clash": "Öğretmen çakışması",
                  "room_clash": "Derslik çakışması", "missing_hours": "Eksik saat", "extra_hours": "Fazla saat",
                  "teacher_avail": "Öğretmen kapalı", "room_avail": "Derslik kapalı", "class_avail": "Sınıf kapalı",
                  "qualification": "Yetkinlik", "room_type": "Derslik türü", "teacher_daily": "Günlük yük",
                  "teacher_weekly": "Haftalık yük", "class_daily": "Sınıf günlük", "bounds": "Saat dışı",
                  "no_teacher": "Öğretmen yok", "teacher_split": "Uyarı", "unknown_lesson": "Plan dışı"}
        self.conflict_table.set_rows([(i, (labels.get(c.kind, c.kind), c.message),
                                       "error" if c.severity == "error" else "warning")
                                      for i, c in enumerate(errors + warnings)])
        self._conflict_list = errors + warnings

    def focus_conflict(self):
        idx = self.conflict_table.selected_id()
        if idx is None or idx >= len(self._conflict_list):
            return
        c = self._conflict_list[idx]
        entry = next((e for e in self.entries if e.id in c.entry_ids), None)
        if entry is None:
            return
        if self.mode == "day":
            self.entity_id = entry.day
        else:
            self.mode = "class"
            self.mode_btn.set("Sınıf")
            self.entity_id = entry.class_id
        self.fill_entities()
        self.render()

    # ------------------------------------------------------------------ editing
    def clear_selection(self):
        if self.selected is not None:
            self.selected = None
            self.render()

    def on_click(self, slot, entry):
        if self.selected is None:
            if entry is not None:
                self.selected = entry
                self.render()
            return
        if entry is not None and entry.id == self.selected.id:
            self.selected = None
            self.render()
            return
        self.move(self.selected, slot, entry)

    def move(self, entry: Entry, slot, occupant: Entry | None):
        old = (entry.day, entry.period)
        moving = [entry] + self._partners(entry)
        swapping = ([occupant] + self._partners(occupant)) if occupant is not None else []
        for e in moving:
            e.day, e.period = slot
            self.svc.update_entry(e)
        for e in swapping:
            e.day, e.period = old
            self.svc.update_entry(e)
        self.selected = None
        self.after_edit("Ders taşındı" + (" (yer değiştirildi)" if occupant else ""))

    def after_edit(self, message: str):
        self.reload_entries()
        self.render()
        n = sum(1 for c in self.conflicts if c.severity == "error")
        self.app.set_status(f"{message}. " + (f"⚠ {n} çakışma var." if n else "Çakışma yok."))

    def on_menu(self, event, slot, entry):
        menu = tk.Menu(self, tearoff=0)
        g = guarded(self)
        if entry is not None:
            menu.add_command(label="Öğretmeni değiştir…", command=g(lambda: self.change_teacher(entry)))
            menu.add_command(label="Dersliği değiştir…", command=g(lambda: self.change_room(entry)))
            menu.add_command(label="Kilidi aç" if entry.locked else "Kilitle (otomatik dağıtımda yerinde kalsın)",
                             command=g(lambda: self.toggle_lock(entry)))
            menu.add_separator()
            menu.add_command(label="Bu saati sil", command=g(lambda: self.delete_entry(entry)))
        elif self.mode == "class" and self.entity_id is not None:
            menu.add_command(label="Ders ekle…", command=g(lambda: self.add_entry(slot)))
        else:
            return
        menu.tk_popup(event.x_root, event.y_root)

    def _lesson(self, entry_or_key):
        key = (entry_or_key.class_id, entry_or_key.subject_id) if isinstance(entry_or_key, Entry) else entry_or_key
        return self.problem.lesson_by_key().get(key)

    def change_teacher(self, entry):
        lesson = self._lesson(entry)
        p = self.problem
        candidates = lesson.teacher_candidates if lesson else list(p.teachers)
        options = [(t.id, f"{t.name} ({t.brans})" + (" ✓" if t.id in candidates else ""))
                   for t in sorted(p.teachers.values(), key=lambda t: t.name)]
        vals = FormDialog(self, "Öğretmen(ler)i değiştir", [
            dict(key="teachers", label="Öğretmen(ler)", kind="multi", options=options, value=entry.teacher_ids,
                 help="✓ = bu derse yetkili. Birden fazla seçilirse ekip olarak aynı anda derse girerler. Yetkisi "
                      "olmayan öğretmen "
                      "seçilirse kontrol listesinde uyarı çıkar."),
            dict(key="all", label="Bu dersin tüm saatlerine uygula", kind="check", value=1),
        ], width=720, height=520).show()
        if not vals:
            return
        if not vals["teachers"]:
            raise ValueError("En az bir öğretmen seçin.")
        keys = {(x.class_id, x.subject_id) for x in [entry] + self._partners(entry)}
        targets = [e for e in self.entries if (e.class_id, e.subject_id) in keys] if vals["all"] \
            else [entry] + self._partners(entry)
        for e in targets:
            e.teacher_id = vals["teachers"][0]
            e.extra_teachers = ",".join(map(str, vals["teachers"][1:]))
            self.svc.update_entry(e)
        self.after_edit("Öğretmen değiştirildi")

    def change_room(self, entry):
        p = self.problem
        lesson = self._lesson(entry)
        rooms = sorted(p.rooms.values(), key=lambda r: r.name)
        options = [(r.id, r.name + (" ✓" if lesson and r.id in lesson.room_candidates else "")) for r in rooms]
        vals = FormDialog(self, "Derslik(ler)i değiştir", [
            dict(key="rooms", label="Derslik(ler)", kind="multi", options=options, value=entry.room_ids,
                 help="✓ = bu ders için uygun derslik. Birden fazla seçilirse aynı anda kullanılır."),
            dict(key="all", label="Bu dersin tüm saatlerine uygula", kind="check", value=0),
        ], width=720, height=480).show()
        if not vals:
            return
        targets = [e for e in self.entries if (e.class_id, e.subject_id) == (entry.class_id, entry.subject_id)] \
            if vals["all"] else [entry]
        for e in targets:
            e.room_id = vals["rooms"][0] if vals["rooms"] else None
            e.extra_rooms = ",".join(map(str, vals["rooms"][1:]))
            self.svc.update_entry(e)
        self.after_edit("Derslik değiştirildi")

    def toggle_lock(self, entry):
        value = 0 if entry.locked else 1
        for e in [entry] + self._partners(entry):
            e.locked = value
            self.svc.update_entry(e)
        self.after_edit("Kilit değiştirildi")

    def delete_entry(self, entry):
        for e in [entry] + self._partners(entry):
            self.svc.delete_entry(e.id, self.tt.id)
        self.after_edit("Ders saati silindi")

    def add_entry(self, slot):
        p = self.problem
        missing = self._missing_for_class(self.entity_id)
        lessons = [l for l in p.lessons if l.class_id == self.entity_id]
        if not lessons:
            return show_info(self, "Bu sınıfın planında ders yok.")
        options = [(l.subject_id, p.subjects[l.subject_id].name + (f"  (eksik {dict(missing)[l.subject_id]})"
                                                                   if l.subject_id in dict(missing) else ""))
                   for l in lessons]
        default = missing[0][0] if missing else lessons[0].subject_id
        vals = FormDialog(self, "Ders ekle", [dict(key="subject_id", label="Ders", kind="combo_id", options=options,
                                                   value=default, allow_none=False)], height=200).show()
        if not vals:
            return
        lesson = self._lesson((self.entity_id, vals["subject_id"]))
        same = [e for e in self.entries if (e.class_id, e.subject_id) == (self.entity_id, vals["subject_id"])]
        if same:
            team, rooms = same[0].teacher_ids, same[0].room_ids
        else:
            team = list(lesson.teacher_candidates) if lesson.team else lesson.teacher_candidates[:1]
            rooms = list(lesson.room_candidates) if lesson.room_mode == "all" else lesson.room_candidates[:1]
        self.svc.add_entry(Entry(timetable_id=self.tt.id, class_id=self.entity_id, subject_id=vals["subject_id"],
                                 teacher_id=team[0] if team else None, room_id=rooms[0] if rooms else None,
                                 day=slot[0], period=slot[1], extra_teachers=",".join(map(str, team[1:])),
                                 extra_rooms=",".join(map(str, rooms[1:])),
                                 block=max((e.block for e in self.entries), default=0) + 1))
        self.after_edit("Ders eklendi")

    def check(self):
        if not self.tt:
            return show_info(self, "Kontrol edilecek program yok.")
        self.problem = build_problem(self.app.db)
        self.reload_entries()
        self.render()
        n = sum(1 for c in self.conflicts if c.severity == "error")
        show_info(self, "Program tüm zorunlu kısıtları sağlıyor." if n == 0 else
                  f"{n} zorunlu kısıt ihlali bulundu. Ayrıntılar alttaki listede.")

    # ------------------------------------------------------------------ variants
    def run_solver(self):
        tid = SolveDialog(self, self.app).show()
        if tid:
            self.app.data_changed(rebuild_only=True)

    def _require_tt(self):
        if not self.tt:
            show_info(self, "Önce bir program oluşturun.")
            return False
        return True

    def copy_variant(self):
        if not self._require_tt():
            return
        vals = FormDialog(self, "Varyantı kopyala", [dict(key="name", label="Yeni varyant adı",
                                                          value=self.svc.next_name())], height=200).show()
        if vals:
            self.svc.duplicate(self.tt.id, vals["name"])
            self.app.data_changed(rebuild_only=True)

    def rename_variant(self):
        if not self._require_tt():
            return
        vals = FormDialog(self, "Varyant adı", [dict(key="name", label="Ad", value=self.tt.name)], height=200).show()
        if vals:
            self.svc.rename(self.tt.id, vals["name"])
            self.app.data_changed(rebuild_only=True)

    def delete_variant(self):
        if self._require_tt() and ask_yes_no(self, f"'{self.tt.name}' silinsin mi?"):
            self.svc.delete(self.tt.id)
            rest = self.svc.list()
            if rest:
                self.svc.set_active(rest[0].id)
            self.app.data_changed(rebuild_only=True)

    def compare(self):
        variants = self.svc.list()
        if len(variants) < 2:
            return show_info(self, "Karşılaştırma için en az iki varyant gerekir.")
        options = [(t.id, f"{t.name} ({t.created_at})") for t in variants]
        vals = FormDialog(self, "Varyant karşılaştır", [
            dict(key="a", label="1. varyant", kind="combo_id", options=options, value=variants[1].id,
                 allow_none=False),
            dict(key="b", label="2. varyant", kind="combo_id", options=options, value=variants[0].id,
                 allow_none=False),
        ], height=240).show()
        if vals:
            CompareDialog(self, self.problem, self.svc, vals["a"], vals["b"])

    def export_excel(self):
        if not self._require_tt():
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".xlsx", initialdir=str(config.EXPORT_DIR),
                                            initialfile=f"{self.tt.name}.xlsx".replace("№", "No"),
                                            filetypes=[("Excel", "*.xlsx")])
        if path:
            export_timetable(self.problem, self.entries, path, title=f"{self.app.settings['school_name']} – "
                                                                     f"{self.tt.name}",
                             period_times=self.app.period_times)
            self.app.set_status(f"Excel kaydedildi: {path}")
            show_info(self, f"Program Excel'e aktarıldı:\n{path}\n\nSayfalar: okul programı, her sınıf, her "
                            f"öğretmen, her derslik ve öğretmen yük raporu.")

    def export_pdf(self):
        if not self._require_tt():
            return
        vals = FormDialog(self, "PDF olarak yazdır", [dict(key="mode", label="Hangi programlar?", kind="combo",
                                                           options=["Sınıflar", "Öğretmenler", "Derslikler"])],
                          height=200).show()
        if not vals:
            return
        mode = {"Sınıflar": "class", "Öğretmenler": "teacher", "Derslikler": "room"}[vals["mode"]]
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".pdf", initialdir=str(config.EXPORT_DIR),
                                            initialfile=f"{self.tt.name} - {vals['mode']}.pdf".replace("№", "No"),
                                            filetypes=[("PDF", "*.pdf")])
        if path:
            export_pdf(self.problem, self.entries, path, mode=mode, title=self.tt.name,
                       period_times=self.app.period_times, school_name=self.app.settings["school_name"])
            self.app.set_status(f"PDF kaydedildi: {path}")
            show_info(self, f"PDF kaydedildi:\n{path}")


class CompareDialog(ctk.CTkToplevel):
    def __init__(self, master, problem, svc, a_id, b_id):
        super().__init__(master)
        self.title("Varyant karşılaştırma")
        self.geometry("760x480")
        a, b = svc.get(a_id), svc.get(b_id)
        ea, eb = svc.entries(a_id), svc.entries(b_id)
        ra, rb = build_report(problem, ea), build_report(problem, eb)

        def spread(r):
            return max((hi - lo for _, lo, hi, n in r.branch_stats.values() if n > 1), default=0)

        rows = [("Kaynak", a.source, b.source), ("Amaç puanı (düşük = iyi)",
                                                 f"{a.objective:.0f}" if a.objective is not None else "—",
                                                 f"{b.objective:.0f}" if b.objective is not None else "—")]
        for (label, va), (_, vb) in zip(ra.summary_rows(), rb.summary_rows()):
            rows.append((label, va, vb))
        rows.append(("En büyük branş içi yük farkı", str(spread(ra)), str(spread(rb))))
        rows.append(("Farklı ders saati sayısı", str(compare_entries(ea, eb)), str(compare_entries(eb, ea))))
        ctk.CTkLabel(self, text="Varyant karşılaştırma", font=ctk.CTkFont(size=18, weight="bold")).pack(
            anchor="w", padx=12, pady=(12, 4))
        table = DataTable(self, [("m", "Ölçüt", 330), ("a", a.name, 190), ("b", b.name, 190)], selectmode="none")
        table.pack(fill="both", expand=True, padx=12, pady=6)
        table.set_rows([(i, r) for i, r in enumerate(rows)])
        ctk.CTkButton(self, text="Kapat", command=self.destroy).pack(pady=(0, 12))
        self.transient(master)
        self.after(150, lambda: (self.lift(), self.grab_set()))
