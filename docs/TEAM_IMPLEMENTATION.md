# Evaluator стратегии оператора

Эта реализация расширяет официальный `test_oil` starter repository. Файлы организатора в
`data/`, `scenarios/`, `schemas/` и `validation/` остаются авторитетными. Код не меняет
решение оператора и не оптимизирует его: он вычисляет последствия фиксированного
`OperatorPlan` в явно выбранном окружении.

```python
result = simulate(plan, environment, case_data, assumptions)
```

`environment` — официальный `BASE`/`MANDATORY_STRESS` либо явная композиция
`official scenario + TEAM risk`. Смешивание никогда не происходит автоматически.

## Границы происхождения данных

- `CASE_INPUT`: официальные CSV, YAML, ограничения и контрольные трактовки.
- `TEAM_DECISION`: заказы, резервирование, инвестиции, preparatory acquisition и mitigation patch.
- `TEAM_ASSUMPTION`: выбранные сроки из диапазонов, временные конвенции, research risks и scoring.
- `DIGITAL_TWIN_RESULT`: физические/экономические последствия конкретного запуска.

Запрошенный план остаётся неизменным. Модель хранит раздельно:

```text
requested != feasible != gross delivered != accepted != served
```

Превышение лимита создаёт `unfulfilled_request_t` и violation; исходный заказ не
перезаписывается допустимым значением.

## Preparatory period и opening stock

Положительный `inventory_policy.initial_inventory` запрещён. Opening inventory на
`2035-01-01` может возникнуть только из `decisions.initial_stock_acquisition`:

```text
source_id
reserved_capacity_t_per_year
ordered_volume_t
order_date
planned_delivery_date
contract_period_start
contract_period_end
notes
status = TEAM_DECISION
```

Pre-horizon evaluator проверяет:

1. существование источника;
2. source availability и инвестиционные prerequisites;
3. delivery lead time;
4. контрактный и физический capacity limit;
5. take-or-pay и reservation fee;
6. scenario delivery share и явную availability share;
7. throughput loss базового хранилища;
8. storage capacity.

Расчёт сохраняет requested, feasible, unfulfilled, payable, procurement,
reservation, take-or-pay effect, gross, losses, net, accepted и opening inventory.
Все preparatory costs относятся к финансовому 2035 году. Цена берётся у выбранного
официального source; отдельной «цены начального запаса» нет.

Preparatory shipment не входит в `actual_arrivals_by_month`, поэтому не появляется
повторно как January-2035 arrival. В `pre_horizon.provenance` хранится цепочка
`opening inventory <- shipment <- order <- source <- contract`.

## Однозначная семантика материального потока

В каждом из 72 месяцев используется одна публичная цепочка:

```text
gross_delivery_t
    -> losses_t
    -> net_delivery_t
    -> accepted_delivery_t
    -> available_inventory_t
    -> served_critical_t / served_noncritical_t
    -> closing_inventory_t
```

Формулы:

```text
Losses = GrossDelivery * LossRate
NetDelivery = GrossDelivery - Losses
FreeCapacity = max(0, StorageCapacity - OpeningInventory)
AcceptedDelivery = min(NetDelivery, FreeCapacity)
Overflow = max(0, NetDelivery - AcceptedDelivery)
AvailableInventory = OpeningInventory + AcceptedDelivery
ServedCritical = min(AvailableInventory, CriticalDemand)
ServedNonCritical = min(
    AvailableInventory - ServedCritical,
    TotalDemand - CriticalDemand
)
ClosingInventory = AvailableInventory - ServedCritical - ServedNonCritical
```

Отрицательный inventory не используется: необслуженный спрос хранится как shortage.
Поля наподобие `delivered_for_balance_t` отсутствуют из публичного результата.

## Pipeline, capacity и delivery

Annual-even order делится на 12 равных requested orders. Для source/year:

```text
reserved_period = annual_reservation * active_fraction
physical_period = sum(monthly active capacities / 12)
contract_limit = min(reserved_period, physical_period)
feasible_factor = min(1, contract_limit / available_requested)
```

Этот factor пропорционально применяется к заказам года; requested значения сохраняются.
Base lead time образует `planned_arrival_month`, а явный risk override —
`actual_arrival_month`. Delivery share и availability share применяются один раз к
feasible shipment до storage loss.

## Demand, storage и service

Официальный annual demand распределяется равномерно по месяцам — это раскрытая
`TEAM_ASSUMPTION`. Scenario/risk multiplier применяется помесячно. Critical demand
вложен в total demand и обслуживается первым как явная policy реализации.

ZBO после фактической commissioning date меняет storage capacity, throughput loss
rate и fixed OPEX. Research risk может отдельно изменить loss rate или capacity на
заданный период. Standing boil-off текущего запаса не моделируется: официальный
коэффициент относится к throughput.

