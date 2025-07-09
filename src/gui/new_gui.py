#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import logging
import time
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


class ResourceManager:
    BASE_DIR = Path(__file__).resolve().parent
    ICONS_DIR = BASE_DIR / 'new_icons'

    @classmethod
    def get_icon_path(cls, icon_name: str) -> str:
        path = cls.ICONS_DIR / icon_name
        if not path.is_file():
            print(f"Avertissement : Icône non trouvée à {path}")
            return ""
        return str(path)

    @classmethod
    def get_pixmap(cls, pixmap_name: str) -> QPixmap:
        path = str(cls.ICONS_DIR / pixmap_name)
        pixmap = QPixmap(path)
        if pixmap.isNull():
            print(f"Avertissement : Image pour splash screen non trouvée à {path}")
        return pixmap


class TelecommandeWindow(QMainWindow):
    # --- Contenu de la classe TelecommandeWindow (inchangé) ---
    def __init__(self, controller: MainController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle('Télécommande du robot')
        self.setWindowIcon(QIcon(ResourceManager.get_icon_path('joystick.png')))
        self.setGeometry(200, 200, 650, 400)
        self._actions = {}
        self._create_ui()
        self.controller.robot_position_updated.connect(self.update_position_display)

    def _create_ui(self):
        self._create_actions_and_menus()
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        self.position_panel = self._create_position_display_panel()
        main_layout.addWidget(self.position_panel)
        self.control_panel = self._create_relative_control_panel()
        main_layout.addWidget(self.control_panel)

    def _create_actions_and_menus(self):
        self.set_zero_action = QAction(QIcon(ResourceManager.get_icon_path('set_zero.png')), "Définir Zéro", self)
        self.set_zero_action.triggered.connect(self.controller.set_robot_zero_position)
        self.set_parking_action = QAction(QIcon(ResourceManager.get_icon_path('parking.png')), "Définir Parking", self)
        self.set_parking_action.triggered.connect(self.controller.set_robot_parking_position)
        menu_bar = self.menuBar()
        menu_ref = menu_bar.addMenu("&Points de Références")
        menu_ref.addAction(self.set_zero_action)
        menu_ref.addAction(self.set_parking_action)

    def _create_frame_with_title(self, title_text: str) -> (QFrame, QVBoxLayout):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setFrameShadow(QFrame.Raised)
        layout = QVBoxLayout(frame)
        title_label = QLabel(title_text)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 5px;")
        layout.addWidget(title_label)
        return frame, layout

    def _create_position_display_panel(self) -> QWidget:
        frame, layout = self._create_frame_with_title("Position Actuelle")
        grid = QGridLayout()
        layout.addLayout(grid)
        headers = ["", "X (mm)", "Y (mm)", "Z (mm)", "Theta (°)", "Phi (°)"]
        for i, header_text in enumerate(headers): grid.addWidget(QLabel(f"<b>{header_text}</b>"), 0, i)
        grid.addWidget(QLabel("<b>Robot:</b>"), 1, 0)
        self.pos_robot_x = QLineEdit("N/C")
        self.pos_robot_x.setReadOnly(True)
        self.pos_robot_y = QLineEdit("N/C")
        self.pos_robot_y.setReadOnly(True)
        self.pos_robot_z = QLineEdit("N/C")
        self.pos_robot_z.setReadOnly(True)
        self.pos_robot_theta = QLineEdit("N/C")
        self.pos_robot_theta.setReadOnly(True)
        self.pos_robot_phi = QLineEdit("N/C")
        self.pos_robot_phi.setReadOnly(True)
        grid.addWidget(self.pos_robot_x, 1, 1)
        grid.addWidget(self.pos_robot_y, 1, 2)
        grid.addWidget(self.pos_robot_z, 1, 3)
        grid.addWidget(self.pos_robot_theta, 1, 4)
        grid.addWidget(self.pos_robot_phi, 1, 5)
        return frame

    def _create_relative_control_panel(self) -> QWidget:
        frame, layout = self._create_frame_with_title("Déplacements Relatifs (pas-à-pas)")
        grid = QGridLayout()
        layout.addLayout(grid)
        self.spin_boxes = {}
        axes = ["X", "Y", "Z", "THETA", "PHI"]
        for i, axis in enumerate(axes):
            label = QLabel(f"<b>{axis}:</b>")
            btn_minus = QPushButton(f"-")
            btn_minus.setFixedWidth(40)
            btn_minus.clicked.connect(
                lambda checked=False, ax=axis, sign=-1: self.controller.move_robot_relative(ax.lower(),
                                                                                            sign * self.spin_boxes[
                                                                                                ax].value()))
            spin_box = QSpinBox()
            spin_box.setRange(1, 1000)
            spin_box.setValue(10)
            spin_box.setSuffix(" U")
            self.spin_boxes[axis] = spin_box
            btn_plus = QPushButton(f"+")
            btn_plus.setFixedWidth(40)
            btn_plus.clicked.connect(
                lambda checked=False, ax=axis, sign=1: self.controller.move_robot_relative(ax.lower(),
                                                                                           sign * self.spin_boxes[
                                                                                               ax].value()))
            grid.addWidget(label, i, 0)
            grid.addWidget(btn_minus, i, 1)
            grid.addWidget(spin_box, i, 2)
            grid.addWidget(btn_plus, i, 3)
        grid.setColumnStretch(4, 1)
        return frame

    @Slot(dict)
    def update_position_display(self, positions: dict):
        self.pos_robot_x.setText(f"{positions.get('X', 0):.3f}")
        self.pos_robot_y.setText(f"{positions.get('Y', 0):.3f}")
        self.pos_robot_z.setText(f"{positions.get('Z', 0):.3f}")
        self.pos_robot_theta.setText(f"{positions.get('THETA', 0):.3f}")
        self.pos_robot_phi.setText(f"{positions.get('PHI', 0):.3f}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.controller = MainController()
        self.telecommande_window: Optional[TelecommandeWindow] = None
        self._actions: Dict[str, QAction] = {}
        self.current_highlighted_row = -1
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
        self.controller.sequence_status_changed.connect(self.update_status_bar)
        self.controller.highlight_point_in_gui.connect(self.highlight_table_row)

    def _setup_ui(self) -> None:
        self.setWindowTitle('Logiciel de Pilotage Robot')
        self.setGeometry(150, 150, 950, 600)
        self.setWindowIcon(QIcon(ResourceManager.get_icon_path('Window-icon.png')))
        self.setMinimumSize(700, 500)
        QApplication.instance().setStyle("Fusion")

        self._create_actions_and_connections()
        self._create_menus()
        self._create_toolbars()
        self._create_central_widget()
        self._create_statusbar()

    def _add_action(self, name, icon, text, tip, shortcut=None, slot=None):
        action = QAction(QIcon(ResourceManager.get_icon_path(icon)), text, self)
        action.setStatusTip(tip)
        if shortcut: action.setShortcut(shortcut)
        if slot: action.triggered.connect(slot)
        self._actions[name] = action
        return action

    def _create_actions_and_connections(self) -> None:
        self._add_action('quitter', 'exit.png', '&Quitter', "Quitter l'application", 'Ctrl+Q', self.close)
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
        self._add_action('start_sequence', 'play.png', 'Démarrer séquence', "Démarrer la séquence de mesure",
                         slot=self._on_start_sequence_triggered)
        self._add_action('stop_sequence', 'pause.png', 'Arrêter séquence', "Arrêter la séquence en cours",
                         slot=self.controller.stop_sequence)

        # CORRIGÉ : Ajout du 4ème argument 'tip'
        self._add_action('start_manual_measure', 'start_measurement.png', 'Démarrer mesure manuelle',
                         "Démarrer une mesure PULSE unique", slot=self.controller.start_manual_measurement)
        self._add_action('save_manual_measure', 'save_measurement.png', 'Sauvegarder mesure manuelle',
                         "Sauvegarder la dernière mesure manuelle", slot=self._on_save_manual_measure_triggered)
        self.update_save_action_state(False)

    def _create_menus(self) -> None:
        menu_bar = self.menuBar()
        menu_fichier = menu_bar.addMenu('&Fichier')
        menu_fichier.addAction(self._actions['ouvrir'])
        menu_fichier.addAction(self._actions['enregistrer'])
        menu_fichier.addAction(self._actions['enregistrer_sous'])
        menu_fichier.addSeparator()
        menu_fichier.addAction(self._actions['quitter'])
        menu_outils = menu_bar.addMenu('&Outils')
        menu_outils.addAction(self._actions['telecommande'])

    def _create_toolbars(self) -> None:
        toolbar_file = QToolBar("Fichier")
        self.addToolBar(toolbar_file)
        toolbar_file.addAction(self._actions['ouvrir'])
        toolbar_file.addAction(self._actions['enregistrer'])

        toolbar_sequence = QToolBar("Séquence")
        self.addToolBar(toolbar_sequence)
        toolbar_sequence.addAction(self._actions['start_sequence'])
        toolbar_sequence.addAction(self._actions['stop_sequence'])

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
        self.points_table.itemSelectionChanged.connect(self._update_point_actions_state)
        self.points_table.cellChanged.connect(lambda: self.controller.set_document_modified(True))
        self._update_point_actions_state()

    def _create_statusbar(self) -> None:
        self.statusBar().showMessage('Prêt')

    def _get_table_data(self) -> list[dict]:
        data = []
        headers = [self.points_table.horizontalHeaderItem(c).text().lower().replace(" ", "_") for c in
                   range(self.points_table.columnCount())]
        for row in range(self.points_table.rowCount()):
            row_data = {}
            for col, header in enumerate(headers):
                item = self.points_table.item(row, col)
                row_data[header] = item.text() if item else ""
            data.append(row_data)
        return data

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
        if not self.controller.save_point_list():
            return self._on_save_as_triggered()
        return True

    @Slot()
    def _on_save_as_triggered(self) -> bool:
        self.controller.sync_points_from_gui(self._get_table_data())
        file_path, _ = QFileDialog.getSaveFileName(self, "Enregistrer la liste de points", "",
                                                   "Fichier CSV (*.csv);;Tous les fichiers (*)")
        if file_path:
            return self.controller.save_point_list_to_file(file_path)
        return False

    @Slot()
    def _on_add_point_triggered(self):
        self.controller.sync_points_from_gui(self._get_table_data())
        self.controller.add_new_point()

    @Slot()
    def _on_delete_points_triggered(self):
        selected_rows = {item.row() for item in self.points_table.selectedItems()}
        if not selected_rows: return
        reply = QMessageBox.question(self, "Confirmation",
                                     f"Voulez-vous vraiment supprimer {len(selected_rows)} point(s) ?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.controller.sync_points_from_gui(self._get_table_data())
            self.controller.delete_selected_points(list(selected_rows))

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
    def _on_start_sequence_triggered(self):
        self.controller.sync_points_from_gui(self._get_table_data())
        self.controller.start_sequence()

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
            return
        self.points_table.setRowCount(len(points))
        for row_index, point_data in enumerate(points):
            for col_index, header in enumerate(headers):
                value = point_data.get(header, "")
                if isinstance(value, float):
                    item = QTableWidgetItem(f"{value:.3f}")
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if header == "measurement_file":
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.points_table.setItem(row_index, col_index, item)
        self.points_table.blockSignals(False)
        self.points_table.resizeColumnsToContents()

    @Slot(bool)
    def update_save_action_state(self, is_modified: bool):
        self._actions['enregistrer'].setEnabled(is_modified)
        title = self.windowTitle().replace(" *", "")
        if is_modified:
            self.setWindowTitle(title + " *")
        else:
            self.setWindowTitle(title)

    def _update_point_actions_state(self):
        selected_items = self.points_table.selectedItems()
        selected_rows = {item.row() for item in selected_items}
        has_selection = len(selected_rows) > 0
        single_selection = len(selected_rows) == 1
        self._actions['delete_point'].setEnabled(has_selection)
        self._actions['move_point_up'].setEnabled(single_selection and list(selected_rows)[0] > 0)
        self._actions['move_point_down'].setEnabled(
            single_selection and list(selected_rows)[0] < self.points_table.rowCount() - 1)

    @Slot()
    def _open_telecommande(self):
        if self.telecommande_window is None or not self.telecommande_window.isVisible():
            self.telecommande_window = TelecommandeWindow(self.controller, self)
            self.telecommande_window.show()
            self.update_status_bar("Télécommande ouverte")
        else:
            self.telecommande_window.activateWindow()
            self.telecommande_window.raise_()

    @Slot(str)
    def update_status_bar(self, message: str):
        print(f"[GUI Log] {message}")
        self.statusBar().showMessage(message, 5000)

    @Slot(int)
    def highlight_table_row(self, row_index: int):
        if self.current_highlighted_row != -1 and self.current_highlighted_row < self.points_table.rowCount():
            for col in range(self.points_table.columnCount()):
                item = self.points_table.item(self.current_highlighted_row, col)
                if item: item.setBackground(QColor("white"))
        if row_index != -1 and row_index < self.points_table.rowCount():
            for col in range(self.points_table.columnCount()):
                item = self.points_table.item(row_index, col)
                if item: item.setBackground(QColor("#a8d8ea"))
        self.current_highlighted_row = row_index

    def closeEvent(self, event: QCloseEvent) -> None:
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


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - (%(threadName)s) %(message)s')
    app = QApplication(sys.argv)

    pixmap = ResourceManager.get_pixmap('splash.png')
    splash = QSplashScreen(pixmap)
    splash.show()
    app.processEvents()

    fenetre = MainWindow()

    splash.showMessage("Initialisation du matériel...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    fenetre.setup_controller_and_signals(splash)

    fenetre.show()
    splash.finish(fenetre)

    return app.exec()


if __name__ == '__main__':
    sys.exit(main())