from pathlib import Path

import pytest
import yaml

from kdataforge_linter.validator import lint_path


@pytest.mark.parametrize(
    "value, valid",
    [
        ({"hideMeshes": ["/Game/Mesh.Mesh"]}, True),
        ({"hideMeshes": []}, False),
        ({"hideMeshes": ["/Game/Mesh.Mesh"], "meshActorsPerTick": 1024}, True),
        ({"hideMeshes": ["/Game/Mesh.Mesh"], "meshActorsPerTick": 0}, False),
        ({"hideMeshes": ["/Game/Mesh.Mesh"], "meshActorsPerTick": "1"}, False),
        ({"visuals": [{"resource": "/Game/R.R_C", "materials": [{"slot": 0, "material": "/Game/M.M"}]}]}, True),
        ({"visuals": [{"resource": "/Game/R.R_C", "materials": [{"slot": 64, "material": "/Game/M.M"}]}]}, False),
        (
            {
                "visuals": [
                    {
                        "resource": "/Game/R.R_C",
                        "materials": [{"slot": 0, "material": "/Game/M.M"}, {"slot": 0, "material": "/Game/N.N"}],
                    }
                ]
            },
            False,
        ),
    ],
)
def test_resource_visual_contract(valid_dataforge: Path, value: dict, valid: bool) -> None:
    pack = next(valid_dataforge.rglob("pack.yml")).parent
    (pack / "nodes.resourcenode.yml").write_text(yaml.safe_dump({"type": "resourcenode", **value}), encoding="utf-8")
    result = lint_path(valid_dataforge)
    assert result.ok == valid, [item.to_dict() for item in result.errors]
