# KDataForge Linter

Schema-driven validation for KDataForge packs. Windows and Linux releases include standalone CLI
and graphical applications; Python is not required.

> [!NOTE]
> This project was written with substantial assistance from OpenAI Codex. See
> [AI_DISCLOSURE.md](AI_DISCLOSURE.md) for scope and responsibility details.

## CLI

```text
kdataforge-linter lint DataForge
kdataforge-linter lint DataForge --format github
kdataforge-linter lint DataForge --format json
kdataforge-linter schemas check
```

Add schemas for third-party KDataForge handlers with `--schema-dir PATH`. External schemas use
JSON Schema Draft 2020-12 written as YAML and declare their root type through `x-kdf-type`.
Built-in types cannot be replaced unless `--allow-schema-override` is passed explicitly.

Exit codes:

| Code | Meaning |
| ---: | --- |
| 0 | Validation passed |
| 1 | Pack validation failed |
| 2 | Invalid invocation or schema set |
| 3 | Internal error |

## GUI

Start `KDataForge-Linter-GUI`, select or drop a `DataForge` directory, then choose **Validate**.
Diagnostics include file, document, YAML path, line, column, rule code, and schema.

## Unlock and dependency class checks

Bundled catalog covers native and Blueprint descendants of `FGUnlock` and
`FGAvailabilityDependency`, including loaded KMods classes. Linter checks instanced class references
in schematic, research-tree, and delivery-task/data-asset lists. Native paths with known Blueprint
implementations, abstract classes without Blueprint variants, wrong-family references, and unknown
paths produce warnings only; they never make an otherwise valid pack fail.

Regenerate catalog from Unreal project root:

```text
UnrealEditor-Cmd.exe FactoryGame.uproject -ExecutePythonScript=Mods/GameFeatures/KDataForge/Tools/scan_instanced_class_catalog.py -unattended -nop4
```

## Development

```text
uv sync --extra gui --group dev
uv run pytest
uv run ruff check .
uv run kdataforge-linter lint ../KPatchwork/DataForge
```

Schemas live in `src/kdataforge_linter/schemas`. Schema-only changes alter validation without
changing Python code.
