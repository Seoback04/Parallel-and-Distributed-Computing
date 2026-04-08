from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.common.exceptions import SessionNotCreatedException

from config import PAGE_SETTLE_SECONDS
from utils.selectors import (
    CONTINUE_TERMS,
    EASY_APPLY_TERMS,
    EXTERNAL_APPLY_TERMS,
    SUBMIT_TERMS,
)

__all__ = ["BrowserSession", "start_browser"]


class BrowserSession:
    """Manages a Selenium browser session for job application automation."""

    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        self.driver: webdriver.Chrome | None = None
        self._brave_path = self._find_brave_path()
        self._chrome_driver_path = self._find_chromedriver_path()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        use_profile = not self.headless
        try:
            self.driver = self._create_driver(use_profile=use_profile)
        except SessionNotCreatedException:
            self.driver = self._create_driver(use_profile=False)

    def stop(self) -> None:
        if self.driver:
            self.driver.quit()
            self.driver = None

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def open(self, url: str) -> None:
        self._require_driver().get(url)

    def wait_for_page_settle(self, seconds: float | None = None) -> None:
        wait_time = seconds if seconds is not None else PAGE_SETTLE_SECONDS
        time.sleep(wait_time)
        driver = self._require_driver()
        try:
            WebDriverWait(driver, 5).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_apply_type(self) -> str:
        body_text = self._require_driver().find_element(By.TAG_NAME, "body").text.lower()
        for term in EASY_APPLY_TERMS:
            if term in body_text:
                return "easy_apply"
        return "external_apply"

    # ------------------------------------------------------------------
    # Clicking
    # ------------------------------------------------------------------

    def click_apply_entry(self, apply_type: str) -> bool:
        terms = EASY_APPLY_TERMS if apply_type == "easy_apply" else EXTERNAL_APPLY_TERMS
        return self._click_button_by_terms(terms)

    def click_next_step(self) -> bool:
        return self._click_button_by_terms(CONTINUE_TERMS)

    def click_submit(self) -> bool:
        return self._click_button_by_terms(SUBMIT_TERMS)

    # ------------------------------------------------------------------
    # Page content
    # ------------------------------------------------------------------

    def extract_page_text(self) -> str:
        try:
            return self._require_driver().find_element(By.TAG_NAME, "body").text
        except Exception:
            return ""

    def collect_inputs(self) -> list[dict[str, Any]]:
        driver = self._require_driver()
        fields: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for tag in ("input", "textarea", "select"):
            for element in driver.find_elements(By.TAG_NAME, tag):
                try:
                    if not element.is_displayed():
                        continue
                except Exception:
                    continue

                elem_id = element.get_attribute("id") or ""
                name = element.get_attribute("name") or ""
                unique_key = f"{tag}:{elem_id}:{name}"
                if unique_key in seen_ids:
                    continue
                seen_ids.add(unique_key)

                field_type = (element.get_attribute("type") or tag).lower()
                if field_type in ("hidden", "submit", "button", "image"):
                    continue

                label_text = self._find_label(element)
                options = self._get_options(element, tag) if tag == "select" else []

                fields.append({
                    "tag": tag,
                    "type": field_type,
                    "name": name,
                    "id": elem_id,
                    "label": label_text,
                    "placeholder": element.get_attribute("placeholder") or "",
                    "aria_label": element.get_attribute("aria-label") or "",
                    "required": element.get_attribute("required") is not None,
                    "options": options,
                    "selector": f"#{elem_id}" if elem_id else "",
                    "xpath": self._build_xpath(element, tag, name, elem_id),
                })

        return fields

    # ------------------------------------------------------------------
    # Form filling
    # ------------------------------------------------------------------

    def apply_fill_plan(self, fill_plan: list[dict[str, Any]]) -> None:
        driver = self._require_driver()
        for item in fill_plan:
            value = str(item.get("value", "")).strip()
            if not value:
                continue

            element = self._locate_field(driver, item)
            if element is None:
                continue

            try:
                tag = item.get("tag", "").lower()
                field_type = item.get("type", "").lower()

                if tag == "select":
                    self._fill_select(element, value)
                elif field_type == "file":
                    element.send_keys(value)
                elif field_type in ("checkbox", "radio"):
                    self._fill_check_or_radio(driver, item, value)
                else:
                    element.clear()
                    element.send_keys(value)
            except Exception:
                continue

    # ------------------------------------------------------------------
    # Screenshot
    # ------------------------------------------------------------------

    def save_screenshot(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._require_driver().save_screenshot(str(path))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_driver(self) -> webdriver.Chrome:
        if self.driver is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self.driver

    @staticmethod
    def _find_brave_path() -> str:
        """Locate Brave browser executable on Windows."""
        common_paths = [
            os.path.join(os.getenv("PROGRAMFILES", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(os.getenv("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
        return ""

    @staticmethod
    def _find_chromedriver_path() -> str:
        cache_dir = Path(".selenium-cache/chromedriver")
        if cache_dir.exists():
            matches = sorted(cache_dir.rglob("chromedriver.exe"), reverse=True)
            if matches:
                return str(matches[0].resolve())
        return ""

    def _create_driver(self, use_profile: bool) -> webdriver.Chrome:
        opts = Options()
        if self._brave_path:
            opts.binary_location = self._brave_path

        if self.headless:
            opts.add_argument("--headless=new")

        opts.add_argument("--disable-gpu")
        opts.add_argument("--start-maximized")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--remote-debugging-port=9222")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])

        if use_profile and self._brave_path:
            user_data_dir = os.path.join(
                os.getenv("LOCALAPPDATA", ""),
                "BraveSoftware",
                "Brave-Browser",
                "User Data",
            )
            if os.path.exists(user_data_dir):
                opts.add_argument(f"--user-data-dir={user_data_dir}")
                opts.add_argument("--profile-directory=Default")

        if self._chrome_driver_path:
            service = Service(self._chrome_driver_path)
            return webdriver.Chrome(service=service, options=opts)

        return webdriver.Chrome(options=opts)

    def _click_button_by_terms(self, terms: list[str]) -> bool:
        driver = self._require_driver()
        clickable = driver.find_elements(By.TAG_NAME, "button") + driver.find_elements(
            By.CSS_SELECTOR, "a[role='button'], input[type='submit'], input[type='button']"
        )
        for element in clickable:
            try:
                text = (element.text or element.get_attribute("aria-label") or "").lower()
                for term in terms:
                    if term in text:
                        element.click()
                        return True
            except Exception:
                continue
        return False

    @staticmethod
    def _find_label(element: WebElement) -> str:
        elem_id = element.get_attribute("id") or ""
        if elem_id:
            try:
                driver = element.parent
                labels = driver.find_elements(By.CSS_SELECTOR, f"label[for='{elem_id}']")
                if labels:
                    return labels[0].text.strip()
            except Exception:
                pass

        try:
            parent = element.find_element(By.XPATH, "..")
            labels = parent.find_elements(By.TAG_NAME, "label")
            if labels:
                return labels[0].text.strip()
        except Exception:
            pass

        return element.get_attribute("aria-label") or element.get_attribute("placeholder") or ""

    @staticmethod
    def _get_options(element: WebElement, tag: str) -> list[str]:
        if tag != "select":
            return []
        try:
            select = Select(element)
            return [opt.text.strip() for opt in select.options if opt.text.strip()]
        except Exception:
            return []

    @staticmethod
    def _build_xpath(element: WebElement, tag: str, name: str, elem_id: str) -> str:
        if elem_id:
            return f"//{tag}[@id='{elem_id}']"
        if name:
            return f"//{tag}[@name='{name}']"
        return ""

    @staticmethod
    def _locate_field(driver: webdriver.Chrome, item: dict[str, Any]) -> WebElement | None:
        selector = item.get("selector", "")
        xpath = item.get("xpath", "")
        name = item.get("name", "")

        if selector:
            try:
                return driver.find_element(By.CSS_SELECTOR, selector)
            except Exception:
                pass

        if xpath:
            try:
                return driver.find_element(By.XPATH, xpath)
            except Exception:
                pass

        if name:
            try:
                return driver.find_element(By.NAME, name)
            except Exception:
                pass

        return None

    @staticmethod
    def _fill_select(element: WebElement, value: str) -> None:
        select = Select(element)
        value_lower = value.lower()
        for option in select.options:
            if option.text.strip().lower() == value_lower:
                select.select_by_visible_text(option.text.strip())
                return
        for option in select.options:
            if value_lower in option.text.strip().lower():
                select.select_by_visible_text(option.text.strip())
                return

    @staticmethod
    def _fill_check_or_radio(driver: webdriver.Chrome, item: dict[str, Any], value: str) -> None:
        name = item.get("name", "")
        if not name:
            return
        value_lower = value.lower()
        elements = driver.find_elements(By.NAME, name)
        for el in elements:
            label_text = ""
            try:
                parent = el.find_element(By.XPATH, "..")
                label_text = parent.text.strip().lower()
            except Exception:
                pass

            el_value = (el.get_attribute("value") or "").lower()
            if value_lower in label_text or value_lower == el_value:
                if not el.is_selected():
                    el.click()
                return


def start_browser() -> tuple[Any, webdriver.Chrome, Any]:
    """Backward-compatible helper that returns (None, driver, driver).

    Old callers used ``p, browser, page = start_browser()``.
    With Selenium there is no separate playwright handle or page object,
    so the driver is returned in place of both *browser* and *page*.
    """
    session = BrowserSession(headless=False)
    session.start()
    driver = session.driver
    return None, driver, driver
