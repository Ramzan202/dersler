import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

from app.config import SHORT_DAY_NAMES

BLOCKED = "#E57373"
FREE = "#81C784"
DISABLED = "#BDBDBD"


def show_error(parent, message: str, title: str = "Hata"):
    messagebox.showerror(title, message, parent=parent)


def show_info(parent, message: str, title: str = "Bilgi"):
    messagebox.showinfo(title, message, parent=parent)


def ask_yes_no(parent, message: str, title: str = "Onay") -> bool:
    return messagebox.askyesno(title, message, parent=parent)


def guarded(parent):
    """Decorator for UI callbacks: shows exceptions as a dialog instead of crashing silently."""
    def deco(fn):
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except ValueError as exc:
                show_error(parent() if callable(parent) else parent, str(exc))
            except Exception as exc:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                show_error(parent() if callable(parent) else parent, f"Beklenmeyen hata: {exc}")
        return wrapper
    return deco


def configure_treeview_style(root, scaling: float = 1.0, dark: bool = False):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    bg = "#2B2B2B" if dark else "#FFFFFF"
    fg = "#EEEEEE" if dark else "#1A1A1A"
    head_bg = "#1F4E79"
    sel = "#3B78B5"
    style.configure("Treeview", background=bg, fieldbackground=bg, foreground=fg,
                    rowheight=int(26 * scaling), font=("Segoe UI", int(10 * scaling)), borderwidth=0)
    style.configure("Treeview.Heading", background=head_bg, foreground="#FFFFFF",
                    font=("Segoe UI", int(10 * scaling), "bold"), relief="flat")
    style.map("Treeview", background=[("selected", sel)], foreground=[("selected", "#FFFFFF")])
    style.map("Treeview.Heading", background=[("active", "#2D6AA3")])


class DataTable(ctk.CTkFrame):
    """ttk.Treeview with scrollbars, column sorting and helpers for selected ids."""

    def __init__(self, master, columns: list[tuple[str, str, int]], height: int = 15, selectmode="extended", **kw):
        super().__init__(master, **kw)
        self.columns = columns
        keys = [c[0] for c in columns]
        self.tree = ttk.Treeview(self, columns=keys, show="headings", height=height, selectmode=selectmode)
        for key, label, width in columns:
            self.tree.heading(key, text=label, command=lambda k=key: self._sort(k))
            self.tree.column(key, width=width, minwidth=40, anchor="w")
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._sort_desc = {}
        self.tree.tag_configure("error", foreground="#C62828")
        self.tree.tag_configure("warning", foreground="#EF6C00")
        self.tree.tag_configure("muted", foreground="#888888")

    def set_rows(self, rows: list[tuple]):
        """rows: list of (iid, values[, tag])."""
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            iid, values = row[0], row[1]
            tags = (row[2],) if len(row) > 2 and row[2] else ()
            self.tree.insert("", "end", iid=str(iid), values=values, tags=tags)
        keep = [i for i in selected if self.tree.exists(i)]
        if keep:
            self.tree.selection_set(keep)

    def selected_ids(self) -> list[int]:
        out = []
        for iid in self.tree.selection():
            try:
                out.append(int(iid))
            except ValueError:
                pass
        return out

    def selected_id(self) -> int | None:
        ids = self.selected_ids()
        return ids[0] if ids else None

    def bind_double_click(self, callback):
        self.tree.bind("<Double-1>", lambda _e: callback())

    def _sort(self, key):
        desc = self._sort_desc.get(key, False)
        items = [(self.tree.set(i, key), i) for i in self.tree.get_children("")]

        def conv(v):
            try:
                return (0, float(str(v).replace(",", ".").rstrip("%")))
            except ValueError:
                return (1, str(v).lower())
        items.sort(key=lambda x: conv(x[0]), reverse=desc)
        for idx, (_, iid) in enumerate(items):
            self.tree.move(iid, "", idx)
        self._sort_desc[key] = not desc


