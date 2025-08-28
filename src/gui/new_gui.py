#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import logging
import logging.handlers
import time
import os
from pathlib import Path
from typing import Optional, Dict

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QToolBar,
    QStatusBar, QMessageBox, QLineEdit, QMenu, QGridLayout, QFrame,
    QSizePolicy, QFormLayout, QSpinBox, QHBoxLayout, QTableWidget,
    QHeaderView, QTableWidgetItem, QPushButton, QFileDialog, QSplashScreen,
    QAbstractItemView, QStyledItemDelegate
)
from PySide6.QtGui import QIcon, QFont, QAction, QCloseEvent, QColor, QPixmap, QIntValidator, QUndoStack
from PySide6.QtCore import Qt, QSize, Slot, QCoreApplication

from src.main_controller import MainController
from src.gui.config_window import ConfigWindow
from src.gui.telecommande_window import TelecommandeWindow
from src.gui.resource_manager import ResourceManager
from src.gui.commands import AddPointCommand, DeletePointsCommand, MovePointCommand, ChangeCellCommand
from src.gui.log_viewer_window import LogViewerWindow


# --- CONFIGURATION CENTRALISÉE DES LOGS ---
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
ROBOT_LOG_FILE = LOG_DIR / "robot_app.log"
PULSE_LOG_FILE = LOG_DIR / "pulse_driver.log"

def setup_logging():
    """Configure les loggers pour l'application avec des fichiers distincts."""
    log_formatter = logging.Formatter('%(asctime)s - %(name)-25s - %(levelname)-8s - (%(threadName)s) %(message)s')

    # Logger Racine (pour la console)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capturer tous les niveaux

    # Vider les handlers existants pour éviter les doublons
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.INFO)  # N'afficher que INFO et plus dans la console
    root_logger.addHandler(console_handler)

    # Handler pour les logs Robot
    robot_handler = logging.handlers.RotatingFileHandler(ROBOT_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=2,
                                                         encoding='utf-8')
    robot_handler.setFormatter(log_formatter)
    robot_handler.setLevel(logging.DEBUG)
    logging.getLogger("RobotApp").addHandler(robot_handler)

    # Handler pour les logs PULSE
    pulse_handler = logging.handlers.RotatingFileHandler(PULSE_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=2,
                                                         encoding='utf-8')
    pulse_handler.setFormatter(log_formatter)
    pulse_handler.setLevel(logging.DEBUG)
    # On attache ce handler spécifiquement au logger du driver Pulse
    logging.getLogger("RobotApp.PulseDriver").addHandler(pulse_handler)

    # Empêcher les logs Pulse de remonter au logger "RobotApp" pour ne pas les écrire dans les deux fichiers
    logging.getLogger("RobotApp.PulseDriver").propagate = False

    logging.info("Système de logging initialisé.")
# --- FIN DE LA SECTION LOGS ---


class IntegerDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        validator = QIntValidator(parent)
        editor.setValidator(validator)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, 0)
        editor.setText(str(value))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.controller = MainController()
        self.telecommande_window: Optional[TelecommandeWindow] = None
        self.robot_log_window: Optional[LogViewerWindow] = None
        self.pulse_log_window: Optional[LogViewerWindow] = None
        self._actions: Dict[str, QAction] = {}
        self.current_highlighted_row = -1
        self._is_sequence_running = False

        self.undo_stack = QUndoStack(self)

        self.status_bar_labels = {}

        self._setup_ui()

    def setup_controller_and_signals(self):
        self.controller.log_message_sent.connect(self.update_status_bar)
        self.controller.point_list_changed.connect(self.update_points_table)
        self.controller.document_modified_status_changed.connect(self.update_save_action_state)
        self.controller.sequence_status_changed.connect(self._handle_sequence_state)
        self.controller.highlight_point_in_gui.connect(self.highlight_table_row)
        self.controller.sequence_finished_with_next_point.connect(self.on_single_point_sequence_finished)
        self.controller.robot_position_updated.connect(self.update_coordinate_display)

        self.undo_stack.canUndoChanged.connect(self._actions['undo'].setEnabled)
        self.undo_stack.canRedoChanged.connect(self._actions['redo'].setEnabled)
        self.undo_stack.cleanChanged.connect(lambda is_clean: self.controller.set_document_modified(not is_clean))

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
        self._add_action('urgence', 'stop.png', 'Arrêt d\'Urgence', "Arrêt immédiat de tous les mouvements", 'F12',
                         self.controller.emergency_stop)
        self._add_action('nouveau', 'new_file.png', '&Nouveau', "Créer une nouvelle liste de points", 'Ctrl+N',
                         self._on_new_triggered)
        self._add_action('quitter', 'exit.png', '&Quitter', "Quitter l'application", 'Ctrl+Q', self.close)
        self._add_action('config', 'settings.png', 'Configuration...', "Configurer l'application",
                         slot=self._open_config_window)
        self._add_action('ouvrir', 'load_file.png', '&Ouvrir...', "Ouvrir une liste de points",
                         slot=self._open_point_file_dialog)
        self._add_action('enregistrer', 'save_file.png', '&Enregistrer', "Enregistrer la liste", 'Ctrl+S',
                         self._on_save_triggered)
        self._add_action('enregistrer_sous', 'save_as.png', 'Enregistrer &sous...', "Enregistrer sous un nouveau nom",
                         slot=self._on_save_as_triggered)

        self._add_action('undo', 'undo.png', 'Annuler', "Annuler la dernière action", 'Ctrl+Z', self.undo_stack.undo)
        self._add_action('redo', 'redo.png', 'Rétablir', "Rétablir la dernière action annulée", 'Ctrl+Y',
                         self.undo_stack.redo)
        self._actions['undo'].setEnabled(False)
        self._actions['redo'].setEnabled(False)

        self._add_action('telecommande', 'joystick.png', 'Télécommande', "Ouvrir la télécommande",
                         slot=self._open_telecommande)
        self._add_action('goto_parking', 'goto_parking.png', 'Aller au parking', "Aller au parking",
                         slot=self.controller.move_robot_to_parking)
        self._add_action('goto_selected', 'goto_point.png', 'Aller au point sélectionné',
                         "Déplace le robot vers le point sélectionné dans la liste",
                         slot=self._on_goto_selected_point_triggered)
        self._add_action('goto_zero', 'goto_zero.png', 'Aller au Zéro',
                         "Déplace le robot aux coordonnées capsule 0,0,0,0,0", slot=self._on_goto_zero_triggered)

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
                         "Exécute la mesure pour le point sélectionné uniquement", slot=self._on_next_point_triggered)
        self._add_action('pause_sequence', 'pause.png', 'Arrêter la séquence',
                         "Arrête la séquence après l'étape en cours", slot=self.controller.stop_sequence)

        self._add_action('toggle_pulse', 'pulse.png', 'Afficher/Cacher PULSE',
                         "Affiche ou cache la fenêtre de PULSE LabShop", slot=self.controller.toggle_pulse_visibility)
        self._add_action('start_manual_measure', 'start_measurement.png', 'Démarrer mesure manuelle',
                         "Démarrer une mesure PULSE unique", slot=self.controller.start_manual_measurement)
        self._add_action('save_manual_measure', 'save_measurement.png', 'Sauvegarder mesure manuelle',
                         "Sauvegarder la dernière mesure manuelle", slot=self._on_save_manual_measure_triggered)

        self._add_action('show_robot_log', 'log_robot.png', 'Afficher Logs Robot',
                         "Ouvre la fenêtre des logs du robot et du contrôleur", slot=self._open_robot_log_viewer)
        self._add_action('show_pulse_log', 'log_pulse.png', 'Afficher Logs PULSE',
                         "Ouvre la fenêtre des logs de l'interface PULSE", slot=self._open_pulse_log_viewer)

    def _create_menus(self) -> None:
        menu_bar = self.menuBar()
        menu_fichier = menu_bar.addMenu('&Fichier')
        menu_fichier.addAction(self._actions['nouveau'])
        menu_fichier.addAction(self._actions['ouvrir'])
        menu_fichier.addAction(self._actions['enregistrer'])
        menu_fichier.addAction(self._actions['enregistrer_sous'])
        menu_fichier.addSeparator()
        menu_fichier.addAction(self._actions['quitter'])
        menu_edition = menu_bar.addMenu('&Édition')
        menu_edition.addAction(self._actions['undo'])
        menu_edition.addAction(self._actions['redo'])
        menu_edition.addSeparator()
        menu_edition.addAction(self._actions['config'])
        menu_outils = menu_bar.addMenu('&Outils')
        menu_outils.addAction(self._actions['telecommande'])

    def _create_toolbars(self) -> None:
        toolbar_file = QToolBar("Fichier")
        self.addToolBar(toolbar_file)
        toolbar_file.addAction(self._actions['nouveau'])
        toolbar_file.addAction(self._actions['ouvrir'])
        toolbar_file.addAction(self._actions['enregistrer'])

        toolbar_edit = QToolBar("Édition")
        self.addToolBar(toolbar_edit)
        toolbar_edit.addAction(self._actions['undo'])
        toolbar_edit.addAction(self._actions['redo'])
        toolbar_edit.addAction(self._actions['config'])

        toolbar_sequence = QToolBar("Séquence")
        self.addToolBar(toolbar_sequence)
        toolbar_sequence.addWidget(QLabel("Séquence : "))
        toolbar_sequence.addAction(self._actions['start_sequence'])
        toolbar_sequence.addAction(self._actions['pause_sequence'])
        toolbar_sequence.addAction(self._actions['next_point'])
        toolbar_sequence.addSeparator()
        toolbar_sequence.addAction(self._actions['urgence'])

        toolbar_manual = QToolBar("Mesure Manuelle")
        self.addToolBar(toolbar_manual)
        toolbar_manual.addWidget(QLabel("Pulse : "))
        toolbar_manual.addAction(self._actions['toggle_pulse'])
        toolbar_manual.addSeparator()
        toolbar_manual.addAction(self._actions['start_manual_measure'])
        self.manual_filename_edit = QLineEdit("mesure_manuelle.txt")
        self.manual_filename_edit.setToolTip("Nom du fichier pour la prochaine mesure manuelle")
        toolbar_manual.addWidget(self.manual_filename_edit)
        toolbar_manual.addAction(self._actions['save_manual_measure'])
        self.addToolBarBreak()

        toolbar_monitoring = QToolBar("Monitoring")
        self.addToolBar(toolbar_monitoring)
        toolbar_monitoring.addWidget(QLabel("Logs : "))
        toolbar_monitoring.addAction(self._actions['show_robot_log'])
        toolbar_monitoring.addAction(self._actions['show_pulse_log'])
        toolbar_monitoring.addSeparator()

        toolbar_robot = QToolBar("Outils Robot")
        self.addToolBar(toolbar_robot)
        toolbar_robot.addWidget(QLabel("Robot : "))
        toolbar_robot.addAction(self._actions['goto_parking'])
        toolbar_robot.addAction(self._actions['goto_zero'])
        toolbar_robot.addAction(self._actions['goto_selected'])
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
        self.points_table.itemChanged.connect(self._on_cell_changed)

    def _create_statusbar(self) -> None:
        status_bar = self.statusBar()
        self.status_message_label = QLabel("Prêt")
        status_bar.addWidget(self.status_message_label, 1)  # Le '1' donne l'espace extensible

        coord_widget = QWidget()
        coord_layout = QHBoxLayout(coord_widget)
        coord_layout.setContentsMargins(10, 0, 10, 0)

        axes = ['X', 'Y', 'Z', 'Theta', 'Phi']
        for axis in axes:
            label = QLabel(f"{axis}: N/C")
            label.setMinimumWidth(80)
            coord_layout.addWidget(label)
            self.status_bar_labels[axis] = label

        status_bar.addPermanentWidget(coord_widget)

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

    @Slot()
    def _on_goto_selected_point_triggered(self):
        selected_rows = {item.row() for item in self.points_table.selectedItems()}
        if len(selected_rows) != 1:
            self.update_status_bar("Veuillez sélectionner une seule ligne de destination.")
            return
        selected_row = list(selected_rows)[0]
        point_data = {}
        for col in range(self.points_table.columnCount()):
            header = self.points_table.horizontalHeaderItem(col).text().lower().replace(" ", "_")
            item = self.points_table.item(selected_row, col)
            point_data[header] = item.text() if item else "0.0"
        self.update_status_bar(f"Déplacement vers le point {selected_row + 1}...")
        self.controller.move_to_point_data(point_data)

    @Slot()
    def _on_goto_zero_triggered(self):
        zero_coords = {'X': 0.0, 'Y': 0.0, 'Z': 0.0, 'THETA': 0.0, 'PHI': 0.0}
        self.update_status_bar("Déplacement vers le Zéro Capsule...")
        self.controller.move_capsule_absolute(zero_coords)

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
        self._actions['next_point'].setEnabled(not running and single_selection)
        self._actions['pause_sequence'].setEnabled(running)
        self._actions['urgence'].setEnabled(running)

        self._actions['add_point'].setEnabled(not running)
        self._actions['delete_point'].setEnabled(not running and has_selection)
        self._actions['move_point_up'].setEnabled(not running and single_selection and list(selected_rows)[0] > 0)
        self._actions['move_point_down'].setEnabled(
            not running and single_selection and list(selected_rows)[0] < self.points_table.rowCount() - 1)

        self._actions['nouveau'].setEnabled(not running)
        self._actions['ouvrir'].setEnabled(not running)
        self._actions['enregistrer'].setEnabled(not running and self.controller.is_modified)
        self._actions['enregistrer_sous'].setEnabled(not running)
        self._actions['goto_parking'].setEnabled(not running)
        self._actions['goto_zero'].setEnabled(not running)
        self._actions['goto_selected'].setEnabled(not running and single_selection)

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

        if not self.undo_stack.isClean():
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

        # --- MODIFICATION DE LA SÉQUENCE DE FERMETURE ---

        # 1. Accepter l'événement de fermeture pour que Qt sache que la fenêtre va se fermer.
        event.accept()

        # 2. Cacher la fenêtre explicitement. Cela retire l'interface de l'écran.
        self.hide()

        # 3. Fermer les fenêtres enfants qui pourraient dépendre du contrôleur.
        if self.telecommande_window:
            self.telecommande_window.close()
        if self.robot_log_window:
            self.robot_log_window.close()
        if self.pulse_log_window:
            self.pulse_log_window.close()

        # 4. Maintenant, faire le nettoyage lourd (déconnexion matériel).
        self.controller.disconnect_robot()

    @Slot()
    def _open_point_file_dialog(self):
        if not self.undo_stack.isClean():
            reply = QMessageBox.question(self, "Modifications non sauvegardées",
                                         "Voulez-vous sauvegarder vos modifications avant d'ouvrir un nouveau fichier ?",
                                         QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save:
                if not self._on_save_triggered(): return
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        file_path, _ = QFileDialog.getOpenFileName(self, "Ouvrir une liste de points", "",
                                                   "Fichiers de données (*.csv *.txt);;Tous les fichiers (*)")
        if file_path:
            self.controller.process_loaded_file(file_path)
            self.undo_stack.clear()

    @Slot()
    def _on_new_triggered(self):
        """Gère la création d'une nouvelle liste de points."""
        if not self.undo_stack.isClean():
            reply = QMessageBox.question(self, "Modifications non sauvegardées",
                                         "Voulez-vous sauvegarder vos modifications avant de créer un nouveau fichier ?",
                                         QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save:
                if not self._on_save_triggered():
                    return  # L'utilisateur a annulé la sauvegarde
            elif reply == QMessageBox.StandardButton.Cancel:
                return  # Annuler l'opération "Nouveau"

        # Procéder à la création du nouveau fichier
        self.controller.create_new_point_list()
        self.undo_stack.clear()  # Ceci remet l'état à "propre"
        self.controller.point_list_changed.emit([])  # Émettre avec une liste vide pour vider le tableau

    @Slot()
    def _on_save_triggered(self) -> bool:
        self.controller.sync_points_from_gui(self._get_table_data())
        if self.controller.current_file_path:
            success = self.controller.save_point_list_to_file(self.controller.current_file_path)
            if success:
                self.undo_stack.setClean()
            return success
        else:
            return self._on_save_as_triggered()

    @Slot()
    def _on_save_as_triggered(self) -> bool:
        self.controller.sync_points_from_gui(self._get_table_data())
        file_path, _ = QFileDialog.getSaveFileName(self, "Enregistrer la liste de points", "",
                                                   "Fichier Texte (*.txt);;Fichier CSV (*.csv);;Tous les fichiers (*)")
        if file_path:
            success = self.controller.save_point_list_to_file(file_path)
            if success:
                self.undo_stack.setClean()
            return success
        return False

    @Slot()
    def _on_add_point_triggered(self):
        point_to_add = self.controller.add_current_position_as_point()
        command = AddPointCommand(self.controller, self, point_to_add if point_to_add else None)
        self.undo_stack.push(command)

    @Slot()
    def _on_delete_points_triggered(self):
        selected_rows = sorted(list({item.row() for item in self.points_table.selectedItems()}))
        if not selected_rows: return
        command = DeletePointsCommand(self.controller, self, selected_rows)
        self.undo_stack.push(command)

    @Slot()
    def _on_move_up_triggered(self):
        selected_rows = {item.row() for item in self.points_table.selectedItems()}
        if len(selected_rows) == 1:
            index = list(selected_rows)[0]
            if index > 0:
                command = MovePointCommand(self.controller, self, index, "haut")
                self.undo_stack.push(command)

    @Slot()
    def _on_move_down_triggered(self):
        selected_rows = {item.row() for item in self.points_table.selectedItems()}
        if len(selected_rows) == 1:
            index = list(selected_rows)[0]
            if index < self.points_table.rowCount() - 1:
                command = MovePointCommand(self.controller, self, index, "bas")
                self.undo_stack.push(command)

    @Slot(QTableWidgetItem)
    def _on_cell_changed(self, item):
        col = item.column()
        row = item.row()
        header = self.controller.get_point_headers()[col]

        if header == 'Nom_fichier': return

        old_value = getattr(self.controller.point_manager.points[row], header)
        new_value_text = item.text()

        if str(old_value) == new_value_text:
            return

        command = ChangeCellCommand(self.controller, self, row, col, old_value, new_value_text)
        self.undo_stack.push(command)

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
        self.points_table.itemChanged.disconnect(self._on_cell_changed)
        self.points_table.setRowCount(0)
        headers = self.controller.get_point_headers()
        if not headers:
            self.points_table.itemChanged.connect(self._on_cell_changed)
            return
        self.points_table.setColumnCount(len(headers))
        self.points_table.setHorizontalHeaderLabels([h.upper().replace("_", " ") for h in headers])

        integer_delegate = IntegerDelegate(self)
        numeric_columns = ['x', 'y', 'z', 'theta', 'phi', 'Nb_mesures/point']
        for col_index, header in enumerate(headers):
            if header in numeric_columns:
                self.points_table.setItemDelegateForColumn(col_index, integer_delegate)

        if points:
            self.points_table.setRowCount(len(points))
            for row_index, point_data in enumerate(points):
                for col_index, header in enumerate(headers):
                    value = point_data.get(header, "")
                    if isinstance(value, (float, int)):
                        item = QTableWidgetItem(f"{round(value)}")
                    else:
                        item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.points_table.setItem(row_index, col_index, item)


        header = self.points_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.points_table.itemChanged.connect(self._on_cell_changed)
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
        self.status_message_label.setText(message)

    @Slot(dict, dict)
    def update_coordinate_display(self, robot_pos: dict, capsule_pos: dict):
        self.status_bar_labels['X'].setText(f"X: {round(capsule_pos.get('X', 0.0))}")
        self.status_bar_labels['Y'].setText(f"Y: {round(capsule_pos.get('Y', 0.0))}")
        self.status_bar_labels['Z'].setText(f"Z: {round(capsule_pos.get('Z', 0.0))}")
        # On utilise robot_pos pour les angles, car ils sont identiques
        self.status_bar_labels['Theta'].setText(f"θ: {round(robot_pos.get('THETA', 0.0))}")
        self.status_bar_labels['Phi'].setText(f"φ: {round(robot_pos.get('PHI', 0.0))}")

    @Slot()
    def _open_robot_log_viewer(self):
        """Ouvre ou active la fenêtre de log du robot."""
        if self.robot_log_window is None or not self.robot_log_window.isVisible():
            self.robot_log_window = LogViewerWindow(
                str(ROBOT_LOG_FILE), "Logs Robot & Application", "log_robot.png", self
            )
            self.robot_log_window.show()
        else:
            self.robot_log_window.activateWindow()
            self.robot_log_window.raise_()

    @Slot()
    def _open_pulse_log_viewer(self):
        """Ouvre ou active la fenêtre de log de PULSE."""
        if self.pulse_log_window is None or not self.pulse_log_window.isVisible():
            self.pulse_log_window = LogViewerWindow(
                str(PULSE_LOG_FILE), "Logs Interface PULSE LabShop", "log_pulse.png", self
            )
            self.pulse_log_window.show()
        else:
            self.pulse_log_window.activateWindow()
            self.pulse_log_window.raise_()


def run_application():
    """
    Fonction principale qui gère le cycle de vie de l'application,
    y compris les vérifications de démarrage.
    """
    app = QApplication(sys.argv)

    controller = MainController()

    pixmap = ResourceManager.get_pixmap('splash.png')
    splash = QSplashScreen(pixmap)
    splash.show()
    app.processEvents()

    # --- VÉRIFICATION DU ROBOT ---
    splash.showMessage("Chargement de la configuration Robot...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    if not controller.setup_robot():
        splash.finish(None)
        QMessageBox.critical(None, "Erreur Critique Robot",
                             "Impossible de lire le fichier de configuration du robot (config.ini).\n"
                             "L'application ne peut pas démarrer.")
        return -1

    splash.showMessage("Connexion au contrôleur Robot...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    if not controller.connect_robot():
        splash.finish(None)
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle("Erreur de Connexion Robot")
        msg_box.setText(f"Impossible de communiquer avec le robot Galil.\n\n"
                        f"Causes possibles :\n"
                        f"- Le robot est éteint ou non connecté.\n"
                        f"- Le port COM sélectionné dans la configuration est incorrect.")

        config_button = msg_box.addButton("Ouvrir la Configuration", QMessageBox.AcceptRole)
        msg_box.addButton("Quitter", QMessageBox.RejectRole)

        msg_box.exec()

        if msg_box.clickedButton() == config_button:
            config_dialog = ConfigWindow(controller, None)
            config_dialog.exec()
            QMessageBox.information(None, "Redémarrage requis",
                                    "La configuration a été modifiée.\nVeuillez redémarrer l'application.")

        return -1

    # --- VÉRIFICATION DE PULSE ---
    splash.showMessage("Initialisation de l'interface PULSE Labshop...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    if not controller.setup_pulse():
        splash.finish(None)
        QMessageBox.critical(None, "Erreur d'Initialisation PULSE",
                             "Impossible d'initialiser PULSE LabShop ou de détecter le boîtier d'acquisition (LAN-XI).\n\n"
                             "Causes possibles :\n"
                             "- PULSE LabShop n'est pas installé.\n"
                             "- Le boîtier d'acquisition est éteint ou non connecté au réseau.\n"
                             "- Problème de configuration réseau.\n"
                             "- La clé d'activation de PULSE est manquante ou invalide.\n\n")
        return -1

    # --- DÉMARRAGE NORMAL ---
    splash.showMessage("Chargement de l'interface...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    fenetre = MainWindow()
    fenetre.controller = controller
    fenetre.setup_controller_and_signals()

    fenetre.show()
    splash.finish(fenetre)

    return app.exec()


if __name__ == '__main__':
    setup_logging()
    exit_code = run_application()
    sys.exit(exit_code)