from __future__ import annotations

from dataclasses import dataclass
import re

__all__ = ["JobPosting", "JobParser"]


@dataclass(slots=True)
class JobPosting:
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""


class JobParser:
    """Extracts lightweight job metadata from raw page text."""

    TITLE_PATTERNS = (
        re.compile(r"Title\s*:\s*(.+)", re.IGNORECASE),
        re.compile(r"Role\s*:\s*(.+)", re.IGNORECASE),
    )
    COMPANY_PATTERNS = (
        re.compile(r"Company\s*:\s*(.+)", re.IGNORECASE),
        re.compile(r"Employer\s*:\s*(.+)", re.IGNORECASE),
    )
    LOCATION_PATTERNS = (
        re.compile(r"Location\s*:\s*(.+)", re.IGNORECASE),
        re.compile(r"Based in\s*:\s*(.+)", re.IGNORECASE),
    )

    def parse_text(self, raw_text: str) -> JobPosting:
        clean_text = (raw_text or "").strip()
        lines = [line.strip() for line in clean_text.splitlines() if line.strip()]

        return JobPosting(
            title=self._extract_first_match(lines, self.TITLE_PATTERNS) or self._guess_title(lines),
            company=self._extract_first_match(lines, self.COMPANY_PATTERNS),
            location=self._extract_first_match(lines, self.LOCATION_PATTERNS),
            description=clean_text,
        )

    @staticmethod
    def _extract_first_match(lines: list[str], patterns: tuple[re.Pattern[str], ...]) -> str:
        for line in lines:
            for pattern in patterns:
                match = pattern.search(line)
                if match:
                    return match.group(1).strip()
        return ""

    @staticmethod
    def _guess_title(lines: list[str]) -> str:
        for line in lines[:10]:
            if 3 <= len(line.split()) <= 8 and len(line) < 100:
                return line
        return ""
