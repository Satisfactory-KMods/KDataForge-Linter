from __future__ import annotations

from pathlib import Path

import pytest

from kdataforge_linter.models import LintResult
from kdataforge_linter.schema_registry import SchemaRegistry
from kdataforge_linter.validator import lint_path


def _write_document(valid_dataforge: Path, filename: str, text: str) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    (pack / filename).write_text(text, encoding="utf-8")


def _assert_valid_runtime_document(result: LintResult) -> None:
    assert result.ok, [item.to_dict() for item in result.diagnostics]
    assert not any(item.code == "schema.unknown-type" for item in result.diagnostics)
    assert not any("custom root type" in item.message for item in result.diagnostics)


def _assert_schema_error(result: LintResult, yaml_path: str, validator: str | None = None) -> None:
    assert any(
        item.yaml_path == yaml_path
        and item.code.startswith("schema.")
        and (validator is None or item.code == f"schema.{validator}")
        for item in result.errors
    ), [item.to_dict() for item in result.diagnostics]


def test_runtime_only_root_types_are_built_in() -> None:
    registry = SchemaRegistry()

    assert "resourcenode" in registry.kinds()
    assert "sublevel" in registry.kinds()


@pytest.mark.parametrize(
    ("filename", "body"),
    [
        (
            "inferred.sublevel.yml",
            "block:\n  - /ExampleMod/Data/DA_Sublevel.DA_Sublevel\n",
        ),
        (
            "inferred.resourcenode.yml",
            "remove:\n  - /Game/FactoryGame/Resource/Desc_Test.Desc_Test_C\n",
        ),
    ],
)
def test_runtime_only_root_types_are_inferred_from_filename(
    valid_dataforge: Path, filename: str, body: str
) -> None:
    _write_document(valid_dataforge, filename, body)

    _assert_valid_runtime_document(lint_path(valid_dataforge))


def test_sublevel_accepts_every_runtime_target_form(valid_dataforge: Path) -> None:
    _write_document(
        valid_dataforge,
        "runtime.sublevel.yml",
        """\
type: sublevel
block:
  - /ExampleMod/Data/DA_Sublevel.DA_Sublevel
  - target: /ExampleMod/Data/DA_OtherSublevel.DA_OtherSublevel
  - target:
      - /ExampleMod/Data/DA_First.DA_First
      - /ExampleMod/Data/DA_Second.DA_Second
  - allAssetsOfClass: /Script/RefinedRDLib.RRDLSublevelAsset
  - target: /ExampleMod/Data/DA_Combined.DA_Combined
    allAssetsOfClass: /Script/KBFL.KBFLSubLevelSpawning
""",
    )

    _assert_valid_runtime_document(lint_path(valid_dataforge))


@pytest.mark.parametrize(
    ("block_yaml", "error_path"),
    [
        ("[]", "$.block"),
        ("{}", "$.block"),
        ("\n  - ''", "$.block[0]"),
        ("\n  - {}", "$.block[0]"),
        ("\n  - target: []", "$.block[0]"),
        ("\n  - target: 42", "$.block[0]"),
        ("\n  - allAssetsOfClass: ''", "$.block[0]"),
    ],
)
def test_sublevel_rejects_invalid_runtime_grammar(
    valid_dataforge: Path, block_yaml: str, error_path: str
) -> None:
    _write_document(
        valid_dataforge,
        "invalid.sublevel.yml",
        f"type: sublevel\nblock: {block_yaml}\n",
    )

    _assert_schema_error(lint_path(valid_dataforge), error_path)


def test_resourcenode_accepts_shorthand_defaults_and_full_options(valid_dataforge: Path) -> None:
    _write_document(
        valid_dataforge,
        "runtime.resourcenode.yml",
        """\
type: resourcenode
remove:
  - /Game/FactoryGame/Resource/RawResources/Iron/Desc_OreIron.Desc_OreIron_C
  - resource: /Game/FactoryGame/Resource/RawResources/Copper/Desc_OreCopper.Desc_OreCopper_C
  - resource: /Game/FactoryGame/Resource/RawResources/Coal/Desc_Coal.Desc_Coal_C
    nodeTypes: []
  - resource: /Game/FactoryGame/Resource/RawResources/Water/Desc_Water.Desc_Water_C
    nodeTypes:
      - Node
      - EResourceNodeType::FrackingSatellite
      - FrackingCore
      - Geyser
      - Deposit
    allowOccupied: true
    removeFromScanner: false
""",
    )

    _assert_valid_runtime_document(lint_path(valid_dataforge))


@pytest.mark.parametrize(
    ("remove_yaml", "error_path"),
    [
        ("[]", "$.remove"),
        ("{}", "$.remove"),
        ("\n  - ''", "$.remove[0]"),
        ("\n  - {}", "$.remove[0]"),
        ("\n  - resource: ''", "$.remove[0]"),
        ("\n  - resource: /Game/FactoryGame/Desc.Desc_C\n    nodeTypes: Node", "$.remove[0]"),
        ("\n  - resource: /Game/FactoryGame/Desc.Desc_C\n    nodeTypes: [Invalid]", "$.remove[0]"),
        ("\n  - resource: /Game/FactoryGame/Desc.Desc_C\n    allowOccupied: 'yes'", "$.remove[0]"),
        ("\n  - resource: /Game/FactoryGame/Desc.Desc_C\n    removeFromScanner: 'no'", "$.remove[0]"),
        ("\n  - resource: /Game/FactoryGame/Desc.Desc_C\n    unexpected: true", "$.remove[0]"),
    ],
)
def test_resourcenode_rejects_invalid_runtime_grammar(
    valid_dataforge: Path, remove_yaml: str, error_path: str
) -> None:
    _write_document(
        valid_dataforge,
        "invalid.resourcenode.yml",
        f"type: resourcenode\nremove: {remove_yaml}\n",
    )

    _assert_schema_error(lint_path(valid_dataforge), error_path)


