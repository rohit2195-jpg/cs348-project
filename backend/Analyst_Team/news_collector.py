"""
Analyst_Team/news_collector.py
══════════════════════════════════════════════════════════════════════════════
Hybrid news collection — Playwright for JS-rendered sites, yfinance direct.

  PLAYWRIGHT (JS-rendered, bot-detection-heavy):
    Finviz, MarketWatch, Nasdaq.com, Reuters, Benzinga

  DIRECT (no browser needed):
    yfinance .news  — internal API, most reliable, always works
    yfinance price  — price snapshot + fundamentals

One BrowserManager per collect_news_for_ticker() call — shared across all
Playwright sources for that ticker so the browser only launches once.

Install:
    pip install playwright beautifulsoup4 yfinance
    playwright install chromium
══════════════════════════════════════════════════════════════════════════════
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
import time
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import yfinance as yf

from database import insert_raw_news, insert_price_snapshot
from Analyst_Team.browser import BrowserManager

logger = logging.getLogger(__name__)

BODY_PREVIEW_CHARS      = 600
MAX_ARTICLES_PER_SOURCE = 15


# ══════════════════════════════════════════════════════════════════════════════
# DIRECT sources (no Playwright)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_yfinance_news(ticker: str) -> list[dict]:
    """
    yfinance .news — internal Yahoo Finance API.
    No HTTP layer, no rate limits, no bot detection. Most reliable source.
    """
    try:
        news     = yf.Ticker(ticker).news or []
        articles = []
        for item in news[:MAX_ARTICLES_PER_SOURCE]:
            pub_ts  = item.get("providerPublishTime")
            pub_str = (
                datetime.fromtimestamp(pub_ts, tz=timezone.utc)
                        .strftime("%a, %d %b %Y %H:%M:%S +0000")
                if pub_ts else ""
            )
            content = item.get("content") or {}
            summary = (
                content.get("summary")
                or content.get("body", "")[:BODY_PREVIEW_CHARS]
                or ""
            )
            articles.append({
                "title":        item.get("title", "").strip(),
                "url":          item.get("link") or (content.get("canonicalUrl") or {}).get("url", ""),
                "published":    pub_str,
                "body_summary": summary[:BODY_PREVIEW_CHARS],
            })
        logger.info(f"[yf_news]     {ticker}: {len(articles)} articles")
        return articles
    except Exception as e:
        logger.warning(f"[yf_news] {ticker}: failed — {e}")
        return []


def fetch_price_snapshot(ticker: str) -> dict | None:
    """yfinance price + fundamentals snapshot."""
    try:
        info  = yf.Ticker(ticker).info
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        if not price:
            return None
        prev    = info.get("previousClose", 0) or 0
        chg_pct = ((price - prev) / prev * 100) if prev else None
        snap    = {
            "ticker":         ticker.upper(),
            "price":          price,
            "prev_close":     prev,
            "day_change_pct": round(chg_pct, 3) if chg_pct is not None else None,
            "volume":         info.get("volume"),
            "avg_volume":     info.get("averageVolume"),
            "market_cap":     info.get("marketCap"),
            "pe_ratio":       info.get("trailingPE"),
            "forward_pe":     info.get("forwardPE"),
            "week_52_high":   info.get("fiftyTwoWeekHigh"),
            "week_52_low":    info.get("fiftyTwoWeekLow"),
            "sector":         info.get("sector"),
        }
        chg_str = f"({chg_pct:+.2f}%)" if chg_pct is not None else ""
        logger.info(f"[yfinance]    {ticker}: ${price} {chg_str}")
        return snap
    except Exception as e:
        logger.warning(f"[yfinance] {ticker}: failed — {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PLAYWRIGHT sources — each accepts a BrowserManager so the browser is reused
# ══════════════════════════════════════════════════════════════════════════════

def fetch_finviz_pw(ticker: str, bm: BrowserManager) -> list[dict]:
    """
    Finviz aggregated headlines via Playwright.
    Increasingly returns 403 to requests-based scrapers — real browser needed.
    """
    url  = f"https://finviz.com/quote.ashx?t={ticker.upper()}&p=d"
    html = bm.get_page_html(url, wait_for="table#news-table", wait_ms=800)
    if not html:
        logger.warning(f"[finviz]      {ticker}: no HTML returned")
        return []

    soup  = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="news-table")
    if not table:
        logger.warning(f"[finviz]      {ticker}: news-table not found")
        return []

    articles  = []
    last_date = ""
    for row in table.find_all("tr")[:MAX_ARTICLES_PER_SOURCE]:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        date_text = cells[0].get_text(strip=True)
        if len(date_text) > 8:
            last_date = date_text
        else:
            date_text = f"{last_date} {date_text}".strip()
        link_tag = cells[1].find("a")
        if not link_tag:
            continue
        articles.append({
            "title":        link_tag.get_text(strip=True),
            "url":          link_tag.get("href", ""),
            "published":    date_text,
            "body_summary": "",
        })

    logger.info(f"[finviz]      {ticker}: {len(articles)} articles")
    return articles


def fetch_marketwatch_pw(ticker: str, bm: BrowserManager) -> list[dict]:
    """
    MarketWatch per-ticker news via Playwright.
    Full JS render required — requests returns skeleton HTML with no articles.
    """
    url  = f"https://www.marketwatch.com/investing/stock/{ticker.lower()}"
    html = bm.get_page_html(
        url,
        wait_for = "div.collection__elements, div[class*='article__content']",
        wait_ms  = 2000,
        scroll   = True,
    )
    if not html:
        logger.warning(f"[marketwatch] {ticker}: no HTML returned")
        return []

    soup     = BeautifulSoup(html, "html.parser")
    articles = []

    for block in soup.select(
        "div.article__content, div.element--article, div[class*='article--trending']"
    )[:MAX_ARTICLES_PER_SOURCE]:
        link = (
            block.find("a", class_=lambda c: c and "title" in (c or ""))
            or block.find("h3")
            or block.find("a")
        )
        if not link:
            continue
        title = link.get_text(strip=True)
        href  = link.get("href", "")
        if not title or len(title) < 10:
            continue

        ts_tag  = block.find("time")
        pub_str = ts_tag.get("datetime", ts_tag.get_text(strip=True)) if ts_tag else ""

        summary_tag = block.find("p")
        summary     = summary_tag.get_text(strip=True)[:BODY_PREVIEW_CHARS] if summary_tag else ""

        articles.append({
            "title":        title,
            "url":          href if href.startswith("http") else f"https://www.marketwatch.com{href}",
            "published":    pub_str,
            "body_summary": summary,
        })

    logger.info(f"[marketwatch] {ticker}: {len(articles)} articles")
    return articles


def fetch_nasdaq_pw(ticker: str, bm: BrowserManager) -> list[dict]:
    """
    Nasdaq.com per-ticker news via Playwright.
    React-rendered — all news content loads after page init.
    """
    url  = f"https://www.nasdaq.com/market-activity/stocks/{ticker.lower()}/news-headlines"
    html = bm.get_page_html(
        url,
        wait_for = "div.quote-news-headlines__item, article.content-feed__card",
        wait_ms  = 2500,
    )
    if not html:
        logger.warning(f"[nasdaq]      {ticker}: no HTML returned")
        return []

    soup     = BeautifulSoup(html, "html.parser")
    articles = []

    items = (
        soup.select("div.quote-news-headlines__item")
        or soup.select("article.content-feed__card")
    )

    for item in items[:MAX_ARTICLES_PER_SOURCE]:
        link = item.find("a")
        if not link:
            continue
        title = link.get_text(strip=True)
        href  = link.get("href", "")
        if not title or len(title) < 10:
            continue

        ts_tag  = item.find("time") or item.find(
            class_=lambda c: c and "date" in (c or "").lower()
        )
        pub_str = ""
        if ts_tag:
            pub_str = ts_tag.get("datetime") or ts_tag.get_text(strip=True)

        articles.append({
            "title":        title,
            "url":          href if href.startswith("http") else f"https://www.nasdaq.com{href}",
            "published":    pub_str,
            "body_summary": "",
        })

    logger.info(f"[nasdaq]      {ticker}: {len(articles)} articles")
    return articles


def fetch_reuters_pw(ticker: str, bm: BrowserManager) -> list[dict]:
    """
    Reuters ticker search via Playwright.
    Fully JS-rendered — requests gets near-empty HTML.
    """
    url  = (
        f"https://www.reuters.com/search/news/?blob={ticker.upper()}"
        f"&sortBy=date&dateRange=pastWeek"
    )
    html = bm.get_page_html(
        url,
        wait_for = "li[class*='story'], div[class*='story-content'], div[class*='search-results']",
        wait_ms  = 2500,
    )
    if not html:
        logger.warning(f"[reuters]     {ticker}: no HTML returned")
        return []

    soup     = BeautifulSoup(html, "html.parser")
    articles = []

    for item in soup.select(
        "li[class*='story'], div[class*='story-content'], div[class*='media-story']"
    )[:MAX_ARTICLES_PER_SOURCE]:
        link = item.find("a")
        if not link:
            continue
        title = link.get_text(strip=True)
        href  = link.get("href", "")
        if not title or len(title) < 10:
            continue

        ts_tag  = item.find("time")
        pub_str = ts_tag.get("datetime", "") if ts_tag else ""

        summary_tag = item.find("p")
        summary     = summary_tag.get_text(strip=True)[:BODY_PREVIEW_CHARS] if summary_tag else ""

        articles.append({
            "title":        title,
            "url":          href if href.startswith("http") else f"https://www.reuters.com{href}",
            "published":    pub_str,
            "body_summary": summary,
        })

    logger.info(f"[reuters]     {ticker}: {len(articles)} articles")
    return articles


def fetch_benzinga_pw(ticker: str, bm: BrowserManager) -> list[dict]:
    """
    Benzinga per-ticker news via Playwright.
    Good for analyst upgrades/downgrades, earnings previews, price targets.
    """
    url  = f"https://www.benzinga.com/stock/{ticker.lower()}"
    html = bm.get_page_html(
        url,
        wait_for = "div[class*='news-feed'], article, section[class*='news']",
        wait_ms  = 2000,
        scroll   = True,
    )
    if not html:
        logger.warning(f"[benzinga]    {ticker}: no HTML returned")
        return []

    soup     = BeautifulSoup(html, "html.parser")
    articles = []
    seen_urls: set[str] = set()

    for item in soup.select(
        "article, div[class*='story'], div[class*='headline']"
    )[:MAX_ARTICLES_PER_SOURCE * 2]:
        link = item.find("a", href=lambda h: h and "/news/" in (h or ""))
        if not link:
            link = item.find("a")
        if not link:
            continue

        title = link.get_text(strip=True)
        href  = link.get("href", "")
        if not title or len(title) < 15:
            continue
        if href in seen_urls:
            continue
        seen_urls.add(href)

        ts_tag  = item.find("time") or item.find(
            class_=lambda c: c and "date" in (c or "").lower()
        )
        pub_str = ""
        if ts_tag:
            pub_str = ts_tag.get("datetime") or ts_tag.get_text(strip=True)

        summary_tag = item.find("p")
        summary     = summary_tag.get_text(strip=True)[:BODY_PREVIEW_CHARS] if summary_tag else ""

        articles.append({
            "title":        title,
            "url":          href if href.startswith("http") else f"https://www.benzinga.com{href}",
            "published":    pub_str,
            "body_summary": summary,
        })
        if len(articles) >= MAX_ARTICLES_PER_SOURCE:
            break

    logger.info(f"[benzinga]    {ticker}: {len(articles)} articles")
    return articles


# ══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════════════════

def collect_news_for_ticker(ticker: str) -> dict:
    """
    Collects news from all sources for one ticker.
    One BrowserManager shared across all Playwright sources.

    Returns summary dict with counts per source and total_inserted.
    """
    ticker = ticker.upper()

    # Direct sources — run outside browser
    yf_articles = fetch_yfinance_news(ticker)
    snapshot    = fetch_price_snapshot(ticker)

    # Playwright sources — one browser for all of them
    fv_articles = mw_articles = rt_articles = bz_articles = []
    try:
        with BrowserManager(headless=True) as bm:
            fv_articles = fetch_finviz_pw(ticker, bm)
            time.sleep(0.8)
            mw_articles = fetch_marketwatch_pw(ticker, bm)
            time.sleep(0.8)
            rt_articles = fetch_reuters_pw(ticker, bm)
            time.sleep(0.8)
            bz_articles = fetch_benzinga_pw(ticker, bm)
    except Exception as e:
        logger.error(f"[collector] Browser session failed for {ticker}: {e}")

    # Persist
    yf_ins = insert_raw_news(ticker, "yfinance_news", yf_articles)
    fv_ins = insert_raw_news(ticker, "finviz",        fv_articles)
    mw_ins = insert_raw_news(ticker, "marketwatch",   mw_articles)
    rt_ins = insert_raw_news(ticker, "reuters",       rt_articles)
    bz_ins = insert_raw_news(ticker, "benzinga",      bz_articles)

    if snapshot:
        insert_price_snapshot(ticker, snapshot)

    total = yf_ins + fv_ins + mw_ins + rt_ins + bz_ins
    logger.info(
        f"[collector]   {ticker}: {total} new articles  "
        f"yf:{yf_ins} fv:{fv_ins} mw:{mw_ins} rt:{rt_ins} bz:{bz_ins}"
    )

    return {
        "ticker":            ticker,
        "yf_news_count":     len(yf_articles),
        "finviz_count":      len(fv_articles),
        "marketwatch_count": len(mw_articles),
        "reuters_count":     len(rt_articles),
        "benzinga_count":    len(bz_articles),
        "total_inserted":    total,
        "price_snapshot":    snapshot,
    }


def collect_news_for_tickers(tickers: list[str], delay: float = 2.0) -> list[dict]:
    """Batch collection with a pause between tickers."""
    results = []
    for i, ticker in enumerate(tickers):
        logger.info(f"Collecting [{i+1}/{len(tickers)}]: {ticker}")
        results.append(collect_news_for_ticker(ticker))
        if i < len(tickers) - 1:
            time.sleep(delay)
    return results


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from database import Base, engine
    Base.metadata.create_all(bind=engine)

    result = collect_news_for_ticker("NVDA")
    print("\nCollection result:")
    for k, v in result.items():
        if k != "price_snapshot":
            print(f"  {k}: {v}")
    if result["price_snapshot"]:
        snap = result["price_snapshot"]
        chg  = f"{snap['day_change_pct']:+.2f}%" if snap.get("day_change_pct") is not None else "N/A"
        print(f"  price: ${snap['price']}  change: {chg}  sector: {snap.get('sector','N/A')}")