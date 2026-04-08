from __future__ import annotations

import csv
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any
from urllib.parse import urlparse

from config import (
    APP_STATE_PATH,
    APPLICATION_PIPELINE_PATH,
    DATA_DIR,
    PROFILE_PATH,
    REPORTS_DIR,
    RESUMES_DIR,
    RUN_HISTORY_PATH,
    SCREENSHOTS_DIR,
)
from core.browser import BrowserSession
from core.job_search import JobSearchEngine
from core.profile_store import ProfileStore
from flows.easy_apply import EasyApplyFlow
from flows.external_apply import ExternalApplyFlow


def _clean_user_path(raw: str) -> str:
    text = (raw or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    text = text.strip('"').strip("'")
    text = os.path.expandvars(text)
    if text.lower().startswith("file://"):
        text = text[7:]
    return text


def _resolve_existing_resume_path(path_text: str) -> Path | None:
    cleaned = _clean_user_path(path_text)
    if not cleaned:
        return None

    primary = Path(cleaned).expanduser()
    candidates = [primary]
    if not primary.is_absolute():
        candidates.append((Path.cwd() / primary).resolve())
    candidates.append((RESUMES_DIR / primary.name).resolve())

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    return None


class ChoiceDialog(simpledialog.Dialog):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        prompt: str,
        choices: list[tuple[str, str]],
    ) -> None:
        self.prompt = prompt
        self.choices = choices
        self.result: str | None = None
        self._choice_var = tk.StringVar(value=(choices[0][0] if choices else ""))
        super().__init__(parent, title)

    def body(self, master: tk.Misc) -> ttk.Widget:
        ttk.Label(master, text=self.prompt, wraplength=520, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))
        frame = ttk.Frame(master)
        frame.pack(fill=tk.BOTH, expand=True)
        self.listbox = tk.Listbox(frame, height=min(10, max(4, len(self.choices))), width=90, exportselection=False)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.configure(yscrollcommand=scrollbar.set)

        for _, label in self.choices:
            self.listbox.insert(tk.END, label)
        if self.choices:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
        self.listbox.bind("<Double-Button-1>", lambda _event: self.ok())
        return self.listbox

    def apply(self) -> None:
        selection = self.listbox.curselection()
        if not selection:
            self.result = None
            return
        index = selection[0]
        self.result = self.choices[index][0]


