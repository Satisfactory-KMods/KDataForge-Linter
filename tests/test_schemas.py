from __future__ import annotations

from pathlib import Path

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