## Contract economics и инвестиции

```text
payable_volume = max(ordered_volume, TOP_share * reserved_period)
procurement = payable_volume * active_variable_price
reservation = reservation_rate * annual_reserved_capacity * period_fraction
holding_month = mean(opening, closing) * annual_holding_rate / 12
TotalCost = procurement + reservation + holding + fixed OPEX + CAPEX
```

Initial-stock procurement/reservation входят в те же компоненты 2035 года и
показываются отдельными informational fields, но не суммируются второй раз.
Earth-New `90 + 270 = 360`; ZBO и ISRU CAPEX также начисляются один раз.

## Official scenarios и TEAM risks

Официальные сценарии не изменяются. По умолчанию TEAM risk строится поверх BASE:

```text
BASE + TEAM_RISK_X
```

Чтобы получить combined run, вызывающая сторона обязана явно передать
`MANDATORY_STRESS` как base scenario. Result сохраняет `base_scenario_id`,
`environment_id`, `risk_ids`, полный список overrides и order of application.

Risk definition содержит event/cause/period/owner, affected parameters, factor changes,
dependencies, likelihood semantics, sources, combination policy, optional mitigation и
provenance status.

Поддерживаемые deterministic factors:

- total/critical demand multiplier;
- actual delivery share;
- source availability share;
- source lead-time addition/override;
- source capacity multiplier;
- variable/reservation price multiplier or override;
- storage loss multiplier/override;
- storage capacity multiplier;
- investment commissioning delay;
- fixed OPEX/CAPEX multiplier or override.

Одинаковый factor/target/period нельзя объявить дважды в одном risk definition.

## Reliability и likelihood

**Organizer `reliability_profile` — только metadata. Он не является автоматически
вероятностью отказа, Bernoulli parameter или delivery multiplier. Значение
`1 - reliability` нигде не вычисляется.**

Likelihood поддерживает:

- `probability`;
- `probability_range`;
- `qualitative` score 1..5;
- `unknown`.

Probability/range/qualitative likelihood требует одновременно `basis` и `source`.
Без них значение переводится в `UNKNOWN` и не получает score. Такие риски всё равно
прогоняются через digital twin и попадают в `unknown_likelihood_risks`.

## Consequence engine

Для каждого риска выполняются два запуска одного плана:

1. `OperatorPlan + selected official scenario`;
2. тот же `OperatorPlan + selected official scenario + risk overrides`.

Сравнение включает shortage, annual service, minimum/final inventory, reserve breach,
overflow, unavailable requested supply, hard violations, first violation, disruption
duration, delayed deliveries и месяцы shortage. Экономические delta включают total,
discounted, procurement, reservation, CAPEX, fixed OPEX и holding costs.

`baseline_run_id` и `risk_run_id` — детерминированные SHA-256 fingerprints плана,
официальных входов, scenario, assumptions и overrides.

## Impact scoring и risk matrix

`configs/risk_scoring.json` имеет статус `TEAM_ASSUMPTION`. Для каждого измерения
вычисляется score 1..5:

- critical-service degradation;
- shortage share;
- incremental cost percent;
- incremental hard violations;
- disruption duration.

Итоговый impact — максимум dimension scores. Физические значения всегда сохраняются
рядом со score.

```text
ordinal_risk_score = likelihood_score * impact_score
```

Это только ordinal prioritization, не expected loss и не monetary damage. 5x5 matrix
строится для конкретного плана; риски без likelihood выводятся в отдельную секцию
`UNKNOWN LIKELIHOOD`.

## Risk register

Register генерируется из risk definition и парных SimulationResult. В нём находятся
provenance, baseline/risk run IDs, quantitative delta, impact dimensions, violations,
likelihood, ordinal score и mitigation/residual fields. Ручной qualitative impact без
расчётного запуска не используется.

## Mitigation

Mitigation не генерируется. Если команда явно предоставляет `plan_patch`, создаётся
новый plan ID, план проходит обычную validation и затем запускается с тем же риском.

```text
mitigation_cost = BASE_cost(mitigated) - BASE_cost(original)
```

Отдельно сохраняются original risk outcome и residual consequence/impact/risk score.
Likelihood не меняется автоматически. `residual_likelihood` принимается только с
явными basis и source.

## Sensitivity и reverse stress

`sensitivity_sweep` прогоняет фиксированный план по явному набору значений одного
environment parameter. Для точки сохраняются cost, service, shortage, inventory и
violations. Есть отдельный official low/base/high demand sweep из `data/demand.csv`.

`find_failure_threshold` выполняет детерминированный ordered-grid search одного
параметра и возвращает last safe value, first failing value, первое нарушение, period и
result metrics. Он не меняет план и не является optimizer.

