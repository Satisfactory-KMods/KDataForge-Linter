from __future__ import annotations

from pathlib import Path

import pytest

from kdataforge_linter.schema_registry import SchemaRegistry
from kdataforge_linter.validator import lint_path

GITHUB_SCHEMA_BASE = (
    "https://raw.githubusercontent.com/Satisfactory-KMods/"
    "KDataForge-Linter/main/src/kdataforge_linter/schemas/"
)


def test_all_builtin_schemas_load() -> None:
    registry = SchemaRegistry()
    assert registry.kinds() == [
        "asset",
        "building",
        "cdo",
        "class",
        "curve",
        "dataasset",
        "gametag",
        "item",
        "localization",
        "mam",
        "pack",
        "recipe",
        "research",
        "resource",
        "schematic",
        "sinkpoints",
        "unlock",
    ]


def test_builtin_schema_ids_use_github_raw_urls() -> None:
    registry = SchemaRegistry()
    assert registry._store
    assert all(schema_id.startswith(GITHUB_SCHEMA_BASE) for schema_id in registry._store)
    assert f"{GITHUB_SCHEMA_BASE}common.schema.yml" in registry._store


def test_builtin_schema_patterns_do_not_use_python_only_inline_flags() -> None:
    registry = SchemaRegistry()

    def collect_patterns(value: object) -> list[str]:
        if isinstance(value, dict):
            own = [value["pattern"]] if isinstance(value.get("pattern"), str) else []
            return own + [pattern for child in value.values() for pattern in collect_patterns(child)]
        if isinstance(value, list):
            return [pattern for child in value for pattern in collect_patterns(child)]
        return []

    patterns = [pattern for schema in registry._store.values() for pattern in collect_patterns(schema)]
    assert patterns
    assert all("(?i)" not in pattern for pattern in patterns)


def test_valid_pack_passes(valid_dataforge: Path) -> None:
    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.diagnostics]
    assert result.pack_count == 1
    assert result.document_count == 1


def test_unknown_field_is_rejected(valid_dataforge: Path) -> None:
    document = next(valid_dataforge.rglob("*.cdo.yml"))
    document.write_text(document.read_text(encoding="utf-8") + "\nunknownField: true\n", encoding="utf-8")
    result = lint_path(valid_dataforge)
    assert any(item.code == "schema.unevaluatedProperties" for item in result.errors)


