from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ProfileStore:
    """Loads, normalizes, and persists applicant profile data."""

    BASIC_KEY_MAP = {
        "full_name": "name",
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "phone": "phone",
        "location": "location",
        "city": "city",
        "country": "country",
        "linkedin": "linkedin",
        "github": "github",
        "website": "website",
        "resume_url": "resume_url",
        "resume_path": "resume_path",
        "summary": "summary",
    }

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            profile = self._default_profile()
            self.save(profile)
            return profile

        with self.path.open("r", encoding="utf-8") as file:
            profile = json.load(file)
        self._ensure_structure(profile)
        return profile

    def save(self, profile: dict[str, Any]) -> None:
        self._ensure_structure(profile)
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(profile, file, indent=2)

    def get_learned_answers(self, profile: dict[str, Any]) -> dict[str, str]:
        self._ensure_structure(profile)
        learned = profile["memory"]["learned_answers"]
        return {str(k): str(v) for k, v in learned.items()}

    def get_custom_answers(self, profile: dict[str, Any]) -> dict[str, str]:
        self._ensure_structure(profile)
        custom = profile["memory"]["custom_fields"]
        return {str(k): str(v) for k, v in custom.items()}

    def remember_answer(
        self,
        profile: dict[str, Any],
        field_key: str,
        value: str,
        label: str,
    ) -> None:
        clean_value = str(value).strip()
        if not clean_value:
            return

        self._ensure_structure(profile)
        profile["memory"]["learned_answers"][field_key] = clean_value

        basic_key = self.BASIC_KEY_MAP.get(field_key)
        if basic_key:
            profile["basics"][basic_key] = clean_value
            return

        if field_key.startswith("custom:"):
            custom_key = field_key.split("custom:", 1)[1]
            profile["memory"]["custom_fields"][custom_key] = clean_value
            if label.strip():
                profile["memory"]["custom_field_labels"][custom_key] = label.strip()

    @staticmethod
    def _ensure_structure(profile: dict[str, Any]) -> None:
        if not isinstance(profile.get("basics"), dict):
            profile["basics"] = {}
        basics = profile["basics"]
        basics.setdefault("name", "")
        basics.setdefault("first_name", "")
        basics.setdefault("last_name", "")
        basics.setdefault("email", "")
        basics.setdefault("phone", "")
        basics.setdefault("location", "")
        basics.setdefault("city", "")
        basics.setdefault("country", "")
        basics.setdefault("linkedin", "")
        basics.setdefault("github", "")
        basics.setdefault("website", "")
        basics.setdefault("resume_url", "")
        basics.setdefault("resume_path", "")
        basics.setdefault("summary", "")
        if not isinstance(profile.get("experience"), list):
            profile["experience"] = []
        if not isinstance(profile.get("skills"), list):
            profile["skills"] = []
        if not isinstance(profile.get("preferences"), dict):
            profile["preferences"] = {}
        preferences = profile["preferences"]
        preferences.setdefault("work_authorized", "")
        preferences.setdefault("requires_sponsorship", "")
        preferences.setdefault("salary_expectation", "")
        preferences.setdefault("notice_period", "")
        if not isinstance(profile.get("memory"), dict):
            profile["memory"] = {}
        if not isinstance(profile.get("job_preferences"), dict):
            profile["job_preferences"] = {}
        memory = profile["memory"]
        if not isinstance(memory.get("learned_answers"), dict):
            memory["learned_answers"] = {}
        if not isinstance(memory.get("custom_fields"), dict):
            memory["custom_fields"] = {}
        if not isinstance(memory.get("custom_field_labels"), dict):
            memory["custom_field_labels"] = {}

    @staticmethod
    def _default_profile() -> dict[str, Any]:
        return {
            "basics": {
                "name": "",
                "first_name": "",
                "last_name": "",
                "email": "",
                "phone": "",
                "location": "",
                "city": "",
                "country": "",
                "linkedin": "",
                "github": "",
                "website": "",
                "resume_url": "",
                "resume_path": "",
                "summary": "",
            },
            "experience": [],
            "skills": [],
            "preferences": {
                "work_authorized": "",
                "requires_sponsorship": "",
                "salary_expectation": "",
                "notice_period": "",
            },
            "memory": {
                "learned_answers": {},
                "custom_fields": {},
                "custom_field_labels": {},
            },
            "job_preferences": {
                "role": "",
                "location": "",
            },
        }