## CLI и exports

```bash
python3 scripts/evaluate_plan.py --plan configs/operator_plan_example.json --scenario both
python3 scripts/evaluate_risks.py --plan configs/operator_plan_example.json \
  --risks configs/risks/team_risks.json --scenario BASE
python3 scripts/run_sensitivity.py --plan configs/operator_plan_example.json \
  --parameter demand_multiplier --values 1.0,1.05,1.10
python3 scripts/run_reverse_stress.py --plan configs/operator_plan_example.json \
  --parameter demand_multiplier --start 1.0 --stop 1.5 --step 0.01 \
  --target-constraint BASE_TOTAL_SERVICE
```

Risk outputs:

```text
results/<plan_id>/risks/
  risk_register.json
  risk_register.csv
  risk_matrix.json
  risk_matrix.csv
  risk_portfolio.json
  risk_scoring.json
  runs/<risk_id>/...
  sensitivity/...
  reverse_stress/...
```

## Проверяемость

- V01–V10 читают expected values из неизменённого `validation/expected_checks.json`.
- Runtime invariant проверяет `closing = opening + accepted - served` ежемесячно.
- Unit/integration tests покрывают preparatory contract, risk isolation, все группы
  overrides, likelihood, scoring, register/matrix, mitigation, sensitivity, reverse
  stress, exports и reproducibility.
- Одинаковые входы дают одинаковый run ID и результат.

## Active TEAM assumptions

Кроме risk definitions/scoring используются:

1. Earth-New project lead — 24 месяца из официальных 18–24.
2. Earth-New operational lag после commissioning — 0 месяцев.
3. Lunar-ISRU delivery lead — 2 месяца из официальных 1–2.
4. Реальная ставка дисконтирования — демонстрационные 5%.
5. Discount timing — конец календарного года, база 2035.
6. Annual demand allocation — равномерно по 12 месяцам.
7. Holding stock-time — trapezoid opening/closing.
8. Emergency 6 недель — `ceil(42 / (365/12)) = 2` model months.
9. Critical demand обслуживается первым.
10. Внутри месяца arrival/storage происходят до service.
11. Annual capacity excess пропорционально распределяется по заказам года.
12. Risk scoring thresholds — `configs/risk_scoring.json`.
13. Non-uniform orders are charged at order-month prices; TOP-only volume uses the
    active-contract-period time-weighted price.

## Ограничения

Это one-node, one-commodity, deterministic monthly evaluator. Он не моделирует
propellant chemistry, standing boil-off, tank thermodynamics, trajectories, launch
vehicles, transfer interfaces, correlated outages, probability distributions,
telemetry или real-world calibration. Strategy Advisor использует ограниченный
детерминированный local search и не доказывает глобальный optimum. Здесь нет MILP,
Optuna, RL, Monte Carlo, automatic contract negotiation, database или UI.

Следовательно, реализация проверяет внутреннюю согласованность и последствия стратегии
в рамках синтетического кейса, но не является инженерно сертифицированным цифровым
двойником лётной системы.

## Конфликты с official starter semantics

Конфликтов, требующих изменения official CASE_INPUT, не обнаружено. Требование
preparatory acquisition является более строгим participant-level правилом поверх
расширяемого official plan envelope; official files не переписаны. Материальная,
contract, reserve и mandatory-stress семантика сохранена.

## v0.4: effective case и advisor

`CaseWorkspace` строит effective `CaseData` копированием official case и применением
typed overlays. `ResearchSourceSpec` задаёт параметры и availability rule;
`FutureYearSpec` обязан явно перечислить спрос, prices, capacity, availability,
reliability metadata, constraints и provenance. Official rows остаются `CASE_INPUT`,
новые entities — `TEAM_ASSUMPTION / RESEARCH_EXTENSION`.

Общий shipment pipeline больше не содержит закрытого словаря A–E. Он вызывает
`source_commissioning_month()` и одинаково обрабатывает requested, feasible, lead,
arrival, loss, acceptance, storage и service для official и research sources.
Специальные policy rules Earth-New, Lunar-ISRU и Emergency остаются привязаны к
official entities и не распространяются на F.

Контрактная экономика рассчитывает помесячную цену заказанных объёмов. Run ID включает
serialized effective case. Exports содержат horizon/source provenance и новые KPI
cost per actually served tonne.

Advisor packages `patch`, `locks`, `distance`, `search_space`, `evaluator`, `repair`,
`improve`, `resilience`, `explore`, `result`, and `serialization` отделены от
simulation. Каждый accepted candidate проходит обычный `simulate()` в BASE и stress.
Original plan не мутируется; применение typed patch остаётся отдельным действием.
