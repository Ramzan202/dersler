"""Make the Microsoft Visual C++ runtime available to OR-Tools on Windows.

OR-Tools' abseil_dll.dll needs MSVCP140.dll, which Python does not ship. The 'msvc-runtime' package (installed
from requirements.txt) copies the runtime DLLs into the virtual environment. A venv's python.exe is only a
launcher, so Windows would not look there on its own: we preload the DLLs by full path before OR-Tools is
imported. This works without administrator rights and without the system-wide VC++ Redistributable.
"""
import os
import sys
from pathlib import Path

RUNTIME_DLLS = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
                "msvcp140_atomic_wait.dll", "concrt140.dll", "vcomp140.dll")
_done = False


def candidate_dirs() -> list[Path]:
    dirs = [Path(sys.prefix), Path(sys.prefix) / "Scripts", Path(sys.prefix) / "Library" / "bin",
            Path(sys.base_prefix), Path(sys.executable).parent]
    seen, out = set(), []
    for d in dirs:
        key = str(d).lower()
        if key not in seen and d.is_dir():
            seen.add(key)
            out.append(d)
    return out


def prepare_native_libs() -> list[str]:
    """Preload VC++ runtime DLLs shipped inside the environment. Returns the paths that were loaded."""
    global _done
    loaded: list[str] = []
    if _done or not sys.platform.startswith("win"):
        return loaded
    _done = True
    import ctypes
    dirs = candidate_dirs()
    for d in dirs:
        try:
            os.add_dll_directory(str(d))
        except (OSError, AttributeError):
            pass
    for name in RUNTIME_DLLS:
        for d in dirs:
            path = d / name
            if path.is_file():
                try:
                    ctypes.WinDLL(str(path))
                    loaded.append(str(path))
                except OSError:
                    continue
                break
    return loaded


def ortools_error() -> str | None:
    """None if OR-Tools can be imported, otherwise a short error text."""
    prepare_native_libs()
    try:
        from ortools.sat.python import cp_model  # noqa: F401
        return None
    except (ImportError, OSError) as exc:
        return str(exc)


if __name__ == "__main__":
    error = ortools_error()
    print("OR-Tools OK" if error is None else f"OR-Tools yüklenemedi: {error}")
    sys.exit(0 if error is None else 1)
