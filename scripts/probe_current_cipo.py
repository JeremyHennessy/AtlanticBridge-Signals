from __future__ import annotations

import argparse
import json
from pathlib import Path

from atlanticbridge.current_cipo import RecordingSession, observe_current_owners


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='ui/data/dashboard.json')
    parser.add_argument('--output', default='artifacts/current-cipo')
    parser.add_argument('--detail-limit', type=int, default=10)
    args = parser.parse_args()
    output = Path(args.output)
    session = RecordingSession(output / 'raw')
    entities = json.loads(Path(args.input).read_text())['research_cohort']
    report = observe_current_owners(entities, session, detail_limit=args.detail_limit)
    report['raw_responses'] = session.responses
    (output / 'current-cipo-proof.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': report['status'], 'summary': report['summary']}, indent=2))
    return 1 if report['failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
