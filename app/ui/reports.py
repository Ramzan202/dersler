import tkinter as tk

import customtkinter as ctk

from app.core.problem import build_problem
from app.core.workload import build_report
from app.services.timetable_service import TimetableService
from app.ui.widgets import DataTable, guarded


class ReportsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.svc = TimetableService(app.db)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(16, 4))
        ctk.CTkLabel(head, text="Dağıtım Raporu", font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        self.variant_var = tk.StringVar()
        self.variant_box = ctk.CTkComboBox(head, variable=self.variant_var, width=320, state="readonly",
                                           command=lambda _v: guarded(self)(self.render)())
        self.variant_box.pack(side="right")
        ctk.CTkLabel(head, text="Varyant:").pack(side="right", padx=6)

        self.summary = ctk.CTkFrame(self)
        self.summary.pack(fill="x", padx=16, pady=6)
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        for name in ("Öğretmen Yükü", "Branş Ortalamaları", "Derslik Doluluğu", "Sınıf Günlük Yükü",
                     "Çakışmalar", "Yerleştirilemeyen", "Grafik"):
            self.tabs.add(name)
        self.t_load = DataTable(self.tabs.tab("Öğretmen Yükü"), [
            ("name", "Öğretmen", 180), ("brans", "Branş", 140), ("hours", "Haftalık", 70), ("max", "Sınır", 60),
            ("days", "Gün", 50), ("gaps", "Boş Pencere", 90), ("daily", "Günlere Göre", 200)])
        self.t_branch = DataTable(self.tabs.tab("Branş Ortalamaları"), [
            ("b", "Branş", 220), ("avg", "Ortalama", 90), ("min", "En az", 70), ("max", "En çok", 70),
            ("n", "Öğretmen", 80)])
        self.t_rooms = DataTable(self.tabs.tab("Derslik Doluluğu"), [
            ("r", "Derslik", 180), ("used", "Kullanılan Saat", 120), ("avail", "Müsait Saat", 100),
            ("pct", "Doluluk %", 90)])
        self.t_class = DataTable(self.tabs.tab("Sınıf Günlük Yükü"), [("c", "Sınıf", 120)] + [
            (f"d{i}", name, 90) for i, name in enumerate(app.day_names)] + [("total", "Toplam", 70)])
        self.t_conf = DataTable(self.tabs.tab("Çakışmalar"), [("kind", "Tür", 140), ("msg", "Açıklama", 900)])
        self.t_unpl = DataTable(self.tabs.tab("Yerleştirilemeyen"), [("c", "Sınıf", 120), ("s", "Ders", 300),
                                                                      ("h", "Eksik Saat", 90)])
        for t in (self.t_load, self.t_branch, self.t_rooms, self.t_class, self.t_conf, self.t_unpl):
            t.pack(fill="both", expand=True)
        self.chart_holder = self.tabs.tab("Grafik")
        self.canvas = None

    def refresh(self):
        variants = self.svc.list()
        self.labels = {f"{t.name}  ·  {t.created_at}": t.id for t in variants}
        self.variant_box.configure(values=list(self.labels) or ["— program yok —"])
        active = self.svc.active()
        if active:
            self.variant_var.set(next(lbl for lbl, i in self.labels.items() if i == active.id))
        else:
            self.variant_var.set("— program yok —")
        self.render()

    def render(self):
        for w in self.summary.winfo_children():
            w.destroy()
        tid = self.labels.get(self.variant_var.get())
        if tid is None:
            ctk.CTkLabel(self.summary, text="Rapor için önce bir program oluşturun.").pack(padx=10, pady=10)
            for t in (self.t_load, self.t_branch, self.t_rooms, self.t_class, self.t_conf, self.t_unpl):
                t.set_rows([])
            return
        problem = build_problem(self.app.db)
        entries = self.svc.entries(tid)
        r = build_report(problem, entries)
        for i, (label, value) in enumerate(r.summary_rows()):
            box = ctk.CTkFrame(self.summary, fg_color="transparent")
            box.grid(row=i // 4, column=i % 4, padx=10, pady=6, sticky="w")
            ctk.CTkLabel(box, text=value, font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w")
            ctk.CTkLabel(box, text=label, text_color="gray").pack(anchor="w")
        for c in range(4):
            self.summary.grid_columnconfigure(c, weight=1)
        self.t_load.set_rows([(tl.teacher_id, (tl.name, tl.brans, tl.hours, tl.max_weekly, tl.days_worked, tl.gaps,
                                               " · ".join(str(x) for x in tl.daily)),
                               "error" if tl.hours > tl.max_weekly else ("muted" if tl.hours == 0 else ""))
                              for tl in r.teacher_loads])
        self.t_branch.set_rows([(i, (b, f"{avg:.1f}", lo, hi, n)) for i, (b, (avg, lo, hi, n))
                                in enumerate(r.branch_stats.items())])
        self.t_rooms.set_rows([(i, (name, used, avail, f"{pct * 100:.0f}")) for i, (name, used, avail, pct)
                               in enumerate(r.room_usage)])
        self.t_class.set_rows([(i, (name, *daily, sum(daily))) for i, (name, daily) in enumerate(r.class_daily.items())])
        self.t_conf.set_rows([(i, (c.kind, c.message), "error" if c.severity == "error" else "warning")
                              for i, c in enumerate(r.conflicts)])
        self.t_unpl.set_rows([(i, row) for i, row in enumerate(r.unplaced)])
        self.draw_chart(r)

    def draw_chart(self, report):
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except ImportError:
            return
        if self.canvas is not None:
            self.canvas.get_tk_widget().destroy()
        loads = [t for t in report.teacher_loads if t.hours or t.max_weekly]
        fig = Figure(figsize=(9, 4.2), dpi=96)
        ax = fig.add_subplot(111)
        names = [t.name for t in loads]
        ax.bar(range(len(loads)), [t.hours for t in loads], color="#3B78B5", label="Haftalık ders")
        ax.plot(range(len(loads)), [t.max_weekly for t in loads], "r_", markersize=14, label="Sınır")
        ax.set_xticks(range(len(loads)))
        ax.set_xticklabels(names, rotation=60, ha="right", fontsize=8)
        ax.set_ylabel("Ders saati")
        ax.set_title("Öğretmen haftalık ders yükü")
        ax.legend(loc="upper right")
        fig.tight_layout()
        self.canvas = FigureCanvasTkAgg(fig, master=self.chart_holder)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
