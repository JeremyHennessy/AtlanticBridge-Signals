"""Bounded current-owner observations, not historical applicant or absence evidence."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import time

from .sources.cipo import CIPOSession


class RecordingSession(CIPOSession):
    def __init__(self, raw_directory: Path):
        super().__init__(timeout=25, attempts=2, backoff_seconds=1)
        self.raw_directory = raw_directory
        self.raw_directory.mkdir(parents=True, exist_ok=True)
        self.responses = []

    def _open(self, request):
        with super()._open(request) as response:
            body, headers = response.read(), response.headers
        digest = hashlib.sha256(body).hexdigest()
        (self.raw_directory / f'{digest}.bin').write_bytes(body)
        self.responses.append({'url': request.full_url, 'method': request.get_method(),
                               'sha256': digest, 'bytes': len(body)})
        replay = BytesIO(body)
        replay.headers = headers
        return replay


def observe_current_owners(entities: list[dict], session, *, detail_limit: int = 10,
                           observed_at: str | None = None, delay: float = 0.3) -> dict:
    if not 1 <= detail_limit <= 50 or not 0 <= delay <= 5:
        raise ValueError('Invalid bounded detail limit or request pacing')
    if len(entities) > 40:
        raise ValueError('Current proof is bounded to 40 reviewed identities')
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    report = {'schema_version': 1, 'observed_at': observed_at,
              'scope': 'CURRENT_OWNER_OBSERVATION_ONLY',
              'absence_inference_allowed': False, 'backtest_eligible': False,
              'publication_clock': 'UNVERIFIED_FOR_HISTORICAL_USE',
              'entities': [], 'observations': [], 'failures': []}
    for entity in entities:
        name = str(entity.get('foreign_legal_name') or '').strip()
        if not name or entity.get('identity_confidence') not in {'HIGH', 'MEDIUM'}:
            raise ValueError('Each input needs a reviewed foreign legal name and identity confidence')
        entry = {'entity_id': entity['id'], 'owner_query': name,
                 'coverage_state': 'UNKNOWN_FOR_ABSENCE', 'search_succeeded': False,
                 'details_checked': 0, 'exact_current_owner_matches': 0}
        report['entities'].append(entry)
        try:
            search = session.search_owner(name)
            entry.update(search_succeeded=True, num_found=search.num_found,
                         num_returned=search.num_returned, response_hash=search.response_hash,
                         request_payload_json=search.request_payload_json,
                         search_records=[asdict(record) for record in search.records],
                         details_truncated=search.num_found > detail_limit)
            for record in search.records[:detail_limit]:
                if delay:
                    time.sleep(delay)
                try:
                    detail = session.fetch_detail(record.record_id)
                    if (not detail.application_number.isdigit()
                            or detail.application_number != record.application_number):
                        raise ValueError('Detail application number does not match the search record')
                    entry['details_checked'] += 1
                    if detail.match_status(name) != 'EXACT_DETAIL_OWNER':
                        continue
                    entry['exact_current_owner_matches'] += 1
                    report['observations'].append({
                        'entity_id': entity['id'], 'owner_query': name,
                        'current_owner': detail.owner_name,
                        'identity_scope': 'EXACT_CURRENT_OWNER_NOT_HISTORICAL_APPLICANT',
                        'application_number': detail.application_number,
                        'mark_name': detail.mark_name, 'status': detail.cipo_status,
                        'filed_date': detail.filed_date or None,
                        'registered_date': detail.registered_date or None,
                        'observed_at': observed_at, 'publicly_available_date': None,
                        'source_url': detail.detail_url,
                        'detail_html_sha256': detail.detail_html_hash,
                        'source_facts_json': detail.facts_json,
                        'action_history': list(detail.action_history),
                        'interpretation': 'Current record observation, not a new filing alert, first Canadian entry or expansion prediction.',
                    })
                except Exception as exc:
                    report['failures'].append({'entity_id': entity['id'], 'record_id': record.record_id,
                                               'operation': 'detail', 'error_type': type(exc).__name__, 'error': str(exc)})
        except Exception as exc:
            report['failures'].append({'entity_id': entity['id'], 'operation': 'search',
                                       'error_type': type(exc).__name__, 'error': str(exc)})
        if delay:
            time.sleep(delay)
    report['summary'] = {
        'reviewed_entities': len(entities),
        'successful_searches': sum(e['search_succeeded'] for e in report['entities']),
        'exact_owner_observations': len(report['observations']),
        'detail_capped_entities': sum(e.get('details_truncated', False) for e in report['entities']),
        'failures': len(report['failures']),
    }
    report['status'] = 'PARTIAL' if report['failures'] else 'FETCHED_WITH_BOUNDED_DETAILS'
    return report
