"""Opt-in development contract for explicit scalar state. Not a v5 scoring change.

Only the trusted host supplies source artifacts. A model may reference their IDs;
it cannot certify a fitted value by supplying a label or a provenance string.
"""

from __future__ import annotations

import ast
import copy
import math

from ..io import canonical, sha
from .expression import FUNCS, complexity, execute, parse

POLICY = "explicit-scalar-lineage-v1-dev"
KINDS = {"train_fitted", "train_statistic", "fixed_scientific"}


def scalar(value):
    if type(value) not in {int, float} or not math.isfinite(value) or abs(value) > 1e100:
        raise ValueError("State must be a finite bounded scalar, never an opaque array or encoder")
    return float(value)


class StateRegistry:
    """Host-owned receipts; their scientific meaning still requires contract review."""

    def __init__(self, artifacts):
        self.artifacts = copy.deepcopy(artifacts)
        if any(sha(artifact) != digest for digest, artifact in self.artifacts.items()):
            raise ValueError("Source artifact hash mismatch")
        self.records = {}

    def register(self, artifact_sha256, path, kind):
        if kind not in KINDS or not isinstance(path, list) or not path:
            raise ValueError("Explicit state kind and source value path required")
        source = self.artifacts[artifact_sha256]
        if sha(source) != artifact_sha256:
            raise ValueError("Source artifact mutation")
        if source.get("status") != "complete":
            raise ValueError("Only completed host computations or reviewed constants may bind")
        expected = "fixed" if kind == "fixed_scientific" else "train"
        if source.get("scope") != expected:
            raise ValueError("State source scope is not permitted; dev/test state cannot bind")
        if source.get("kind") != kind:
            raise ValueError("State kind must agree with the trusted source receipt")
        value = source
        for key in path:
            if type(key) not in {str, int}:
                raise ValueError("Invalid source value path")
            value = value[key]
        record = {
            "value": scalar(value),
            "kind": kind,
            "artifact_sha256": artifact_sha256,
            "value_path": copy.deepcopy(path),
        }
        digest = sha(record)
        self.records[digest] = record
        return digest

    def resolve(self, digest):
        record = self.records[digest]
        if sha(record) != digest:
            raise ValueError("State binding mutation")
        if self.register(record["artifact_sha256"], record["value_path"], record["kind"]) != digest:
            raise ValueError("Source value mutation")
        return copy.deepcopy(record)


def compile_program(expression, inputs, parameters, bindings, registry, *, kernels=None):
    """Expand all kernels, reject unbound literal state, count shared scalar identities.

    Even structural numeric constants require a host fixed-constant binding. This
    deliberately strict development contract does not reinterpret old submissions.
    """
    kernels = dict(kernels or {})
    parameters = {k: scalar(v) for k, v in parameters.items()}
    if len(parameters) > 8 or any(not k.startswith("p") or not k[1:].isdigit() for k in parameters):
        raise ValueError("At most eight explicitly named final-stage parameters are permitted")
    groups = [set(inputs), set(parameters), set(bindings), set(kernels), set(FUNCS)]
    if len(inputs) != len(set(inputs)) or any(
        a & b for i, a in enumerate(groups) for b in groups[i + 1 :]
    ):
        raise ValueError("Inputs, operators, parameters, bindings and kernels must not collide")
    if any(not name.isidentifier() or name.startswith("_") for group in groups for name in group):
        raise ValueError("Invalid symbolic identifier")
    if len(kernels) > 24 or len(bindings) > 128:
        raise ValueError("Kernel/state capacity exceeded")

    def expand(text, ancestors=()):
        if not isinstance(text, str) or len(text) > 12000 or len(ancestors) > 24:
            raise ValueError("Kernel expansion exceeds limits")
        tree = ast.parse(text, mode="eval")

        class Expand(ast.NodeTransformer):
            def visit_Name(self, node):
                if node.id not in kernels:
                    return node
                if node.id in ancestors:
                    raise ValueError("Recursive kernel definition")
                return ast.copy_location(expand(kernels[node.id], (*ancestors, node.id)), node)

        tree = Expand().visit(tree)
        if len(list(ast.walk(tree))) > 160:
            raise ValueError("Expanded kernel node budget exceeded")
        return tree.body

    tree = expand(expression)
    text = ast.unparse(tree)
    parse(text, inputs + list(bindings), list(parameters))
    if any(isinstance(n, ast.Constant) for n in ast.walk(tree)):
        raise ValueError("Unbound literal state: use a trusted fixed or train-state binding")
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    if set(parameters) - used or set(bindings) - used:
        raise ValueError("Unused parameters or bindings obscure learned-state accounting")
    states = {digest: registry.resolve(digest) for digest in set(bindings.values())}
    by_id = {digest: f"bound{i}" for i, digest in enumerate(sorted(states))}
    # Canonical internal symbols cannot depend on user kernel/binding names.
    if set(by_id.values()) & (set(inputs) | set(parameters)):
        raise ValueError("Input collides with canonical state namespace")

    class Rename(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id in bindings:
                return ast.copy_location(
                    ast.Name(id=by_id[bindings[node.id]], ctx=ast.Load()), node
                )
            return node

    final = ast.unparse(Rename().visit(tree))
    all_values = parameters | {by_id[digest]: r["value"] for digest, r in states.items()}
    simp = complexity(final, all_values)
    inherited = sum(r["kind"] == "train_fitted" for r in states.values())
    stats = sum(r["kind"] == "train_statistic" for r in states.values())
    if len(parameters) + inherited > 8:
        raise ValueError("At most eight fitted scalars across final and inherited state")
    learned = len(parameters) + inherited + stats
    simp.update(
        {
            "policy": POLICY,
            "free_parameters": len(parameters),
            "final_stage_parameters": len(parameters),
            "inherited_fitted_scalars": inherited,
            "train_statistic_scalars": stats,
            "learned_scalar_count": learned,
            "fixed_scientific_scalars": sum(
                r["kind"] == "fixed_scientific" for r in states.values()
            ),
            "learned_state_bytes": 8 * learned,
            "learned_state_encoding": "float64 values, unique state IDs; excludes provenance metadata",
            "binding_receipt_bytes": len(canonical(states)),
            "degrees_of_freedom": "not_assessed",
            "preprocessing": "Only operations expanded here; upstream measurement preprocessing remains separate",
            "ranking_authorized": False,
        }
    )
    record = {
        "policy": POLICY,
        "specification": {
            "expression": expression,
            "inputs": inputs,
            "parameters": parameters,
            "bindings": bindings,
            "kernels": kernels,
        },
        "expression": final,
        "execution_values": all_values,
        "states": states,
        "simplicity": simp,
    }
    record["sha256"] = sha(record)
    return copy.deepcopy(record)


def verify_program(record, registry):
    spec = record["specification"]
    rebuilt = compile_program(
        spec["expression"],
        spec["inputs"],
        spec["parameters"],
        spec["bindings"],
        registry,
        kernels=spec["kernels"],
    )
    if rebuilt != record:
        raise ValueError("Frozen compiled program or binding mutation")
    return rebuilt


def execute_program(record, columns, registry):
    verified = verify_program(record, registry)
    if set(columns) != set(verified["specification"]["inputs"]):
        raise ValueError("Measurement inventory mismatch")
    return execute(verified["expression"], columns, verified["execution_values"])
