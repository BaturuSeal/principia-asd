"""Portable, human-readable views of already exported evidence; no fitting or scoring."""

from __future__ import annotations

import html
import json
import math
import os
import re
import uuid
from pathlib import Path
from urllib.parse import quote

from .catalog.presentation import describe_scenario, describe_task
from .catalog.reviews import task_advisories
from .io import contained, file_sha, read_json
from .methods.registry import METHODS
from .web.rule_view import rule_view

STYLE = """
:root{color-scheme:light;--ink:#283046;--muted:#626b80;--line:#e4e5ee;--accent:#6653b9}
*{box-sizing:border-box}body{margin:0;background:#f7f7fc;color:var(--ink);font:15px/1.6 system-ui,sans-serif}
header,main,footer{max-width:1160px;margin:auto;padding:24px}header{display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid var(--line)}
a{color:var(--accent);text-underline-offset:3px}a:hover{text-decoration-thickness:2px}a:focus-visible,input:focus-visible{outline:3px solid #ad9bff;outline-offset:4px}
header a{font-size:20px;font-weight:750;text-decoration:none}h1{font-size:clamp(26px,4vw,38px);line-height:1.2;margin:12px 0 20px}h2{font-size:22px;margin-top:32px}h3{font-size:17px;margin:10px 0}
p{max-width:85ch}.muted,small{color:var(--muted)}small{display:block;font-size:12px}.eyebrow{text-transform:uppercase;letter-spacing:.12em;color:var(--accent);font-size:12px;font-weight:700}
.panel,.card,.stat{background:white;border:1px solid var(--line);border-radius:14px;padding:20px}.panel{margin:20px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}.card{display:flex;flex-direction:column;gap:8px}.card h3{flex:1}.card p{margin:0}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin:24px 0}.stat strong{display:block;font-size:25px;font-variant-numeric:tabular-nums}.stat span{color:var(--muted);font-size:13px}
.tag{display:inline-block;padding:3px 9px;border-radius:6px;background:#efecfa;color:#5c489f;font-size:12px;margin:2px}.warning{background:#fff4df;color:#79540a}.note{padding:16px 20px;background:#f0edf9;border-left:3px solid #a492dd;border-radius:5px}
.table{overflow:auto;border:1px solid var(--line);border-radius:12px;background:white;margin:20px 0}table{width:100%;border-collapse:collapse;white-space:nowrap}th,td{padding:14px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}thead{background:#f0eff7}td.wrap{white-space:normal;min-width:260px}td.num{font-variant-numeric:tabular-nums}caption{text-align:left;padding:14px;color:var(--muted)}
.formula{font:14px/1.7 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;padding:18px;background:#f5f4fa;border-radius:10px}dl{display:grid;grid-template-columns:minmax(140px,1fr) 3fr;gap:14px 20px}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}.links{display:flex;gap:16px;flex-wrap:wrap}.crumb{font-size:13px}.id{overflow-wrap:anywhere;word-break:break-word}footer{font-size:13px;color:var(--muted)}
input{display:block;width:100%;max-width:540px;font:inherit;padding:12px;border:1px solid #c8c8d8;border-radius:8px;background:white;margin:8px 0 24px}[hidden]{display:none!important}details>summary{cursor:pointer;color:var(--accent)}
@media(max-width:600px){header,main,footer{padding:18px}dl{grid-template-columns:1fr;gap:6px}dd{margin-bottom:12px}.cards{grid-template-columns:1fr}header{align-items:center}.panel{padding:16px}}
"""


def esc(value):
    return html.escape(str(value), quote=True)


def number(value):
    if value is None:
        return "Not available"
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        return f"{value:.4g}" if math.isfinite(value) else "Invalid"
    return esc(value)


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ValueError("Unsafe artifact identity")
    return value


