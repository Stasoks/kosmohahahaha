# Errata and provenance

This participant repository keeps organizer-owned CSV, YAML, schemas, and validation
vectors separate from team decisions and assumptions.

## Source layers

- `CASE_INPUT`: `data/`, `scenarios/`, `schemas/`, and `validation/`.
- `TEAM_DECISION`: operator plans and accepted plan patches.
- `TEAM_ASSUMPTION`: model assumptions, deterministic research risks, research
  sources, and post-2040 horizon extensions.
- `DIGITAL_TWIN_RESULT`: simulation, risk, sensitivity, advisor, and comparison
  outputs.

The source package referenced by the migration audit did not include the primary
questionnaire named in `data/README.md`. No missing value has been silently
reconstructed. The machine-readable starter inputs are treated as authoritative for
the competition model; limitations are disclosed in `docs/SCIENTIFIC_BASIS.md`.

## Known interpretation choices

- Critical demand is nested in total demand.
- Reliability profiles are metadata in BASE, not automatic delivery multipliers.
- Emergency six-week lead time is converted to two model months by the documented
  TEAM assumption.
- Earth-New and Lunar-ISRU range selections are explicit TEAM assumptions.
- Research years and sources never receive `CASE_INPUT` status.

`CaseWorkspace` overlays are in-memory/copy-on-build. They never rewrite an organizer
file. The effective case—not only the original files—is included in every run ID.
