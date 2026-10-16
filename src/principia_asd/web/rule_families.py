"""Conservative structural grouping, independent of method names and test scores.

Parameter alpha-renaming and whitespace are ignored. Numerical literals, shared
bindings, input identities and fixed constants are retained. No equivalence or
identical-prediction claim is inferred from a group.
"""

import ast

from ..engine.equations import mathematical_signature
from ..io import sha


def structure_id(card, task):
    parameters = card.get("parameters", {})
    mapping = {}

    def expression(text):
        class Rename(ast.NodeTransformer):
            def visit_Name(self, n):
                if n.id in parameters:
                    mapping.setdefault(n.id, f"coefficient_{len(mapping)}")
                    return ast.Name(id=mapping[n.id], ctx=ast.Load())
                return n

        return ast.dump(Rename().visit(ast.parse(text, mode="eval")), include_attributes=False)

    context = {
        "inputs": card.get("inputs", task.get("inputs")),
        "output": card.get("output", task.get("output")),
        "task": task.get("task_id"),
        "representation": card.get("representation", "expression"),
    }
    if card.get("representation") == "equation-system-v1":
        s = card["equation_system"]
        # Group the expanded mathematics; retain each interpretation in its own card.
        context["expanded_graph"] = mathematical_signature(s)
    elif card.get("representation") in {"tree", "bound_expression_v1"} or card.get("program"):
        context["full_state"] = card.get("tree", card.get("program"))
    else:
        context["expression"] = expression(card["expression"])
        context["unused_parameters"] = sorted(set(parameters) - set(mapping))
    return sha(context)
