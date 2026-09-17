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
        "resourcenode",
        "schematic",
        "sinkpoints",
        "sublevel",
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


def test_pack_allows_description_metadata(valid_dataforge: Path) -> None:
    manifest = next(valid_dataforge.rglob("pack.yml"))
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "\ndescription: Human-readable pack summary.\n",
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
    # Patch entries compose the shared scope-filter keys via allOf/$ref, so unknown keys surface
    # as unevaluatedProperties rather than additionalProperties.
    assert any(
        item.code == "schema.unevaluatedProperties" and item.yaml_path == "$.patches[0]" for item in result.errors
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


@pytest.mark.parametrize(
    ("root_type", "entries_key", "removed_class"),
    [
        ("recipe", "recipes", "/Game/FactoryGame/Recipes/Constructor/Recipe_IronPlate.Recipe_IronPlate_C"),
        ("schematic", "schematics", "/Game/FactoryGame/Schematics/Progression/Schematic_1-1.Schematic_1-1_C"),
        ("research", "research", "/Game/FactoryGame/Schematics/MAM/Trees/Quartz/Research_Quartz.Research_Quartz_C"),
    ],
)
def test_content_roots_allow_remove_only_documents(
    valid_dataforge: Path, root_type: str, entries_key: str, removed_class: str
) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    (pack / f"remove-only.{root_type}.yml").write_text(
        "\n".join(
            [
                f"type: {root_type}",
                "remove:",
                f"  - {removed_class}",
            ]
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.diagnostics]


def test_schematic_allows_entries_and_document_remove_together(valid_dataforge: Path) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    (pack / "replace.schematic.yml").write_text(
        "\n".join(
            [
                "type: schematic",
                "remove:",
                "  - /Game/FactoryGame/Schematics/Progression/Schematic_1-1.Schematic_1-1_C",
                "schematics:",
                "  - id: ReplacementSchematic",
                "    parent: /Script/FactoryGame.FGSchematic",
            ]
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.diagnostics]


def test_sublevel_documents_accept_scalar_and_selector_blocks(valid_dataforge: Path) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    (pack / "world.sublevel.yml").write_text(
        "\n".join(
            [
                "type: sublevel",
                "block:",
                "  - /RefinedPower/World/Sublevels/Example.Example",
                "  - target:",
                "      - /KBFL/World/Sublevels/Example.Example",
                "    allAssetsOfClass: /Script/KBFL.KBFLSubLevelSpawning",
            ]
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.diagnostics]


def test_resourcenode_documents_accept_scalar_and_option_maps(valid_dataforge: Path) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    (pack / "nodes.resourcenode.yml").write_text(
        "\n".join(
            [
                "type: resourcenode",
                "remove:",
                "  - /Game/FactoryGame/Resource/RawResources/Iron/Desc_Iron.Desc_Iron_C",
                "  - resource: /Game/FactoryGame/Resource/RawResources/Coal/Desc_Coal.Desc_Coal_C",
                "    nodeTypes:",
                "      - Node",
                "      - EResourceNodeType::Geyser",
                "    allowOccupied: false",
                "    removeFromScanner: true",
            ]
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.diagnostics]


def test_cdo_patch_allows_combined_runtime_selectors(valid_dataforge: Path) -> None:
    document = next(valid_dataforge.rglob("*.cdo.yml"))
    document.write_text(
        "\n".join(
            [
                "type: cdo",
                "patches:",
                "  - target: /Game/Example.Example_C",
                "    allAssetsOfClass: /Script/FactoryGame.FGItemDescriptor",
                "    properties:",
                "      - path: mValue",
                "        value: 2",
            ]
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.diagnostics]


def test_cdo_patch_allows_scope_filters(valid_dataforge: Path) -> None:
    document = next(valid_dataforge.rglob("*.cdo.yml"))
    document.write_text(
        "\n".join(

            [
                "type: cdo",
                "patches:",
                "  - producedIn: Build_ConstructorMk1_C",
                "    properties:",
                "      - path: mManufactoringDuration",
                "        op: multiply",
                "        value: 0.5",
                "  - ingredient: [Desc_IronIngot_C, Desc_CopperIngot_C]",
                "    product: Desc_IronPlate_C",
                "    ofClass: /Script/FactoryGame.FGRecipe",
                "    properties:",
                "      - path: mManufactoringDuration",
                "        value: 2",
                "  - ofClass: /Script/FactoryGame.FGRecipe",
                "    matchName: Recipe_Alternate_*",
                "    where:",
                "      - path: mManufactoringDuration",
                "        greaterThan: 4",
                "      - path: mIngredients[*].ItemClass",
                "        equals: Desc_IronIngot_C",
                "      - path: mProducedIn",
                "        isEmpty: false",
                "      - path: mDisplayName",
                "        matches: '*Alternate*'",
                "    properties:",
                "      - path: mManufactoringDuration",
                "        op: multiply",
                "        value: 0.8",
                "  - ofClass: /Script/FactoryGame.FGSchematic",
                "    where:",
                "      path: mTechTier",
                "      lessOrEqual: 3",
                "    properties:",
                "      - path: mTimeToComplete",
                "        value: 1",
                "  - producedIn: /Script/FactoryGame.FGBuildGun",
                "    where:",
                "      path: mIngredients",
                "      isEmpty: false",
                "    properties:",
                "      - path: mIngredients[0].Amount",
                "        op: multiply",
                "        value: 0.8",
                "  - ofClass: /Script/FactoryGame.FGItemDescriptor",
                "    where:",
                "      - path: mForm",
                "        in: [RF_LIQUID, RF_GAS]",
                "      - path: mProducedIn",
                "        notIn: [Build_ConstructorMk1_C]",
                "    properties:",
                "      - path: mResourceSinkPoints",
                "        value: 0",
            ]
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.diagnostics]


@pytest.mark.parametrize(
    ("patch_lines", "expected_message"),
    [
        # matchName / where need an explicit ofClass scope
        (["  - matchName: Recipe_*"], "matchName requires ofClass"),
        (
            ["  - ofClass: /Script/FactoryGame.FGRecipe", "    where:", "      path: mTechTier"],
            "needs exactly one operator",
        ),
        # exactly one operator per where clause
        (
            [
                "  - ofClass: /Script/FactoryGame.FGRecipe",
                "    where:",
                "      path: mTechTier",
                "      equals: 1",
                "      lessThan: 3",
            ],
            "needs exactly one operator",
        ),
        # numeric operators take numbers
        (
            ["  - ofClass: /Script/FactoryGame.FGRecipe", "    where:", "      path: mTechTier", "      lessThan: abc"],
            "lessThan must be a finite number",
        ),
        # unknown where key
        (
            ["  - ofClass: /Script/FactoryGame.FGRecipe", "    where:", "      path: mTechTier", "      like: abc"],
            "like is not a where operator",
        ),
        # `[*]` is accepted, other junk in a path is not
        (
            [
                "  - ofClass: /Script/FactoryGame.FGRecipe",
                "    where:",
                "      path: mIngredients[*]..ItemClass",
                "      equals: Desc_IronIngot_C",
            ],
            "path is not a valid property path",
        ),
    ],
)
def test_cdo_scope_filters_reject_malformed_input(
    valid_dataforge: Path, patch_lines: list[str], expected_message: str
) -> None:
    document = next(valid_dataforge.rglob("*.cdo.yml"))
    document.write_text(
        "\n".join(
            [
                "type: cdo",
                "patches:",
                *patch_lines,
                "    properties:",
                "      - path: mValue",
                "        value: 2",
            ]
        ),
        encoding="utf-8",
    )

    result = lint_path(valid_dataforge)
    assert not result.ok
    # The semantic pass carries the precise, user-facing reason (the JSON schema's `oneOf`
    # wrapper around `where` only reports "not valid under any of the given schemas").
    assert any(expected_message in item.message for item in result.errors), [
        item.to_dict() for item in result.diagnostics
    ]


@pytest.mark.parametrize(
    ("filename", "body"),
    [
        (
            "prune.recipe.yml",
            "\n".join(
                [
                    "type: recipe",
                    "remove:",
                    "  - Recipe_IronPlateReinforced_C",
                    "  - producedIn: Build_ConstructorMk1_C",
                    "    ingredient: Desc_IronIngot_C",
                    "  - ofClass: /Script/FactoryGame.FGRecipe",
                    "    matchName: Recipe_Alternate_*",
                    "    where:",
                    "      path: mManufactoringDuration",
                    "      greaterThan: 10",
                ]
            ),
        ),
        (
            "prune.schematic.yml",
            "\n".join(
                [
                    "type: schematic",
                    "remove:",
                    "  - where: # scope defaults to FGSchematic",
                    "      path: mTechTier",
                    "      greaterOrEqual: 8",
                    "  - matchName: Schematic_Alternate_*",
                ]
            ),
        ),
        (
            "prune.research.yml",
            "\n".join(
                [
                    "type: research",
                    "remove:",
                    "  - ofClass: /Script/FactoryGame.FGResearchTree",
                    "    matchName: /Game/SomeMod/*",
                ]
            ),
        ),
        (
            "prune.resourcenode.yml",
            "\n".join(
                [
                    "type: resourcenode",
                    "remove:",
                    "  - ofClass: /Script/FactoryGame.FGResourceDescriptor",
                    "    matchName: Desc_OreUranium*",
                    "    nodeTypes: [Node]",
                    "    allowOccupied: true",
                ]
            ),
        ),
        (
            "prune.sublevel.yml",
            "\n".join(
                [
                    "type: sublevel",
                    "block:",
                    "  - ofClass: /Script/RefinedRDLib.RRDLSublevelAsset",
                    "    matchName: DA_Optional_*",
                ]
            ),
        ),
        (
            "points.sinkpoints.yml",
            "\n".join(
                [
                    "type: sinkpoints",
                    "entries:",
                    "  - item: Desc_IronPlate_C",
                    "    points: 6",
                    "  - where: # scope defaults to FGItemDescriptor",
                    "      path: mForm",
                    "      in: [RF_LIQUID, RF_GAS]",
                    "    points: 0",
                ]
            ),
        ),
    ],
)
def test_scope_filters_are_accepted_by_every_selecting_type(valid_dataforge: Path, filename: str, body: str) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    (pack / filename).write_text(body, encoding="utf-8")

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.diagnostics]


@pytest.mark.parametrize(
    ("filename", "body", "expected_message"),
    [
        (
            "bad.recipe.yml",
            "type: recipe\nremove:\n  - ofClass: /Script/FactoryGame.FGRecipe\n",
            "map entries need a filter",
        ),
        (
            "bad.sublevel.yml",
            "type: sublevel\nblock:\n  - matchName: DA_*\n",
            "filters require ofClass",
        ),
        (
            "bad.sinkpoints.yml",
            "type: sinkpoints\nentries:\n  - points: 3\n",
            "requires item or a filter",
        ),
    ],
)
def test_scope_filter_forms_reject_missing_selectors(
    valid_dataforge: Path, filename: str, body: str, expected_message: str
) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    (pack / filename).write_text(body, encoding="utf-8")

    result = lint_path(valid_dataforge)
    assert not result.ok
    assert any(expected_message in item.message for item in result.errors), [
        item.to_dict() for item in result.diagnostics
    ]


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
