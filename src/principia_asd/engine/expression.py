"""Bounded numerical AST interpreter. Never evaluates Python or resolves attributes."""

from __future__ import annotations

import ast
import math

import numpy as np

OPS = {
    ast.Add: np.add,
    ast.Sub: np.subtract,
    ast.Mult: np.multiply,
    ast.Div: np.divide,
    ast.Pow: np.power,
}
FUNCS = {
    "abs": (np.abs, 1),
    "sqrt": (np.sqrt, 1),
    "log": (np.log, 1),
    "log1p": (np.log1p, 1),
    "exp": (np.exp, 1),
    "sin": (np.sin, 1),
    "cos": (np.cos, 1),
    "tanh": (np.tanh, 1),
    "minimum": (np.minimum, 2),
    "maximum": (np.maximum, 2),
    "where": (np.where, 3),
}
COMPS = {
    ast.Lt: np.less,
    ast.LtE: np.less_equal,
    ast.Gt: np.greater,
    ast.GtE: np.greater_equal,
    ast.Eq: np.equal,
    ast.NotEq: np.not_equal,
}


def parse(expression: str, inputs: list[str], parameters: list[str] = (), max_nodes=160):
    if not isinstance(expression, str) or len(expression) > 12000:
        raise ValueError("Expression is too large")
    tree = ast.parse(expression, mode="eval")
    nodes = list(ast.walk(tree))
    if len(nodes) > max_nodes:
        raise ValueError("Expression exceeds the node budget")
    names = set(inputs) | set(parameters)
    if names & set(FUNCS):
        raise ValueError("Input names collide with registered operators")

    def check(n, depth=0):
        if depth > 24:
            raise ValueError("Expression is too deep")
        if isinstance(n, ast.Constant):
            if not isinstance(n.value, (int, float, str)) or isinstance(n.value, bool):
                raise ValueError("Invalid constant")
            if isinstance(n.value, (int, float)) and (
                not math.isfinite(n.value) or abs(n.value) > 1e100
            ):
                raise ValueError("Invalid numeric literal")
        elif isinstance(n, ast.Name):
            if n.id not in names or n.id.startswith("_"):
                raise ValueError("Undeclared input or parameter: " + n.id)
        elif isinstance(n, ast.BinOp) and type(n.op) in OPS:
            if (
                isinstance(n.op, ast.Pow)
                and isinstance(n.right, ast.Constant)
                and (not isinstance(n.right.value, (int, float)) or abs(n.right.value) > 8)
            ):
                raise ValueError("Exponent outside [-8,8]")
            check(n.left, depth + 1)
            check(n.right, depth + 1)
        elif isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            check(n.operand, depth + 1)
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS:
            if n.keywords or len(n.args) != FUNCS[n.func.id][1]:
                raise ValueError("Invalid operator arguments")
            for x in n.args:
                check(x, depth + 1)
        elif isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in COMPS:
            check(n.left, depth + 1)
            check(n.comparators[0], depth + 1)
        else:
            raise ValueError("Unsupported expression construct: " + type(n).__name__)

    check(tree.body)
    return tree


def execute(expression: str, columns: dict, parameters: dict | None = None, n: int | None = None):
    params = parameters or {}
    tree = parse(expression, list(columns), list(params))
    n = n if n is not None else len(next(iter(columns.values())))

    def value(t):
        if isinstance(t, ast.Constant):
            # Avoid Python big-integer/object arithmetic inside NumPy ufuncs.
            return float(t.value) if isinstance(t.value, (int, float)) else t.value
        if isinstance(t, ast.Name):
            return params[t.id] if t.id in params else columns[t.id]
        if isinstance(t, ast.BinOp):
            return OPS[type(t.op)](value(t.left), value(t.right))
        if isinstance(t, ast.UnaryOp):
            return -value(t.operand) if isinstance(t.op, ast.USub) else value(t.operand)
        if isinstance(t, ast.Call):
            return FUNCS[t.func.id][0](*[value(a) for a in t.args])
        if isinstance(t, ast.Compare):
            return COMPS[type(t.ops[0])](value(t.left), value(t.comparators[0]))
        raise ValueError("Invalid AST")

    with np.errstate(all="ignore"):
        result = np.asarray(value(tree.body), dtype=float)
    if result.ndim == 0:
        result = np.full(n, float(result))
    if result.shape != (n,):
        raise ValueError("Prediction shape does not match the cohort")
    return result


def expanded(expression: str, parameters: dict) -> str:
    tree = ast.parse(expression, mode="eval")

    class Expand(ast.NodeTransformer):
        def visit_Name(self, node):
            return (
                ast.copy_location(ast.Constant(float(parameters[node.id])), node)
                if node.id in parameters
                else node
            )

    return ast.unparse(Expand().visit(tree))


def structural_key(expression):
    """Canonicalize commutative operations without asserting algebraic equivalence."""

    def key(node):
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mult)):
            return (
                type(node.op).__name__,
                tuple(sorted([key(node.left), key(node.right)], key=repr)),
            )
        return (
            type(node).__name__,
            tuple(
                (
                    name,
                    key(value)
                    if isinstance(value, ast.AST)
                    else tuple(key(v) for v in value)
                    if isinstance(value, list)
                    else repr(value),
                )
                for name, value in ast.iter_fields(node)
            ),
        )

    return repr(key(ast.parse(expression, mode="eval")))


def complexity(expression: str, parameters=None):
    tree = ast.parse(expression, mode="eval")
    nodes = list(ast.walk(tree))
    weighted = sum(
        3
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", "") in {"exp", "log", "log1p", "sin", "cos"}
        else 1
        for n in nodes
        if isinstance(n, (ast.BinOp, ast.UnaryOp, ast.Call, ast.Compare))
    )
    return {
        "weighted_operator_count": weighted,
        "free_parameters": len(parameters or {}),
        "numeric_literal_count": sum(
            isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) for n in nodes
        ),
        "literal_state_bytes": sum(
            len(repr(n.value).encode()) for n in nodes if isinstance(n, ast.Constant)
        ),
        "nodes": len(nodes),
        "expression_bytes": len(expression.encode()),
        "learned_state_bytes": len(str(parameters or {}).encode()),
        "expanded_expression": expanded(expression, parameters or {}),
        "preprocessing": "none unless explicitly expanded in the expression",
    }
