import sys

from app.utils import native_libs


def test_ortools_loads_after_preparation():
    assert native_libs.ortools_error() is None


def test_prepare_is_noop_outside_windows(monkeypatch):
    monkeypatch.setattr(native_libs, "_done", False)
    if not sys.platform.startswith("win"):
        assert native_libs.prepare_native_libs() == []
    assert all(d.is_dir() for d in native_libs.candidate_dirs())