CONTENT_ROOTS = [
    ("recipe", "recipes", "/Game/FactoryGame/Recipes/Recipe_Test.Recipe_Test_C"),
    ("schematic", "schematics", "/Game/FactoryGame/Schematics/Schematic_Test.Schematic_Test_C"),
    ("research", "research", "/Game/FactoryGame/Research/Tree_Test.Tree_Test_C"),
]


@pytest.mark.parametrize(("root_type", "entries_key", "class_path"), CONTENT_ROOTS)
def test_content_removal_accepts_removal_only_document(
    valid_dataforge: Path, root_type: str, entries_key: str, class_path: str
) -> None:
    _write_document(
        valid_dataforge,
        f"remove-only.{root_type}.yml",
        f"type: {root_type}\nremove:\n  - {class_path}\n",
    )

    _assert_valid_runtime_document(lint_path(valid_dataforge))


@pytest.mark.parametrize(("root_type", "entries_key", "class_path"), CONTENT_ROOTS)
def test_content_removal_accepts_mixed_registration_and_removal(
    valid_dataforge: Path, root_type: str, entries_key: str, class_path: str
) -> None:
    _write_document(
        valid_dataforge,
        f"mixed.{root_type}.yml",
        (
            f"type: {root_type}\n"
            f"{entries_key}:\n"
            f"  - class: {class_path}\n"
            "remove:\n"
            f"  - {class_path}\n"
        ),
    )

    _assert_valid_runtime_document(lint_path(valid_dataforge))


def test_content_removal_accepts_mam_alias(valid_dataforge: Path) -> None:
    _write_document(
        valid_dataforge,
        "remove-only.mam.yml",
        """\
type: mam
remove:
  - /Game/FactoryGame/Research/Tree_Test.Tree_Test_C
""",
    )

    _assert_valid_runtime_document(lint_path(valid_dataforge))


@pytest.mark.parametrize(("root_type", "entries_key", "class_path"), CONTENT_ROOTS)
@pytest.mark.parametrize("ignored_entries", ["[]", "not-a-sequence"])
def test_content_removal_accepts_runtime_ignored_empty_or_nonsequence_entries(
    valid_dataforge: Path,
    root_type: str,
    entries_key: str,
    class_path: str,
    ignored_entries: str,
) -> None:
    _write_document(
        valid_dataforge,
        f"ignored-entries.{root_type}.yml",
        (
            f"type: {root_type}\n"
            f"{entries_key}: {ignored_entries}\n"
            "remove:\n"
            f"  - {class_path}\n"
        ),
    )

    _assert_valid_runtime_document(lint_path(valid_dataforge))


@pytest.mark.parametrize(("root_type", "entries_key", "class_path"), CONTENT_ROOTS)
def test_content_removal_requires_entries_or_remove(
    valid_dataforge: Path, root_type: str, entries_key: str, class_path: str
) -> None:
    _write_document(valid_dataforge, f"empty.{root_type}.yml", f"type: {root_type}\n")

    result = lint_path(valid_dataforge)
    assert not result.ok
    _assert_schema_error(result, "$")


@pytest.mark.parametrize(("root_type", "entries_key", "class_path"), CONTENT_ROOTS)
@pytest.mark.parametrize("invalid_entries", ["[]", "not-a-sequence"])
def test_content_root_rejects_empty_or_nonsequence_entries_without_remove(
    valid_dataforge: Path,
    root_type: str,
    entries_key: str,
    class_path: str,
    invalid_entries: str,
) -> None:
    _write_document(
        valid_dataforge,
        f"invalid-entries.{root_type}.yml",
        f"type: {root_type}\n{entries_key}: {invalid_entries}\n",
    )

    result = lint_path(valid_dataforge)
    assert not result.ok
    _assert_schema_error(result, "$")


@pytest.mark.parametrize(("root_type", "entries_key", "class_path"), CONTENT_ROOTS)
@pytest.mark.parametrize(
    ("remove_yaml", "error_path", "validator"),
    [
        ("[]", "$.remove", "minItems"),
        ("not-a-sequence", "$.remove", "type"),
        ("\n  - ''", "$.remove[0]", "minLength"),
        ("\n  - {class: /Game/FactoryGame/Example.Example_C}", "$.remove[0]", "type"),
    ],
)
def test_content_removal_rejects_non_scalar_or_empty_references(
    valid_dataforge: Path,
    root_type: str,
    entries_key: str,
    class_path: str,
    remove_yaml: str,
    error_path: str,
    validator: str,
) -> None:
    _write_document(
        valid_dataforge,
        f"invalid-remove.{root_type}.yml",
        (
            f"type: {root_type}\n"
            f"{entries_key}:\n"
            f"  - class: {class_path}\n"
            f"remove: {remove_yaml}\n"
        ),
    )

    _assert_schema_error(lint_path(valid_dataforge), error_path, validator)
