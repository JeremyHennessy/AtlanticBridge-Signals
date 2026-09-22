"""One-time, hash-pinned import of the accepted eight-source observation ledger."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import zipfile
from atlanticbridge.company_sources import Ledger
from atlanticbridge.monitoring_checkpoint import checkpoint, save

ACCEPTED_ARTIFACT = 10717489758
ACCEPTED_SHA256 = '003c42f02705066074a87bc5cac33ac0c72833d1c4a03bed3b01a1c5b660874a'

def bootstrap(archive: Path, state: Path) -> None:
    marker = json.loads((state / 'bootstrap.json').read_text())
    if marker != {'status': 'BOOTSTRAP_PENDING', 'artifact_id': ACCEPTED_ARTIFACT, 'sha256': ACCEPTED_SHA256}:
        raise ValueError('Bootstrap not explicitly authorized or already initialized')
    if (state / 'checkpoint.json').exists():
        raise ValueError('Existing checkpoint may not be replaced by a seed')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ACCEPTED_SHA256:
        raise ValueError('Accepted proof archive digest mismatch')
    with tempfile.TemporaryDirectory() as directory, zipfile.ZipFile(archive) as z:
        # Read exactly one known member; never execute source or extract archive paths.
        path = Path(directory) / 'seed.sqlite'
        path.write_bytes(z.read('observations.sqlite'))
        seed = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        ledger = Ledger(':memory:')
        try:
            if seed.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Seed database integrity failure')
            seed.backup(ledger.db)
            value = checkpoint(ledger)
            sources = json.loads(Path('reviews/company_sources/pilot-2026-09-22.json').read_text())['sources']
            if {s['id'] for s in sources} != {s['id'] for s in value['tables']['company_source_state']}:
                raise ValueError('Seed sources do not match the accepted manifest')
            if len(value['tables']['company_observations']) != 373 or value['tables']['company_observation_events']:
                raise ValueError('Unexpected accepted seed observations/events')
            save(state / 'checkpoint.json', value)
            (state / 'bootstrap.json').write_text(json.dumps(dict(marker, status='INITIALIZED'), indent=2) + '\n')
        finally:
            seed.close(); ledger.close()

if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive', type=Path, required=True)
    ap.add_argument('--state-dir', type=Path, required=True)
    args=ap.parse_args();bootstrap(args.archive,args.state_dir)
