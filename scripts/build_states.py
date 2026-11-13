#!/usr/bin/env python3
"""Baut states.json aus Bootstrap, Handdatei und aktuellem Texas-Stand."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = ROOT / "data" / "tx-history-bootstrap.json"
MANUAL_PATH = ROOT / "data" / "states-manuell.json"
TRACKER_PATH = ROOT / "tracker.json"
STATES_PATH = ROOT / "states.json"

TXDMV_URL = (
    "https://txmccs.txdmv.gov/api/TruckStop/companies/"
    "81edcff1-8a6e-4ed0-be1f-60668515e223/automated-motor-vehicles"
)
TX_COLOR = "#FF6A00"
BOOTSTRAP_ORIGINS = {"robotaxistats", "robotaxistats-history", "wayback"}


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"{path.name} ist kein Objekt")
    return data


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def point_from_bootstrap(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": item["date"],
        "value": int(item["value"]),
        "dash": False,
        "status": "offiziell und live",
        "origin": item.get("origin") or "robotaxistats",
        "source_name": item.get("source_name"),
        "source_url": item.get("source_url"),
    }


def merge_series(
    bootstrap_points: list[dict[str, Any]],
    live_points: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for item in bootstrap_points:
        date = str(item.get("date") or "")
        if not date:
            continue
        by_date[date] = point_from_bootstrap(item)
    if isinstance(live_points, dict):
        live_points = [live_points]
    for lp in live_points or []:
        if not lp or not lp.get("date"):
            continue
        date = str(lp["date"])
        existing = by_date.get(date)
        if existing and existing.get("origin") in BOOTSTRAP_ORIGINS:
            # Feste historische Punkte nicht überschreiben, auch am selben Tag.
            continue
        by_date[date] = lp
    return [by_date[k] for k in sorted(by_date)]


def texas_block(
    series: list[dict[str, Any]],
    current: int,
    cybercab: int | None,
    as_of: str,
    source_url: str,
) -> dict[str, Any]:
    return {
        "id": "TX",
        "name": "Texas",
        "color": TX_COLOR,
        "current": current,
        "cybercab_current": cybercab,
        "as_of": as_of,
        "status": "offiziell und live",
        "source_name": "Texas DMV (TxMCCS). Historische Punkte bis 10.11.2026: robotaxistats (CC BY 4.0) und ein Wayback-API-Snapshot.",
        "source_url": source_url or TXDMV_URL,
        "note": "Zulassungen in Texas, nicht die Zahl der Autos auf der Straße und nicht nach Stadt aufgeteilt. Die Linie zählt alle Tesla-Robotaxis (Model Y und Cybercab), weil die historische Reihe so belegt ist.",
        "series": series,
    }


def without_volatile(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out.pop("last_updated", None)
    return out


def live_point(date: str, value: int, cybercab: int | None, source_url: str) -> dict[str, Any]:
    return {
        "date": date,
        "value": int(value),
        "dash": False,
        "status": "offiziell und live",
        "origin": "cybergiga-snapshot",
        "source_name": "Texas DMV (TxMCCS), eigener Snapshot",
        "source_url": source_url or TXDMV_URL,
        "cybercab": cybercab,
    }


def texas_series(
    history: list[dict[str, Any]] | None,
    tesla_total: int,
    as_of: str,
    source_url: str,
    cybercab_total: int | None = None,
) -> list[dict[str, Any]]:
    """Bootstrap plus alle eigenen Tageswerte (nicht nur der heutige).

    Bis 13.11.2026 wurde nur der heutige Live-Punkt angehängt, ältere eigene
    Tage fielen beim nächsten Tag wieder aus der Linie.
    """
    bootstrap = load_json(BOOTSTRAP_PATH)
    lives: list[dict[str, Any]] = []
    for row in history or []:
        if isinstance(row, dict) and isinstance(row.get("tesla_total"), int) and row.get("date") != as_of:
            lives.append(live_point(str(row["date"]), row["tesla_total"], row.get("registered_total"), source_url))
    lives.append(live_point(as_of, tesla_total, cybercab_total, source_url))
    return merge_series(list(bootstrap.get("points") or []), lives)


def build_states(
    tesla_total: int,
    cybercab_total: int | None,
    as_of: str,
    last_updated: str,
    source_url: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    manual = load_json(MANUAL_PATH)
    series = texas_series(history, tesla_total, as_of, source_url, cybercab_total)
    latest = series[-1]["value"] if series else tesla_total
    states = [texas_block(series, latest, cybercab_total, as_of, source_url)]
    for item in manual.get("states") or []:
        if not isinstance(item, dict):
            continue
        if item.get("id") == "TX":
            continue
        row = dict(item)
        row.setdefault("series", [])
        states.append(row)
    return {
        "ok": True,
        "last_updated": last_updated,
        "title": "Tesla-Robotaxis nach Bundesstaat",
        "metric": "Zugelassene Tesla-Robotaxis, soweit amtlich belegt. Das ist nicht die Zahl der Autos auf der Straße.",
        "y_axis": "Die Y-Achse richtet sich nach dem Staat mit der höchsten belegten Zahl (aktuell Texas).",
        "attribution": {
            "text": "Historische Texas-Werte: robotaxistats, CC BY 4.0, Primärquelle Texas DMV (TxMCCS). Aktueller Texas-Stand: eigener Abruf der öffentlichen TxDMV-Liste.",
            "url": "https://www.robotaxistats.com/",
            "license": "CC BY 4.0",
            "source_page": "https://www.robotaxistats.com/sources/tx-dmv/",
        },
        "states": states,
    }


def write_if_changed(new_doc: dict[str, Any]) -> bool:
    old = load_json(STATES_PATH) if STATES_PATH.exists() else None
    if old is not None and without_volatile(old) == without_volatile(new_doc):
        if old.get("last_updated") == new_doc.get("last_updated"):
            return False
        # Nur der Zeitstempel wäre neu: Datei trotzdem schreiben, wenn sie schon den Inhalt hat?
        # Gleicher Inhalt, anderer Zeitstempel: nicht schreiben, damit der Workflow nicht unnötig committed.
        return False
    atomic_write(STATES_PATH, new_doc)
    return True


def from_tracker() -> dict[str, Any]:
    tracker = load_json(TRACKER_PATH)
    tesla = tracker.get("tesla_registered_tx")
    if not isinstance(tesla, int):
        raise RuntimeError("tracker.json ohne tesla_registered_tx")
    cyber = tracker.get("registered_total")
    updated = str(tracker.get("last_updated") or iso(datetime.now(timezone.utc)))
    as_of = updated[:10] if len(updated) >= 10 else datetime.now(timezone.utc).date().isoformat()
    source_url = str(tracker.get("source_url") or TXDMV_URL)
    return build_states(
        tesla_total=tesla,
        cybercab_total=cyber if isinstance(cyber, int) else None,
        as_of=as_of,
        last_updated=updated,
        source_url=source_url,
        history=tracker.get("history") if isinstance(tracker.get("history"), list) else None,
    )


def build_and_write_from_live(
    tesla_total: int,
    cybercab_total: int | None,
    as_of: str,
    last_updated: str,
    source_url: str,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    doc = build_states(tesla_total, cybercab_total, as_of, last_updated, source_url, history)
    return write_if_changed(doc)


def main() -> int:
    doc = from_tracker()
    changed = write_if_changed(doc)
    tx = next(s for s in doc["states"] if s["id"] == "TX")
    print(
        f"ok=true states.json written={changed} tx={tx['current']} "
        f"points={len(tx['series'])} as_of={tx['as_of']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
