# src/gui/log_viewer_window.py

import os
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QCheckBox, QHBoxLayout, QWidget
from PySide6.QtCore import Slot, QFileSystemWatcher, Qt
from PySide6.QtGui import QIcon, QFont

from src.gui.resource_manager import ResourceManager


class LogViewerWindow(QDialog):
    """
    Une fenêtre de dialogue qui affiche le contenu d'un fichier journal
    et le met à jour en temps réel, avec des options de filtrage par niveau.
    """

    def __init__(self, file_path: str, title: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(QIcon(ResourceManager.get_icon_path(icon_name)))
        self.setGeometry(250, 250, 800, 600)

        self.file_path = file_path

        # --- NOUVEAU : Stockage en mémoire de toutes les lignes ---
        self.all_lines = []
        self.last_pos = 0

        # --- NOUVEAU : Filtres ---
        filter_widget = QWidget(self)
        filter_layout = QHBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)

        self.log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        self.filter_checkboxes = {}

        for level in self.log_levels:
            checkbox = QCheckBox(level, self)
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._refilter_log_view)
            self.filter_checkboxes[level] = checkbox
            filter_layout.addWidget(checkbox)

        filter_layout.addStretch()

        # Widget principal pour afficher le texte
        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas, 'Courier New', monospace", 10))
        self.text_edit.setStyleSheet("background-color: #fdfdfd;")

        # Layout principal
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(filter_widget)  # Ajout de la barre de filtres
        main_layout.addWidget(self.text_edit)
        self.setLayout(main_layout)

        # Surveillant de fichier
        self.watcher = QFileSystemWatcher([self.file_path], self)
        self.watcher.fileChanged.connect(self._update_log_content)

        # Chargement initial du contenu
        self._initial_load()

    def _initial_load(self):
        """Charge le contenu existant du fichier et le filtre."""
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.all_lines = content.splitlines()
                    self.last_pos = f.tell()
                self._refilter_log_view()  # Appliquer le filtre initial
        except Exception as e:
            self.text_edit.setPlainText(f"Erreur lors du chargement du fichier de log : {e}")

    @Slot()
    def _refilter_log_view(self):
        """Efface et ré-affiche le contenu en fonction des filtres actifs."""
        active_levels = {level for level, cb in self.filter_checkboxes.items() if cb.isChecked()}

        filtered_lines = []
        for line in self.all_lines:
            # On vérifie si un des niveaux actifs est dans la ligne.
            # L'ajout des " - " permet de ne pas matcher des mots comme "INFORMATION".
            if any(f" - {level}" in line for level in active_levels):
                filtered_lines.append(line)

        self.text_edit.setPlainText("\n".join(filtered_lines))
        # Défiler jusqu'en bas
        self.text_edit.verticalScrollBar().setValue(self.text_edit.verticalScrollBar().maximum())

    @Slot(str)
    def _update_log_content(self, path):
        """Lit les nouvelles lignes, les ajoute à la liste et à la vue si elles correspondent au filtre."""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                f.seek(self.last_pos)
                new_text = f.read()
                if new_text:
                    new_lines = new_text.strip().splitlines()
                    self.all_lines.extend(new_lines)
                    self.last_pos = f.tell()

                    # Appliquer le filtre seulement sur les nouvelles lignes pour l'affichage
                    active_levels = {level for level, cb in self.filter_checkboxes.items() if cb.isChecked()}
                    lines_to_append = []
                    for line in new_lines:
                        if any(f" - {level}" in line for level in active_levels):
                            lines_to_append.append(line)

                    if lines_to_append:
                        self.text_edit.moveCursor(self.text_edit.textCursor().MoveOperation.End)
                        self.text_edit.insertPlainText("\n" + "\n".join(lines_to_append))

        except Exception as e:
            if not os.path.exists(self.file_path):
                self.last_pos = 0
            print(f"Erreur de lecture du log : {e}")