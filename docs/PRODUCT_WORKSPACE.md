# Product workspace

The October 14 interface revision organizes discovery around a scenario, a task and a method. It retains the existing scientific records and adds readable presentation and task management.

## Example scenarios

All 40 packaged examples have an editorial title and a short scientific introduction. A scenario guide explains the measurements, independent unit, input representation, partitions, source context and limitations. Local installations show the resolved package path with a copy action. Portable reports use relative package links instead of embedding a developer's filesystem path.

The [scenario guide](../data/SCENARIO_GUIDE.md) provides the same introductions and variable definitions outside the application. Unknown physical units or upstream derivation details remain explicitly qualified. Editorial descriptions do not replace frozen task contracts or grant scientific admission.

The first release has no minimum scenario count. A few dozen reviewed, useful scenarios are sufficient; further editions may expand the collection without weakening the quality gates.

## Tasks and variables

Each task declares its permitted inputs and one output. The task selector displays a readable prediction question. Click a variable chip to read its meaning, units, role and recorded lineage. A scenario can contain multiple preset contracts; its task selector and leaderboards keep them separate.

**Add task** lets a user choose a different combination of the preset task's available numeric variables. The new task receives its own identity and lives in the private workspace. It preserves the original training and development groups, exposes only the selected fields to the method, and does not copy test observations, targets or assessment permissions. Users can add another task for a different output. Timing and scientific appropriateness require review whenever the question changes.

Custom tasks produce development portfolios. Their Test loss remains unavailable until a separate, reviewed evaluation contract is supplied; the application never reuses the original task's test score or treats development error as test error.

## Rule leaderboards

Choose a scenario, then a task. Each task has its own table:

| Column | Meaning |
|---|---|
| Rule | Unique descriptive display name, linked to the Rule Card |
| Method | The actual method recorded for the rule |
| Test loss | The task's frozen primary loss, or unavailable for unassessed work |
| Rule operators | The recorded expanded operator count |
| Parameters | The recorded free-parameter count |
| Status | Execution and assessment state, including provisional or invalid results |

The scenario's portable page links to every task instead of overwriting one task with another. Campaign exports partition submissions, rankings and failed-attempt denominators by the actual task identity. Known preparation and learned-state limitations stay attached to affected results.

## Reading a rule

Each Rule Card shows a LaTeX expression rendered locally with KaTeX and native MathML. Fitted parameters use symbolic names; separate tables show their meanings and values to four significant digits. Input symbols link the expression to measurement definitions. Decision-tree rules expose a compact region formula and all terminal-region conditions.

The card also includes a structural interpretation, applicability limits, test performance, discovery method and model recipe, provenance, and downloadable exact artifacts. **Copy LaTeX** copies the mathematical source. Display rounding never changes stored coefficients, executable programs, predictions or scores.

An interpretation explains what the expression computes. It does not establish mechanism, causality or novelty. Historical complexity counts and their limitations are preserved; a presentation change cannot repair an incomplete learned-state audit.

## Methods and product content

**Adaptive Primitive Search (APS)** replaces the display name Principia Engine. APS is one method hosted by Principia ASD. Internal `principia_engine` and `principia_engine_explicit` identifiers remain unchanged so existing runs, capabilities and freezes remain reproducible.

Functional pages focus on selecting tasks, executing discovery and inspecting evidence. General product information appears under **About & release**. Campaign accounting is absent from the navigation sidebar; request budgeting and private accounting remain enforced by the backend.

## Scope

This revision changes the product experience, not the scientific status of the frozen comparison. It makes no new provider requests and does not rerun discovery or modify published numerical records. Source rights, scientific admission, remaining method integrations and separate scientific review remain tracked release gates. The product is still a research release candidate and has not been publicly deployed.
