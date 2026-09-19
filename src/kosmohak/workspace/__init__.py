from kosmohak.workspace.domain import FutureYearSpec, ResearchSourceSpec
from kosmohak.workspace.serialization import (
    effective_case_to_dict,
    load_workspace,
    save_workspace,
)
from kosmohak.workspace.workspace import CaseWorkspace


def add_research_source(case_data, spec: ResearchSourceSpec):
    return CaseWorkspace.from_official(case_data).add_source(spec).build()


def extend_horizon(case_data, specs):
    return CaseWorkspace.from_official(case_data).extend_horizon(specs).build()


__all__ = [
    "CaseWorkspace",
    "ResearchSourceSpec",
    "FutureYearSpec",
    "add_research_source",
    "extend_horizon",
    "effective_case_to_dict",
    "save_workspace",
    "load_workspace",
]
