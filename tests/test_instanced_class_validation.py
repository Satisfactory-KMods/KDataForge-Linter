from __future__ import annotations

from pathlib import Path

from kdataforge_linter.models import Diagnostic
from kdataforge_linter.validator import lint_path


def _write_document(root: Path, name: str, content: str) -> None:
    pack = next(root.rglob("pack.yml")).parent
    (pack / name).write_text(content, encoding="utf-8")


def _catalog_diagnostics(root: Path) -> list[Diagnostic]:
    return [item for item in lint_path(root).diagnostics if item.code.startswith("class.")]


def test_schematic_native_unlock_and_dependency_paths_warn_with_concrete_remaps(valid_dataforge: Path) -> None:
    _write_document(
        valid_dataforge,
        "progression.schematic.yml",
        """type: schematic
schematics:
  - id: Schematic_Test
    unlocks:
      - class: /Script/FactoryGame.FGUnlockRecipe
    dependencies:
      - class: /Script/FactoryGame.FGSchematicPurchasedDependency
""",
    )

    diagnostics = _catalog_diagnostics(valid_dataforge)
    assert [item.code for item in diagnostics] == ["class.native-remapped", "class.native-remapped"]
    assert diagnostics[0].yaml_path == "$.schematics[0].unlocks[0].class"
    assert diagnostics[1].yaml_path == "$.schematics[0].dependencies[0].class"
    assert all(item.severity == "warning" for item in diagnostics)


def test_concrete_blueprint_paths_pass_without_catalog_diagnostics(valid_dataforge: Path) -> None:
    _write_document(
        valid_dataforge,
        "progression.schematic.yml",
        """type: schematic
schematics:
  - id: Schematic_Test
    unlocks:
      - class: /Game/FactoryGame/Unlocks/BP_UnlockRecipe.BP_UnlockRecipe_C
    dependencies:
      - class: /Game/FactoryGame/AvailabilityDependencies/BP_SchematicPurchasedDependency
""",
    )

    assert _catalog_diagnostics(valid_dataforge) == []


def test_unknown_wrong_family_and_abstract_without_blueprint_are_warnings(valid_dataforge: Path) -> None:
    _write_document(
        valid_dataforge,
        "progression.schematic.yml",
        """type: schematic
schematics:
  - id: Schematic_Test
    unlocks:
      - class: /Script/FactoryGame.FGSchematicPurchasedDependency
      - class: /OtherMod/Unlocks/BP_Custom.BP_Custom_C
      - class: /Script/FactoryGame.FGUnlock
    dependencies:
      - class: /Script/FactoryGame.FGRecipeUnlockedDependency
""",
    )

    diagnostics = _catalog_diagnostics(valid_dataforge)
    assert {item.code for item in diagnostics} == {
        "class.abstract-no-blueprint",
        "class.unknown",
        "class.wrong-family",
    }
    assert all(item.severity == "warning" for item in diagnostics)
    assert lint_path(valid_dataforge).ok is True


def test_unlock_document_parent_is_catalog_linted(valid_dataforge: Path) -> None:
    _write_document(
        valid_dataforge,
        "reusable.unlock.yml",
        """type: unlock
unlocks:
  - id: ReusableUnlock
    parent: /Script/FactoryGame.FGUnlockInventorySlot
""",
    )

    diagnostics = _catalog_diagnostics(valid_dataforge)
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "class.native-remapped"
    assert diagnostics[0].yaml_path == "$.unlocks[0].parent"


def test_research_tree_dependency_lists_are_catalog_linted(valid_dataforge: Path) -> None:
    _write_document(
        valid_dataforge,
        "tree.research.yml",
        """type: research
research:
  - id: Research_Test
    unlockDependencies:
      - class: /Script/FactoryGame.FGItemPickedUpDependency
    visibilityDependencies:
      - class: /Script/FactoryGame.FGGamePhaseReachedDependency
""",
    )

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.errors]
    diagnostics = [item for item in result.warnings if item.code == "class.native-remapped"]
    assert [item.yaml_path for item in diagnostics] == [
        "$.research[0].unlockDependencies[0].class",
        "$.research[0].visibilityDependencies[0].class",
    ]


def test_delivery_task_unlock_and_dependency_lists_are_catalog_linted(valid_dataforge: Path) -> None:
    _write_document(
        valid_dataforge,
        "task.dataasset.yml",
        """type: dataasset
assets:
  - id: DeliveryTask_Test
    class: /Script/KAPI.KAPIDeliveryTask
    unlocks:
      - class: /Script/FactoryGame.FGUnlockSchematic
    dependencies:
      - class: /Script/FactoryGame.FGResearchTreeProgressionDependency
""",
    )

    result = lint_path(valid_dataforge)
    assert result.ok, [item.to_dict() for item in result.errors]
    diagnostics = [item for item in result.warnings if item.code == "class.native-remapped"]
    assert [item.yaml_path for item in diagnostics] == [
        "$.assets[0].unlocks[0].class",
        "$.assets[0].dependencies[0].class",
    ]
