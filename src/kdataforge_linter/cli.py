from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from kdataforge_linter import __version__
from kdataforge_linter.models import Diagnostic, LintResult
from kdataforge_linter.schema_registry import SchemaRegistry, SchemaRegistryError
from kdataforge_linter.validator import lint_path


def _format_location(item: Diagnostic) -> str:
    location = str(item.file) if item.file else "<configuration>"
    if item.line is not None:
        location += f":{item.line}"
        if item.column is not None:
            location += f":{item.column}"
    if item.document is not None:
        location += f"[{item.document}]"
    return location


def _print_text(result: LintResult) -> None:
    for item in result.diagnostics:
        print(
            f"{item.severity}: {_format_location(item)}: {item.message} ({item.code}, {item.yaml_path})",
            file=sys.stderr,
        )
    if result.ok:
        print(f"lint passed: {result.pack_count} pack(s), {result.document_count} YAML document(s)")
    else:
        print(f"lint failed: {len(result.errors)} error(s), {len(result.warnings)} warning(s)", file=sys.stderr)


def _print_github(result: LintResult) -> None:
    for item in result.diagnostics:
        properties = [f"file={item.file}"] if item.file else []
        if item.line is not None:
            properties.append(f"line={item.line}")
        if item.column is not None:
            properties.append(f"col={item.column}")
        message = item.message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::{item.severity} {','.join(properties)}::{message} [{item.code} {item.yaml_path}]")
    print(f"Validated {result.pack_count} pack(s) and {result.document_count} YAML document(s).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kdataforge-linter")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    lint_parser = subparsers.add_parser("lint", help="validate a DataForge directory")
    lint_parser.add_argument("path", type=Path)
    lint_parser.add_argument("--schema-dir", type=Path, action="append", default=[])
    lint_parser.add_argument("--format", choices=("text", "json", "github"), default="text")
    lint_parser.add_argument("--warnings-as-errors", action="store_true")
    lint_parser.add_argument("--allow-unknown-types", action="store_true")
    lint_parser.add_argument("--allow-schema-override", action="store_true")
    lint_parser.add_argument("--no-color", action="store_true", help="reserved for stable scripting compatibility")

    schema_parser = subparsers.add_parser("schemas", help="inspect loaded schemas")
    schema_parser.add_argument("action", choices=("list", "check"))
    schema_parser.add_argument("--schema-dir", type=Path, action="append", default=[])
    schema_parser.add_argument("--allow-schema-override", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "schemas":
            registry = SchemaRegistry(args.schema_dir, args.allow_schema_override)
            if args.action == "list":
                print("\n".join(registry.kinds()))
            else:
                print(f"schemas valid: {len(registry.kinds())} root type(s)")
            return 0
        result = lint_path(
            args.path,
            args.schema_dir,
            args.allow_schema_override,
            args.allow_unknown_types,
        )
    except SchemaRegistryError as error:
        print(f"schema error: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # pragma: no cover - final CLI containment
        print(f"internal error: {error}", file=sys.stderr)
        return 3

    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2))
    elif args.format == "github":
        _print_github(result)
    else:
        _print_text(result)
    return 1 if result.errors or (args.warnings_as_errors and result.warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
