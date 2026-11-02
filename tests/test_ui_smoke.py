"""Opens the main window, visits every page, runs the optimizer through the dialog and edits the timetable.
Skipped automatically when no display is available."""
import os
import sys
import time

import pytest


def _display_available() -> bool:
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY"))


pytestmark = pytest.mark.skipif(not _display_available(), reason="grafik ekran yok")


def test_main_window_end_to_end(tmp_path, monkeypatch):
    pytest.importorskip("tkinter")
    from app.database.database import Database
    from app.database.seed import load_demo_data
    from app.ui import solve_dialog, widgets
    from app.ui.main_window import PAGES, MainWindow

    monkeypatch.setattr(widgets, "ask_yes_no", lambda *a, **k: True)
    monkeypatch.setattr(solve_dialog, "ask_yes_no", lambda *a, **k: True)
    db = Database(tmp_path / "ui.db")
    db.set_setting("periods_per_day", 9)
    load_demo_data(db)
    db.set_setting("solver_time_limit", 60)
    win = MainWindow(db)
    try:
        for key, _, _ in PAGES:
            win.show_page(key)
            win.update()
        page = win.pages["timetable"]
        dlg = solve_dialog.SolveDialog(page, win)
        dlg.start()
        deadline = time.time() + 240
        while dlg.result_timetable_id is None and time.time() < deadline:
            win.update()
            time.sleep(0.05)
        assert dlg.result_timetable_id is not None
        dlg.destroy()
        win.data_changed()
        win.show_page("timetable")
        assert page.entries and not [c for c in page.conflicts if c.severity == "error"]
        prob = page.problem
        for cid, cls in prob.classes.items():
            page.entity_id = cid
            used = {(e.day, e.period) for e in page.view_entries()}
            free_slots = [s for s in sorted(cls.available) if s not in used]
            if free_slots:
                break
        page.render()
        first = page.view_entries()[0]
        free = free_slots[0]
        page.on_click((first.day, first.period), first)
        page.on_click(free, None)
        moved = next(e for e in page.entries if e.id == first.id)
        assert (moved.day, moved.period) == free
        for mode in ("Öğretmen", "Derslik", "Gün", "Sınıf"):
            page.on_mode(mode)
            win.update()
        win.show_page("reports")
        win.update()
    finally:
        win.destroy()