class JobBotApp:
    HISTORY_LIMIT = 20
    PIPELINE_LIMIT = 100

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Job Bot Control Center")
        self.root.geometry("1180x760")
        self.root.minsize(1060, 680)

        self.profile_var = tk.StringVar(value=str(PROFILE_PATH))
        self.resume_var = tk.StringVar(value="")
        self.role_var = tk.StringVar(value="")
        self.role_options: list[str] = []
        self.company_var = tk.StringVar(value="")
        self.location_var = tk.StringVar(value="")
        self.application_stage_var = tk.StringVar(value="Ready to Apply")
        self.priority_var = tk.StringVar(value="Medium")
        self.source_var = tk.StringVar(value="1")
        self.url_var = tk.StringVar(value="")
        self.headless_var = tk.BooleanVar(value=False)
        self.keep_browser_open_var = tk.BooleanVar(value=True)
        self.review_only_var = tk.BooleanVar(value=True)
        self.browser_mode_var = tk.StringVar(value="Start a new automation browser")
        self.tab_info_var = tk.StringVar(value="No browser tab selected yet.")
        self.readiness_var = tk.StringVar(value="Run preflight to verify profile, resume, and browser access.")
        self.last_run_var = tk.StringVar(value="No runs yet.")
        self.last_result_var = tk.StringVar(value="Awaiting first automation run.")
        self.last_detected_role_var = tk.StringVar(value="No role suggestions loaded.")
        self.pipeline_count_var = tk.StringVar(value="0 active records")
        self.submitted_count_var = tk.StringVar(value="0 submitted")
        self.history_filter_var = tk.StringVar(value="")
        self.url_entry: ttk.Entry | None = None
        self.role_combo: ttk.Combobox | None = None
        self.start_btn: ttk.Button | None = None
        self.search_btn: ttk.Button | None = None
        self.stop_btn: ttk.Button | None = None
        self.history_listbox: tk.Listbox | None = None
        self.pipeline_listbox: tk.Listbox | None = None
        self.notes_text: tk.Text | None = None
        self.history_items: list[dict[str, Any]] = []
        self.pipeline_items: list[dict[str, Any]] = []
        self.current_browser: BrowserSession | None = None
        self.stop_requested = False

        self._configure_root()
        self._build_ui()
        self._load_history()
        self._load_pipeline()
        self._load_app_state()
        self._load_defaults()
        self._refresh_preflight_status()

    def _configure_root(self) -> None:
        self.root.configure(bg="#eef1f5")

    @staticmethod
    def _open_path(path: Path) -> None:
        os.startfile(str(path))

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        title_font = ("SF Pro Display", 22, "bold")
        body_font = ("SF Pro Text", 10)
        ui_font = ("SF Pro Text", 10)
        ui_semibold = ("SF Pro Text", 10, "bold")
        metric_font = ("SF Pro Display", 13, "bold")

        style.configure("Root.TFrame", background="#eef1f5")
        style.configure("Panel.TFrame", background="#f7f8fa", relief="flat")
        style.configure("Header.TFrame", background="#eef1f5")
        style.configure("HeroTitle.TLabel", background="#eef1f5", foreground="#111111", font=title_font)
        style.configure("HeroBody.TLabel", background="#eef1f5", foreground="#667085", font=body_font)
        style.configure("Metric.TLabelframe", background="#f7f8fa", borderwidth=1, relief="solid")
        style.configure("Metric.TLabelframe.Label", background="#f7f8fa", foreground="#7a7f87", font=ui_font)
        style.configure("Section.TLabelframe", background="#f7f8fa", borderwidth=1, relief="solid", padding=14)
        style.configure("Section.TLabelframe.Label", background="#f7f8fa", foreground="#111111", font=ui_semibold)
        style.configure("Primary.TButton", font=ui_semibold, padding=(14, 10))
        style.map("Primary.TButton", background=[("!disabled", "#0a84ff")], foreground=[("!disabled", "#ffffff")])
        style.configure("Secondary.TButton", font=ui_font, padding=(10, 8))
        style.configure("SummaryValue.TLabel", background="#f7f8fa", foreground="#111111", font=metric_font)
        style.configure("SummaryHint.TLabel", background="#f7f8fa", foreground="#8a9099", font=("SF Pro Text", 9))
        style.configure("Body.TLabel", background="#f7f8fa", foreground="#4b5563", font=body_font)
        style.configure("Caption.TLabel", background="#f7f8fa", foreground="#8a9099", font=("SF Pro Text", 9))
        style.configure("Field.TLabel", background="#f7f8fa", foreground="#1f2937", font=ui_font)
        style.configure("TCheckbutton", background="#f7f8fa", foreground="#1f2937", font=ui_font)
        style.configure("TRadiobutton", background="#f7f8fa", foreground="#1f2937", font=ui_font)
        style.configure("TEntry", padding=7)
        style.configure("TCombobox", padding=6)

        outer = ttk.Frame(self.root, padding=18, style="Root.TFrame")
        outer.pack(fill=tk.BOTH, expand=True)

        hero = ttk.Frame(outer, padding=(4, 0, 4, 4), style="Header.TFrame")
        hero.pack(fill=tk.X, pady=(0, 14))
        ttk.Label(hero, text="Job Bot", style="HeroTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(
            hero,
            text="Minimal application assistant for selecting a job page, validating readiness, and filling forms with review-first controls.",
            style="HeroBody.TLabel",
            wraplength=920,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(6, 0))

        summary_row = ttk.Frame(outer, style="Root.TFrame")
        summary_row.pack(fill=tk.X, pady=(0, 12))
        self._metric_card(summary_row, "Readiness", self.readiness_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._metric_card(summary_row, "Last Run", self.last_run_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self._metric_card(summary_row, "Detected Role", self.last_detected_role_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self._metric_card(summary_row, "Pipeline", self.pipeline_count_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        main_row = ttk.Frame(outer, style="Root.TFrame")
        main_row.pack(fill=tk.BOTH, expand=True)

        left_col = ttk.Frame(main_row, style="Root.TFrame")
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right_col = ttk.Frame(main_row, style="Root.TFrame")
        right_col.pack(side=tk.LEFT, fill=tk.BOTH, padx=(12, 0))

        profile_box = ttk.LabelFrame(left_col, text="Profile", style="Section.TLabelframe")
        profile_box.pack(fill=tk.X, pady=(0, 10))
        self._row_with_browse(profile_box, "Profile JSON", self.profile_var, self._browse_profile)
        self._row_with_browse(profile_box, "Resume File", self.resume_var, self._browse_resume)

        pref_box = ttk.LabelFrame(left_col, text="Job Preferences", style="Section.TLabelframe")
        pref_box.pack(fill=tk.X, pady=(0, 10))
        self._row(pref_box, "Company", self.company_var)
        self._role_row(pref_box, "Role")
        self._row(pref_box, "Location", self.location_var)
        ttk.Label(
            pref_box,
            text="Role suggestions are pulled from the selected tab or job page when available.",
            wraplength=430,
            justify=tk.LEFT,
            style="Caption.TLabel",
        ).pack(anchor=tk.W, pady=(4, 0))

        source_box = ttk.LabelFrame(left_col, text="Job Source", style="Section.TLabelframe")
        source_box.pack(fill=tk.X, pady=(0, 10))
        ttk.Radiobutton(
            source_box,
            text="Paste Job Link",
            variable=self.source_var,
            value="1",
            command=self._toggle_source,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            source_box,
            text="Auto Search Jobs",
            variable=self.source_var,
            value="2",
            command=self._toggle_source,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            source_box,
            text="Use Open Browser Tab",
            variable=self.source_var,
            value="3",
            command=self._toggle_source,
        ).pack(anchor=tk.W)
        self._row(source_box, "Job URL", self.url_var)
        ttk.Label(source_box, textvariable=self.tab_info_var, wraplength=430, justify=tk.LEFT, style="Caption.TLabel").pack(anchor=tk.W, pady=(6, 0))

        options_box = ttk.LabelFrame(right_col, text="Options", style="Section.TLabelframe")
        options_box.pack(fill=tk.X)
        ttk.Checkbutton(options_box, text="Headless Browser", variable=self.headless_var).pack(anchor=tk.W)
        ttk.Checkbutton(options_box, text="Keep Browser Open After Run", variable=self.keep_browser_open_var).pack(anchor=tk.W)
        ttk.Checkbutton(options_box, text="Review Only Mode (never auto-submit)", variable=self.review_only_var).pack(anchor=tk.W)
        ttk.Label(options_box, text="Browser Access", style="Field.TLabel").pack(anchor=tk.W, pady=(8, 0))
        browser_mode = ttk.Combobox(
            options_box,
            textvariable=self.browser_mode_var,
            values=["Start a new automation browser", "Attach to existing Brave debug session"],
            state="readonly",
        )
        browser_mode.pack(fill=tk.X)

        application_box = ttk.LabelFrame(right_col, text="Application Details", style="Section.TLabelframe")
        application_box.pack(fill=tk.X, pady=(10, 0))
        self._combo_row(
            application_box,
            "Stage",
            self.application_stage_var,
            ["Ready to Apply", "In Review", "Submitted", "Follow Up", "Interview", "Offer", "Closed"],
        )
        self._combo_row(
            application_box,
            "Priority",
            self.priority_var,
            ["Low", "Medium", "High"],
        )
        ttk.Label(application_box, text="Notes", style="Field.TLabel").pack(anchor=tk.W, pady=(8, 0))
        self.notes_text = tk.Text(
            application_box,
            height=6,
            wrap=tk.WORD,
            bd=0,
            relief=tk.FLAT,
            bg="#f3f4f6",
            fg="#1f2937",
            insertbackground="#111111",
            font=("SF Pro Text", 10),
            padx=10,
            pady=10,
        )
        self.notes_text.pack(fill=tk.X, pady=(6, 0))
        details_actions = ttk.Frame(application_box)
        details_actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(details_actions, text="Save Draft", command=self._save_draft, style="Secondary.TButton").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(details_actions, text="Export CSV", command=self._export_pipeline_csv, style="Secondary.TButton").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Label(
            application_box,
            textvariable=self.submitted_count_var,
            style="Caption.TLabel",
        ).pack(anchor=tk.W, pady=(8, 0))

        action_box = ttk.LabelFrame(right_col, text="Run", style="Section.TLabelframe")
        action_box.pack(fill=tk.X, pady=(10, 0))
        self.start_btn = ttk.Button(action_box, text="Start Autofill", command=self._start, style="Primary.TButton")
        self.start_btn.pack(fill=tk.X)
        action_row = ttk.Frame(action_box)
        action_row.pack(fill=tk.X, pady=(8, 0))
        self.search_btn = ttk.Button(action_row, text="Search Jobs", command=self._search_jobs_only, style="Secondary.TButton")
        self.search_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.stop_btn = ttk.Button(action_row, text="Stop", command=self._stop_run, style="Secondary.TButton", state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        quick_actions = ttk.Frame(action_box)
        quick_actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(quick_actions, text="Preflight", command=self._run_preflight, style="Secondary.TButton").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(quick_actions, text="Data", command=self._open_data_folder, style="Secondary.TButton").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(quick_actions, text="Screenshots", command=self._open_screenshots, style="Secondary.TButton").pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(action_box, textvariable=self.status_var, style="Field.TLabel").pack(anchor=tk.W, pady=(8, 0))
        ttk.Label(action_box, textvariable=self.last_result_var, wraplength=300, justify=tk.LEFT, style="Caption.TLabel").pack(anchor=tk.W, pady=(4, 0))

        pipeline_box = ttk.LabelFrame(left_col, text="Pipeline", style="Section.TLabelframe")
        pipeline_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        pipeline_frame = ttk.Frame(pipeline_box)
        pipeline_frame.pack(fill=tk.BOTH, expand=True)
        self.pipeline_listbox = tk.Listbox(pipeline_frame, height=9, exportselection=False)
        self.pipeline_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pipeline_scroll = ttk.Scrollbar(pipeline_frame, orient=tk.VERTICAL, command=self.pipeline_listbox.yview)
        pipeline_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.pipeline_listbox.configure(yscrollcommand=pipeline_scroll.set)
        self.pipeline_listbox.bind("<Double-Button-1>", self._apply_selected_pipeline)
        self.pipeline_listbox.bind("<Return>", self._apply_selected_pipeline)
        ttk.Label(
            pipeline_box,
            text="Double-click a record to reload the company, role, stage, priority, URL, and notes.",
            wraplength=430,
            justify=tk.LEFT,
            style="Caption.TLabel",
        ).pack(anchor=tk.W, pady=(8, 0))

        history_box = ttk.LabelFrame(right_col, text="Recent Runs", style="Section.TLabelframe")
        history_box.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        filter_row = ttk.Frame(history_box)
        filter_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(filter_row, text="Search").pack(side=tk.LEFT)
        filter_entry = ttk.Entry(filter_row, textvariable=self.history_filter_var)
        filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        filter_entry.bind("<KeyRelease>", lambda _event: self._render_history())

        list_frame = ttk.Frame(history_box)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.history_listbox = tk.Listbox(list_frame, height=14, exportselection=False)
        self.history_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        history_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.history_listbox.yview)
        history_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_listbox.configure(yscrollcommand=history_scroll.set)
        self.history_listbox.bind("<Double-Button-1>", self._apply_selected_history)
        self.history_listbox.bind("<Return>", self._apply_selected_history)
        ttk.Label(
            history_box,
            text="Double-click a run to reload its role, location, source mode, and URL.",
            wraplength=300,
            justify=tk.LEFT,
            style="Caption.TLabel",
        ).pack(anchor=tk.W, pady=(8, 0))

        log_box = ttk.LabelFrame(outer, text="Execution Log", style="Section.TLabelframe")
        log_box.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log_text = tk.Text(
            log_box,
            height=16,
            wrap=tk.WORD,
            bd=0,
            relief=tk.FLAT,
            bg="#f3f4f6",
            fg="#1f2937",
            insertbackground="#111111",
            font=("SF Mono", 10),
            padx=12,
            pady=12,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.configure(state=tk.DISABLED)

        self._toggle_source()

    def _metric_card(self, parent: ttk.Widget, title: str, value_var: tk.StringVar) -> ttk.LabelFrame:
        card = ttk.LabelFrame(parent, text=title, style="Metric.TLabelframe", padding=12)
        ttk.Label(card, textvariable=value_var, style="SummaryValue.TLabel", wraplength=260, justify=tk.LEFT).pack(anchor=tk.W)
        ttk.Label(card, text="Live status for the current session.", style="SummaryHint.TLabel").pack(anchor=tk.W, pady=(4, 0))
        return card

    def _row(self, parent: ttk.Widget, label: str, var: tk.StringVar) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label, width=12, style="Field.TLabel").pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if var is self.url_var:
            self.url_entry = entry

    def _row_with_browse(
        self,
        parent: ttk.Widget,
        label: str,
        var: tk.StringVar,
        callback,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label, width=12, style="Field.TLabel").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Browse", command=callback, style="Secondary.TButton").pack(side=tk.LEFT, padx=(8, 0))

    def _role_row(self, parent: ttk.Widget, label: str) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label, width=12, style="Field.TLabel").pack(side=tk.LEFT)
        combo = ttk.Combobox(row, textvariable=self.role_var)
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.role_combo = combo

    def _combo_row(self, parent: ttk.Widget, label: str, var: tk.StringVar, values: list[str]) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label, width=12, style="Field.TLabel").pack(side=tk.LEFT)
        combo = ttk.Combobox(row, textvariable=var, values=values, state="readonly")
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _browse_profile(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Profile JSON",
            filetypes=[("JSON", "*.json"), ("All Files", "*.*")],
        )
        if path:
            self.profile_var.set(path)
            self._refresh_preflight_status()

    def _browse_resume(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Resume File",
            filetypes=[("Documents", "*.pdf *.doc *.docx *.txt"), ("All Files", "*.*")],
        )
        if path:
            self.resume_var.set(path)
            self._refresh_preflight_status()

    def _toggle_source(self) -> None:
        enabled = self.source_var.get() == "1"
        if self.url_entry is not None:
            self.url_entry.configure(state=("normal" if enabled else "disabled"))

    def _load_defaults(self) -> None:
        try:
            store = ProfileStore(Path(self.profile_var.get()))
            profile = store.load()
            basics = profile.get("basics", {})
            prefs = profile.get("job_preferences", {})
            if not self.resume_var.get().strip():
                self.resume_var.set(str(basics.get("resume_path", "")).strip())
            if not self.role_var.get().strip():
                self.role_var.set(str(prefs.get("role", "")))
            if not self.location_var.get().strip():
                self.location_var.set(str(prefs.get("location", "")))
            self._set_role_suggestions([str(prefs.get("role", ""))] if prefs.get("role") else [])
        except Exception:
            return

    def _log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{stamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
        self.root.update_idletasks()

    def _set_role_suggestions(self, suggestions: list[str]) -> None:
        cleaned = [item.strip() for item in suggestions if str(item).strip()]
        unique: list[str] = []
        seen: set[str] = set()
        for item in cleaned:
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique.append(item)
        self.role_options = unique
        if self.role_combo is not None:
            self.role_combo.configure(values=self.role_options)
        if not self.role_var.get().strip() and self.role_options:
            self.role_var.set(self.role_options[0])
        if self.role_options:
            self.last_detected_role_var.set(self.role_options[0])

    def _choose_from_list(self, title: str, prompt: str, choices: list[tuple[str, str]]) -> str | None:
        dialog = ChoiceDialog(self.root, title=title, prompt=prompt, choices=choices)
        return dialog.result

    def _prefer_existing_browser(self) -> bool:
        return self.browser_mode_var.get() == "Attach to existing Brave debug session"

    def _history_payload(self) -> list[dict[str, Any]]:
        if not RUN_HISTORY_PATH.exists():
            return []
        try:
            return json.loads(RUN_HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _load_history(self) -> None:
        self.history_items = self._history_payload()
        self._render_history()
        if self.history_items:
            self.last_run_var.set(str(self.history_items[0].get("timestamp", "No runs yet.")))
            self.last_result_var.set(str(self.history_items[0].get("summary", "Awaiting first automation run.")))

    def _pipeline_payload(self) -> list[dict[str, Any]]:
        if not APPLICATION_PIPELINE_PATH.exists():
            return []
        try:
            return json.loads(APPLICATION_PIPELINE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _load_pipeline(self) -> None:
        self.pipeline_items = self._pipeline_payload()
        self._render_pipeline()

    def _render_pipeline(self) -> None:
        if self.pipeline_listbox is None:
            return
        self.pipeline_listbox.delete(0, tk.END)
        for item in self.pipeline_items[: self.PIPELINE_LIMIT]:
            self.pipeline_listbox.insert(tk.END, self._pipeline_label(item))
        total = len(self.pipeline_items)
        submitted = sum(1 for item in self.pipeline_items if str(item.get("stage", "")).lower() == "submitted")
        self.pipeline_count_var.set(f"{total} tracked applications")
        self.submitted_count_var.set(f"{submitted} submitted")

    @staticmethod
    def _pipeline_label(item: dict[str, Any]) -> str:
        company = str(item.get("company", "Unknown company"))
        role = str(item.get("role", "Unknown role"))
        stage = str(item.get("stage", ""))
        priority = str(item.get("priority", ""))
        return f"{company} | {role} | {stage} | {priority}"

    def _render_history(self) -> None:
        if self.history_listbox is None:
            return
        self.history_listbox.delete(0, tk.END)
        term = self.history_filter_var.get().strip().lower()
        for item in self.history_items:
            label = self._history_label(item)
            if term and term not in label.lower():
                continue
            self.history_listbox.insert(tk.END, label)

    @staticmethod
    def _history_label(item: dict[str, Any]) -> str:
        timestamp = str(item.get("timestamp", ""))
        role = str(item.get("role", "Unknown role"))
        source = str(item.get("source", ""))
        result = str(item.get("result", ""))
        return f"{timestamp} | {role} | {source} | {result}"

    def _selected_history_item(self) -> dict[str, Any] | None:
        if self.history_listbox is None:
            return None
        selection = self.history_listbox.curselection()
        if not selection:
            return None
        target_label = self.history_listbox.get(selection[0])
        for item in self.history_items:
            if self._history_label(item) == target_label:
                return item
        return None

    def _apply_selected_history(self, _event: Any = None) -> None:
        item = self._selected_history_item()
        if item is None:
            return
        self.company_var.set(str(item.get("company", "")))
        self.role_var.set(str(item.get("role", "")))
        self.location_var.set(str(item.get("location", "")))
        self.url_var.set(str(item.get("url", "")))
        self.source_var.set(str(item.get("source_value", "1")))
        self._toggle_source()
        self.tab_info_var.set(f"Loaded recent run: {item.get('summary', '')}")
        self._log(f"Loaded recent run for role '{item.get('role', '')}'")

    def _append_history(self, entry: dict[str, Any]) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = [entry, *self.history_items]
        self.history_items = payload[: self.HISTORY_LIMIT]
        RUN_HISTORY_PATH.write_text(json.dumps(self.history_items, indent=2), encoding="utf-8")
        self._render_history()
        self.last_run_var.set(str(entry.get("timestamp", "")))
        self.last_result_var.set(str(entry.get("summary", "")))

    def _app_state_payload(self) -> dict[str, Any]:
        if not APP_STATE_PATH.exists():
            return {}
        try:
            return json.loads(APP_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _load_app_state(self) -> None:
        payload = self._app_state_payload()
        if not payload:
            return
        self.profile_var.set(str(payload.get("profile_path", self.profile_var.get())))
        self.resume_var.set(str(payload.get("resume_path", self.resume_var.get())))
        self.company_var.set(str(payload.get("company", "")))
        self.role_var.set(str(payload.get("role", self.role_var.get())))
        self.location_var.set(str(payload.get("location", self.location_var.get())))
        self.source_var.set(str(payload.get("source", self.source_var.get())))
        self.url_var.set(str(payload.get("url", self.url_var.get())))
        self.headless_var.set(bool(payload.get("headless", self.headless_var.get())))
        self.keep_browser_open_var.set(bool(payload.get("keep_browser_open", self.keep_browser_open_var.get())))
        self.review_only_var.set(bool(payload.get("review_only", self.review_only_var.get())))
        self.browser_mode_var.set(str(payload.get("browser_mode", self.browser_mode_var.get())))
        self.application_stage_var.set(str(payload.get("application_stage", self.application_stage_var.get())))
        self.priority_var.set(str(payload.get("priority", self.priority_var.get())))
        self._toggle_source()
        notes = str(payload.get("notes", ""))
        if self.notes_text is not None:
            self.notes_text.delete("1.0", tk.END)
            self.notes_text.insert("1.0", notes)

    def _save_app_state(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "profile_path": self.profile_var.get().strip(),
            "resume_path": self.resume_var.get().strip(),
            "company": self.company_var.get().strip(),
            "role": self.role_var.get().strip(),
            "location": self.location_var.get().strip(),
            "source": self.source_var.get(),
            "url": self.url_var.get().strip(),
            "headless": bool(self.headless_var.get()),
            "keep_browser_open": bool(self.keep_browser_open_var.get()),
            "review_only": bool(self.review_only_var.get()),
            "browser_mode": self.browser_mode_var.get(),
            "application_stage": self.application_stage_var.get().strip(),
            "priority": self.priority_var.get().strip(),
            "notes": self._notes_value(),
        }
        APP_STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _notes_value(self) -> str:
        if self.notes_text is None:
            return ""
        return self.notes_text.get("1.0", tk.END).strip()

    def _append_pipeline_entry(self, entry: dict[str, Any]) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = [entry, *self.pipeline_items]
        self.pipeline_items = payload[: self.PIPELINE_LIMIT]
        APPLICATION_PIPELINE_PATH.write_text(json.dumps(self.pipeline_items, indent=2), encoding="utf-8")
        self._render_pipeline()

    def _selected_pipeline_item(self) -> dict[str, Any] | None:
        if self.pipeline_listbox is None:
            return None
        selection = self.pipeline_listbox.curselection()
        if not selection:
            return None
        target_label = self.pipeline_listbox.get(selection[0])
        for item in self.pipeline_items:
            if self._pipeline_label(item) == target_label:
                return item
        return None

    def _apply_selected_pipeline(self, _event: Any = None) -> None:
        item = self._selected_pipeline_item()
        if item is None:
            return
        self.company_var.set(str(item.get("company", "")))
        self.role_var.set(str(item.get("role", "")))
        self.location_var.set(str(item.get("location", "")))
        self.url_var.set(str(item.get("url", "")))
        self.application_stage_var.set(str(item.get("stage", "Ready to Apply")))
        self.priority_var.set(str(item.get("priority", "Medium")))
        self.source_var.set(str(item.get("source_value", "1")))
        self._toggle_source()
        if self.notes_text is not None:
            self.notes_text.delete("1.0", tk.END)
            self.notes_text.insert("1.0", str(item.get("notes", "")))
        self._save_app_state()
        self._log(f"Loaded pipeline record for {item.get('company', '')} - {item.get('role', '')}")

    def _save_draft(self) -> None:
        self._save_app_state()
        company = self.company_var.get().strip() or "Unknown company"
        role = self.role_var.get().strip() or "Unknown role"
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "company": company,
            "role": role,
            "location": self.location_var.get().strip(),
            "url": self.url_var.get().strip(),
            "stage": self.application_stage_var.get().strip() or "Ready to Apply",
            "priority": self.priority_var.get().strip() or "Medium",
            "notes": self._notes_value(),
            "source_value": self.source_var.get(),
        }
        self._append_pipeline_entry(entry)
        self.last_result_var.set(f"Draft saved for {company}")
        self._log(f"Saved draft for {company} - {role}")

    def _export_pipeline_csv(self) -> None:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = REPORTS_DIR / f"pipeline_export_{stamp}.csv"
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["timestamp", "company", "role", "location", "stage", "priority", "url", "notes", "source_value"],
            )
            writer.writeheader()
            for item in self.pipeline_items:
                writer.writerow({key: item.get(key, "") for key in writer.fieldnames})
        self._log(f"Exported pipeline CSV: {path}")
        messagebox.showinfo("Export Complete", f"Pipeline exported to:\n{path}", parent=self.root)

    @staticmethod
    def _infer_company_name(url: str, title: str) -> str:
        cleaned_title = " ".join((title or "").split()).strip()
        if cleaned_title:
            for separator in ("|", "-", " at ", " @ "):
                if separator in cleaned_title:
                    parts = [part.strip() for part in cleaned_title.split(separator) if part.strip()]
                    if len(parts) >= 2:
                        candidate = parts[-1]
                        if 2 <= len(candidate) <= 80:
                            return candidate
        host = urlparse(url).netloc.lower()
        host = host.replace("www.", "").split(":")[0]
        if host:
            base = host.split(".")[0].replace("-", " ").replace("_", " ")
            return " ".join(part.capitalize() for part in base.split() if part)
        return ""

    def _preflight_report(self) -> tuple[bool, str]:
        issues: list[str] = []
        profile_path = Path(_clean_user_path(self.profile_var.get()) or PROFILE_PATH)
        if not profile_path.exists():
            issues.append("Profile file missing")
        resume_path = _resolve_existing_resume_path(self.resume_var.get())
        if resume_path is None:
            issues.append("Resume missing")
        if self.source_var.get() == "1" and not self.url_var.get().strip():
            issues.append("Job URL missing")
        if self.source_var.get() == "2" and not self.role_var.get().strip():
            issues.append("Role missing for auto-search")
        if self.source_var.get() == "3" and not self._prefer_existing_browser():
            issues.append("Use attached browser mode for open-tab selection")
        return (not issues, "Ready to run" if not issues else " | ".join(issues))

    def _refresh_preflight_status(self) -> None:
        ready, text = self._preflight_report()
        self.readiness_var.set(text)
        if ready:
            self.status_var.set("Ready")

    def _run_preflight(self) -> None:
        self._refresh_preflight_status()
        ready, text = self._preflight_report()
        browser_hint = "Brave debug attach enabled." if self._prefer_existing_browser() else "New browser session will be launched."
        message = f"{text}\n\nBrowser: {browser_hint}"
        if ready:
            messagebox.showinfo("Preflight Check", message, parent=self.root)
            self._log(f"Preflight passed: {text}")
        else:
            messagebox.showwarning("Preflight Check", message, parent=self.root)
            self._log(f"Preflight issues: {text}")

    def _open_data_folder(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._open_path(DATA_DIR)

    def _open_screenshots(self) -> None:
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        self._open_path(SCREENSHOTS_DIR)

    def _start(self) -> None:
        self._save_app_state()
        self.stop_requested = False
        if self.start_btn is not None:
            self.start_btn.configure(state=tk.DISABLED)
        if self.search_btn is not None:
            self.search_btn.configure(state=tk.DISABLED)
        if self.stop_btn is not None:
            self.stop_btn.configure(state=tk.NORMAL)
        self.status_var.set("Running...")
        self._log("Starting workflow")
        try:
            self._run_workflow()
        except Exception as exc:
            if str(exc) == "Run stopped by user.":
                self._log("Run stopped by user.")
            else:
                self._log(f"Error: {exc}")
                messagebox.showerror("Job Bot", str(exc))
        finally:
            if self.start_btn is not None:
                self.start_btn.configure(state=tk.NORMAL)
            if self.search_btn is not None:
                self.search_btn.configure(state=tk.NORMAL)
            if self.stop_btn is not None:
                self.stop_btn.configure(state=tk.DISABLED)
            self._refresh_preflight_status()
            self.current_browser = None

    def _search_jobs_only(self) -> None:
        self._save_app_state()
        role = self.role_var.get().strip()
        if not role:
            messagebox.showwarning("Search Jobs", "Enter a role first.", parent=self.root)
            return

        preferences = {
            "role": role,
            "location": self.location_var.get().strip(),
        }
        self.status_var.set("Searching...")
        self._log("Searching for jobs...")
        try:
            search_engine = JobSearchEngine()
            results = search_engine.search(preferences=preferences)
            if not results:
                raise RuntimeError("No jobs found for the current search.")
            choice_key = self._choose_from_list(
                "Choose Job Result",
                "Select the job page you want to use.",
                [(item.url, f"{item.title}\n{item.url}") for item in results[:8]],
            )
            if not choice_key:
                self._log("Search cancelled.")
                return
            self.url_var.set(choice_key)
            self.source_var.set("1")
            self._toggle_source()
            self.tab_info_var.set(f"Selected search result: {choice_key}")
            self._save_app_state()
            self._log(f"Selected search result: {choice_key}")
        except Exception as exc:
            self._log(f"Search error: {exc}")
            messagebox.showerror("Search Jobs", str(exc), parent=self.root)
        finally:
            self.status_var.set("Ready")
            self._refresh_preflight_status()

    def _stop_run(self) -> None:
        self.stop_requested = True
        self.status_var.set("Stopping...")
        self._log("Stop requested. Waiting for a safe checkpoint...")

    def _yield_ui(self) -> None:
        self.root.update()

    def _check_stop_requested(self) -> None:
        self._yield_ui()
        if self.stop_requested:
            if self.current_browser is not None:
                try:
                    self.current_browser.stop(keep_browser_open=False)
                except Exception:
                    pass
            raise RuntimeError("Run stopped by user.")

    def _run_workflow(self) -> None:
        self._check_stop_requested()
        profile_path = Path(_clean_user_path(self.profile_var.get()) or PROFILE_PATH)
        store = ProfileStore(profile_path)
        profile = store.load()

        RESUMES_DIR.mkdir(parents=True, exist_ok=True)
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

        resume_source = _resolve_existing_resume_path(self.resume_var.get())
        if resume_source is None:
            raise FileNotFoundError("Resume file not found. Use Browse and pick your resume file.")

        destination = RESUMES_DIR / resume_source.name
        if resume_source.resolve() != destination.resolve():
            shutil.copy2(resume_source, destination)
        final_resume = str(destination.resolve())
        store.remember_answer(profile, "resume_path", final_resume, "Resume")

        preferences = {
            "role": self.role_var.get().strip(),
            "location": self.location_var.get().strip(),
        }
        profile["job_preferences"] = preferences
        store.save(profile)

        choice = self.source_var.get()
        if choice == "1":
            job_url = self.url_var.get().strip()
            if not job_url:
                raise ValueError("Job URL is required when 'Paste Job Link' is selected.")
            if "://" not in job_url:
                job_url = f"https://{job_url}"
        elif choice == "2":
            if not preferences["role"]:
                raise ValueError("Role is required for auto-search.")
            self._log("Auto-searching for jobs...")
            search_engine = JobSearchEngine()
            results = search_engine.search(preferences=preferences)
            if not results:
                raise RuntimeError("No jobs found by auto-search. Try manual URL mode.")
            for index, item in enumerate(results[:8], start=1):
                self._log(f"{index}. {item.title} -> {item.url}")
            choice_key = self._choose_from_list(
                "Choose Job Result",
                "Select the job page you want the automation to continue with.",
                [(item.url, f"{item.title}\n{item.url}") for item in results[:8]],
            )
            if not choice_key:
                raise RuntimeError("No job result selected.")
            job_url = choice_key
        else:
            job_url = ""

        browser = BrowserSession(headless=self.headless_var.get())
        self.current_browser = browser
        easy_flow = EasyApplyFlow(profile_store=store)
        external_flow = ExternalApplyFlow(profile_store=store)

        def prompt_missing(missing_fields: list[dict[str, Any]]) -> bool:
            changed = False
            seen: set[str] = set()
            for field in missing_fields:
                key = str(field.get("key", "")).strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                label = str(field.get("label") or key)
                options = field.get("options", []) or []
                suffix = f"\nOptions: {', '.join(map(str, options[:8]))}" if options else ""
                value = simpledialog.askstring(
                    "Missing Field",
                    f"Enter value for: {label}{suffix}",
                    parent=self.root,
                )
                if value and value.strip():
                    store.remember_answer(profile=profile, field_key=key, value=value.strip(), label=label)
                    changed = True
            if changed:
                store.save(profile)
            return changed

        try:
            self._check_stop_requested()
            attach_existing = self._prefer_existing_browser() or choice == "3"
            self._log("Opening browser...")
            attached = browser.start(attach_to_existing=attach_existing)
            self._check_stop_requested()

            if choice == "3":
                if not attached:
                    raise RuntimeError(
                        "Could not attach to an existing Brave debug session. "
                        "Start Brave with --remote-debugging-port=9222 or use 'Start a new automation browser'."
                    )
                tabs = browser.list_tabs(job_only=True)
                if not tabs:
                    tabs = browser.list_tabs(job_only=False)
                if not tabs:
                    raise RuntimeError("No open tabs were available in the attached browser session.")

                selected_handle = self._choose_from_list(
                    "Choose Browser Tab",
                    "I found these open tabs. Pick the job page you want to continue on.",
                    [(tab["handle"], f"{tab['title'] or '(Untitled)'}\n{tab['url']}") for tab in tabs],
                )
                if not selected_handle:
                    raise RuntimeError("No browser tab selected.")
                browser.switch_to_tab(selected_handle)
                browser.wait_for_page_settle()
                self._check_stop_requested()
                summary = browser.get_current_page_summary()
                self.tab_info_var.set(f"Selected tab: {summary['title'] or summary['url']}")
                self._log(f"Selected browser tab: {summary['url']}")
            else:
                browser.open(job_url)
                browser.wait_for_page_settle()
                self._check_stop_requested()

            page_summary = browser.get_current_page_summary()
            inferred_company = self._infer_company_name(page_summary.get("url", ""), page_summary.get("title", ""))
            if inferred_company and not self.company_var.get().strip():
                self.company_var.set(inferred_company)
                self._log(f"Detected company: {inferred_company}")

            self._check_stop_requested()
            role_suggestions = browser.extract_role_suggestions()
            if role_suggestions:
                self._set_role_suggestions(role_suggestions)
                self._log(f"Role suggestions from page: {', '.join(role_suggestions[:5])}")
                self.last_detected_role_var.set(role_suggestions[0])

            selected_role = self.role_var.get().strip()
            if selected_role and not browser.has_application_form():
                self._check_stop_requested()
                matched_job = browser.find_best_matching_job_link(selected_role)
                if matched_job is not None:
                    open_match = messagebox.askyesno(
                        "Open Matching Job",
                        f"Found a matching job link for '{selected_role}':\n\n{matched_job['title']}\n\nOpen it now?",
                        parent=self.root,
                    )
                    if open_match:
                        browser.open(matched_job["url"])
                        browser.wait_for_page_settle()
                        self._check_stop_requested()
                        self._log(f"Opened matching job page: {matched_job['url']}")
                        role_suggestions = browser.extract_role_suggestions()
                        if role_suggestions:
                            self._set_role_suggestions(role_suggestions)

            self._check_stop_requested()
            apply_type = browser.detect_apply_type()
            self._log(f"Detected apply type: {apply_type}")
            if apply_type == "easy_apply":
                result = easy_flow.run(
                    browser=browser,
                    profile=profile,
                    resume_path=final_resume,
                    prompt_missing=prompt_missing,
                )
            else:
                result = external_flow.run(
                    browser=browser,
                    profile=profile,
                    resume_path=final_resume,
                    prompt_missing=prompt_missing,
                )

            self._check_stop_requested()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = SCREENSHOTS_DIR / f"review_{timestamp}.png"
            browser.save_screenshot(screenshot_path)
            filled_count = sum(1 for item in result.get("fill_plan", []) if str(item.get("value", "")).strip())

            self._log(f"Review screenshot: {screenshot_path}")
            self._log(f"Fields detected: {len(result.get('fill_plan', []))}")
            self._log(f"Fields filled: {filled_count}")

            do_submit = False
            if self.review_only_var.get():
                self._log("Review-only mode is on. Submission skipped.")
            else:
                do_submit = messagebox.askyesno(
                    "Review Before Submit",
                    "Form filling is complete.\n\nSubmit now?",
                    parent=self.root,
                )
            if do_submit:
                clicked = browser.click_submit()
                if clicked:
                    self._log("Submit clicked. Check browser for final confirmation.")
                else:
                    self._log("Could not auto-click submit. Please submit manually.")
            else:
                self._log("Submission skipped by user.")

            source_name = {
                "1": "Direct URL",
                "2": "Auto Search",
                "3": "Open Browser Tab",
            }.get(choice, "Unknown")
            run_summary = f"Filled {filled_count}/{len(result.get('fill_plan', []))} fields on {source_name}"
            result_stage = "Submitted" if do_submit else (self.application_stage_var.get().strip() or "Ready to Apply")
            self._append_history(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "company": self.company_var.get().strip(),
                    "role": self.role_var.get().strip(),
                    "location": self.location_var.get().strip(),
                    "url": browser.get_current_page_summary().get("url", job_url),
                    "source": source_name,
                    "source_value": choice,
                    "result": "Submitted" if do_submit else "Review pending",
                    "summary": run_summary,
                    "filled_count": filled_count,
                    "detected_count": len(result.get("fill_plan", [])),
                    "screenshot": str(screenshot_path),
                }
            )
            self._append_pipeline_entry(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "company": self.company_var.get().strip() or inferred_company,
                    "role": self.role_var.get().strip(),
                    "location": self.location_var.get().strip(),
                    "url": browser.get_current_page_summary().get("url", job_url),
                    "stage": result_stage,
                    "priority": self.priority_var.get().strip() or "Medium",
                    "notes": self._notes_value(),
                    "source_value": choice,
                    "result": "Submitted" if do_submit else "Review pending",
                }
            )
            self.last_result_var.set(run_summary)
            self._save_app_state()
            messagebox.showinfo("Job Bot", "Workflow completed.", parent=self.root)
        finally:
            browser.stop(keep_browser_open=self.keep_browser_open_var.get())


def main() -> None:
    root = tk.Tk()
    app = JobBotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
