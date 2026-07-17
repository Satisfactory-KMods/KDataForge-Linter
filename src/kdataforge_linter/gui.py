from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from importlib.resources import as_file, files
from pathlib import Path

from kdataforge_linter.models import Diagnostic, LintResult
from kdataforge_linter.schema_registry import SchemaRegistryError
from kdataforge_linter.validator import lint_path

try:
    from PySide6.QtCore import Qt, QUrl
    from PySide6.QtGui import QColor, QDesktopServices, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSplitter,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as error:  # pragma: no cover - depends on optional GUI install
    raise SystemExit("PySide6 is required for the GUI. Install kdataforge-linter[gui].") from error

PALETTE = {
    "background": "#101C2F",
    "surface": "#1B304D",
    "primary": "#2F5279",
    "accent": "#BDD2EA",
    "text": "#F7F9FC",
    "muted": "#91A8C2",
    "error": "#FF6B6B",
    "warning": "#F3C969",
    "success": "#4FC38A",
}

STYLE = f"""
QWidget {{ background: {PALETTE["background"]}; color: {PALETTE["text"]}; font-size: 13px; }}
QFrame#card {{ background: {PALETTE["surface"]}; border: 1px solid {PALETTE["primary"]}; border-radius: 12px; }}
QLineEdit, QTextEdit, QListWidget {{
  background: #13243B; border: 1px solid {PALETTE["primary"]}; border-radius: 8px; padding: 8px;
}}
QLineEdit:focus, QTextEdit:focus, QListWidget:focus {{ border-color: {PALETTE["accent"]}; }}
QPushButton {{ background: {PALETTE["primary"]}; border: 0; border-radius: 8px; padding: 9px 14px; font-weight: 600; }}
QPushButton:hover {{ background: #3B6592; }}
QPushButton:disabled {{ background: #263B55; color: {PALETTE["muted"]}; }}
QListWidget::item {{ padding: 7px; border-bottom: 1px solid #243B59; }}
QListWidget::item:selected {{ background: {PALETTE["primary"]}; }}
"""


class MainWindow(QMainWindow):
    def __init__(self, initial_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("KDataForge Linter")
        self.resize(1050, 720)
        self.setAcceptDrops(True)
        self.result: LintResult | None = None
        self.schema_directories: list[Path] = []
        self._build_ui(initial_path)

    def _build_ui(self, initial_path: Path | None) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        header = QFrame(objectName="card")
        header_layout = QHBoxLayout(header)
        logo_label = QLabel()
        logo = files("kdataforge_linter").joinpath("resources/kmods-logo.png")
        with as_file(logo) as logo_path:
            pixmap = QPixmap(str(logo_path)).scaled(
                82, 82, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        logo_label.setPixmap(pixmap)
        header_layout.addWidget(logo_label)
        title_layout = QVBoxLayout()
        title = QLabel("KDataForge Linter")
        title.setStyleSheet("font-size: 26px; font-weight: 700;")
        subtitle = QLabel("Schema-driven validation for KDataForge packs")
        subtitle.setStyleSheet(f"color: {PALETTE['accent']}; font-size: 14px;")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header_layout.addLayout(title_layout, 1)
        layout.addWidget(header)

        controls = QFrame(objectName="card")
        controls_layout = QHBoxLayout(controls)
        self.path_edit = QLineEdit(str(initial_path.resolve()) if initial_path else "")
        self.path_edit.setPlaceholderText("Select or drop a DataForge directory")
        controls_layout.addWidget(self.path_edit, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        controls_layout.addWidget(browse)
        schemas = QPushButton("Add schemas")
        schemas.clicked.connect(self._add_schema_directory)
        controls_layout.addWidget(schemas)
        validate = QPushButton("Validate")
        validate.clicked.connect(self._validate)
        controls_layout.addWidget(validate)
        layout.addWidget(controls)

        self.status = QLabel("Ready")
        self.status.setStyleSheet(f"color: {PALETTE['muted']}; padding-left: 4px;")
        layout.addWidget(self.status)

        splitter = QSplitter()
        self.diagnostics = QListWidget()
        self.diagnostics.currentItemChanged.connect(self._show_diagnostic)
        self.diagnostics.itemDoubleClicked.connect(self._open_diagnostic)
        splitter.addWidget(self.diagnostics)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Select a diagnostic to see details")
        splitter.addWidget(self.details)
        splitter.setSizes([620, 390])
        layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        export = QPushButton("Export JSON")
        export.clicked.connect(self._export)
        actions.addWidget(export)
        layout.addLayout(actions)
        self.setCentralWidget(root)

    def _browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select DataForge directory", self.path_edit.text())
        if selected:
            self.path_edit.setText(selected)

    def _add_schema_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Add external schema directory")
        if selected:
            path = Path(selected).resolve()
            if path not in self.schema_directories:
                self.schema_directories.append(path)
            self.status.setText(f"External schemas: {', '.join(str(item) for item in self.schema_directories)}")

    def _validate(self) -> None:
        path = Path(self.path_edit.text().strip())
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.result = lint_path(path, self.schema_directories)
        except SchemaRegistryError as error:
            QMessageBox.critical(self, "Schema error", str(error))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.diagnostics.clear()
        for diagnostic in self.result.diagnostics:
            prefix = "ERROR" if diagnostic.severity == "error" else "WARNING"
            location = f"{diagnostic.file.name}: " if diagnostic.file else ""
            item = QListWidgetItem(f"{prefix}  {location}{diagnostic.message}")
            item.setData(Qt.ItemDataRole.UserRole, diagnostic)
            item.setForeground(QColor(PALETTE[diagnostic.severity]))
            self.diagnostics.addItem(item)
        color = PALETTE["success"] if self.result.ok else PALETTE["error"]
        self.status.setStyleSheet(f"color: {color}; padding-left: 4px; font-weight: 600;")
        self.status.setText(
            f"{len(self.result.errors)} errors · {len(self.result.warnings)} warnings · "
            f"{self.result.pack_count} packs · {self.result.document_count} documents"
        )
        if not self.result.diagnostics:
            self.details.setPlainText("Validation passed without diagnostics.")

    def _show_diagnostic(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        item: Diagnostic = current.data(Qt.ItemDataRole.UserRole)
        lines = [item.message, "", f"Code: {item.code}", f"YAML path: {item.yaml_path}"]
        if item.file:
            lines.append(f"File: {item.file}")
        if item.line is not None:
            lines.append(f"Position: {item.line}:{item.column or 1}")
        if item.schema:
            lines.append(f"Schema: {item.schema}")
        self.details.setPlainText("\n".join(lines))

    def _open_diagnostic(self, current: QListWidgetItem) -> None:
        item: Diagnostic = current.data(Qt.ItemDataRole.UserRole)
        if item.file:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.file)))

    def _export(self) -> None:
        if self.result is None:
            QMessageBox.information(self, "Nothing to export", "Run validation first.")
            return
        selected, _ = QFileDialog.getSaveFileName(self, "Export diagnostics", "kdataforge-lint.json", "JSON (*.json)")
        if selected:
            Path(selected).write_text(json.dumps(self.result.to_dict(), indent=2), encoding="utf-8")

    def dragEnterEvent(self, event: object) -> None:
        if hasattr(event, "mimeData") and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: object) -> None:
        urls = event.mimeData().urls()
        if urls:
            path = Path(urls[0].toLocalFile())
            self.path_edit.setText(str(path if path.is_dir() else path.parent))
            event.acceptProposedAction()


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    app = QApplication([sys.argv[0], *args])
    app.setStyleSheet(STYLE)
    initial = Path(args[0]) if args else None
    window = MainWindow(initial)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
