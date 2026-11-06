"""Local-only CLI. Running a tick does not establish a background schedule."""
import argparse
import json
from pathlib import Path
from .models import SourceContract
from .scheduler import OfflineScheduler, utc_now
from .store import Store, verify_database


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    register = sub.add_parser("register", help="Pin a local source contract; starts paused")
    register.add_argument("--contract", required=True, type=Path)
    register.add_argument("--input", required=True, type=Path)
    for command in ("resume-local", "pause"):
        state = sub.add_parser(command)
        state.add_argument("--source", required=True)
        state.add_argument("--actor", required=True)
        state.add_argument("--review-reason")
    tick = sub.add_parser("tick-local", help="One bounded local-file pass; never a live collector")
    tick.add_argument("--max-jobs", type=int, default=100)
    sub.add_parser("health")
    sub.add_parser("work-items")
    save = sub.add_parser("save-work-item")
    save.add_argument("--item", required=True)
    save.add_argument("--revision", required=True, type=int)
    save.add_argument("--status", choices=("TRIAGE", "ACTIVE", "HOLD", "DONE"), required=True)
    save.add_argument("--notes-file", required=True, type=Path)
    save.add_argument("--due-date")
    save.add_argument("--needs-review", action="store_true")
    save.add_argument("--actor", required=True)
    backup = sub.add_parser("backup")
    backup.add_argument("--output", required=True, type=Path)
    sub.add_parser("verify", help="Read-only verification of --db")
    args = parser.parse_args(argv)
    exit_code = 0
    if args.command == "verify":
        result = verify_database(args.db)
    else:
        with Store(args.db) as store:
            if args.command == "init":
                result = {"mode": "LOCAL_ONLY_NO_DELIVERY", "initialized": True}
            elif args.command == "register":
                with args.contract.open("rb") as handle:
                    body = handle.read(65537)
                if len(body) > 65536:
                    raise ValueError("Contract file too large")
                contract = SourceContract.from_dict(json.loads(body))
                created = store.register(contract, at=utc_now(), input_path=args.input)
                state = store.db.execute("SELECT state FROM sources WHERE source_id=?", (contract.source_id,)).fetchone()[0]
                result = {"created": created, "state": state}
            elif args.command in {"resume-local", "pause"}:
                state = store.set_source_state(args.source, "READY" if args.command == "resume-local" else "PAUSED",
                                               at=utc_now(), actor=args.actor, review_reason=args.review_reason)
                result = {"source_id": args.source, "state": state, "local_only": True}
            elif args.command == "tick-local":
                result = OfflineScheduler(store).run_due(max_jobs=args.max_jobs)
                if any(item["status"] in {"FAILED", "LEASE_LOST"} for item in result):
                    exit_code = 1
            elif args.command == "health":
                result = store.health(at=utc_now())
            elif args.command == "work-items":
                result = store.work_items()
            elif args.command == "save-work-item":
                with args.notes_file.open(encoding="utf-8") as handle:
                    notes = handle.read(16001)
                result = {"revision": store.update_work_item(args.item, expected_revision=args.revision, status=args.status,
                          notes=notes, due_date=args.due_date, needs_review=args.needs_review, at=utc_now(), actor=args.actor)}
            elif args.command == "backup":
                result = store.backup(args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
