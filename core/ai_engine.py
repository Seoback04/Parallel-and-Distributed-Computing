from __future__ import annotations

from typing import Any

from .job_parser import JobPosting

__all__ = ["AIEngine", "generate_cover_letter", "generate_answers"]


class AIEngine:
    """
    Generates answer candidates for application fields using only local logic.
    """

    def __init__(self, model: str = "local-free") -> None:
        self.model = model

    def build_answers(self, profile: dict[str, Any], job: JobPosting) -> dict[str, str]:
        return self._build_answers_locally(profile, job)

    @staticmethod
    def _build_answers_locally(profile: dict[str, Any], job: JobPosting) -> dict[str, str]:
        basics = profile.get("basics", {})
        preferences = profile.get("preferences", {})
        experience = profile.get("experience", [])

        full_name = str(basics.get("name", "")).strip()
        first_name, last_name = AIEngine._split_name(full_name)

        summary = str(basics.get("summary", "")).strip()
        if not summary:
            summary = (
                f"{full_name or 'Candidate'} is interested in"
                f" the {job.title or 'role'} opportunity"
                f"{f' at {job.company}' if job.company else ''}."
            )

        cover_letter = (
            f"Dear Hiring Team,\n\n"
            f"I am excited to apply for the {job.title or 'position'}"
            f"{f' at {job.company}' if job.company else ''}. "
            f"My background in {summary.lower()} makes me a strong fit for this role.\n\n"
            f"Thank you for your time and consideration.\n"
            f"{full_name}".strip()
        )

        return {
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "email": str(basics.get("email", "")),
            "phone": str(basics.get("phone", "")),
            "location": str(basics.get("location", "")),
            "city": str(basics.get("city", "")),
            "country": str(basics.get("country", "")),
            "linkedin": str(basics.get("linkedin", "")),
            "github": str(basics.get("github", "")),
            "website": str(basics.get("website", "")),
            "resume_url": str(basics.get("resume_url", "")),
            "resume_path": str(basics.get("resume_path", "")),
            "years_of_experience": str(len(experience)),
            "current_company": AIEngine._latest_experience_field(experience, "company"),
            "current_title": AIEngine._latest_experience_field(experience, "title"),
            "work_authorized": str(preferences.get("work_authorized", "")),
            "requires_sponsorship": str(preferences.get("requires_sponsorship", "")),
            "salary_expectation": str(preferences.get("salary_expectation", "")),
            "notice_period": str(preferences.get("notice_period", "")),
            "summary": summary,
            "cover_letter": cover_letter,
        }

    @staticmethod
    def _split_name(full_name: str) -> tuple[str, str]:
        parts = [part for part in full_name.split() if part]
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], " ".join(parts[1:])

    @staticmethod
    def _latest_experience_field(experience: list[Any], key: str) -> str:
        if not experience:
            return ""
        latest = experience[0] if isinstance(experience[0], dict) else {}
        return str(latest.get(key, "")) if isinstance(latest, dict) else ""


def generate_cover_letter(job_desc: str, profile: dict[str, Any] | str) -> str:
    """
    Backward-compatible helper for older calls in this project.
    Uses local fallback text when structured generation is unavailable.
    """
    if not str(job_desc).strip():
        return "I am interested in this opportunity and believe my background is a strong match."
    return (
        "Dear Hiring Team,\n\n"
        "I am excited to apply for this opportunity. "
        "My background and hands-on experience align well with the role requirements.\n\n"
        "Thank you for your consideration."
    )


def generate_answers(job_desc: str) -> str:
    """Backward-compatible helper for generic text answers."""
    if not str(job_desc).strip():
        return "I am motivated to contribute and grow in this role."
    return (
        "Why this role: It aligns with my skills and long-term growth goals.\n"
        "Why hire me: I bring hands-on automation experience and consistent execution."
    )
