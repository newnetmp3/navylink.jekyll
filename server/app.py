from __future__ import annotations

import re
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "_data"
DB_PATH = Path("/var/lib/navylink/navylink.db")
RATE_WINDOW_SECONDS = 2.0

app = FastAPI(title="Navylink API", docs_url=None, redoc_url=None)
_recent: dict[tuple[str, str], float] = {}
_recent_lock = Lock()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def load_catalog() -> dict[str, dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for name in ("quick_links.yml", "extra_links.yml", "mnp_quick_links_generated.yml"):
        path = DATA_DIR / name
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or []
                if isinstance(loaded, list):
                    items.extend(loaded)
    catalog: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        item_id = str(item.get("id") or slugify(str(item["name"]))).strip()
        if item_id:
            catalog[item_id] = item
    return catalog


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS link_totals (
                link_id TEXT PRIMARY KEY,
                total_count INTEGER NOT NULL DEFAULT 0,
                last_clicked INTEGER
            );
            CREATE TABLE IF NOT EXISTS click_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link_id TEXT NOT NULL,
                clicked_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_click_events_link_time
                ON click_events(link_id, clicked_at);
            CREATE INDEX IF NOT EXISTS idx_click_events_time
                ON click_events(clicked_at);
            """
        )


@app.on_event("startup")
def startup() -> None:
    init_db()


def transient_client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limited(client_key: str, link_id: str) -> bool:
    now = time.monotonic()
    key = (client_key, link_id)
    with _recent_lock:
        last = _recent.get(key)
        if last is not None and now - last < RATE_WINDOW_SECONDS:
            return True
        _recent[key] = now
        if len(_recent) > 5000:
            cutoff = now - 30
            stale = [k for k, t in _recent.items() if t < cutoff]
            for stale_key in stale:
                _recent.pop(stale_key, None)
    return False


def increment_click(link_id: str) -> None:
    now = int(time.time())
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO link_totals(link_id, total_count, last_clicked)
            VALUES (?, 1, ?)
            ON CONFLICT(link_id) DO UPDATE SET
                total_count = total_count + 1,
                last_clicked = excluded.last_clicked
            """,
            (link_id, now),
        )
        conn.execute(
            "INSERT INTO click_events(link_id, clicked_at) VALUES (?, ?)",
            (link_id, now),
        )
        conn.execute("DELETE FROM click_events WHERE clicked_at < ?", (now - 90 * 86400,))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/click/{link_id}")
def record_click(link_id: str, request: Request) -> JSONResponse:
    catalog = load_catalog()
    if link_id not in catalog:
        raise HTTPException(status_code=404, detail="Unknown link")

    client_key = transient_client_key(request)
    if rate_limited(client_key, link_id):
        return JSONResponse({"ok": True, "counted": False})

    increment_click(link_id)
    return JSONResponse({"ok": True, "counted": True})


@app.get("/api/go/{link_id}")
def tracked_redirect(link_id: str, request: Request) -> RedirectResponse:
    catalog = load_catalog()
    item = catalog.get(link_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Unknown link")

    destination = str(item.get("url", "")).strip()
    if not destination.startswith(("https://", "http://")):
        raise HTTPException(status_code=500, detail="Invalid destination")

    client_key = transient_client_key(request)
    if not rate_limited(client_key, link_id):
        increment_click(link_id)

    return RedirectResponse(destination, status_code=302)


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    catalog = load_catalog()
    now = int(time.time())
    day_cutoff = now - 86400
    week_cutoff = now - 7 * 86400

    totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "day": 0, "week": 0, "last_clicked": None}
    )

    with connect() as conn:
        for row in conn.execute("SELECT link_id, total_count, last_clicked FROM link_totals"):
            if row["link_id"] in catalog:
                totals[row["link_id"]]["total"] = int(row["total_count"])
                totals[row["link_id"]]["last_clicked"] = row["last_clicked"]

        for row in conn.execute(
            """
            SELECT link_id,
                   SUM(CASE WHEN clicked_at >= ? THEN 1 ELSE 0 END) AS day_count,
                   SUM(CASE WHEN clicked_at >= ? THEN 1 ELSE 0 END) AS week_count
            FROM click_events
            WHERE clicked_at >= ?
            GROUP BY link_id
            """,
            (day_cutoff, week_cutoff, week_cutoff),
        ):
            if row["link_id"] in catalog:
                totals[row["link_id"]]["day"] = int(row["day_count"] or 0)
                totals[row["link_id"]]["week"] = int(row["week_count"] or 0)

    ranked = sorted(
        (
            {
                "id": link_id,
                "name": str(catalog[link_id].get("name", link_id)),
                "url": str(catalog[link_id].get("url", "#")),
                **values,
            }
            for link_id, values in totals.items()
        ),
        key=lambda item: (-item["total"], item["name"].lower()),
    )

    return {"links": ranked, "generated_at": now}
