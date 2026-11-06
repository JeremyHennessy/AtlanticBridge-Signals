"""Offline pinned-evidence planning only. Never downloads or changes evidence."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from archive_evidence import MAX_BYTES, PINS, inspect_zip, parse_json


def read_bounded(path, limit):
    with Path(path).open('rb') as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Input exceeds bounded size')
    return raw


def inventory_observations(value):
    """Accept explicit per-artifact observations, never infer from list omission."""
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value.get('schema_version') != 1:
        raise ValueError('Invalid inventory schema')
    rows = value.get('observations')
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('Invalid inventory observations')
    observations = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid inventory observation')
        aid = row.get('artifact_id')
        if type(aid) is not int or aid not in PINS or aid in observations:
            raise ValueError('Unknown or duplicate pinned artifact')
        status = row.get('http_status')
        if status is not None and (type(status) is not int or not 100 <= status <= 599):
            raise ValueError('Invalid inventory HTTP status')
        expired = row.get('expired')
        if expired is not None and type(expired) is not bool:
            raise ValueError('Invalid inventory expiry flag')
        observations[aid] = (status, expired)
    return observations


def plan(inventory=None, retained=None):
    """Verify supplied local ZIPs against immutable pins; inventory is historical only."""
    observations = inventory_observations(inventory) if inventory is not None else {}
    if retained is not None and not isinstance(retained, dict):
        raise ValueError('Retained inputs must be a dictionary')
    retained = {} if retained is None else retained
    if any(type(aid) is not int or aid not in PINS for aid in retained):
        raise ValueError('Unknown retained artifact')
    items = []
    for aid, expected in PINS.items():
        code, expired = observations.get(aid, (None, None))
        source = 'uncertain'
        if code == 200 and expired is True:
            source = 'observed_expired'
        elif code in (404, 410):
            # Auth, visibility, deletion and expiry cannot be distinguished here.
            source = 'observed_unavailable'
        elif code == 200:
            source = 'metadata_only_not_byte_verified'
        local = 'not_supplied'
        if aid in retained:
            try:
                raw = read_bounded(retained[aid], MAX_BYTES)
                archive, _ = inspect_zip(raw, expected)
                archive.close()
                local = 'verified_retained'
            except FileNotFoundError:
                local = 'missing_local_copy'
            except Exception:
                # No file names, response content, URLs or exception messages leave here.
                local = 'needs_manual_review'
        if local == 'verified_retained':
            status, action = local, 'preserve_verified_local_copy'
        elif local == 'needs_manual_review':
            status, action = local, 'review_local_copy_without_replacing_evidence'
        else:
            status = local if local == 'missing_local_copy' else source
            action = 'manual_review_before_any_backfill'
        items.append({'artifact_id': aid, 'expected_sha256': expected,
                      'status': status, 'source_observation': source,
                      'retained_local_copy': local, 'next_step': action})
    return {'schema_version': 1, 'mode': 'offline_plan_only',
            'current_remote_availability': 'not_checked',
            'counts': dict(sorted(Counter(item['status'] for item in items).items())),
            'items': items,
            'limitations': [
                'Inventory observations are historical inputs, not current availability proof.',
                'API errors and inventory omissions do not establish absence.',
                'Verified retained means supplied local bytes only; remote retention and privacy are not verified.',
                'No downloads, uploads, source requests, regeneration or backfill were performed.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', help='Local JSON inventory, optional')
    parser.add_argument('--retained', action='append', default=[], metavar='ARTIFACT_ID=LOCAL_ZIP')
    args = parser.parse_args(argv)
    try:
        retained = {}
        for value in args.retained:
            aid, path = value.split('=', 1)
            aid = int(aid)
            if aid in retained or not path:
                raise ValueError('Duplicate or empty retained input')
            retained[aid] = path
        inventory = (parse_json(read_bounded(args.inventory, 1024 * 1024), 'Local inventory')
                     if args.inventory else None)
        result = plan(inventory, retained)
    except Exception:
        print('Offline plan failed: invalid or unreadable supplied inputs. No backfill performed.', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
