"""Independent bounded outcome-discovery proof using accepted capture and ledger code."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from atlanticbridge.company_sources import Ledger, parse_article, url
from atlanticbridge.investment_discovery import discovery_summary, parse_investment_cards, retained_review_records
from probe_company_sources import Capture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="reviews/company_sources/investment-discovery-2026-09-22.json")
    parser.add_argument("--output", default="artifacts/investment-discovery")
    parser.add_argument("--state", help="Existing dedicated company-source ledger; reuse to retain first observations")
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text())
    sources = manifest["sources"]
    if not sources or len(sources) > 10 or len({s["id"] for s in sources}) != len(sources):
        raise ValueError("Expected 1-10 distinct reviewed source paths")
    if any(s["kind"] not in {"investment_cards", "article"} for s in sources):
        raise ValueError("Only reviewed investment cards and calibration articles are accepted")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    capture = Capture(out / "raw", {urlsplit(url(s["url"])).hostname for s in sources})
    state = Path(args.state) if args.state else out / "observations.sqlite"
    state.parent.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(str(state))
    report = {"schema_version": 1, "scope": "OUTCOME_DISCOVERY_NOT_VERIFIED_FIRST_ENTRY",
              "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              "public_alert_allowed": False, "backtest_eligible": False,
              "sources": [], "observations": [], "events": [], "failures": []}
    queue = []
    try:
        for source in sources:
            try:
                # Accepted Capture checks robots before fetching the requested page.
                body, sha = capture.get(source["url"])
                rows = (parse_investment_cards if source["kind"] == "investment_cards" else parse_article)(body, source)
                observed = datetime.now(timezone.utc).isoformat()
                events = ledger.apply(source, rows, observed, sha)
                if ledger.apply(source, rows, observed, sha):
                    raise AssertionError("Identical replay generated new observations")
                result = {"id": source["id"], "records": len(rows), "observed_at": observed,
                          "raw_sha256": sha, "events": len(events), "replay_events": 0}
                if source["kind"] == "investment_cards":
                    result["discovery"] = discovery_summary(rows)
                    queue.extend(retained_review_records(ledger, rows))
                report["sources"].append(result)
                report["observations"].extend(rows)
                report["events"].extend(events)
                print(json.dumps(result, ensure_ascii=False), flush=True)
            except Exception as exc:
                failure = {"id": source["id"], "status": "UNVERIFIED_SOURCE_FAILURE",
                           "type": type(exc).__name__, "error": str(exc)}
                report["failures"].append(failure)
                print(json.dumps(failure), flush=True)
    finally:
        ledger.close()
        for response in capture.responses:
            if "sha256" in response:
                raw = capture.directory / (response["sha256"] + ".bin")
                if hashlib.sha256(raw.read_bytes()).hexdigest() != response["sha256"]:
                    raise AssertionError("Retained response does not match provenance hash")
        report["responses"] = capture.responses
        report["summary"] = {"requested_sources": len(sources), "successful_sources": len(report["sources"]),
                             "failures": len(report["failures"]), "observations": len(report["observations"]),
                             "discovery_candidates": len(queue), "events": len(report["events"]),
                             "verified_first_entry_labels": 0, "raw_responses_verified": sum("sha256" in r for r in capture.responses)}
        (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        (out / "outcome-review-queue.json").write_text(json.dumps({
            "status": "UNREVIEWED_DISCOVERY_CANDIDATES", "records": queue,
            "backtest_eligible": False, "independent_holdout": False}, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps(report["summary"]), flush=True)
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
