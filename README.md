# Job Bot v2
Job Bot v2 is a Windows desktop automation project for speeding up job applications. It combines a Tkinter GUI, Selenium browser automation, local answer generation, profile persistence, and flow-specific form handling to reduce repeated manual entry across job sites.

The primary path is the GUI in `app_gui.py`. It loads your profile, opens the target job page in Brave, detects whether the page is an Easy Apply or external application flow, fills recognized fields, prompts for missing answers, saves a screenshot for review, and only submits after confirmation.

## What this project does
- opens job pages in Brave using your existing Brave profile
- keeps you logged in by reusing the default Brave user data directory
- stores profile details and learned answers in `profile.json`
- copies selected resumes into the project data folder for consistent reuse
- extracts visible form fields from pages and maps them to known profile values
- supports both direct job links and simple auto-search mode
- handles multi-step Easy Apply flows and standard external apply flows
- saves generated cover letters and review screenshots

## What this project is not
- not a guaranteed one-click submit bot for every job site
- not a cloud service or remote runner
- not a replacement for manual review on dynamic or custom-built forms
- not a stealth scraper or anti-detection system

## Main components
### GUI application
`app_gui.py` is the main user-facing entry point.

The GUI includes:
- profile JSON picker
- resume picker
- role input
- location input
- job source selection
- job URL input
- headless toggle
- execution log

### Browser layer
`core/browser.py` contains `BrowserSession`.

It is responsible for:
- locating Brave
- starting the Selenium session
- reusing the default Brave profile
- opening pages
- collecting inputs
- clicking common buttons such as apply, next, continue, review, and submit
- filling text, select, checkbox, radio, and file inputs
- saving screenshots

### Data and profile storage
`core/profile_store.py` normalizes and persists applicant data.

It keeps:
- `basics`
- `preferences`
- `job_preferences`
- `memory.learned_answers`
- `memory.custom_fields`

### Flow orchestration
The flow layer decides how a form is processed:
- `flows/easy_apply.py` for multi-step Easy Apply workflows
- `flows/external_apply.py` for normal external application pages

### Parsing and answer generation
- `core/job_parser.py` extracts lightweight job metadata
- `core/form_filler.py` maps page fields to profile answers
- `core/ai_engine.py` generates local fallback answers and cover letter text
- `core/job_search.py` handles auto-search using public web search results

## Requirements
- Windows
- Python 3.13 recommended
- Brave Browser installed
- internet access for dependency installation and auto-search

## Quick start
1. Clone the repository.
2. Create a virtual environment.
3. Install dependencies.
4. Review and update `profile.json`.
5. Launch the GUI.
6. Select your resume and start the workflow.

## Installation
Create the virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Current dependency list:

```text
selenium>=4.20.0
```

Selenium 4 is used for browser automation. Driver download and resolution may be handled automatically depending on the local setup.

## Running the project
### GUI
Recommended:

```powershell
python app_gui.py
```

Alternative launch scripts:

```powershell
.\start_job_bot_gui.bat
```

```powershell
.\Launch_JobBot_GUI.bat
```

`Launch_JobBot_GUI.bat` attempts dependency installation before launching the GUI with `pythonw`.

### CLI
There is also a basic CLI entry point:

```powershell
python main.py
```

The CLI is more limited than the GUI. It currently supports manual URL input and basic field filling, but the GUI is the intended primary workflow.

## Browser behavior
The browser layer is configured to prefer Brave.

Current behavior:
- searches standard Windows install locations for `brave.exe`
- sets Brave as the Selenium binary when found
- reuses the default Brave profile directory
- opens the job page in Brave so existing logins can be reused

Typical Brave profile path:
- `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data`

If Brave is not detected, Selenium may still start a Chrome-compatible session depending on local availability, but the intended setup is Brave.

## How the GUI workflow works
1. Select a `Profile JSON` file.
2. Select a `Resume File`.
3. Enter a target `Role`.
4. Optionally enter a `Location`.
5. Choose the job source:
   - `Paste Job Link`
   - `Auto Search Jobs`
6. If manual mode is selected, enter the target `Job URL`.
7. Optionally enable `Headless Browser`.
8. Click `Start`.

When the run starts, the app:
1. loads and normalizes profile data
2. validates the resume path
3. copies the selected resume into `data/resumes/`
4. saves updated preferences back to the profile
5. gets the target job URL directly or through auto-search
6. starts the browser session
7. detects the type of apply flow
8. collects visible form fields
9. generates answers and a fill plan
10. prompts for missing values when needed
11. fills the page
12. saves a review screenshot
13. asks whether to submit

The GUI writes progress to the `Execution Log`.

## Auto-search behavior
Auto-search uses `core/job_search.py`.

