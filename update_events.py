#!/usr/bin/env python3
"""Actualise events.json à partir des événements publics d'Île-de-France.

Aucune dépendance externe. N'écrase pas le catalogue si la collecte échoue.
"""
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "events.json"
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
    text = re.sub(r"<[^>]*>", " ", str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_date(value):
    if isinstance(value, dict):
        value = value.get("date") or value.get("begin") or value.get("start")
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value or ""))
    if match:
        try:
            return dt.date.fromisoformat(match.group(0))
        except ValueError:
            pass
    return None


def span_days(start, end):
    if not start:
        return []
    end = end or start
    if end < start or (end - start).days > 31:
        return []
    first, last = max(start, TODAY), min(end, UNTIL)
    if last < first:
        return []
    return [(first + dt.timedelta(days=i)).isoformat()
            for i in range((last - first).days + 1)]


def occurrence_dates(fields):
    raw = fields.get("timings") or fields.get("detailed_times") or fields.get("times")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = None
    if isinstance(raw, dict):
        raw = raw.get("events") or raw.get("dates") or raw.get("times") or [raw]

    if isinstance(raw, list) and raw:
        days = set()
        valid_entries = 0
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            start = parse_date(entry.get("begin") or entry.get("start") or entry.get("date"))
            end = parse_date(entry.get("end") or entry.get("finish"))
            if start:
                valid_entries += 1
                days.update(span_days(start, end))
        # Des séances détaillées existent : ne pas remplir artificiellement
        # l'intervalle global lorsque les séances sont passées ou espacées.
        if valid_entries:
            return sorted(days)

    start = parse_date(fields.get("firstdate_begin") or fields.get("first_date_beginning"))
    end = parse_date(fields.get("lastdate_end") or fields.get("last_date_end"))
    if not start:
        return []
    if not end or end == start:
        return span_days(start, start)
    # Sans séances détaillées, seules les dates attestées sont conservées.
    return sorted(set(span_days(start, start) + span_days(end, end)))


def department(fields):
    code = clean(fields.get("location_department") or fields.get("department") or fields.get("departement"))
    if code in DEPTS:
        return code
    postcode = clean(fields.get("location_postalcode") or fields.get("postal_code") or fields.get("zipcode"))
    match = re.search(r"\b(75|77|78|91|92|93|94|95)\d{3}\b", postcode)
    return match.group(1) if match else None


def normalize(record):
    fields = record.get("fields") or record
    title = clean(fields.get("title_fr") or fields.get("title"))
    dep = department(fields)
    dates = occurrence_dates(fields)
    uid = clean(fields.get("uid") or fields.get("id") or record.get("recordid"))
    if not title or not dep or not dates or not uid:
        return None

    city = clean(fields.get("location_city") or fields.get("city"))
    venue = clean(fields.get("location_name") or fields.get("place_name"))
    address = clean(fields.get("location_address") or fields.get("address"))
    description = clean(fields.get("description_fr") or fields.get("longdescription_fr") or fields.get("description"))
    url = clean(fields.get("canonicalurl") or fields.get("url") or fields.get("location_website"))
    if not url.startswith(("https://", "http://")):
        url = "https://data.iledefrance.fr/explore/dataset/evenements-publics-cibul/"
    return {
        "id": "idf-" + uid,
        "name": title[:140],
        "place": ", ".join(x for x in (venue, address, city) if x),
        "city": city,
        "dept": dep,
        "dates": dates,
        "time": "Voir les horaires dans la source",
        "price": "Voir les conditions dans la source",
        "desc": description[:320] or "Consulte la programmation et les modalités auprès de l'organisateur.",
        "url": url,
        "emoji": "✦",
        "source": "Région Île-de-France / OpenAgenda",
        "updated": clean(fields.get("updatedat") or fields.get("last_update")),
    }


def fetch_page(offset):
    # Filtrage côté serveur : ne pas parcourir des milliers d'archives anciennes.
    where = (f"lastdate_end >= date'{TODAY.isoformat()}' "
             f"AND firstdate_begin <= date'{UNTIL.isoformat()}'")
    query = urllib.parse.urlencode({
        "where": where,
        "order_by": "firstdate_begin ASC",
        "limit": PAGE_SIZE,
        "offset": offset,
    })
    request = urllib.request.Request(
        BASE + "?" + query,
        headers={"User-Agent": "dehors-app/1.0 (public event sync)", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        data = json.load(response)
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise RuntimeError("Réponse API inattendue : results absent")
    return data


def main():
    print(f"Collecte des événements du {TODAY} au {UNTIL}", flush=True)
    unique = {}
    received = 0
    total = None
    for offset in range(0, MAX_RECORDS, PAGE_SIZE):
        data = fetch_page(offset)
        rows = data["results"]
        total = data.get("total_count", total)
        received += len(rows)
        for row in rows:
            item = normalize(row)
            if item:
                unique[item["id"]] = item
        print(f"Reçus : {received} / {total or '?'} | valides : {len(unique)}", flush=True)
        if len(rows) < PAGE_SIZE:
            break

    if not unique:
        raise RuntimeError("Aucun événement futur valide : events.json conservé")
    if total is not None and total > MAX_RECORDS:
        print(f"Attention : {total} résultats possibles, collecte plafonnée à {MAX_RECORDS}.", flush=True)

    events = sorted(unique.values(), key=lambda e: (e["dates"][0], e["name"]))
    payload = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": BASE,
        "events": events,
    }
    # Écriture atomique pour éviter un JSON partiellement écrit.
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(f"SUCCÈS : {len(events)} événements enregistrés dans {OUTPUT.name}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (urllib.error.URLError, ValueError, RuntimeError) as exc:
        print(f"ERREUR : {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
