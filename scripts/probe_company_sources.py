"""Bounded public-source proof; writes no production feed, UI, score, or historical labels."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from atlanticbridge.company_sources import (Ledger, discover_ats, parse_article,
    parse_ashby, parse_feed, parse_greenhouse, parse_index, url)

UA = "AtlanticBridgeSignalsSourceProof/1.0 (+https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
LIMIT = 16 * 1024 * 1024


def accept_header_for(target):
    # robots.txt is a text/plain resource; do not negotiate it as a JSON/HTML API.
    # Status errors and robots disallows still fail through the existing policy.
    return ("text/plain, */*;q=0.1" if urlsplit(target).path == "/robots.txt"
            else "application/json, text/html, application/xml;q=0.9")


def unavailable_robots_allowed(status, target):
    # RFC 9309 section 2.3.1.3 distinguishes unavailable robots from protected
    # content. Restrict the observed 401/403 case to Ashby's documented PUBLIC
    # postings endpoint; a 401/403 from the endpoint itself still raises.
    p = urlsplit(target)
    documented_public_api = p.hostname == "api.ashbyhq.com" and p.path.startswith("/posting-api/job-board/")
    return status in (404, 410) or (status in (401, 403) and documented_public_api)


class SafeRedirect(HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = url(newurl)
        if urlsplit(target).hostname not in self.hosts:
            raise ValueError("Redirect outside reviewed host allowlist")
        return super().redirect_request(req, fp, code, msg, headers, target)


class Capture:
    def __init__(self, directory, hosts):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.hosts = hosts
        self.opener = build_opener(SafeRedirect(hosts))
        self.responses = []
        self.robots = {}

    def raw(self, target):
        target = url(target)
        if urlsplit(target).hostname not in self.hosts:
            raise ValueError("Unreviewed network host")
        time.sleep(0.6)
        error = None
        try:
            response = self.opener.open(Request(target, headers={"User-Agent": UA, "Accept": accept_header_for(target)}), timeout=25)
        except HTTPError as exc:
            response, error = exc, exc
        with response:
            body = response.read(LIMIT + 1)
            if len(body) > LIMIT:
                raise ValueError("Response exceeds download bound")
            sha = hashlib.sha256(body).hexdigest()
            (self.directory / (sha + ".bin")).write_bytes(body)
            self.responses.append({"url": target, "final_url": response.url,
                                   "status": response.status, "sha256": sha, "bytes": len(body),
                                   "retrieved_at": datetime.now(timezone.utc).isoformat(),
                                   "content_type": response.headers.get("Content-Type")})
        if error:
            raise error
        return body, sha

    def get(self, target):
        p = urlsplit(url(target))
        origin = f"https://{p.netloc}"
        if origin not in self.robots:
            policy = RobotFileParser()
            try:
                body, _ = self.raw(origin + "/robots.txt")
                policy.parse(body.decode("utf-8", errors="replace").splitlines())
            except HTTPError as exc:
                if not unavailable_robots_allowed(exc.code, target):
                    raise
                policy.parse(["User-agent: *", "Disallow:"])
                self.responses.append({"url": origin + "/robots.txt", "status": exc.code,
                                       "policy": "UNAVAILABLE_ROBOTS_RFC9309_2_3_1_3_NOT_CONTENT_AUTHORIZATION"})
            self.robots[origin] = policy
        policy = self.robots[origin]
        if not policy.can_fetch(UA, target):
            raise ValueError("robots.txt disallows this source path")
        delay = policy.crawl_delay(UA) or 0
        if delay > 30:
            raise ValueError("Source crawl delay exceeds bounded proof budget")
        if delay:
            time.sleep(delay)
        return self.raw(target)


def collect(source, capture):
    body, sha = capture.get(source["url"])
    if source["kind"] == "careers":
        candidates = discover_ats(body, source["url"])
        if len(candidates) != 1:
            raise ValueError(f"Official careers page needs exactly one supported ATS binding; found {candidates}")
        family, token = candidates[0]
        endpoint = (f"https://api.ashbyhq.com/posting-api/job-board/{quote(token, safe='')}" if family == "ashby"
                    else f"https://boards-api.greenhouse.io/v1/boards/{quote(token, safe='')}/jobs?content=true")
        data, sha = capture.get(endpoint)
        rows = (parse_ashby if family == "ashby" else parse_greenhouse)(json.loads(data), source)
        return rows, sha, {"adapter": family, "official_binding_sha256": hashlib.sha256(body).hexdigest(),
                           "endpoint": endpoint, "coverage": "CURRENT_PUBLISHED_BOARD_NOT_COMPANY_WIDE_ABSENCE"}
    parser = {"index": parse_index, "article": parse_article, "feed": parse_feed}[source["kind"]]
    return parser(body, source), sha, {"adapter": source["kind"], "coverage": "BOUNDED_PAGE_OR_FEED_WINDOW_NOT_ABSENCE_PROOF"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default="reviews/company_sources/pilot-2026-09-22.json")
    ap.add_argument("--output", default="artifacts/company-sources")
    ap.add_argument("--state", help="Optional existing SQLite ledger; preserve this path between live collections")
    args = ap.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    sources = manifest["sources"]
    if not 1 <= len(sources) <= 20 or len({s["id"] for s in sources}) != len(sources):
        raise ValueError("Source manifest must contain 1-20 unique reviewed paths")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    hosts = {urlsplit(url(s["url"])).hostname for s in sources}
    hosts.update({"api.ashbyhq.com", "boards-api.greenhouse.io"})
    capture = Capture(out / "raw", hosts)
    state = Path(args.state) if args.state else out / "observations.sqlite"
    ledger = Ledger(str(state))
    report = {"schema_version": 1, "scope": "SOURCE_FEASIBILITY_AND_OBSERVATIONS_ONLY",
              "manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
              "public_alert_allowed": False, "backtest_eligible": False,
              "sources": [], "observations": [], "events": [], "failures": []}
    try:
        for source in sources:
            try:
                rows, sha, coverage = collect(source, capture)
                observed = datetime.now(timezone.utc).isoformat()
                events = ledger.apply(source, rows, observed, sha)
                replay = ledger.apply(source, rows, observed, sha)
                if replay:
                    raise AssertionError("Non-idempotent source replay")
                report["observations"].extend(rows)
                report["events"].extend(events)
                result = {"id": source["id"], "status": "OBSERVED", "records": len(rows),
                          "canada_candidates": sum(r["canada_relevance"] == "CANDIDATE_REQUIRES_REVIEW" and not r["scope_exclusion"] for r in rows),
                          "new_observation_events": len(events), "replay_events": len(replay), **coverage}
                report["sources"].append(result)
                print(json.dumps(result, ensure_ascii=False), flush=True)
                for row in rows:
                    if row["canada_relevance"] == "CANDIDATE_REQUIRES_REVIEW" and not row["scope_exclusion"]:
                        print(json.dumps({"candidate": row["title"][:220], "url": row["source_url"],
                                          "source_id": source["id"], "clock": row["publication_clock"]}, ensure_ascii=False), flush=True)
            except Exception as exc:
                failure = {"id": source["id"], "status": "UNVERIFIED_SOURCE_FAILURE", "type": type(exc).__name__, "error": str(exc), "failed_url": getattr(exc, "url", None)}
                report["failures"].append(failure)
                report["sources"].append(failure)
                print(json.dumps(failure, ensure_ascii=False), flush=True)
    finally:
        ledger.close()
        for response in capture.responses:
            if "sha256" in response:
                actual = hashlib.sha256((capture.directory / (response["sha256"] + ".bin")).read_bytes()).hexdigest()
                if actual != response["sha256"]:
                    raise AssertionError("Raw provenance hash mismatch")
        report["responses"] = capture.responses
        report["summary"] = {"sources_requested": len(sources), "sources_observed": len(sources) - len(report["failures"]),
                             "source_failures": len(report["failures"]), "observations": len(report["observations"]),
                             "events": len(report["events"]), "raw_responses_verified": sum("sha256" in r for r in capture.responses)}
        (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
