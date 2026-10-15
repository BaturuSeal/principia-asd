# Public website and private local companion

Delivery revision: 15 October 2026. No cloud deployment is performed by this delivery.

## Two surfaces, one collection

The **public website** is static HTML, CSS, JavaScript and versioned JSON. It displays the 40 packaged example scenarios, their tasks, 693 primary rules and all 520 primary attempt outcomes, including 37 failed attempts. The primary ranking is preserved. Separate historical engineering cohorts remain in the companion's portable reports, not merged into the primary leaderboard.

The **local companion** runs discovery on the visitor's own computer. Visitors choose a shared example or a local CSV folder, select a task, method and model roles, and inspect their own rules. It reads the public edition and never writes to the shared data or leaderboard directories. Private imports, custom tasks, API settings, provider receipts, test partitions and run results live in a separate workspace.

“Try it yourself” on the website opens instructions and a link to the local companion. This is a deliberate two-step flow: a public web page cannot run the Python scientific stack against a visitor's local folder. Installation is required for private discovery; browsing the shared results requires no installation or API key.

The public page does **not** fetch localhost APIs, use CORS to reach private services, select files, accept keys, create accounts, store personal results or proxy LLM traffic. The handoff is a normal link opening a separate local-origin tab. Only public scenario/task IDs are included. If a public identifier is absent from the installed edition, the local app keeps its own catalog; it never downloads or executes a remote recipe.

## Visitor setup

Extract the companion bundle. From the extracted directory containing `projects/`, `datas/` and `leaderboards/`:

```bash
python3 -m venv ~/.principia-asd-venv
~/.principia-asd-venv/bin/pip install projects/PrincipiaASD-dev-26Oct10/dist/principia_asd-1.0.0rc3-py3-none-any.whl
~/.principia-asd-venv/bin/principia-asd companion --bundle-root .
```

Open http://127.0.0.1:8150/. Python 3.11+ is required. The restricted numerical interpreter supports macOS/Linux. Separately marked generated-code development workers require the tested macOS sandbox and refuse unsupported platforms. Windows support is not claimed.

The default private workspace is `~/.local/share/principia-asd`. Use `--workspace /my/private/workspace --port 8152` for another independent local installation. The standard web handoff uses port 8150; when choosing another port, open the printed URL and select the scenario there. Different people sharing a computer should use separate OS accounts, not the same companion daemon or workspace.

The companion binds only to `127.0.0.1`. Host, Origin and CSRF checks protect mutation endpoints. No `--host 0.0.0.0` option is provided. **Do not reverse-proxy the companion, share its port or deploy it as a cloud multi-user backend.** The public site has no dependency on an always-running companion.

## SiliconFlow API settings

Use **API settings → Save key locally**. Saving a key makes zero provider calls. The key is stored as plaintext in an owner-readable `0600` file inside a `0700` private workspace directory; it is not claimed to be encrypted or stored in the OS keychain. It is never returned by the API, put in browser storage or URLs, or included in Rule Card downloads. Only the local host gateway uses it for SiliconFlow requests.

Then select models and explicitly click **Check models**. The button shows the conservative reservation: CNY 2 per model, up to CNY 8 for four models. The check uses the frozen exact generation profiles and one small request per model. Uncertain usage stays reserved and is never automatically replayed. Failed capabilities remain unavailable with no model substitution. The gateway retains the dated price snapshot; a later price/configuration change requires a separate reviewed profile.

Replacing or disconnecting a key is blocked while runs or checks are outstanding. Replacing it invalidates previous capability checks. Disconnect removes the app-managed key; externally supplied environment files are never modified or deleted. A restarted local check is shown as interrupted and does not resume by itself. Discovery spending is bounded per run and by the workspace ledger; the historical research ledger is not bundled.

Reference methods need no key. Missing keys or model checks open setup before any LLM discovery request. A successful setup does not automatically start a paid discovery run.

## Data and result custody

| Item | Public cloud | Visitor's computer | SiliconFlow |
|---|---|---|---|
| Shared scenario descriptions and existing rules | Static, read-only | Included in companion | Only when supplied as task context |
| Visitor's original folder | Never received | Read locally; not modified | Folder itself is never sent |
| Selected train/dev measurements | Never received | Private staged data | Necessary permitted context for selected LLM method |
| Imported test targets | Never received | Private evaluator subdirectory | Not supplied to discovery |
| Visitor API key | Never received | Private credential file | Authorization header from local gateway |
| New rules, requests and results | Never received | Private run directory/download | Provider receives model requests only |

The public export builder accepts only the registered data and leaderboard roots. It has no private-workspace argument. It excludes local imports and custom tasks, omits machine paths, and retains failed/invalid outcomes. Initial catalog pages load a small index; full rule data loads separately for the selected task. No analytics, third-party fonts or remote formula renderer are needed.

Numerical results from public examples remain retrospective. New visitor runs without evaluator targets show development results and an explicit pending final assessment. Importing a private folder creates its test partition inside that visitor's workspace, never in the benchmark vault. No personal run is promoted into the public leaderboard.

## Build and host

Run from an installed environment:

```bash
principia-asd build-site \
  --data-root /path/to/datas/ASD-Scenarios-26Oct10 \
  --leaderboard-root /path/to/leaderboards/Scenarios-rules-26Oct10 \
  --output /path/to/new-site-build \
  --companion-bundle /path/to/verified-companion.zip
```

An existing output path is refused. The result includes a `site-manifest.json` with source hashes, file hashes and exact counts. Use the optional companion download only after checking the archive receipt. Without it, the public UI gives installation instructions without inventing a download URL.

**Current data redistribution remains unauthorized in the frozen edition.** The default build therefore refuses public release. `--preview` creates the complete local acceptance preview, explicitly marked `preview_only`; it does not grant permission to publish datasets or derived content. Source rights and scientific admission remain separate from completion of this product work. Do not edit frozen publication flags merely to bypass the gate; create a reviewed successor edition when cleared.

For local preview only:

```bash
python3 -m http.server 8153 --bind 127.0.0.1 --directory /path/to/new-site-build
```

Once publication is cleared, copy **only** the static build into a web root. `deploy/nginx.conf` is a template for a static server behind your HTTPS proxy. It disables writes, directory listings and `/api/`, adds a Content Security Policy restricting scripts and connections to the same origin, and compresses task JSON. Inline layout styles are allowed for KaTeX formula rendering. Check `nginx -t` on the target server before reload. Site files should be read-only for the web-server account. Do not point nginx at the repository parent, private workspace, evaluator directory or the developer's home directory.

Deployments are versioned directories. Verify checksums, switch the document root or a release symlink, and retain the previous build for rollback. No database migration, provider secret, background discovery worker or cloud account system is needed. A cloud visitor can inspect shared results immediately; their private discovery takes place entirely in their own companion.

## Acceptance boundaries

This delivery verifies application behavior and public/private separation. It does not resolve source rights, known historical scientific-contract defects, provisional complexity accounting, missing adapters or external review. Existing frozen comparisons and the previous acceptance archive remain unchanged. No new paid campaign, scientific re-ranking or public upload is part of this change.
