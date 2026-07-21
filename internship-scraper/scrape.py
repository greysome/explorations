#!/usr/bin/env python3
"""
Internship scraper -> Telegram.

Run every ~3h via cron:
    0 */3 * * *  cd /path/to/this/dir && python3 scrape.py >> scrape.log 2>&1

Telegram creds:  fill in TG_BOT_TOKEN / TG_CHAT_ID below.
State:    seen.csv in this dir. Dedupe is by (source,id); last-updated is only
          used on first run to avoid backfilling ancient postings.

Sources (edit the lists below to add/remove):
  - MyCareersFuture (SG govt jobs board)
  - Greenhouse boards
  - Lever boards
  - Ashby boards

No external deps -- stdlib only.
"""
import csv
import html
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ---- config: edit freely ----------------------------------------------------

TG_BOT_TOKEN = ""   # from @BotFather
TG_CHAT_ID   = ""   # your user id or a channel id like "@my_channel"

INCLUDE_KEYWORDS = [
    "software", "swe", "engineer", "backend", "infrastructure", "systems",
    "distributed", "compiler", "kernel", "hpc", "high performance",
    "performance", "platform", "cloud", "devops", "sre", "ml infra",
]
EXCLUDE_KEYWORDS = [
    # quant / finance
    "quant", "quantitative", "trading", "trader", "hedge", "market making",
    "prop trading", "hft", "actuar",
    # non-SWE roles that leak through
    "sales", "marketing", "recruiter", "designer", "product manager",
    "data analyst", "business analyst", "hr ",
]

GREENHOUSE_BOARDS = [
    "stripe", "databricks", "cloudflare", "gitlab", "discord", "figma",
    "notion", "airtable", "rippling", "openai", "anthropic", "airbnb",
    "dropbox", "reddit", "pinterest", "snap",
]
LEVER_COMPANIES = [
    "netflix", "spotify", "plaid", "ramp", "attentive",
]
ASHBY_BOARDS = [
    # e.g. "posthog", "linear", "vercel"
]

# Only used before seen.csv exists, to skip ancient backlog.
FIRST_RUN_LOOKBACK_DAYS = 7

HERE = Path(__file__).parent
SEEN_CSV = HERE / "seen.csv"
CSV_FIELDS = ["id", "source", "company", "title", "url", "first_seen"]
UA = "Mozilla/5.0 (intern-scraper)"

# ---- http helpers -----------------------------------------------------------

def http_json(url, method="GET", body=None, headers=None, timeout=30):
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p\s*>", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(s)).strip()

def is_sg(*locs):
    for l in locs:
        if not l:
            continue
        s = l.lower()
        if "singapore" in s or s.strip() in ("sg", "sgp"):
            return True
    return False

def matches_filters(title, description=""):
    t = f"{title} {description}".lower()
    if "intern" not in t:
        return False
    if not any(k in t for k in INCLUDE_KEYWORDS):
        return False
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return False
    return True

# ---- sources ----------------------------------------------------------------
# Each source is a generator yielding dicts:
#   {id, source, company, title, description, location, url}

def source_mycareersfuture():
    # NOTE: verify this endpoint if it stops working -- MCF has changed hosts
    # historically (api.mycareersfuture.gov.sg vs api.mycareersfuture.sg).
    url = ("https://api.mycareersfuture.gov.sg/v2/search"
           "?limit=30&page=0&sessionId=intern-scraper")
    body = {
        "search": "software intern",
        "sortBy": ["new_posting_date"],
        "employmentTypes": ["Internship"],
    }
    try:
        data = http_json(url, method="POST", body=body)
    except Exception as e:
        print(f"[mcf] fetch failed: {e}", file=sys.stderr)
        return
    for j in data.get("results", []):
        uuid = j.get("uuid") or (j.get("metadata") or {}).get("jobPostId")
        if not uuid:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", (j.get("title") or "").lower()).strip("-")
        company = ((j.get("hiringCompany") or j.get("postedCompany") or {})
                   .get("name") or "?")
        yield {
            "id": f"mcf:{uuid}",
            "source": "mycareersfuture",
            "company": company,
            "title": j.get("title", ""),
            "description": strip_html(j.get("description", "")),
            "location": "Singapore",
            "url": f"https://www.mycareersfuture.gov.sg/job/{slug}-{uuid[:20]}",
        }