class MultiSelect(ctk.CTkFrame):
    def __init__(self, master, items: list[tuple[int, str]], selected=(), height: int = 160, **kw):
        super().__init__(master, **kw)
        self.filter_var = tk.StringVar()
        entry = ctk.CTkEntry(self, placeholder_text="Ara…", textvariable=self.filter_var)
        entry.pack(fill="x", padx=2, pady=(2, 4))
        self.scroll = ctk.CTkScrollableFrame(self, height=height)
        self.scroll.pack(fill="both", expand=True)
        self.vars: dict[int, tk.IntVar] = {}
        self.boxes: dict[int, ctk.CTkCheckBox] = {}
        selected = set(selected)
        for ident, label in items:
            var = tk.IntVar(value=1 if ident in selected else 0)
            box = ctk.CTkCheckBox(self.scroll, text=label, variable=var)
            box.pack(anchor="w", pady=1)
            self.vars[ident] = var
            self.boxes[ident] = box
        self.labels = dict(items)
        self.filter_var.trace_add("write", lambda *_: self._apply_filter())

    def _apply_filter(self):
        text = self.filter_var.get().lower()
        for ident, box in self.boxes.items():
            box.pack_forget()
        for ident, box in self.boxes.items():
            if text in self.labels[ident].lower():
                box.pack(anchor="w", pady=1)

    def get(self) -> list[int]:
        return [i for i, v in self.vars.items() if v.get()]


