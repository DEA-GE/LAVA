"""Documentation browser tab with Markdown rendering support."""

from __future__ import annotations

import re
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Mapping, Optional, Tuple

from PIL import Image, ImageTk

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    yaml = None

try:
    import mistune  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    mistune = None


PARENT_DIR = Path(__file__).resolve().parent.parent


class DocumentationTab(ttk.Frame):
    """Read-only browser for every page in the MkDocs documentation."""

    DOCS_ROOT = PARENT_DIR / "docs"
    MKDOCS_CONFIG = PARENT_DIR / "mkdocs.yml"
    ONLINE_DOCS_ROOT = "https://lava-tool.readthedocs.io/en/latest/"

    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master)
        self.document_paths: Dict[str, Path] = {}
        self.current_document: Optional[Path] = None
        self.document_title_var = tk.StringVar(value="Documentation")
        self.document_path_var = tk.StringVar(value="")
        self.document_link_counter = 0
        self.document_images: List[Any] = []
        self.document_table_widgets: List[tk.Widget] = []

        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(10, 8, 10, 6))
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            textvariable=self.document_title_var,
            font=("Segoe UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            textvariable=self.document_path_var,
            foreground="#666666",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Button(
            header,
            text="Open Markdown file",
            command=self._open_selected_document,
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 0))
        ttk.Button(
            header,
            text="Open online documentation",
            command=self._open_online_documentation,
        ).grid(row=0, column=2, rowspan=2, sticky="e", padx=(8, 0))

        navigation = ttk.LabelFrame(self, text="Documents", padding=6)
        navigation.grid(row=1, column=0, sticky="ns", padx=(10, 4), pady=(0, 10))
        navigation.rowconfigure(0, weight=1)
        navigation.columnconfigure(0, weight=1)
        self.document_tree = ttk.Treeview(
            navigation,
            show="tree",
            selectmode="browse",
        )
        self.document_tree.column("#0", width=250, minwidth=180, stretch=True)
        self.document_tree.grid(row=0, column=0, sticky="nsew")
        navigation_scroll = ttk.Scrollbar(
            navigation, orient="vertical", command=self.document_tree.yview
        )
        navigation_scroll.grid(row=0, column=1, sticky="ns")
        self.document_tree.configure(yscrollcommand=navigation_scroll.set)
        self.document_tree.bind("<<TreeviewSelect>>", self._on_document_selected)

        content = ttk.Frame(self)
        content.grid(row=1, column=1, sticky="nsew", padx=(4, 10), pady=(0, 10))
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        self.document_text = tk.Text(
            content,
            wrap="word",
            state="disabled",
            font=("Segoe UI", 10),
            padx=14,
            pady=12,
        )
        self.document_text.grid(row=0, column=0, sticky="nsew")
        content_scroll = ttk.Scrollbar(
            content, orient="vertical", command=self.document_text.yview
        )
        content_scroll.grid(row=0, column=1, sticky="ns")
        self.document_text.configure(yscrollcommand=content_scroll.set)

        first_document = self._populate_document_tree()
        if first_document:
            self.document_tree.selection_set(first_document)
            self.document_tree.focus(first_document)
            self.document_tree.see(first_document)
            self._display_document(first_document)
        else:
            self._set_document_text("No Markdown documentation files were found.")

    @classmethod
    def _documentation_entries(cls) -> List[Tuple[Tuple[str, ...], str, Path]]:
        """Return MkDocs navigation entries followed by any unlisted pages."""
        entries: List[Tuple[Tuple[str, ...], str, Path]] = []
        listed_paths: set[Path] = set()

        def visit_navigation(items: Any, parents: Tuple[str, ...] = ()) -> None:
            if not isinstance(items, list):
                return
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                for title, destination in item.items():
                    if isinstance(destination, str) and destination.endswith(".md"):
                        path = (cls.DOCS_ROOT / destination).resolve()
                        if path.is_file():
                            entries.append((parents, str(title), path))
                            listed_paths.add(path)
                    elif isinstance(destination, list):
                        visit_navigation(destination, parents + (str(title),))

        if yaml is not None and cls.MKDOCS_CONFIG.is_file():
            try:
                config = yaml.safe_load(
                    cls.MKDOCS_CONFIG.read_text(encoding="utf-8")
                ) or {}
                if isinstance(config, Mapping):
                    visit_navigation(config.get("nav", []))
            except (OSError, ValueError, yaml.YAMLError):
                pass

        for path in sorted(cls.DOCS_ROOT.rglob("*.md")):
            resolved = path.resolve()
            if resolved in listed_paths:
                continue
            relative = path.relative_to(cls.DOCS_ROOT)
            parents = tuple(
                part.replace("_", " ").title() for part in relative.parts[:-1]
            )
            title = path.stem.replace("_", " ").title()
            entries.append((parents or ("Other",), title, resolved))
        return entries

    def _populate_document_tree(self) -> Optional[str]:
        parent_nodes: Dict[Tuple[str, ...], str] = {}
        first_document: Optional[str] = None
        for parents, title, path in self._documentation_entries():
            parent_id = ""
            accumulated: Tuple[str, ...] = ()
            for category in parents:
                accumulated += (category,)
                if accumulated not in parent_nodes:
                    parent_nodes[accumulated] = self.document_tree.insert(
                        parent_id,
                        "end",
                        text=category,
                        open=True,
                    )
                parent_id = parent_nodes[accumulated]
            relative = path.relative_to(self.DOCS_ROOT.resolve()).as_posix()
            item_id = f"document:{relative}"
            self.document_tree.insert(parent_id, "end", iid=item_id, text=title)
            self.document_paths[item_id] = path
            if first_document is None or relative == "index.md":
                first_document = item_id
        return first_document

    def _on_document_selected(self, _event: tk.Event) -> None:
        selection = self.document_tree.selection()
        if selection and selection[0] in self.document_paths:
            self._display_document(selection[0])

    def _display_document(self, item_id: str) -> None:
        path = self.document_paths.get(item_id)
        if path is None:
            return
        self.current_document = path
        self.document_title_var.set(self.document_tree.item(item_id, "text"))
        self.document_path_var.set(path.relative_to(PARENT_DIR).as_posix())
        self._load_document(self.document_text, path)

    def _set_document_text(self, content: str) -> None:
        self.document_text.configure(state="normal")
        self.document_text.delete("1.0", "end")
        self.document_text.insert("end", content)
        self.document_text.configure(state="disabled")

    @staticmethod
    def _prepare_markdown(content: str) -> str:
        """Normalize MkDocs-only syntax before parsing it as Markdown."""
        if content.startswith("---"):
            lines = content.splitlines()
            if lines and lines[0].strip() == "---":
                try:
                    closing = next(
                        index
                        for index, line in enumerate(lines[1:], start=1)
                        if line.strip() == "---"
                    )
                except StopIteration:
                    closing = -1
                if closing >= 0:
                    content = "\n".join(lines[closing + 1 :])

        # Image sizing attributes are understood by MkDocs but otherwise show
        # up as literal text in a generic Markdown parser.
        content = re.sub(
            r"(!\[[^\]]*\]\([^\n)]+\))\s*\{[^\n}]*\}", r"\1", content
        )

        # Convert MkDocs admonitions into block quotes while retaining their
        # title, formatted content, links, and lists.
        source_lines = content.splitlines()
        converted: List[str] = []
        index = 0
        while index < len(source_lines):
            line = source_lines[index]
            match = re.match(
                r'^!!!\s+([A-Za-z0-9_-]+)(?:\s+["\'](.+?)["\'])?\s*$', line
            )
            if not match:
                converted.append(line)
                index += 1
                continue
            kind = match.group(1).replace("_", " ").title()
            title = match.group(2) or kind
            converted.extend((f"> **{title}**", ">"))
            index += 1
            while index < len(source_lines):
                nested = source_lines[index]
                if nested.startswith("    "):
                    converted.append("> " + nested[4:])
                    index += 1
                    continue
                if not nested.strip():
                    converted.append(">")
                    index += 1
                    continue
                break
        return "\n".join(converted)

    @staticmethod
    def _plain_markdown_text(nodes: Any) -> str:
        if isinstance(nodes, list):
            return "".join(DocumentationTab._plain_markdown_text(node) for node in nodes)
        if not isinstance(nodes, Mapping):
            return str(nodes or "")
        node_type = str(nodes.get("type", ""))
        if node_type in {"softbreak", "linebreak"}:
            return " "
        if node_type == "inline_html":
            raw = str(nodes.get("raw", ""))
            return "\n" if re.fullmatch(r"<br\s*/?>", raw, re.IGNORECASE) else ""
        if "raw" in nodes:
            return str(nodes.get("raw", ""))
        return DocumentationTab._plain_markdown_text(nodes.get("children", []))

    @staticmethod
    def _markdown_link_target(nodes: Any) -> Optional[str]:
        for node in nodes if isinstance(nodes, list) else [nodes]:
            if not isinstance(node, Mapping):
                continue
            if node.get("type") == "link":
                target = str(node.get("attrs", {}).get("url", "")).strip()
                if target:
                    return target
            nested = DocumentationTab._markdown_link_target(node.get("children", []))
            if nested:
                return nested
        return None

    def _configure_document_tags(self, widget: tk.Text) -> None:
        widget.tag_configure(
            "h1", font=("Segoe UI", 18, "bold"), spacing1=4, spacing3=12
        )
        widget.tag_configure(
            "h2", font=("Segoe UI", 14, "bold"), spacing1=14, spacing3=7
        )
        widget.tag_configure(
            "h3", font=("Segoe UI", 11, "bold"), spacing1=11, spacing3=5
        )
        widget.tag_configure(
            "h4", font=("Segoe UI", 10, "bold"), spacing1=8, spacing3=4
        )
        widget.tag_configure("strong", font=("Segoe UI", 10, "bold"))
        widget.tag_configure("emphasis", font=("Segoe UI", 10, "italic"))
        widget.tag_configure(
            "inline_code",
            font=("Consolas", 9),
            background="#EEF1F4",
            foreground="#8B1E3F",
        )
        widget.tag_configure(
            "code_block",
            font=("Consolas", 9),
            background="#F1F3F5",
            lmargin1=16,
            lmargin2=16,
            rmargin=12,
            spacing1=6,
            spacing3=8,
        )
        widget.tag_configure(
            "quote",
            background="#EEF5FA",
            foreground="#34495E",
            lmargin1=18,
            lmargin2=18,
            rmargin=12,
            spacing1=5,
            spacing3=7,
        )
        widget.tag_configure(
            "list", lmargin1=20, lmargin2=38, spacing1=2, spacing3=2
        )
        widget.tag_configure(
            "table", font=("Consolas", 9), background="#F7F8FA", spacing1=2
        )
        widget.tag_configure(
            "table_head",
            font=("Consolas", 9, "bold"),
            background="#E5EAF0",
            spacing1=3,
            spacing3=3,
        )
        widget.tag_configure("link", foreground="#0D5D9B", underline=True)
        widget.tag_configure("caption", foreground="#666666", justify="center")

    def _insert_document_link(
        self,
        widget: tk.Text,
        children: Any,
        target: str,
        source_path: Path,
        inherited_tags: Tuple[str, ...],
    ) -> None:
        self.document_link_counter += 1
        link_tag = f"documentation_link_{self.document_link_counter}"
        self._render_markdown_inline(
            widget,
            children,
            source_path,
            inherited_tags + ("link", link_tag),
        )
        widget.tag_bind(
            link_tag,
            "<Button-1>",
            lambda _event, destination=target, source=source_path: (
                self._open_document_link(destination, source)
            ),
        )
        widget.tag_bind(
            link_tag,
            "<Enter>",
            lambda _event, target_widget=widget: target_widget.configure(cursor="hand2"),
        )
        widget.tag_bind(
            link_tag,
            "<Leave>",
            lambda _event, target_widget=widget: target_widget.configure(cursor=""),
        )

    def _insert_document_image(
        self, widget: tk.Text, node: Mapping[str, Any], source_path: Path
    ) -> None:
        target = str(node.get("attrs", {}).get("url", "")).strip()
        alt_text = self._plain_markdown_text(node.get("children", [])).strip()
        if target.startswith(("http://", "https://")):
            self._insert_document_link(
                widget,
                [{"type": "text", "raw": alt_text or target}],
                target,
                source_path,
                (),
            )
            return
        image_path = (source_path.parent / target.split("#", 1)[0]).resolve()
        try:
            with Image.open(image_path) as source_image:
                display_image = source_image.copy()
            display_image.thumbnail((720, 430), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(display_image)
            self.document_images.append(photo)
            widget.image_create("end", image=photo)
            widget.insert("end", "\n")
            if alt_text:
                widget.insert("end", alt_text + "\n", ("caption",))
        except (OSError, tk.TclError):
            widget.insert("end", f"[Image unavailable: {alt_text or target}]", ("emphasis",))

    def _render_markdown_inline(
        self,
        widget: tk.Text,
        nodes: Any,
        source_path: Path,
        inherited_tags: Tuple[str, ...] = (),
    ) -> None:
        for node in nodes if isinstance(nodes, list) else [nodes]:
            if not isinstance(node, Mapping):
                widget.insert("end", str(node), inherited_tags)
                continue
            node_type = str(node.get("type", ""))
            children = node.get("children", [])
            if node_type == "text":
                widget.insert("end", str(node.get("raw", "")), inherited_tags)
            elif node_type == "softbreak":
                widget.insert("end", " ", inherited_tags)
            elif node_type == "linebreak":
                widget.insert("end", "\n", inherited_tags)
            elif node_type == "codespan":
                widget.insert(
                    "end", str(node.get("raw", "")), inherited_tags + ("inline_code",)
                )
            elif node_type == "strong":
                self._render_markdown_inline(
                    widget, children, source_path, inherited_tags + ("strong",)
                )
            elif node_type == "emphasis":
                self._render_markdown_inline(
                    widget, children, source_path, inherited_tags + ("emphasis",)
                )
            elif node_type == "link":
                self._insert_document_link(
                    widget,
                    children,
                    str(node.get("attrs", {}).get("url", "")),
                    source_path,
                    inherited_tags,
                )
            elif node_type == "image":
                self._insert_document_image(widget, node, source_path)
            elif node_type == "inline_html":
                raw = str(node.get("raw", ""))
                if re.fullmatch(r"<br\s*/?>", raw, re.IGNORECASE):
                    widget.insert("end", "\n", inherited_tags)
                else:
                    plain = re.sub(r"<[^>]+>", "", raw)
                    if plain:
                        widget.insert("end", plain, inherited_tags)
            else:
                self._render_markdown_inline(widget, children, source_path, inherited_tags)

    def _render_markdown_list(
        self,
        widget: tk.Text,
        node: Mapping[str, Any],
        source_path: Path,
        depth: int = 0,
    ) -> None:
        ordered = bool(node.get("attrs", {}).get("ordered"))
        for index, item in enumerate(node.get("children", []), start=1):
            prefix = f"{index}. " if ordered else "• "
            widget.insert("end", "    " * depth + prefix, ("list",))
            children = item.get("children", []) if isinstance(item, Mapping) else []
            nested_lists: List[Mapping[str, Any]] = []
            for child in children:
                if child.get("type") == "list":
                    nested_lists.append(child)
                elif child.get("type") in {"block_text", "paragraph"}:
                    self._render_markdown_inline(
                        widget, child.get("children", []), source_path, ("list",)
                    )
                else:
                    self._render_markdown_nodes(widget, [child], source_path)
            widget.insert("end", "\n")
            for nested in nested_lists:
                self._render_markdown_list(widget, nested, source_path, depth + 1)
        if depth == 0:
            widget.insert("end", "\n")

    def _render_markdown_table(
        self, widget: tk.Text, node: Mapping[str, Any], source_path: Path
    ) -> None:
        rows: List[Tuple[bool, List[Mapping[str, Any]]]] = []
        for section in node.get("children", []):
            section_type = section.get("type")
            if section_type == "table_head":
                rows.append((True, list(section.get("children", []))))
            elif section_type == "table_body":
                for row in section.get("children", []):
                    rows.append((False, list(row.get("children", []))))
        if not rows:
            return

        column_count = max(len(cells) for _, cells in rows)
        column_scores: List[int] = []
        for column in range(column_count):
            longest = max(
                (
                    len(
                        self._plain_markdown_text(cells[column].get("children", []))
                    )
                    for _, cells in rows
                    if column < len(cells)
                ),
                default=8,
            )
            column_scores.append(max(8, min(42, longest)))
        available_width = 760
        score_total = max(1, sum(column_scores))
        column_widths = [
            max(90, int(available_width * score / score_total))
            for score in column_scores
        ]

        border_color = "#C9D1D9"
        table_frame = tk.Frame(widget, background=border_color, borderwidth=1)
        self.document_table_widgets.append(table_frame)
        for row_index, (is_header, cells) in enumerate(rows):
            for column in range(column_count):
                cell = cells[column] if column < len(cells) else {}
                children = cell.get("children", []) if isinstance(cell, Mapping) else []
                cell_text = self._plain_markdown_text(children).strip()
                background = "#E5EAF0" if is_header else (
                    "#FFFFFF" if row_index % 2 else "#F7F8FA"
                )
                target = self._markdown_link_target(children)
                cell_label = tk.Label(
                    table_frame,
                    text=cell_text,
                    justify="left",
                    anchor="nw",
                    wraplength=max(70, column_widths[column] - 16),
                    width=1,
                    background=background,
                    foreground="#0D5D9B" if target else "#24292F",
                    font=(
                        "Segoe UI",
                        9,
                        "bold" if is_header else ("underline" if target else "normal"),
                    ),
                    padx=7,
                    pady=5,
                    borderwidth=1,
                    relief="solid",
                )
                cell_label.grid(row=row_index, column=column, sticky="nsew")
                table_frame.columnconfigure(
                    column, minsize=column_widths[column], weight=column_scores[column]
                )
                if target:
                    cell_label.configure(cursor="hand2")
                    cell_label.bind(
                        "<Button-1>",
                        lambda _event, destination=target, source=source_path: (
                            self._open_document_link(destination, source)
                        ),
                    )
        widget.window_create("end", window=table_frame, padx=2, pady=6)
        widget.insert("end", "\n")
        widget.insert("end", "\n")

    def _render_markdown_nodes(
        self,
        widget: tk.Text,
        nodes: Any,
        source_path: Path,
        block_tags: Tuple[str, ...] = (),
    ) -> None:
        for node in nodes if isinstance(nodes, list) else [nodes]:
            if not isinstance(node, Mapping):
                continue
            node_type = str(node.get("type", ""))
            children = node.get("children", [])
            if node_type == "heading":
                level = min(4, max(1, int(node.get("attrs", {}).get("level", 1))))
                self._render_markdown_inline(
                    widget, children, source_path, block_tags + (f"h{level}",)
                )
                widget.insert("end", "\n", block_tags + (f"h{level}",))
            elif node_type in {"paragraph", "block_text"}:
                self._render_markdown_inline(widget, children, source_path, block_tags)
                widget.insert("end", "\n\n" if node_type == "paragraph" else "", block_tags)
            elif node_type == "block_code":
                raw = str(node.get("raw", "")).rstrip()
                widget.insert("end", raw + "\n", block_tags + ("code_block",))
                widget.insert("end", "\n")
            elif node_type == "list":
                self._render_markdown_list(widget, node, source_path)
            elif node_type == "block_quote":
                self._render_markdown_nodes(
                    widget, children, source_path, block_tags + ("quote",)
                )
            elif node_type == "table":
                self._render_markdown_table(widget, node, source_path)
            elif node_type == "thematic_break":
                widget.insert("end", "────────────────────────────────────────\n\n")
            elif node_type == "image":
                self._insert_document_image(widget, node, source_path)
                widget.insert("end", "\n")
            elif node_type == "blank_line":
                continue
            else:
                self._render_markdown_inline(widget, children, source_path, block_tags)

    def _load_document(self, widget: tk.Text, path: Path) -> None:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            content = f"Documentation could not be loaded:\n{exc}"
        widget.configure(state="normal")
        for table_widget in self.document_table_widgets:
            try:
                if table_widget.winfo_exists():
                    table_widget.destroy()
            except tk.TclError:
                pass
        widget.delete("1.0", "end")
        self.document_images = []
        self.document_table_widgets = []
        self.document_link_counter = 0
        self._configure_document_tags(widget)
        prepared = self._prepare_markdown(content)
        if mistune is None:
            widget.insert("end", prepared)
        else:
            parser = mistune.create_markdown(
                renderer="ast", plugins=["table", "strikethrough", "url"]
            )
            try:
                nodes = parser(prepared)
                self._render_markdown_nodes(widget, nodes, path)
            except Exception as exc:
                widget.insert(
                    "end",
                    f"Markdown formatting could not be rendered ({exc}).\n\n{prepared}",
                )
        widget.configure(state="disabled")

    def _open_document_link(self, target: str, source_path: Path) -> None:
        clean_target = target.strip()
        if not clean_target:
            return
        if clean_target.startswith(("http://", "https://", "mailto:")):
            webbrowser.open_new_tab(clean_target)
            return
        relative_target = clean_target.split("#", 1)[0]
        if not relative_target:
            return
        destination = (source_path.parent / relative_target).resolve()
        if destination.suffix.lower() == ".md":
            selected = next(
                (
                    item_id
                    for item_id, path in self.document_paths.items()
                    if path.resolve() == destination
                ),
                None,
            )
            if selected:
                self.document_tree.selection_set(selected)
                self.document_tree.focus(selected)
                self.document_tree.see(selected)
                self._display_document(selected)
                return
        if destination.exists():
            webbrowser.open_new_tab(destination.as_uri())
            return
        messagebox.showwarning(
            "Documentation",
            f"Linked documentation resource was not found:\n{destination}",
            parent=self,
        )

    def _open_selected_document(self) -> None:
        path = self.current_document
        if path is None:
            messagebox.showwarning(
                "Documentation", "Select a document first.", parent=self
            )
            return
        if not path.is_file():
            messagebox.showerror(
                "Documentation",
                f"Documentation file not found:\n{path}",
                parent=self,
            )
            return
        webbrowser.open_new_tab(path.resolve().as_uri())

    def _open_online_documentation(self) -> None:
        path = self.current_document
        if path is None:
            url = self.ONLINE_DOCS_ROOT
        else:
            relative = path.relative_to(self.DOCS_ROOT.resolve()).with_suffix("")
            page = relative.as_posix().strip("/")
            if page == "index":
                page = ""
            url = self.ONLINE_DOCS_ROOT.rstrip("/") + "/"
            if page:
                url += page + "/"
        try:
            webbrowser.open_new_tab(url)
        except Exception as exc:
            messagebox.showerror(
                "Documentation",
                f"Could not open the online documentation:\n{exc}",
                parent=self,
            )

