# Test protocol

## Suites

- `tests/unit`: pure physics, economics, loading, timing, initial acquisition, and risk
  validation.
- `tests/integration`: complete simulation, constraints, scenarios, risks,
  sensitivity/reverse stress, exports, and reproducibility.
- `tests/official`: unchanged organizer V01–V10 vectors.
- `tests/acceptance`: independent remaining-core, EXT/HOR, advisor, product API, and
  save/reopen properties.
- `tests/service`: the stable UI facade, including context, plan validation and
  round-trip, real BASE/STRESS/risk/sensitivity/advisor calls, workspace persistence,
  and the downloadable ZIP contract.

## Independent expected results

The preparatory contract vector fixes the expected values directly from the
requirement: reservation 100, order 50, TOP 70%, price 6.2, reservation rate 0.45,
loss 4.5% gives payable 70, procurement 434, reservation 45, TOP effect 124, gross 50,
loss 2.25, and opening inventory 47.75.

The partial-price vector fixes 10 t outside and 30 t inside a 2x price period for a
source without TOP: `10*8.9 + 30*17.8 = 623`. It does not import the contract helper to
derive the expected value.

EXT/HOR fixtures require source F to use the standard pipeline, a 2040-12 order with
four-month lead to arrive in 2041-04, 2041 to produce 84 states, and 2042 to produce 96.

## Negative/property tests

- negative inputs and unavailable sources;
- capacity excess preserves requested volume and the original plan;
- price-only shocks preserve physics and violations;
- locks make an otherwise repairable search return no feasible repair;
- impossible search never fabricates feasibility;
- saved patch/workspace reopens to the same plan/case and result;
- same effective inputs/config/seed produce identical results.

## Commands

```bash
python3 -m pytest
python3 tools/validate_reference_repo.py
python3 tools/validate_participant_repo.py
bash operator_tests/run_all.sh
```

The final verified counts and validator result are recorded after the final commands,
not inferred from earlier runs.

`validate_reference_repo.py` contains a starter-template-only guard that intentionally
fails when `src/`, `configs/`, `results/`, or `pyproject.toml` exists. The participant
validator executes every other organizer integrity check and names that single skipped
guard explicitly.

## Final verified run — 2026-09-19

```text
python3 -m pytest
116 passed, 0 failed

python3 -m pytest tests/official
10 passed, 0 failed

python3 -m pytest tests/acceptance/test_workspace_extension.py
7 passed, 0 failed

python3 -m pytest tests/acceptance/test_strategy_advisor.py
3 passed, 0 failed

python3 -m pytest tests/integration/test_risk_engine.py tests/unit/test_risk_loading.py
18 passed, 0 failed

python3 -m pytest tests/integration/test_reproducibility_and_export.py \
  tests/acceptance/test_product_api_and_serialization.py
6 passed, 0 failed

python3 -m pytest tests/integration/test_sensitivity_reverse.py
4 passed, 0 failed

python3 -m pytest tests/service/test_ui_service_api.py
10 passed, 0 failed
```

`python3 tools/validate_participant_repo.py` passed all applicable organizer
integrity checks with zero failures. The latest full participant CI on the final-evidence branch reports `116 passed`. `bash operator_tests/run_all.sh` exited 0 and ran
all ten operator fixtures. The original reference validator passed those same content
checks but, as designed, returned 1 only for `check_no_ready_solution` because this is
now a participant repository containing `src/`, `configs/`, `results/`, and
`pyproject.toml`.
