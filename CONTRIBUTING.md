# Contributing to Principia ASD

Aim to make scientific claims easier to inspect, reproduce, and challenge. Open an issue with the scientific question or product problem before proposing a large change. Small fixes can go directly to a pull request.

## Scenarios and tasks

Provide a source citation, explicit redistribution terms, acquisition/version hashes, measurement meanings and units, and a deterministic preprocessing recipe. Distinguish measured, derived, and fitted fields. Declare the independent sampling unit and split policy; fit learned preprocessing on training data only. Keep the expanded public package below 10 MB unless a scientific reason justifies an exception.

New tasks need a frozen input–output contract and matched numerical controls. Never include target aliases, future observations, author-fitted outputs, protected targets, or credentials in the public package. Add a new versioned collection rather than modifying historical experimental inputs. Document limitations and rejected cases as carefully as admitted examples.

## Methods and equation systems

Implement the shared method and Rule Card contracts, record the source revision and license, and test the algorithm's defining behavior. A faithful adaptation can simplify infrastructure; it cannot silently replace the method with a generic prompt loop. Report unsupported and incomplete execution explicitly.

Equation graphs must expose their expanded operators, units, intermediate quantities, assumptions, parameter bindings, and fitted state. Compare against simpler alternatives. Source established scientific forms; label model-generated proposals distinctly. A successful fit is not evidence of a unique physical mechanism.

## Development

Use Python 3.11 or newer, keep virtual environments outside the checkout, and install the development extras:

```bash
python3 -m venv ../principia-asd-dev-env
../principia-asd-dev-env/bin/pip install '.[dev]'
../principia-asd-dev-env/bin/ruff check --no-cache src tests scripts
PYTHONDONTWRITEBYTECODE=1 ../principia-asd-dev-env/bin/python -m pytest -q -p no:cacheprovider
```

Run relevant checks first. Exercise changes to user journeys in a browser, including empty states and failures. Some isolation checks require macOS; absence of that sandbox must remain an explicit unsupported state. Synthetic fixtures should not make paid API calls.

Keep keys, local imports, private evaluator outcomes, environments, and mutable jobs outside Git. Do not replay ambiguous paid requests, rewrite frozen results, tune on private-test feedback, or remove unfavorable attempts. Include a concise description of the problem, changed behavior, tests, and scientific limits in the PR.

## Reporting problems

For a reproducibility issue, include the package version, task and method IDs, hashes, and a minimal non-sensitive example. For a suspected privacy issue, avoid posting credentials, private data, or a working exploit containing someone else's information in a public issue. Contact the repository maintainer with a minimal description first.
