#!/usr/bin/env python3
"""Static KDataForge pack/schema linter used by local development and CI."""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml

KNOWN_TYPES = {
    "asset",
    "building",
    "cdo",
    "class",
    "curve",
    "dataasset",
    "gametag",
    "item",
    "localization",
    "recipe",
    "research",
    "resource",
    "schematic",
    "sinkpoints",
    "unlock",
}
CONTENT_KEYS = {
    "building": "buildings",
    "class": "classes",
    "item": "items",
    "recipe": "recipes",
    "research": "research",
    "resource": "resources",
    "schematic": "schematics",
    "unlock": "unlocks",
}
REGISTER_AS = {"recipe", "schematic", "research"}
CURVE_INTERP_MODES = {"constant", "linear", "cubic"}
CURVE_TANGENT_MODES = {"auto", "smartauto", "user", "break"}
CURVE_TANGENT_WEIGHT_MODES = {"none", "arrive", "leave", "both"}
CURVE_EXTRAPOLATION_MODES = {"none", "constant", "linear", "cycle", "cyclewithoffset", "oscillate"}
OPS = {
    "add",
    "append",
    "clamp",
    "clear",
    "copy",
    "duplicate",
    "divide",
    "insert",
    "max",
    "min",
    "move",
    "multiply",
    "prepend",
    "remove",
    "remove_at",
    "replace",
    "reverse",
    "set",
    "sort",
    "subtract",
    "swap",
    "unique",
}
OP_REQUIRED = {
    "add": {"value"},
    "append": {"value"},
    "clamp": {"min", "max"},
    "copy": {"from"},
    "divide": {"value"},
    "duplicate": {"index"},
    "insert": {"index", "value"},
    "max": {"value"},
    "min": {"value"},
    "move": {"from"},
    "multiply": {"value"},
    "prepend": {"value"},
    "remove": {"value"},
    "remove_at": {"index"},
    "replace": {"index", "value"},
    "set": {"value"},
    "subtract": {"value"},
    "swap": {"index", "with"},
}
TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
PROPERTY_PATH = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[(?:\d+|[A-Za-z0-9_ -]+|\"[^\"]+\")\])*$"
)


class LintError(ValueError):
    pass


class Linter:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.manifests: dict[Path, dict[str, Any]] = {}
        self.refs: dict[str, Path] = {}
        self.generated_ids: dict[str, dict[str, Path]] = defaultdict(dict)
        self.document_count = 0

    def error(self, path: Path, message: str) -> None:
        self.errors.append(f"{path}: {message}")

    def warning(self, path: Path, message: str) -> None:
        self.warnings.append(f"{path}: {message}")

    def parse(self, path: Path) -> Any:
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            self.error(path, f"invalid YAML: {exc}")
            return None

    def parse_all(self, path: Path) -> list[Any] | None:
        try:
            return list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except (OSError, yaml.YAMLError) as exc:
            self.error(path, f"invalid YAML: {exc}")
            return None

    def require_map(self, value: Any, path: Path, context: str) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            self.error(path, f"{context} must be a YAML mapping")
            return None
        return value

    def require_string(self, mapping: dict[str, Any], key: str, path: Path, context: str = "") -> str | None:
        value = mapping.get(key)
        if not isinstance(value, str) or not value.strip():
            self.error(path, f"{context + ': ' if context else ''}{key} must be a non-empty string")
            return None
        return value.strip()

    def require_contributors(self, mapping: dict[str, Any], path: Path) -> None:
        value = mapping.get("contributer")
        contributors = [value] if isinstance(value, str) else value
        if not isinstance(contributors, list) or not contributors:
            self.error(path, "contributer must be a non-empty GitHub login or sequence of logins")
            return
        seen: set[str] = set()
        for contributor in contributors:
            if not isinstance(contributor, str) or not contributor.strip():
                self.error(path, "contributer entries must be non-empty GitHub logins")
                continue
            normalized = contributor.strip().casefold()
            if not TOKEN.fullmatch(contributor.strip()):
                self.error(path, f"contributer {contributor!r} contains invalid characters")
            if normalized in seen:
                self.error(path, f"duplicate contributer {contributor!r}")
            seen.add(normalized)

    def require_sequence(self, mapping: dict[str, Any], key: str, path: Path, context: str) -> list[Any] | None:
        value = mapping.get(key)
        if not isinstance(value, list) or not value:
            self.error(path, f"{context} requires a non-empty '{key}' sequence")
            return None
        return value

    def find_pack_root(self, path: Path) -> Path | None:
        current = path.parent.resolve()
        while True:
            if (current / "pack.yml").is_file():
                return current
            if current == self.root:
                return None
            if self.root not in current.parents:
                return None
            current = current.parent

    def validate_manifest(self, path: Path) -> None:
        data = self.require_map(self.parse(path), path, "pack.yml")
        if data is None:
            return
        ref = self.require_string(data, "ref", path)
        self.require_string(data, "name", path)
        version = self.require_string(data, "version", path)
        self.require_contributors(data, path)
        if ref and not TOKEN.fullmatch(ref):
            self.error(path, f"ref {ref!r} contains invalid characters")
        if version and not SEMVER.fullmatch(version):
            self.error(path, f"version {version!r} is not semver-like")
        if isinstance(data.get("priority"), bool) or not isinstance(data.get("priority", 100), int):
            self.error(path, "priority must be an integer")
        for key in ("enabled", "debug"):
            if key in data and not isinstance(data[key], bool):
                self.error(path, f"{key} must be boolean")
        if "conditions" in data:
            self.validate_conditions(data["conditions"], path)
        self.validate_condition_behavior(data, path)
        if "dependencies" in data and not self.string_list(data["dependencies"], path, "dependencies"):
            pass
        if "redirects" in data:
            redirects = self.require_map(data["redirects"], path, "redirects")
            if redirects is not None:
                for old, new in redirects.items():
                    if not isinstance(old, str) or not isinstance(new, str) or not old or not new:
                        self.error(path, "redirects keys and values must be non-empty strings")
        if ref:
            folded = ref.casefold()
            if folded in self.refs:
                self.error(path, f"duplicate pack ref {ref!r}; already used by {self.refs[folded]}")
            else:
                self.refs[folded] = path
        self.manifests[path.parent.resolve()] = data

    def string_list(self, value: Any, path: Path, key: str) -> bool:
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            self.error(path, f"{key} must be a sequence of non-empty strings")
            return False
        return True

    def validate_pack_dependencies(self) -> None:
        packs: dict[str, tuple[Path, list[str]]] = {}
        for root, manifest in self.manifests.items():
            ref = manifest.get("ref")
            dependencies = manifest.get("dependencies", [])
            if (
                isinstance(ref, str)
                and isinstance(dependencies, list)
                and all(isinstance(item, str) for item in dependencies)
            ):
                packs[ref] = (root / "pack.yml", dependencies)

        invalid: set[str] = set()
        changed = True
        while changed:
            changed = False
            for ref, (path, dependencies) in packs.items():
                if ref in invalid:
                    continue
                bad = next((dep for dep in dependencies if dep == ref or dep not in packs or dep in invalid), None)
                if bad is not None:
                    self.error(path, f"dependency {bad!r} is missing, invalid, or self-referential")
                    invalid.add(ref)
                    changed = True

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(ref: str, stack: list[str]) -> None:
            if ref in visited or ref in invalid:
                return
            if ref in visiting:
                cycle = stack[stack.index(ref) :] + [ref]
                for cycle_ref in cycle[:-1]:
                    if cycle_ref not in invalid:
                        self.error(packs[cycle_ref][0], f"dependency cycle detected: {' -> '.join(cycle)}")
                        invalid.add(cycle_ref)
                return
            visiting.add(ref)
            stack.append(ref)
            for dependency in packs[ref][1]:
                if dependency in packs:
                    visit(dependency, stack)
            stack.pop()
            visiting.remove(ref)
            visited.add(ref)

        for ref in packs:
            visit(ref, [])

    def infer_type(self, path: Path, document: dict[str, Any], multi_document: bool) -> str | None:
        explicit = document.get("type")
        if explicit is not None:
            if not isinstance(explicit, str) or not explicit.strip():
                self.error(path, "type must be a non-empty string")
                return None
            normalized = explicit.strip().casefold()
            return "research" if normalized == "mam" else normalized
        if multi_document:
            self.error(path, "every document in a multi-document YAML file requires explicit type")
            return None
        stem = path.name.casefold()
        for root_type in sorted(KNOWN_TYPES, key=len, reverse=True):
            if stem.endswith(f".{root_type}.yml") or stem.endswith(f".{root_type}.yaml"):
                return root_type
        if stem.endswith(".mam.yml") or stem.endswith(".mam.yaml"):
            return "research"
        self.error(path, "missing type and filename has no recognized <name>.<type>.yml suffix")
        return None

    def validate_conditions(self, value: Any, path: Path) -> None:
        if isinstance(value, dict):
            condition_objects = [value]
        elif isinstance(value, list):
            condition_objects = value
        else:
            self.error(path, "conditions must be a mapping or sequence of mappings")
            return
        allowed = {
            "gameVersion",
            "hasMod",
            "modVersion",
            "hasClass",
            "ifNotMatch",
        }
        for index, condition in enumerate(condition_objects):
            context = "condition" if isinstance(value, dict) else f"conditions[{index}]"
            if not isinstance(condition, dict):
                self.error(path, f"{context} must be a mapping")
                continue
            for key in condition:
                if key not in allowed:
                    self.warning(path, f"unknown condition key {key!r}")
            for key in ("hasMod", "hasClass"):
                if key in condition and not isinstance(condition[key], (str, list)):
                    self.error(path, f"{context}.{key} must be string or sequence")
            if "modVersion" in condition and not isinstance(condition["modVersion"], dict):
                self.error(path, f"{context}.modVersion must be a mapping")
            if "ifNotMatch" in condition and not isinstance(condition["ifNotMatch"], bool):
                self.error(path, f"{context}.ifNotMatch must be boolean")

    def validate_condition_behavior(self, mapping: dict[str, Any], path: Path) -> None:
        for key in ("conditionBehaivor", "conditionBehavior"):
            if key in mapping and (
                not isinstance(mapping[key], str) or mapping[key].casefold() not in {"and", "or"}
            ):
                self.error(path, f"{key} must be AND or OR")

    def validate_property_ops(self, value: Any, path: Path, context: str) -> None:
        if not isinstance(value, list) or not value:
            self.error(path, f"{context} must be a non-empty sequence")
            return
        for index, operation in enumerate(value):
            label = f"{context}[{index}]"
            if not isinstance(operation, dict):
                self.error(path, f"{label} must be a mapping")
                continue
            property_path = operation.get("path")
            if (
                not isinstance(property_path, str)
                or not property_path.strip()
                or not PROPERTY_PATH.fullmatch(property_path)
            ):
                self.error(path, f"{label}.path is not a valid property path")
            op = operation.get("op", "set")
            if not isinstance(op, str) or op.casefold() not in OPS:
                self.error(path, f"{label}.op must be one of {sorted(OPS)}")
                continue
            required = OP_REQUIRED.get(op.casefold(), set())
            for key in required:
                if key not in operation:
                    self.error(path, f"{label} operation {op!r} requires {key!r}")
            for key in ("from", "path"):
                if key in operation and not isinstance(operation[key], str):
                    self.error(path, f"{label}.{key} must be a string")
            for key in ("index",):
                if key in operation and (isinstance(operation[key], bool) or not isinstance(operation[key], int)):
                    self.error(path, f"{label}.{key} must be an integer")
            if (
                op.casefold() in {"copy", "move"}
                and isinstance(operation.get("from"), str)
                and not PROPERTY_PATH.fullmatch(operation["from"])
            ):
                self.error(path, f"{label}.from is not a valid property path")
            if "value" in operation:
                self.validate_inline_instances(operation["value"], path, f"{label}.value")

    def validate_inline_instances(self, value: Any, path: Path, context: str) -> None:
        if isinstance(value, list):
            for index, entry in enumerate(value):
                self.validate_inline_instances(entry, path, f"{context}[{index}]")
            return
        if not isinstance(value, dict):
            return
        if "properties" in value:
            class_path = value.get("class")
            if not isinstance(class_path, str) or not class_path.strip():
                self.error(path, f"{context}.class must be a non-empty string when properties is present")
            self.validate_property_ops(value["properties"], path, f"{context}.properties")
            return
        for key, child in value.items():
            self.validate_inline_instances(child, path, f"{context}.{key}")

    def validate_target(self, patch: dict[str, Any], path: Path, context: str) -> None:
        selectors = [key for key in ("target", "allAssetsOfClass", "matchTag") if key in patch]
        if not selectors:
            self.error(path, f"{context} needs target, allAssetsOfClass, or matchTag")
        if len(selectors) > 1:
            self.error(path, f"{context} selectors are mutually exclusive: {selectors}")
        if "target" in patch:
            target = patch["target"]
            values = target if isinstance(target, list) else [target]
            if not values or any(not isinstance(item, str) or not item.strip() for item in values):
                self.error(path, f"{context}.target must be a path string or sequence of path strings")
        for key in ("allAssetsOfClass", "ofClass", "tagProperty"):
            if key in patch and not isinstance(patch[key], str):
                self.error(path, f"{context}.{key} must be a string")
        if "matchTag" in patch and "ofClass" not in patch:
            self.error(path, f"{context}.matchTag requires ofClass")
        for key in ("applyToSubclasses", "applyToSpawnedActors", "deferOneGameTick"):
            if key in patch and not isinstance(patch[key], bool):
                self.error(path, f"{context}.{key} must be a boolean")
        if "properties" not in patch:
            self.error(path, f"{context} requires properties")
        else:
            self.validate_property_ops(patch["properties"], path, f"{context}.properties")

    @staticmethod
    def is_finite_number(value: Any) -> bool:
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)

    def validate_curve_value(self, value: Any, curve_type: str, path: Path, context: str) -> None:
        if curve_type == "float":
            if not self.is_finite_number(value):
                self.error(path, f"{context} must be a finite number")
            return
        if isinstance(value, list):
            if len(value) != 3 or any(not self.is_finite_number(component) for component in value):
                self.error(path, f"{context} must contain exactly three finite numbers")
            return
        if isinstance(value, dict):
            components = {str(key).casefold(): component for key, component in value.items()}
            if set(components) != {"x", "y", "z"} or any(
                not self.is_finite_number(components[axis]) for axis in ("x", "y", "z")
            ):
                self.error(path, f"{context} must be an X/Y/Z mapping of finite numbers")
            return
        self.error(path, f"{context} must be an X/Y/Z mapping or three-number sequence")

    def validate_curve_document(self, document: dict[str, Any], path: Path, pack_ref: str) -> None:
        raw_curve_type = document.get("curveType")
        curve_type = raw_curve_type.casefold() if isinstance(raw_curve_type, str) else ""
        if curve_type not in {"float", "vector"}:
            self.error(path, "curveType must be float or vector")
            return
        curves = self.require_sequence(document, "curves", path, "curve")
        if curves is None:
            return
        for index, curve in enumerate(curves):
            context = f"curve.curves[{index}]"
            if not isinstance(curve, dict):
                self.error(path, f"{context} must be a mapping")
                continue
            has_id = isinstance(curve.get("id"), str) and bool(curve["id"].strip())
            has_target = isinstance(curve.get("target"), str) and bool(curve["target"].strip())
            if has_id == has_target:
                self.error(path, f"{context} requires exactly one non-empty id or target")
            if has_id:
                identifier = curve["id"].strip()
                if not TOKEN.fullmatch(identifier):
                    self.error(path, f"{context}.id {identifier!r} contains invalid characters")
                elif identifier.casefold() in self.generated_ids[pack_ref.casefold()]:
                    self.error(path, f"duplicate generated id {identifier!r} in pack {pack_ref}")
                else:
                    self.generated_ids[pack_ref.casefold()][identifier.casefold()] = path

            keys = self.require_sequence(curve, "keys", path, context)
            if keys is not None:
                times: set[float] = set()
                for key_index, key in enumerate(keys):
                    key_context = f"{context}.keys[{key_index}]"
                    if not isinstance(key, dict):
                        self.error(path, f"{key_context} must be a mapping")
                        continue
                    time = key.get("time")
                    if not self.is_finite_number(time):
                        self.error(path, f"{key_context}.time must be a finite number")
                    elif float(time) in times:
                        self.error(path, f"{key_context}.time duplicates {time}")
                    else:
                        times.add(float(time))
                    self.validate_curve_value(key.get("value"), curve_type, path, f"{key_context}.value")
                    enum_fields = {
                        "interpMode": CURVE_INTERP_MODES,
                        "tangentMode": CURVE_TANGENT_MODES,
                        "tangentWeightMode": CURVE_TANGENT_WEIGHT_MODES,
                    }
                    for field, allowed in enum_fields.items():
                        if field in key and (not isinstance(key[field], str) or key[field].casefold() not in allowed):
                            self.error(path, f"{key_context}.{field} must be one of {sorted(allowed)}")
                    for field in (
                        "arriveTangent",
                        "leaveTangent",
                        "arriveTangentWeight",
                        "leaveTangentWeight",
                    ):
                        if field in key:
                            self.validate_curve_value(key[field], curve_type, path, f"{key_context}.{field}")

            if "defaultValue" in curve:
                self.validate_curve_value(curve["defaultValue"], curve_type, path, f"{context}.defaultValue")
            for field in ("preInfinityExtrap", "postInfinityExtrap"):
                if field in curve and (
                    not isinstance(curve[field], str) or curve[field].casefold() not in CURVE_EXTRAPOLATION_MODES
                ):
                    self.error(
                        path,
                        f"{context}.{field} must be one of {sorted(CURVE_EXTRAPOLATION_MODES)}",
                    )
            if "isEventCurve" in curve:
                if curve_type != "float":
                    self.error(path, f"{context}.isEventCurve is only valid for float curves")
                elif not isinstance(curve["isEventCurve"], bool):
                    self.error(path, f"{context}.isEventCurve must be boolean")

    def validate_content_entries(self, root_type: str, document: dict[str, Any], path: Path, pack_ref: str) -> None:
        key = CONTENT_KEYS[root_type]
        entries = self.require_sequence(document, key, path, root_type)
        if entries is None:
            return
        for index, entry in enumerate(entries):
            context = f"{root_type}.{key}[{index}]"
            if not isinstance(entry, dict):
                self.error(path, f"{context} must be a mapping")
                continue
            has_id = isinstance(entry.get("id"), str) and bool(entry["id"].strip())
            has_class = isinstance(entry.get("class"), str) and bool(entry["class"].strip())
            if has_id == has_class:
                self.error(path, f"{context} requires exactly one non-empty id or class")
            if has_class and root_type not in {"recipe", "schematic", "research"}:
                self.error(path, f"{context} class (register-only) is only valid for recipe/schematic/research")
            if has_id:
                identifier = entry["id"].strip()
                if not TOKEN.fullmatch(identifier):
                    self.error(path, f"{context}.id {identifier!r} contains invalid characters")
                elif identifier.casefold() in self.generated_ids[pack_ref.casefold()]:
                    self.error(path, f"duplicate generated id {identifier!r} in pack {pack_ref}")
                else:
                    self.generated_ids[pack_ref.casefold()][identifier.casefold()] = path
            if "parent" in entry and not isinstance(entry["parent"], str):
                self.error(path, f"{context}.parent must be a string")
            if root_type == "unlock" and has_id and not entry.get("parent"):
                self.error(path, f"{context} with id requires parent")
            if "registerAs" in entry and (root_type != "class" or entry["registerAs"] not in REGISTER_AS):
                self.error(path, f"{context}.registerAs must be recipe/schematic/research on class entries")
            if "properties" in entry:
                self.validate_property_ops(entry["properties"], path, f"{context}.properties")
            if root_type == "schematic":
                for key_name in ("unlocks", "dependencies"):
                    if key_name in entry:
                        self.validate_instanced_list(entry[key_name], path, f"{context}.{key_name}")
            if root_type == "research":
                self.validate_research_mutations(entry, path, context)

    def validate_instanced_list(self, value: Any, path: Path, context: str) -> None:
        if not isinstance(value, list):
            self.error(path, f"{context} must be a sequence")
            return
        for index, entry in enumerate(value):
            if not isinstance(entry, dict) or not isinstance(entry.get("class"), str) or not entry["class"].strip():
                self.error(path, f"{context}[{index}] requires class")
            elif "properties" in entry:
                self.validate_property_ops(entry["properties"], path, f"{context}[{index}].properties")

    def validate_nodes(self, value: Any, path: Path, context: str) -> None:
        if not isinstance(value, list) or not value:
            self.error(path, f"{context} must be a non-empty sequence")
            return
        for index, node in enumerate(value):
            if not isinstance(node, dict):
                self.error(path, f"{context}[{index}] must be a mapping")
                continue
            schematic = node.get("schematic")
            if not isinstance(schematic, str) or not schematic.strip():
                self.error(path, f"{context}[{index}] requires a non-empty schematic class reference")
            if "class" in node and (not isinstance(node["class"], str) or not node["class"].strip()):
                self.error(path, f"{context}[{index}].class must be a non-empty string")
            if "coordinate" in node:
                self.validate_coordinate(node["coordinate"], path, f"{context}[{index}].coordinate")
            for key in ("parents", "nodesToUnhide", "unhiddenBy"):
                if key in node:
                    self.validate_node_references(node[key], path, f"{context}[{index}].{key}")
            if "properties" in node:
                self.validate_property_ops(node["properties"], path, f"{context}[{index}].properties")

    def validate_research_mutations(self, entry: dict[str, Any], path: Path, context: str) -> None:
        if "autoPath" in entry and not isinstance(entry["autoPath"], bool):
            self.error(path, f"{context}.autoPath must be boolean")
        if "addNodes" in entry:
            self.validate_nodes(entry["addNodes"], path, f"{context}.addNodes")
        if "nodes" in entry:
            self.validate_nodes(entry["nodes"], path, f"{context}.nodes")
        if "addNodes" in entry and "nodes" in entry:
            self.error(path, f"{context} cannot contain both addNodes and legacy nodes; nodes would be ignored")
        if "removeNodes" in entry:
            removals = entry["removeNodes"]
            if not isinstance(removals, list) or not removals:
                self.error(path, f"{context}.removeNodes must be a non-empty sequence")
            else:
                for index, removal in enumerate(removals):
                    if isinstance(removal, str):
                        reference = removal
                    elif isinstance(removal, dict):
                        reference = removal.get("schematic")
                    else:
                        reference = None
                    if not isinstance(reference, str) or not reference.strip():
                        self.error(
                            path,
                            f"{context}.removeNodes[{index}] requires a non-empty schematic class reference",
                        )

    def validate_coordinate(self, value: Any, path: Path, context: str) -> None:
        if not isinstance(value, dict):
            self.error(path, f"{context} must be a mapping")
            return
        for axis in ("X", "Y"):
            coordinate = value.get(axis)
            if isinstance(coordinate, bool) or not isinstance(coordinate, int):
                self.error(path, f"{context}.{axis} must be an integer")

    def validate_node_references(self, value: Any, path: Path, context: str) -> None:
        if not isinstance(value, list):
            self.error(path, f"{context} must be a sequence")
            return
        for index, reference in enumerate(value):
            label = f"{context}[{index}]"
            if not isinstance(reference, dict):
                self.error(path, f"{label} must be a coordinate or schematic mapping")
                continue
            schematic = reference.get("schematic")
            if schematic is not None:
                if not isinstance(schematic, str) or not schematic.strip():
                    self.error(path, f"{label}.schematic must be a non-empty string")
            else:
                self.validate_coordinate(reference, path, label)

    def validate_document(self, path: Path, document: Any, index: int, multi_document: bool, pack_root: Path) -> None:
        mapping = self.require_map(document, path, f"document[{index}]")
        if mapping is None:
            return
        root_type = self.infer_type(path, mapping, multi_document)
        if root_type is None:
            return
        self.document_count += 1
        if "conditions" in mapping:
            self.validate_conditions(mapping["conditions"], path)
        self.validate_condition_behavior(mapping, path)
        if "debug" in mapping and not isinstance(mapping["debug"], bool):
            self.error(path, "debug must be boolean")
        if "include" in mapping:
            includes = mapping["include"] if isinstance(mapping["include"], list) else [mapping["include"]]
            for include in includes:
                if not isinstance(include, str) or not include.strip():
                    self.error(path, "include entries must be non-empty strings")
                    continue
                target = (path.parent / include).resolve()
                if self.root not in target.parents and target != self.root:
                    self.error(path, f"include escapes DataForge root: {include}")
                elif not target.is_file():
                    self.error(path, f"include does not exist: {include}")
        pack_data = self.manifests.get(pack_root)
        pack_ref = str(pack_data.get("ref", pack_root.name)) if pack_data else pack_root.name
        if root_type == "cdo":
            patches = self.require_sequence(mapping, "patches", path, "cdo")
            if patches:
                for i, patch in enumerate(patches):
                    if isinstance(patch, dict):
                        self.validate_target(patch, path, f"cdo.patches[{i}]")
                    else:
                        self.error(path, f"cdo.patches[{i}] must be a mapping")
        elif root_type == "gametag":
            tags = self.require_sequence(mapping, "tags", path, "gametag")
            if tags:
                for i, tag in enumerate(tags):
                    if isinstance(tag, str) and tag.strip():
                        continue
                    if not isinstance(tag, dict) or not isinstance(tag.get("tag"), str) or not tag["tag"].strip():
                        self.error(path, f"gametag.tags[{i}] must be tag string or mapping with tag")
        elif root_type in CONTENT_KEYS:
            self.validate_content_entries(root_type, mapping, path, pack_ref)
        elif root_type == "curve":
            self.validate_curve_document(mapping, path, pack_ref)
        elif root_type in {"asset", "dataasset"}:
            assets = self.require_sequence(mapping, "assets", path, root_type)
            if assets:
                for i, asset in enumerate(assets):
                    context = f"{root_type}.assets[{i}]"
                    if not isinstance(asset, dict) or not isinstance(asset.get("id"), str) or not asset["id"].strip():
                        self.error(path, f"{context} requires id")
                        continue
                    identifier = asset["id"].strip().casefold()
                    if identifier in self.generated_ids[pack_ref.casefold()]:
                        self.error(path, f"duplicate generated id {asset['id']!r} in pack {pack_ref}")
                    else:
                        self.generated_ids[pack_ref.casefold()][identifier] = path
                    required = "file" if root_type == "asset" else "class"
                    value = asset.get(required)
                    if not isinstance(value, str) or not value.strip():
                        self.error(path, f"{context} requires {required}")
                    elif root_type == "asset":
                        relative = Path(value.replace("\\", "/"))
                        if relative.is_absolute() or ".." in relative.parts:
                            self.error(path, f"{context}.file must stay inside pack")
                        elif not (pack_root / relative).is_file():
                            self.error(path, f"{context}.file does not exist: {value}")
                        elif relative.suffix.casefold() not in {".png", ".jpg", ".jpeg", ".tga", ".bmp"}:
                            self.error(path, f"{context}.file must be png/jpg/jpeg/tga/bmp")
                    if "properties" in asset:
                        self.validate_property_ops(asset["properties"], path, f"{context}.properties")
        elif root_type == "localization":
            namespace = self.require_string(mapping, "namespace", path, "localization")
            entries = mapping.get("entries")
            if not isinstance(entries, dict) or not entries:
                self.error(path, "localization requires non-empty entries mapping")
            elif any(not isinstance(key, str) or not key.strip() for key in entries):
                self.error(path, "localization entry keys must be non-empty strings")
            else:
                for key, value in entries.items():
                    if not isinstance(value, (str, dict)):
                        self.error(path, f"localization entry {key!r} must be string or mapping")
                    elif isinstance(value, dict) and (
                        not isinstance(value.get("text"), str) or not value["text"].strip()
                    ):
                        self.error(path, f"localization entry {key!r} requires non-empty text")
            if "culture" in mapping and not isinstance(mapping["culture"], str):
                self.error(path, "localization culture must be string")
        elif root_type == "sinkpoints":
            if mapping.get("track", "Default") not in {"Default", "Exploration"}:
                self.error(path, "sinkpoints track must be Default or Exploration")
            entries = self.require_sequence(mapping, "entries", path, "sinkpoints")
            if entries:
                for i, entry in enumerate(entries):
                    if (
                        not isinstance(entry, dict)
                        or not isinstance(entry.get("item"), str)
                        or not entry["item"].strip()
                    ):
                        self.error(path, f"sinkpoints.entries[{i}] requires item")
                    points = entry.get("points") if isinstance(entry, dict) else None
                    if isinstance(points, bool) or not isinstance(points, int):
                        self.error(path, f"sinkpoints.entries[{i}].points must be integer")
        elif root_type not in KNOWN_TYPES:
            self.warning(path, f"custom root type {root_type!r}; structural validation delegated to runtime handler")

    def run(self) -> int:
        if not self.root.is_dir():
            self.error(self.root, "DataForge root does not exist")
            return 1
        for path in self.root.rglob("*"):
            if path.is_symlink():
                self.error(path, "symlinks are not allowed in DataForge packs")
        manifests = sorted(self.root.rglob("pack.yml"))
        if not manifests:
            self.error(self.root, "no pack.yml found")
        for manifest in manifests:
            if len(manifest.relative_to(self.root).parts) < 2:
                self.error(manifest, "expected DataForge/**/<pack>/pack.yml layout")
            self.validate_manifest(manifest)
        self.validate_pack_dependencies()
        for document in sorted(self.root.rglob("*.yml")) + sorted(self.root.rglob("*.yaml")):
            if document.name == "pack.yml":
                continue
            pack_root = self.find_pack_root(document)
            if pack_root is None:
                self.error(document, "YAML document is outside a pack with pack.yml")
                continue
            documents = self.parse_all(document)
            if documents is None:
                continue
            multi_document = len(documents) > 1
            if not documents or all(item is None for item in documents):
                self.error(document, "empty YAML document")
                continue
            for index, item in enumerate(documents):
                if item is not None:
                    self.validate_document(document, item, index, multi_document, pack_root)
        for warning in self.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if self.errors:
            for error in self.errors:
                print(f"error: {error}", file=sys.stderr)
            return 1
        print(f"lint passed: {len(manifests)} pack(s), {self.document_count} YAML document(s)")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("DataForge"))
    args = parser.parse_args()
    return Linter(args.root).run()


if __name__ == "__main__":
    raise SystemExit(main())