def test_document_allows_schema_metadata_and_inverted_condition(valid_dataforge: Path) -> None:
    document = next(valid_dataforge.rglob("*.cdo.yml"))
    document.write_text(
        "\n".join(
            [
                f"$schema: {GITHUB_SCHEMA_BASE}cdo.schema.yml",
                "type: cdo",
                "conditions:",
                "  hasMod:",
                "    - Tin@>=1.0.0",
                "  ifNotMatch: true",
                "patches:",
                "  - target: /Game/Example.Example_C",
                "    properties:",
                "      - path: mValue",
                "        value: 2",
            ]
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.diagnostics]


def test_asset_allows_schema_metadata_and_case_insensitive_image_extension(valid_dataforge: Path) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    (pack / "icon.PNG").write_bytes(b"")
    (pack / "icons.asset.yml").write_text(
        "\n".join(
            [
                f"$schema: {GITHUB_SCHEMA_BASE}asset.schema.yml",
                "type: asset",
                "assets:",
                "  - id: Icon_Test",
                "    file: icon.PNG",
            ]
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.diagnostics]


@pytest.mark.parametrize("behavior_key", ["conditionBehaivor", "conditionBehavior"])
def test_document_allows_condition_sequences_and_behavior_aliases(
    valid_dataforge: Path, behavior_key: str
) -> None:
    document = next(valid_dataforge.rglob("*.cdo.yml"))
    document.write_text(
        "\n".join(
            [
                "type: cdo",
                f"{behavior_key}: or",
                "conditions:",
                "  - hasMod: RefinedPower",
                "  - hasMod: IncompatibleMod",
                "    ifNotMatch: true",
                "patches:",
                "  - target: /Game/Example.Example_C",
                "    properties:",
                "      - path: mValue",
                "        value: 2",
            ]
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.diagnostics]


def test_pack_allows_schema_metadata_and_current_condition_grammar(valid_dataforge: Path) -> None:
    manifest = next(valid_dataforge.rglob("pack.yml"))
    manifest.write_text(
        "\n".join(
            [
                f"$schema: {GITHUB_SCHEMA_BASE}pack.schema.yml",
                "ref: Example",
                "name: Example Pack",
                "version: 1.0.0",
                "contributer: ExampleAuthor",
                "conditionBehavior: AND",
                "conditions:",
                "  - hasMod: KAPI",
                "  - hasMod: IncompatibleMod",
                "    ifNotMatch: true",
            ]
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.diagnostics]


def test_if_not_match_requires_boolean(valid_dataforge: Path) -> None:
    document = next(valid_dataforge.rglob("*.cdo.yml"))
    document.write_text(
        document.read_text(encoding="utf-8").replace(
            "patches:", "conditions:\n  hasMod: KAPI\n  ifNotMatch: inverted\npatches:"
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert any(
        item.code == "schema.type" and item.yaml_path == "$.conditions.ifNotMatch" for item in result.errors
    )


def test_condition_behavior_rejects_unknown_value(valid_dataforge: Path) -> None:
    document = next(valid_dataforge.rglob("*.cdo.yml"))
    document.write_text(
        document.read_text(encoding="utf-8").replace("type: cdo", "type: cdo\nconditionBehavior: XOR"),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert any(
        item.code == "schema.pattern" and item.yaml_path == "$.conditionBehavior" for item in result.errors
    )


def test_removed_propagate_to_instances_is_rejected(valid_dataforge: Path) -> None:
    document = next(valid_dataforge.rglob("*.cdo.yml"))
    document.write_text(
        document.read_text(encoding="utf-8").replace(
            "    properties:", "    propagateToInstances: true\n    properties:"
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert any(
        item.code == "schema.additionalProperties" and item.yaml_path == "$.patches[0]" for item in result.errors
    )


@pytest.mark.parametrize(
    ("root_type", "entries_key"),
    [
        ("item", "items"),
        ("resource", "resources"),
        ("building", "buildings"),
        ("unlock", "unlocks"),
    ],
)
def test_register_only_class_is_rejected_for_non_registerable_roots(
    valid_dataforge: Path, root_type: str, entries_key: str
) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    (pack / f"invalid.{root_type}.yml").write_text(
        "\n".join(
            [
                f"type: {root_type}",
                f"{entries_key}:",
                "  - class: /Game/Example.Example_C",
            ]
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert any("register-only" in item.message for item in result.errors)


def test_register_only_class_remains_valid_for_recipe(valid_dataforge: Path) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    (pack / "existing.recipe.yml").write_text(
        "\n".join(
            [
                "type: recipe",
                "recipes:",
                "  - class: /Game/Example.Recipe_Example_C",
            ]
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.diagnostics]


def test_external_schema_adds_custom_type(valid_dataforge: Path, tmp_path: Path) -> None:
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "custom.schema.yml").write_text(
        "\n".join(
            [
                "$schema: https://json-schema.org/draft/2020-12/schema",
                "$id: https://example.invalid/custom.schema.yml",
                "x-kdf-type: custom",
                "type: object",
                "additionalProperties: false",
                "required: [type, value]",
                "properties:",
                "  type: { const: custom }",
                "  value: { type: integer }",
            ]
        ),
        encoding="utf-8",
    )
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    (pack / "example.custom.yml").write_text("type: custom\nvalue: 7\n", encoding="utf-8")
    result = lint_path(valid_dataforge, [schema_dir])
    assert not any(item.code == "schema.unknown-type" for item in result.diagnostics)
