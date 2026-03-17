"""
Analyst_Team/browser.py
══════════════════════════════════════════════════════════════════════════════
Shared Playwright browser manager.

One browser instance is launched per collection run and reused across all
sources and all tickers — no per-page browser startup overhead.

Usage (called by news_collector.py and macro_collector.py):

    from Analyst_Team.browser import BrowserManager

    with BrowserManager() as bm:
        html = bm.get_page_html("https://example.com")
        html2 = bm.get_page_html("https://example2.com", wait_for="table.news")

Design decisions:
  - Headless Chromium (bundled with Playwright, no system Chrome needed)
  - Single persistent context with realistic browser fingerprint
  - wait_for_selector before returning HTML — handles JS-rendered content
  - Per-page timeout of 20s; on failure returns empty string (never raises)
  - Stealth headers to reduce bot detection
══════════════════════════════════════════════════════════════════════════════
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
import time
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

# Realistic Mac Chrome fingerprint
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

VIEWPORT        = {"width": 1280, "height": 800}
PAGE_TIMEOUT_MS = 20_000       # 20s max per page
NAV_TIMEOUT_MS  = 25_000       # 25s navigation timeout


class BrowserManager:
    """
    Context manager that owns a single Playwright browser for the duration
    of a collection run. All fetch calls share the same browser instance.

    with BrowserManager() as bm:
        html = bm.get_page_html(url)
    """

    def __init__(self, headless: bool = True, slow_mo: int = 0):
        self.headless   = headless
        self.slow_mo    = slow_mo
        self._playwright = None
        self._browser:   Browser        | None = None
        self._context:   BrowserContext | None = None

    def __enter__(self) -> "BrowserManager":
        self._playwright = sync_playwright().start()
        self._browser    = self._playwright.chromium.launch(
            headless = self.headless,
            slow_mo  = self.slow_mo,
            args     = [
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        )
        self._context = self._browser.new_context(
            user_agent         = USER_AGENT,
            viewport           = VIEWPORT,
            locale             = "en-US",
            timezone_id        = "America/New_York",
            # Pretend to be a normal browser, not a bot
            java_script_enabled = True,
            extra_http_headers  = {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        # Hide webdriver flag — basic anti-bot measure
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        logger.debug("[browser] Playwright browser launched")
        return self

    def __exit__(self, *args):
        try:
            if self._context:  self._context.close()
            if self._browser:  self._browser.close()
            if self._playwright: self._playwright.stop()
        except Exception:
            pass
        logger.debug("[browser] Playwright browser closed")

    def get_page_html(
        self,
        url:          str,
        wait_for:     str | None = None,   # CSS selector to wait for before extracting
        wait_ms:      int        = 1500,   # extra ms to wait after selector appears
        scroll:       bool       = False,  # scroll to bottom to trigger lazy-load
        timeout_ms:   int        = PAGE_TIMEOUT_MS,
    ) -> str:
        """
        Navigates to url, waits for JS to render, returns full page HTML.
        Returns empty string on any error — never raises.
        """
        page: Page | None = None
        try:
            page = self._context.new_page()
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(NAV_TIMEOUT_MS)

            page.goto(url, wait_until="domcontentloaded")

            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=timeout_ms)
                except PWTimeout:
                    logger.debug(f"[browser] selector '{wait_for}' not found on {url}")

            if wait_ms > 0:
                page.wait_for_timeout(wait_ms)

            if scroll:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(800)

            return page.content()

        except PWTimeout:
            logger.warning(f"[browser] Timeout loading {url}")
            return ""
        except Exception as e:
            logger.warning(f"[browser] Error loading {url}: {e}")
            return ""
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass

    def get_text_content(self, url: str, selector: str, **kwargs) -> str:
        """
        Convenience: returns innerText of the first matching selector.
        Useful for grabbing a single element's text without parsing full HTML.
        """
        html = self.get_page_html(url, wait_for=selector, **kwargs)
        if not html:
            return ""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        el   = soup.select_one(selector)
        return el.get_text(strip=True) if el else ""