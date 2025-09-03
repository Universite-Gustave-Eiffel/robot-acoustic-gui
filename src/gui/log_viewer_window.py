# -*- coding: utf-8 -*-
# src/gui/log_viewer_window.py

import os
from collections import deque
from pathlib import Path
from typing import Deque, List, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QCheckBox,
    QPushButton, QWidget, QSizePolicy, QMessageBox
)

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
MAX_DOC_LINES = 20000  # borne d'affichage : n'affiche que les N dernières lignes dans le widget


class LogViewerWindow(QDialog):
    """
    Visionneuse de logs :
      - suit le fichier (tail -f) sans le tronquer
      - filtre par niveaux
      - défilement auto optionnel
      - borne l'affichage pour rester fluide (le fichier, lui, reste complet)
    """
    def __init__(self, file_path: str, title: str, icon_name_or_path: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        if icon_name_or_path:
            try:
                self.setWindowIcon(QIcon(icon_name_or_path))
            except Exception:
                pass

        self.file_path = Path(file_path)

        # état lecture
        self._pos: int = 0
        self._buffer: Deque[str] = deque(maxlen=20000)  # buffer mémoire borné pour rebuild rapide
        self._last_render_count: int = 0

        # filtres niveaux (par défaut tout coché)
        self._levels_enabled = {lvl: True for lvl in LEVELS}

        # défilement auto
        self._auto_scroll: bool = True

        self._build_ui()
        self._wire_events()

        # timer de polling
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_file)
        self._timer.start(500)

        # première lecture : tout le fichier
        self._poll_file(initial=True)

    # ---------- UI ----------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # chemin du fichier
        path_row = QHBoxLayout()
        self.lbl_path = QLabel(str(self.file_path))
        self.lbl_path.setStyleSheet("color: gray;")
        self.lbl_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_row.addWidget(self.lbl_path)
        path_row.addStretch(1)
        layout.addLayout(path_row)

        # filtres niveaux
        filt_row = QHBoxLayout()
        filt_row.addWidget(QLabel("Niveaux :"))
        self.chk_levels = {}
        for lvl in LEVELS:
            cb = QCheckBox(lvl)
            cb.setChecked(True)
            self.chk_levels[lvl] = cb
            filt_row.addWidget(cb)

        filt_row.addStretch(1)

        self.chk_autoscroll = QCheckBox("Défilement auto")
        self.chk_autoscroll.setChecked(True)
        filt_row.addWidget(self.chk_autoscroll)

        self.btn_open_dir = QPushButton("Ouvrir dossier")
        filt_row.addWidget(self.btn_open_dir)

        layout.addLayout(filt_row)

        # zone texte
        self.view = QPlainTextEdit(self)
        self.view.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        self.view.setFont(mono)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.view)

        self.setMinimumSize(900, 600)

    def _wire_events(self):
        for lvl, cb in self.chk_levels.items():
            cb.toggled.connect(lambda checked, L=lvl: self._on_level_toggled(L, checked))
        self.chk_autoscroll.toggled.connect(self._on_autoscroll_toggled)
        self.btn_open_dir.clicked.connect(self._on_open_dir)

    # ---------- Slots ----------

    def _on_level_toggled(self, level: str, checked: bool):
        self._levels_enabled[level] = bool(checked)
        self._rebuild_view_full()

    def _on_autoscroll_toggled(self, val: bool):
        self._auto_scroll = bool(val)
        if self._auto_scroll:
            self._scroll_to_bottom()

    def _on_open_dir(self):
        if not self.file_path.exists():
            QMessageBox.information(self, "Ouvrir dossier", "Fichier introuvable.")
            return
        folder = str(self.file_path.parent)
        try:
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif os.sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}"')
        except Exception:
            pass

    # ---------- Lecture / rendu ----------

    def _poll_file(self, initial: bool = False):
        try:
            if not self.file_path.exists():
                return

            size = self.file_path.stat().st_size
            if initial or size < self._pos:
                # fichier nouveau/rotaté → repartir au début
                self._pos = 0
                self._buffer.clear()
                self._last_render_count = 0

            if size == self._pos and not initial:
                return

            with self.file_path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(self._pos)
                data = f.read()
                self._pos = f.tell()

            if not data and not initial:
                return

            lines = data.splitlines(True)
            for ln in lines:
                self._buffer.append(ln)

            if self.view.document().isEmpty() or self._last_render_count == 0 or initial:
                self._rebuild_view_full()
            else:
                self._render_incremental(lines)

        except Exception:
            # silencieux pour ne pas polluer l'UI
            pass

    def _render_incremental(self, new_lines: List[str]):
        filtered = self._apply_level_filter(new_lines)
        if not filtered:
            return

        was_bottom = self._is_near_bottom()
        sb = self.view.verticalScrollBar()
        prev_value = sb.value()

        # insertion via curseur de document (pas le curseur du widget)
        doc_cursor = QTextCursor(self.view.document())
        doc_cursor.movePosition(QTextCursor.End)
        doc_cursor.insertText("".join(filtered))
        self._last_render_count += len(filtered)

        # autoscroll seulement si actif OU si on était déjà en bas
        if self._auto_scroll or was_bottom:
            self._scroll_to_bottom()
        else:
            sb.setValue(prev_value)

        # borne l'affichage pour garder la vue fluide (le fichier n'est pas touché)
        self._trim_document_if_needed()

    def _rebuild_view_full(self):
        filtered = self._apply_level_filter(list(self._buffer))
        self.view.setPlainText("".join(filtered))
        self._last_render_count = len(filtered)
        if self._auto_scroll:
            self._scroll_to_bottom()
        self._trim_document_if_needed()

    def _apply_level_filter(self, lines: List[str]) -> List[str]:
        out: List[str] = []
        enabled = self._levels_enabled

        for ln in lines:
            try:
                parts = ln.split(" - ")
                level = parts[2].strip().split()[0] if len(parts) >= 3 else ""
            except Exception:
                level = ""

            if level in enabled:
                if not enabled[level]:
                    continue  # niveau désactivé → on saute
            # niveau inconnu → on affiche quand même
            out.append(ln)

        return out

    # ---------- utilitaires UI ----------

    def _is_near_bottom(self) -> bool:
        sb = self.view.verticalScrollBar()
        return sb.value() >= sb.maximum() - 2

    def _scroll_to_bottom(self):
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _trim_document_if_needed(self):
        """
        Maintient le nombre de blocs (≈ lignes) affichés sous MAX_DOC_LINES
        sans jamais toucher au fichier source.
        """
        doc = self.view.document()
        blocks = doc.blockCount()
        if blocks <= MAX_DOC_LINES:
            return

        excess = blocks - MAX_DOC_LINES

        sb = self.view.verticalScrollBar()
        was_bottom = self._is_near_bottom()
        prev_value = sb.value()

        cur = QTextCursor(doc)
        start_pos = doc.findBlockByNumber(0).position()
        end_pos = doc.findBlockByNumber(excess).position()
        cur.setPosition(start_pos)
        cur.setPosition(end_pos, QTextCursor.KeepAnchor)
        cur.removeSelectedText()
        # nettoie un éventuel \n résiduel
        cur.deleteChar()

        if self._auto_scroll or was_bottom:
            self._scroll_to_bottom()
        else:
            sb.setValue(prev_value)

    def closeEvent(self, ev):
        try:
            self._timer.stop()
        except Exception:
            pass
        super().closeEvent(ev)
