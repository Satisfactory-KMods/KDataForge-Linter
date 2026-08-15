from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any, Literal

ClassFamily = Literal["unlock", "dependency"]


@dataclass(frozen=True, slots=True)
class ClassCatalogEntry:
    family: ClassFamily
    name: str
    path: str
    parent: str | None
    abstract: bool
    blueprint: str | None
    blueprints: tuple[str, ...]
    source: str
    source_file: str


def _normalize_class_path(path: str) -> str:
    value = path.strip()
    if "'" in value:
        parts = value.split("'", 2)
        if len(parts) > 1:
            value = parts[1]
    if value.startswith("/") and not value.startswith("/Script/"):
        if "." not in value.rsplit("/", 1)[-1]:
            asset = value.rsplit("/", 1)[-1]
            value = f"{value}.{asset}_C"
        elif not value.endswith("_C"):
            value += "_C"
    return value.casefold()


class ClassCatalog:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            resource = files("kdataforge_linter").joinpath("catalogs/instanced_classes.json")
            with as_file(resource) as resource_path:
                document = json.loads(resource_path.read_text(encoding="utf-8"))
        else:
            document = json.loads(path.read_text(encoding="utf-8"))
        self.schema_version = int(document["schemaVersion"])
        self.engine_version = str(document["engineVersion"])
        self._entries: dict[ClassFamily, tuple[ClassCatalogEntry, ...]] = {}
        self._lookup: dict[str, ClassCatalogEntry] = {}
        for family, family_data in document["families"].items():
            typed_family: ClassFamily = family
            entries = tuple(self._entry(typed_family, item) for item in family_data["entries"])
            self._entries[typed_family] = entries
            for entry in entries:
                self._lookup[_normalize_class_path(entry.path)] = entry

    @staticmethod
    def _entry(family: ClassFamily, item: dict[str, Any]) -> ClassCatalogEntry:
        return ClassCatalogEntry(
            family=family,
            name=str(item["name"]),
            path=str(item["path"]),
            parent=str(item["parent"]) if item.get("parent") else None,
            abstract=bool(item["abstract"]),
            blueprint=str(item["blueprint"]) if item.get("blueprint") else None,
            blueprints=tuple(str(value) for value in item.get("blueprints", [])),
            source=str(item["source"]),
            source_file=str(item["sourceFile"]),
        )

    def entries(self, family: ClassFamily) -> tuple[ClassCatalogEntry, ...]:
        return self._entries[family]

    def lookup(self, path: str) -> ClassCatalogEntry | None:
        return self._lookup.get(_normalize_class_path(path))