def relative(page, target):
    return quote(os.path.relpath(target, page.parent), safe="/.-_")


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def page(root, destination, title, body, script=""):
    sheet = relative(destination, root / "assets/report.css")
    home = relative(destination, root / "index.html")
    math_script = relative(destination, root / "assets/katex.min.js")
    render_script = relative(destination, root / "assets/math.js")
    document = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{esc(title)} · Principia ASD</title><link rel="stylesheet" href="{sheet}"><script defer src="{math_script}"></script><script defer src="{render_script}"></script></head>'
        f'<body><header><a href="{home}">Principia ASD</a><span>Rule evidence · research candidate</span></header>'
        f"<main>{body}</main><footer>Read-only views of frozen records. Quantitative assessment and scientific review are separate. "
        f"No cross-scenario scientific score is implied.</footer>{script}</body></html>"
    )
    _write(destination, document)


def method_name(method_id):
    method = METHODS.get(method_id)
    return method.name if method else method_id


def link(page_path, target, label):
    return f'<a href="{relative(page_path, target)}">{esc(label)}</a>'


def pairs(items):
    return "<dl>" + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in items) + "</dl>"


def stats(items):
    return (
        '<div class="stats">'
        + "".join(
            f'<div class="stat"><strong>{number(v)}</strong><span>{esc(k)}</span></div>'
            for k, v in items
        )
        + "</div>"
    )


def review_notices(advisories):
    return "".join(
        f'<aside class="note"><strong>{esc(a["scenario_id"])} · {esc(a["title"])}</strong>'
        f"<p>{esc(a['detail'])}</p><p>{esc(a['consequence'])}</p></aside>"
        for a in advisories
    )


