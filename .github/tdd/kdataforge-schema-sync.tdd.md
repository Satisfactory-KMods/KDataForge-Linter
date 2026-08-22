# KDataForge schema sync TDD evidence

## Source and user journeys

No plan file was supplied. Journeys came from reported editor diagnostics and current KDataForge
runtime/docs:

- Pack author adds root `$schema` metadata for YAML editor completion without linter errors.
- Pack author uses condition maps or arrays, per-object `ifNotMatch`, and either behavior spelling.
- Linter rejects invalid condition values and YAML accepted by old schemas but unsupported by current runtime.
- Image asset schemas work in JSON Schema's ECMA-262 regex environment.

## Task report

| Behavior | RED evidence | GREEN evidence | Guarantee |
| --- | --- | --- | --- |
| Root `$schema` on documents and `pack.yml` | `uv run pytest tests/test_schemas.py` — 11 failed, 6 passed | Same command — 17 passed | Editor schema metadata is allowed while arbitrary root keys remain rejected. |
| Current condition grammar | RED failures included mapping `ifNotMatch`, condition arrays, both behavior spellings, and pack parity | Focused suite 17 passed; final full suite 31 passed | Schema and legacy semantic passes accept runtime-supported grammar and reject invalid inversion/behavior values. |
| Removed/unsupported forms | RED failures showed `propagateToInstances` and register-only item/resource/building/unlock roots were accepted | Focused suite 17 passed | Strict schemas no longer advertise removed CDO behavior or unsupported register-only roots; recipe register-only remains valid. |
| Editor-compatible image pattern | Focused suite after regression addition — 1 failed, 18 passed | Same command — 19 passed; Node regex smoke test passed | Asset filename pattern avoids Python-only flags and works in ECMA-262/JavaScript schema consumers. |

## Test specification

| # | What is guaranteed | Test | Type | Result |
| ---: | --- | --- | --- | --- |
| 1 | CDO root accepts `$schema` plus mapping-level `ifNotMatch` | `test_document_allows_schema_metadata_and_inverted_condition` | Integration | PASS |
| 2 | Documents accept condition arrays and both behavior spellings case-insensitively | `test_document_allows_condition_sequences_and_behavior_aliases` | Integration | PASS |
| 3 | `pack.yml` accepts `$schema` and same condition grammar | `test_pack_allows_schema_metadata_and_current_condition_grammar` | Integration | PASS |
| 4 | `ifNotMatch` must be boolean and behavior must be AND/OR | `test_if_not_match_requires_boolean`, `test_condition_behavior_rejects_unknown_value` | Negative | PASS |
| 5 | Removed `propagateToInstances` is rejected | `test_removed_propagate_to_instances_is_rejected` | Negative | PASS |
| 6 | Register-only class is limited to runtime-capable roots | `test_register_only_class_is_rejected_for_non_registerable_roots`, `test_register_only_class_remains_valid_for_recipe` | Negative/integration | PASS |
| 7 | Unknown root properties remain rejected | `test_unknown_field_is_rejected` | Regression | PASS |
| 8 | Asset documents accept `$schema` and case-insensitive supported image extensions | `test_asset_allows_schema_metadata_and_case_insensitive_image_extension` | Integration | PASS |
| 9 | Bundled patterns avoid Python-only inline case flags | `test_builtin_schema_patterns_do_not_use_python_only_inline_flags` | Schema portability | PASS |

## Verification and known gaps

- `uv run pytest --cov=kdataforge_linter --cov-report=term-missing`: 31 passed; 56% project-wide coverage.
  Existing untested GUI and legacy branches keep repository coverage below 80%; project config has no enforced threshold.
- `uv run ruff check .`: PASS.
- `uv run kdataforge-linter schemas check`: PASS, 17 root types.
- `uv build`: PASS, sdist and wheel produced.
- `uv run kdataforge-linter lint ../KPatchwork/DataForge --schema-dir ../KPatchwork/ci/schemas --allow-schema-override --format github`: PASS, 10 packs and 134 documents.
- Configured `uv run mypy` remains blocked by missing `py.typed`; direct source checking also reports 13 pre-existing stub/type issues.
- `uvx pip-audit --path .venv/Lib/site-packages` reports one dev-only finding: pytest 8.4.2 (`PYSEC-2026-1845`, fixed in 9.0.3). Current project constraint is pytest `<9`.

## Worktree evidence

No commits or pushes were retained. RED/GREEN results above describe current uncommitted worktree.
