#!/usr/bin/env python3
"""
Fetch recent Hacker News stories, classify with OpenRouter LLM,
merge into public/data.json. Run hourly via GitHub Actions.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "public" / "data.json"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "anthropic/claude-haiku-4-5"
).strip()

# Search the last 14 days; we re-classify only items we haven't seen before.
LOOKBACK_DAYS = 14
# How many days of items to keep in data.json.
RETENTION_DAYS = 60

# Multiple narrow queries beat one broad query — Algolia ranks by recency
# within the result set, and a broad "linux" query buries the signal.
QUERIES = [
    "linux privilege escalation",
    "linux LPE",
    "linux kernel exploit",
    "linux kernel CVE",
    "sudo CVE",
    "polkit CVE",
    "pwnkit",
    "dirty pipe",
    "dirty cow",
    "container escape linux",
    "glibc CVE",
    "systemd CVE",
    "io_uring exploit",
    "netfilter exploit",
]

HN_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def fetch_hn() -> list[dict[str, Any]]:
    """Fetch HN stories matching any of our queries in the lookback window."""
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).timestamp())
    seen: dict[str, dict[str, Any]] = {}
    for q in QUERIES:
        try:
            r = requests.get(
                HN_SEARCH,
                params={
                    "query": q,
                    "tags": "story",
                    "numericFilters": f"created_at_i>{cutoff}",
                    "hitsPerPage": 50,
                },
                timeout=20,
            )
            r.raise_for_status()
            hits = r.json().get("hits", [])
        except Exception as e:
            log(f"HN query failed for {q!r}: {e}")
            continue

        for h in hits:
            sid = str(h.get("objectID") or "")
            if not sid or sid in seen:
                continue
            title = (h.get("title") or "").strip()
            if not title:
                continue
            seen[sid] = {
                "id": sid,
                "title": title,
                "url": (h.get("url") or "").strip()
                or f"https://news.ycombinator.com/item?id={sid}",
                "hn_url": f"https://news.ycombinator.com/item?id={sid}",
                "points": h.get("points") or 0,
                "num_comments": h.get("num_comments") or 0,
                "author": h.get("author") or "",
                "created_at": h.get("created_at") or "",
                "created_at_i": h.get("created_at_i") or 0,
            }
        time.sleep(0.2)  # be polite
    log(f"HN: {len(seen)} unique stories across {len(QUERIES)} queries")
    return list(seen.values())


CLASSIFY_SYSTEM = (
    "You are a security-news classifier. Decide if a Hacker News story is "
    "about a NEW or recently disclosed Linux local privilege escalation "
    "vulnerability, exploit, technique, or write-up. "
    "Qualify: kernel LPE bugs, sudo/polkit/systemd/glibc/setuid LPE, container "
    "escapes that yield host root from an unprivileged container user, eBPF "
    "or io_uring privilege bugs, public PoCs/exploits/write-ups for any of "
    "the above. "
    "Disqualify: Windows/macOS/Android-only issues, generic linux news, "
    "remote-code-execution-only without LPE angle, hardening/defense posts, "
    "tutorials about old/well-known bugs unless they cover a fresh "
    "disclosure, distro release notes, opinion pieces. "
    "Return STRICT JSON only with keys: is_privesc (bool), confidence (0-1 "
    "float), severity ('low'|'medium'|'high'|'critical'), cve (string or "
    "empty), summary (<= 200 chars, plain text). "
    "CRITICAL — cve field rules: only set cve to a CVE-YYYY-NNNN identifier "
    "if that exact identifier appears verbatim in the Title or URL. "
    "Do NOT infer, guess, or recall CVE numbers from memory. If the "
    "identifier is not literally in the input text, return cve as an empty "
    "string."
)


def classify_batch(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Classify items one-by-one (small models do worse on batched JSON)."""
    if not OPENROUTER_API_KEY:
        log("OPENROUTER_API_KEY missing — skipping classification")
        return {}
    out: dict[str, dict[str, Any]] = {}
    for it in items:
        verdict = classify_one(it)
        if verdict is not None:
            out[it["id"]] = verdict
        time.sleep(0.1)
    return out


