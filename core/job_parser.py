from dataclasses import dataclass


@dataclass
class JobPosting:
    title: str
    company: str
    description: str = ""


def extract_job_details(page):
    try:
        title = page.locator("h1").inner_text()
    except:
        title = ""

    try:
        desc = page.locator("body").inner_text()
    except:
        desc = ""

    return {
        "title": title,
        "description": desc[:3000]
    }