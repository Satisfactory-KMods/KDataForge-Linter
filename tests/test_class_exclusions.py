from pathlib import Path

import pytest
import yaml

from kdataforge_linter.validator import lint_path


@pytest.mark.parametrize("excluded, scoped, valid", [
    ("/KLib/*", True, True),
    (["/KLib/*", "/Other/Recipe_?.Recipe_?_C", "/Game/A.A_C"], True, True),
    ("/Game/A.A_C", True, True),
    ("/KLib/*", False, False),
    ("Recipe_*", True, False),
    ([], True, False),
    ([None], True, False),
])
def test_class_exclusions_match_runtime_contract(
    valid_dataforge: Path, excluded: object, scoped: bool, valid: bool
) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    patch = {"excludeClasses": excluded, "properties": [{"path": "mValue", "value": 1}]}
    if scoped:
        patch["ofClass"] = "/Script/FactoryGame.FGRecipe"
    (pack / "exclude.cdo.yml").write_text(
        yaml.safe_dump({"type": "cdo", "patches": [patch]}), encoding="utf-8"
    )
    result = lint_path(valid_dataforge)
    assert result.ok == valid, [item.to_dict() for item in result.errors]
