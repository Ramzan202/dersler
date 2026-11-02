import tkinter as tk

import customtkinter as ctk

from app.services import meb_catalog
from app.ui.widgets import guarded, show_info


class MebImportDialog(ctk.CTkToplevel):
    """Choose Alan → Program → Dal → grades and import MEB weekly course schedules as curricula."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.result = []
        _, _, meta = meb_catalog.load_catalog()
        self.title("MEB çerçeve programından plan ekle")
        self.geometry("820x640")
        ctk.CTkLabel(self, text="MEB Haftalık Ders Çizelgeleri", font=ctk.CTkFont(size=18, weight="bold")).pack(
            anchor="w", padx=14, pady=(14, 0))
        ctk.CTkLabel(self, text=f"{meta['title']} · kaynak: {meta['source']} · alındı: {meta['retrieved']}",
                     text_color="gray", wraplength=780, justify="left").pack(anchor="w", padx=14)
        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=14, pady=10)
        form.grid_columnconfigure(1, weight=1)
        self.alan_var, self.prog_var, self.dal_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        g = guarded(self)
        ctk.CTkLabel(form, text="Alan").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.alan_box = ctk.CTkComboBox(form, values=meb_catalog.alans(), variable=self.alan_var, state="readonly",
                                        command=lambda _v: g(self.on_alan)())
        self.alan_box.grid(row=0, column=1, sticky="ew", padx=8)
        ctk.CTkLabel(form, text="Program").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        self.prog_box = ctk.CTkComboBox(form, values=[], variable=self.prog_var, state="readonly",
                                        command=lambda _v: g(self.on_program)())
        self.prog_box.grid(row=1, column=1, sticky="ew", padx=8)
        ctk.CTkLabel(form, text="Dal").grid(row=2, column=0, sticky="w", padx=8, pady=6)
        self.dal_box = ctk.CTkComboBox(form, values=[], variable=self.dal_var, state="readonly",
                                       command=lambda _v: g(self.preview)())
        self.dal_box.grid(row=2, column=1, sticky="ew", padx=8)
        ctk.CTkLabel(form, text="Sınıflar").grid(row=3, column=0, sticky="w", padx=8, pady=6)
        grades = ctk.CTkFrame(form, fg_color="transparent")
        grades.grid(row=3, column=1, sticky="w", padx=8)
        self.grade_vars = {}
        for gr in ("9", "10", "11", "12"):
            var = tk.IntVar(value=1)
            ctk.CTkCheckBox(grades, text=f"{gr}. sınıf", variable=var, width=20).pack(side="left", padx=(0, 14))
            self.grade_vars[gr] = var
        self.text = ctk.CTkTextbox(self, height=300)
        self.text.pack(fill="both", expand=True, padx=14, pady=4)
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=12)
        ctk.CTkButton(bar, text="📥 Seçilen planları ekle", fg_color="#2E7D32", command=g(self.do_import)).pack(
            side="right", padx=4)
        ctk.CTkButton(bar, text="Kapat", fg_color="gray", command=self.destroy).pack(side="right", padx=4)
        default = "Bilişim Teknolojileri" if "Bilişim Teknolojileri" in meb_catalog.alans() else meb_catalog.alans()[0]
        self.alan_var.set(default)
        self.on_alan()
        self.transient(master)
        self.after(150, lambda: (self.lift(), self.grab_set()))

    def on_alan(self):
        progs = meb_catalog.programs(self.alan_var.get())
        self.prog_box.configure(values=progs)
        self.prog_var.set(progs[0] if progs else "")
        self.on_program()

    def on_program(self):
        dals = meb_catalog.dals(self.alan_var.get(), self.prog_var.get())
        labels = [d or "Alan ortak" for d in dals]
        self.dal_box.configure(values=labels)
        self.dal_var.set(labels[0] if labels else "")
        self.preview()

    def plan(self):
        dal = self.dal_var.get()
        return meb_catalog.find(self.alan_var.get(), self.prog_var.get(), "" if dal == "Alan ortak" else dal)

    def preview(self):
        self.text.delete("1.0", "end")
        plan = self.plan()
        if plan is None:
            return
        lines = [f"Kaynak PDF: {plan.pdf}", ""]
        for grade in ("9", "10", "11", "12"):
            items = plan.grades.get(grade)
            if not items:
                note = " (PDF tablosu okunamadı – elle girin)" if grade in plan.skipped_grades else " (ders yok)"
                lines.append(f"{grade}. SINIF:{note}")
                continue
            lines.append(f"{grade}. SINIF – okulda {plan.hours(grade)} saat/hafta"
                         + (f" + işletmede {plan.ime[grade]} saat" if grade in plan.ime else ""))
            lines.extend(f"    {h:>2}  {name}" for name, h in items)
            lines.append("")
        self.text.insert("1.0", "\n".join(lines))

    def do_import(self):
        plan = self.plan()
        grades = [g for g, v in self.grade_vars.items() if v.get()]
        if plan is None or not grades:
            return show_info(self, "Alan, program, dal ve en az bir sınıf seçin.")
        created = meb_catalog.import_plan(self.app.db, plan, grades)
        self.result.extend(created)
        self.app.data_changed()
        show_info(self, f"{len(created)} öğretim planı eklendi/güncellendi:\n" + "\n".join(c.name for c in created)
                  + "\n\nYeni dersler 'Dersler' bölümüne eklendi; öğretmenlerini ve dersliklerini kontrol edin.")

    def show(self):
        self.wait_window()
        return self.result
