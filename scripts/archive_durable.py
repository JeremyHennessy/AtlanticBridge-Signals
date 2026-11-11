"""Exact-head durable archive admission. Local candidate; never bootstraps state.

Only the fixed monitoring-state branch is writable. No retries, redirects, git
processes, credentials provisioning, force updates, or fallback storage.
"""
import base64
from copy import deepcopy
import json
import hashlib
import re
import threading
import time
import urllib.request
import archive_admission as gate

STATE = 'archive-admission.json'
BRANCH = 'monitoring-state'
ENDPOINT = 'https://api.github.com/graphql'
LIMIT = 4 * 1024 * 1024


def deny():
    raise gate.AdmissionError('Durable archive requires review; no retry authorized') from None


def oid(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{40}', value):
        deny()
    return value


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                deny()
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: deny())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        deny()


class GraphQL:
    """Fixed origin, bounded response, configured proxies, sanitized failures."""
    def __init__(self, token):
        if not token:
            deny()
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect())

    def __call__(self, query, variables):
        try:
            request = urllib.request.Request(ENDPOINT,
                data=encode({'query': query, 'variables': variables}).encode(),
                headers={'Authorization': 'Bearer ' + self.token,
                         'Content-Type': 'application/json',
                         'Cache-Control': 'no-cache',
                         'User-Agent': 'AtlanticBridge-durable-archive'}, method='POST')
            with self.opener.open(request, timeout=60) as response:
                if response.status != 200 or response.geturl() != ENDPOINT:
                    deny()
                raw = response.read(LIMIT + 1)
                if len(raw) > LIMIT:
                    deny()
                result = decode(raw)
            if not isinstance(result, dict) or result.get('errors') or not isinstance(result.get('data'), dict):
                deny()
            return result['data']
        except Exception:
            deny()


class Store:
    def __init__(self, transport):
        self.transport = transport

    def read(self, paths, *, at=None):
        """All blobs are resolved from the same branch-target Commit snapshot."""
        try:
            fields = ' '.join('f%d:file(path:%s){mode type object{... on Blob{text isTruncated}}}'
                              % (i, json.dumps(path)) for i, path in enumerate(paths))
            if at is not None:
                oid(at)
            query = '''query {repository(owner:"JeremyHennessy",name:"AtlanticBridge-Signals"){
                ref(qualifiedName:"refs/heads/monitoring-state"){
                target{... on Commit{oid %s}}}}}''' % fields
            if at is not None:
                query = query.replace('ref(qualifiedName:"refs/heads/monitoring-state"){\n                target{... on Commit{oid', 'object(expression:' + json.dumps(at) + '){... on Commit{oid')
                query = query[:-1]
            repository = self.transport(query, {})['repository']
            target = repository['object'] if at is not None else repository['ref']['target']
            revision = oid(target['oid'])
            if at is not None and revision != at:
                deny()
            files = {}
            for i, path in enumerate(paths):
                entry = target['f%d' % i]
                if entry is None:
                    files[path] = None
                else:
                    if entry.get('mode') != 33188 or entry.get('type') != 'blob':
                        deny()
                    blob = entry['object']
                    if blob.get('isTruncated') is not False or not isinstance(blob.get('text'), str):
                        deny()
                    files[path] = blob['text']
            return revision, files
        except Exception:
            deny()

    def commit(self, expected, files):
        """One mutation, exact expectedHeadOid; preserve every unmentioned path."""
        try:
            oid(expected)
            if not 1 <= len(files) <= 5 or sum(len(v.encode()) for v in files.values()) > LIMIT:
                deny()
            for path, raw in files.items():
                if not (path in {STATE, 'archive-health.json', 'archive-attempt.json', 'archive-migration.json'} or
                        re.fullmatch(r'archive-(?:runs|manifests)/[1-9][0-9]{0,19}-[1-9][0-9]{0,9}\.json', path)):
                    deny()
                if not isinstance(raw, str) or len(raw.encode()) > LIMIT:
                    deny()
            query = '''mutation($input:CreateCommitOnBranchInput!){
                createCommitOnBranch(input:$input){commit{oid}}}'''
            variables = {'input': {'branch': {'repositoryNameWithOwner': gate.REPOSITORY,
                                             'branchName': BRANCH},
                'expectedHeadOid': expected,
                'message': {'headline': 'Record durable archive transition'},
                'fileChanges': {'additions': [{'path': path,
                    'contents': base64.b64encode(raw.encode()).decode()}
                    for path, raw in files.items()]}}}
            revision = oid(self.transport(query, variables)['createCommitOnBranch']['commit']['oid'])
            if revision == expected:
                deny()
            observed, actual = self.read(list(files))
            if observed != revision or actual != files:
                deny()
            return revision
        except Exception:
            deny()


