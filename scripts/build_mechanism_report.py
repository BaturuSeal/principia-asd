"""Read frozen evidence only: per-task comparisons, retained failures and local report."""

import argparse
import collections
import csv
import html
from pathlib import Path

from principia_asd.io import file_sha, read_json, write_json

CONTROL_METHODS = {
    "mean_control",
    "linear_control",
    "polynomial_control",
    "tree_control",
    "persistence_control",
}


def build(data, leaderboard, output):
    freeze = read_json(leaderboard / "receipts/campaign-freeze.json")
    assert freeze["all_submissions_frozen"]
    rules = read_json(leaderboard / "exports/all-rules.json")
    attempts = read_json(leaderboard / "exports/all-attempts.json")
    coverage = read_json(leaderboard / "exports/coverage.json")
    rows = []

    def selected(values):
        return min(values, key=lambda r: (r["card"]["dev_error"], r["rule_id"])) if values else None

    def short(row):
        if row is None:
            return None
        card = row["card"]
        return {
            "rule_id": row["rule_id"],
            "method": row["method_id"],
            "method_revision": card["method_version"],
            "name": card.get("equation_system", {}).get("name", row["method_id"]),
            "dev_loss": card["dev_error"],
            "test_loss": row["accuracy"]["primary_error"],
            "equations": len(card.get("equation_system", {}).get("nodes", [])),
            "operators": row["simplicity"]["weighted_operator_count"],
            "parameters": row["simplicity"]["free_parameters"],
            "origin": card.get("origin"),
            "status": row["status"],
            "coverage": row["coverage"]["fraction"],
            "identifiability": card.get("identifiability"),
        }

    for sid in sorted({r["scenario_id"] for r in rules}):
        task = read_json(data / "scenarios" / sid / "task-contracts/task-001.json")
        info = read_json(data / "scenarios" / sid / "scenario.json")
        group = [r for r in rules if r["scenario_id"] == sid]
        controls = [
            r
            for r in group
            if r["method_id"] in CONTROL_METHODS
            and (
                r["method_id"] not in {"linear_control", "polynomial_control"}
                or r["card"]["method_version"] == "centered-least-squares-v3"
            )
        ]
        # Selection never uses test error, including failed/invalid assessments.
        control = selected(controls)
        equation = selected([r for r in group if r["method_id"] == "equation_search"])
        agent = selected([r for r in group if r["method_id"] == "equation_agent"])
        c, e, a = short(control), short(equation), short(agent)
        delta = None
        if (
            c
            and e
            and c["test_loss"] is not None
            and e["test_loss"] is not None
            and c["test_loss"] > 0
        ):
            delta = 100 * (1 - e["test_loss"] / c["test_loss"])
        valid_control_losses = [
            r["accuracy"]["primary_error"]
            for r in controls
            if r["accuracy"]["primary_error"] is not None
        ]
        strongest_control = min(valid_control_losses) if valid_control_losses else None
        rows.append(
            {
                "scenario_id": sid,
                "title": info["title"],
                "task_id": task["task_id"],
                "units": task["quantity_units"][task["output"]],
                "partitions": info["rows"],
                "development_selected_control": c,
                "development_selected_scientific_model": e,
                "development_selected_agent_rule": a,
                "scientific_model_test_loss_reduction_percent": delta,
                "strongest_observed_control_test_loss": strongest_control,
                "scientific_model_below_every_control_test_loss": e is not None
                and e["test_loss"] is not None
                and strongest_control is not None
                and e["test_loss"] < strongest_control,
                "attempt_outcomes": dict(
                    collections.Counter(x["status"] for x in attempts if x["scenario_id"] == sid)
                ),
                "limits": info["limitations"],
            }
        )
    report = {
        "scope": "Retrospective local engineering comparison, not a new primary benchmark or independent mechanism validation",
        "selection": "Minimum development loss within each workflow; comparator chosen on development from mean, corrected linear/polynomial, tree and eligible persistence. Every outcome retained. Strongest observed test control is an additional descriptive comparison, not a selection criterion.",
        "control_correction": "All eight linear/polynomial controls were refitted uniformly after a synthetic constant-coordinate conditioning defect was confirmed. Earlier solver outputs remain in the canonical exports and attempt denominator. Current comparison uses centered-least-squares-v3 only for these two methods.",
        "model_failures": "The first eight multi-role attempts failed. A separate output-bounded revision retained those attempts and produced three complete, one incomplete and four provider-failed attempts. No ambiguous billed request was replayed.",
        "coverage": coverage,
        "costs": read_json(leaderboard / "exports/costs.json"),
        "source_binding": {
            "data_edition_sha256": file_sha(data / "EDITION.json"),
            "all_rules_sha256": file_sha(leaderboard / "exports/all-rules.json"),
            "all_attempts_sha256": file_sha(leaderboard / "exports/all-attempts.json"),
        },
        "scenarios": rows,
        "scientific_review": "not_assessed",
        "independent_mechanism_validation": "not_assessed",
        "novelty": "not_assessed",
        "run_to_run_stability": "not_assessed",
        "small_group_uncertainty": "No confidence interval claimed for these small, heterogeneous grouped holdouts",
    }
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "comparison.json", report)
    with (output / "comparison.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "scenario_id",
                "title",
                "units",
                "control",
                "control_test_loss",
                "scientific_model",
                "scientific_model_test_loss",
                "scientific_model_test_loss_reduction_percent",
                "agent_test_loss",
                "equations",
            ],
        )
        writer.writeheader()
        for r in rows:
            c, e, a = (
                r["development_selected_control"],
                r["development_selected_scientific_model"],
                r["development_selected_agent_rule"],
            )
            writer.writerow(
                {
                    "scenario_id": r["scenario_id"],
                    "title": r["title"],
                    "units": r["units"],
                    "control": c["method"],
                    "control_test_loss": c["test_loss"],
                    "scientific_model": e["name"],
                    "scientific_model_test_loss": e["test_loss"],
                    "scientific_model_test_loss_reduction_percent": r[
                        "scientific_model_test_loss_reduction_percent"
                    ],
                    "agent_test_loss": a["test_loss"] if a else None,
                    "equations": e["equations"],
                }
            )
    esc = html.escape

    def fmt(value):
        return "—" if value is None else f"{value:.4g}"

    body = []
    for r in rows:
        c, e, a = (
            r["development_selected_control"],
            r["development_selected_scientific_model"],
            r["development_selected_agent_rule"],
        )
        body.append(
            f'<article><p class="eyebrow">{r["scenario_id"]} · {esc(r["units"])}</p><h2>{esc(r["title"])}</h2><p>{esc(e["name"])} · {e["equations"]} connected equations · {e["parameters"]} shared parameters.</p><table><tr><th>Workflow / dev-selected rule</th><th>Dev MAE</th><th>Test MAE</th></tr><tr><td>Control: {esc(c["method"])}</td><td>{fmt(c["dev_loss"])}</td><td>{fmt(c["test_loss"])}</td></tr><tr><td>Scientific equation search · sourced priors</td><td>{fmt(e["dev_loss"])}</td><td>{fmt(e["test_loss"])}</td></tr><tr><td>Adaptive Equation Discovery</td><td>{fmt(a["dev_loss"] if a else None)}</td><td>{fmt(a["test_loss"] if a else None)}</td></tr></table><p>{esc(a["origin"] if a else "No complete model-agent submission. Failed or incomplete attempts remain recorded.")}</p><details><summary>Scope and retained outcomes</summary><p>{esc(str(r["attempt_outcomes"]))}</p><ul>'
            + "".join("<li>" + esc(x) + "</li>" for x in r["limits"])
            + f'</ul></details><a href="http://127.0.0.1:8150/#scenario/{r["scenario_id"]}">Inspect equations and all fits →</a></article>'
        )
    page = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Principia ASD · connected scientific models</title><style>body{font:16px/1.65 system-ui;background:#f5f3ec;color:#202b29;margin:0}main{max-width:1100px;margin:auto;padding:48px 24px}h1{font-size:44px;line-height:1.15}h2{font-size:23px}p{max-width:85ch}.eyebrow{letter-spacing:.1em;font-size:12px;color:#466354;text-transform:uppercase}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:20px}article{background:#fff;border:1px solid #d9dfd7;border-radius:12px;padding:24px}table{width:100%;border-collapse:collapse;font-size:14px}th,td{border-bottom:1px solid #e6e6df;text-align:left;padding:10px 4px}a{color:#255b49}details{margin:20px 0}li{margin:6px 0}</style><main><p class="eyebrow">Principia ASD · local rc6 scientific preview</p><h1>Connected equations.<br>Competing explanations.</h1><p>Eight new or upgraded tasks combine physically interpretable intermediate quantities, shared parameters, matched controls and frozen test assessment. Known scientific families are explicit priors, not discoveries.</p><p>'
        + esc(report["selection"])
        + "</p><p><b>"
        + str(coverage["attempts"])
        + " retained attempts · "
        + str(coverage["rules"])
        + " frozen rules · 8 tasks.</b> Four scenarios are new to the local library.</p><details><summary>Read the experimental limits before interpreting gains</summary><p>"
        + esc(report["control_correction"])
        + "</p><p>"
        + esc(report["model_failures"])
        + '</p><p>No scientific novelty, independently identified mechanism or universal advantage is claimed. The biosensor and soil tasks favor simpler controls; the learned gearbox revision transfers worse than its source model.</p></details><p><a href="comparison.json">Full evidence JSON</a> · <a href="comparison.csv">Comparison CSV</a></p><div class="grid">'
        + "".join(body)
        + "</div></main></html>"
    )
    (output / "index.html").write_text(page)
    print(
        {
            "attempts": coverage["attempts"],
            "rules": coverage["rules"],
            "tasks": len(rows),
            "improve_over_dev_selected_control": sum(
                (r["scientific_model_test_loss_reduction_percent"] or 0) > 0 for r in rows
            ),
            "below_all_observed_controls": sum(
                r["scientific_model_below_every_control_test_loss"] for r in rows
            ),
        }
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ["data", "leaderboard", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    build(a.data, a.leaderboard, a.output)