class DaySelect(ctk.CTkFrame):
    def __init__(self, master, days: list[str], selected=(), **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.vars = []
        selected = set(selected)
        for i, name in enumerate(days):
            var = tk.IntVar(value=1 if i in selected else 0)
            ctk.CTkCheckBox(self, text=name, variable=var, width=20).grid(row=0, column=i, padx=4, sticky="w")
            self.vars.append(var)

    def get(self) -> list[int]:
        return [i for i, v in enumerate(self.vars) if v.get()]


class FormDialog(ctk.CTkToplevel):
    """Generic modal form.

    fields: list of dicts with keys: key, label, kind (text|int|combo|combo_id|check|days|multi|textarea),
    value, options (for combo/combo_id/multi), days (for days), help.
    """

    def __init__(self, master, title: str, fields: list[dict], width: int = 620, height: int = 640,
                 validate=None):
        super().__init__(master)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.minsize(480, 360)
        self.result = None
        self.fields = fields
        self.widgets = {}
        self.validate_fn = validate
        body = ctk.CTkScrollableFrame(self)
        body.pack(fill="both", expand=True, padx=12, pady=(12, 0))
        body.grid_columnconfigure(1, weight=1)
        for row, f in enumerate(fields):
            ctk.CTkLabel(body, text=f["label"], anchor="w", justify="left", wraplength=200).grid(
                row=row, column=0, sticky="nw", padx=(0, 10), pady=5)
            widget = self._make(body, f)
            widget.grid(row=row, column=1, sticky="ew", pady=5)
            self.widgets[f["key"]] = widget
            if f.get("help"):
                ctk.CTkLabel(body, text=f["help"], text_color="gray", font=ctk.CTkFont(size=11), anchor="w",
                             justify="left", wraplength=360).grid(row=row, column=2, sticky="w", padx=(8, 0))
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=12, pady=12)
        ctk.CTkButton(buttons, text="Kaydet", command=self._ok).pack(side="right", padx=4)
        ctk.CTkButton(buttons, text="İptal", fg_color="gray", command=self.destroy).pack(side="right", padx=4)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.transient(master)
        self.after(150, self._focus)

    def _focus(self):
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except tk.TclError:
            pass

    def _make(self, parent, f):
        kind = f.get("kind", "text")
        value = f.get("value")
        if kind in ("text", "int"):
            var = tk.StringVar(value="" if value is None else str(value))
            w = ctk.CTkEntry(parent, textvariable=var)
            w.var = var
            return w
        if kind == "textarea":
            w = ctk.CTkTextbox(parent, height=70)
            w.insert("1.0", value or "")
            return w
        if kind == "combo":
            values = [str(v) for v in f.get("options", [])]
            var = tk.StringVar(value=str(value) if value not in (None, "") else (values[0] if values else ""))
            w = ctk.CTkComboBox(parent, values=values, variable=var, state="normal" if f.get("editable") else "readonly")
            w.var = var
            return w
        if kind == "combo_id":
            options = [(None, "— seçilmedi —")] + list(f.get("options", [])) if f.get("allow_none", True) else list(
                f.get("options", []))
            labels = [lbl for _, lbl in options]
            current = next((lbl for i, lbl in options if i == value), labels[0] if labels else "")
            var = tk.StringVar(value=current)
            w = ctk.CTkComboBox(parent, values=labels, variable=var, state="readonly")
            w.var = var
            w.options = options
            return w
        if kind == "check":
            var = tk.IntVar(value=1 if value else 0)
            w = ctk.CTkCheckBox(parent, text="", variable=var)
            w.var = var
            return w
        if kind == "days":
            return DaySelect(parent, f["days"], value or [])
        if kind == "multi":
            return MultiSelect(parent, f.get("options", []), value or [], height=f.get("height", 140))
        raise ValueError(kind)

    def values(self) -> dict:
        out = {}
        for f in self.fields:
            w = self.widgets[f["key"]]
            kind = f.get("kind", "text")
            if kind == "text":
                out[f["key"]] = w.var.get().strip()
            elif kind == "int":
                text = w.var.get().strip()
                if text == "":
                    out[f["key"]] = f.get("default", 0)
                else:
                    try:
                        out[f["key"]] = int(text)
                    except ValueError:
                        raise ValueError(f"'{f['label']}' alanına bir tam sayı girin.")
            elif kind == "textarea":
                out[f["key"]] = w.get("1.0", "end").strip()
            elif kind == "combo":
                out[f["key"]] = w.var.get()
            elif kind == "combo_id":
                label = w.var.get()
                out[f["key"]] = next((i for i, lbl in w.options if lbl == label), None)
            elif kind == "check":
                out[f["key"]] = int(w.var.get())
            elif kind in ("days", "multi"):
                out[f["key"]] = w.get()
        return out

    def _ok(self):
        try:
            vals = self.values()
            if self.validate_fn:
                self.validate_fn(vals)
        except ValueError as exc:
            show_error(self, str(exc))
            return
        self.result = vals
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result


