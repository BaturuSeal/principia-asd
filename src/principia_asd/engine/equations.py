"""Unit-checked, bounded equation DAGs. No Python evaluation or hidden fitted state.

Intermediate quantities are hypotheses with declared meanings, not proof of a mechanism.
Every operation and shared coefficient remains visible in the executable record.
"""

from __future__ import annotations

import ast
import copy
import math
import re

import numpy as np

from ..io import sha
from .expression import FUNCS, complexity, execute, parse

VERSION = "equation-system-v1"
# Mass, length, time, temperature. Radians are dimensionless.
UNITS = {
    "1": (0, 0, 0, 0),
    "K": (0, 0, 0, 1),
    "s": (0, 0, 1, 0),
    "s^-1": (0, 0, -1, 0),
    "rad/s": (0, 0, -1, 0),
    "Pa": (1, -1, -2, 0),
    "Pa*s": (1, -1, -1, 0),
    "m": (0, 1, 0, 0),
    "kg/m3": (1, -3, 0, 0),
    "W/m2": (1, 0, -3, 0),
    "W/m2/K4": (1, 0, -3, -4),
    "m/s": (0, 1, -1, 0),
    "N": (1, 1, -2, 0),
}
ZERO = UNITS["1"]

# Add electrical current, amount of substance and an explicitly uncalibrated
# fluorescence channel as independent dimensions. Existing SI meanings do not change.
UNITS = {k: (*v, 0, 0, 0) for k, v in UNITS.items()}
UNITS.update(
    {
        "W": (1, 2, -3, 0, 0, 0, 0),
        "W/K": (1, 2, -3, -1, 0, 0, 0),
        "J/K": (1, 2, -2, -1, 0, 0, 0),
        "N*m": (1, 2, -2, 0, 0, 0, 0),
        "V": (1, 2, -3, 0, -1, 0, 0),
        "A": (0, 0, 0, 0, 1, 0, 0),
        "K/s": (0, 0, -1, 1, 0, 0, 0),
        "kg/m2/s": (1, -2, -1, 0, 0, 0, 0),
        "mol/m2/s": (0, -2, -1, 0, 0, 1, 0),
        "mol/m3": (0, -3, 0, 0, 0, 1, 0),
        "a.u.": (0, 0, 0, 0, 0, 0, 1),
        "a.u./s": (0, 0, -1, 0, 0, 0, 1),
        "a.u./s2": (0, 0, -2, 0, 0, 0, 1),
    }
)
ZERO = UNITS["1"]


def dimension(unit):
    if unit not in UNITS:
        raise ValueError(f"Unsupported or unaudited unit: {unit!r}; convert to registered SI units")
    return UNITS[unit]


def _combine(a, b, sign=1):
    return tuple(x + sign * y for x, y in zip(a, b, strict=True))


def infer(node, names):
    if isinstance(node, ast.Name):
        return names[node.id]
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
            raise ValueError("Equation systems accept numeric quantities only")
        # Coefficients and dimensional conversion constants must be explicit records.
        if node.value not in (0, 1, 2, 3, 4, 6):
            raise ValueError("Move numeric coefficients to a sourced constant or fitted parameter")
        return ZERO
    if isinstance(node, ast.UnaryOp):
        return infer(node.operand, names)
    if isinstance(node, ast.Compare):
        if infer(node.left, names) != infer(node.comparators[0], names):
            raise ValueError("Comparison has incompatible units")
        return ZERO
    if isinstance(node, ast.BinOp):
        a, b = infer(node.left, names), infer(node.right, names)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            if a != b:
                raise ValueError("Addition/subtraction has incompatible units")
            return a
        if isinstance(node.op, ast.Mult):
            return _combine(a, b)
        if isinstance(node.op, ast.Div):
            return _combine(a, b, -1)
        if isinstance(node.op, ast.Pow):
            if b != ZERO:
                raise ValueError("Exponent must be dimensionless")
            if isinstance(node.right, ast.Constant):
                return tuple(x * node.right.value for x in a)
            if a != ZERO:
                raise ValueError("A variable exponent requires a dimensionless base")
            return ZERO
    if isinstance(node, ast.Call):
        args = [infer(a, names) for a in node.args]
        name = node.func.id
        if name in {"exp", "log", "log1p", "sin", "cos", "tanh"}:
            if args[0] != ZERO:
                raise ValueError(f"{name} requires a dimensionless argument")
            return ZERO
        if name == "sqrt":
            return tuple(x / 2 for x in args[0])
        if name == "abs":
            return args[0]
        if name == "where":
            if args[0] != ZERO or args[1] != args[2]:
                raise ValueError("Conditional branches have incompatible units")
            return args[1]
        if name in {"minimum", "maximum"}:
            if args[0] != args[1]:
                raise ValueError("Extrema have incompatible units")
            return args[0]
    raise ValueError("Unsupported dimensional operation")


