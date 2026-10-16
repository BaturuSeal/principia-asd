# Explorer — rc7 release notes

Version **1.0.0rc7** combines the former Scenario library and Discover pages into one entry point. This revision changes the product interface and local-companion onboarding. Scientific data, task contracts, equations, scores and historical outcomes are preserved.

## One place to explore and investigate

The top of Explorer holds a compact scenario/task selector. Input and output details open on demand; method, model and budget settings open in a discovery dialog. Closing that dialog or visiting API settings preserves the draft configuration.

Below it, **Public examples** presents the shared collection with search, domain and equation-system filters. **My scenarios** keeps imported data separate. Local imports accept a descriptive scenario name and remain in the local workspace. The hosted view explains where personal scenarios live without asking for files or pretending to access the visitor's computer.

Existing scenario guides, task-specific explored rules, equation cards, API settings and run history remain accessible. Older `#scenarios` and `#discover/...` links are supported.

## A deliberate handoff to local discovery

A public website cannot start software on the visitor's computer. The previous direct localhost link could therefore lead to a connection error. **Set up local discovery** now provides the companion download, installation commands, platform requirements and troubleshooting first.

For an already running companion, the visitor enters its printed address and confirms it is running. The link accepts only a plain HTTP loopback origin, including a custom port. A normal same-tab navigation carries the selected public scenario and task; it needs no popup and sends no folder path, key or result. The public page does not probe localhost or call local APIs.

`principia-asd companion --bundle-root . --open-browser` opens the local workspace after successfully binding its port. An occupied port produces an actionable message. Private execution requires a supported desktop environment; mobile visitors can browse shared examples and results.

## Verification and release

- Local workspace: `http://127.0.0.1:8150/`
- Hosted-site preview: `http://127.0.0.1:8155/web/asd-test/`
- Acceptance evidence: `LOCAL_ACCEPTANCE.json` alongside the rc7 delivery directory, with browser screenshots and verification results.

The owner accepted this revision and authorized cloud deployment and a new GitHub pull request on 16 October 2026. The original local acceptance delivery remains unchanged as evidence. A separately assembled deployment records that authorization; the release builder continues to default to local-only authorization.

The accepted build passed 1,699 Python tests (three skipped), Ruff, both frontend suites, a fresh installation, and all 16 CLI help paths. Browser checks covered desktop and mobile Explorer layouts, public setup, a real task handoff to the local companion, API gating, local import, a zero-API numerical run, and typeset equation cards. The public inventory remains 47 scenarios, 51 task leaderboards, 799 rules and 631 retained attempts. All scientific payloads are unchanged from rc6.

## Contributor attribution

New release commits use the owner's GitHub identity, `Chipflow-pzq`, and its ID-based GitHub noreply address. The two earlier rc6 commits accidentally used an agent default identity. At the owner's request, `.mailmap` canonicalizes that name and email in compatible Git history and contributor tools without rewriting their hashes or the merged branch. Raw historical commit headers remain unchanged. GitHub's contributors view requires qualifying commits on the default branch; the new release commit establishes that attribution once merged.
