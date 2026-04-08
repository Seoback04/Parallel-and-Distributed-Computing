from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .ai_engine import AIEngine
from .form_filler import FormFiller
from .job_parser import JobParser
from .profile_store import ProfileStore

__all__ = ["EasyApplyBot", "run_easy_apply"]


class EasyApplyBot:
    """Coordinates job parsing, answer generation, and form filling."""

    def __init__(
        self,
        ai_engine: AIEngine | None = None,
        job_parser: JobParser | None = None,
        form_filler: FormFiller | None = None,
        profile_store: ProfileStore | None = None,
    ) -> None:
        self.ai_engine = ai_engine or AIEngine()
        self.job_parser = job_parser or JobParser()
        self.form_filler = form_filler or FormFiller()
        self.profile_store = profile_store

    def prepare_application(
        self,
        profile: dict[str, Any],
        page_text: str,
        fields: list[dict[str, Any]],
        extra_answers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        job = self.job_parser.parse_text(page_text)
        ai_answers = self.ai_engine.build_answers(profile, job)
        learned_answers = {}
        custom_answers = {}
        if self.profile_store is not None:
            learned_answers = self.profile_store.get_learned_answers(profile)
            custom_answers = self.profile_store.get_custom_answers(profile)

        answers = {**ai_answers, **learned_answers, **(extra_answers or {})}
        fill_plan, missing_fields = self.form_filler.build_fill_plan(
            fields=fields,
            answers=answers,
            custom_answers=custom_answers,
        )

        return {
            "job": asdict(job),
            "answers": answers,
            "fill_plan": fill_plan,
            "missing_fields": missing_fields,
        }


def run_easy_apply(
    profile: dict[str, Any],
    page_text: str,
    fields: list[dict[str, Any]],
    profile_store: ProfileStore | None = None,
    extra_answers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Backward-compatible helper for callers that import `run_easy_apply`.
    """
    bot = EasyApplyBot(profile_store=profile_store)
    return bot.prepare_application(
        profile=profile,
        page_text=page_text,
        fields=fields,
        extra_answers=extra_answers,
    )
