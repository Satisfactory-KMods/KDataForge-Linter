from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    severity: Severity
    code: str
    message: str
    file: Path | None = None
    document: int | None = None
    yaml_path: str = "$"
    line: int | None = None
    column: int | None = None
    schema: str | None = None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["file"] = str(self.file) if self.file else None
        data["yamlPath"] = data.pop("yaml_path")
        return data


@dataclass(slots=True)
class LintResult:
    diagnostics: list[Diagnostic] = field(default_factory=list)
    pack_count: int = 0
    document_count: int = 0

    @property
    def errors(self) -> list[Diagnostic]:
        return [item for item in self.diagnostics if item.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [item for item in self.diagnostics if item.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "packs": self.pack_count,
            "documents": self.document_count,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }
