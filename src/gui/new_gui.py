#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import logging
import time
import os
from pathlib import Path
from typing import Optional, Dict

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QToolBar,
    QStatusBar, QMessageBox, QLineEdit, QMenu, QGridLayout, QFrame,
    QSizePolicy, QFormLayout, QSpinBox, QHBoxLayout, QTableWidget,
    QHeaderView, QTableWidgetItem, QPushButton, QFileDialog, QSplashScreen,
    QAbstractItemView
)
from PySide6.QtGui import QIcon, QFont, QAction, QCloseEvent, QColor, QPixmap
from PySide6.QtCore import Qt, QSize, Slot, QCoreApplication

from src.main_controller import MainController
from src.gui.config_window import ConfigWindow
from src.gui.telecommande_window import TelecommandeWindow
from src.gui.resource_manager import ResourceManager


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.controller = MainController()
        self.telecommande_window: Optional[TelecommandeWindow] = None
        self._actions: Dict[str, QAction] = {}
        self.current_highlighted_row = -1
        self._is_sequence_running = False
        self._setup_ui()

    def setup_controller_and_signals(self, splash: QSplashScreen):
        splash.showMessage("Initialisation du contrôleur Robot...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        QCoreApplication.processEvents()
        self.controller.setup_robot()
        time.sleep(0.5)

        splash.showMessage("Initialisation de l'interface PULSE Labshop...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        QCoreApplication.processEvents()
        self.controller.setup_pulse()
        time.sleep(0.5)

        splash.showMessage("Connexions finales...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        self.controller.log_message_sent.connect(self.update_status_bar)
        self.controller.point_list_changed.connect(self.update_points_table)
        self.controller.document_modified_status_changed.connect(self.update_save_action_state)
        self.controller.sequence_status_changed.connect(self._handle_sequence_state)
        self.controller.highlight_point_in_gui.connect(self.highlight_table_row)
        self.controller.sequence_finished_with_next_point.connect(self.on_single_point_sequence_finished)

    def _setup_ui(self) -> None:
        self.setWindowTitle('Logiciel de Pilotage Robot')
        self.setGeometry(150, 150, 1200, 700)
        self.setWindowIcon(QIcon(ResourceManager.get_icon_path('Window-icon.png')))
        self.setMinimumSize(800, 600)
        QApplication.instance().setStyle("Fusion")

        self._create_actions_and_connections()
        self._create_menus()
        self._create_toolbars()
        self._create_central_widget()
        self._create_statusbar()

        self._update_actions_state()

    def _add_action(self, name, icon, text, tip, shortcut=None, slot=None):
        action = QAction(QIcon(ResourceManager.get_icon_path(icon)), text, self)
        action.setStatusTip(tip)
        if shortcut: action.setShortcut(shortcut)
        if slot: action.triggered.connect(slot)
        self._actions[name] = action
        return action

    def _create_actions_and_connections(self) -> None:
        self._add_action('quitter', 'exit.png', '&Quitter', "Quitter l'application", 'Ctrl+Q', self.close)
        self._add_action('config', 'settings.png', 'Configuration...', "Configurer l'application",
                         slot=self._open_config_window)
        self._add_action('ouvrir', 'load_file.png', '&Ouvrir...', "Ouvrir une liste de points",
                         slot=self._open_point_file_dialog)
        self._add_action('enregistrer', 'save_file.png', '&Enregistrer', "Enregistrer la liste", 'Ctrl+S',
                         self._on_save_triggered)
        self._add_action('enregistrer_sous', 'save_as.png', 'Enregistrer &sous...', "Enregistrer sous un nouveau nom",
                         slot=self._on_save_as_triggered)
        self._add_action('telecommande', 'joystick.png', 'Télécommande', "Ouvrir la télécommande",
                         slot=self._open_telecommande)
        self._add_action('goto_parking', 'goto_parking.png', 'Aller au parking', "Aller au parking",
                         slot=self.controller.move_robot_to_parking)
        self._add_action('add_point', 'add.png', "Ajouter point", "Ajouter un nouveau point à la fin",
                         slot=self._on_add_point_triggered)
        self._add_action('delete_point', 'minus.png', "Supprimer point(s)", "Supprimer le(s) point(s) sélectionné(s)",
                         slot=self._on_delete_points_triggered)
        self._add_action('move_point_up', 'arrow_up.png', "Monter", "Déplacer vers le haut",
                         slot=self._on_move_up_triggered)
        self._add_action('move_point_down', 'arrow_down.png', "Descendre", "Déplacer vers le bas",
                         slot=self._on_move_down_triggered)

        self._add_action('start_sequence', 'play.png', 'Démarrer Séquence',
                         "Démarrer la séquence à partir du point sélectionné",
                         slot=self._on_start_full_sequence_triggered)
        self._add_action('next_point', 'next.png', 'Mesurer Point Suivant',
                         "Exécute la mesure pour le point sélectionné uniquement",
                         slot=self._on_next_point_triggered)
        self._add_action('pause_sequence', 'pause.png', 'Arrêter la séquence',
                         "Arrête la séquence après l'étape en cours",
                         slot=self.controller.stop_sequence)

        self._add_action('start_manual_measure', 'start_measurement.png', 'Démarrer mesure manuelle',
                         "Démarrer une mesure PULSE unique", slot=self.controller.start_manual_measurement)
        self._add_action('save_manual_measure', 'save_measurement.png', 'Sauvegarder mesure manuelle',
                         "Sauvegarder la dernière mesure manuelle", slot=self._on_save_manual_measure_triggered)

    def _create_menus(self) -> None:
        menu_bar = self.menuBar()
        menu_fichier = menu_bar.addMenu('&Fichier')
        menu_fichier.addAction(self._actions['ouvrir'])
        menu_fichier.addAction(self._actions['enregistrer'])
        menu_fichier.addAction(self._actions['enregistrer_sous'])
        menu_fichier.addSeparator()
        menu_fichier.addAction(self._actions['quitter'])
        menu_edition = menu_bar.addMenu('&Édition')
        menu_edition.addAction(self._actions['config'])
        menu_outils = menu_bar.addMenu('&Outils')
        menu_outils.addAction(self._actions['telecommande'])

    def _create_toolbars(self) -> None:
        toolbar_file = QToolBar("Fichier")
        self.addToolBar(toolbar_file)
        toolbar_file.addAction(self._actions['ouvrir'])
        toolbar_file.addAction(self._actions['enregistrer'])
        toolbar_file.addAction(self._actions['config'])

        toolbar_sequence = QToolBar("Séquence")
        self.addToolBar(toolbar_sequence)
        toolbar_sequence.addAction(self._actions['start_sequence'])
        toolbar_sequence.addAction(self._actions['pause_sequence'])
        toolbar_sequence.addAction(self._actions['next_point'])

        toolbar_manual = QToolBar("Mesure Manuelle")
        self.addToolBar(toolbar_manual)
        toolbar_manual.addAction(self._actions['start_manual_measure'])
        self.manual_filename_edit = QLineEdit("mesure_manuelle.txt")
        self.manual_filename_edit.setToolTip("Nom du fichier pour la prochaine mesure manuelle")
        toolbar_manual.addWidget(self.manual_filename_edit)
        toolbar_manual.addAction(self._actions['save_manual_measure'])
        self.addToolBarBreak()
        toolbar_robot = QToolBar("Outils Robot")
        self.addToolBar(toolbar_robot)
        toolbar_robot.addWidget(QLabel("Robot : "))
        toolbar_robot.addAction(self._actions['goto_parking'])
        toolbar_edition = QToolBar("Édition Liste")
        toolbar_edition.setOrientation(Qt.Orientation.Vertical)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, toolbar_edition)
        toolbar_edition.addAction(self._actions['add_point'])
        toolbar_edition.addAction(self._actions['delete_point'])
        toolbar_edition.addSeparator()
        toolbar_edition.addAction(self._actions['move_point_up'])
        toolbar_edition.addAction(self._actions['move_point_down'])

    def _create_central_widget(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        title_label = QLabel("Liste des points à mesurer")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        self.points_table = QTableWidget()
        self.points_table.verticalHeader().setVisible(True)
        self.points_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        main_layout.addWidget(self.points_table)
        self.points_table.itemSelectionChanged.connect(self._update_actions_state)
        self.points_table.cellChanged.connect(lambda: self.controller.set_document_modified(True))

    def _create_statusbar(self) -> None:
        self.statusBar().showMessage('Prêt')

    def _get_table_data(self) -> list[dict]:
        data = []
        headers = [self.points_table.horizontalHeaderItem(c).text().lower().replace("_", " ") for c in
                   range(self.points_table.columnCount())]
        headers = [h.replace(" ", "_") for h in headers]
        for row in range(self.points_table.rowCount()):
            row_data = {}
            for col, header in enumerate(headers):
                item = self.points_table.item(row, col)
                row_data[header] = item.text() if item else ""
            data.append(row_data)
        return data

    def _start_sequence_common(self, start_method):
        self.controller.sync_points_from_gui(self._get_table_data())
        selected_rows = {item.row() for item in self.points_table.selectedItems()}
        start_index = 0
        if selected_rows:
            start_index = min(selected_rows)

        missing_indices = self.controller.validate_filenames()
        if missing_indices:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("Noms de mesure manquants")
            msg_box.setText(f"{len(missing_indices)} point(s) n'ont pas de nom de fichier de mesure.")
            msg_box.setInformativeText("Voulez-vous les remplir automatiquement ?")
            autofill_button = msg_box.addButton("Auto-remplir", QMessageBox.AcceptRole)
            cancel_button = msg_box.addButton("Annuler", QMessageBox.RejectRole)
            msg_box.exec()

            if msg_box.clickedButton() == autofill_button:
                self.controller.autofill_filenames()
                QApplication.processEvents()
            else:
                self.update_status_bar("Action annulée. Veuillez remplir les noms de fichiers.")
                return

        self._is_sequence_running = True
        self._update_actions_state()
        start_method(start_index)

    @Slot()
    def _on_start_full_sequence_triggered(self):
        self._start_sequence_common(self.controller.start_full_sequence)

    @Slot()
    def _on_next_point_triggered(self):
        self._start_sequence_common(self.controller.start_single_point_sequence)

    @Slot(str)
    def _handle_sequence_state(self, status: str):
        self.update_status_bar(status)
        if "Démarrage" in status:
            self._is_sequence_running = True
        elif "Séquence terminée" in status or "ERREUR" in status or "arrêtée" in status:
            self._is_sequence_running = False
        self._update_actions_state()

    @Slot(str, int)
    def on_single_point_sequence_finished(self, final_message: str, next_point_index: int):
        if next_point_index < self.points_table.rowCount():
            self.points_table.selectRow(next_point_index)

    def _update_actions_state(self):
        running = self._is_sequence_running
        has_points = self.points_table.rowCount() > 0
        selected_items = self.points_table.selectedItems()
        selected_rows = {item.row() for item in selected_items}
        has_selection = len(selected_rows) > 0
        single_selection = len(selected_rows) == 1

        self._actions['start_sequence'].setEnabled(not running and has_points)
        self._actions['next_point'].setEnabled(not running and has_selection)
        self._actions['pause_sequence'].setEnabled(running)

        self._actions['add_point'].setEnabled(not running)
        self._actions['delete_point'].setEnabled(not running and has_selection)
        self._actions['move_point_up'].setEnabled(not running and single_selection and list(selected_rows)[0] > 0)
        self._actions['move_point_down'].setEnabled(
            not running and single_selection and list(selected_rows)[0] < self.points_table.rowCount() - 1)

        self._actions['ouvrir'].setEnabled(not running)
        self._actions['enregistrer'].setEnabled(not running and self.controller.is_modified)
        self._actions['enregistrer_sous'].setEnabled(not running)

        self.points_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers if running else QAbstractItemView.DoubleClicked
        )

    @Slot(int)
    def highlight_table_row(self, row_index: int):
        self.points_table.blockSignals(True)
        if self.current_highlighted_row != -1 and self.current_highlighted_row < self.points_table.rowCount():
            for col in range(self.points_table.columnCount()):
                item = self.points_table.item(self.current_highlighted_row, col)
                if item: item.setBackground(QColor("white"))
        if row_index != -1 and row_index < self.points_table.rowCount():
            for col in range(self.points_table.columnCount()):
                item = self.points_table.item(row_index, col)
                if item: item.setBackground(QColor("#a8d8ea"))
            self.points_table.selectRow(row_index)
            self.points_table.scrollToItem(self.points_table.item(row_index, 0))
        self.current_highlighted_row = row_index
        self.points_table.blockSignals(False)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._is_sequence_running:
            QMessageBox.warning(self, "Séquence en cours", "Veuillez d'abord arrêter la séquence avant de quitter.")
            event.ignore()
            return
        self.controller.sync_points_from_gui(self._get_table_data())
        if self.controller.is_modified:
            reply = QMessageBox.question(self, "Quitter",
                                         "Des modifications n'ont pas été sauvegardées.\nVoulez-vous les enregistrer avant de quitter ?",
                                         QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save:
                if not self._on_save_triggered():
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        self.controller.disconnect_robot()
        if self.telecommande_window: self.telecommande_window.close()
        event.accept()

    @Slot()
    def _open_point_file_dialog(self):
        if self.controller.is_modified:
            reply = QMessageBox.question(self, "Modifications non sauvegardées",
                                         "Voulez-vous sauvegarder vos modifications avant d'ouvrir un nouveau fichier ?",
                                         QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save:
                if not self._on_save_triggered():
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        file_path, _ = QFileDialog.getOpenFileName(self, "Ouvrir une liste de points", "",
                                                   "Fichiers de données (*.csv *.txt);;Tous les fichiers (*)")
        if file_path: self.controller.process_loaded_file(file_path)

    @Slot()
    def _on_save_triggered(self) -> bool:
        self.controller.sync_points_from_gui(self._get_table_data())
        if not self.controller.current_file_path:
            return self._on_save_as_triggered()
        return self.controller.save_point_list()

    @Slot()
    def _on_save_as_triggered(self) -> bool:
        self.controller.sync_points_from_gui(self._get_table_data())
        file_path, _ = QFileDialog.getSaveFileName(self, "Enregistrer la liste de points", "",
                                                   "Fichier Texte (*.txt);;Fichier CSV (*.csv);;Tous les fichiers (*)")
        if file_path:
            return self.controller.save_point_list_to_file(file_path)
        return False

    @Slot()
    def _on_add_point_triggered(self):
        self.controller.sync_points_from_gui(self._get_table_data())
        self.controller.add_new_point()

    @Slot()
    def _on_delete_points_triggered(self):
        selected_rows = sorted(list({item.row() for item in self.points_table.selectedItems()}))
        if not selected_rows: return
        reply = QMessageBox.question(self, "Confirmation",
                                     f"Voulez-vous vraiment supprimer {len(selected_rows)} point(s) ?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.controller.sync_points_from_gui(self._get_table_data())
            self.controller.delete_selected_points(selected_rows)

    @Slot()
    def _on_move_up_triggered(self):
        selected_rows = {item.row() for item in self.points_table.selectedItems()}
        if len(selected_rows) == 1:
            self.controller.sync_points_from_gui(self._get_table_data())
            self.controller.move_selected_point_up(list(selected_rows)[0])

    @Slot()
    def _on_move_down_triggered(self):
        selected_rows = {item.row() for item in self.points_table.selectedItems()}
        if len(selected_rows) == 1:
            self.controller.sync_points_from_gui(self._get_table_data())
            self.controller.move_selected_point_down(list(selected_rows)[0])

    @Slot()
    def _on_save_manual_measure_triggered(self):
        filename = self.manual_filename_edit.text()
        if not filename:
            QMessageBox.warning(self, "Nom de fichier manquant",
                                "Veuillez entrer un nom de fichier pour la sauvegarde.")
            return
        self.controller.save_manual_measurement(filename)

    @Slot(list)
    def update_points_table(self, points: list):
        self.points_table.blockSignals(True)
        self.points_table.setRowCount(0)
        headers = self.controller.get_point_headers()
        if not headers:
            self.points_table.blockSignals(False)
            return
        self.points_table.setColumnCount(len(headers))
        self.points_table.setHorizontalHeaderLabels([h.upper().replace("_", " ") for h in headers])
        if not points:
            self.points_table.blockSignals(False)
            self._update_actions_state()
            return
        self.points_table.setRowCount(len(points))
        for row_index, point_data in enumerate(points):
            for col_index, header in enumerate(headers):
                value = point_data.get(header, "")
                if isinstance(value, (float, int)):
                    item = QTableWidgetItem(f"{value}")
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.points_table.setItem(row_index, col_index, item)
        self.points_table.blockSignals(False)
        self.points_table.resizeColumnsToContents()
        self.points_table.horizontalHeader().setStretchLastSection(True)
        self._update_actions_state()

    @Slot(bool)
    def update_save_action_state(self, is_modified: bool):
        title = self.windowTitle().replace(" *", "")
        if is_modified:
            title += " *"
        self.setWindowTitle(title)
        self._update_actions_state()

    @Slot()
    def _open_telecommande(self):
        if self.telecommande_window is None or not self.telecommande_window.isVisible():
            self.telecommande_window = TelecommandeWindow(self.controller, self)
            self.telecommande_window.show()
            self.update_status_bar("Télécommande ouverte")
        else:
            self.telecommande_window.activateWindow()
            self.telecommande_window.raise_()

    @Slot()
    def _open_config_window(self):
        config_dialog = ConfigWindow(self.controller, self)
        config_dialog.exec()
        self.update_status_bar("Fenêtre de configuration fermée.")

    @Slot(str)
    def update_status_bar(self, message: str):
        print(f"[GUI Log] {message}")
        self.statusBar().showMessage(message, 5000)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - (%(threadName)s) %(message)s')
    app = QApplication(sys.argv)
    pixmap = ResourceManager.get_pixmap('splash.png')
    splash = QSplashScreen(pixmap)
    splash.show()
    app.processEvents()
    fenetre = MainWindow()
    fenetre.setup_controller_and_signals(splash)
    fenetre.show()
    splash.finish(fenetre)
    sys.exit(app.exec())