from principia_asd.evaluate.metrics import evaluate_rule, pareto_front


def contract():
    return {
        "task_id": "t",
        "inputs": ["x"],
        "output": "target",
        "split": {"train": [], "dev": [], "test": []},
        "metric": {"primary": "mae"},
        "stability": {"domain": "finite", "relative_noise": 0.01},
        "test_exposure": "private-test",
    }


def test_perfect_rule_and_complexity():
    rows = [{"x": 1.0}, {"x": 2.0}]
    result = evaluate_rule({"expression": "2*x", "parameters": {}}, rows, [2.0, 4.0], contract())
    assert result["accuracy"]["mae"] == 0.0
    assert result["coverage"]["fraction"] == 1.0
    assert result["simplicity"]["weighted_operator_count"] == 1


def test_pareto_keeps_accuracy_simplicity_tradeoff():
    rows = [
        {
            "rule_id": "a",
            "status": "complete",
            "accuracy": {"primary_error": 1},
            "coverage": {"fraction": 1},
            "simplicity": {"weighted_operator_count": 1, "free_parameters": 1},
            "stability": {"mean_relative_sensitivity": 1},
        },
        {
            "rule_id": "b",
            "status": "complete",
            "accuracy": {"primary_error": 0.5},
            "coverage": {"fraction": 1},
            "simplicity": {"weighted_operator_count": 3, "free_parameters": 1},
            "stability": {"mean_relative_sensitivity": 1},
        },
    ]
    assert {x["rule_id"] for x in pareto_front(rows)} == {"a", "b"}
