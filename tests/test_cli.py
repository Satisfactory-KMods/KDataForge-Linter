from __future__ import annotations

import json
from pathlib import Path

from kdataforge_linter.cli import main


def test_cli_json_output(valid_dataforge: Path, capsys: object) -> None:
    assert main(["lint", str(valid_dataforge), "--format", "json"]) == 0
    output = capsys.readouterr().out
    data = json.loads(output)
    assert data["ok"] is True
    assert data["packs"] == 1


def test_cli_validation_failure(valid_dataforge: Path) -> None:
    next(valid_dataforge.rglob("*.cdo.yml")).write_text("type: cdo\npatches: []\n", encoding="utf-8")
    assert main(["lint", str(valid_dataforge)]) == 1


def test_schema_check(capsys: object) -> None:
    assert main(["schemas", "check"]) == 0
    assert "schemas valid" in capsys.readouterr().out
