from principia_asd.contracts.schema import validate_contract


def test_contract_requires_blind_test_and_stability():
    assert validate_contract({"task_id": "t"})
    assert not validate_contract(
        {
            "task_id": "t",
            "scenario_id": "s",
            "inputs": ["x"],
            "output": "y",
            "split": {
                "train": "public/train.csv.gz",
                "dev": "public/dev.csv.gz",
                "test": "public/test_inputs.csv.gz",
            },
            "metric": {"primary": "mae"},
            "stability": {"domain": "finite"},
            "test_exposure": "private-test",
        }
    )


def test_malformed_contract_returns_validation_errors():
    assert validate_contract({"inputs": [{}], "split": {"train": [], "dev": [], "test": []}})
