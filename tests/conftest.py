from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def valid_dataforge(tmp_path: Path) -> Path:
    root = tmp_path / "DataForge"
    pack = root / "Example"
    pack.mkdir(parents=True)
    (pack / "pack.yml").write_text(
        "\n".join(
            [
                "ref: Example",
                "name: Example Pack",
                "version: 1.0.0",
                "contributer: ExampleAuthor",
            ]
        ),
        encoding="utf-8",
    )
    (pack / "balance.cdo.yml").write_text(
        "\n".join(
            [
                "type: cdo",
                "patches:",
                "  - target: /Game/Example.Example_C",
                "    properties:",
                "      - path: mValue",
                "        value: 2",
            ]
        ),
        encoding="utf-8",
    )
    return root
