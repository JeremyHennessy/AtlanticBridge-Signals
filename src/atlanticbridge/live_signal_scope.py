"""Product-scope review for current awards; never changes source or backtest evidence."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from decimal import Decimal
import json
import re
import sqlite3
import unicodedata

from .constants import EU27
from .live_signals import _decimal


def _normal(value: object) -> str:
    text = unicodedata.normalize('NFKD', str(value or '')).casefold()
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', text).split())


_CANADIAN = {
    'canada', 'national capital region ncr', 'ontario', 'ontario except ncr',
    'quebec', 'quebec except ncr', 'nova scotia', 'new brunswick',
    'prince edward island', 'newfoundland and labrador', 'manitoba',
    'saskatchewan', 'alberta', 'british columbia', 'yukon', 'yukon territory',
    'northwest territories', 'nunavut', 'nunavut territory', 'montreal',
    'mont joli', 'longueuil', 'cambridge bay',
}
_FOREIGN = {_normal(c) for c in EU27} | {
    'south africa', 'new zealand', 'south america', 'mexico',
    'united states of america', 'united states', 'africa', 'caribbean',
    'asia', 'europe', 'central america', 'oceania', 'qatar',
    'united kingdom', 'norway', 'switzerland', 'iceland',
}
_MILITARY = re.compile(
    r'\b(?:department of national defen[cs]e|dnd|canadian armed forces|'
    r'royal canadian navy|royal canadian air force|armament|machine guns?|military)\b'
)


def classify_signal(signal: dict, raw: dict | None = None) -> dict:
    raw = raw or {}
    text = _normal(' '.join(str(signal.get(k) or '') for k in (
        'title', 'award_description', 'contracting_entity'
    )) + ' ' + str(raw.get('endUserEntitiesName-nomEntitesUtilisateurFinal-eng') or ''))
    match = _MILITARY.search(text)
    if match:
        return {'state': 'EXCLUDED_MILITARY', 'reason': 'Explicit military scope in notice',
                'matched_text': match.group(0)}
    if re.search(r'\bcbrn\b', text):
        return {'state': 'REVIEW_REQUIRED', 'reason': 'CBRN use requires civilian/military scope review'}
    regions = str(signal.get('regions_of_delivery') or '')
    tokens = [_normal(t) for t in re.split(r'\*|;|\|', regions) if _normal(t)]
    if any(t in _CANADIAN for t in tokens):
        return {'state': 'INCLUDED_CANADIAN_DELIVERY',
                'reason': 'At least one explicit Canadian delivery region in notice'}
    if tokens and all(t in _FOREIGN for t in tokens):
        return {'state': 'EXCLUDED_FOREIGN_DELIVERY',
                'reason': 'All stated delivery regions are outside Canada'}
    if any(t in _FOREIGN for t in tokens):
        return {'state': 'REVIEW_REQUIRED',
                'reason': 'Foreign delivery plus unresolved location; Canadian delivery not established'}
    return {'state': 'INCLUDED_BUYER_ONLY',
            'reason': 'Canadian buyer relationship only; delivery location remains unverified'}


def apply_commercial_scope(payload: dict, conn: sqlite3.Connection | None = None) -> dict:
    """Retain excluded/review rows in an audit ledger, not as negative signals."""
    result = deepcopy(payload)
    if result.get('status') != 'ACTIVE':
        return result
    included, excluded, review = [], [], []
    decisions = Counter()
    for original in result['signals']:
        signal = deepcopy(original)
        raw = {}
        if conn is not None:
            row = conn.execute('SELECT raw_json FROM canadabuys_awards WHERE record_id = ?',
                               (signal['record_id'],)).fetchone()
            if row is not None:
                raw = json.loads(row[0])
        decision = classify_signal(signal, raw)
        signal['scope_review'] = decision
        decisions[decision['state']] += 1
        if decision['state'].startswith('EXCLUDED_'):
            excluded.append(signal)
            continue
        if decision['state'] == 'REVIEW_REQUIRED':
            review.append(signal)
            continue
        company = signal['company_name']
        buyer = signal.get('contracting_entity') or 'the named Canadian federal buyer'
        location_note = (
            'The notice lists Canadian delivery; this does not establish a Canadian office or first entry.'
            if decision['state'] == 'INCLUDED_CANADIAN_DELIVERY' else
            'Delivery location is unverified. This establishes a buyer relationship, not operations in Canada.'
        )
        if decision['state'] == 'INCLUDED_BUYER_ONLY':
            signal['signal_stage'] = 'CANADIAN_BUYER_RELATIONSHIP_LOCATION_UNVERIFIED'
        signal['why_surfaced'] = (
            f'CanadaBuys names {company} as supplier to {buyer}. '
            f'Supplier address country: {signal["country"]}; ultimate control is not established by this field. '
            f'{location_note} No expansion probability or regional fit is inferred.'
        )
        included.append(signal)
    result['signals'] = included
    public_dates = [s['publicly_available_date'] for s in included]
    amount = sum((_decimal(s['contract_amount']) or Decimal('0')
                  for s in included if s.get('contract_currency') == 'CAD'), Decimal('0'))
    result['summary'].update({
        'signal_count': len(included), 'company_count': len({s['company_id'] for s in included}),
        'country_count': len({s['country'] for s in included}),
        'latest_public_date': max(public_dates) if public_dates else None,
        'earliest_public_date': min(public_dates) if public_dates else None,
        'cad_contract_amount': format(amount, 'f'),
    })
    result['scope_audit'] = {
        'schema_version': 1, 'input_signal_count': sum(decisions.values()),
        'included_signal_count': len(included), 'decision_counts': dict(sorted(decisions.items())),
        'excluded_signals': excluded, 'review_required_signals': review,
        'boundary': 'Product-scope exclusions are not negative expansion labels. Raw source evidence is unchanged.',
    }
    result['interpretation'] = (
        'Current non-military Canadian-buyer evidence after scope review. Foreign-only delivery is withheld; '
        'unknown delivery remains buyer-only evidence. Supplier address country is not ultimate control. '
        'No first-entry, prediction or market-fit inference.'
    )
    return result
