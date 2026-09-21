from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = (
    (
        ROOT / "reviews/backtests/2026-09-21-cipo-researcher-manifest.json",
        ROOT / "reviews/backtests/source_proofs/2026-09-21-cipo-researcher-evidence.json",
    ),
    (
        ROOT / "reviews/backtests/2026-09-21-canadabuys-historical-manifest.json",
        ROOT / "reviews/backtests/source_proofs/2026-09-21-canadabuys-evidence.json",
    ),
    (
        ROOT / "reviews/backtests/2026-09-21-ted-historical-manifest.json",
        ROOT / "reviews/backtests/source_proofs/2026-09-21-ted-evidence.json",
    ),
)


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_contract(manifest_path: Path, evidence_path: Path) -> dict[str, str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    accepted = manifest.get("accepted_evidence_artifact")
    if not isinstance(accepted, dict):
        raise ValueError(
            f"{manifest_path} lacks accepted_evidence_artifact"
        )

    configured_path = str(accepted.get("path") or "")
    expected_relative = evidence_path.relative_to(ROOT).as_posix()
    if configured_path != expected_relative:
        raise ValueError(
            f"{manifest_path}: artifact path mismatch "
            f"{configured_path!r} != {expected_relative!r}"
        )

    expected_sha = str(accepted.get("sha256") or "")
    if len(expected_sha) != 64:
        raise ValueError(
            f"{manifest_path}: accepted evidence SHA-256 is not pinned"
        )

    actual_sha = sha256_path(evidence_path)
    if actual_sha != expected_sha:
        raise ValueError(
            f"{manifest_path}: accepted evidence drifted "
            f"{actual_sha} != {expected_sha}"
        )

    return {
        "signal_family": str(manifest.get("signal_family") or ""),
        "manifest": manifest_path.relative_to(ROOT).as_posix(),
        "evidence": expected_relative,
        "sha256": actual_sha,
    }


def main() -> int:
    results = [
        validate_contract(manifest_path, evidence_path)
        for manifest_path, evidence_path in CONTRACTS
    ]
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
