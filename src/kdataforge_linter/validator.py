from __future__ import annotations

import contextlib
import io
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import yaml

from kdataforge_linter import legacy
from kdataforge_linter.class_catalog import ClassCatalog, ClassFamily
from kdataforge_linter.models import Diagnostic, LintResult
from kdataforge_linter.schema_registry import SchemaRegistry

BUILTIN_TYPES = {
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
    "recipe",
    "research",
    "resource",
    "schematic",
    "sinkpoints",
    "unlock",
}


def _yaml_path(parts: Sequence[object]) -> str:
    value = "$"
    for part in parts:
        if isinstance(part, int):
            value += f"[{part}]"
        else:
            value += f".{part}"
    return value


def _node_at_path(node: yaml.Node | None, parts: Sequence[object]) -> yaml.Node | None:
    current = node
    for part in parts:
        if isinstance(current, yaml.MappingNode):
            match = next(
                (value for key, value in current.value if isinstance(key, yaml.ScalarNode) and key.value == str(part)),
                None,
            )
            current = match
        elif isinstance(current, yaml.SequenceNode) and isinstance(part, int) and 0 <= part < len(current.value):
            current = current.value[part]
        else:
            return current
    return current


def _infer_type(path: Path, document: dict[str, Any], multi_document: bool) -> str | None:
    explicit = document.get("type")
    if isinstance(explicit, str) and explicit.strip():
        normalized = explicit.strip().casefold()
        return "research" if normalized == "mam" else normalized
    if multi_document:
        return None
    lower_name = path.name.casefold()
    for kind in sorted(BUILTIN_TYPES, key=len, reverse=True):
        if lower_name.endswith(f".{kind}.yml") or lower_name.endswith(f".{kind}.yaml"):
            return "research" if kind == "mam" else kind
    return None


def _legacy_diagnostic(raw: str, severity: str, candidates: Sequence[Path]) -> Diagnostic:
    for candidate in candidates:
        prefix = f"{candidate}: "
        if raw.startswith(prefix):
            return Diagnostic(severity=severity, code="semantic", file=candidate, message=raw[len(prefix) :])  # type: ignore[arg-type]
    return Diagnostic(severity=severity, code="semantic", message=raw)  # type: ignore[arg-type]


def lint_path(
    root: Path,
    schema_directories: Iterable[Path] = (),
    allow_schema_override: bool = False,
    allow_unknown_types: bool = False,
) -> LintResult:
    root = root.resolve()
    registry = SchemaRegistry(schema_directories, allow_schema_override)
    class_catalog = ClassCatalog()
    result = LintResult()
    if not root.is_dir():
        result.diagnostics.append(Diagnostic("error", "root.missing", "DataForge root does not exist", root))
        return result

    candidates = sorted(
        (path.resolve() for path in root.rglob("*") if path.is_file()), key=lambda item: len(str(item)), reverse=True
    )
    semantic = legacy.Linter(root)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        semantic.run()
    result.pack_count = len(semantic.manifests)
    result.document_count = semantic.document_count
    result.diagnostics.extend(_legacy_diagnostic(item, "warning", candidates) for item in semantic.warnings)
    result.diagnostics.extend(_legacy_diagnostic(item, "error", candidates) for item in semantic.errors)

    for manifest in sorted(root.rglob("pack.yml")):
        _validate_file_documents(
            manifest, registry, result, forced_kind="pack", allow_unknown_types=allow_unknown_types
        )
    for path in sorted(root.rglob("*.yml")) + sorted(root.rglob("*.yaml")):
        if path.name == "pack.yml":
            continue
        _validate_file_documents(
            path,
            registry,
            result,
            class_catalog=class_catalog,
            allow_unknown_types=allow_unknown_types,
        )

    result.diagnostics.sort(
        key=lambda item: (
            str(item.file or ""),
            item.document if item.document is not None else -1,
            item.line if item.line is not None else -1,
            item.severity,
            item.code,
            item.message,
        )
    )
    return result


def _validate_file_documents(
    path: Path,
    registry: SchemaRegistry,
    result: LintResult,
    forced_kind: str | None = None,
    class_catalog: ClassCatalog | None = None,
    allow_unknown_types: bool = False,
) -> None:
    try:
        text = path.read_text(encoding="utf-8")
        documents = list(yaml.safe_load_all(text))
        nodes = list(yaml.compose_all(text))
    except (OSError, yaml.YAMLError):
        return
    multi_document = len([item for item in documents if item is not None]) > 1
    for index, document in enumerate(documents):
        if document is None or not isinstance(document, dict):
            continue
        kind = forced_kind or _infer_type(path, document, multi_document)
        if kind is None:
            continue
        entry = registry.validator_for(kind)
        if entry is None:
            result.diagnostics.append(
                Diagnostic(
                    "warning" if allow_unknown_types else "error",
                    "schema.unknown-type",
                    f"no schema registered for root type {kind!r}",
                    path,
                    index,
                )
            )
            continue
        validator, loaded = entry
        node = nodes[index] if index < len(nodes) else None
        for error in sorted(validator.iter_errors(document), key=lambda item: (list(item.absolute_path), item.message)):
            parts = list(error.absolute_path)
            source_node = _node_at_path(node, parts)
            result.diagnostics.append(
                Diagnostic(
                    "error",
                    f"schema.{error.validator}",
                    error.message,
                    path,
                    index,
                    _yaml_path(parts),
                    source_node.start_mark.line + 1 if source_node else None,
                    source_node.start_mark.column + 1 if source_node else None,
                    loaded.path.name,
                )
            )
        if class_catalog is not None:
            _validate_instanced_class_references(document, kind, path, index, node, class_catalog, result)


