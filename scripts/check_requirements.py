"""Exit 0 if every dependency from requirements.txt is installed and the file did not change since the last
successful installation; exit 1 otherwise. Uses only the standard library. With --stamp, record the current state."""
import hashlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ = ROOT / "requirements.txt"
STAMP = Path(sys.prefix) / ".req_hash"
MODULES = ["ortools", "customtkinter", "openpyxl", "matplotlib", "reportlab", "tkinter"]


def digest() -> str:
    return hashlib.sha256(REQ.read_bytes()).hexdigest()


def main() -> int:
    if "--stamp" in sys.argv:
        STAMP.write_text(digest(), encoding="ascii")
        return 0
    if not STAMP.exists() or STAMP.read_text(encoding="ascii").strip() != digest():
        return 1
    missing = [m for m in MODULES if importlib.util.find_spec(m) is None]
    if missing:
        print("Eksik kütüphaneler: " + ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
