# Campaign operation

Use `scripts/launch_campaign.py` with the workspace settings, a fresh campaign ID, method IDs, and optionally scenario IDs. It snapshots source outside the upload roots and launches one locked driver. The driver executes at most four numerical workers, freezes the complete assigned matrix, assesses without model calls, and exports per-scenario results.

```bash
python scripts/launch_campaign.py --settings /path/to/settings.json   --campaign-id new-comparison --methods direct_deepseek principia_engine
python scripts/status.py --workspace /path/to/workspace
```

Completed submissions are immutable. Resume uses the campaign's original snapshot. Completed provider requests are reusable only for the identical payload. Unknown or reserved requests without a reusable completed response are never automatically repeated. A changed method, source, prompt or limit requires a fresh identity.

The CNY 3,000 cap includes CNY 18 conservatively carried forward from the archived preview and all subsequent probes, interactive jobs and campaigns. SQLite serializes global and per-attempt reservations before dispatch. Actual usage is settled without assuming cache discounts; missing usage remains conservatively reserved. The hourly monitor reports spending and active jobs rather than assuming a phase-start timestamp means a stall.

Engineering revisions are disclosed. `controls-v2` was superseded after a code review identified missing free-parameter accounting for the fitted mean. The corrected whole matrix is `controls-v3`; no task or private target changed. All previous attempts remain in the historical export. The multi-model engineering pilot is a separate frozen cohort and must finish before authorizing a subsequent full comparison configuration.

The corrected 16-attempt interface pilot completed successfully. The primary matrix is `full-comparison-v5`: 40 scenarios times 13 executable configurations. Its source and settings are frozen separately. Final assessment and export occur only after all 520 submissions freeze; prior engineering cohorts remain in a separate history export when the primary table becomes available. Corrections used development logs and schema failures, never private test-loss feedback.

The primary campaign has finished: 483 complete and 37 failed attempts, with 693 rules. Exact frozen-runtime assessment replay passed for all 520 attempts. The subsequent `agent-laboratory-pilot-v1` and `guarded-adapters-pilot-v2` are separate engineering cohorts. The latter records eight complete Agent Laboratory v2 attempts and five complete plus three incomplete data-to-paper v1 attempts. All failed or incomplete attempts and program checks remain in history.

The guarded pilot's frozen driver separates its own completion counts from `canonical_export` counts. Earlier driver records remain unchanged; use each manifest and freeze map for its fixed denominator. Do not infer a pilot's size from an older driver's canonical-export summary.