def render_rule(root, board, row, task_dir, title, attempt, advisories=(), task=None):
    rid = safe_id(row["rule_id"])
    directory = contained(task_dir, "rules/" + rid)
    card_path = directory / "rule-card.json"
    receipt_path = directory / "evaluation-receipt.json"
    program_path = directory / "program/expression.json"
    for artifact in [card_path, receipt_path, program_path]:
        if not artifact.is_file():
            raise ValueError("Missing exported rule artifact: " + str(artifact))
    card, receipt = read_json(card_path), read_json(receipt_path)
    if (
        card != row["card"]
        or receipt["rule_id"] != rid
        or receipt["rule_sha256"] != card["rule_sha256"]
    ):
        raise ValueError("Rule page differs from canonical artifacts")
    if any(row.get(key) != value for key, value in receipt.items()):
        raise ValueError("Leaderboard metrics differ from the frozen evaluation receipt")
    output = directory / "index.html"
    unit = card.get("units", {}).get("output", "not supplied")
    formula = card.get("simplicity", {}).get("expanded_expression") or card["expression"]
    presentation = rule_view(card, task or {})
    metric = row["accuracy"]["primary"]
    front = rid in board.get("pareto_front_rule_ids", [])
    body = (
        '<p class="crumb">'
        + link(output, root / "index.html", "All scenarios")
        + " / "
        + link(
            output, root / "scenarios" / board["scenario_id"] / "index.html", board["scenario_id"]
        )
        + '</p><div class="eyebrow">Frozen Rule Card</div>'
        + f"<h1>{esc(presentation['name'])}</h1><p>{esc(title)} · {esc(method_name(row['method_id']))}</p>"
        + f'<p class="id muted">{esc(rid)}</p><span class="tag">{esc(row["status"])}</span>'
        + ('<span class="tag">Pareto front</span>' if front else "")
        + f'<span class="tag {"" if row["accuracy_gate"] else "warning"}">{"Accuracy gate passed" if row["accuracy_gate"] else "Accuracy gate not met"}</span>'
    )
    body += review_notices(advisories)
    body += stats(
        [
            ("Test " + metric.upper(), row["accuracy"]["primary_error"]),
            ("Weighted rule operations", row["simplicity"]["weighted_operator_count"]),
            ("Free parameters", row["simplicity"]["free_parameters"]),
            (
                "Coverage",
                str(row["coverage"]["predicted"]) + " / " + str(row["coverage"]["eligible"]),
            ),
        ]
    )
    body += '<section class="panel"><h2>Executable rule</h2>'
    body += f'<div class="math-panel" data-latex="{esc(presentation["latex"])}"></div>'
    if presentation["regions"]:
        body += (
            "<details><summary>All decision regions</summary>"
            + "".join(
                f'<div class="math-panel" data-latex="{esc(r["condition"])}"></div><span data-latex="{esc(r["symbol"])}"></span>'
                for r in presentation["regions"]
            )
            + "</details>"
        )
    body += (
        "<h3>Interpretation</h3><p>"
        + esc(presentation["interpretation"])
        + '</p><p class="muted">'
        + esc(presentation["interpretation_scope"])
        + "</p>"
    )
    body += '<h3>Variables</h3><div class="table"><table><thead><tr><th>Symbol</th><th>Meaning</th><th>Units</th></tr></thead><tbody>'
    body += "".join(
        f'<tr><td data-latex="{esc(v["symbol"])}"></td><td class="wrap">{esc(v["description"])}</td><td>{esc(v["units"])}</td></tr>'
        for v in presentation["variables"]
    )
    body += (
        "</tbody></table></div><h3>ASD recipe</h3><p>"
        + esc(method_name(card["method_id"]))
        + "</p><p>"
        + esc(
            METHODS[card["method_id"]].mechanism
            if card["method_id"] in METHODS
            else "See the recorded method configuration"
        )
        + "</p>"
    )
    body += (
        '<details><summary>LaTeX and full-precision executable source</summary><pre class="formula">'
        + esc(presentation["expanded_latex"] or presentation["latex"])
        + '</pre><pre class="formula">'
        + esc(formula)
        + "</pre></details>"
    )
    body += pairs(
        [
            ("Inputs", ", ".join(card.get("inputs", []))),
            ("Output", card.get("output", "target") + " (" + unit + ")"),
            ("Representation", card.get("representation", "expression")),
            (
                "Input units",
                json.dumps(card.get("units", {}).get("inputs", {}), ensure_ascii=False),
            ),
            ("Unit verification", card.get("units", {}).get("status", "Not assessed")),
            ("Rule preprocessing", card["simplicity"].get("preprocessing", "See complete program")),
        ]
    )
    body += '<h3>Parameter values</h3><p class="muted">Four significant digits; execution retains full precision.</p><div class="table"><table><thead><tr><th>Symbol</th><th>Value</th><th>Role</th></tr></thead><tbody>'
    body += "".join(
        f'<tr><td data-latex="{esc(v["symbol"])}"></td><td>{number(v["value"])}</td><td class="wrap">{esc(v["description"])}</td></tr>'
        for v in presentation["parameters"]
    )
    body += "</tbody></table></div></section>"
    body += '<section class="panel"><h2>Assessment and limitations</h2>'
    sensitivity = row.get("stability", {})
    body += pairs(
        [
            (
                "Primary metric",
                metric.upper()
                + "; "
                + row["accuracy"].get("aggregation", "declared task aggregation"),
            ),
            ("Training loss", number(card.get("train_error"))),
            ("Development loss", number(card.get("dev_error"))),
            ("Train-mean comparator loss", number(row.get("baseline_loss"))),
            ("Mean sensitivity", number(sensitivity.get("mean_relative_sensitivity"))),
            ("Sensitivity scope", sensitivity.get("scope", "Not assessed")),
            ("Uncertainty", row.get("uncertainty", {}).get("reason", "Not assessed")),
            ("Scientific review", row.get("scientific_review", "not_assessed")),
            ("Test exposure", row.get("test_exposure", board.get("exposure", "Not supplied"))),
            ("Evaluator", row.get("evaluator_version", "Not supplied")),
        ]
    )
    body += '<p class="note">Complexity counts the submitted expression or tree relative to prepared inputs. Upstream scenario preprocessing, calibration and scientific property routines are not included; inspect the scenario contract and preparation records. Historical learned-state accounting is incomplete: the primary audit found 64 rules with train-derived normalization literals and one rule with copied fitted coefficients. These are exact-match lower bounds. Preserve the recorded metrics, but treat complexity and Pareto labels as provisional until a versioned correction is assessed. Predictive performance does not establish mechanism, novelty, causality or impact. Sensitivity is diagnostic unless the task contract explicitly authorizes ranking.</p></section>'
    body += '<section class="panel"><h2>Provenance and reproducibility</h2>'
    body += pairs(
        [
            ("Method revision", card.get("method_version", "Not supplied")),
            ("Models", ", ".join(card.get("model_ids", [])) or "Local numerical method"),
            ("Campaign", row.get("campaign_id", "Not supplied")),
            ("Attempt", row.get("run_id", "Not supplied")),
            ("Rule hash", card["rule_sha256"]),
            ("Attempt accounting", json.dumps(attempt.get("accounting", {}), ensure_ascii=False)),
        ]
    )
    body += '<p class="muted">Accounting is shared by all rules from this attempt. Exact numeric precision and full learned state are retained in the downloads.</p><div class="links">'
    body += (
        "".join(
            link(output, target, label)
            for target, label in [
                (card_path, "Rule Card JSON"),
                (program_path, "Executable representation"),
                (receipt_path, "Evaluation receipt"),
            ]
        )
        + "</div></section>"
    )
    page(root, output, rid, body)


