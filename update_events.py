#!/usr/bin/env python3
"""Met à jour events.json avec les événements datés d'Île-de-France.

Source : portail open data de la Région Île-de-France (OpenAgenda).
Bibliothèque standard Python uniquement. Les anciennes données sont préservées
si la collecte ne produit aucun événement valide.
"""
import datetime as dt
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "https://data.iledefrance.fr/api/explore/v2.1/catalog/datasets/evenements-publics-cibul/records"
DEPTS = {"75", "77", "78", "91", "92", "93", "94", "95"}
TODAY = dt.datetime.now(dt.timezone.utc).date()
UNTIL = TODAY + dt.timedelta(days=150)
PAGE_SIZE = 100
MAX_RECORDS = 5000


def clean(value):
    if isinstance(value, dict):
        value = value.get("fr") or value.get("en") or next(iter(value.values()), "")
    if isinstance(value, list):
        value = ", ".join(map(str, value))
    text = str(value or "")
    text = re.sub(r"<[^>]*>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def first_date(value):
    if isinstance(value, dict):
        value = value.get("date") or value.get("begin") or value.get("start")
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value or ""))
    if not match:
        return None
    try:
        return dt.date.fromisoformat(match.group(0))
    except ValueError:
        return None


def date_span(start, end, max_days=31):
    if not start:
        return []
    end = end or start
    if end < start or (end - start).days > max_days:
        return []
    a, b = max(start, TODAY), min(end, UNTIL)
    if b < a:
        return []
    return [(a + dt.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def occurrence_dates(fields):
    """Priorité aux occurrences détaillées pour éviter de combler les interruptions."""
    raw = fields.get("timings") or fields.get("detailed_times") or fields.get("times")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = None
    if isinstance(raw, dict):
        raw = raw.get("events") or raw.get("dates") or raw.get("times") or [raw]

    dates = set()
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            start = first_date(entry.get("begin") or entry.get("start") or entry.get("date"))
            end = first_date(entry.get("end") or entry.get("finish"))
            dates.update(date_span(start, end))
        if dates:
            return sorted(dates)

    # Sans occurrences exploitables, ne supposer une plage continue que si elle
    # est courte. Pour les longues périodes, conserver uniquement les dates
    # de début et fin connues (sans remplir les jours intermédiaires).
    start = first_date(fields.get("firstdate_begin") or fields.get("first_date_beginning"))
    end = first_date(fields.get("lastdate_end") or fields.get("last_date_end"))
    if not start:
        return []
    if not end or end == start:
        return date_span(start, start)
    if end < start:
        return []
    if (end - start).days <= 7:
        return date_span(start, end, max_days=7)
    return sorted(set(date_span(start, start) + date_span(end, end)))
