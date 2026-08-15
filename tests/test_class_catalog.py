from __future__ import annotations

from kdataforge_linter.class_catalog import ClassCatalog


def test_catalog_contains_complete_unreal_inventory_snapshot() -> None:
    catalog = ClassCatalog()

    unlocks = catalog.entries("unlock")
    dependencies = catalog.entries("dependency")

    assert len([entry for entry in unlocks if entry.path.startswith("/Script/")]) == 39
    assert len([entry for entry in unlocks if not entry.path.startswith("/Script/")]) == 31
    assert len([entry for entry in dependencies if entry.path.startswith("/Script/")]) == 33
    assert len([entry for entry in dependencies if not entry.path.startswith("/Script/")]) == 17


def test_catalog_records_abstract_flags_blueprints_and_mod_classes() -> None:
    catalog = ClassCatalog()

    base = catalog.lookup("/Script/FactoryGame.FGUnlock")
    assert base is not None
    assert base.abstract is True
    assert base.blueprint is None
    assert base.blueprints == (
        "/AB_FluidExtras/Exhausts/Func/ABUnlock_UnsafeExhaust.ABUnlock_UnsafeExhaust_C",
    )

    recipe = catalog.lookup("/Script/FactoryGame.FGUnlockRecipe")
    assert recipe is not None
    assert recipe.abstract is True
    assert recipe.blueprint == "/Game/FactoryGame/Unlocks/BP_UnlockRecipe.BP_UnlockRecipe_C"

    tape = catalog.lookup("/Script/FactoryGame.FGUnlockTape")
    assert tape is not None
    assert tape.abstract is False
    assert tape.blueprint is None

    unavailable = catalog.lookup("/Script/FactoryGame.FGRecipeUnlockedDependency")
    assert unavailable is not None
    assert unavailable.abstract is True
    assert unavailable.blueprint is None

    mod_unlock = catalog.lookup("/Script/KPrivateCodeLib.KPCLFaxitSpeedUnlock")
    assert mod_unlock is not None
    assert mod_unlock.source == "KPrivateCodeLib"
    assert mod_unlock.blueprint == (
        "/KPrivateCodeLib/Unlocks/BP_FaxitSpeedUnlock.BP_FaxitSpeedUnlock_C"
    )

    blueprint_only = catalog.lookup(
        "/AB_FluidExtras/Exhausts/Func/ABUnlock_UnsafeExhaust.ABUnlock_UnsafeExhaust_C"
    )
    assert blueprint_only is not None
    assert blueprint_only.family == "unlock"
    assert blueprint_only.source == "AB_FluidExtras"


def test_catalog_normalizes_blueprint_asset_and_generated_class_forms() -> None:
    catalog = ClassCatalog()
    full = "/Game/FactoryGame/Unlocks/BP_UnlockRecipe.BP_UnlockRecipe_C"

    assert catalog.lookup(full) == catalog.lookup("/Game/FactoryGame/Unlocks/BP_UnlockRecipe")
    assert catalog.lookup(full) == catalog.lookup("/Game/FactoryGame/Unlocks/BP_UnlockRecipe.BP_UnlockRecipe")
