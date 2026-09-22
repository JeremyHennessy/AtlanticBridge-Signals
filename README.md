# AtlanticBridge monitoring state

Dedicated operational-data branch. No application source or deployment workflows belong here. The scheduled company monitor may update only checkpoint.json, health.json, bootstrap.json and runs/.

Bootstrap is explicitly pinned to accepted eight-source proof artifact 10717489758. Original source-observation dates must survive initialization. Once initialized, a missing or corrupt checkpoint is an error, not permission to reset the baseline.

Durable files contain source-local record references, fingerprints, dates, review-only event metadata and run health. They do not contain company/job descriptions, article bodies, contact details, analyst notes or automatically approved leads. Raw responses remain in separately retained 90-day Actions artifacts. This branch is not a twelve-month raw-evidence archive and cannot authorize historical backtests or expansion scores.

No force-push or automatic history deletion is part of this workflow. Restore through an explicitly reviewed commit after verifying the relevant checkpoint checksum.
