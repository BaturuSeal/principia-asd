<p align="center"><img src="docs/assets/overview.svg" alt="Principia ASD: from measurements to inspectable rules" width="100%"></p>

<p align="center">
  <a href="https://atlas.chipflow.net/web/asd-test/">Explore the live library</a> ·
  <a href="#start-your-own-investigation">Start locally</a> ·
  <a href="docs/METHODS.md">Methods</a> ·
  <a href="docs/EVALUATION.md">Evaluation</a>
</p>

**Principia ASD is a workspace for scientific rule discovery.** It brings compact scientific scenarios, interchangeable discovery methods, and inspectable mathematical rules into one reproducible workflow.

A useful result should be more than a low test loss. You should be able to see the expression, understand its variables, inspect its fitted state, and trace how it was obtained. Principia ASD makes these questions part of the artifact—not an afterthought in a model-written report.

### One task. Multiple explanations. Visible evidence.

- **A common experimental contract.** Each task declares its inputs, output, partitions and evaluation policy. Different methods investigate the same question.
- **Rules you can inspect.** Rule Cards combine rendered mathematics, parameter tables, measurements, development history and deterministic assessments. Accuracy, complexity and stability remain distinct.
- **A method workbench.** Numerical controls, LLM proposal and refinement, adapted research agents, and Adaptive Primitive Search (APS) share one interface. Availability and adaptation boundaries are explicit.
- **Public evidence, private experimentation.** The website serves the shared library. Your folders, API key and newly generated results stay in your local companion. Selected development context goes directly to SiliconFlow only when you run an LLM method.

### Explore what is already here

| Current research preview | Retained evidence |
|---|---:|
| Compact retrospective scenarios / task leaderboards | 40 / 40 |
| Primary method–task attempts | 520 |
| Completed / failed attempts | 483 / 37 |
| Submitted rules | 693 |
| Valid / invalid deterministic assessments | 684 / 9 |

These are coverage counts, not counts of independent discoveries. Every task preserves its failures and original denominator. Scientific review is separate from the numerical ranking.

### Start your own investigation

Python **3.11+**, on macOS or Linux. Download the companion from the website, extract it, and open a terminal in the **`public-release`** folder:

```bash
python3 -m venv ~/.principia-asd-venv
~/.principia-asd-venv/bin/pip install .
~/.principia-asd-venv/bin/principia-asd companion --bundle-root .
```

Open **http://127.0.0.1:8150/**. Keep the terminal running.

1. Browse **Scenario library → Try it yourself**, or import your own grouped numeric CSV.
2. Inspect the task card, choose inputs and output, then select a method. Numerical controls work without a key.
3. For LLM methods, open **API settings**. Save your SiliconFlow key, add or edit exact model IDs, record current prices, and explicitly check model access. Checks are billed; saving settings and browsing the provider catalog do not generate model responses.
4. Run discovery, inspect the frozen Rule Cards, and export the evidence. New runs never overwrite the shared leaderboards.

Use `--port 8152` if the default port is occupied. Private state defaults to `~/.local/share/principia-asd`; `--workspace /another/private/folder` creates a separate workspace. Never expose the local companion to the internet. [Installation and privacy details →](docs/DEPLOYMENT.md)

### Adaptive Primitive Search

APS treats the search space itself as something to investigate. Agents propose primitives, reusable kernels and formula patterns; local code composes and fits candidates; development diagnostics guide subsequent revisions. Every retained kernel expands into operations and parameter bindings that can be inspected.

APS is **one hosted method**, not a synonym for the platform. The historical identifier `principia_engine` is retained for reproducibility. The explicitly marked development protocols expose additional learned-state accounting and do not replace the frozen primary comparison.

### Small public surface. Explicit private boundary.

```text
public-release/                 # GitHub repository and local companion
  src/principia_asd/            # Package, CLI, methods, evaluator, local UI
  data/                        # Public train/dev, test inputs, task contracts
  leaderboards/                # Frozen per-task rules, receipts, exports
  docs/  tests/  configs/       # Explanations, verification and policies

private-evaluator/             # Separate operator-only delivery; never publish
  targets/                     # Protected targets for registered scenarios
  README.md                    # Administrative evaluation and custody
```

The server hosts a separately generated **static website**. It has no user-upload endpoint or discovery API. Visiting the public library requires no installation; running private discovery requires the local companion. Existing test results are viewable, but a new example-scenario run cannot recompute protected test loss without an authorized evaluator. Local imports use a private, local split.

### What this release establishes—and what remains open

This **1.0 release candidate** delivers a working rule-discovery product and a retrospective evidence collection. It does not establish novel scientific laws, causality, independent discovery or method superiority. Six historical preparation defects, three unfinished source reviews and incomplete learned-state accounting for at least 65 rules remain attached to the affected evidence. A few dozen strong scenarios are preferable to an arbitrary count of 100.

The October 15 public research preview is deployed at the project owner's request. That deployment does **not** certify third-party data rights or scientific admission: the frozen edition's unresolved rights flags remain unchanged. Code is MIT; datasets and upstream adaptations retain their own terms. Review [provenance](PROVENANCE.md), [data licenses](data/LICENSES.md) and [known limitations](docs/RELEASE_SCOPE.md) before redistributing data or making scientific claims.

**Build on the evidence.** Add a carefully specified task, contribute a reproducible method adapter, or improve a scenario's source and split audit. The next useful step is a better question with a stronger test—not a larger unqualified score.
