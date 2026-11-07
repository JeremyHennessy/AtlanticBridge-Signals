# CanadaBuys observation-clock scope

`first_observed_at` and `last_observed_at` describe the history retained in the database supplied to the feed builder. They do not establish first-ever discovery across deployments. The public JSON declares `observation_history_scope: INPUT_DATABASE_ONLY` on each notice and on its source, with an explanatory source warning.

The current Pages workflow creates an empty temporary database for each refresh. Re-reading unchanged source bytes therefore gives its rows new database observation timestamps. A continuing database preserves the first observation and updates the last observation, as before. No timestamps are inferred from an earlier feed or rewritten by this clarification.

Evidence: Pages runs [42253354014](https://github.com/JeremyHennessy/AtlanticBridge-Signals/actions/runs/42253354014) and [42261953533](https://github.com/JeremyHennessy/AtlanticBridge-Signals/actions/runs/42261953533), both at `1408cb351872c19db6ed5b8febe58fa039e0b4d0`, published the same 46 retained notices and source SHA-256 `d5a1675b88d2d1b72a49b407e4ac7510ab3e51f4ba34aee8fa1025db562e189c`. Every row's first/last observation changed from `2026-11-06T16:32:48.654207+00:00` to `2026-11-06T17:28:39.874299+00:00`; all other row fields were identical.

Use the notice's `publicly_available_date` for publication/amendment recency. Keep `event_date` separate. A refresh, or a later database observation, is not evidence of a new award or changed company activity. The current UI already labels snapshot time as “Source checked” and bases recency on public dates.

This is an additive provenance clarification. It does not create persistence, backfill earlier observations, change source enrollment or schedules, alter source values, or affect inclusion, counts, amounts, identities or model eligibility.
