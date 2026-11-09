#!/usr/bin/env python3
"""
fetch_quantum_events.py
Self-populating quantum event aggregator for QShift Lab (qshiftlab.com).
Fetches live quantum news and event announcements via open RSS feeds,
categorizes them into the QShift stack, deduplicates, and updates data/events.json.
Runs weekly via GitHub Actions cron. Zero external dependencies (pure Python 3).
"""

import os
import re
import json
import html
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "events.json")

RSS_FEEDS = [
    {
        "url": "https://news.google.com/rss/search?q=%22quantum+computing%22+(Singapore+OR+Asia+OR+summit+OR+conference+OR+symposium)&hl=en-SG&gl=SG&ceid=SG:en",
        "default_badge": "Global Wire",
        "default_organizer": "Industry News Wire"
    },
    {
        "url": "https://news.google.com/rss/search?q=%22post-quantum%22+OR+%22FIPS+203%22+OR+%22quantum-safe%22&hl=en-SG&gl=SG&ceid=SG:en",
        "default_badge": "Security Wire",
        "default_organizer": "Cybersecurity & Standards"
    }
]

CATEGORY_KEYWORDS = {
    "Maritime & Logistics": ["maritime", "port", "vessel", "shipping", "logistics", "routing", "qaoa", "annealing", "supply chain"],
    "Fintech & Risk": ["fintech", "finance", "banking", "portfolio", "risk", "var", "derivative", "monte carlo", "qae"],
    "Biopharma & Chemistry": ["biopharma", "chemistry", "molecular", "drug discovery", "protein", "docking", "vqe", "hamiltonian", "materials"],
    "Post-Quantum Security (PQC)": ["post-quantum", "pqc", "fips 203", "fips 204", "kyber", "dilithium", "cryptography", "quantum-safe", "qkd"]
}

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    return text.strip()

def detect_category(title: str, summary: str) -> str:
    combined = f"{title} {summary}".lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return cat
    return "All Domains"

def fetch_rss_feed(feed_cfg):
    events = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QShiftLab-EventBot/1.0"}
    try:
        req = urllib.request.Request(feed_cfg["url"], headers=headers)
        with urllib.request.urlopen(req, timeout=12) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall(".//item")[:10]:
                title = clean_text(item.findtext("title", ""))
                link = item.findtext("link", "").strip()
                pub_date = item.findtext("pubDate", "").strip()
                description = clean_text(item.findtext("description", ""))
                
                # Filter out irrelevant clickbait
                if not any(k in title.lower() for k in ["quantum", "qubit", "pqc", "qaoa"]):
                    continue
                
                # Format date YYYY-MM-DD
                event_date = datetime.now().strftime("%Y-%m-%d")
                try:
                    dt = datetime.strptime(pub_date[:25].strip(), "%a, %d %b %Y %H:%M:%S")
                    event_date = dt.strftime("%Y-%m-%d")
                except Exception:
                    pass
                
                category = detect_category(title, description)
                organizer = feed_cfg["default_organizer"]
                source_tag = item.findtext("source", "")
                if source_tag:
                    organizer = clean_text(source_tag)
                
                events.append({
                    "id": f"rss-{abs(hash(title)) % 1000000:06d}",
                    "title": title[:110],
                    "date": event_date,
                    "endDate": event_date,
                    "location": "Global / Hybrid Feed",
                    "category": category,
                    "organizer": organizer[:60],
                    "link": link,
                    "badge": feed_cfg["default_badge"],
                    "summary": (description[:240] + "...") if len(description) > 240 else description
                })
    except Exception as e:
        print(f"Error fetching feed {feed_cfg['url']}: {e}")
    return events

def main():
    existing_events = []
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                existing_events = json.load(f)
        except Exception as e:
            print(f"Warning: could not read existing events: {e}")
    
    # Existing curated events (with id starting with q-evt-) are anchor events to always keep
    anchor_events = [e for e in existing_events if e.get("id", "").startswith("q-evt-")]
    
    # Fetch live feeds
    fetched_events = []
    for cfg in RSS_FEEDS:
        fetched_events.extend(fetch_rss_feed(cfg))
    
    # Merge and deduplicate by title similarity / URL
    merged = list(anchor_events)
    seen_titles = {re.sub(r'[^a-zA-Z0-9]', '', e["title"].lower()[:40]) for e in merged}
    
    added_count = 0
    for evt in fetched_events:
        slug = re.sub(r'[^a-zA-Z0-9]', '', evt["title"].lower()[:40])
        if slug not in seen_titles:
            seen_titles.add(slug)
            merged.append(evt)
            added_count += 1
            if added_count >= 15:  # Keep feed fresh and focused
                break
                
    # Sort: anchor events first, then by date descending
    merged.sort(key=lambda x: (not x.get("id", "").startswith("q-evt-"), x.get("date", "")), reverse=False)
    
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    
    print(f"Successfully updated {DATA_PATH}: {len(merged)} total events ({len(anchor_events)} anchor, {added_count} newly ingested from live feeds).")

if __name__ == "__main__":
    main()
