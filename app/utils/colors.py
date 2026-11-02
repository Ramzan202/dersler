from app.config import SUBJECT_PALETTE


def subject_color(subject) -> str:
    if subject is None:
        return "#FFFFFF"
    if getattr(subject, "color", ""):
        return subject.color
    return SUBJECT_PALETTE[(subject.id or 0) % len(SUBJECT_PALETTE)]


def text_color_for(bg: str) -> str:
    bg = bg.lstrip("#")
    if len(bg) != 6:
        return "#000000"
    r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#FFFFFF"