class ArchiveRun:
    """Process-local once-only execution; receipt is never serialized or restored.

    The durable run record prevents reusing even a completed owner after an hour.
    This API is an integration guard, not a sandbox against hostile callers.
    """
    def __init__(self, store, owner, clock=lambda: int(time.time()), *, migration_receipt=None):
        if not isinstance(owner, str) or not re.fullmatch(r'[1-9][0-9]{0,19}-[1-9][0-9]{0,9}', owner):
            deny()
        self.store, self.owner, self.clock = store, owner, clock
        self.migration_receipt = deepcopy(migration_receipt)
        self.used = False
        self.lock = threading.Lock()

    def execute(self, client_factory, archive):
        with self.lock:
            if self.used:
                deny()
            self.used = True
        record = 'archive-runs/' + self.owner + '.json'
        manifest = 'archive-manifests/' + self.owner + '.json'
        try:
            revision, files = self.store.read([STATE, record, manifest, 'archive-attempt.json'])
            if files[record] is not None or files[manifest] is not None:
                deny()
            state = decode(files[STATE])
            gate._validate(state, self.clock())
            prior = files['archive-attempt.json']
            if state['status'] == 'migration_pending':
                from archive_migration import admit
                state = admit(self.store, revision, files[STATE], self.owner,
                              self.migration_receipt, self.clock())
                prior = None
            elif self.migration_receipt is not None:
                deny()
            if state['spent'] > 0 and prior is None:
                deny()
            if prior is not None:
                previous = decode(prior)
                if not isinstance(previous, dict) or previous.get('status') != 'ready':
                    deny()
                self._verify_previous(revision, files[STATE], prior, previous)
            reservation = gate.propose_reservation(state, self.clock(), self.owner)
            reserved = self.store.commit(revision, {STATE: encode(reservation),
                record: encode({'owner': self.owner, 'status': 'reserved'})})
        except Exception:
            deny()
        # Neither factory nor archive can run until exact durable readback succeeded.
        client = None
        try:
            client = client_factory()
            result = archive(client)
            if not isinstance(result, dict) or result.get('status') != 'VERIFIED_DRAFT_COPY':
                deny()
        except Exception as error:
            # Failure preserves last-good health/manifests. If this write fails,
            # reserved remains a hold. No retry, even for an uncertain write.
            self._finish(reserved, reservation, record, manifest, None, error)
            deny()
        # BaseException/cancellation deliberately leaves reserved, never ready.
        self._finish(reserved, reservation, record, manifest, result)
        return deepcopy(result)

    def _verify_previous(self, revision, raw_state, raw_attempt, previous):
        """A different run can admit only a complete committed success bundle.

        This handles lost final acknowledgment without retrying that mutation.
        A lone ready latch, legacy success, or partial final bundle is insufficient.
        """
        if set(previous) != {'owner', 'status', 'reservation_revision', 'state_sha256', 'manifest_sha256'}:
            deny()
        owner = previous.get('owner')
        if not isinstance(owner, str) or not re.fullmatch(r'[1-9][0-9]{0,19}-[1-9][0-9]{0,9}', owner):
            deny()
        oid(previous.get('reservation_revision'))
        record = 'archive-runs/' + owner + '.json'
        manifest = 'archive-manifests/' + owner + '.json'
        observed, files = self.store.read([STATE, 'archive-attempt.json', record,
                                           manifest, 'archive-health.json'])
        if (observed != revision or files[STATE] != raw_state or
                files['archive-attempt.json'] != raw_attempt or files[record] != raw_attempt or
                files[manifest] is None or files[manifest] != files['archive-health.json']):
            deny()
        digest = lambda raw: hashlib.sha256(raw.encode()).hexdigest()
        if (previous.get('state_sha256') != digest(raw_state) or
                previous.get('manifest_sha256') != digest(files[manifest])):
            deny()
        result = decode(files[manifest])
        if not isinstance(result, dict) or result.get('status') != 'VERIFIED_DRAFT_COPY':
            deny()

    def _finish(self, revision, reservation, record, manifest, result, error=None):
        try:
            state = gate.propose_completion(reservation, self.clock(), self.owner,
                                           verified=result is not None)
            attempt = {'owner': self.owner, 'status': state['status'],
                       'reservation_revision': revision,
                       'state_sha256': hashlib.sha256(encode(state).encode()).hexdigest()}
            if result is not None:
                attempt['manifest_sha256'] = hashlib.sha256(encode(result).encode()).hexdigest()
            if error is not None:
                attempt['error_type'] = type(error).__name__
                # Use only the verifier's own fixed-key, sanitized diagnostic.
                from archive_evidence import PrivacyCheckError
                if isinstance(error, PrivacyCheckError):
                    attempt['privacy_check'] = deepcopy(error.diagnostic)
            files = {STATE: encode(state), record: encode(attempt),
                     'archive-attempt.json': encode(attempt)}
            if result is not None:
                files.update({'archive-health.json': encode(result), manifest: encode(result)})
            self.store.commit(revision, files)
        except Exception:
            deny()
