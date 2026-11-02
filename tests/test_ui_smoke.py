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


def test_settings_autosave(tmp_path, monkeypatch):
    pytest.importorskip("tkinter")
    from app.database.database import Database
    from app.ui import settings as settings_ui
    from app.ui import widgets
    from app.ui.main_window import MainWindow

    errors = []
    monkeypatch.setattr(widgets, "show_error", lambda *a, **k: errors.append(a[1]))
    monkeypatch.setattr(settings_ui, "show_info", lambda *a, **k: None)
    path = tmp_path / "s.db"
    db = Database(path)
    win = MainWindow(db)
    win.show_page("settings")
    page = win.pages["settings"]
    page.periods.set("9")
    page.school.set("Deneme MTAL")
    win.show_page("classes")
    assert db.get_setting("periods_per_day") == 9 and win.current == "classes"
    win.show_page("settings")
    page.limit.set("abc")
    page.year.set("2030-2031")
    win.show_page("dashboard")
    assert win.current == "settings" and errors
    assert db.get_setting("academic_year") != "2030-2031"
    page.limit.set("100")
    win.on_close()
    again = Database(path).all_settings()
    assert again["solver_time_limit"] == 100 and again["academic_year"] == "2030-2031"
    assert again["school_name"] == "Deneme MTAL" and again["periods_per_day"] == 9
