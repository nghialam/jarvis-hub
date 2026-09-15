"""
services/research_service.py - Research Crawler Service (Phase 3.12)

JH3.0: Scans broker websites for new research reports.
Works without LLM, LLM optional for summary generation.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from core.config import load_config
from core.db import Database

log = logging.getLogger(__name__)


class ResearchService:
    """
    Scan broker websites for new research reports.
    
    Brokers scanned: SSI, VCI, HCM, TCBS, VCBS
    """
    
    BROKERS = {
        "SSI": {
            "name": "SSI Securities",
            "url": "https://www.ssi.com.vn/research",
            "last_scan": None,
        },
        "VCI": {
            "name": "Viet Capital Securities",
            "url": "https://vcsc.com.vn/research",
            "last_scan": None,
        },
        "HCM": {
            "name": "HCM Securities",
            "url": "https://www.hcmsec.com.vn/research",
            "last_scan": None,
        },
        "TCBS": {
            "name": "TCBS Bank",
            "url": "https://www.tcbs.com.vn/research",
            "last_scan": None,
        },
        "VCBS": {
            "name": "VCBank Securities",
            "url": "https://www.vcbs.com.vn/research",
            "last_scan": None,
        },
    }
    
    def __init__(self, config=None, db=None):
        self.config = config or load_config()
        self.db = db or Database()
        self.downloads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "reports")
        os.makedirs(self.downloads_dir, exist_ok=True)
    
    def scan_brokers(self) -> List[Dict]:
        """
        Scan all broker websites for new research reports.
        
        Returns:
            List of new reports found
        """
        log.info("Starting broker research scan...")
        new_reports = []
        
        for broker_id, broker_info in self.BROKERS.items():
            try:
                reports = self._scan_broker(broker_id, broker_info)
                new_reports.extend(reports)
                broker_info["last_scan"] = datetime.utcnow().isoformat()
                log.info("Broker %s: found %d reports", broker_id, len(reports))
            except Exception as e:
                log.error("Broker %s scan failed: %s", broker_id, e)
        
        # Save to database
        if new_reports:
            self._save_reports(new_reports)
            log.info("Saved %d new reports to database", len(new_reports))
        
        return new_reports
    
    def get_reports(self, limit: int = 50, broker: str = None) -> List[Dict]:
        """
        Get research reports from database.
        
        Args:
            limit: Maximum number of reports
            broker: Filter by broker ID (optional)
        """
        try:
            conn = self.db.get_connection()
            
            query = "SELECT id, broker, title, author, publish_date, pdf_url, summary, created_at FROM research_items"
            params = []
            
            if broker:
                query += " WHERE broker = ?"
                params.append(broker)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            
            return [
                {
                    "id": row[0],
                    "broker": row[1],
                    "title": row[2],
                    "author": row[3],
                    "publish_date": row[4],
                    "pdf_url": row[5],
                    "summary": row[6],
                    "created_at": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            log.error("Failed to get reports: %s", e)
            return []
    
    def get_pdf(self, report_id: str) -> Optional[str]:
        """
        Get path to PDF file for a report.
        
        Returns:
            File path or None
        """
        try:
            conn = self.db.get_connection()
            row = conn.execute(
                "SELECT pdf_url FROM research_items WHERE id = ?",
                (report_id,)
            ).fetchone()
            
            if row and row[0]:
                # Check if file exists locally
                local_path = os.path.join(self.downloads_dir, f"{report_id}.pdf")
                if os.path.exists(local_path):
                    return local_path
                # Return remote URL if local doesn't exist
                return row[0]
        except Exception as e:
            log.error("Failed to get PDF: %s", e)
        
        return None
    
    def generate_summary(self, report_id: str) -> Optional[Dict]:
        """
        Generate LLM summary of a report.
        Runs async, returns immediately with heuristic summary.
        
        Args:
            report_id: Report ID
        
        Returns:
            Summary dict
        """
        try:
            # Get report from DB
            conn = self.db.get_connection()
            row = conn.execute(
                "SELECT title, author, pdf_url FROM research_items WHERE id = ?",
                (report_id,)
            ).fetchone()
            
            if not row:
                return None
            
            # Generate heuristic summary
            summary = self._generate_heuristic_summary(row)
            
            # If LLM enabled, queue async generation
            if self.config.get("llm", {}).get("enabled", False):
                self._queue_llm_summary(report_id, row)
            
            return summary
            
        except Exception as e:
            log.error("Failed to generate summary: %s", e)
            return None
    
    def _scan_broker(self, broker_id: str, broker_info: Dict) -> List[Dict]:
        """Scan a single broker website."""
        reports = []
        
        try:
            import requests
            
            # Try to fetch broker page
            resp = requests.get(broker_info["url"], timeout=10)
            if resp.status_code == 200:
                # Simple parsing - extract titles and links
                # This is a placeholder - real implementation would use BeautifulSoup
                html = resp.text
                
                # Look for report links (simplified pattern matching)
                import re
                links = re.findall(r'href="([^"]+\.pdf[^"]*)"', html)
                titles = re.findall(r'<h[23]>?([^<]+)</h[23]>', html)
                
                for i, link in enumerate(links[:10]):
                    title = titles[i] if i < len(titles) else f"Report {i+1}"
                    
                    # Check if already in database
                    if not self._report_exists(broker_id, title):
                        reports.append({
                            "broker": broker_id,
                            "title": title,
                            "author": "Unknown",
                            "publish_date": datetime.utcnow().strftime("%Y-%m-%d"),
                            "pdf_url": link,
                            "summary": None,
                            "created_at": datetime.utcnow().isoformat(),
                        })
        except Exception as e:
            log.error("Failed to scan broker %s: %s", broker_id, e)
        
        return reports
    
    def _report_exists(self, broker_id: str, title: str) -> bool:
        """Check if report already exists in database."""
        try:
            conn = self.db.get_connection()
            row = conn.execute(
                "SELECT COUNT(*) FROM research_items WHERE broker = ? AND title = ?",
                (broker_id, title)
            ).fetchone()
            return row and row[0] > 0
        except Exception:
            return False
    
    def _save_reports(self, reports: List[Dict]):
        """Save new reports to database."""
        try:
            conn = self.db.get_connection()
            for report in reports:
                conn.execute(
                    """INSERT OR IGNORE INTO research_items 
                       (broker, title, author, publish_date, pdf_url, summary, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        report["broker"],
                        report["title"],
                        report["author"],
                        report["publish_date"],
                        report["pdf_url"],
                        report.get("summary"),
                        report["created_at"],
                    )
                )
            conn.commit()
        except Exception as e:
            log.error("Failed to save reports: %s", e)
    
    def _generate_heuristic_summary(self, row) -> Dict:
        """Generate heuristic summary from report metadata."""
        title = row[0] or ""
        author = row[1] or "Unknown"
        broker = row[2] or "Unknown"
        
        # Simple heuristic summary
        summary = f"Research report from {broker} by {author}."
        
        # Extract key metrics from title if present
        import re
        price_match = re.search(r'([0-9,.]+)', title)
        target_match = re.search(r'target ([0-9,.]+)', title, re.IGNORECASE)
        
        metrics = {}
        if price_match:
            metrics["mentioned_price"] = price_match.group(1)
        if target_match:
            metrics["target_price"] = target_match.group(1)
        
        return {
            "summary": summary,
            "metrics": metrics,
            "source": "heuristic",
            "generated_at": datetime.utcnow().isoformat(),
        }
    
    def _queue_llm_summary(self, report_id: str, row):
        """Queue LLM summary generation."""
        try:
            from core.async_queue import get_async_queue
            queue = get_async_queue()
            
            queue.submit("generate_report_summary", {
                "report_id": report_id,
                "title": row[0],
                "pdf_url": row[2],
            })
            
            log.info("Queued LLM summary for report %s", report_id)
        except Exception as e:
            log.error("Failed to queue LLM summary: %s", e)
