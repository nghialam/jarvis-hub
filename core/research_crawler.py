"""
research_crawler.py -- Brokerage report crawler for Hub 2.0 Research Hub.

Crawls: SSI, VCI, HCM, TCBS, VCBS research/report pages.
Stores: brokerage_reports table in jarvis.db
"""
import json
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

BROKERS = {
    "SSI": {
        "url": "https://ssi.com.vn/research/reports/",
        "selectors": {"title": "h3.report-title", "date": "span.report-date", "pdf": "a.pdf-download[href$='.pdf']"},
    },
    "VCI": {
        "url": "https://vci.com.vn/research/",
        "selectors": {"title": "div.report-item h4", "date": "div.report-item .date", "pdf": "a.download-link"},
    },
    "HCM": {
        "url": "https://hsc.com.vn/research-reports/",
        "selectors": {"title": "h3", "date": "span.date", "pdf": "a[href$='.pdf']"},
    },
    "TCBS": {
        "url": "https://tcbs.com.vn/research/",
        "selectors": {"title": "h4", "date": "span.date", "pdf": "a[href$='.pdf']"},
    },
    "VCBS": {
        "url": "https://vcbroker.com.vn/research/",
        "selectors": {"title": "h3.title", "date": "span.date", "pdf": "a[href$='.pdf']"},
    },
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def crawl_single_broker(broker: str, url: str) -> list:
    """Crawl a single brokerage website for research reports.
    Returns list of report dicts: {title, date, pdf_url, source_url, rating, summary}
    """
    reports = []
    try:
        r = requests.get(url, timeout=15, headers=HEADERS)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Try to find report entries - common patterns across brokerage sites
        entries = soup.find_all(["div", "article", "li"], class_=re.compile(r"report|article|item|list", re.I))

        if not entries:
            # Fallback: look for any anchor with .pdf in href
            entries = [a.parent for a in soup.find_all("a", href=re.compile(r"\.pdf$", re.I)) if a.parent]

        for entry in entries[:10]:  # max 10 per broker
            try:
                title_el = entry.find(["h1", "h2", "h3", "h4", "title", "span"])
                title = title_el.get_text(strip=True) if title_el else ""

                if not title or len(title) < 5:
                    continue

                date_el = entry.find(["span", "time"], class_=re.compile(r"date|time|publish", re.I))
                date_str = date_el.get_text(strip=True) if date_el else ""

                pdf_el = entry.find("a", href=re.compile(r"\.pdf$", re.I))
                pdf_url = str(pdf_el["href"]) if pdf_el else ""
                if pdf_url and not pdf_url.startswith("http"):
                    pdf_url = url.rsplit("/", 1)[0] + "/" + pdf_url

                source_url = entry.find("a")
                source_url = source_url["href"] if source_url and source_url.has_attr("href") else url

                if title and (pdf_url or date_str):
                    reports.append({
                        "title": title,
                        "date": date_str,
                        "pdf_url": pdf_url,
                        "source_url": source_url,
                    })
            except Exception:
                continue

    except Exception as e:
        print(f"[WARN] Crawl failed for {broker}: {e}", file=__import__("sys").stderr)

    return reports


def crawl_all_brokers() -> list:
    """Crawl all configured brokerage websites.
    Returns list of all reports found.
    """
    all_reports = []
    for broker, config in BROKERS.items():
        reports = crawl_single_broker(broker, config["url"])
        for r in reports:
            r["broker"] = broker
        all_reports.extend(reports)

    print(f"[CRAWLER] Found {len(all_reports)} reports across {len(BROKERS)} brokers")
    return all_reports


def store_reports(reports: list, db=None) -> int:
    """Store reports into DB."""
    if db is None:
        db = __import__("core.db", fromlist=["Database"]).Database()

    saved = 0
    for report in reports:
        try:
            db.save_brokerage_report(
                broker=report.get("broker", ""),
                title=report.get("title", ""),
                summary=report.get("summary", ""),
                pdf_url=report.get("pdf_url", ""),
                report_date=report.get("date", ""),
                source_url=report.get("source_url", ""),
            )
            saved += 1
        except Exception as e:
            print(f"[CRAWLER] Save failed for {report.get('title', '')}: {e}", file=__import__("sys").stderr)

    return saved


def generate_llm_summary(title: str) -> str:
    """Generate a brief summary using LLM. Falls back to title if LLM fails."""
    try:
        omlx_url = __import__("core.config", fromlist=["load_config"]).load_config().get("omlx", {}).get("url", "http://localhost:11434")
        resp = requests.post(
            f"{omlx_url}/v1/chat/completions",
            json={
                "model": "Qwen3.6-35B-A3B-MLX-8bit",
                "messages": [
                    {"role": "system", "content": "Generate a 1-line Vietnamese summary of this brokerage report title. Keep it under 80 chars."},
                    {"role": "user", "content": f"Report title: {title}"},
                ],
                "stream": False,
                "num_predict": 100,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("message", {}).get("content", "")[:200]
    except Exception as e:
        print(f"[CRAWLER] LLM summary failed: {e}", file=__import__("sys").stderr)

    # Fallback: extract key info from title
    keywords = re.findall(r"[A-Z]{2,}|[^\s]{3,}", title)
    return "Báo cáo " + " ".join(keywords[:3]) if keywords else title


def run_crawl_and_store(db=None) -> dict:
    """Main entry: crawl all brokers, enrich, store.
    Returns summary dict.
    """
    reports = crawl_all_brokers()

    # Enrich with LLM summaries
    for report in reports:
        if not report.get("summary"):
            report["summary"] = generate_llm_summary(report.get("title", ""))

    saved = store_reports(reports, db)

    return {
        "total_found": len(reports),
        "total_saved": saved,
        "brokers_crawled": len(BROKERS),
        "timestamp": datetime.now().isoformat(),
    }
