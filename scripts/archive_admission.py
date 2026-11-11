"""Pure admission policy used by the local, unpublished archive_durable adapter.

A store must implement authoritative load() -> (revision, document) and atomic
compare_and_swap(revision, document) -> durable_revision, with no force pushes,
retry, or merge-on-conflict. Returned revisions are verified by a second load.
This module alone does not protect the shipping workflow; the integrated candidate
has not been published or verified live.
"""
from copy import deepcopy
import re

SCHEMA = 1
REPOSITORY = 'JeremyHennessy/AtlanticBridge-Signals'
BUDGET = 48
WINDOW_SECONDS = 3600

class AdmissionError(ValueError):
    pass

def _deny():
    raise AdmissionError('Archive admission requires review; no request authorized') from None

def _validate(state, now):
    keys = {'schema', 'repository', 'status', 'updated_at', 'window_start', 'spent', 'owner'}
    if not isinstance(state, dict) or set(state) != keys:
        _deny()
    if type(state['schema']) is not int or state['schema'] != SCHEMA or state['repository'] != REPOSITORY:
        _deny()
    if type(now) is not int or now < 0:
        _deny()
    if any(type(state[k]) is not int for k in ('updated_at', 'window_start', 'spent')):
        _deny()
    if not 0 <= state['window_start'] <= state['updated_at'] <= now:
        _deny()
    if not 0 <= state['spent'] <= BUDGET:
        _deny()
    if state['status'] not in ('ready', 'reserved', 'review_hold', 'migration_pending'):
        _deny()
    if state['status'] == 'ready':
        if state['owner'] is not None:
            _deny()
    elif state['spent'] != BUDGET or not isinstance(state['owner'], str) or not re.fullmatch(r'[1-9][0-9]{0,19}-[1-9][0-9]{0,9}', state['owner']):
        _deny()

def propose_reservation(state, now, owner):
    """Pure proposal, NOT permission. Missing, malformed or unfinished state is held."""
    _validate(state, now)
    if state['status'] != 'ready' or not isinstance(owner, str) or not re.fullmatch(r'[1-9][0-9]{0,19}-[1-9][0-9]{0,9}', owner):
        _deny()
    result = deepcopy(state)
    if now - result['updated_at'] >= WINDOW_SECONDS:
        result['window_start'] = now
        result['spent'] = 0
    if result['spent'] + BUDGET > BUDGET:
        _deny()
    result.update(status='reserved', owner=owner, updated_at=now, spent=BUDGET)
    return result

def reserve(store, now, owner):
    """Reserve once and verify persistence; never perform any archive request.

    A future adapter must consume this receipt only in this same run/attempt,
    once, with its <= BUDGET client. It must not persist reusable admission tokens.
    """
    try:
        revision, state = store.load()
        if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}', revision):
            _deny()
        proposal = propose_reservation(state, now, owner)
        committed = store.compare_and_swap(revision, proposal)
        if not isinstance(committed, str) or not re.fullmatch(r'[0-9a-f]{40}', committed) or committed == revision:
            _deny()
        observed_revision, observed = store.load()
        _validate(observed, now)
        if observed_revision != committed or observed != proposal:
            _deny()
        return committed, deepcopy(proposal)
    except Exception:
        # Do not leak transport text, credentials, or attempt a retry.
        _deny()

def propose_completion(reservation, now, owner, *, verified):
    """Pure proposal. Never refund consumed budget or clear failure on a timer.

    Caller must CAS against the exact reservation commit. Only fully verified
    archive completion permits ready; any known failure writes review_hold.
    Cancellation/crash leaves reserved, which also blocks every future admission.
    """
    _validate(reservation, now)
    if reservation['status'] != 'reserved' or reservation['owner'] != owner or type(verified) is not bool:
        _deny()
    result = deepcopy(reservation)
    result.update(status='ready' if verified else 'review_hold', updated_at=now,
                  owner=None if verified else owner)
    return result
