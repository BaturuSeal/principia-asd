# Reproducing a rule

The public repository contains the application, task contracts, train/dev data, test inputs and frozen historical result artifacts. Protected example targets and historical provider traces are deliberately excluded. Software rc4 binds the original rc2 data and leaderboard editions in `configs/edition-compatibility.json`.

From the extracted public-release root:

```bash
python3 VERIFY.py
python3 -m venv ~/.principia-asd-venv
~/.principia-asd-venv/bin/pip install '.[dev]'
~/.principia-asd-venv/bin/python -m pytest -q -p no:cacheprovider
~/.principia-asd-venv/bin/principia-asd companion --bundle-root .
```

Choose a scenario and a numerical control to reproduce development fitting without a provider call. For LLM methods, exact prompts, configuration hashes, receipts, fitted candidates and failed attempts are recorded in your private workspace. A new provider response is not deterministic replay of a historical response. Original source snapshots are required to resume old frozen jobs after a software change.

Every new UI run freezes its task, train/dev hashes, exact model roles, dated model profiles, capability receipts, resource envelope and runtime identity. Model edits affect future runs only. The gateway rejects ambiguous paid replay and mismatched cached request identities. Quantitative evaluation calls no model.

`principia-asd --help` lists catalog, audit, validate, run, resume, evaluate, replay, review, leaderboard, export, serve, companion and build-site commands. CLI run settings are private machine configuration; do not commit them. New shared-example test assessments remain pending without protected targets. User imports create grouped local partitions in their private workspace and leave the original source folder unchanged.

The existing leaderboards preserve 520 primary attempts and all failed/invalid outcomes. Source data and canonical numerical results are copied byte-for-byte. Read `docs/RELEASE_SCOPE.md` for unresolved preparation and complexity limits. Older dated receipts describe their original source snapshots; they do not certify the newer product code.

Public static builds read only public editions and do not access a local job workspace. The assembly script `scripts/build_public_release.py` separately selects protected target pairs by registered scenario ID. Never copy the entire private-workspace tree into a delivery. `BUNDLE_MANIFEST.json`, `SHA256SUMS`, the archive checksum and the deployment receipt document artifact integrity; they are not digital signatures or independent scientific review.