def validate(system, task):
    """Validate an ordered acyclic graph, its units, scope and all learned state."""
    if system.get("version") != VERSION:
        raise ValueError("Unsupported equation-system version")
    if not system.get("name") or not system.get("assumptions"):
        raise ValueError("An equation system needs a name and explicit assumptions")
    nodes = system.get("nodes", [])
    parameters, constants = system.get("parameters", {}), system.get("constants", {})
    if not 1 <= len(nodes) <= 24 or len(parameters) > 8 or len(constants) > 16:
        raise ValueError("Equation-system capacity exceeded")
    units = task.get("quantity_units", {})
    names = {k: dimension(units.get(k)) for k in task["inputs"]}
    dimension(units.get(task["output"]))
    dependencies = {}
    all_ids = set(names)
    # A model-provided citation string cannot turn a learned number into a constant.
    approved_constants = {(3.141592653589793, "1"), (5.670374419e-8, "W/m2/K4")}
    for template in task.get("equation_templates", []):
        approved_constants.update(
            (v["value"], v["unit"]) for v in template.get("constants", {}).values()
        )
    for mapping, kind in [(parameters, "parameter"), (constants, "constant")]:
        for name, record in mapping.items():
            if (
                not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name)
                or name in all_ids
                or name in FUNCS
                or name == task["output"]
            ):
                raise ValueError("Duplicate, target-alias or prohibited quantity: " + name)
            if not record.get("meaning"):
                raise ValueError("Every quantity needs a meaning")
            names[name] = dimension(record.get("unit"))
            all_ids.add(name)
            value = record.get("initial") if kind == "parameter" else record.get("value")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError("Invalid quantity value")
            if kind == "parameter":
                bounds = record.get("bounds", [])
                if (
                    len(bounds) != 2
                    or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in bounds)
                    or not bounds[0] < bounds[1]
                    or not bounds[0] <= value <= bounds[1]
                ):
                    raise ValueError("Finite, ordered parameter bounds are required")
            elif not record.get("source"):
                raise ValueError("Fixed constants require a source")
            elif (value, record["unit"]) not in approved_constants:
                raise ValueError(
                    "Fixed constant is not in the task's audited library; represent it as a fitted parameter"
                )
    operations = 0
    for node in nodes:
        name = node["id"]
        if (
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name)
            or name in all_ids
            or name in FUNCS
            or name == task["output"]
        ):
            raise ValueError("Duplicate, target-alias or prohibited intermediate: " + name)
        if not node.get("meaning"):
            raise ValueError("Intermediate quantities require a scientific meaning")
        tree = parse(node["expression"], list(names))
        if infer(tree.body, names) != dimension(node["unit"]):
            raise ValueError("Declared unit does not match equation: " + name)
        dependencies[name] = {
            n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id in names
        }
        names[name] = dimension(node["unit"])
        all_ids.add(name)
        operations += complexity(node["expression"])["weighted_operator_count"]
    if operations > 192:
        raise ValueError("Total operation budget exceeded")
    output = system.get("output")
    if output not in dependencies or names[output] != dimension(units[task["output"]]):
        raise ValueError("Output must name a computed quantity with the target unit")
    used = set()

    def visit(name):
        if name in used:
            return
        used.add(name)
        for other in dependencies.get(name, ()):
            visit(other)

    visit(output)
    if (set(dependencies) | set(parameters) | set(constants)) - used:
        raise ValueError("Unused equations or coefficients would disguise complexity")
    return {
        "dependencies": {k: sorted(v) for k, v in dependencies.items()},
        "operations": operations,
    }


