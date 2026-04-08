"""Core automation package."""

from .job_parser import JobParser, JobPosting
from .easy_apply import EasyApplyBot
from .ai_engine import AIEngine

__all__ = ["AIEngine", "EasyApplyBot", "JobParser", "JobPosting"]