def classify_one(item: dict[str, Any]) -> dict[str, Any] | None:
    user = (
        f"Title: {item['title']}\n"
        f"URL: {item.get('url', '')}\n"
        f"HN: {item['hn_url']}\n\n"
        "Classify per the system instructions. JSON only."
    )
    body = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": CLASSIFY_SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": 300,
    }
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://linuxprivesctoday.site",
                "X-Title": "linuxprivesctoday",
            },
            json=body,
            timeout=60,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"classify failed for {item['id']}: {e}")
        return None

    parsed = parse_json_lenient(content)
    if not isinstance(parsed, dict):
        log(f"classify non-dict for {item['id']}: {content[:200]}")
        return None
    return {
        "is_privesc": bool(parsed.get("is_privesc", False)),
        "confidence": clamp_float(parsed.get("confidence"), 0.0, 1.0),
        "severity": str(parsed.get("severity") or "").lower() or "unknown",
        "cve": str(parsed.get("cve") or "").strip().upper(),
        "summary": str(parsed.get("summary") or "").strip()[:240],
    }


def parse_json_lenient(s: str) -> Any:
    s = s.strip()
    # Strip ```json fences if the model adds them despite response_format.
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None


def clamp_float(v: Any, lo: float, hi: float) -> float:
    try:
        f = float(v)
    except Exception:
        return 0.0
    return max(lo, min(hi, f))


def canonical_url(url: str) -> str:
    """Normalize a URL for dedupe — strip scheme, www, query, fragment, and
    common GitHub path noise like /tree/<branch>, /blob/<branch>."""
    if not url:
        return ""
    s = url.strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = s.split("#", 1)[0]
    s = s.split("?", 1)[0]
    s = re.sub(r"/(tree|blob)/[^/]+/?$", "", s)
    s = re.sub(r"/(tree|blob)/[^/]+/", "/", s)
    return s.rstrip("/")


def load_existing() -> dict[str, Any]:
    if not DATA_FILE.exists():
        return {"items": {}, "generated_at": "", "model": ""}
    try:
        with DATA_FILE.open() as f:
            data = json.load(f)
        if isinstance(data.get("items"), list):
            data["items"] = {it["id"]: it for it in data["items"] if it.get("id")}
        if not isinstance(data.get("items"), dict):
            data["items"] = {}
        return data
    except Exception as e:
        log(f"load existing failed: {e} — starting fresh")
        return {"items": {}, "generated_at": "", "model": ""}


def main() -> int:
    existing = load_existing()
    items_by_id: dict[str, dict[str, Any]] = existing["items"]

    fresh = fetch_hn()
    new_items = [it for it in fresh if it["id"] not in items_by_id]
    log(f"new (unclassified) stories: {len(new_items)}")

    verdicts = classify_batch(new_items)

    for it in new_items:
        v = verdicts.get(it["id"])
        if v is None:
            continue  # don't store unclassified — try again next run
        it.update(v)
        items_by_id[it["id"]] = it

    # Drop items older than RETENTION_DAYS to keep data.json bounded.
    cutoff_i = int(
        (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).timestamp()
    )
    items_by_id = {
        k: v
        for k, v in items_by_id.items()
        if int(v.get("created_at_i") or 0) >= cutoff_i
    }

    # Output: list sorted newest-first.
    items = sorted(
        items_by_id.values(),
        key=lambda x: int(x.get("created_at_i") or 0),
        reverse=True,
    )

    # Dedupe by canonical URL — when the same story is submitted to HN
    # multiple times, keep the highest-points submission.
    by_canon: dict[str, dict[str, Any]] = {}
    for it in items:
        key = canonical_url(it.get("url", "")) or f"hn:{it['id']}"
        cur = by_canon.get(key)
        if cur is None or (it.get("points") or 0) > (cur.get("points") or 0):
            by_canon[key] = it
    items = sorted(
        by_canon.values(),
        key=lambda x: int(x.get("created_at_i") or 0),
        reverse=True,
    )

    privesc_items = [x for x in items if x.get("is_privesc")]

    today_utc = datetime.now(timezone.utc).date()
    today_count = sum(
        1
        for x in privesc_items
        if datetime.fromtimestamp(int(x.get("created_at_i") or 0), tz=timezone.utc).date()
        == today_utc
    )

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": OPENROUTER_MODEL if OPENROUTER_API_KEY else "(none)",
        "today_count": today_count,
        "total_privesc": len(privesc_items),
        "total_scanned": len(items),
        "items": items,
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w") as f:
        json.dump(out, f, indent=2, sort_keys=False)
    log(
        f"wrote {DATA_FILE} — {len(items)} scanned, {len(privesc_items)} privesc, "
        f"{today_count} today"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
