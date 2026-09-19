from __future__ import annotations

import copy
from dataclasses import replace
from typing import Iterable

from kosmohak.domain.case import CaseData
from kosmohak.workspace.domain import FutureYearSpec, ResearchSourceSpec
from kosmohak.workspace.horizon import build_future_demand
from kosmohak.workspace.sources import build_research_source
from kosmohak.workspace.validation import validate_future_year_spec, validate_source_spec


class CaseWorkspace:
    """Non-destructive overlay builder over organizer-owned CaseData."""

    def __init__(self, official_case: CaseData) -> None:
        self._official_case = official_case
        self._source_specs: list[ResearchSourceSpec] = []
        self._future_specs: list[FutureYearSpec] = []

    @classmethod
    def from_official(cls, case_data: CaseData) -> "CaseWorkspace":
        return cls(case_data)

    def add_source(self, spec: ResearchSourceSpec) -> "CaseWorkspace":
        ids = set(self._official_case.sources) | {item.source_id for item in self._source_specs}
        names = {item.name for item in self._official_case.sources.values()} | {
            item.name for item in self._source_specs
        }
        validate_source_spec(spec, self._official_case, ids, names)
        prospective_ids = ids | {spec.source_id}
        expected = max(self._official_case.years) + 1
        for future_spec in self._future_specs:
            validate_future_year_spec(
                future_spec, self._official_case, prospective_ids, expected
            )
            expected += 1
        self._source_specs.append(copy.deepcopy(spec))
        return self

    def extend_horizon(
        self, specs: FutureYearSpec | Iterable[FutureYearSpec]
    ) -> "CaseWorkspace":
        values = [specs] if isinstance(specs, FutureYearSpec) else list(specs)
        source_ids = set(self._official_case.sources) | {
            item.source_id for item in self._source_specs
        }
        expected = max(
            (*self._official_case.years, *(item.year for item in self._future_specs))
        ) + 1
        for spec in values:
            validate_future_year_spec(
                spec, self._official_case, source_ids, expected
            )
            expected += 1
        self._future_specs.extend(copy.deepcopy(values))
        return self

    def _revalidate_future_specs(self) -> None:
        source_ids = set(self._official_case.sources) | {
            item.source_id for item in self._source_specs
        }
        expected = max(self._official_case.years) + 1
        for spec in self._future_specs:
            validate_future_year_spec(
                spec, self._official_case, source_ids, expected
            )
            expected += 1

    def build(self) -> CaseData:
        self._revalidate_future_specs()
        sources = copy.deepcopy(self._official_case.sources)
        for spec in self._source_specs:
            sources[spec.source_id] = build_research_source(spec)
        demand = copy.deepcopy(self._official_case.demand)
        horizon = copy.deepcopy(self._official_case.horizon_provenance)
        future: dict[int, dict] = copy.deepcopy(
            self._official_case.future_year_assumptions
        )
        for spec in self._future_specs:
            demand[spec.year] = build_future_demand(spec)
            provenance = {
                **spec.provenance,
                "status": "TEAM_ASSUMPTION",
                "scope": "RESEARCH_EXTENSION",
                "notes": spec.notes,
            }
            horizon[spec.year] = provenance
            future[spec.year] = spec.to_dict()
        has_overlay = bool(self._source_specs or self._future_specs)
        return replace(
            self._official_case,
            demand=demand,
            sources=sources,
            source_id_by_name={source.name: source_id for source_id, source in sources.items()},
            constraints=copy.deepcopy(self._official_case.constraints),
            storage=copy.deepcopy(self._official_case.storage),
            investments=copy.deepcopy(self._official_case.investments),
            status="TEAM_ASSUMPTION" if has_overlay else self._official_case.status,
            horizon_provenance=horizon,
            future_year_assumptions=future,
            workspace_provenance={
                "status": "TEAM_ASSUMPTION" if has_overlay else "CASE_INPUT",
                "scope": "EFFECTIVE_CASE" if has_overlay else "OFFICIAL_CASE",
                "research_source_ids": [item.source_id for item in self._source_specs],
                "research_extension_years": [item.year for item in self._future_specs],
            },
        )

    def to_dict(self) -> dict:
        return {
            "status": "TEAM_ASSUMPTION",
            "base": "OFFICIAL_CASE",
            "sources": [item.to_dict() for item in self._source_specs],
            "future_years": [item.to_dict() for item in self._future_specs],
        }

    @classmethod
    def from_dict(cls, official_case: CaseData, value: dict) -> "CaseWorkspace":
        workspace = cls.from_official(official_case)
        for raw in value.get("sources", []):
            workspace.add_source(ResearchSourceSpec.from_dict(raw))
        for raw in value.get("future_years", []):
            workspace.extend_horizon(FutureYearSpec.from_dict(raw))
        return workspace
