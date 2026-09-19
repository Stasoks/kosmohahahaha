#!/usr/bin/env python3
"""Run organizer integrity checks that remain applicable after participant implementation."""

from __future__ import annotations

from validate_reference_repo import (
    check_demand,
    check_investments_and_constraints,
    check_json_yaml_syntax,
    check_mandatory_stress,
    check_no_placeholders_or_secrets,
    check_relative_markdown_links,
    check_required_readme_content,
    check_schemas,
    check_sources,
    check_validation_vectors,
)


def main() -> int:
    checks = [
        check_json_yaml_syntax,
        check_demand,
        check_sources,
        check_investments_and_constraints,
        check_mandatory_stress,
        check_schemas,
        check_validation_vectors,
        check_relative_markdown_links,
        check_required_readme_content,
        check_no_placeholders_or_secrets,
    ]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    print(
        "PASS participant repository integrity; skipped only "
        "check_no_ready_solution (starter-template guard)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
