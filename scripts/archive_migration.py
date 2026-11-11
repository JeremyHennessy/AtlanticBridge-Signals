"""Explicit operator-reviewed historical migration. Never runs archive work.

Approval/receipt files are trusted operator inputs, NOT an authentication service.
No shipped workflow invokes this tool. No migration is approved by this code.
"""
from copy import deepcopy
import argparse
import hashlib
import os
from pathlib import Path
import re
import time
import archive_durable as d

CERT = 'archive-migration.json'
CORE = [d.STATE, 'archive-attempt.json', 'archive-health.json']
SCOPE = 'permit-one-first-archive-run-not-privacy-proof'
OWNER = r'[1-9][0-9]{0,19}-[1-9][0-9]{0,9}'


def digest(value):
    return hashlib.sha256(d.encode(value).encode()).hexdigest()


def load_json(path, limit):
    """Bound trusted local inputs before JSON decoding; never log their bytes."""
    try:
        with open(path, 'rb') as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            d.deny()
        return d.decode(raw)
    except Exception:
        d.deny()


def concise(value):
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= 512
            and not any(ord(char) < 32 for char in value))


def check_path(path):
    if (not isinstance(path, str) or len(path) > 240 or
            not re.fullmatch(r'[A-Za-z0-9_./-]+', path) or
            any(part in ('', '.', '..') for part in path.split('/')) or path == CERT):
        d.deny()


def validate_plan(plan):
    if (not isinstance(plan, dict) or set(plan) !=
            {'schema', 'repository', 'expected_head', 'evidence', 'evidence_sha256'} or
            plan['schema'] != 'historical-migration-plan-v1' or
            plan['repository'] != d.gate.REPOSITORY):
        d.deny()
    d.oid(plan['expected_head'])
    evidence = plan['evidence']
    if not isinstance(evidence, dict) or not set(CORE) <= set(evidence) or len(evidence) > 32:
        d.deny()
    for path, raw in evidence.items():
        check_path(path)
        if raw is not None and not isinstance(raw, str):
            d.deny()
    if plan['evidence_sha256'] != digest(evidence) or len(d.encode(plan).encode()) > d.LIMIT // 2:
        d.deny()


def plan(store, expected_head, pins=()):
    """Read-only proposal. Pins name additional provenance blobs at exact head.

    The entire original tree remains reachable through expected_head, including
    all history not embedded here. Nulls preserve authoritative nonexistence.
    """
    d.oid(expected_head)
    paths = list(dict.fromkeys(CORE + list(pins)))
    for path in paths:
        check_path(path)
    revision, files = store.read(paths + [CERT])
    if revision != expected_head or files.pop(CERT) is not None:
        d.deny()
    result = {'schema': 'historical-migration-plan-v1', 'repository': d.gate.REPOSITORY,
              'expected_head': revision, 'evidence': files, 'evidence_sha256': digest(files)}
    validate_plan(result)
    return result


def validate_decisions(proposal, resolution, approval, now):
    """Validate bindings and explicit assertions; authenticity is operator-owned."""
    validate_plan(proposal)
    if type(now) is not int or now < 0:
        d.deny()
    if (not isinstance(resolution, dict) or set(resolution) != {
            'schema', 'repository', 'expected_head', 'evidence_sha256',
            'restriction_resolved', 'stale_jobs_drained', 'reviewer', 'evidence_reference',
            'resolved_at', 'drained_at'} or resolution['schema'] != 'restriction-resolution-v1' or
            resolution['repository'] != d.gate.REPOSITORY or
            resolution['expected_head'] != proposal['expected_head'] or
            resolution['evidence_sha256'] != proposal['evidence_sha256'] or
            resolution['restriction_resolved'] is not True or
            resolution['stale_jobs_drained'] is not True):
        d.deny()
    for key in ('reviewer', 'evidence_reference'):
        if not concise(resolution[key]):
            d.deny()
    if (not isinstance(approval, dict) or set(approval) != {
            'schema', 'repository', 'expected_head', 'plan_sha256', 'resolution_sha256',
            'scope', 'first_owner', 'approved_by', 'authorization_reference',
            'issued_at', 'expires_at'} or approval['schema'] != 'migration-approval-v1' or
            approval['repository'] != d.gate.REPOSITORY or
            approval['expected_head'] != proposal['expected_head'] or
            approval['plan_sha256'] != digest(proposal) or
            approval['resolution_sha256'] != digest(resolution) or approval['scope'] != SCOPE or
            not isinstance(approval['first_owner'], str) or
            not re.fullmatch(OWNER, approval['first_owner'])):
        d.deny()
    for key in ('approved_by', 'authorization_reference'):
        if not concise(approval[key]):
            d.deny()
    if (any(type(x) is not int for x in (resolution['drained_at'], resolution['resolved_at'], approval['issued_at'], approval['expires_at'])) or
            not 0 <= resolution['drained_at'] <= resolution['resolved_at'] <= approval['issued_at'] <= now < approval['expires_at'] or
            now - resolution['drained_at'] < d.gate.WINDOW_SECONDS or
            approval['expires_at'] - approval['issued_at'] > 3600):
        d.deny()


