# Public library and private local discovery

The cloud service is a static, read-only library. All personal discovery happens on the visitor's computer using the Python local companion. The browser never sends folder contents, API keys or generated results to the public host. Only selected development context is sent from the companion directly to SiliconFlow when the visitor starts an LLM method. Provider-side handling is governed by the visitor's provider account and terms.

## Local installation

Run the README's three commands from the repository root or `public-release`. The folder contains the installable package plus `data/`, `leaderboards/`, and versioned `collections/` registered by `COLLECTIONS.json`. Every relative collection path and edition hash is checked. The companion registers bundled tasks automatically; no operator evaluator path is inherited. A legacy three-folder distribution is also supported. macOS and Linux support ordinary numerical-expression methods. Development workers that execute generated code require the tested macOS sandbox and will explicitly refuse unsupported platforms; no unsandboxed fallback is supplied. Windows users need a supported local Linux environment.

Use API settings to add, edit or remove model profiles. The identifier must match SiliconFlow exactly. The catalog button lists account-visible identifiers; it does not infer pricing or claim chat/JSON capability. Enter dated conservative prices, choose generation options, then explicitly probe the selected profiles. Profiles and capability receipts freeze with a new run. Edits invalidate the affected probe; active or unresolved runs prevent settings changes. Ambiguous billed requests never automatically replay. Reasoning-budget enforcement varies by model; a successful small probe is not a universal bound guarantee.

The default workspace is `~/.local/share/principia-asd`. Keys are owner-readable files; jobs, imported data, split targets, receipts and results are stored under that private directory. Use separate OS accounts for different people sharing a computer, or separate `--workspace` and `--port` values for distinct workspaces. Two application instances cannot own the same workspace. The companion listens only on loopback and checks Host, Origin and CSRF tokens. Do not reverse-proxy it onto a public network.

## Cloud layout

```text
/data/pzq/Principia-ASD/
  repository/                   # Git history of public source/artifacts only
  releases/<release-id>/
    public-release/             # Detached Git worktree at the recorded release commit
    public-site/                # The only nginx document root
    private-evaluator/          # Owner-only, never served
    DEPLOYMENT_AUTHORIZATION.json
  current -> releases/<release-id>
  shared/operator-venv/          # Server-created environment; no copied runtime
  backups/                      # Nginx rollback copies
```

The route `/web/asd-test/` serves `current/public-site/`. The build supports a fixed URL prefix; assets, lazy task records and the companion ZIP share it. Nginx allows GET/HEAD only and denies API and dotfile routes. The public download is constructed from `public-release` only, with a manifest and payload hashes. Protected targets are a sibling directory with mode 0700, files 0600; nginx cannot read them. The administrative evaluator is available over SSH, not as a web API.

No user computation is scheduled on the server. Visitors cannot collide with another visitor's jobs, modify the common result store, or consume an operator's provider key. No cloud key is installed. Administrator evaluation outputs must be written to a separate private directory; publishing new shared results requires a deliberate new immutable edition.

## Build and verify

```bash
principia-asd build-site --data-root data --leaderboard-root leaderboards \
  --collections COLLECTIONS.json \
  --output ../public-site --base-path /web/asd-test/ \
  --companion-bundle ../principia-asd-public-release.zip --preview
python3 VERIFY.py
```

`--preview` retains the frozen edition's unresolved publication flags. It is not rights clearance. The hosted deployment is an explicitly authorized public research preview; its separate authorization receipt records that distinction. Do not silently turn archival flags into a scientific or legal approval.

Keep the previous release and nginx backup. For rollback, repoint `current` atomically to the previous verified release, run `sudo nginx -t`, then reload nginx. For the first deployment, remove only the ASD include/snippet using the saved original config. Existing `/web/`, `/web/legacy/` and `/web/api/demo/` routes must pass their original health checks before and after every change.

## Git-tracked upgrades

Prepare and verify a new public bundle locally before deployment. Commit its complete public source and artifacts on a review branch; exclude the separately assembled evaluator and every mutable workspace. On the server, retain a Git repository under `repository/` and create a detached worktree for the exact release commit under `releases/<release-id>/public-release`. Record the commit and all three payload manifests in a private deployment receipt.

Stage the matching static site and protected evaluator alongside that worktree. Verify all payload hashes, task/target contract bindings, owner-only evaluator access, installed package version, and the existing services before switching `current` atomically. Verify HTTPS content, security headers, blocked write routes, scenario/task/rule counts, and the downloaded companion afterward. Retain the prior release for immediate rollback; do not rewrite its files. The private evaluator and deployment state are never committed to the public repository.
