from __future__ import annotations

from typing import Any

from .ai_engine import generate_cover_letter
from .profile_store import ProfileStore

__all__ = ["EasyApplyBot", "run_easy_apply"]


def run_easy_apply(page):
    try:
        page.click("text=Easy Apply")
    except:
        return False

    for _ in range(5):
        try:
            page.click("text=Next")
        except:
            break

    return True


class EasyApplyBot:
    FIELD_KEY_MAP: dict[str, list[str]] = {
        "full_name": ["full name", "name"],
        "first_name": ["first name", "given name"],
        "last_name": ["last name", "family name", "surname"],
        "email": ["email", "e-mail", "e mail"],
        "phone": ["phone", "mobile", "telephone", "contact number"],
        "location": ["location", "city", "address", "country"],
        "linkedin": ["linkedin"],
        "github": ["github"],
        "website": ["website", "portfolio", "site"],
        "resume_path": ["resume", "cv", "upload resume", "attach resume", "file upload"],
        "resume_file": ["resume", "cv", "upload resume", "attach resume", "file upload"],
        "cover_letter": ["cover letter", "motivation", "why this role", "why you", "message"],
        "summary": ["summary", "about you", "about me", "profile"],
        "work_authorized": ["work authorized", "work authorization", "authorized to work", "eligible to work"],
        "requires_sponsorship": ["sponsorship", "need sponsor", "requires sponsorship", "work visa"],
        "salary_expectation": ["salary", "compensation", "expected pay", "desired salary", "pay range"],
        "notice_period": ["notice period", "availability", "start date", "available to start"],
        "current_company": ["current company", "employer", "company"],
        "current_title": ["current title", "current role", "position"],
        "role": ["role", "position", "job title"],
    }

    def __init__(self, profile_store: ProfileStore | None = None) -> None:
        self.profile_store = profile_store

    def prepare_application(
        self,
        profile: dict[str, Any],
        page_text: str,
        fields: list[dict[str, Any]],
        extra_answers: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        answers = self._build_answers(profile, extra_answers or {}, page_text)
        fill_plan: list[dict[str, Any]] = []
        missing_fields: list[dict[str, Any]] = []

        for field in fields:
            value = self._resolve_field_value(field, answers, page_text)
            if value:
                fill_plan.append({
                    "tag": field.get("tag", ""),
                    "type": field.get("type", ""),
                    "name": field.get("name", ""),
                    "id": field.get("id", ""),
                    "selector": field.get("selector", ""),
                    "xpath": field.get("xpath", ""),
                    "value": value,
                })
            elif field.get("required"):
                missing_fields.append(
                    {
                        "key": self._field_key(field),
                        "label": field.get("label") or field.get("name") or field.get("placeholder") or "",
                        "options": field.get("options", []) or [],
                    }
                )

        return {
            "fill_plan": fill_plan,
            "missing_fields": missing_fields,
            "answers": answers,
        }

    def _build_answers(
        self,
        profile: dict[str, Any],
        extra_answers: dict[str, Any],
        page_text: str,
    ) -> dict[str, str]:
        learned: dict[str, str] = {}
        if self.profile_store is not None:
            learned.update(self.profile_store.get_custom_answers(profile))
            learned.update(self.profile_store.get_learned_answers(profile))

        basics = profile.get("basics", {}) if isinstance(profile.get("basics"), dict) else {}
        preferences = profile.get("preferences", {}) if isinstance(profile.get("preferences"), dict) else {}
        job_preferences = profile.get("job_preferences", {}) if isinstance(profile.get("job_preferences"), dict) else {}

        answers: dict[str, str] = {}
        for key, value in {**basics, **preferences, **job_preferences, **learned, **extra_answers}.items():
            if value is None:
                continue
            answers[str(key).lower()] = str(value).strip()

        # Keep resume helpers available under both keys.
        if "resume_path" in answers and "resume_file" not in answers:
            answers["resume_file"] = answers["resume_path"]
        if "resume_file" in answers and "resume_path" not in answers:
            answers["resume_path"] = answers["resume_file"]

        if "cover_letter" not in answers and page_text:
            answers["cover_letter"] = generate_cover_letter(page_text, profile)

        return answers

    def _resolve_field_value(
        self,
        field: dict[str, Any],
        answers: dict[str, str],
        page_text: str,
    ) -> str:
        parts = [
            str(field.get("label", "")),
            str(field.get("name", "")),
            str(field.get("placeholder", "")),
            str(field.get("aria_label", "")),
        ]
        field_text = " ".join(part.lower() for part in parts if part).replace("_", " ").replace("-", " ")

        if not field_text:
            return ""

        field_type = str(field.get("type", "")).lower()
        tag = str(field.get("tag", "")).lower()

        if field_type == "file":
            return answers.get("resume_file", "") or answers.get("resume_path", "")

        if any(term in field_text for term in ["cover letter", "coverletter", "why this role", "motivation", "about you", "message"]):
            return answers.get("cover_letter", "")

        for key, synonyms in self.FIELD_KEY_MAP.items():
            if any(term in field_text for term in synonyms):
                return answers.get(key, "")

        for key, value in answers.items():
            if not value:
                continue
            if key in field_text:
                return value

        if tag == "select" and field.get("options"):
            options = [str(opt).strip() for opt in field.get("options", []) if str(opt).strip()]
            for option in options:
                option_lower = option.lower()
                if any(answer_value.lower() in option_lower for answer_value in answers.values() if answer_value):
                    return option
            return options[0] if options else ""

        return ""

    @staticmethod
    def _field_key(field: dict[str, Any]) -> str:
        return str(field.get("name") or field.get("id") or field.get("label") or field.get("placeholder") or "").strip()
