# src/gui/log_viewer_window.py

import os
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit
from PySide6.QtCore import Slot, QFileSystemWatcher, Qt
from PySide6.QtGui import QIcon

from src.gui.resource_manager import ResourceManager


class LogViewerWindow(QDialog):
    """
    Une fenêtre de dialogue qui affiche le contenu d'un fichier journal
    et le met à jour en temps réel.
    """
    def __init__(self, file_path: str, title: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(QIcon(ResourceManager.get_icon_path(icon_name)))
        self.setGeometry(250, 250, 800, 600)

        self.file_path = file_path
        self.last_pos = 0

        # Widget principal pour afficher le texte
        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("font-family: Consolas, 'Courier New', monospace; background-color: #f0f0f0;")

        # Layout
        layout = QVBoxLayout(self)
        layout.addWidget(self.text_edit)
        self.setLayout(layout)

        # Surveillant de fichier
        self.watcher = QFileSystemWatcher([self.file_path], self)
        self.watcher.fileChanged.connect(self._update_log_content)

        # Chargement initial du contenu
        self._initial_load()

    def _initial_load(self):
        """Charge le contenu existant du fichier au démarrage."""
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.text_edit.setPlainText(content)
                    self.last_pos = f.tell()
                    # Défiler jusqu'en bas
                    self.text_edit.verticalScrollBar().setValue(self.text_edit.verticalScrollBar().maximum())
        except Exception as e:
            self.text_edit.setPlainText(f"Erreur lors du chargement du fichier de log : {e}")

    @Slot(str)
    def _update_log_content(self, path):
        """Met à jour le contenu en lisant uniquement les nouvelles lignes."""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                f.seek(self.last_pos)
                new_text = f.read()
                if new_text:
                    self.text_edit.moveCursor(self.text_edit.textCursor().MoveOperation.End)
                    self.text_edit.insertPlainText(new_text)
                    self.last_pos = f.tell()
        except Exception as e:
            # Gérer le cas où le fichier est recréé
            if not os.path.exists(self.file_path):
                 self.last_pos = 0
            print(f"Erreur de lecture du log : {e}")