The query is built from:
- role
- location
- generic job terms

The current implementation:
- searches public DuckDuckGo HTML results
- scores likely matches
- prefers common job domains such as LinkedIn, Indeed, Greenhouse, Lever, Workday, and other jobs pages
- falls back to generated job search URLs if live results are unavailable

Auto-search is useful for discovery, but pasting a direct job URL is usually more reliable.

## Profile configuration
The project reads profile data from `profile.json` in the repository root.

The most important sections are:
- `basics`
- `preferences`
- `job_preferences`
- `memory`

Recommended minimum structure:

```json
{
  "basics": {
    "name": "Your Name",
    "first_name": "Your",
    "last_name": "Name",
    "email": "you@example.com",
    "phone": "+64XXXXXXXX",
    "location": "Auckland",
    "city": "Auckland",
    "country": "New Zealand",
    "linkedin": "https://linkedin.com/in/yourprofile",
    "github": "https://github.com/yourprofile",
    "website": "",
    "resume_url": "",
    "resume_path": "B:\\Bot\\data\\resumes\\your_resume.pdf",
    "summary": "Short professional summary"
  },
  "preferences": {
    "work_authorized": "Yes",
    "requires_sponsorship": "No",
    "salary_expectation": "",
    "notice_period": ""
  },
  "job_preferences": {
    "role": "Software Tester",
    "location": "Auckland"
  },
  "memory": {
    "learned_answers": {},
    "custom_fields": {},
    "custom_field_labels": {}
  }
}
```

Important note:
- the code normalizes the nested `basics`, `preferences`, `job_preferences`, and `memory` sections
- older top-level fields may still exist in a profile file, but the nested structure is what the current application logic uses

## Data written by the app
The application stores output under `data/`:

- `data/resumes/` for copied resume files
- `data/cover_letters/` for generated cover letter text files
- `data/screenshots/` for pre-submit review screenshots

This means the project keeps a local record of what resume was used and what artifacts were generated during runs.

## Repository structure
- `app_gui.py` — main desktop application
- `main.py` — CLI entry point
- `config.py` — shared paths and constants
- `core/browser.py` — Selenium browser session management
- `core/easy_apply.py` — answer generation and fill-plan preparation
- `core/form_filler.py` — field aliasing and fill-plan construction
- `core/job_parser.py` — simple job metadata extraction
- `core/job_search.py` — job discovery and ranking
- `core/profile_store.py` — profile persistence and learned answer storage
- `flows/easy_apply.py` — multi-step Easy Apply handling
- `flows/external_apply.py` — standard external apply handling
- `utils/selectors.py` — keyword lists used for button detection
- `data/` — runtime files such as resumes, screenshots, and cover letters

## Typical usage pattern
1. Keep your resume updated.
2. Keep `profile.json` filled with accurate details.
3. Stay logged into job platforms in Brave.
4. Launch the GUI.
5. Use a direct job URL for the most reliable result.
6. Review the generated screenshot before submitting.
7. Save learned answers when prompted so future runs require less manual work.

## Known limitations
- job sites change markup frequently
- many sites use highly custom JavaScript controls
- some fields cannot be detected from the visible DOM alone
- radio buttons and custom widgets may require manual finishing
- auto-search results are best-effort only
- generated cover letter text is simple local fallback text, not a full remote LLM workflow

## Troubleshooting
### Resume file not found
Use the `Browse` button and choose a valid resume file.

Supported GUI file types:
- `.pdf`
- `.doc`
- `.docx`
- `.txt`

### Job URL is required
If `Paste Job Link` is selected, the URL field must be filled before starting.

### No jobs found in auto-search
Use manual mode and paste the exact job page URL.

### Brave opens without the expected login session
- close all Brave windows completely
- confirm you are logged in inside the default Brave profile
- relaunch the app

### The app fills some fields but not all
This is expected on many real job sites. Use the prompt dialogs and finish any unsupported fields manually.

### Selenium starts but browser launch fails
Check:
- Python environment is activated
- `selenium` is installed
- Brave is installed
- no conflicting stale browser session is locking the profile

## Development notes
- the project is organized as a local desktop automation tool, not a packaged Python library
- the GUI path is the most complete path and should be treated as the reference workflow
- `main.py` exists for simple CLI testing but is not as complete as the GUI flow

## Summary
This repository is a practical local job application helper built around:
- a simple desktop UI
- Brave-based Selenium automation
- reusable profile memory
- multi-step form filling
- review-before-submit behavior

For most users, the fastest way to use the project is:
1. update `profile.json`
2. launch `app_gui.py`
3. paste a job URL
4. review the screenshot
5. submit manually or confirm submit in the app
