from __future__ import annotations

import json
from pathlib import Path

from kosmohak.domain.plan import OperatorPlan
from kosmohak.optimization.patch import PlanPatch, apply_plan_patch
from kosmohak.optimization.result import OptimizationResult, SuggestedPlan


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def save_patch(patch: PlanPatch, path: str | Path) -> Path:
    return _write(Path(path), patch.to_dict())


def load_patch(path: str | Path) -> PlanPatch:
    return PlanPatch.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save_suggestion(suggestion: SuggestedPlan, directory: str | Path) -> Path:
    root = Path(directory)
    _write(root / "suggestion.json", suggestion.to_dict())
    _write(root / "suggested_plan.json", suggestion.resulting_plan.raw)
    _write(root / "patch.json", suggestion.patch.to_dict())
    return root


def reopen_suggested_plan(
    original: OperatorPlan,
    patch_path: str | Path,
    *,
    plan_id: str,
) -> OperatorPlan:
    raw = apply_plan_patch(original, load_patch(patch_path), plan_id=plan_id)
    return OperatorPlan.from_dict(raw)


def save_optimization_result(result: OptimizationResult, directory: str | Path) -> Path:
    root = Path(directory)
    _write(root / "optimization_result.json", result.to_dict())
    _write(root / "optimizer_config.json", result.search_config)
    for index, suggestion in enumerate(result.suggestions, start=1):
        save_suggestion(suggestion, root / f"suggestion-{index:02d}")
    return root
