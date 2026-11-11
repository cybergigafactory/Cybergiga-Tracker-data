#!/usr/bin/env python3
"""Aktualisiert tracker.json aus der öffentlichen TxDMV-AV-Liste.

Nur Aggregatzahlen in tracker.json. VIN-Liste mit first_seen_at in data/vins.json.
Keine Personendaten, keine Adressen, keine Kennzeichen (liefert die API nicht).
Bei API-Fehler bleibt der letzte gute Stand unverändert, Logzeile ok=false.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRACKER_PATH = ROOT / "tracker.json"
VINS_PATH = ROOT / "data" / "vins.json"

DEFAULT_COMPANY_ID = "81edcff1-8a6e-4ed0-be1f-60668515e223"
SEARCH_NAME = "Tesla Robotaxi"
CYBERCAB_PREFIX = "5YJAJEEU"
MODEL_Y_PREFIX = "7SAYGDEE"
PAGE_LIMIT = 100
MAX_OFFSET = 20000
HTTP_RETRIES = 3
HTTP_TIMEOUT = 30
USER_AGENT = (
    "Cybergiga-Tracker/1.0 "
    "(+https://github.com/cybergigafactory/Cybergiga-Tracker-data)"
)
API_BASE = "https://txmccs.txdmv.gov/api/TruckStop"
FORCE_TIMESTAMP_AFTER = timedelta(hours=12)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("tracker")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def http_get_json(url: str) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, HTTP_RETRIES + 1):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                raw = resp.read()
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status} für {url}")
                return json.loads(raw.decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            log.warning("Versuch %s/%s fehlgeschlagen: %s", attempt, HTTP_RETRIES, exc)
            if attempt < HTTP_RETRIES:
                time.sleep(2 * attempt)
    raise RuntimeError(f"API-Abruf fehlgeschlagen: {last_error}")


def discover_company_id() -> str:
    query = urllib.parse.urlencode(
        {
            "searchType": "CompanyName",
            "searchValue": SEARCH_NAME,
            "limit": 5,
            "offset": 0,
        }
    )
    data = http_get_json(f"{API_BASE}/companies?{query}")
    results = data.get("results") if isinstance(data, dict) else None
    if not results:
        raise RuntimeError("Firmensuche lieferte keine Treffer")
    first = results[0]
    cid = first.get("businessEntityId") or first.get("id") or first.get("companyId")
    name = first.get("companyName") or first.get("name") or ""
    if not cid:
        raise RuntimeError("Firmensuche ohne ID")
    log.info("Firma gefunden: %s id=%s", name, cid)
    return str(cid)


def vehicles_url(company_id: str, limit: int, offset: int) -> str:
    query = urllib.parse.urlencode({"limit": limit, "offset": offset})
    return f"{API_BASE}/companies/{company_id}/automated-motor-vehicles?{query}"


def fetch_all_vins(company_id: str) -> tuple[list[str], int, str]:
    offset = 0
    collected: list[str] = []
    total: int | None = None
    source_url = f"{API_BASE}/companies/{company_id}/automated-motor-vehicles"
    while offset <= MAX_OFFSET:
        url = vehicles_url(company_id, PAGE_LIMIT, offset)
        data = http_get_json(url)
        if not isinstance(data, dict):
            raise RuntimeError("Unerwartete API-Antwort (kein Objekt)")
        rows = data.get("vehicles")
        if not isinstance(rows, list):
            raise RuntimeError("Unerwartete API-Antwort (kein vehicles-Feld)")
        if "total" not in data:
            raise RuntimeError("Unerwartete API-Antwort (kein total-Feld)")
        total = int(data["total"])
        page_vins: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            vin = str(row.get("vin") or "").strip().upper()
            if vin:
                page_vins.append(vin)
        collected.extend(page_vins)
        log.info("Seite offset=%s n=%s total=%s", offset, len(page_vins), total)
        if not page_vins:
            break
        offset += PAGE_LIMIT
        if offset >= total:
            break
        if len(page_vins) < PAGE_LIMIT and offset < total:
            raise RuntimeError(
                f"Seite unvollständig: {len(page_vins)} bei total={total} offset={offset - PAGE_LIMIT}"
            )
    if total is None:
        raise RuntimeError("Kein total von der API")
    unique = sorted(set(collected))
    if len(collected) != len(unique):
        log.warning("Doppelte VINs in der Antwort: %s roh, %s eindeutig", len(collected), len(unique))
    if len(unique) != total:
        raise RuntimeError(
            f"Zählung weicht ab: {len(unique)} eindeutige VINs, API-total={total}"
        )
    return unique, total, source_url


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Bestehende Datei unlesbar: {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Bestehende Datei ist kein Objekt: {path.name}")
    return data


def previous_first_seen(prev: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not prev:
        return out
    rows = prev.get("vins")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            vin = str(row.get("vin") or "").strip().upper()
            seen = row.get("first_seen_at")
            if vin and isinstance(seen, str) and seen:
                out[vin] = seen
    elif isinstance(rows, dict):
        for vin, meta in rows.items():
            key = str(vin).strip().upper()
            if isinstance(meta, dict):
                seen = meta.get("first_seen_at")
            elif isinstance(meta, str):
                seen = meta
            else:
                seen = None
            if key and isinstance(seen, str) and seen:
                out[key] = seen
    return out


def classify(vins: list[str]) -> dict[str, int]:
    cyber = sum(1 for v in vins if v.startswith(CYBERCAB_PREFIX))
    model_y = sum(1 for v in vins if v.startswith(MODEL_Y_PREFIX))
    other = len(vins) - cyber - model_y
    return {
        "registered_total": cyber,
        "tesla_registered_tx": len(vins),
        "model_y_registered_tx": model_y,
        "unclassified_vin_count": other,
    }


def history_with_today(prev_tracker: dict[str, Any] | None, today: str, total: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if prev_tracker and isinstance(prev_tracker.get("history"), list):
        for item in prev_tracker["history"]:
            if not isinstance(item, dict):
                continue
            date = item.get("date")
            value = item.get("registered_total")
            if not isinstance(date, str):
                continue
            if not isinstance(value, int):
                continue
            if date == today:
                continue
            rows.append({"date": date, "registered_total": value})
    rows.append({"date": today, "registered_total": total})
    rows.sort(key=lambda r: r["date"])
    return rows[-400:]


def lookup_history(history: list[dict[str, Any]], date: str) -> int | None:
    for item in history:
        if item.get("date") == date:
            value = item.get("registered_total")
            if isinstance(value, int):
                return value
    return None


def compute_deltas(
    history: list[dict[str, Any]],
    current: int,
    now: datetime,
    first_snapshot_at: datetime,
) -> tuple[int | None, int | None]:
    delta_1d: int | None = None
    delta_1w: int | None = None
    if now >= first_snapshot_at + timedelta(days=1):
        prior = lookup_history(history, (now.date() - timedelta(days=1)).isoformat())
        if prior is not None:
            delta_1d = current - prior
    if now >= first_snapshot_at + timedelta(days=7):
        prior = lookup_history(history, (now.date() - timedelta(days=7)).isoformat())
        if prior is not None:
            delta_1w = current - prior
    return delta_1d, delta_1w


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def meaningful_change(old: dict[str, Any] | None, new: dict[str, Any], keys: list[str]) -> bool:
    if old is None:
        return True
    for key in keys:
        if old.get(key) != new.get(key):
            return True
    return False


def vins_changed(old_map: dict[str, str], new_rows: list[dict[str, str]]) -> bool:
    new_map = {row["vin"]: row["first_seen_at"] for row in new_rows}
    return old_map != new_map


def should_write_tracker(
    prev: dict[str, Any] | None,
    new: dict[str, Any],
    now: datetime,
) -> bool:
    if prev is None:
        return True
    keys = [
        "registered_total",
        "tesla_registered_tx",
        "model_y_registered_tx",
        "unclassified_vin_count",
        "delta_1d",
        "delta_1w",
        "history",
        "source_url",
        "ok",
    ]
    if meaningful_change(prev, new, keys):
        return True
    prev_updated = parse_iso(str(prev.get("last_updated") or ""))
    if prev_updated is None:
        return True
    return now - prev_updated >= FORCE_TIMESTAMP_AFTER


def fail(message: str) -> int:
    log.error("ok=false %s", message)
    print(f"ok=false error={message}", file=sys.stderr)
    return 1


def main() -> int:
    prev_tracker = load_json(TRACKER_PATH)
    prev_vins_doc = load_json(VINS_PATH)
    prev_counts = None
    if prev_tracker and isinstance(prev_tracker.get("registered_total"), int):
        prev_counts = {
            "registered_total": prev_tracker["registered_total"],
            "tesla_registered_tx": prev_tracker.get("tesla_registered_tx"),
        }

    try:
        company_id = DEFAULT_COMPANY_ID
        try:
            vins, api_total, source_url = fetch_all_vins(company_id)
        except Exception as first_exc:
            log.warning("Abruf mit bekannter ID fehlgeschlagen: %s, versuche Firmensuche", first_exc)
            company_id = discover_company_id()
            vins, api_total, source_url = fetch_all_vins(company_id)
    except Exception as exc:
        return fail(str(exc))

    if not vins:
        return fail("API lieferte keine VINs")

    if prev_counts and isinstance(prev_counts.get("tesla_registered_tx"), int):
        previous_total = prev_counts["tesla_registered_tx"]
        if previous_total >= 20 and api_total < previous_total * 0.5:
            return fail(
                f"Verdacht auf unvollständige Antwort: total={api_total}, zuvor={previous_total}"
            )

    counts = classify(vins)
    now = utcnow()
    today = now.date().isoformat()
    prev_seen = previous_first_seen(prev_vins_doc)
    first_snapshot_at = parse_iso(
        (prev_vins_doc or {}).get("first_snapshot_at")
        or (prev_tracker or {}).get("first_snapshot_at")
    ) or now

    vin_rows = []
    for vin in vins:
        seen = prev_seen.get(vin) or iso(now)
        vin_rows.append({"vin": vin, "first_seen_at": seen})

    history = history_with_today(prev_tracker, today, counts["registered_total"])
    delta_1d, delta_1w = compute_deltas(
        history, counts["registered_total"], now, first_snapshot_at
    )

    tracker = {
        "ok": True,
        "registered_total": counts["registered_total"],
        "delta_1d": delta_1d,
        "delta_1w": delta_1w,
        "last_updated": iso(now),
        "source_url": source_url,
        "source_name": "Texas DMV (TxMCCS)",
        "tesla_registered_tx": counts["tesla_registered_tx"],
        "model_y_registered_tx": counts["model_y_registered_tx"],
        "unclassified_vin_count": counts["unclassified_vin_count"],
        "vin_prefix_cybercab": CYBERCAB_PREFIX,
        "note": (
            "Zulassungen von Cybercabs in Texas. "
            "Das ist nicht die Zahl der Autos auf der Straße und nicht nach Stadt aufgeteilt."
        ),
        "first_snapshot_at": iso(first_snapshot_at),
        "history": history,
    }

    vins_doc = {
        "ok": True,
        "last_updated": iso(now),
        "first_snapshot_at": iso(first_snapshot_at),
        "source_url": source_url,
        "company_id": company_id,
        "company_name": "Tesla Robotaxi, LLC",
        "registered_total": counts["registered_total"],
        "tesla_registered_tx": counts["tesla_registered_tx"],
        "model_y_registered_tx": counts["model_y_registered_tx"],
        "unclassified_vin_count": counts["unclassified_vin_count"],
        "vin_prefix_cybercab": CYBERCAB_PREFIX,
        "vins": vin_rows,
    }

    write_vins = vins_changed(prev_seen, vin_rows) or prev_vins_doc is None
    write_tracker = should_write_tracker(prev_tracker, tracker, now)

    if write_vins:
        atomic_write(VINS_PATH, vins_doc)
        log.info("data/vins.json geschrieben (%s VINs)", len(vin_rows))
    else:
        log.info("data/vins.json unverändert")

    if write_tracker:
        atomic_write(TRACKER_PATH, tracker)
        log.info("tracker.json geschrieben")
    else:
        log.info("tracker.json unverändert (nur Zeitstempel, unter 12 Stunden)")

    if counts["unclassified_vin_count"]:
        log.warning(
            "Unbekannte VIN-Präfixe: %s (nicht %s und nicht %s)",
            counts["unclassified_vin_count"],
            CYBERCAB_PREFIX,
            MODEL_Y_PREFIX,
        )

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from build_states import build_and_write_from_live
        states_written = build_and_write_from_live(
            tesla_total=counts["tesla_registered_tx"],
            cybercab_total=counts["registered_total"],
            as_of=today,
            last_updated=iso(now),
            source_url=source_url,
        )
        log.info("states.json geschrieben=%s", states_written)
    except Exception as states_exc:
        log.warning("states.json nicht aktualisiert: %s", states_exc)

    log.info(
        "ok=true registered_total=%s tesla_registered_tx=%s model_y=%s delta_1d=%s delta_1w=%s",
        counts["registered_total"],
        counts["tesla_registered_tx"],
        counts["model_y_registered_tx"],
        delta_1d,
        delta_1w,
    )
    print(
        "ok=true "
        f"registered_total={counts['registered_total']} "
        f"tesla_registered_tx={counts['tesla_registered_tx']} "
        f"delta_1d={delta_1d} delta_1w={delta_1w}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        sys.exit(fail(str(exc)))