def execute_system(system, columns, parameters, task, *, intermediates=False, checked=False):
    if not checked:
        validate(system, task)
    if set(parameters) != set(system["parameters"]):
        raise ValueError("Fitted parameter coverage mismatch")
    values = {k: float(v["value"]) for k, v in system.get("constants", {}).items()}
    for k, v in parameters.items():
        low, high = system["parameters"][k]["bounds"]
        if not np.isfinite(v) or not low <= v <= high:
            raise ValueError("Parameter outside its declared domain")
        values[k] = float(v)
    n = len(next(iter(columns.values())))
    scope = {k: np.asarray(columns[k], float) for k in task["inputs"]}
    computed = {}
    for node in system["nodes"]:
        result = execute(node["expression"], scope, values, n)
        if not np.isfinite(result).all():
            raise ValueError("Nonfinite intermediate quantity: " + node["id"])
        scope[node["id"]] = result
        computed[node["id"]] = result
    return computed if intermediates else computed[system["output"]]


def expanded_expression(system):
    expressions = {}

    class Expand(ast.NodeTransformer):
        def visit_Name(self, node):
            return copy.deepcopy(expressions.get(node.id, node))

    for node in system["nodes"]:
        tree = Expand().visit(ast.parse(node["expression"], mode="eval").body)
        if len(list(ast.walk(tree))) > 12000:
            raise ValueError("Expanded equation budget exceeded")
        expressions[node["id"]] = tree
    return ast.unparse(expressions[system["output"]])


def system_complexity(system, parameters):
    expanded = expanded_expression(system)
    result = complexity(expanded, parameters)
    result.update(
        dag_weighted_operator_count=sum(
            complexity(n["expression"])["weighted_operator_count"] for n in system["nodes"]
        ),
        intermediate_quantities=len(system["nodes"]) - 1,
        shared_parameter_count=len(parameters),
        fixed_constants=len(system.get("constants", {})),
        learned_state_bytes=len(str(parameters).encode()),
        preprocessing="Source preparation is recorded in the task; all fitted state is the shared parameter vector",
        scope="Expanded operation count; DAG operations also reported, shared parameters counted once",
    )
    return result


def system_identity(system):
    return sha(system)


def mathematical_signature(system):
    """Conservative executable-structure identity, ignoring names and initial guesses.

    This detects alpha-renaming and factoring into different intermediate nodes,
    not general algebraic equivalence. Boundaries and coefficient units remain part
    of the scientific hypothesis. All raw proposals remain in request receipts.
    """
    mapping = {}
    constants = system.get("constants", {})

    class Canonical(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id in constants:
                record = constants[node.id]
                return ast.Name(
                    id="fixed_" + sha([record["value"], record["unit"]]), ctx=ast.Load()
                )
            if node.id in system["parameters"]:
                mapping.setdefault(node.id, "p" + str(len(mapping)))
                return ast.Name(id=mapping[node.id], ctx=ast.Load())
            return node

    tree = Canonical().visit(ast.parse(expanded_expression(system), mode="eval"))
    return sha(
        {
            "expression": ast.dump(tree, include_attributes=False),
            "parameters": {
                v: {k: system["parameters"][name][k] for k in ("unit", "bounds")}
                for name, v in mapping.items()
            },
            "output_unit": next(n["unit"] for n in system["nodes"] if n["id"] == system["output"]),
        }
    )
