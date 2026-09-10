#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "_data"
OUTPUT = DATA_DIR / "mnp_quick_links.generated.yml"
META = DATA_DIR / "mnp_quick_links.meta.yml"
SEARCH_URL = "https://www.mn3p.navy.mil/web/guest/search"
QUICK_LINK_TYPE = "com.liferay.object.model.ObjectDefinition#11047502"
DELTA = 60
USER_AGENT = "Navylink-MNP-Sync/1.0 (+https://navylink.net/)"

GROUP_MAP = [
    ("Advancement & Promotion", "Career & Personnel", "Advancement & Boards"),
    ("Command Advancement Tools", "Career & Personnel", "Advancement & Boards"),
    ("Assignment, Leave, Travel", "Pay, Benefits & Travel", "Travel & PCS"),
    ("Career Planning", "Career & Personnel", "Career & Orders"),
    ("Personnel Records", "Career & Personnel", "Records & Admin"),
    ("Retirement & Separation", "Career & Personnel", "Retirement & Separation"),
    ("Pay & Benefits", "Pay, Benefits & Travel", "Pay & Benefits"),
    ("Training, Education, Qualifications", "Training & Education", "Training & Education"),
    ("Sailor & Family Support", "Family & Quality of Life", "Family & Support"),
    ("Deployment & Mobilization", "Readiness & Health", "Health & Readiness"),
    ("Performance", "Career & Personnel", "Records & Admin"),
    ("New to the Navy", "Career & Personnel", "Career & Orders"),
    ("Join the Navy", "Recruiting & Transition", "Recruiting"),
]

HUB_WORDS = {
    "overview", "resources", "resource", "directory", "directories", "links",
    "portal", "homepage", "home page", "site index", "commands", "library",
    "about", "information", "website"
}


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def canonical_url(value: str) -> str:
    value = clean_space(value)
    if not value:
        return ""
    if value.startswith("/"):
        value = urljoin("https://www.mn3p.navy.mil", value)
    parts = urlsplit(value)
    scheme = (parts.scheme or "https").lower()
    host = parts.netloc.lower()
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_")]
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def load_existing() -> tuple[set[str], set[str]]:
    urls: set[str] = set()
    names: set[str] = set()
    for filename in ("quick_links.yml", "extra_links.yml"):
        path = DATA_DIR / filename
        if not path.exists():
            continue
        items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("url"):
                urls.add(canonical_url(str(item["url"])))
            if item.get("name"):
                names.add(clean_space(str(item["name"])).casefold())
    return urls, names


def extract_counts(text: str) -> tuple[int | None, int | None]:
    quick = None
    overall = None
    m = re.search(r"Quick\s+Link\s*\(([\d,]+)\)", text, re.I)
    if m:
        quick = int(m.group(1).replace(",", ""))
    m = re.search(r"([\d,]+)\s+Results\s+for", text, re.I)
    if m:
        overall = int(m.group(1).replace(",", ""))
    return quick, overall


