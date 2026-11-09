"""Reusable Tkinter widgets used across the LAVA interface."""

from __future__ import annotations

import keyword
import re
import tkinter as tk
from typing import Any, Dict, List, Optional, Tuple


class Tooltip:
    """Small delayed tooltip for longer setting descriptions."""

    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text = text.strip()
        self.delay_ms = delay_ms
        self._after_id: Optional[str] = None
        self._window: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _event: Optional[tk.Event] = None) -> None:
        self._cancel()
        if self.text:
            self._after_id = self.widget.after(self.delay_ms, self._show)

    def _show(self) -> None:
        self._after_id = None
        if not self.widget.winfo_exists() or self._window is not None:
            return
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.attributes("-topmost", True)
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        window.geometry(f"+{x}+{y}")
        tk.Label(
            window,
            text=self.text,
            background="#FFFCE8",
            foreground="#202020",
            relief="solid",
            borderwidth=1,
            justify="left",
            wraplength=420,
            padx=7,
            pady=5,
        ).pack()
        self._window = window

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _hide(self, _event: Optional[tk.Event] = None) -> None:
        self._cancel()
        if self._window is not None:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
            self._window = None


class TextSyntaxHighlighter:
    """Lightweight syntax highlighting for Tkinter ``Text`` widgets."""

    _TAG_STYLES: Dict[str, Dict[str, Any]] = {
        "comment": {"foreground": "#6A9955"},
        "keyword": {"foreground": "#C586C0"},
        "string": {"foreground": "#CE9178"},
        "number": {"foreground": "#B5CEA8"},
        "key": {"foreground": "#2F7ACC"},
        "boolean": {"foreground": "#4FC1FF"},
        "decorator": {"foreground": "#DCDCAA"},
    }
    _PY_KEYWORD_PATTERN = re.compile(
        r"\b(?:" + "|".join(sorted(re.escape(word) for word in keyword.kwlist)) + r")\b"
    )
    _PY_STRING_PATTERN = re.compile(
        r"""('''.*?'''|\"\"\".*?\"\"\"|'[^'\\]*(?:\\.[^'\\]*)*'|\"[^\"\\]*(?:\\.[^\"\\]*)*\")""",
        re.DOTALL,
    )
    _YAML_STRING_PATTERN = re.compile(r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""")
    _LANGUAGE_RULES: Dict[str, List[Tuple[str, re.Pattern[str], int]]] = {
        "yaml": [
            ("comment", re.compile(r"#.*", re.MULTILINE), 0),
            ("key", re.compile(r"(?m)^\s*([^:\n]+)(?=\s*:)"), 1),
            ("string", _YAML_STRING_PATTERN, 0),
            ("boolean", re.compile(r"(?i)\b(?:true|false|yes|no|null|on|off)\b"), 0),
            ("number", re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?"), 0),
        ],
        "python": [
            ("comment", re.compile(r"#.*", re.MULTILINE), 0),
            ("decorator", re.compile(r"(?m)^\s*@[\w\.]+"), 0),
            ("string", _PY_STRING_PATTERN, 0),
            ("keyword", _PY_KEYWORD_PATTERN, 0),
            ("number", re.compile(r"\b\d+(?:\.\d+)?\b"), 0),
        ],
        "plain": [],
    }
    _DEBOUNCE_MS = 120

    def __init__(self, widget: tk.Text, language: str = "plain") -> None:
        self.widget = widget
        self.language = language if language in self._LANGUAGE_RULES else "plain"
        self._after_id: Optional[str] = None
        self._configured_tags: set[str] = set()
        self._setup_tags()
        for sequence in (
            "<KeyRelease>",
            "<<Paste>>",
            "<<Cut>>",
            "<<Undo>>",
            "<<Redo>>",
        ):
            widget.bind(sequence, self._schedule_refresh, add="+")
        widget.bind("<FocusIn>", self._schedule_refresh, add="+")
        widget.bind("<Expose>", self._schedule_refresh, add="+")
        widget.bind("<Destroy>", self._on_destroy, add="+")
        self.refresh()

    def refresh(self) -> None:
        if not self.widget.winfo_exists():
            return
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self._apply_highlight()

    def _setup_tags(self) -> None:
        for tag_name, options in self._TAG_STYLES.items():
            self.widget.tag_configure(tag_name, **options)
            self._configured_tags.add(tag_name)

    def _schedule_refresh(self, _event: Optional[tk.Event] = None) -> None:
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = self.widget.after(self._DEBOUNCE_MS, self._apply_highlight)

    def _apply_highlight(self) -> None:
        if not self.widget.winfo_exists():
            return
        rules = self._LANGUAGE_RULES.get(self.language, [])
        text = self.widget.get("1.0", "end-1c")
        for tag in self._configured_tags:
            self.widget.tag_remove(tag, "1.0", "end")
        if not text or not rules:
            return
        for tag, pattern, group in rules:
            for match in pattern.finditer(text):
                start_offset = match.start(group)
                end_offset = match.end(group)
                if start_offset == -1 or end_offset == -1:
                    continue
                start_index = f"1.0+{start_offset}c"
                end_index = f"1.0+{end_offset}c"
                self.widget.tag_add(tag, start_index, end_index)

    def _on_destroy(self, _event: Optional[tk.Event] = None) -> None:
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

