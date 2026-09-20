"""Refresh the pinned audit cohort without crawling unrelated historical pages.

Page movement or changed identity/event evidence fails closed. Raw responses are
retained in the output directory for inspection; audit judgments are not changed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from atlanticbridge.entry_identity import normalize_legal_name
from atlanticbridge.sources.corporations_canada import (
    fetch_corporation_json, detail_corporation_names, first_federal_jurisdiction_event,
)
from atlanticbridge.sources.investment_canada import fetch_index_page, parse_index_html


def refresh(cases_path, output):
    payload = json.loads(Path(cases_path).read_text())
    cases = payload['cases']
    if len(cases) != payload['case_count'] or len({c['outcome_record_id'] for c in cases}) != len(cases):
        raise ValueError('Pinned cohort count or unique IDs do not agree')
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=True)

    def page(url):
        parsed = urlparse(url)
        bucket = parsed.path.rstrip('/').split('/')[-1]
        index = int(parse_qs(parsed.query).get('page', ['0'])[0])
        fetched_url, html = fetch_index_page(bucket, index)
        (folder / f'notification-{bucket}-{index}.html').write_text(html)
        rows = parse_index_html(html, source_url_value=fetched_url, source_bucket=bucket, source_page=index)
        return url, {r.record_id: r for r in rows}, hashlib.sha256(html.encode()).hexdigest()

    with ThreadPoolExecutor(max_workers=4) as pool:
        pages = {url: (rows, digest) for url, rows, digest in pool.map(page, sorted({c['outcome_source_url'] for c in cases}))}

    def case(c):
        rows, page_hash = pages[c['outcome_source_url']]
        r = rows.get(c['outcome_record_id'])
        if r is None:
            raise ValueError(f"Notification moved or changed: {c['outcome_record_id']}")
        if not r.is_new_business or r.investor_name != c['investor_name'] or r.certification_month != c['notification_month']:
            raise ValueError(f"Notification classification changed: {c['outcome_record_id']}")
        url, raw = fetch_corporation_json(c['corporation_number'])
        text = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        (folder / f"registry-{c['corporation_number']}.json").write_text(text + '\n')
        names = {normalize_legal_name(n) for n in detail_corporation_names(raw)}
        if normalize_legal_name(c['canadian_business_name']) not in names:
            raise ValueError(f"Registry name changed: {c['corporation_number']}")
        businesses = json.loads(r.canadian_businesses_json)
        if normalize_legal_name(c['canadian_business_name']) not in {normalize_legal_name(b['name']) for b in businesses}:
            raise ValueError(f"Notification business differs: {c['outcome_record_id']}")
        if first_federal_jurisdiction_event(raw) != (c['federal_event_type'], c['federal_event_date']):
            raise ValueError(f"Registry event changed: {c['corporation_number']}")
        return {'outcome_record_id': c['outcome_record_id'], 'corporation_number': c['corporation_number'],
                'notification_page_sha256': page_hash, 'registry_raw_sha256': hashlib.sha256(text.encode()).hexdigest(),
                'registry_source_url': url, 'status': 'NOTIFICATION_AND_REGISTRY_EVENT_VERIFIED'}

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(case, cases))
    summary = {'observed_at': datetime.now(timezone.utc).isoformat(), 'case_count': len(results),
               'scope': 'Pinned notification and registry event refresh; first operations and model eligibility not asserted',
               'cases': results}
    (folder / 'refresh.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, sort_keys=True))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', default='reviews/outcome_audit/2026-09-20-cases.json')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    refresh(args.cases, args.output)
