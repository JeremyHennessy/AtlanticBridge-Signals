"""Documentary event review over source-local discovery; never first-entry inference.

Plans, ceremonies, reported openings and production bounds are different events.
Source-country labels are not corporate control. No model gate is opened here.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date
import re
import unicodedata

from bs4 import BeautifulSoup

from .company_sources import instant, parse_article, url
from .constants import EU27

KINDS = {
    'PROJECT_ANNOUNCED': 'SOURCE_ASSERTED_DAY',
    'OPENING_ANNOUNCED': 'SOURCE_ASSERTED_DAY',
    'INAUGURATION_REPORTED': 'SOURCE_ASSERTED_DAY',
    'IMPLEMENTATION_REPORTED': 'REPORTED_BY_DAY',
    'OPENING_REPORTED': 'REPORTED_BY_DAY',
    'OPERATING_BY_DATE': 'UPPER_BOUND_DAY',
    'PROJECT_COMPLETED_BY_DATE': 'UPPER_BOUND_DAY',
    'SERVICE_AVAILABLE_BY_DATE': 'UPPER_BOUND_DAY',
    'OFFICE_ESTABLISHED_BY_DATE': 'UPPER_BOUND_DAY',
}
FORBIDDEN_FLAGS = ('legal_identity_confirmed', 'first_entry_confirmed',
                   'independent_holdout', 'backtest_eligible', 'public_alert_allowed')


def normalized(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('Evidence text must be a string')
    return ' '.join(unicodedata.normalize('NFKC', value).split()).casefold()


def origin_label_bucket(label: str) -> str:
    """Triage source labels only; preserve mixed origins and unrecognized countries."""
    if label in EU27:
        return 'EU27_SOURCE_LABEL_NOT_CONTROL_PROOF'
    if label in {'United Kingdom', 'Norway', 'Switzerland'}:
        return 'OTHER_EUROPE_SOURCE_LABEL_NOT_CONTROL_PROOF'
    if label in {'Netherlands & South Korea', 'South Korea and United States'}:
        return 'MIXED_SOURCE_LABEL_REQUIRES_REVIEW'
    if label in {'United States', 'Australia', 'Brazil', 'India', 'Japan', 'New Zealand'}:
        return 'NON_EUROPE_SOURCE_LABEL_NOT_CONTROL_PROOF'
    return 'UNCLASSIFIED_SOURCE_LABEL'


def parse_review_document(body: bytes, source: dict) -> list[dict]:
    """Apply only explicitly reviewed layout selectors; preserve original raw capture."""
    layout = source.get('reviewed_layout')
    if layout is None:
        return parse_article(body, source)
    allowed = {
        'sanofi-flu-inauguration-20260916': ('title', '#ReleaseContent'),
        'avanade-halifax-20220628': ('h1.page-title', 'article.article--full .field--name-body'),
        'nature-farnham-plan-20220315': ('h1', 'article.news-release'),
        'roquette-rd-20200619': ('h1.page__heading', 'article.page__content'),
    }
    pair = (layout.get('title_selector'), layout.get('content_selector'))
    if pair != allowed.get(source['id']):
        raise ValueError('Unreviewed document layout')
    soup = BeautifulSoup(body, 'html.parser')
    headings, contents = soup.select(pair[0]), soup.select(pair[1])
    if len(headings) != 1 or len(contents) != 1 or not headings[0].get_text(strip=True):
        raise ValueError('Missing, duplicate or empty reviewed title/content region')
    # Copy source text/markup, not inferred content. Shared parser still enforces
    # date and evidence anchors. Captured bytes and their SHA-256 remain unchanged.
    scoped = BeautifulSoup('<h1></h1><main></main>', 'html.parser')
    scoped.h1.string = headings[0].get_text(' ', strip=True)
    region = contents[0].extract()
    if source['id'] in {'nature-farnham-plan-20220315', 'roquette-rd-20200619'}:
        # These retained pages put the publication date in the article's own header.
        # Keep that source text, not unrelated site headers or a fabricated date.
        for header in region.select('header'):
            header.name = 'div'
    scoped.main.append(region)
    return parse_article(str(scoped).encode('utf-8'), source)


def source_window(source: dict, record: dict) -> str:
    body = normalized(record['evidence_text'])
    if source.get('section_anchor'):
        start = normalized(source['section_anchor'])
        if body.count(start) != 1:
            raise ValueError('Missing or ambiguous dated subsection')
        body = body.split(start, 1)[1]
        end = normalized(source['section_end_anchor'])
        if end not in body:
            raise ValueError('Missing subsection end boundary')
        body = start + ' ' + body.split(end, 1)[0]
    return body


def qualify(discovery: list[dict], manifest: dict, evidence: dict[str, dict]) -> dict:
    """Only supplied, retained primary records can substantiate a reviewed claim."""
    if manifest.get('schema_version') != 1:
        raise ValueError('Unsupported review schema')
    source_rows = manifest['sources']
    if len({s['id'] for s in source_rows}) != len(source_rows):
        raise ValueError('Duplicate evidence source')
    sources = {s['id']: s for s in source_rows}
    index = {r['source_record_id']: r for r in discovery}
    if len(index) != len(discovery) or not discovery:
        raise ValueError('Empty or duplicate discovery collection')
    for row in discovery:
        if row.get('source_id') != 'investcanada-investment-cards-20260922':
            raise ValueError('Wrong discovery source namespace')
        if any(row.get(flag) is not False for flag in FORBIDDEN_FLAGS):
            raise ValueError('Discovery rows must retain their unqualified boundaries')
    used, project_keys, reviewed = set(), set(), {}
    for case in manifest['cases']:
        cid, rid, project = case.get('id'), case['discovery_record_id'], case.get('project_key')
        if not cid or cid in used or not project or project in project_keys or rid in reviewed:
            raise ValueError('Duplicate/missing case, project or discovery review')
        used.add(cid); project_keys.add(project)
        if rid not in index or not case.get('reviewer') or not case.get('interpretation'):
            raise ValueError('Unbound or unattributed review')
        if any(case.get(flag) is not False for flag in FORBIDDEN_FLAGS):
            raise ValueError('Documentary review cannot establish legal identity, entry, holdout or alerts')
        expected = case.get('expected_discovery', {})
        fields = {'company_candidate', 'source_country_as_published', 'location_text', 'investment_type_as_published'}
        if set(expected) != fields or any(index[rid].get(k) != v for k, v in expected.items()):
            raise ValueError('Discovery identity/project changed; review cannot be silently reused')
        refs = {}
        def checked(source_id: str, anchors: list[str]) -> dict:
            if source_id not in sources or source_id not in evidence:
                raise ValueError('Missing retained primary-source evidence: ' + source_id)
            s, r = sources[source_id], evidence[source_id]
            if r.get('source_id') != source_id or url(r['source_url']) != url(s['url']):
                raise ValueError('Evidence source/URL mismatch')
            if r.get('source_publication_date') != s['reviewed_publication_date']:
                raise ValueError('Source-publication clock mismatch')
            if not re.fullmatch(r'[a-f0-9]{64}', r.get('raw_sha256', '')):
                raise ValueError('Retained raw provenance required')
            observed = instant(r['last_observed_at'])
            if date.fromisoformat(r['source_publication_date']) > observed.date():
                raise ValueError('Future publication date')
            body = source_window(s, r)
            if not anchors or any(not a or normalized(a) not in body for a in anchors):
                raise ValueError('Reviewed event/identity anchor absent in source subsection')
            refs[source_id] = {k: r[k] for k in ('source_id', 'source_url', 'source_publication_date',
                'first_observed_at', 'last_observed_at', 'raw_sha256')}
            return r
        events = deepcopy(case.get('events', []))
        if not events:
            raise ValueError('Documentary review must contain supported events')
        event_keys = set()
        for event in events:
            kind, day = event.get('kind'), date.fromisoformat(event['date'])
            if kind not in KINDS or event.get('date_basis') != KINDS[kind]:
                raise ValueError('Event kind/date precision conflation')
            key = (kind, day, event['source_id'])
            if key in event_keys:
                raise ValueError('Duplicate event')
            event_keys.add(key)
            r = checked(event['source_id'], event['required_text'])
            if event['date'] != r['source_publication_date']:
                raise ValueError('This review batch only asserts source-day events or upper bounds')
            if 'operational_opening_date' in event or 'first_operation_date' in event:
                raise ValueError('No exact first-operation date is established by these event types')
            year = event.get('planned_operation_year')
            if year is not None and (kind != 'PROJECT_ANNOUNCED' or type(year) is not int or year < day.year):
                raise ValueError('Planned operation year cannot become an actual opening')
            event['first_operation_date'] = None
            event['historical_signal_eligible'] = False
        presence = case.get('prior_presence_evidence')
        if presence:
            checked(presence['source_id'], presence['required_text'])
        named = case.get('named_entity_evidence')
        if named:
            checked(named['source_id'], [named['name']])
        reviewed[rid] = dict(case, events=events, evidence=list(refs.values()),
            documentary_status='PRIMARY_DOCUMENTS_CHECKED_LEGAL_IDENTITY_PENDING',
            prior_presence_status='SOURCE_REPORTS_EXISTING_PRESENCE' if presence else 'NOT_ESTABLISHED',
            current_project_status='NOT_ESTABLISHED_BY_HISTORICAL_REVIEW',
            first_operation_date=None)
    records = []
    for original in discovery:
        row = deepcopy(original)
        row['source_origin_triage'] = origin_label_bucket(row['source_country_as_published'])
        row['documentary_review'] = reviewed.get(row['source_record_id'])
        row['documentary_status'] = 'REVIEWED' if row['documentary_review'] else 'UNREVIEWED'
        records.append(row)
    return {'schema_version': 1, 'status': 'DOCUMENTARY_REVIEW_NOT_PREDICTIVE_VALIDATION',
        'records': records, 'summary': {
            'discovery_records': len(records), 'documentary_reviewed_projects': len(reviewed),
            'unreviewed_projects': len(records) - len(reviewed),
            'primary_documents_used': len({r['source_id'] for c in reviewed.values() for r in c['evidence']}),
            'source_origin_triage': dict(sorted(Counter(r['source_origin_triage'] for r in records).items())),
            'event_kind_counts': dict(sorted(Counter(e['kind'] for c in reviewed.values() for e in c['events']).items())),
            'first_entry_training_labels': 0, 'independent_holdout_rows': 0,
            'expansion_score_publication_allowed': False, 'new_public_alerts': 0}}
