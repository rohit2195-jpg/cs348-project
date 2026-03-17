"""
Analyst_Team/macro_collector.py
══════════════════════════════════════════════════════════════════════════════
Collects geopolitical and macroeconomic news from reliable RSS feeds.

Stores into the existing raw_news table using:
  ticker = "MACRO"
  source = "reuters_world" | "bbc_world" | "ap_world" | "ft_markets" | etc.

No new DB schema needed. Downstream agents query:
  get_recent_news_for_ticker("MACRO", hours=24)

Sources (all free, no API keys, consistently reliable):
  - Reuters world news RSS
  - BBC News world RSS
  - Associated Press top news RSS
  - Financial Times markets RSS
  - CNBC world markets RSS
  - Politico economy RSS  (US policy, tariffs, sanctions)

Why these over Google News:
  - These are official publisher RSS feeds — not scraped search results
  - They don't rate-limit or block automated access
  - They cover geopolitical events that move markets (tariffs, sanctions, wars)
══════════════════════════════════════════════════════════════════════════════
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ssl
import certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import feedparser
import logging
import time
from datetime import datetime
from bs4 import BeautifulSoup
from database import insert_raw_news
from Analyst_Team.browser import BrowserManager

logger = logging.getLogger(__name__)

BODY_PREVIEW_CHARS = 600
MAX_PER_FEED       = 20

# ── Feed registry ─────────────────────────────────────────────────────────────
# Each entry: (source_key, url, description)
# All verified to return entries as of early 2025.

# ── RSS feeds — stable publisher feeds that don't need a browser ─────────────

RSS_FEEDS = [
    (
        "bbc_world",
        "http://feeds.bbci.co.uk/news/world/rss.xml",
        "BBC World — international events, conflicts, diplomacy",
    ),
    (
        "ap_world",
        "https://feeds.apnews.com/rss/apf-worldnews",
        "AP world news — direct official feed, no proxy",
    ),
    (
        "ap_top",
        "https://feeds.apnews.com/rss/apf-topnews",
        "AP top news — breaking stories",
    ),
    (
        "npr_world",
        "https://feeds.npr.org/1004/rss.xml",
        "NPR World — US policy, economy, international",
    ),
    (
        "guardian_world",
        "https://www.theguardian.com/world/rss",
        "The Guardian World — international events, geopolitics",
    ),
    (
        "aljazeera",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "Al Jazeera — geopolitics, conflicts, trade",
    ),
    (
        "ft_world",
        "https://www.ft.com/world?format=rss",
        "Financial Times world — geopolitics, trade",
    ),
]

# ── Playwright sources — JS-rendered, RSS is unreliable or dead ──────────────

def _fetch_reuters_macro_pw(bm: BrowserManager) -> list[dict]:
    """Reuters world news via Playwright — JS-rendered, requests gets skeleton HTML."""
    url  = "https://www.reuters.com/world/"
    html = bm.get_page_html(
        url,
        wait_for = "li[class*='story'], div[class*='story-content'], article",
        wait_ms  = 2500,
    )
    if not html:
        return []

    soup     = BeautifulSoup(html, "html.parser")
    articles = []
    for item in soup.select(
        "li[class*='story'], div[class*='story-content'], article[class*='story']"
    )[:MAX_PER_FEED]:
        link = item.find("a")
        if not link:
            continue
        title = link.get_text(strip=True)
        href  = link.get("href", "")
        if not title or len(title) < 15:
            continue
        if not _is_relevant(title, ""):
            continue
        ts_tag  = item.find("time")
        pub_str = ts_tag.get("datetime", "") if ts_tag else ""
        summary_tag = item.find("p")
        summary = summary_tag.get_text(strip=True)[:BODY_PREVIEW_CHARS] if summary_tag else ""
        articles.append({
            "title":        title,
            "url":          href if href.startswith("http") else f"https://www.reuters.com{href}",
            "published":    pub_str,
            "body_summary": summary,
        })

    logger.info(f"[macro] reuters_world_pw: {len(articles)} relevant articles")
    return articles


def _fetch_cnbc_macro_pw(bm: BrowserManager) -> list[dict]:
    """CNBC world + economy news via Playwright."""
    articles = []
    for section_url in [
        "https://www.cnbc.com/world/?region=world",
        "https://www.cnbc.com/economy/",
    ]:
        html = bm.get_page_html(
            section_url,
            wait_for = "div.Card-titleContainer, div[class*='Card-title'], a[class*='card-title']",
            wait_ms  = 2000,
        )
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for item in soup.select(
            "div.Card-titleContainer, div[class*='LatestNews'], div[class*='card-title-container']"
        )[:MAX_PER_FEED]:
            link = item.find("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href  = link.get("href", "")
            if not title or len(title) < 15:
                continue
            if not _is_relevant(title, ""):
                continue
            articles.append({
                "title":        title,
                "url":          href if href.startswith("http") else f"https://www.cnbc.com{href}",
                "published":    "",
                "body_summary": "",
            })
        time.sleep(0.8)

    logger.info(f"[macro] cnbc_pw: {len(articles)} relevant articles")
    return articles

# Keywords that flag an article as market-relevant geopolitical/macro news.
# Articles without any of these are skipped to reduce noise.
RELEVANCE_KEYWORDS = [
    # Trade & tariffs
    "tariff", "tariffs", "trade war", "trade deal", "import duty", "export ban",
    "export control", "sanctions", "sanction", "embargo", "trade restriction",
    # Geopolitical
    "war", "conflict", "invasion", "military", "nato", "missile", "attack",
    "ceasefire", "occupation", "nuclear", "geopolit",
    # Macro / central banks
    "federal reserve", "fed rate", "interest rate", "rate hike", "rate cut",
    "inflation", "cpi", "gdp", "recession", "unemployment", "jobs report",
    "central bank", "ecb", "bank of england", "boj", "pboc",
    # Energy & commodities
    "oil price", "opec", "crude", "natural gas", "commodity", "supply chain",
    "chip", "semiconductor", "rare earth",
    # Key regions that move markets
    "china", "russia", "iran", "north korea", "taiwan", "ukraine",
    "middle east", "europe", "eurozone",
]


def _is_relevant(title: str, summary: str) -> bool:
    """Returns True if the article likely has market-moving implications."""
    combined = (title + " " + summary).lower()
    return any(kw in combined for kw in RELEVANCE_KEYWORDS)


def _parse_feed(source_key: str, url: str) -> list[dict]:
    """
    Parses one RSS feed and returns filtered article dicts.

    Pre-fetches with requests so we control encoding before feedparser
    sees the XML — fixes Politico and other feeds with encoding issues.
    feedparser.bozo=True with entries present is fine (minor XML warning);
    we only bail if bozo=True AND no entries at all.
    """
    import requests as _requests

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
    }

    try:
        # Fetch with retry adapter — handles transient DNS/connection blips
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        session = _requests.Session()
        retry   = Retry(total=3, backoff_factor=1,
                        status_forcelist=[429, 500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.mount("http://",  HTTPAdapter(max_retries=retry))
        resp = session.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        # Force UTF-8 decoding; replace undecodable bytes rather than erroring
        xml_text = resp.content.decode("utf-8", errors="replace")
        feed     = feedparser.parse(xml_text)

        # bozo=True with zero entries = genuinely broken feed, skip it
        # bozo=True with entries = minor XML warning, still usable
        if feed.bozo and not feed.entries:
            logger.warning(
                f"[macro] {source_key}: feed error — "
                f"{getattr(feed, 'bozo_exception', 'unknown')}"
            )
            return []

        articles = []
        for entry in feed.entries[:MAX_PER_FEED]:
            title   = entry.get("title", "").strip()
            summary = BeautifulSoup(
                entry.get("summary", ""), "html.parser"
            ).get_text(strip=True)

            if not title:
                continue
            if not _is_relevant(title, summary):
                continue

            articles.append({
                "title":        title,
                "url":          entry.get("link", ""),
                "published":    entry.get("published", ""),
                "body_summary": summary[:BODY_PREVIEW_CHARS],
            })

        logger.info(f"[macro] {source_key}: {len(articles)} relevant articles")
        return articles

    except Exception as e:
        logger.warning(f"[macro] {source_key}: failed — {e}")
        return []


# ── Main entry point ──────────────────────────────────────────────────────────

def collect_macro_news(delay: float = 0.5) -> dict:
    """
    Collects geopolitical/macro news from all sources and stores under ticker="MACRO".

    RSS feeds (BBC, AP, Politico, FT) run directly.
    Reuters and CNBC use Playwright — both are JS-rendered.

    Returns summary dict with counts per source and total_inserted.
    """
    by_source   = {}
    total_fetch = 0
    total_ins   = 0

    # ── RSS feeds ─────────────────────────────────────────────────────────────
    for source_key, url, _ in RSS_FEEDS:
        articles = _parse_feed(source_key, url)
        inserted = insert_raw_news("MACRO", source_key, articles)
        by_source[source_key] = inserted
        total_fetch += len(articles)
        total_ins   += inserted
        if delay > 0:
            time.sleep(delay)

    # ── Playwright sources ────────────────────────────────────────────────────
    try:
        with BrowserManager(headless=True) as bm:
            reuters_articles = _fetch_reuters_macro_pw(bm)
            time.sleep(0.8)
            cnbc_articles    = _fetch_cnbc_macro_pw(bm)

        rt_ins = insert_raw_news("MACRO", "reuters_world", reuters_articles)
        cn_ins = insert_raw_news("MACRO", "cnbc",          cnbc_articles)

        by_source["reuters_world"] = rt_ins
        by_source["cnbc"]          = cn_ins
        total_fetch += len(reuters_articles) + len(cnbc_articles)
        total_ins   += rt_ins + cn_ins

    except Exception as e:
        logger.error(f"[macro] Playwright session failed: {e}")

    logger.info(f"[macro] Total: {total_ins} new articles inserted ({total_fetch} fetched)")
    return {
        "total_fetched":  total_fetch,
        "total_inserted": total_ins,
        "by_source":      by_source,
    }


def get_macro_headlines_text(hours: int = 24, limit: int = 40) -> str:
    """
    Returns a formatted string of recent macro headlines ready to inject
    into an LLM prompt. Called by both the news analyst and macro analyst agents.
    """
    from database import get_recent_news_for_ticker
    articles = get_recent_news_for_ticker("MACRO", hours=hours, limit=limit)
    if not articles:
        return "No recent macro/geopolitical news collected."

    lines = [f"=== Macro & Geopolitical Headlines (last {hours}h) ===\n"]
    for i, a in enumerate(articles, 1):
        lines.append(f"{i}. [{a['source']}] {a['title']}")
        if a.get("published"):
            lines.append(f"   {a['published']}")
        if a.get("body_summary"):
            lines.append(f"   {a['body_summary'][:200]}")
        lines.append("")
    return "\n".join(lines)


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from database import Base, engine
    Base.metadata.create_all(bind=engine)

    result = collect_macro_news()
    print(f"\nMacro collection result:")
    print(f"  Total fetched:  {result['total_fetched']}")
    print(f"  Total inserted: {result['total_inserted']}")
    for src, count in result["by_source"].items():
        print(f"  {src:<25} {count} new")

    print("\nSample headlines:")
    print(get_macro_headlines_text(hours=24, limit=5))