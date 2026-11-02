import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.problem import Problem
from app.database.models import Entry
from app.utils.colors import subject_color

_FONT = None


def _register_font() -> tuple[str, str]:
    """Register a TrueType font that contains Turkish characters (ş, ğ, ı, İ, ö, ü, ç)."""
    global _FONT
    if _FONT:
        return _FONT
    candidates = []
    windir = os.environ.get("WINDIR", r"C:\Windows")
    candidates.append((Path(windir, "Fonts", "arial.ttf"), Path(windir, "Fonts", "arialbd.ttf")))
    candidates.append((Path(windir, "Fonts", "calibri.ttf"), Path(windir, "Fonts", "calibrib.ttf")))
    try:
        import matplotlib
        base = Path(matplotlib.get_data_path(), "fonts", "ttf")
        candidates.append((base / "DejaVuSans.ttf", base / "DejaVuSans-Bold.ttf"))
    except Exception:
        pass
    candidates.append((Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                       Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")))
    for regular, bold in candidates:
        if regular.exists():
            pdfmetrics.registerFont(TTFont("TRFont", str(regular)))
            pdfmetrics.registerFont(TTFont("TRFont-Bold", str(bold if bold.exists() else regular)))
            _FONT = ("TRFont", "TRFont-Bold")
            return _FONT
    _FONT = ("Helvetica", "Helvetica-Bold")
    return _FONT


def export_pdf(problem: Problem, entries: list[Entry], path: Path | str, mode: str = "class", title: str = "",
               period_times: list[str] | None = None, school_name: str = "") -> Path:
    font, bold = _register_font()
    period_times = period_times or []
    path = Path(path)
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=10 * mm, bottomMargin=10 * mm, title=title or "Ders Programı")
    h_style = ParagraphStyle("h", fontName=bold, fontSize=15, leading=19)
    sub_style = ParagraphStyle("s", fontName=font, fontSize=9, leading=11, textColor=colors.grey)
    cell_style = ParagraphStyle("c", fontName=font, fontSize=7.5, leading=9, alignment=1)
    head_style = ParagraphStyle("hh", fontName=bold, fontSize=9, leading=11, alignment=1, textColor=colors.white)

    if mode == "class":
        objs = sorted(problem.classes.values(), key=lambda c: (c.grade, c.name))
        pred = lambda e, o: e.class_id == o.id  # noqa: E731
        label = "Sınıf"
    elif mode == "teacher":
        objs = sorted(problem.teachers.values(), key=lambda t: t.name)
        pred = lambda e, o: o.id in e.teacher_ids  # noqa: E731
        label = "Öğretmen"
    else:
        objs = sorted(problem.rooms.values(), key=lambda r: r.name)
        pred = lambda e, o: o.id in e.room_ids  # noqa: E731
        label = "Derslik"

    story = []
    page_width = landscape(A4)[0] - 20 * mm
    first_col = 24 * mm
    col_w = (page_width - first_col) / max(1, problem.num_days)
    for obj in objs:
        items = [e for e in entries if pred(e, obj)]
        if not items and mode != "class":
            continue
        if story:
            story.append(PageBreak())
        story.append(Paragraph(f"{label}: {obj.name}", h_style))
        story.append(Paragraph(" · ".join(x for x in (school_name, title, f"Haftalık {len(items)} ders saati") if x),
                               sub_style))
        story.append(Spacer(1, 4 * mm))
        grid = {(e.day, e.period): e for e in items}
        data = [[Paragraph("Saat", head_style)] + [Paragraph(d, head_style) for d in problem.days]]
        style = [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#E8EEF5")),
        ]
        for p in range(problem.periods):
            t = period_times[p] if p < len(period_times) else ""
            row = [Paragraph(f"<b>{p + 1}. ders</b><br/>{t}", cell_style)]
            for d in range(problem.num_days):
                e = grid.get((d, p))
                if e:
                    subj = problem.subjects[e.subject_id].name
                    lines = [f"<b>{subj}</b>"]
                    if mode != "class":
                        lines.insert(0, problem.classes[e.class_id].name)
                    if mode != "teacher":
                        names = [problem.teachers[t].name for t in e.teacher_ids if t in problem.teachers]
                        if names:
                            lines.append(", ".join(names))
                    if mode != "room":
                        rooms = [problem.rooms[r].name for r in e.room_ids if r in problem.rooms]
                        if rooms:
                            lines.append(", ".join(rooms))
                    row.append(Paragraph("<br/>".join(lines), cell_style))
                    style.append(("BACKGROUND", (d + 1, p + 1), (d + 1, p + 1),
                                  colors.HexColor(subject_color(problem.subjects[e.subject_id]))))
                else:
                    row.append("")
            data.append(row)
        avail = 170 * mm
        row_h = min(19 * mm, avail / (problem.periods + 1))
        cell_style.fontSize = 7.5 if problem.periods <= 10 else 6
        cell_style.leading = cell_style.fontSize + 1.5
        heights = [8 * mm] + [row_h] * problem.periods if problem.periods <= 10 else None
        table = Table(data, colWidths=[first_col] + [col_w] * problem.num_days, rowHeights=heights, repeatRows=1)
        table.setStyle(TableStyle(style))
        story.append(table)
    if not story:
        story.append(Paragraph("Programda gösterilecek ders yok.", h_style))
    doc.build(story)
    return path
