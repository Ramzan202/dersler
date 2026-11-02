import queue
import threading
import time
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

from app.core.problem import build_problem
from app.core.scheduler import Scheduler
from app.core.validator import validate
from app.services.timetable_service import TimetableService
from app.ui.widgets import DataTable, ask_yes_no, show_error


class SolveDialog(ctk.CTkToplevel):
    """Runs validation and the CP-SAT optimizer in a background thread with live progress and cancellation."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.title("Otomatik Ders Dağılımı")
        self.geometry("760x640")
        self.minsize(640, 520)
        self.result_timetable_id = None
        self.queue: queue.Queue = queue.Queue()
        self.scheduler: Scheduler | None = None
        self.thread: threading.Thread | None = None
        self.started = 0.0
        settings = app.db.all_settings()
        self.tt_svc = TimetableService(app.db)
        active = self.tt_svc.active()

        ctk.CTkLabel(self, text="Otomatik Ders Dağılımı", font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 0))
        ctk.CTkLabel(self, text="Tüm zorunlu kısıtlar (çakışma yok, tam saat, yetkinlik, müsaitlik, derslik, yük "
                                "sınırları) kesin olarak sağlanır; tercihler ayarlardaki önceliklere göre en iyilenir.",
                     wraplength=720, justify="left", text_color="gray").pack(anchor="w", padx=16)

        opts = ctk.CTkFrame(self)
        opts.pack(fill="x", padx=16, pady=10)
        ctk.CTkLabel(opts, text="Süre sınırı (saniye):").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self.time_var = tk.StringVar(value=str(settings.get("solver_time_limit", 90)))
        ctk.CTkEntry(opts, textvariable=self.time_var, width=80).grid(row=0, column=1, sticky="w")
        self.hint_var = tk.IntVar(value=1 if active else 0)
        self.lock_var = tk.IntVar(value=1 if active else 0)
        ctk.CTkCheckBox(opts, text=f"Etkin programı başlangıç noktası olarak kullan"
                                   f"{' (' + active.name + ')' if active else ''}", variable=self.hint_var,
                        state="normal" if active else "disabled").grid(row=1, column=0, columnspan=3, padx=8,
                                                                      pady=4, sticky="w")
        ctk.CTkCheckBox(opts, text="Kilitli (🔒) dersleri yerinde tut", variable=self.lock_var,
                        state="normal" if active else "disabled").grid(row=2, column=0, columnspan=3, padx=8,
                                                                      pady=(0, 6), sticky="w")

        self.status = ctk.CTkLabel(self, text="Başlamak için 'Dağıtımı başlat' düğmesine basın.",
                                   font=ctk.CTkFont(size=14, weight="bold"))
        self.status.pack(anchor="w", padx=16)
        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=16, pady=6)
        self.detail = ctk.CTkLabel(self, text="", text_color="gray")
        self.detail.pack(anchor="w", padx=16)

        self.log = ctk.CTkTextbox(self, height=150)
        self.log.pack(fill="both", expand=True, padx=16, pady=6)
        self.terms = DataTable(self, [("term", "Tercih", 380), ("weight", "Öncelik", 70), ("value", "Değer", 80)],
                               height=6, selectmode="none")
        self.terms.pack(fill="x", padx=16, pady=(0, 6))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(0, 16))
        self.start_btn = ctk.CTkButton(bar, text="▶ Dağıtımı başlat", fg_color="#2E7D32", command=self.start)
        self.start_btn.pack(side="left")
        self.cancel_btn = ctk.CTkButton(bar, text="■ Durdur", fg_color="#C62828", command=self.cancel,
                                        state="disabled")
        self.cancel_btn.pack(side="left", padx=8)
        self.close_btn = ctk.CTkButton(bar, text="Kapat", fg_color="gray", command=self.on_close)
        self.close_btn.pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.transient(master)
        self.after(150, lambda: (self.lift(), self.grab_set()))

    def write(self, text: str):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def start(self):
        try:
            limit = max(5, int(self.time_var.get()))
        except ValueError:
            return show_error(self, "Süre sınırı bir tam sayı olmalıdır.")
        self.log.delete("1.0", "end")
        self.terms.set_rows([])
        self.write("Veriler kontrol ediliyor…")
        problem = build_problem(self.app.db)
        issues = validate(self.app.db, problem)
        errors = [i for i in issues if i.is_error]
        warnings = [i for i in issues if not i.is_error]
        for i in errors:
            self.write(f"✖ [{i.category}] {i.message}")
        for i in warnings:
            self.write(f"⚠ [{i.category}] {i.message}")
        if errors:
            self.status.configure(text=f"Veri hatası: {len(errors)} sorun düzeltilmeli", text_color="#C62828")
            self.write("\nDağıtım başlatılmadı: önce yukarıdaki veri hatalarını düzeltin. (Bunlar, çözümsüz bir "
                       "programdan farklı olarak giriş verilerindeki eksik/çelişkili bilgilerdir.)")
            self._store_last_run("data_error", "Veri hatası", [i.message for i in errors])
            return
        if warnings and not ask_yes_no(self, f"{len(warnings)} uyarı var (ayrıntılar pencerede). Devam edilsin mi?"):
            return
        hints = locked = None
        active = self.tt_svc.active()
        if active and self.hint_var.get():
            hints = self.tt_svc.entries(active.id)
        if active and self.lock_var.get():
            locked = [e for e in self.tt_svc.entries(active.id) if e.locked]
            if locked:
                self.write(f"{len(locked)} kilitli ders saati korunacak.")
        self.limit = limit
        self.problem = problem
        self.scheduler = Scheduler(problem)
        workers = int(self.app.db.get_setting("solver_workers") or 8)
        self.write(f"{len(problem.lessons)} ders, {sum(l.hours for l in problem.lessons)} saat dağıtılacak. "
                   f"En fazla {limit} sn.")
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.close_btn.configure(state="disabled")
        self.status.configure(text="Çalışıyor…", text_color=("black", "white"))
        self.started = time.time()

        def work():
            try:
                res = self.scheduler.solve(time_limit=limit, workers=workers, hints=hints, locked=locked,
                                           on_progress=lambda p: self.queue.put(("progress", p)))
                self.queue.put(("done", res))
            except Exception as exc:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                self.queue.put(("error", exc))

        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()
        self.after(200, self.poll)

    def poll(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "progress":
                    if payload.objective is not None:
                        gap = ""
                        if payload.bound is not None and payload.objective:
                            gap = f", alt sınır {payload.bound:.0f}"
                        self.detail.configure(text=f"{payload.solutions} çözüm · en iyi puan {payload.objective:.0f}"
                                                   f"{gap} (düşük = daha iyi)")
                        if payload.solutions in (1, 2, 5) or payload.solutions % 10 == 0:
                            self.write(f"{payload.elapsed:5.1f} sn: {payload.message}, puan {payload.objective:.0f}")
                    elif payload.message:
                        self.write(payload.message)
                elif kind == "done":
                    return self.finish(payload)
                elif kind == "error":
                    self._reset_buttons()
                    self.status.configure(text="Hata oluştu", text_color="#C62828")
                    self.write(f"Hata: {payload}")
                    return
        except queue.Empty:
            pass
        elapsed = time.time() - self.started
        self.progress.set(min(1.0, elapsed / max(1, self.limit)))
        if not self.detail.cget("text"):
            self.detail.configure(text=f"Geçen süre {elapsed:.0f} sn")
        self.after(200, self.poll)

    def _reset_buttons(self):
        self.start_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.close_btn.configure(state="normal")

    def finish(self, res):
        self._reset_buttons()
        self.progress.set(1.0)
        self.write(f"\nSonuç: {res.status_text} ({res.wall_time:.1f} sn)")
        if res.ok:
            name = self.tt_svc.next_name()
            tt = self.tt_svc.create(name, res.entries, source="auto", status=res.status, objective=res.objective,
                                    solve_seconds=res.wall_time,
                                    notes=f"{datetime.now():%d.%m.%Y %H:%M} otomatik dağıtım")
            self.result_timetable_id = tt.id
            self.status.configure(text=f"✔ {res.status_text}", text_color="#2E7D32")
            self.write(f"'{name}' olarak kaydedildi ve etkin program yapıldı. {len(res.entries)} ders saati "
                       f"yerleştirildi.")
            self.terms.set_rows([(i, (label, weight, value)) for i, (label, weight, value)
                                 in enumerate(res.term_values.values())])
            self._store_last_run(res.status, f"{res.status_text} – {name}", [])
        else:
            color = "#EF6C00" if res.status == "cancelled" else "#C62828"
            self.status.configure(text=f"✖ {res.status_text}", text_color=color)
            if res.status == "infeasible":
                self.write("Program oluşturulmadı. Zorunlu kısıtları ihlal eden bir program kaydedilmez.\n"
                           "Engelleyen kısıtlar:")
            for msg in res.explanations:
                self.write(f"  • {msg}")
            self._store_last_run(res.status, res.status_text, res.explanations)
        self.app.data_changed(rebuild_only=True)

    def _store_last_run(self, status, text, details):
        self.app.db.set_setting("last_run", {"time": f"{datetime.now():%d.%m.%Y %H:%M}", "status": status,
                                             "text": text, "details": details[:20]})

    def cancel(self):
        if self.scheduler:
            self.scheduler.cancel()
            self.write("Durduruluyor… (bulunan en iyi geçerli çözüm kaydedilecek)")

    def on_close(self):
        if self.thread and self.thread.is_alive():
            if not ask_yes_no(self, "Hesaplama sürüyor. Durdurup kapatılsın mı?"):
                return
            self.scheduler.cancel()
            self.thread.join(timeout=15)
            try:
                while True:
                    kind, payload = self.queue.get_nowait()
                    if kind == "done":
                        self.finish(payload)
            except queue.Empty:
                pass
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result_timetable_id
