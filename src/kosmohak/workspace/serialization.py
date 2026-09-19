from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from kosmohak.domain.case import CaseData
from kosmohak.workspace.workspace import CaseWorkspace


def effective_case_to_dict(case_data: CaseData) -> dict[str, Any]:
    return {
        "status": case_data.status,
        "demand": {
            str(year): asdict(row) for year, row in sorted(case_data.demand.items())
        },
        "sources": {
            source_id: asdict(source)
            for source_id, source in sorted(case_data.sources.items())
        },
        "storage": {
            storage_id: asdict(value)
            for storage_id, value in sorted(case_data.storage.items())
        },
        "investments": {
            investment_id: asdict(value)
            for investment_id, value in sorted(case_data.investments.items())
        },
        "constraints": {
            constraint_id: asdict(value)
            for constraint_id, value in sorted(case_data.constraints.items())
        },
        "horizon_provenance": {
            str(year): value
            for year, value in sorted(case_data.horizon_provenance.items())
        },
        "future_year_assumptions": {
            str(year): value
            for year, value in sorted(case_data.future_year_assumptions.items())
        },
        "workspace_provenance": case_data.workspace_provenance,
    }


def save_workspace(workspace: CaseWorkspace, path: str | Path) -> Path:
    target = Path(path)
    target.write_text(
        json.dumps(workspace.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def load_workspace(
    path: str | Path, official_case: CaseData
) -> CaseWorkspace:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return CaseWorkspace.from_dict(official_case, value)