def parse_page(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    lines = [clean_space(x) for x in soup.get_text("\n").splitlines()]
    lines = [x for x in lines if x]
    title_indexes = [i for i, line in enumerate(lines)
                     if re.match(r"^.+\s+Quick\s+Link$", line, re.I)]
    results: list[dict[str, str]] = []

    for pos, start in enumerate(title_indexes):
        end = title_indexes[pos + 1] if pos + 1 < len(title_indexes) else min(len(lines), start + 40)
        block = lines[start:end]
        raw_name = re.sub(r"\s+Quick\s+Link$", "", block[0], flags=re.I).strip()
        if not raw_name or raw_name.lower() in {"quick", "type"}:
            continue

        url = ""
        description = ""
        categories = ""
        for idx, line in enumerate(block[1:], start=1):
            if not url and (re.match(r"^https?://", line, re.I) or line.startswith("/web/") or line.startswith("/group/")):
                url = line
            if line.lower().startswith("description:"):
                description = clean_space(line.split(":", 1)[1])
                if not description and idx + 1 < len(block) and not block[idx + 1].lower().startswith("category:"):
                    description = block[idx + 1]
            if line.lower().startswith("category:"):
                categories = clean_space(line.split(":", 1)[1])
                if not categories and idx + 1 < len(block):
                    categories = block[idx + 1]

        if not url:
            # Fall back to the result-title anchor when the displayed URL is omitted.
            anchor = soup.find(string=re.compile(rf"^{re.escape(block[0])}$", re.I))
            if anchor:
                parent = anchor.parent
                if parent and parent.name == "a" and parent.get("href"):
                    url = parent.get("href", "")
                elif parent:
                    a = parent.find_parent("a")
                    if a and a.get("href"):
                        url = a.get("href", "")

        if url:
            results.append({
                "name": raw_name,
                "url": urljoin("https://www.mn3p.navy.mil", url),
                "description": description,
                "mnp_categories": categories,
            })
    return results


def classify(name: str, url: str, mnp_categories: str) -> tuple[str, str, str]:
    hay = f"{name} {url} {mnp_categories}".lower()

    if any(word in hay for word in ("reserve", "selres", "rcsbp", "nrh", "resfor")):
        group, category = "Reserve", "Reserve"
    elif any(word in hay for word in ("recruit", "join the navy", "navy.com")):
        group, category = "Recruiting & Transition", "Recruiting"
    elif any(word in hay for word in ("transition", "skillbridge", "separation", "retired", "retirement")):
        group, category = "Recruiting & Transition", "Transition"
    elif any(word in hay for word in ("sapr", "suicide", "resilience", "prevention", "safety", "drug", "alcohol")):
        group, category = "Readiness & Health", "Safety & Resilience"
    elif any(word in hay for word in ("medical", "health", "tricare", "mrrs", "prims", "pfa", "fitness", "nutrition")):
        group, category = "Readiness & Health", "Health & Readiness"
    elif any(word in hay for word in ("housing", "child", "family", "ombudsman", "mwr", "voting")):
        group, category = "Family & Quality of Life", "Family & Support"
    elif any(word in hay for word in ("instruction", "manual", "regulation", "directive", "navadmin", "alnav", "forms", "policy")):
        group, category = "Policy & References", "References"
    elif any(word in hay for word in ("training", "education", "qualification", "school", "college", "university", "learning", "pqs", "dantes", "jst")):
        group, category = "Training & Education", "Training & Education"
    elif any(word in hay for word in ("pay", "benefit", "dfas", "travel", "dts", "pcs", "leave", "move", "gtcc")):
        group, category = "Pay, Benefits & Travel", "Travel & PCS" if any(w in hay for w in ("travel", "dts", "pcs", "leave", "move", "gtcc")) else "Pay & Benefits"
    elif any(word in hay for word in ("advancement", "promotion", "selection board", "profile sheet", "frocking")):
        group, category = "Career & Personnel", "Advancement & Boards"
    elif any(word in hay for word in ("record", "ompf", "esr", "evaluation", "fitrep", "ndaws")):
        group, category = "Career & Personnel", "Records & Admin"
    elif any(word in hay for word in ("assignment", "detail", "career", "community management", "reenlist")):
        group, category = "Career & Personnel", "Career & Orders"
    else:
        group, category = "Career & Personnel", "Career & Orders"
        for official, mapped_group, mapped_category in GROUP_MAP:
            if official.lower() in mnp_categories.lower():
                group, category = mapped_group, mapped_category
                break

    kind = "direct"
    lower_name = name.lower()
    lower_url = url.lower()
    if any(word in lower_name for word in HUB_WORDS):
        kind = "hub"
    if any(token in lower_url for token in ("/overview", "/resources/links", "/site-index", "/commands/")):
        kind = "hub"
    if "mn3p.navy.mil/web/" in lower_url or "mnp.navy.mil/group/" in lower_url:
        # MNP content/overview pages are generally intermediary guidance pages.
        kind = "hub"
        group, category = "Portals & Directories", "Portals & Directories"

    return group, category, kind


def build_tags(name: str, mnp_categories: str) -> str:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9&'/-]*", f"{name} {mnp_categories}")
    seen: set[str] = set()
    out: list[str] = ["mnp", "mynavy", "quicklinks"]
    for word in words:
        key = word.casefold()
        if key in seen or len(word) < 2:
            continue
        seen.add(key)
        out.append(word)
    return " ".join(out[:40])


def fetch_catalog(session: requests.Session) -> tuple[list[dict[str, str]], int | None]:
    records: list[dict[str, str]] = []
    expected_quick: int | None = None
    total_results: int | None = None
    pages = 1

    for page in range(1, 31):
        if page > pages:
            break
        response = session.get(
            SEARCH_URL,
            params={"type": QUICK_LINK_TYPE, "delta": DELTA, "start": page, "q": ""},
            timeout=30,
        )
        response.raise_for_status()
        text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
        quick_count, overall_count = extract_counts(text)
        if quick_count:
            expected_quick = quick_count
        if overall_count:
            total_results = overall_count
        if page == 1:
            basis = total_results or expected_quick or DELTA
            pages = max(1, min(30, math.ceil(basis / DELTA)))

        page_records = parse_page(response.text)
        records.extend(page_records)
        print(f"MNP page {page}/{pages}: {len(page_records)} Quick Link records parsed", file=sys.stderr)

    return records, expected_quick


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync all public MyNavy Portal Quick Links into Navylink.")
    parser.add_argument("--audit", action="store_true", help="Audit only; do not write generated YAML.")
    parser.add_argument("--min-records", type=int, default=350, help="Minimum parsed record sanity threshold.")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})

    records, expected = fetch_catalog(session)
    if len(records) < args.min_records:
        raise SystemExit(f"Refusing update: parsed only {len(records)} MNP Quick Link records (minimum {args.min_records}).")
    if expected and len(records) < int(expected * 0.90):
        raise SystemExit(f"Refusing update: parsed {len(records)} of about {expected} MNP Quick Link records.")

    # Merge duplicate MNP records that resolve to the same destination.
    merged: dict[str, dict[str, str]] = {}
    for record in records:
        canon = canonical_url(record["url"])
        if not canon:
            continue
        if canon not in merged:
            merged[canon] = dict(record)
        else:
            prev = merged[canon]
            cats = clean_space(f"{prev.get('mnp_categories', '')} {record.get('mnp_categories', '')}")
            prev["mnp_categories"] = cats
            if len(record.get("description", "")) > len(prev.get("description", "")):
                prev["description"] = record["description"]

    existing_urls, existing_names = load_existing()
    generated: list[dict[str, object]] = []
    already_covered = 0

    for canon, record in sorted(merged.items(), key=lambda kv: kv[1]["name"].casefold()):
        if canon in existing_urls or record["name"].casefold() in existing_names:
            already_covered += 1
            continue
        group, category, kind = classify(record["name"], record["url"], record.get("mnp_categories", ""))
        generated.append({
            "name": record["name"],
            "url": record["url"],
            "group": group,
            "category": category,
            "kind": kind,
            "tags": build_tags(record["name"], record.get("mnp_categories", "")),
            "description": record.get("description") or f"MyNavy Portal Quick Link: {record['name']}.",
            "cac": False,
            "source": "MyNavy Portal Quick Links",
            "mnp_categories": record.get("mnp_categories", ""),
        })

    summary = {
        "source": SEARCH_URL,
        "reported_quick_link_records": expected,
        "parsed_records": len(records),
        "unique_mnp_destinations": len(merged),
        "already_covered_by_curated_catalog": already_covered,
        "generated_missing_destinations": len(generated),
        "represented_unique_destinations": already_covered + len(generated),
    }

    print(yaml.safe_dump(summary, sort_keys=False).strip())

    if args.audit:
        return 0

    tmp = OUTPUT.with_suffix(OUTPUT.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(generated, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    tmp.replace(OUTPUT)
    META.write_text(yaml.safe_dump(summary, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote {OUTPUT} with {len(generated)} MNP-only destinations.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
