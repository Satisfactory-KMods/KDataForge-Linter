from pathlib import Path

import pytest
import yaml

from kdataforge_linter.validator import lint_path


def write_patch(pack: Path, name: str, operation: dict) -> None:
    path = pack / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({
        "type": "cdo",
        "patches": [{"target": "/Game/Example.Example_C", "properties": [operation]}],
    }), encoding="utf-8")


@pytest.mark.parametrize("value", ["/Example/Desc_Item.Desc_Item_C", [1, 2], [], [{"Amount": 2}]])
def test_append_unique_accepts_runtime_values(valid_dataforge: Path, value: object) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    write_patch(pack, "unique.cdo.yml", {"path": "mItems", "op": "append_unique", "value": value})
    result = lint_path(valid_dataforge)
    assert result.ok, [d.to_dict() for d in result.errors]


def test_append_unique_requires_value(valid_dataforge: Path) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    write_patch(pack, "unique.cdo.yml", {"path": "mItems", "op": "append_unique"})
    result = lint_path(valid_dataforge)
    assert any("requires 'value'" in d.message for d in result.errors)


@pytest.mark.parametrize("value", [{"class": "/Script/Example.Item"}, [{"class": "/Script/Example.Item"}]])
def test_append_unique_rejects_inline_instances(valid_dataforge: Path, value: object) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    write_patch(pack, "unique.cdo.yml", {"path": "mItems", "op": "append_unique", "value": value})
    result = lint_path(valid_dataforge)
    assert any("inline instanced objects require append" in d.message for d in result.errors)


def test_nested_include_resolves_from_pack_root(valid_dataforge: Path) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    write_patch(pack, "base/first.cdo.yml", {"path": "mValue", "value": 1})
    write_patch(pack, "overrides/last.cdo.yml", {"path": "mValue", "value": 2})
    path = pack / "overrides/last.cdo.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["include"] = ["base/first.cdo.yml"]
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    result = lint_path(valid_dataforge)
    assert result.ok, [d.to_dict() for d in result.errors]


def test_include_cannot_escape_to_another_pack(valid_dataforge: Path) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    other = valid_dataforge / "Other"
    other.mkdir()
    (other / "pack.yml").write_text(
        "ref: Other\nname: Other\nversion: 1.0.0\ncontributer: ExampleAuthor\n", encoding="utf-8"
    )
    write_patch(other, "first.cdo.yml", {"path": "mValue", "value": 1})
    path = pack / "balance.cdo.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["include"] = ["../Other/first.cdo.yml"]
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    result = lint_path(valid_dataforge)
    assert any("include escapes pack root" in d.message for d in result.errors)
