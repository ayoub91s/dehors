
#!/usr/bin/env python3
"""Synchronise les annonces publiques de la Région Île-de-France vers events.json.
Aucune dépendance Python externe. Ne crée pas de dates fictives.
"""
import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = 'https://data.iledefrance.fr/api/explore/v2.1/catalog/datasets/evenements-publics-cibul/records'
DEPTS = {'75', '77', '78', '91', '92', '93', '94', '95'}
TODAY = dt.datetime.now(dt.timezone.utc).date()
UNTIL = TODAY + dt.timedelta(days=150)


def string(v):
    if isinstance(v, str):
        return re.sub(r'<[^>]+>', ' ', v).strip()
    if isinstance(v, dict):
        return str(v.get('fr') or v.get('en') or next(iter(v.values()), ''))
    return str(v or '')


def datepart(v):
    if isinstance(v, dict):
        v = v.get('date') or v.get('start') or v.get('begin') or ''
    if not isinstance(v, str):
        return None
    m = re.search(r'\d{4}-\d{2}-\d{2}', v)
    return m.group(0) if m else None


def dates_for(f):
    # Les dates détaillées sont prioritaires.
    spans = f.get('detailed_times') or f.get('times')

    if isinstance(spans, str):
        try:
            spans = json.loads(spans)
        except (ValueError, TypeError):
            spans = None

    if isinstance(spans, dict):
        spans = (
            spans.get('events')
            or spans.get('dates')
            or spans.get('times')
            or [spans]
        )

    days = set()

    if isinstance(spans, list):
        for item in spans:
            if not isinstance(item, dict):
                continue

            start = datepart(
                item.get('begin')
                or item.get('start')
                or item.get('date')
            )
            end = datepart(
                item.get('end')
                or item.get('finish')
            ) or start

            if not start:
                continue

            try:
                a = dt.date.fromisoformat(start)
                b = dt.date.fromisoformat(end)

                if b < a or (b - a).days > 31:
                    continue

                for i in range((b - a).days + 1):
                    day = a + dt.timedelta(days=i)

                    if TODAY <= day <= UNTIL:
                        days.add(day.isoformat())

            except ValueError:
                continue

    if days:
        return sorted(days)

    # Intervalle global utilisé uniquement si fourni par la source.
    a = datepart(
        f.get('first_date_beginning')
        or f.get('first_date_begin')
        or f.get('firstdate_begin')
    )
    b = datepart(
        f.get('last_date_end')
        or f.get('last_date_beginning')
        or f.get('lastdate_end')
    ) or a

    if a and b:
        try:
            x = dt.date.fromisoformat(a)
            y = dt.date.fromisoformat(b)

            if y >= x and (y - x).days <= 31:
                return [
                    (x + dt.timedelta(days=i)).isoformat()
                    for i in range((y - x).days + 1)
                    if TODAY <= x + dt.timedelta(days=i) <= UNTIL
                ]

        except ValueError:
            pass

    return []


def normalise(record):
    f = (
        record.get('record', {}).get('fields')
        or record.get('fields')
        or record
    )

    name = string(f.get('title'))

    if not name:
        return None

    dep = string(
        f.get('department')
        or f.get('departement')
    )

    if not dep or dep not in DEPTS:
        zipc = string(
            f.get('postal_code')
            or f.get('zipcode')
        )
        dep = zipc[:2] if zipc else ''

    if dep not in DEPTS:
        return None

    dates = dates_for(f)

    if not dates:
        return None

    city = string(
        f.get('city')
        or f.get('commune')
    )

    address = string(
        f.get('address')
        or f.get('place_address')
    )

    venue = string(f.get('place_name'))

    desc = string(
        f.get('description')
        or f.get('long_description')
    )[:320]

    url = string(
        f.get('url')
        or f.get('canonical_url')
        or f.get('link')
    )

    if not url.startswith(('https://', 'http://')):
        url = (
            'https://data.iledefrance.fr/explore/'
            'dataset/evenements-publics-cibul/table/'
        )

    raw_id = string(
        f.get('id')
        or f.get('uid')
        or record.get('recordid')
        or record.get('record', {}).get('id')
    )

    if not raw_id:
        return None

    return {
        'id': 'idf-' + raw_id,
        'name': name[:140],
        'place': ', '.join(
            x for x in (venue, address, city) if x
        ),
        'city': city,
        'dept': dep,
        'dates': dates,
        'time': 'Voir les horaires dans la source',
        'price': 'Voir les conditions dans la source',
        'desc': desc or (
            'Événement temporaire : consulte la programmation '
            'et les modalités auprès de l’organisateur.'
        ),
        'url': url,
        'emoji': '✦',
        'source': 'Région Île-de-France / OpenAgenda',
        'updated': string(f.get('last_update'))
    }


def main():
    items = []

    print('=== DIAGNOSTIC DEHORS ===', flush=True)
    print('Source API :', BASE, flush=True)
    print('Date actuelle :', TODAY, flush=True)
    print('Date limite :', UNTIL, flush=True)

    total_received = 0

    # API paginée : 100 enregistrements par requête.
    for offset in range(0, 2000, 100):

        query = urllib.parse.urlencode({
            'limit': 100,
            'offset': offset,
            'order_by': '-record_timestamp'
        })

        request = urllib.request.Request(
            BASE + '?' + query,
            headers={
                'User-Agent': 'dehors-app/1.0 (open-data sync)'
            }
        )

        print(
            f'Récupération des événements : offset {offset}',
            flush=True
        )

        with urllib.request.urlopen(request, timeout=35) as response:
            print(
                'Code HTTP :',
                response.status,
                flush=True
            )
            body = json.load(response)

        rows = body.get('results', [])

        # NOUVEAU : informations de diagnostic.
        print(
            'Nombre de résultats reçus :',
            len(rows),
            flush=True
        )

        if offset == 0:
            print(
                'Champs de la réponse API :',
                list(body.keys()),
                flush=True
            )

            if rows:
                print(
                    'Champs du premier événement :',
                    list(rows[0].keys()),
                    flush=True
                )

                print(
                    'Premier événement brut :',
                    json.dumps(
                        rows[0],
                        ensure_ascii=False,
                        default=str
                    )[:4000],
                    flush=True
                )

        total_received += len(rows)

        valid_on_page = 0

        for r in rows:
            item = normalise(r)

            if item:
                items.append(item)
                valid_on_page += 1

        print(
            f'Événements valides sur cette page : {valid_on_page}',
            flush=True
        )

        if len(rows) < 100:
            break

    print('=== BILAN ===', flush=True)
    print('Événements reçus :', total_received, flush=True)
    print('Événements valides :', len(items), flush=True)

    if not items:
        raise RuntimeError(
            'Aucun événement valide récupéré : '
            'conservation du flux précédent'
        )

    unique = {
        e['id']: e
        for e in items
    }

    payload = {
        'updated_at': dt.datetime.now(
            dt.timezone.utc
        ).isoformat(),
        'source': BASE,
        'events': list(unique.values())
    }

    (ROOT / 'events.json').write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ),
        encoding='utf-8'
    )

    print(
        f'{len(unique)} événements publiés',
        flush=True
    )


if __name__ == '__main__':
    main()
