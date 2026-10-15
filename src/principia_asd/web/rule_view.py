"""Lossless symbolic display; never changes a fitted rule or its numerical score."""

from __future__ import annotations

import ast
import hashlib

from ..catalog.presentation import variable
from ..engine.expression import parse


def rule_view(card, task):
    inputs = card.get("inputs", task.get("inputs", []))
    symbols = {k: f"x_{{{i + 1}}}" for i, k in enumerate(inputs)}
    parameters = []
    bindings = {}
    symbol_counts = {}

    def bind(key, value, description, prefix="\\theta"):
        symbol_counts[prefix] = symbol_counts.get(prefix, 0) + 1
        symbol = f"{prefix}_{{{symbol_counts[prefix]}}}"
        parameters.append(
            {"symbol": symbol, "key": key, "value": value, "description": description}
        )
        bindings[key] = symbol
        return symbol

    program = card.get("program", {})
    values = program.get("execution_values", card.get("parameters", {}))
    states = {f"bound{i}": r for i, (_, r) in enumerate(sorted(program.get("states", {}).items()))}
    for name, value in values.items():
        kind = states.get(name, {}).get("kind", "fitted coefficient").replace("_", " ")
        source = states.get(name, {}).get("value_path", [])
        meaning = f"{kind.capitalize()}" + (
            ": " + " / ".join(map(str, source))
            if source
            else f" ({name}); conditional on this formula and the training data"
        )
        bind(name, value, meaning)

    def render(node, parent=0):
        if isinstance(node, ast.Name):
            return symbols.get(node.id, bindings.get(node.id, ""))
        if isinstance(node, ast.Constant):
            if node.value in (0, 1, 2) and isinstance(node.value, int):
                return str(node.value)
            key = "literal:" + repr(node.value)
            return bindings.get(key) or bind(
                key,
                node.value,
                "Recorded numeric constant; its original fixed or learned provenance is not inferred",
                "c",
            )
        if isinstance(node, ast.UnaryOp):
            return ("-" if isinstance(node.op, ast.USub) else "+") + render(node.operand, 3)
        if isinstance(node, ast.Compare):
            ops = {
                ast.Lt: "<",
                ast.LtE: r"\leq",
                ast.Gt: ">",
                ast.GtE: r"\geq",
                ast.Eq: "=",
                ast.NotEq: r"\ne",
            }
            return (
                render(node.left) + " " + ops[type(node.ops[0])] + " " + render(node.comparators[0])
            )
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Div):
                return r"\frac{" + render(node.left) + "}{" + render(node.right) + "}"
            if isinstance(node.op, ast.Pow):
                return "{" + render(node.left, 4) + "}^{" + render(node.right) + "}"
            level = 2 if isinstance(node.op, ast.Mult) else 1
            op = {ast.Mult: r"\, ", ast.Add: " + ", ast.Sub: " - "}[type(node.op)]
            # Parenthesize same-level right subtraction and composite multiplicands.
            text = (
                render(node.left, level)
                + op
                + render(node.right, level + (1 if isinstance(node.op, ast.Sub) else 0))
            )
            return r"\left(" + text + r"\right)" if level < parent else text
        if isinstance(node, ast.Call):
            args = [render(a) for a in node.args]
            name = node.func.id
            if name == "sqrt":
                return r"\sqrt{" + args[0] + "}"
            if name == "abs":
                return r"\left|" + args[0] + r"\right|"
            if name == "log1p":
                return r"\log\left(1 + " + args[0] + r"\right)"
            if name == "where":
                return (
                    r"\begin{cases}"
                    + args[1]
                    + " & "
                    + args[0]
                    + r"\\"
                    + args[2]
                    + r" & \text{otherwise}\end{cases}"
                )
            op = {"minimum": "min", "maximum": "max"}.get(name, name)
            return "\\" + op + r"\left(" + ", ".join(args) + r"\right)"
        raise ValueError("Unsupported mathematical display")

    conditions = []
    expanded_latex = None
    if card.get("representation") == "tree":
        tree = card["tree"]

        def branch(i, path):
            if tree["left"][i] == -1:
                symbol = bind(
                    f"leaf-{i}",
                    tree["value"][i],
                    "Predicted output in this terminal region",
                    r"\mu",
                )
                conditions.append(
                    {"symbol": symbol, "condition": r"\;\land\;".join(path) or r"\text{all inputs}"}
                )
                return
            threshold = bind(
                f"threshold-{i}",
                tree["threshold"][i],
                "Split threshold for " + tree["features"][tree["feature"][i]],
                r"\tau",
            )
            x = symbols[tree["features"][tree["feature"][i]]]
            branch(tree["left"][i], path + [x + r"\leq " + threshold])
            branch(tree["right"][i], path + [x + "> " + threshold])

        branch(0, [])
        expanded_latex = (
            r"\hat{y} = \begin{cases}"
            + r"\\".join(x["symbol"] + " & " + x["condition"] for x in conditions)
            + r"\end{cases}"
        )
        expression = (
            r"\sum_{j=1}^{"
            + str(len(conditions))
            + r"} \mu_j \mathbf{1}_{\{\boldsymbol{x} \in R_j\}}"
        )
        family = "Piecewise"
        interpretation = "The decision tree partitions the input domain at learned thresholds. Each terminal region returns its fitted constant response. The region definitions below expand every terminal path; boundaries need not be smooth."
    else:
        expr = program.get("expression", card.get("expression", ""))
        tree = parse(expr, inputs, list(values)).body
        expression = render(tree)
        names = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)}
        operators = {type(n.op) for n in ast.walk(tree) if isinstance(n, ast.BinOp)}

        def degree(node):
            if isinstance(node, ast.Name):
                return int(node.id in inputs)
            if isinstance(node, ast.Constant):
                return 0
            if isinstance(node, ast.UnaryOp):
                return degree(node.operand)
            if isinstance(node, ast.BinOp):
                a, b = degree(node.left), degree(node.right)
                if a is None or b is None:
                    return None
                if isinstance(node.op, (ast.Add, ast.Sub)):
                    return max(a, b)
                if isinstance(node.op, ast.Mult):
                    return a + b
                if isinstance(node.op, ast.Div) and b == 0:
                    return a
            return None

        family = (
            "Constant"
            if not any(isinstance(n, ast.Name) and n.id in inputs for n in ast.walk(tree))
            else "Piecewise"
            if "where" in names
            else "Exponential"
            if "exp" in names
            else "Logarithmic"
            if names & {"log", "log1p"}
            else "Oscillatory"
            if names & {"sin", "cos"}
            else "Rational"
            if ast.Div in operators
            else "Polynomial"
            if ast.Pow in operators
            else "Affine"
            if degree(tree) == 1
            else "Algebraic"
        )
        interpretation = {
            "Constant": "A constant response provides a reference independent of the input measurements.",
            "Piecewise": "The expression switches between response branches at its declared condition. Each branch and boundary is part of the rule.",
            "Exponential": "The expression uses exponential response terms, which can represent rapid growth or decay within the observed domain.",
            "Logarithmic": "Logarithmic terms express changes on a compressed response scale. Their arguments must stay within the mathematical domain.",
            "Oscillatory": "Trigonometric terms encode periodic variation. Their presence does not establish an underlying oscillator.",
            "Rational": "The rule combines measurements through ratios. Denominators determine important domain restrictions and sensitivity near zero.",
            "Polynomial": "Powers and products encode curvature or interactions among the observed inputs.",
            "Affine": "An intercept and weighted input contributions describe an additive response. Each coefficient is a conditional fitted sensitivity within the sampled data; it is not a causal effect.",
            "Algebraic": "The rule combines the displayed measurements and fitted coefficients through the explicit arithmetic operations shown.",
        }[family]
    if card.get("representation") != "tree" and family == "Affine":

        def terms(n):
            return (
                terms(n.left) + terms(n.right)
                if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub))
                else [n]
            )

        roles = {}
        for term in terms(tree):
            if isinstance(term, ast.Name) and term.id in values:
                roles[term.id] = (
                    "Additive intercept; output units. Its value is conditional on the other terms."
                )
            if isinstance(term, ast.BinOp) and isinstance(term.op, ast.Mult):
                for coefficient, measurement in [(term.left, term.right), (term.right, term.left)]:
                    if (
                        isinstance(coefficient, ast.Name)
                        and coefficient.id in values
                        and isinstance(measurement, ast.Name)
                        and measurement.id in inputs
                    ):
                        roles[coefficient.id] = (
                            "Weight on "
                            + variable(task, measurement.id)["label"].lower()
                            + "; output units per input unit. This is an association, not a causal effect."
                        )
        for parameter in parameters:
            if parameter["key"] in roles and parameter["key"] not in states:
                parameter["description"] = roles[parameter["key"]]
    output = variable(
        task | {"output": card.get("output", task.get("output", "target"))},
        card.get("output", task.get("output", "target")),
    )
    identity = card.get("rule_id", card.get("candidate_id", card.get("rule_sha256", repr(card))))
    code = hashlib.sha256(identity.encode()).hexdigest()[:8].upper()
    name = f"{family} {output['label'][:64].rstrip()} · {code}"
    return {
        "regions": conditions,
        "expanded_latex": expanded_latex,
        "name": name,
        "latex": r"\hat{y} = " + expression,
        "parameters": parameters,
        "variables": [{"symbol": symbols[k], **variable(task, k)} for k in inputs]
        + [{"symbol": r"\hat{y}", **output}],
        "interpretation": interpretation,
        "interpretation_scope": "Structural reading of the executable formula, not an independently validated mechanism. Test performance alone does not establish causality, novelty or practical impact.",
        "formula_scope": "Symbolic names preserve full-precision execution values. Rounded table values are for reading only; use the downloaded record for reproduction. Constants retain their recorded provenance.",
        "source_identity": identity,
    }