def source_greenhouse(board):
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    try:
        data = http_json(url)
    except Exception as e:
        print(f"[greenhouse:{board}] fetch failed: {e}", file=sys.stderr)
        return
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        offices = " | ".join(o.get("name", "") for o in j.get("offices") or [])
        if not is_sg(loc, offices):
            continue
        yield {
            "id": f"gh:{board}:{j['id']}",
            "source": f"greenhouse:{board}",
            "company": board,
            "title": j.get("title", ""),
            "description": strip_html(j.get("content", "")),
            "location": loc,
            "url": j.get("absolute_url", ""),
        }

def source_lever(company):
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    try:
        data = http_json(url)
    except Exception as e:
        print(f"[lever:{company}] fetch failed: {e}", file=sys.stderr)
        return
    for j in data:
        cats = j.get("categories") or {}
        loc = cats.get("location") or ""
        addl = " | ".join(cats.get("allLocations") or [])
        if not is_sg(loc, addl):
            continue
        yield {
            "id": f"lever:{company}:{j['id']}",
            "source": f"lever:{company}",
            "company": company,
            "title": j.get("text", ""),
            "description": strip_html(j.get("descriptionPlain")
                                      or j.get("description", "")),
            "location": loc,
            "url": j.get("hostedUrl", ""),
        }

def source_ashby(board):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=false"
    try:
        data = http_json(url)
    except Exception as e:
        print(f"[ashby:{board}] fetch failed: {e}", file=sys.stderr)
        return
    for j in data.get("jobs", []):
        loc = j.get("location", "")
        addl = " | ".join(a.get("location", "") for a in j.get("secondaryLocations") or [])
        if not is_sg(loc, addl):
            continue
        yield {
            "id": f"ashby:{board}:{j['id']}",
            "source": f"ashby:{board}",
            "company": board,
            "title": j.get("title", ""),
            "description": strip_html(j.get("descriptionHtml", "")),
            "location": loc,
            "url": j.get("jobUrl", ""),
        }

# ---- state ------------------------------------------------------------------

def load_seen():
    if not SEEN_CSV.exists():
        return set()
    with SEEN_CSV.open() as f:
        return {row["id"] for row in csv.DictReader(f)}

def append_seen(rows):
    new_file = not SEEN_CSV.exists()
    with SEEN_CSV.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow(r)

# ---- telegram ---------------------------------------------------------------

def tg_send(job):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print(f"[tg] skipped (no creds): {job['id']}", file=sys.stderr)
        return
    desc = job["description"] or ""
    if len(desc) > 700:
        desc = desc[:700].rstrip() + "…"
    text = (
        f"<b>{html.escape(job['company'])}</b> — {html.escape(job['title'])}\n\n"
        f"{html.escape(desc)}\n\n"
        f"{html.escape(job['url'])}"
    )
    try:
        http_json(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                  method="POST",
                  body={"chat_id": TG_CHAT_ID, "text": text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": False})
    except urllib.error.HTTPError as e:
        print(f"[tg] {e.code}: {e.read().decode(errors='replace')}", file=sys.stderr)
    except Exception as e:
        print(f"[tg] {e}", file=sys.stderr)

# ---- main -------------------------------------------------------------------

def main():
    seen = load_seen()
    sources = [source_mycareersfuture()]
    sources += [source_greenhouse(b) for b in GREENHOUSE_BOARDS]
    sources += [source_lever(c) for c in LEVER_COMPANIES]
    sources += [source_ashby(b) for b in ASHBY_BOARDS]

    new_rows = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for src in sources:
        for job in src:
            if job["id"] in seen:
                continue
            if not matches_filters(job["title"], job.get("description", "")):
                continue
            seen.add(job["id"])
            print(f"NEW  {job['id']:50s}  {job['company']:20s}  {job['title']}")
            tg_send(job)
            new_rows.append({
                "id": job["id"], "source": job["source"],
                "company": job["company"], "title": job["title"],
                "url": job["url"], "first_seen": now,
            })
    if new_rows:
        append_seen(new_rows)
    print(f"done: {len(new_rows)} new")

if __name__ == "__main__":
    main()
