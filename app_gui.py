from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from config import PROFILE_PATH, RESUMES_DIR, SCREENSHOTS_DIR
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


class JobBotApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Job Bot v2")
        self.root.geometry("860x620")
        self.root.minsize(820, 560)

        self.profile_var = tk.StringVar(value=str(PROFILE_PATH))
        self.resume_var = tk.StringVar(value="")
        self.role_var = tk.StringVar(value="")
        self.location_var = tk.StringVar(value="")
        self.source_var = tk.StringVar(value="1")
        self.url_var = tk.StringVar(value="")
        self.headless_var = tk.BooleanVar(value=False)
        self.url_entry: ttk.Entry | None = None

        self._build_ui()
        self._load_defaults()

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Section.TLabelframe", padding=10)

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="Job Bot v2", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text="Fill details once, press Start, review before submit.",
        ).pack(anchor=tk.W, pady=(0, 10))

        top_row = ttk.Frame(outer)
        top_row.pack(fill=tk.X)

        left_col = ttk.Frame(top_row)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right_col = ttk.Frame(top_row)
        right_col.pack(side=tk.LEFT, fill=tk.BOTH, padx=(12, 0))

        profile_box = ttk.LabelFrame(left_col, text="Profile", style="Section.TLabelframe")
        profile_box.pack(fill=tk.X, pady=(0, 10))
        self._row_with_browse(profile_box, "Profile JSON", self.profile_var, self._browse_profile)
        self._row_with_browse(profile_box, "Resume File", self.resume_var, self._browse_resume)

        pref_box = ttk.LabelFrame(left_col, text="Job Preferences", style="Section.TLabelframe")
        pref_box.pack(fill=tk.X, pady=(0, 10))
        self._row(pref_box, "Role", self.role_var)
        self._row(pref_box, "Location", self.location_var)

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
        self._row(source_box, "Job URL", self.url_var)

        options_box = ttk.LabelFrame(right_col, text="Options", style="Section.TLabelframe")
        options_box.pack(fill=tk.X)
        ttk.Checkbutton(options_box, text="Headless Browser", variable=self.headless_var).pack(anchor=tk.W)

        action_box = ttk.LabelFrame(right_col, text="Run", style="Section.TLabelframe")
        action_box.pack(fill=tk.X, pady=(10, 0))
        self.start_btn = ttk.Button(action_box, text="Start", command=self._start)
        self.start_btn.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(action_box, textvariable=self.status_var).pack(anchor=tk.W, pady=(8, 0))

        log_box = ttk.LabelFrame(outer, text="Execution Log", style="Section.TLabelframe")
        log_box.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log_text = tk.Text(log_box, height=16, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.configure(state=tk.DISABLED)

        self._toggle_source()

    def _row(self, parent: ttk.Widget, label: str, var: tk.StringVar) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label, width=12).pack(side=tk.LEFT)
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
        ttk.Label(row, text=label, width=12).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Browse", command=callback).pack(side=tk.LEFT, padx=(8, 0))

    def _browse_profile(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Profile JSON",
            filetypes=[("JSON", "*.json"), ("All Files", "*.*")],
        )
        if path:
            self.profile_var.set(path)

    def _browse_resume(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Resume File",
            filetypes=[("Documents", "*.pdf *.doc *.docx *.txt"), ("All Files", "*.*")],
        )
        if path:
            self.resume_var.set(path)

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
            self.resume_var.set(str(basics.get("resume_path", "")).strip())
            self.role_var.set(str(prefs.get("role", "")))
            self.location_var.set(str(prefs.get("location", "")))
        except Exception:
            return

    def _log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{stamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
        self.root.update_idletasks()

    def _start(self) -> None:
        self.start_btn.configure(state=tk.DISABLED)
        self.status_var.set("Running...")
        self._log("Starting workflow")
        try:
            self._run_workflow()
        except Exception as exc:
            self._log(f"Error: {exc}")
            messagebox.showerror("Job Bot", str(exc))
        finally:
            self.start_btn.configure(state=tk.NORMAL)
            self.status_var.set("Ready")

    def _run_workflow(self) -> None:
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
        if not preferences["role"]:
            raise ValueError("Role is required.")
        profile["job_preferences"] = preferences
        store.save(profile)

        choice = self.source_var.get()
        if choice == "1":
            job_url = self.url_var.get().strip()
            if not job_url:
                raise ValueError("Job URL is required when 'Paste Job Link' is selected.")
            if "://" not in job_url:
                job_url = f"https://{job_url}"
        else:
            self._log("Auto-searching for jobs...")
            search_engine = JobSearchEngine()
            results = search_engine.search(preferences=preferences)
            best = search_engine.pick_best(results)
            if not best:
                raise RuntimeError("No jobs found by auto-search. Try manual URL mode.")
            for index, item in enumerate(results[:5], start=1):
                self._log(f"{index}. {item.title} -> {item.url}")
            self._log(f"Picked best: {best.url}")
            job_url = best.url

        browser = BrowserSession(headless=self.headless_var.get())
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
            self._log("Opening browser...")
            browser.start()
            browser.open(job_url)
            browser.wait_for_page_settle()

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

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = SCREENSHOTS_DIR / f"review_{timestamp}.png"
            browser.save_screenshot(screenshot_path)
            filled_count = sum(1 for item in result.get("fill_plan", []) if str(item.get("value", "")).strip())

            self._log(f"Review screenshot: {screenshot_path}")
            self._log(f"Fields detected: {len(result.get('fill_plan', []))}")
            self._log(f"Fields filled: {filled_count}")

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

            messagebox.showinfo("Job Bot", "Workflow completed.", parent=self.root)
        finally:
            browser.stop()


def main() -> None:
    root = tk.Tk()
    app = JobBotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
