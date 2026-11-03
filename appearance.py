"""Consistent ttk palettes for the native light and dark interfaces."""

import sys
from tkinter import ttk

PALETTES = {
    "light": dict(
        bg="#f4f6fb",
        panel="#ffffff",
        field="#ffffff",
        text="#17243b",
        muted="#66758d",
        border="#dce3ef",
        hover="#e8edf8",
        accent="#5260e8",
        pressed="#3c49c8",
        selected="#e2e6ff",
        disabled="#8d99ad",
        stripe="#f8faff",
    ),
    "dark": dict(
        bg="#101521",
        panel="#1a2232",
        field="#202b3e",
        text="#edf2fb",
        muted="#a1aec4",
        border="#34415a",
        hover="#2b3850",
        accent="#8a97ff",
        pressed="#6f7ded",
        selected="#34416b",
        disabled="#8995aa",
        stripe="#1e283a",
    ),
}


def titlebar(window, dark):
    if sys.platform == "win32":
        try:
            import ctypes

            window.update_idletasks()
            handle = ctypes.windll.user32.GetParent(window.winfo_id())
            value = ctypes.c_int(int(dark))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                handle, 20, ctypes.byref(value), ctypes.sizeof(value)
            )
        except (AttributeError, OSError):
            pass


def apply_theme(root, theme):
    p = PALETTES[theme]
    style = ttk.Style(root)
    if style.theme_use() != "clam":
        style.theme_use("clam")
    root.configure(background=p["bg"])
    style.configure(
        ".",
        font=("Segoe UI", 10),
        background=p["bg"],
        foreground=p["text"],
        bordercolor=p["border"],
        lightcolor=p["border"],
        darkcolor=p["border"],
        focuscolor=p["accent"],
    )
    style.configure("TFrame", background=p["bg"])
    style.configure("TLabel", background=p["bg"], foreground=p["text"])
    style.configure("Muted.TLabel", foreground=p["muted"])
    style.configure("Title.TLabel", font=("Segoe UI", 25, "bold"))
    style.configure(
        "TButton",
        padding=(12, 9),
        background=p["panel"],
        foreground=p["text"],
        borderwidth=1,
        relief="flat",
        focusthickness=2,
        focuscolor=p["accent"],
    )
    style.map(
        "TButton",
        background=[("disabled", p["bg"]), ("pressed", p["border"]), ("active", p["hover"])],
        foreground=[("disabled", p["disabled"])],
        bordercolor=[("focus", p["accent"])],
    )
    style.configure(
        "Accent.TButton",
        background=p["accent"],
        foreground="#101521" if theme == "dark" else "#ffffff",
        borderwidth=0,
        font=("Segoe UI", 10, "bold"),
    )
    style.map(
        "Accent.TButton",
        background=[("disabled", p["border"]), ("pressed", p["pressed"]), ("active", p["pressed"])],
        foreground=[("disabled", p["disabled"]), ("active", "#ffffff")],
    )
    for widget in ("TEntry", "TCombobox"):
        style.configure(
            widget,
            padding=7,
            fieldbackground=p["field"],
            background=p["panel"],
            foreground=p["text"],
            insertcolor=p["text"],
            arrowcolor=p["muted"],
            borderwidth=1,
        )
        style.map(
            widget,
            fieldbackground=[("disabled", p["bg"]), ("readonly", p["field"])],
            foreground=[("disabled", p["disabled"]), ("readonly", p["text"])],
            selectbackground=[("!disabled", p["selected"])],
            selectforeground=[("!disabled", p["text"])],
            bordercolor=[("focus", p["accent"])],
            arrowcolor=[("disabled", p["disabled"])],
        )
    style.configure(
        "TCheckbutton",
        padding=(0, 6),
        background=p["bg"],
        foreground=p["text"],
        indicatorbackground=p["field"],
        indicatormargin=6,
        indicatorforeground=p["accent"],
    )
    style.map(
        "TCheckbutton",
        background=[("active", p["bg"])],
        foreground=[("disabled", p["disabled"])],
        indicatorbackground=[("selected", p["accent"]), ("active", p["hover"])],
    )
    style.configure(
        "Treeview",
        rowheight=34,
        font=("Segoe UI", 10),
        background=p["panel"],
        fieldbackground=p["panel"],
        foreground=p["text"],
        borderwidth=1,
        relief="flat",
    )
    style.map(
        "Treeview", background=[("selected", p["selected"])], foreground=[("selected", p["text"])]
    )
    style.configure(
        "Treeview.Heading",
        padding=(12, 10),
        font=("Segoe UI", 10, "bold"),
        background=p["panel"],
        foreground=p["muted"],
        relief="flat",
    )
    style.map("Treeview.Heading", background=[("active", p["hover"])])
    style.configure(
        "Vertical.TScrollbar",
        background=p["border"],
        troughcolor=p["panel"],
        borderwidth=0,
        arrowsize=12,
        arrowcolor=p["muted"],
    )
    style.map("Vertical.TScrollbar", background=[("active", p["muted"])])
    style.configure(
        "Horizontal.TProgressbar",
        background=p["accent"],
        troughcolor=p["border"],
        borderwidth=0,
        thickness=6,
    )
    for option, value in {
        "background": p["field"],
        "foreground": p["text"],
        "selectBackground": p["selected"],
        "selectForeground": p["text"],
        "font": ("Segoe UI", 10),
    }.items():
        root.option_add("*TCombobox*Listbox." + option, value)
    titlebar(root, theme == "dark")
    return p