class AvailabilityDialog(ctk.CTkToplevel):
    """Weekly grid: click a cell to toggle it, click a day header or period label to toggle the whole column/row."""

    def __init__(self, master, title: str, days: list[str], periods: int, blocked: set, period_times=None,
                 note: str = ""):
        super().__init__(master)
        self.title(title)
        self.result = None
        self.days, self.periods = days, periods
        self.blocked = set(blocked)
        self.buttons = {}
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=16, weight="bold")).pack(padx=12, pady=(12, 2),
                                                                                       anchor="w")
        ctk.CTkLabel(self, text=note or "Kırmızı: kapalı (ders konamaz) · Yeşil: müsait. Hücreye tıklayarak "
                                        "değiştirin; gün başlığına veya saat numarasına tıklayarak tüm sütunu/satırı "
                                        "değiştirin.", wraplength=640, justify="left", text_color="gray").pack(
            padx=12, anchor="w")
        grid = ctk.CTkFrame(self)
        grid.pack(padx=12, pady=10)
        period_times = period_times or []
        for d, name in enumerate(days):
            ctk.CTkButton(grid, text=name, width=110, command=lambda d=d: self._toggle_col(d)).grid(
                row=0, column=d + 1, padx=2, pady=2)
        for p in range(periods):
            label = f"{p + 1}. ders" + (f"\n{period_times[p]}" if p < len(period_times) else "")
            ctk.CTkButton(grid, text=label, width=100, fg_color="#455A64",
                          command=lambda p=p: self._toggle_row(p)).grid(row=p + 1, column=0, padx=2, pady=2)
            for d in range(len(days)):
                b = tk.Button(grid, width=12, height=1, relief="flat", command=lambda d=d, p=p: self._toggle(d, p))
                b.grid(row=p + 1, column=d + 1, padx=2, pady=2, sticky="nsew")
                self.buttons[(d, p)] = b
        self._paint()
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(bar, text="Tümünü aç", fg_color="#2E7D32", command=self._clear).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Tümünü kapat", fg_color="#C62828", command=self._fill).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Kaydet", command=self._ok).pack(side="right", padx=4)
        ctk.CTkButton(bar, text="İptal", fg_color="gray", command=self.destroy).pack(side="right", padx=4)
        self.transient(master)
        self.after(150, lambda: (self.lift(), self.grab_set()))

    def _paint(self):
        for (d, p), b in self.buttons.items():
            blocked = (d, p) in self.blocked
            b.configure(bg=BLOCKED if blocked else FREE, activebackground=BLOCKED if blocked else FREE,
                        text="Kapalı" if blocked else "")

    def _toggle(self, d, p):
        self.blocked ^= {(d, p)}
        self._paint()

    def _toggle_col(self, d):
        col = {(d, p) for p in range(self.periods)}
        self.blocked = self.blocked - col if col <= self.blocked else self.blocked | col
        self._paint()

    def _toggle_row(self, p):
        row = {(d, p) for d in range(len(self.days))}
        self.blocked = self.blocked - row if row <= self.blocked else self.blocked | row
        self._paint()

    def _clear(self):
        self.blocked = set()
        self._paint()

    def _fill(self):
        self.blocked = set(self.buttons)
        self._paint()

    def _ok(self):
        self.result = set(self.blocked)
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result


class EntityPage(ctk.CTkFrame):
    """Base page: title, toolbar, search box and table."""

    title = ""
    columns: list[tuple[str, str, int]] = []

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(16, 6))
        ctk.CTkLabel(head, text=self.title, font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        self.count_label = ctk.CTkLabel(head, text="", text_color="gray")
        self.count_label.pack(side="left", padx=12)
        self.search_var = tk.StringVar()
        ctk.CTkEntry(head, placeholder_text="Ara…", width=200, textvariable=self.search_var).pack(side="right")
        self.search_var.trace_add("write", lambda *_: self.refresh())
        self.toolbar = ctk.CTkFrame(self, fg_color="transparent")
        self.toolbar.pack(fill="x", padx=16, pady=(0, 6))
        self.build_toolbar()
        self.table = DataTable(self, self.columns)
        self.table.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.table.bind_double_click(guarded(self)(self.on_edit))

    def tool(self, text, command, color=None):
        kw = {"fg_color": color} if color else {}
        b = ctk.CTkButton(self.toolbar, text=text, command=guarded(self)(command), width=110, **kw)
        b.pack(side="left", padx=(0, 6))
        return b

    def build_toolbar(self):
        self.tool("➕ Ekle", self.on_add)
        self.tool("✏️ Düzenle", self.on_edit)
        self.tool("🗑 Sil", self.on_delete, "#C62828")

    def matches(self, values) -> bool:
        text = self.search_var.get().strip().lower()
        return not text or any(text in str(v).lower() for v in values)

    def refresh(self):
        rows = [r for r in self.load_rows() if self.matches(r[1])]
        self.table.set_rows(rows)
        self.count_label.configure(text=f"{len(rows)} kayıt")

    def load_rows(self) -> list[tuple]:
        return []

    def on_add(self):
        pass

    def on_edit(self):
        pass

    def on_delete(self):
        pass

    def require_selection(self) -> int | None:
        ident = self.table.selected_id()
        if ident is None:
            show_info(self, "Lütfen listeden bir kayıt seçin.")
        return ident