def pending(approval, now):
    return dict(schema=1, repository=d.gate.REPOSITORY, status='migration_pending',
                updated_at=now, window_start=now, spent=d.gate.BUDGET, owner=approval['first_owner'])


def apply(store, proposal, resolution, approval, now):
    """Single CAS, no retries. Only successful exact readback returns a receipt.

    The certificate itself cannot admit a run. Failure/crash before receipt
    delivery is an unresolved hold, with no recovery/reset command.
    """
    try:
        proposal, resolution, approval = deepcopy((proposal, resolution, approval))
        validate_decisions(proposal, resolution, approval, now)
        owner = approval['first_owner']
        state = pending(approval, now)
        cert = dict(schema='historical-migration-certificate-v1', plan=proposal,
                    resolution=resolution, approval=approval, pending_state=state)
        if len(d.encode(cert).encode()) + len(d.encode(state).encode()) > d.LIMIT:
            d.deny()
        record, manifest = 'archive-runs/' + owner + '.json', 'archive-manifests/' + owner + '.json'
        paths = list(proposal['evidence']) + [CERT, record, manifest]
        revision, files = store.read(paths)
        if (revision != proposal['expected_head'] or
                any(files[p] is not None for p in (CERT, record, manifest)) or
                {p: files[p] for p in proposal['evidence']} != proposal['evidence']):
            d.deny()
        committed = store.commit(revision, {d.STATE: d.encode(state), CERT: d.encode(cert)})
        return dict(schema='migration-first-run-receipt-v1', repository=d.gate.REPOSITORY,
                    migration_revision=committed, certificate_sha256=digest(cert),
                    first_owner=owner)
    except Exception:
        d.deny()


def admit(store, revision, raw_state, owner, receipt, now):
    """Trusted receipt + exact authoritative bundle, never legacy success."""
    try:
        if (not isinstance(receipt, dict) or set(receipt) != {
                'schema', 'repository', 'migration_revision', 'certificate_sha256', 'first_owner'} or
                receipt['schema'] != 'migration-first-run-receipt-v1' or
                receipt['repository'] != d.gate.REPOSITORY or receipt['first_owner'] != owner or
                receipt['migration_revision'] != revision):
            d.deny()
        observed, files = store.read([d.STATE, CERT])
        cert = d.decode(files[CERT])
        if (observed != revision or files[d.STATE] != raw_state or
                not isinstance(cert, dict) or set(cert) != {
                'schema', 'plan', 'resolution', 'approval', 'pending_state'} or
                cert['schema'] != 'historical-migration-certificate-v1' or
                digest(cert) != receipt['certificate_sha256']):
            d.deny()
        proposal, resolution, approval = cert['plan'], cert['resolution'], cert['approval']
        validate_decisions(proposal, resolution, approval, now)
        state = d.decode(raw_state)
        if (approval['first_owner'] != owner or state != cert['pending_state'] or
                state != pending(approval, state['updated_at']) or
                not approval['issued_at'] <= state['updated_at'] <= now):
            d.deny()
        # Independently resolve originals from immutable commit, never mutable HEAD.
        _, original = store.read(list(proposal['evidence']), at=proposal['expected_head'])
        if original != proposal['evidence']:
            d.deny()
        paths = [p for p in proposal['evidence'] if p != d.STATE]
        observed, current = store.read(paths)
        if observed != revision or current != {p: proposal['evidence'][p] for p in paths}:
            d.deny()
        # Ephemeral proposal only. No durable ready state and no old success claim.
        return dict(schema=1, repository=d.gate.REPOSITORY, status='ready',
                    updated_at=now, window_start=now, spent=0, owner=None)
    except Exception:
        d.deny()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('plan')
    p.add_argument('--expected-head', required=True)
    p.add_argument('--pin', action='append', default=[])
    p.add_argument('--output', required=True)
    p = sub.add_parser('apply')
    for name in ('plan', 'resolution', 'approval', 'output'):
        p.add_argument('--' + name, required=True)
    args = parser.parse_args()
    # Create fresh exclusive output BEFORE any remote mutation. Never overwrite.
    out = Path(args.output).absolute()
    if any(p.is_symlink() for p in out.parents):
        d.deny()
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        store = d.Store(d.GraphQL(os.environ.get('GH_TOKEN', '')))
        if args.command == 'plan':
            result = plan(store, args.expected_head, args.pin)
        else:
            result = apply(store, load_json(args.plan, d.LIMIT // 2),
                           load_json(args.resolution, 8192),
                           load_json(args.approval, 8192), int(time.time()))
        with os.fdopen(fd, 'w') as stream:
            fd = None
            stream.write(d.encode(result))
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if fd is not None:
            os.close(fd)


if __name__ == '__main__':
    main()
