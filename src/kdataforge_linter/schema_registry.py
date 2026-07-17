from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource


class SchemaRegistryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LoadedSchema:
    kind: str
    path: Path
    document: dict[str, Any]


class SchemaRegistry:
    def __init__(
        self,
        external_directories: Iterable[Path] = (),
        allow_override: bool = False,
    ) -> None:
        self.schemas: dict[str, LoadedSchema] = {}
        self._store: dict[str, dict[str, Any]] = {}
        package_schemas = files("kdataforge_linter").joinpath("schemas")
        with as_file(package_schemas) as schema_path:
            self._load_directory(schema_path, built_in=True, allow_override=False)
        for directory in external_directories:
            self._load_directory(directory.resolve(), built_in=False, allow_override=allow_override)
        self._validate_references()
        self._registry = Registry().with_resources(
            (schema_id, Resource.from_contents(document)) for schema_id, document in self._store.items()
        )

    def _load_directory(self, directory: Path, built_in: bool, allow_override: bool) -> None:
        if not directory.is_dir():
            raise SchemaRegistryError(f"schema directory does not exist: {directory}")
        paths = sorted(directory.glob("*.schema.yml")) + sorted(directory.glob("*.schema.yaml"))
        if not paths:
            raise SchemaRegistryError(f"no *.schema.yml files found in {directory}")
        for path in paths:
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as error:
                raise SchemaRegistryError(f"invalid schema YAML {path}: {error}") from error
            if not isinstance(raw, dict):
                raise SchemaRegistryError(f"schema must be a mapping: {path}")
            try:
                Draft202012Validator.check_schema(raw)
            except SchemaError as error:
                raise SchemaRegistryError(f"invalid JSON Schema {path}: {error.message}") from error
            schema_id = raw.get("$id")
            if not isinstance(schema_id, str) or not schema_id:
                raise SchemaRegistryError(f"schema requires non-empty $id: {path}")
            if schema_id in self._store and not allow_override:
                raise SchemaRegistryError(
                    f"schema id {schema_id!r} from {path} duplicates an already loaded schema; "
                    "use --allow-schema-override to replace it"
                )
            self._store[schema_id] = raw
            kind = raw.get("x-kdf-type")
            if kind is None:
                continue
            if not isinstance(kind, str) or not kind.strip():
                raise SchemaRegistryError(f"x-kdf-type must be a non-empty string: {path}")
            normalized = kind.casefold()
            if normalized in self.schemas and not allow_override:
                source = "built-in" if built_in else "external"
                raise SchemaRegistryError(
                    f"{source} schema type {kind!r} duplicates {self.schemas[normalized].path}; "
                    "use --allow-schema-override to replace it"
                )
            self.schemas[normalized] = LoadedSchema(normalized, path, raw)

    def _validate_references(self) -> None:
        def walk(value: object, source: Path) -> None:
            if isinstance(value, dict):
                reference = value.get("$ref")
                if isinstance(reference, str):
                    base = reference.split("#", 1)[0]
                    if base and base not in self._store:
                        raise SchemaRegistryError(
                            f"schema {source} references unavailable or network schema: {reference}"
                        )
                for child in value.values():
                    walk(child, source)
            elif isinstance(value, list):
                for child in value:
                    walk(child, source)

        for loaded in self.schemas.values():
            walk(loaded.document, loaded.path)

    def kinds(self) -> list[str]:
        return sorted(self.schemas)

    def validator_for(self, kind: str) -> tuple[Draft202012Validator, LoadedSchema] | None:
        loaded = self.schemas.get(kind.casefold())
        if loaded is None:
            return None
        return Draft202012Validator(loaded.document, registry=self._registry), loaded
