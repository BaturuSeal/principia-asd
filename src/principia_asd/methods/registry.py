"""Executable methods and explicitly unavailable integrations. Names are not evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass

MODELS = (
    "deepseek-ai/DeepSeek-V4-Flash",
    "zai-org/GLM-5.3",
    "Qwen/Qwen3.8-27B",
    "Pro/moonshotai/Kimi-K2.6",
)
DEFAULT_ROLES = {
    "planner": MODELS[1],
    "coder": MODELS[0],
    "critic": MODELS[2],
    "reporter": MODELS[3],
}


@dataclass(frozen=True)
class MethodSpec:
    method_id: str
    name: str
    tier: str
    mechanism: str
    available: bool = True
    needs_llm: bool = False
    source_url: str | None = None
    reason: str | None = None
    version: str = "1.0.0rc2"

    def as_dict(self):
        return asdict(self)


METHODS = {}


def add(id, name, tier, mechanism, **kw):
    METHODS[id] = MethodSpec(id, name, tier, mechanism, **kw)


add("mean_control", "Mean predictor", "reference", "One training-set mean, frozen before test")
add(
    "linear_control",
    "Linear regression",
    "reference",
    "Multivariable least-squares on train; all coefficients reported",
)
add(
    "polynomial_control",
    "Polynomial regression",
    "reference",
    "Degree-two interactions; train fitting with dev selection",
)
add(
    "tree_control",
    "Decision tree",
    "reference",
    "Depth selected on dev, complete tree exported; predictive reference",
)
add(
    "symbolic_control",
    "Fixed symbolic search",
    "classical",
    "Bounded term composition and train fitting; group-aware dev selection",
)
add(
    "direct",
    "Direct proposal",
    "llm",
    "One model response; one numeric expression; local parameter fitting without repair",
    needs_llm=True,
)
for suffix, model in zip(["deepseek", "glm", "qwen", "kimi"], MODELS, strict=True):
    add(
        "direct_" + suffix,
        "Direct · "
        + {"deepseek": "DeepSeek", "glm": "GLM", "qwen": "Qwen", "kimi": "Kimi"}[suffix],
        "llm",
        "One response from " + model + "; no model repair",
        needs_llm=True,
    )
add(
    "best_of_n",
    "Best of 3",
    "llm",
    "Three independent proposals; same training fit; development selection",
    needs_llm=True,
)
add(
    "feedback_refinement",
    "Feedback refinement",
    "llm",
    "Three proposal/fit/diagnostic rounds with real residual feedback",
    needs_llm=True,
)
add(
    "tool_agent",
    "Tool-using investigator",
    "llm",
    "Model-selected inspect, fit and search actions executed on permitted train/dev data",
    needs_llm=True,
)
add(
    "principia_engine",
    "Adaptive Primitive Search (APS)",
    "integrated",
    "Multiple model roles revise a bounded primitive library using executed train fits and dev diagnostics",
    needs_llm=True,
)
add(
    "principia_engine_explicit",
    "Adaptive Primitive Search · explicit-state development",
    "engineering",
    "Choose protocol v2 or original v1. Two planner/coder/critic rounds with source-bound fitted state, three frozen nomination slots and checkpoint recovery. Train/dev only; scientific review and public ranking remain unavailable.",
    needs_llm=True,
    version="principia-explicit-state-interactive-v2-dev",
)
add(
    "agent_laboratory",
    "Agent Laboratory · Principia adaptation",
    "adapted_asd",
    "Research and planning handoffs, executed expression program, experimental critique, structural revision and evidence-linked reporting; local context only",
    needs_llm=True,
    version="agent-laboratory-adaptation-v2",
    source_url="https://github.com/SamuelSchmidgall/AgentLaboratory/tree/d9017d90e329112d2a80b7712f37ee9094d2cd27",
)
add(
    "agent_laboratory_explicit",
    "Agent Laboratory · explicit-state development",
    "engineering",
    "Six research/planning/coding/critique/reporting handoffs and two model-proposed experiments. Frozen train/dev inputs, explicit fitted state and checkpoint recovery; no private-test assessment or public ranking. The live pilot retains incomplete and truncated-report outcomes.",
    needs_llm=True,
    version="agent-laboratory-explicit-state-v1-dev",
    source_url="https://github.com/SamuelSchmidgall/AgentLaboratory/tree/d9017d90e329112d2a80b7712f37ee9094d2cd27",
)
add(
    "data_to_paper",
    "data-to-paper · Principia adaptation",
    "adapted_asd",
    "Contract-checked analysis plan, executed statistical program, methodological review and a report with computed numeric references; controlled local context",
    needs_llm=True,
    version="data-to-paper-adaptation-v2",
    source_url="https://github.com/Technion-Kishony-lab/data-to-paper/tree/81df14c4b9600466e645c3b2b336cc54daa3df3a",
)
add(
    "data_to_paper_explicit",
    "data-to-paper · explicit-state development",
    "engineering",
    "Version 2: guarded plan, executed analysis, post-freeze statistics, critique and computed-reference report. Train/dev only; no private-test assessment or public ranking. Live pilot: 2 complete, 4 report-incomplete and 2 unsupported; partial analyses remain visible.",
    needs_llm=True,
    version="data-to-paper-explicit-state-v2-dev",
    source_url="https://github.com/Technion-Kishony-lab/data-to-paper/tree/81df14c4b9600466e645c3b2b336cc54daa3df3a",
)
add(
    "asta_autodiscovery",
    "Asta AutoDiscovery · Principia adaptation",
    "adapted_asd",
    "Branching hypothesis search, progressive widening, UCT selection, executed programs and sampled prior/posterior Beta-belief rewards; controlled local context",
    needs_llm=True,
    version="asta-autodiscovery-adaptation-v2",
    source_url="https://github.com/allenai/asta-autodiscovery/tree/effa4be80f94e234d3d926f4f24b6aa6064d10e7",
)
add(
    "agentrxiv",
    "AgentRxiv · Principia adaptation",
    "adapted_asd",
    "Two isolated laboratories publish completed reports; a private archive supplies a peer formula for an executed, revised follow-up",
    needs_llm=True,
    version="agentrxiv-adaptation-v1",
    source_url="https://arxiv.org/abs/2503.18102v1",
)
for id, name, url in [
    ("pysr", "PySR", "https://github.com/MilesCranmer/PySR"),
    ("sindy", "SINDy", "https://github.com/dynamicslab/pysindy"),
    ("llm_sr", "LLM-SR", "https://github.com/deep-symbolic-mathematics/LLM-SR"),
    ("sr_llm", "SR-LLM", None),
    (
        "funsearch",
        "FunSearch-style program evolution",
        "https://github.com/google-deepmind/funsearch",
    ),
    ("ai_scientist_v2", "AI Scientist-v2", "https://github.com/SakanaAI/AI-Scientist-v2"),
    ("internagent", "InternAgent", "https://github.com/InternScience/InternAgent"),
]:
    add(
        id,
        name,
        "integration_pending",
        "Upstream method must pass distinct algorithm conformance before use",
        available=False,
        source_url=url,
        reason="Adapter not verified. Earlier shared-formula preview rows are withdrawn from ranking.",
    )


def get_method(method_id):
    if method_id not in METHODS:
        raise ValueError("Unknown method: " + method_id)
    return METHODS[method_id]
