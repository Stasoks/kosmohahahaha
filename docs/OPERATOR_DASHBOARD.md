# Operator dashboard

The Streamlit application is the operator-facing presentation layer for the
authoritative `kosmohak.service` backend.

## Run

```bash
python3 -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

The default plan is `plans/final_base.json`, with
`configs/operator_plan_example.json` as a fallback. Nothing is silently persisted to
the server filesystem: JSON downloads/uploads are the primary portable workflow.

## Architecture

```text
streamlit_app.py + app/pages/*
    -> app/kernel_bridge.py
    -> kosmohak.service
    -> authoritative simulation/risk/workspace/Builder modules
    -> SimulationResult and other domain results
    -> app/view_models.py + app/charts.py
```

The frontend only formats backend rows, builds charts and calculates display-only
deltas between complete results. Physics, losses, lead time, reservations,
take-or-pay, CAPEX, reserve, feasibility and service validity are not reimplemented.

## State and calculation lifecycle

Session state keeps the editable plan, the last calculated plan, BASE/STRESS results,
the selected stress-specific plan, risk/mitigation/sensitivity/reverse-stress values,
research workspace and browser-session snapshots.

Editing a TEAM_DECISION does not calculate automatically. The UI compares canonical
plan hashes and shows `ЕСТЬ НЕСЧИТАННЫЕ ИЗМЕНЕНИЯ` until the user presses
`Пересчитать`. Deterministic work is cached by canonical JSON. Builder, portfolio
risk, wide sensitivity and ZIP generation run only after an explicit action.

## Main user flows

- **Обзор:** minimum annual total/critical service, shortages, 45-day reserve,
  separate CAPEX limits, lifecycle/PV cost, inventory, source mix and top problems.
- **Стратегия:** dynamic source/year decisions, preserved monthly schedules,
  reservations, investments, paid opening stock, reserve policy and Emergency role;
  structural validation precedes calculation.
- **Результаты:** annual/monthly balances, channel mechanics, economics and readable
  hard/benchmark/warning rows.
- **Сценарии:** A=current plan in BASE, B=the exact same plan in mandatory stress,
  C=an ex-ante stress-specific plan in mandatory stress. Builder candidates are
  labelled bounded heuristic, never global optimum.
- **Риски и чувствительность:** portfolio with honest UNKNOWN likelihood, causal risk
  detail, validated mitigation, official LOW/BASE/HIGH, custom one-factor sweeps,
  reverse-stress threshold and stakeholder consequences.
- **Исследования:** a non-destructive `CaseWorkspace`, explicit new-source and
  contiguous future-year assumptions, dynamic decision axes and normal simulator
  evaluation.
- **Данные и экспорт:** plan JSON roundtrip, CASE_INPUT inspection, backend CSV and a
  reproducible ZIP.

## Scenario semantics

In BASE, annual total service >=97% and critical service >=99% are official hard
constraints. In MANDATORY_STRESS the same levels are displayed as resilience
benchmarks. A benchmark miss is visible but is not relabelled as a hard organizer
violation.

C is a separately planned ex-ante scenario alternative. It is not a reactive switch
made after observing a 2038 event.

## Provenance labels

The UI uses `CASE_INPUT`, `TEAM_DECISION`, `TEAM_ASSUMPTION`,
`DIGITAL_TWIN_RESULT` and `RESILIENCE_BENCHMARK`. Official inputs are read-only in
the competition view. Research inputs live only in the workspace overlay.

## Boundaries

- Builder is deterministic bounded beam search and does not prove a global optimum or
  global infeasibility.
- Mandatory stress is official only for the case horizon; future-year scenario values
  are TEAM_ASSUMPTION.
- Server-local snapshots are supplementary and session-scoped. Use JSON download for
  durable transfer.
- The UI does not invent profit, revenue, penalties, counterparty review rules or risk
  probabilities absent from CASE_INPUT/team evidence.
