import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from app import config
from app.database.seed import clear_all, load_demo_data
from app.ui.widgets import ask_yes_no, guarded, show_info
from app.utils.backup import create_backup, list_backups, restore_backup
from app.utils.excel_export import export_data
from app.utils.excel_import import import_workbook

SCALES = {"%80": 0.8, "%90": 0.9, "%100": 1.0, "%110": 1.1, "%125": 1.25, "%150": 1.5}
THEMES = {"Açık": "light", "Koyu": "dark", "Sistem": "system"}


def open_folder(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:  # noqa: BLE001
        pass


class SettingsPage(ctk.CTkScrollableFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        g = guarded(self)
        ctk.CTkLabel(self, text="Ayarlar ve Veri İşlemleri", font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 6))

        gen = self.section("Okul ve ders saatleri")
        self.school = self.entry(gen, 0, "Okul adı", width=380)
        self.year = self.entry(gen, 1, "Öğretim yılı")
        ctk.CTkLabel(gen, text="Haftalık okul günü").grid(row=2, column=0, sticky="w", padx=10, pady=4)
        self.days_var = tk.StringVar()
        ctk.CTkComboBox(gen, values=["5", "6"], variable=self.days_var, width=80, state="readonly").grid(
            row=2, column=1, sticky="w")
        self.periods = self.entry(gen, 3, "Günlük ders saati sayısı")
        ctk.CTkLabel(gen, text="Ders saatleri\n(her satıra bir saat)").grid(row=4, column=0, sticky="nw", padx=10)
        self.times = ctk.CTkTextbox(gen, height=170, width=200)
        self.times.grid(row=4, column=1, sticky="w", pady=4)

        opt = self.section("Optimizasyon")
        self.limit = self.entry(opt, 0, "Süre sınırı (saniye)")
        self.workers = self.entry(opt, 1, "Paralel iş parçacığı")
        self.hard_limit = self.entry(opt, 2, "Sınıf için günlük en fazla zor ders saati (tercih)")
        ctk.CTkLabel(opt, text="Tercihlerin öncelikleri (0 = dikkate alma, 10 = en yüksek). Değişiklikler bir sonraki "
                               "otomatik dağıtımın sonucunu etkiler.", text_color="gray", wraplength=700,
                     justify="left").grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))
        self.weight_vars = {}
        for i, (key, label, _) in enumerate(config.WEIGHT_DEFINITIONS):
            ctk.CTkLabel(opt, text=label).grid(row=4 + i, column=0, sticky="w", padx=10, pady=2)
            var = tk.IntVar()
            val_label = ctk.CTkLabel(opt, text="0", width=40)
            slider = ctk.CTkSlider(opt, from_=0, to=10, number_of_steps=10, variable=var, width=260,
                                   command=lambda v, lbl=val_label: lbl.configure(text=self._level(int(v))))
            slider.grid(row=4 + i, column=1, sticky="w")
            val_label.grid(row=4 + i, column=2, sticky="w", padx=6)
            self.weight_vars[key] = (var, val_label)

        look = self.section("Görünüm")
        ctk.CTkLabel(look, text="Arayüz ölçeği").grid(row=0, column=0, sticky="w", padx=10, pady=4)
        self.scale_var = tk.StringVar()
        ctk.CTkComboBox(look, values=list(SCALES), variable=self.scale_var, width=100, state="readonly").grid(
            row=0, column=1, sticky="w")
        ctk.CTkLabel(look, text="Tema").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        self.theme_var = tk.StringVar()
        ctk.CTkComboBox(look, values=list(THEMES), variable=self.theme_var, width=100, state="readonly").grid(
            row=1, column=1, sticky="w")
        self.auto_backup = tk.IntVar()
        ctk.CTkCheckBox(look, text="Her gün ilk açılışta otomatik yedek al", variable=self.auto_backup).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=10, pady=4)

        ctk.CTkButton(self, text="💾 Ayarları kaydet", height=36, command=g(self.save)).pack(anchor="w", padx=16,
                                                                                           pady=8)

        data = self.section("Veri işlemleri")
        buttons = [
            ("📥 Excel'den içe aktar", self.import_excel, "#1565C0"),
            ("📤 Tüm verileri Excel'e aktar", self.export_excel, "#1565C0"),
            ("📄 Boş Excel şablonu", self.export_template, "#1565C0"),
            ("🛟 Şimdi yedek al", self.backup, "#2E7D32"),
            ("♻ Yedekten geri yükle", self.restore, "#EF6C00"),
            ("📂 Yedek klasörünü aç", lambda: open_folder(config.BACKUP_DIR), None),
            ("📂 Dışa aktarım klasörü", lambda: open_folder(config.EXPORT_DIR), None),
            ("🧪 Örnek verileri yükle", self.demo, "#6A1B9A"),
            ("🗑 Tüm verileri sil", self.wipe, "#C62828"),
        ]
        for i, (text, cmd, color) in enumerate(buttons):
            ctk.CTkButton(data, text=text, command=g(cmd), width=230, **({"fg_color": color} if color else {})).grid(
                row=i // 3, column=i % 3, padx=8, pady=6, sticky="w")
        self.backup_info = ctk.CTkLabel(data, text="", text_color="gray", justify="left")
        self.backup_info.grid(row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(4, 8))

    @staticmethod
    def _level(v: int) -> str:
        return f"{v} " + ("(kapalı)" if v == 0 else "(düşük)" if v <= 3 else "(orta)" if v <= 6 else "(yüksek)")

    def section(self, title):
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        return inner

    def entry(self, parent, row, label, width=120):
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=4)
        var = tk.StringVar()
        ctk.CTkEntry(parent, textvariable=var, width=width).grid(row=row, column=1, sticky="w")
        return var

    def refresh(self):
        s = self.app.db.all_settings()
        self.school.set(s["school_name"])
        self.year.set(s["academic_year"])
        self.days_var.set(str(s["days_count"]))
        self.periods.set(str(s["periods_per_day"]))
        self.times.delete("1.0", "end")
        self.times.insert("1.0", "\n".join(s["period_times"][:int(s["periods_per_day"])]))
        self.limit.set(str(s["solver_time_limit"]))
        self.workers.set(str(s["solver_workers"]))
        self.hard_limit.set(str(s["hard_per_day_limit"]))
        for key, (var, lbl) in self.weight_vars.items():
            var.set(int(s["weights"].get(key, 0)))
            lbl.configure(text=self._level(var.get()))
        self.scale_var.set(next((k for k, v in SCALES.items() if abs(v - float(s["ui_scaling"])) < 0.01), "%100"))
        self.theme_var.set(next((k for k, v in THEMES.items() if v == s["appearance"]), "Açık"))
        self.auto_backup.set(1 if s.get("auto_backup", True) else 0)
        backups = list_backups()
        self.backup_info.configure(text=f"Yedek klasörü: {config.BACKUP_DIR}  ·  {len(backups)} yedek"
                                        + (f"  ·  son: {backups[0].name}" if backups else ""))

    def save(self):
        def as_int(var, label, lo, hi):
            try:
                v = int(var.get())
            except ValueError:
                raise ValueError(f"'{label}' bir tam sayı olmalıdır.")
            if not lo <= v <= hi:
                raise ValueError(f"'{label}' {lo} ile {hi} arasında olmalıdır.")
            return v
        db = self.app.db
        periods = as_int(self.periods, "Günlük ders saati", 1, 14)
        times = [t.strip() for t in self.times.get("1.0", "end").splitlines()]
        old = db.get_setting("period_times")
        times = (times + old[len(times):])[:max(periods, len(old))]
        db.set_setting("school_name", self.school.get().strip() or config.DEFAULT_SETTINGS["school_name"])
        db.set_setting("academic_year", self.year.get().strip())
        db.set_setting("days_count", int(self.days_var.get()))
        db.set_setting("periods_per_day", periods)
        db.set_setting("period_times", times)
        db.set_setting("solver_time_limit", as_int(self.limit, "Süre sınırı", 5, 7200))
        db.set_setting("solver_workers", as_int(self.workers, "Paralel iş parçacığı", 1, 64))
        db.set_setting("hard_per_day_limit", as_int(self.hard_limit, "Günlük zor ders", 1, 14))
        db.set_setting("weights", {k: int(v.get()) for k, (v, _) in self.weight_vars.items()})
        db.set_setting("ui_scaling", SCALES[self.scale_var.get()])
        db.set_setting("appearance", THEMES[self.theme_var.get()])
        db.set_setting("auto_backup", bool(self.auto_backup.get()))
        self.app.apply_appearance()
        self.app.data_changed()
        show_info(self, "Ayarlar kaydedildi.")

    def import_excel(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Excel", "*.xlsx *.xlsm")])
        if not path:
            return
        create_backup(self.app.db, "ice_aktarma_oncesi")
        report = import_workbook(self.app.db, path)
        self.app.data_changed()
        show_info(self, "İçe aktarma tamamlandı (öncesinde otomatik yedek alındı).\n\n" + report.text())

    def export_excel(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".xlsx", initialdir=str(config.EXPORT_DIR),
                                            initialfile="okul_verileri.xlsx", filetypes=[("Excel", "*.xlsx")])
        if path:
            export_data(self.app.db, path)
            show_info(self, f"Veriler aktarıldı:\n{path}\n\nBu dosyayı düzenleyip tekrar içe aktarabilirsiniz.")

    def export_template(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".xlsx", initialdir=str(config.EXPORT_DIR),
                                            initialfile="sablon.xlsx", filetypes=[("Excel", "*.xlsx")])
        if path:
            export_data(self.app.db, path, template_only=True)
            show_info(self, f"Şablon kaydedildi:\n{path}\n\nGünler: 'Pazartesi, Salı'; kapalı saatler: '1-3, 5' veya "
                            f"'tümü'; çoklu dersler ';' ile ayrılır; Evet/Hayır alanları 'Evet' veya 'Hayır'.")

    def backup(self):
        path = create_backup(self.app.db, "manuel")
        self.refresh()
        show_info(self, f"Yedek alındı:\n{path}")

    def restore(self):
        path = filedialog.askopenfilename(parent=self, initialdir=str(config.BACKUP_DIR),
                                          filetypes=[("Veritabanı", "*.db"), ("Tümü", "*.*")])
        if path and ask_yes_no(self, "Mevcut veriler seçilen yedekle değiştirilecek (öncesinde güvenlik yedeği "
                                     "alınır). Devam edilsin mi?"):
            safety = restore_backup(self.app.db, path)
            self.app.data_changed()
            show_info(self, f"Yedek geri yüklendi.\nÖnceki durumun yedeği: {safety.name}")

    def demo(self):
        if self.app.db.is_empty() or ask_yes_no(self, "Mevcut tüm veriler silinip örnek veriler yüklenecek "
                                                      "(öncesinde yedek alınır). Emin misiniz?"):
            if not self.app.db.is_empty():
                create_backup(self.app.db, "ornek_veri_oncesi")
            load_demo_data(self.app.db)
            self.app.data_changed()
            show_info(self, "Örnek veriler yüklendi: 10 sınıf (AMP9A–AMP12B), 21 öğretmen, 16 derslik, MEB Bilişim "
                            "Teknolojileri haftalık ders çizelgesi.")

    def wipe(self):
        if ask_yes_no(self, "TÜM veriler (sınıflar, öğretmenler, dersler, programlar) silinecek. Öncesinde yedek "
                            "alınır. Emin misiniz?"):
            create_backup(self.app.db, "silme_oncesi")
            clear_all(self.app.db)
            self.app.db.set_setting("last_run", None)
            self.app.data_changed()
