"""Forum Konwerter — desktop UI for WAPRO MAG → Comarch Optima XML conversion."""

from __future__ import annotations

import json
import sys
import traceback
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from converter import ConvertOptions, convert_file

APP_NAME = "Forum Konwerter"
SETTINGS_FILE = Path.home() / ".forum-konwerter.json"


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


class ConvertWorker(QObject):
    progress = Signal(int, int, str)
    file_done = Signal(str, str, str)
    finished = Signal(int, int)

    def __init__(self, files: list[Path], opts: ConvertOptions) -> None:
        super().__init__()
        self._files = files
        self._opts = opts
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        ok = 0
        fail = 0
        total = len(self._files)
        for idx, f in enumerate(self._files, start=1):
            if self._cancelled:
                break
            self.progress.emit(idx, total, f.name)
            try:
                out_path = convert_file(f, self._opts)
                self.file_done.emit(str(f), str(out_path), "")
                ok += 1
            except Exception as exc:
                self.file_done.emit(str(f), "", f"{exc}\n{traceback.format_exc()}")
                fail += 1
        self.finished.emit(ok, fail)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(900, 640)

        self._files: list[Path] = []
        self._thread: QThread | None = None
        self._worker: ConvertWorker | None = None

        self._build_ui()
        self._load_state()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        files_box = QGroupBox("Pliki źródłowe (WAPRO MAG XML)")
        fb_layout = QVBoxLayout(files_box)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Plik", "Status"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setColumnWidth(0, 540)
        fb_layout.addWidget(self.tree)

        files_btns = QHBoxLayout()
        self.add_files_btn = QPushButton("Dodaj pliki…")
        self.add_folder_btn = QPushButton("Dodaj folder…")
        self.remove_btn = QPushButton("Usuń zaznaczone")
        self.clear_btn = QPushButton("Wyczyść")
        for b in (self.add_files_btn, self.add_folder_btn, self.remove_btn, self.clear_btn):
            files_btns.addWidget(b)
        files_btns.addStretch(1)
        fb_layout.addLayout(files_btns)
        root.addWidget(files_box, 1)

        opt_box = QGroupBox("Opcje konwersji")
        form = QFormLayout(opt_box)

        self.initials_edit = QLineEdit()
        self.initials_edit.setPlaceholderText("np. MRK")
        self.initials_edit.setMaxLength(8)
        form.addRow("Inicjały (w nazwie pliku):", self.initials_edit)

        self.rejestr_edit = QLineEdit("SP")
        self.rejestr_edit.setMaxLength(20)
        form.addRow("Rejestr VAT:", self.rejestr_edit)

        self.kategoria_edit = QLineEdit("730-1")
        form.addRow("Kategoria (KATEGORIA / OPIS_POS):", self.kategoria_edit)

        self.bzrd_edit = QLineEdit("BZ")
        form.addRow("BAZA_ZRD_ID:", self.bzrd_edit)

        self.bdoc_edit = QLineEdit("K1")
        form.addRow("BAZA_DOC_ID:", self.bdoc_edit)

        self.detal_chk = QCheckBox("Dodaj kontrahenta „Sprzedaż detaliczna”")
        self.detal_chk.setChecked(True)
        form.addRow(self.detal_chk)

        out_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("Pozostaw puste, aby zapisać obok plików źródłowych")
        out_row.addWidget(self.output_dir_edit, 1)
        self.browse_out_btn = QPushButton("Wybierz…")
        out_row.addWidget(self.browse_out_btn)
        out_widget = QWidget()
        out_widget.setLayout(out_row)
        form.addRow("Folder docelowy:", out_widget)

        root.addWidget(opt_box)

        run_row = QHBoxLayout()
        self.convert_btn = QPushButton("Konwertuj")
        self.convert_btn.setMinimumHeight(36)
        self.cancel_btn = QPushButton("Anuluj")
        self.cancel_btn.setEnabled(False)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        run_row.addWidget(self.convert_btn)
        run_row.addWidget(self.cancel_btn)
        run_row.addWidget(self.progress, 1)
        root.addLayout(run_row)

        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        log_layout.addWidget(self.log)
        root.addWidget(log_box, 1)

        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Gotowy")

        self.add_files_btn.clicked.connect(self._on_add_files)
        self.add_folder_btn.clicked.connect(self._on_add_folder)
        self.remove_btn.clicked.connect(self._on_remove)
        self.clear_btn.clicked.connect(self._on_clear)
        self.browse_out_btn.clicked.connect(self._on_browse_out)
        self.convert_btn.clicked.connect(self._on_convert)
        self.cancel_btn.clicked.connect(self._on_cancel)

    def _load_state(self) -> None:
        s = load_settings()
        self.initials_edit.setText(s.get("initials", ""))
        self.rejestr_edit.setText(s.get("rejestr", "SP"))
        self.kategoria_edit.setText(s.get("kategoria", "730-1"))
        self.bzrd_edit.setText(s.get("base_zrd_id", "BZ"))
        self.bdoc_edit.setText(s.get("base_doc_id", "K1"))
        self.detal_chk.setChecked(s.get("include_detal", True))
        self.output_dir_edit.setText(s.get("output_dir", ""))

    def _save_state(self) -> None:
        save_settings(
            {
                "initials": self.initials_edit.text().strip(),
                "rejestr": self.rejestr_edit.text().strip() or "SP",
                "kategoria": self.kategoria_edit.text().strip() or "730-1",
                "base_zrd_id": self.bzrd_edit.text().strip() or "BZ",
                "base_doc_id": self.bdoc_edit.text().strip() or "K1",
                "include_detal": self.detal_chk.isChecked(),
                "output_dir": self.output_dir_edit.text().strip(),
            }
        )

    def closeEvent(self, event) -> None:
        self._save_state()
        super().closeEvent(event)

    def _add_paths(self, paths: list[Path]) -> None:
        added = 0
        existing = {str(p) for p in self._files}
        for p in paths:
            if p.suffix.lower() != ".xml":
                continue
            if str(p) in existing:
                continue
            self._files.append(p)
            existing.add(str(p))
            item = QTreeWidgetItem([str(p), "Oczekuje"])
            self.tree.addTopLevelItem(item)
            added += 1
        if added:
            self.statusBar().showMessage(f"Dodano {added} plików (łącznie {len(self._files)})")

    def _on_add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Wybierz pliki XML do konwersji",
            "",
            "Pliki XML (*.xml);;Wszystkie pliki (*.*)",
        )
        if files:
            self._add_paths([Path(f) for f in files])

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Wybierz folder z plikami XML")
        if folder:
            paths = sorted(Path(folder).glob("*.xml"))
            self._add_paths(paths)

    def _on_remove(self) -> None:
        for item in list(self.tree.selectedItems()):
            idx = self.tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self.tree.takeTopLevelItem(idx)
                if 0 <= idx < len(self._files):
                    self._files.pop(idx)

    def _on_clear(self) -> None:
        self.tree.clear()
        self._files.clear()

    def _on_browse_out(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Wybierz folder docelowy")
        if folder:
            self.output_dir_edit.setText(folder)

    def _set_running(self, running: bool) -> None:
        self.convert_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        self.add_files_btn.setEnabled(not running)
        self.add_folder_btn.setEnabled(not running)
        self.remove_btn.setEnabled(not running)
        self.clear_btn.setEnabled(not running)

    def _on_convert(self) -> None:
        if not self._files:
            QMessageBox.information(self, APP_NAME, "Najpierw dodaj pliki XML do listy.")
            return

        out_dir_text = self.output_dir_edit.text().strip()
        out_dir = Path(out_dir_text) if out_dir_text else None
        opts = ConvertOptions(
            initials=self.initials_edit.text().strip(),
            rejestr=self.rejestr_edit.text().strip() or "SP",
            kategoria=self.kategoria_edit.text().strip() or "730-1",
            base_zrd_id=self.bzrd_edit.text().strip() or "BZ",
            base_doc_id=self.bdoc_edit.text().strip() or "K1",
            include_detal=self.detal_chk.isChecked(),
            output_dir=out_dir,
            when=date.today(),
        )
        self._save_state()

        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setText(1, "Oczekuje")

        self.log.clear()
        self.progress.setRange(0, len(self._files))
        self.progress.setValue(0)
        self._set_running(True)

        self._thread = QThread(self)
        self._worker = ConvertWorker(list(self._files), opts)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.finished.connect(self._on_all_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.statusBar().showMessage("Anulowanie…")

    def _on_progress(self, current: int, total: int, name: str) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(current - 1)
        self.statusBar().showMessage(f"[{current}/{total}] {name}")

    def _on_file_done(self, src: str, dst: str, error: str) -> None:
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.text(0) == src:
                if error:
                    it.setText(1, "BŁĄD")
                else:
                    it.setText(1, "OK")
                break
        if error:
            self.log.appendPlainText(f"[BŁĄD] {src}\n{error.strip()}\n")
        else:
            self.log.appendPlainText(f"[OK] {src}\n   → {dst}")
        self.progress.setValue(self.progress.value() + 1)

    def _on_all_done(self, ok: int, fail: int) -> None:
        self.progress.setValue(self.progress.maximum())
        self._set_running(False)
        msg = f"Zakończono. Sukces: {ok}, błędy: {fail}"
        self.statusBar().showMessage(msg)
        if fail and ok == 0:
            QMessageBox.critical(self, APP_NAME, msg)
        elif fail:
            QMessageBox.warning(self, APP_NAME, msg)
        else:
            QMessageBox.information(self, APP_NAME, msg)

    def _cleanup_thread(self) -> None:
        if self._thread:
            self._thread.deleteLater()
        if self._worker:
            self._worker.deleteLater()
        self._thread = None
        self._worker = None


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