def render_leaderboards(root: Path, data_root: Path | None = None):
    """Read canonical exported boards, writing HTML/CSS only. Safe during discovery."""
    root = root.resolve()
    edition_path = root / "EDITION.json"
    edition_hash = file_sha(edition_path)
    edition = read_json(edition_path)
    coverage = read_json(root / "exports/coverage.json")
    records = []
    for board_path in sorted((root / "scenarios").glob("*/tasks/*/leaderboard.json")):
        board = read_json(board_path)
        # Stale derived folders must not add rows to the selected edition.
        if board.get("campaign_id") != edition["campaign_id"]:
            continue
        sid = safe_id(board["scenario_id"])
        if board_path.parent.parent.parent.name != sid:
            raise ValueError("Scenario path does not match its board identity")
        descriptor = {}
        task = {}
        advisories = []
        if data_root:
            source = contained(data_root, "scenarios/" + sid + "/scenario.json")
            if source.exists():
                descriptor = read_json(source)
                for task_path in sorted((source.parent / "task-contracts").glob("*.json")):
                    candidate = read_json(task_path)
                    if candidate.get("task_id") == board["task_id"]:
                        task = candidate
                        advisories = task_advisories(task)
                        break
                descriptor = descriptor | describe_scenario(descriptor, task)
        title = descriptor.get("title", sid)
        domain = descriptor.get("domain", "Scientific measurements")
        task_dir = board_path.parent
        output = task_dir / "index.html"
        attempts = {a["run_id"]: a for a in board["attempts"]}
        for row in board["rules"]:
            render_rule(
                root,
                board,
                row,
                task_dir,
                title,
                attempts.get(row.get("run_id"), {}),
                advisories,
                task,
            )
        body = '<p class="crumb">' + link(output, root / "index.html", "← All scenarios") + "</p>"
        body += f'<div class="eyebrow">{esc(sid)} · {esc(domain)}</div><h1>{esc(title)}</h1>'
        body += (
            f"<p>{esc(board['task_id'])} · {esc(board.get('track', 'engineering'))} comparison</p>"
        )
        body += review_notices(advisories)
        body += (
            '<p class="note">'
            + esc(board["ranking"])
            + ". Scientific review: "
            + esc(board["scientific_review"])
            + ".</p>"
        )
        body += stats(
            [
                ("Frozen rules", len(board["rules"])),
                ("Assigned attempts", len(board["attempts"])),
                ("Failed attempts", sum(a["status"] == "failed" for a in board["attempts"])),
            ]
        )
        body += (
            '<div class="links">'
            + link(output, board_path, "Complete leaderboard JSON")
            + link(output, task_dir / "leaderboard.csv", "Download CSV")
            + "</div>"
        )
        body += '<h2>Rules and predictive evidence</h2><div class="table"><table><caption>Open a rule to inspect its formula, parameters, provenance and receipts. Row order is not a universal scientific score. Complexity counts the submitted expression or tree relative to prepared inputs. Upstream scenario preprocessing, calibration and scientific property routines are not included; inspect the scenario contract and preparation records. Historical learned-state accounting is incomplete: the primary audit found 64 rules with train-derived normalization literals and one rule with copied fitted coefficients. These are exact-match lower bounds. Preserve the recorded metrics, but treat complexity and Pareto labels as provisional until a versioned correction is assessed.</caption><thead><tr><th scope="col">Rule</th><th scope="col">Method</th><th scope="col">Test loss</th><th scope="col">Rule operators</th><th scope="col">Parameters</th><th scope="col">Status</th></tr></thead><tbody>'
        for row in board["rules"]:
            rid = safe_id(row["rule_id"])
            details = task_dir / "rules" / rid / "index.html"
            body += '<tr><td class="wrap">' + link(
                output, details, rule_view(row["card"], task)["name"]
            )
            body += f'</td><td>{esc(method_name(row["method_id"]))}</td><td class="num">{number(row["accuracy"]["primary_error"])}<small>{esc(row["accuracy"]["primary"].upper())}</small></td>'
            body += f"<td>{number(row['simplicity']['weighted_operator_count'])}</td><td>{number(row['simplicity']['free_parameters'])}</td>"
            body += f'<td><span class="tag">{esc(row["status"])}</span>'
            if rid in board.get("pareto_front_rule_ids", []):
                body += '<span class="tag">Pareto front</span>'
            elif not row["accuracy_gate"]:
                body += '<span class="tag warning">Below accuracy gate</span>'
            body += "</td></tr>"
        if not board["rules"]:
            body += '<tr><td colspan="6">No rules were submitted. All assigned attempts remain below.</td></tr>'
        body += '</tbody></table></div><h2>All assigned attempts</h2><div class="table"><table><thead><tr><th scope="col">Attempt</th><th scope="col">Execution</th><th scope="col">Rules</th><th scope="col">Reason</th></tr></thead><tbody>'
        for attempt in board["attempts"]:
            body += f'<tr><td class="wrap">{esc(method_name(attempt["method_id"]))}<small class="id">{esc(attempt["run_id"])}</small></td><td>{esc(attempt["status"])}</td><td>{attempt["rule_count"]}</td><td class="wrap">{esc(attempt.get("reason") or "—")}</td></tr>'
        body += "</tbody></table></div>"
        page(root, output, sid + " rule leaderboard", body)
        records.append(
            {
                "body": body,
                "task_title": describe_task(task)["display_title"]
                if task.get("inputs")
                else board["task_id"],
                "sid": sid,
                "title": title,
                "domain": domain,
                "rules": len(board["rules"]),
                "attempts": len(board["attempts"]),
                "path": output,
                "review_advisories": advisories,
            }
        )
    grouped = {}
    for record in records:
        grouped.setdefault(record["sid"], []).append(record)
    scenario_records = []
    for sid, tasks in grouped.items():
        output = root / "scenarios" / sid / "index.html"
        record = tasks[0]
        if len(tasks) == 1:
            # Keep the established scenario URL as a full single-task view.
            # Links must be relative to this page, so use a task selector as the entry point.
            body = f"<h1>{esc(record['title'])}</h1><h2>Tasks</h2>" + link(
                output, record["path"], record["task_title"]
            )
        else:
            body = f"<h1>{esc(record['title'])}</h1><h2>Task leaderboards</h2>" + "".join(
                '<section class="panel"><h3>'
                + link(output, t["path"], t["task_title"])
                + f"</h3><p>{t['rules']} rules · {t['attempts']} assigned attempts</p></section>"
                for t in tasks
            )
        body += review_notices(record["review_advisories"])
        page(root, output, record["title"], body)
        scenario_records.append(
            record
            | {
                "path": output,
                "rules": sum(t["rules"] for t in tasks),
                "attempts": sum(t["attempts"] for t in tasks),
            }
        )
    records = scenario_records
    if (
        len(records) != coverage["scenarios"]
        or sum(r["rules"] for r in records) != coverage["rules"]
        or sum(r["attempts"] for r in records) != coverage["assigned_attempt_denominator"]
    ):
        raise ValueError("HTML coverage differs from the canonical fixed denominator")
    output = root / "index.html"
    body = '<div class="eyebrow">Reproducible scientific rule discovery</div><h1>Scenario rule leaderboards</h1>'
    body += "<p>Explore each task, compare its frozen rules, and follow every result back to an executable representation and assessment receipt.</p>"
    body += stats(
        [
            ("Scenarios", coverage["scenarios"]),
            ("Frozen rules", coverage["rules"]),
            ("Assigned attempts", coverage["assigned_attempt_denominator"]),
            ("Failed attempts retained", coverage["status_counts"].get("failed", 0)),
        ]
    )
    track = coverage.get("track", "engineering")
    body += f'<p class="note">{esc(track.capitalize())} comparison · version {esc(edition["version"])}. Historical test exposure is retrospective. Scientific review remains {esc(edition.get("scientific_review", "not_assessed"))}. Failed attempts stay in the denominator.</p>'
    all_advisories = [a for record in records for a in record["review_advisories"]]
    if all_advisories:
        body += (
            '<details class="note"><summary>Scientific scope and source-review notes · '
            + str(len(all_advisories))
            + " notices</summary>"
            + review_notices(all_advisories)
            + "</details>"
        )
    body += (
        '<p class="links">'
        + "".join(
            link(output, root / target, label)
            for target, label in [
                ("exports/all-rules.csv", "All rules CSV"),
                ("exports/coverage.json", "Coverage receipt"),
                ("exports/all-attempts.json", "All attempts JSON"),
                ("reviews/scientific-review.json", "Scientific review status"),
            ]
        )
        + '</p><label for="scenario-search">Find a scenario by title, domain or ID</label><input id="scenario-search" type="search" placeholder="For example: fracture, battery, P100-054"><p id="search-count" class="muted" aria-live="polite">'
        + str(len(records))
        + ' scenarios</p><div class="cards">'
    )
    for record in records:
        search = " ".join([record["sid"], record["title"], record["domain"]]).lower()
        body += (
            f'<article class="card" data-search="{esc(search)}"><div class="eyebrow">{esc(record["sid"])} · {esc(record["domain"])}</div><h3>'
            + link(output, record["path"], record["title"])
            + f'</h3><p class="muted">{record["rules"]} rules · {record["attempts"]} assigned attempts</p></article>'
        )
    body += "</div>"
    script = '<script>const search=document.getElementById("scenario-search");search.addEventListener("input",()=>{let n=0;document.querySelectorAll("[data-search]").forEach(card=>{card.hidden=!card.dataset.search.includes(search.value.toLowerCase().trim());if(!card.hidden)n++;});document.getElementById("search-count").textContent=n+" matching scenarios";});</script>'
    if file_sha(edition_path) != edition_hash:
        raise ValueError(
            "Export edition changed during HTML rendering; retry after export finishes"
        )
    _write(
        root / "assets/report.css",
        STYLE
        + "\n.math-panel{background:#faf9fd;border:1px solid #e4deee;border-radius:12px;padding:28px;margin:18px 0;overflow:auto;font-size:24px}.math-panel math{min-width:max-content}td math{font-size:18px}",
    )
    vendor = Path(__file__).parent / "web/vendor"
    _write(root / "assets/katex.min.js", (vendor / "katex.min.js").read_text())
    _write(root / "assets/KATEX-LICENSE.txt", (vendor / "KATEX-LICENSE.txt").read_text())
    _write(
        root / "assets/math.js",
        "document.querySelectorAll('[data-latex]').forEach(el=>{try{katex.render(el.dataset.latex,el,{output:'mathml',displayMode:el.classList.contains('math-panel'),trust:false,throwOnError:true});}catch{el.textContent=el.dataset.latex;}});",
    )
    page(root, output, "Scenario rule leaderboards", body, script)
    return {
        "scenarios": len(records),
        "rule_pages": sum(r["rules"] for r in records),
        "attempts": sum(r["attempts"] for r in records),
        "numerical_records_modified": False,
    }
