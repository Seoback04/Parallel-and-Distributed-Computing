from __future__ import annotations

from typing import Any
import re


class FormFiller:
    """Maps generic form fields to known answers across many site variants."""

    FIELD_ALIASES = {
        "name": "full_name",
        "full name": "full_name",
        "first name": "first_name",
        "last name": "last_name",
        "email": "email",
        "phone": "phone",
        "mobile": "phone",
        "location": "location",
        "address": "location",
        "city": "city",
        "country": "country",
        "linkedin": "linkedin",
        "github": "github",
        "website": "website",
        "portfolio": "website",
        "resume": "resume_url",
        "resume upload": "resume_path",
        "upload resume": "resume_path",
        "attach resume": "resume_path",
        "resume file": "resume_path",
        "cv": "resume_url",
        "upload cv": "resume_path",
        "cv upload": "resume_path",
        "experience": "years_of_experience",
        "years of experience": "years_of_experience",
        "current company": "current_company",
        "current title": "current_title",
        "expected salary": "salary_expectation",
        "salary expectation": "salary_expectation",
        "notice period": "notice_period",
        "work authorization": "work_authorized",
        "authorized to work": "work_authorized",
        "sponsorship": "requires_sponsorship",
        "visa sponsorship": "requires_sponsorship",
        "summary": "summary",
        "cover letter": "cover_letter",
    }

    def build_fill_plan(
        self,
        fields: list[dict[str, Any]],
        answers: dict[str, str],
        custom_answers: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        plan: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        custom_answers = custom_answers or {}

        for field in fields:
            key = self._infer_key(field)
            value = self._resolve_value(field_key=key, answers=answers, custom_answers=custom_answers)

            if not value and self._needs_value(field, key):
                missing.append(
                    {
                        "label": str(field.get("label", "")),
                        "name": str(field.get("name", "")),
                        "key": key,
                        "type": str(field.get("type", "")),
                        "required": bool(field.get("required", False)),
                        "options": field.get("options", []) or [],
                    }
                )

            plan.append(
                {
                    "field": str(field.get("label", "")),
                    "key": key,
                    "name": str(field.get("name", "")),
                    "selector": str(field.get("selector", "")),
                    "xpath": str(field.get("xpath", "")),
                    "tag": str(field.get("tag", "")),
                    "type": str(field.get("type", "")),
                    "options": field.get("options", []) or [],
                    "radio_options": field.get("radio_options", []) or [],
                    "value": value,
                }
            )

        return plan, missing

    def _infer_key(self, field: dict[str, Any]) -> str:
        label = str(field.get("label", ""))
        name = str(field.get("name", ""))
        placeholder = str(field.get("placeholder", ""))
        aria_label = str(field.get("aria_label", ""))

        haystack = " ".join([label, name, placeholder, aria_label]).strip()
        normalized = self._normalize_text(haystack)
        field_type = str(field.get("type", "")).strip().lower()

        if field_type == "email":
            return "email"
        if field_type in {"tel", "phone"}:
            return "phone"
        if field_type == "file":
            return "resume_path"
        if field_type == "url":
            if "linkedin" in normalized:
                return "linkedin"
            if "github" in normalized:
                return "github"
            return "website"

        for alias, canonical in self.FIELD_ALIASES.items():
            alias_norm = self._normalize_text(alias)
            if alias_norm and alias_norm in normalized:
                return canonical

        if "first name" in normalized:
            return "first_name"
        if "last name" in normalized:
            return "last_name"
        if "cover" in normalized and "letter" in normalized:
            return "cover_letter"
        if "summary" in normalized or "about" in normalized:
            return "summary"

        custom_key = self._to_custom_key(label or name or "unknown_field")
        return f"custom:{custom_key}"

    @staticmethod
    def _resolve_value(field_key: str, answers: dict[str, str], custom_answers: dict[str, str]) -> str:
        if field_key in answers:
            return str(answers[field_key]).strip()
        if field_key.startswith("custom:"):
            custom_key = field_key.split("custom:", 1)[1]
            if custom_key in custom_answers:
                return str(custom_answers[custom_key]).strip()
        return ""

    @staticmethod
    def _needs_value(field: dict[str, Any], key: str) -> bool:
        field_type = str(field.get("type", "")).lower()
        if field_type in {"submit", "button", "reset", "file", "hidden"}:
            return key == "resume_path"
        if bool(field.get("required", False)):
            return True

        if key.startswith("custom:"):
            label = str(field.get("label", ""))
            normalized_label = FormFiller._normalize_text(label)
            if normalized_label.startswith("field ") or not normalized_label:
                return False
            return True

        return True

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = text.lower().replace("_", " ")
        cleaned = re.sub(r"[^a-z0-9\s]+", " ", lowered)
        return " ".join(cleaned.split())

    def _to_custom_key(self, text: str) -> str:
        normalized = self._normalize_text(text)
        return normalized.replace(" ", "_")