def _validate_instanced_class_references(
    document: dict[str, Any],
    kind: str,
    path: Path,
    document_index: int,
    node: yaml.Node | None,
    catalog: ClassCatalog,
    result: LintResult,
) -> None:
    def warn(family: ClassFamily, class_path: object, parts: list[object]) -> None:
        if not isinstance(class_path, str) or not class_path.strip():
            return
        value = class_path.strip()
        if value.startswith("/KDataForge/Gen/") or ("/" not in value and "." not in value):
            return
        entry = catalog.lookup(value)
        code: str | None = None
        message: str | None = None
        if entry is None:
            code = "class.unknown"
            message = f"{family} class {value!r} is not in the bundled Unreal class catalog; runtime will verify it"
        elif entry.family != family:
            code = "class.wrong-family"
            message = f"{value!r} is a {entry.family} class, not a {family} class"
        elif entry.path.startswith("/Script/") and entry.blueprint:
            code = "class.native-remapped"
            message = f"native class {value!r} is remapped at runtime to concrete Blueprint {entry.blueprint!r}"
        elif entry.abstract:
            code = "class.abstract-no-blueprint"
            message = f"abstract {family} class {value!r} has no known concrete Blueprint variant"
        if code is None or message is None:
            return
        source_node = _node_at_path(node, parts)
        result.diagnostics.append(
            Diagnostic(
                "warning",
                code,
                message,
                path,
                document_index,
                _yaml_path(parts),
                source_node.start_mark.line + 1 if source_node else None,
                source_node.start_mark.column + 1 if source_node else None,
            )
        )

    def validate_list(value: object, family: ClassFamily, parts: list[object]) -> None:
        if not isinstance(value, list):
            return
        for index, entry in enumerate(value):
            if isinstance(entry, dict):
                warn(family, entry.get("class"), [*parts, index, "class"])

    if kind == "unlock":
        for index, entry in enumerate(document.get("unlocks", [])):
            if isinstance(entry, dict):
                warn("unlock", entry.get("parent"), ["unlocks", index, "parent"])
    elif kind == "schematic":
        for index, entry in enumerate(document.get("schematics", [])):
            if not isinstance(entry, dict):
                continue
            validate_list(entry.get("unlocks"), "unlock", ["schematics", index, "unlocks"])
            validate_list(entry.get("dependencies"), "dependency", ["schematics", index, "dependencies"])
    elif kind == "research":
        for index, entry in enumerate(document.get("research", [])):
            if not isinstance(entry, dict):
                continue
            validate_list(
                entry.get("unlockDependencies"),
                "dependency",
                ["research", index, "unlockDependencies"],
            )
            validate_list(
                entry.get("visibilityDependencies"),
                "dependency",
                ["research", index, "visibilityDependencies"],
            )
    elif kind == "dataasset":
        for index, entry in enumerate(document.get("assets", [])):
            if not isinstance(entry, dict):
                continue
            validate_list(entry.get("unlocks"), "unlock", ["assets", index, "unlocks"])
            validate_list(entry.get("dependencies"), "dependency", ["assets", index, "dependencies"])

    property_families: dict[str, ClassFamily] = {
        "mUnlocks": "unlock",
        "mSchematicDependencies": "dependency",
        "mUnlockDependencies": "dependency",
        "mVisibilityDependencies": "dependency",
        "mTaskDependencies": "dependency",
    }

    def scan_properties(value: object, parts: list[object]) -> None:
        if isinstance(value, list):
            for index, child in enumerate(value):
                scan_properties(child, [*parts, index])
            return
        if not isinstance(value, dict):
            return
        property_path = value.get("path")
        if isinstance(property_path, str):
            field = property_path.rsplit(".", 1)[-1]
            family = property_families.get(field)
            if family is not None:
                raw = value.get("value")
                validate_list(raw if isinstance(raw, list) else [raw], family, [*parts, "value"])
        for key, child in value.items():
            scan_properties(child, [*parts, key])

    scan_properties(document, [])
