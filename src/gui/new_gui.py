import sys
import logging
import logging.handlers
from logging import FileHandler
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

from main_controller import MainController
from gui.config_window import ConfigWindow
from gui.telecommande_window import TelecommandeWindow
from gui.resource_manager import ResourceManager
from gui.commands import AddPointCommand, DeletePointsCommand, MovePointCommand, ChangeCellCommand
from gui.log_viewer_window import LogViewerWindow

def _get_active_log_file(logger_candidates: list[str]) -> Path | None:
    """Trouve le chemin du fichier de log actif pour une catégorie donnée.

    Cette fonction utilitaire parcourt les loggers Python pour trouver le premier
    `FileHandler` attaché à l'un des noms de logger fournis. Elle est utilisée
    par les visionneuses de logs pour savoir quel fichier surveiller.

    :param logger_candidates: Une liste de noms de loggers à inspecter
                              (ex: ["RobotApp.RobotController", "RobotApp.GalilDriver"]).
    :return: Un objet `Path` vers le fichier de log, ou `None` si aucun n'est trouvé.
    """
    for name in logger_candidates:
        lg = logging.getLogger(name)
        for h in lg.handlers:
            if isinstance(h, FileHandler):
                try:
                    return Path(h.baseFilename)
                except Exception:
                    pass
    return None

# --- CONFIGURATION CENTRALISÉE DES LOGS ---
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
SESSION_TS = time.strftime("%Y%m%d_%H%M%S")
ROBOT_LOG_FILE = LOG_DIR / f"robot_app_{SESSION_TS}.log"
PULSE_LOG_FILE = LOG_DIR / f"pulse_driver_{SESSION_TS}.log"

def setup_logging():
    """Configure le système de logging pour l'ensemble de l'application.

    Cette fonction doit être appelée une seule fois au démarrage de l'application.
    Elle met en place une configuration de logging à plusieurs niveaux :

    - **Root Logger** : Affiche les messages de niveau INFO et supérieur sur la console.
    - **Logger Robot** : Redirige tous les messages (DEBUG et supérieur) provenant des
      modules du robot (`RobotApp.GalilDriver`, `RobotApp.RobotController`, etc.)
      vers un fichier de log dédié (ex: `logs/robot_YYYYMMDD_HHMMSS.log`).
    - **Logger PULSE** : Redirige tous les messages (DEBUG et supérieur) provenant du
      driver PULSE (`RobotApp.PulseLabshopDriver`) vers un autre fichier de log dédié.

    Cette séparation des logs par fichier facilite grandement le diagnostic en
    cas de problème avec un sous-système spécifique. Les fichiers de log sont
    horodatés pour ne pas écraser les sessions précédentes.
    """
    import sys
    import logging
    from pathlib import Path
    from datetime import datetime

    # -------- Où écrire les logs ? --------
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # exécutable PyInstaller → écrire à côté de l'exe
        base_dir = Path(sys.executable).resolve().parent
    else:
        # exécution depuis les sources → racine du projet
        # (adapté à ton layout : launcher.py à la racine, code sous src/)
        base_dir = Path(__file__).resolve().parents[2]  # .../robot-acoustic-gui
        # si __file__ est sous src/gui/new_gui.py, parents[2] remonte à la racine

    logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    robot_log = logs_dir / f"robot_{ts}.log"
    pulse_log = logs_dir / f"pulse_{ts}.log"

    # -------- Formatters & Handlers --------
    fmt = logging.Formatter(
        fmt="%(asctime)s - %(name)-28s - %(levelname)-8s - (%(threadName)s) %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    robot_fh = logging.FileHandler(robot_log, mode="w", encoding="utf-8", errors="replace")
    robot_fh.setLevel(logging.DEBUG)
    robot_fh.setFormatter(fmt)

    pulse_fh = logging.FileHandler(pulse_log, mode="w", encoding="utf-8", errors="replace")
    pulse_fh.setLevel(logging.DEBUG)
    pulse_fh.setFormatter(fmt)

    # -------- Root logger: console uniquement --------
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Nettoyage des handlers existants si relance interactive
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(console)

    # -------- Route les logs “robot” vers robot_fh --------
    # On capte au minimum Galil + RobotController ; ajoute d'autres si besoin.
    for name in ("RobotApp.GalilDriver", "RobotApp.RobotController"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        # éviter doublons si setup_logging() est rappelé
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.addHandler(robot_fh)
        # on laisse propagate=True (ainsi on voit aussi passer en console via root)
        lg.propagate = True

    # -------- Route les logs “pulse” vers pulse_fh --------
    # Assure-toi que le driver PULSE loggue bien sous ce nom.
    for name in ("RobotApp.PulseLabshopDriver",):
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.addHandler(pulse_fh)
        lg.propagate = True

    # -------- Petit message de démarrage --------
    logging.getLogger("root").info("Système de logging initialisé.")
    logging.getLogger("root").info(f"Logs robot : {robot_log}")
    logging.getLogger("root").info(f"Logs pulse : {pulse_log}")
# --- FIN DE LA SECTION LOGS ---


class IntegerDelegate(QStyledItemDelegate):
    """Un délégué pour éditer des entiers dans une cellule de QTableWidget.

    Force la saisie de valeurs numériques entières dans les colonnes où il est appliqué.
    """
    def createEditor(self, parent, option, index):
        """Crée un QLineEdit avec un validateur d'entiers."""
        editor = QLineEdit(parent)
        validator = QIntValidator(parent)
        editor.setValidator(validator)
        return editor

    def setEditorData(self, editor, index):
        """Remplit l'éditeur avec la valeur actuelle de la cellule."""
        value = index.model().data(index, 0)
        editor.setText(str(value))

    def setModelData(self, editor, model, index):
        """Met à jour le modèle avec la nouvelle valeur de l'éditeur."""
        model.setData(index, editor.text())


class MainWindow(QMainWindow):
    """Fenêtre principale de l'application.

    Cette classe construit l'interface utilisateur principale, y compris les menus,
    les barres d'outils, le tableau de points et la barre d'état. Elle est
    responsable de l'affichage des données et de la transmission des actions
    de l'utilisateur au :class:`~src.main_controller.MainController` via des signaux.

    Elle utilise un `QUndoStack` pour gérer l'historique des actions d'édition
    (Annuler/Rétablir).
    """
    def __init__(self, controller: MainController) -> None:
        """Initialise la fenêtre principale.

        :param controller: L'instance du contrôleur principal de l'application.
        """
        super().__init__()
        self.controller = controller
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
        """Connecte les signaux du MainController aux slots de la MainWindow.

        Cette méthode établit le dialogue entre la logique métier et l'interface.
        """
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
        """Construit tous les composants de l'interface utilisateur."""
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
        """Crée et configure une QAction, puis l'ajoute au dictionnaire des actions. (Interne)"""
        action = QAction(QIcon(ResourceManager.get_icon_path(icon)), text, self)
        action.setStatusTip(tip)
        if shortcut: action.setShortcut(shortcut)
        if slot: action.triggered.connect(slot)
        self._actions[name] = action
        return action

    def _create_actions_and_connections(self) -> None:
        """Crée toutes les QAction de l'application et connecte leurs signaux. (Interne)"""
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
        """Crée la barre de menu et ses menus (Fichier, Édition, Outils). (Interne)"""
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
        """Crée et remplit toutes les barres d'outils. (Interne)"""
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
        """Crée le widget central, qui contient principalement le tableau de points. (Interne)"""
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
        """Crée la barre d'état avec la zone de message et l'affichage des coordonnées. (Interne)"""
        status_bar = self.statusBar()
        self.status_message_label = QLabel("Prêt")
        status_bar.addWidget(self.status_message_label, 1)

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
        """Extrait toutes les données du tableau de points.

        :return: Une liste de dictionnaires, où chaque dictionnaire représente une ligne du tableau.
        """
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
        """Logique commune pour le démarrage d'une séquence. (Interne)

        Gère la validation (noms de fichiers manquants) et la récupération
        de l'index de départ avant d'appeler la méthode de démarrage effective
        du contrôleur.

        :param start_method: La méthode du contrôleur à appeler pour démarrer
                             (ex: `controller.start_full_sequence`).
        """
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
        """Slot déclenché par l'action "Démarrer Séquence"."""
        self._start_sequence_common(self.controller.start_full_sequence)

    @Slot()
    def _on_next_point_triggered(self):
        """Slot déclenché par l'action "Mesurer Point Suivant"."""
        self._start_sequence_common(self.controller.start_single_point_sequence)

    @Slot()
    def _on_goto_selected_point_triggered(self):
        """Slot pour déplacer le robot vers le point sélectionné dans le tableau."""
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
        """Slot pour déplacer le robot à la position capsule zéro."""
        zero_coords = {'X': 0.0, 'Y': 0.0, 'Z': 0.0, 'THETA': 0.0, 'PHI': 0.0}
        self.update_status_bar("Déplacement vers le Zéro Capsule...")
        self.controller.move_capsule_absolute(zero_coords)

    @Slot(str)
    def _handle_sequence_state(self, status: str):
        """Met à jour l'interface en fonction de l'état de la séquence.

        Affiche le message de statut et met à jour l'état (activé/désactivé) des actions.

        :param status: Le message de statut reçu du séquenceur.
        """
        self.update_status_bar(status)
        if "Démarrage" in status:
            self._is_sequence_running = True
        elif "Séquence terminée" in status or "ERREUR" in status or "arrêtée" in status:
            self._is_sequence_running = False
        self._update_actions_state()

    @Slot(str, int)
    def on_single_point_sequence_finished(self, final_message: str, next_point_index: int):
        """Gère la fin d'une séquence "point unique".

        Sélectionne automatiquement le point suivant dans le tableau pour faciliter
        l'enchaînement manuel des mesures.

        :param final_message: Le message de statut final.
        :param next_point_index: L'index du point suivant à sélectionner.
        """
        if next_point_index < self.points_table.rowCount():
            self.points_table.selectRow(next_point_index)

    def _update_actions_state(self):
        """Met à jour l'état (activé/désactivé) de toutes les actions et widgets.

        Cette méthode est appelée à chaque changement d'état important (début/fin
        de séquence, changement de sélection dans le tableau) pour s'assurer
        que l'utilisateur ne puisse cliquer que sur les boutons pertinents.
        """
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

        self._actions['start_manual_measure'].setEnabled(not running)
        self._actions['save_manual_measure'].setEnabled(not running)
        self.manual_filename_edit.setEnabled(not running)

    @Slot(int)
    def highlight_table_row(self, row_index: int):
        """Surligne une ligne spécifique du tableau.

        Utilisé par le séquenceur pour indiquer visuellement le point en cours de traitement.

        :param row_index: L'index de la ligne à surligner.
        """
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
        """Gère l'événement de fermeture de la fenêtre.

        Demande confirmation à l'utilisateur s'il y a des modifications non
        sauvegardées et s'assure que les connexions matérielles sont
        proprement fermées.
        """
        if self._is_sequence_running:
            QMessageBox.warning(self, "Séquence en cours", "Veuillez d'abord arrêter la séquence avant de quitter.")
            event.ignore()
            return

        self.controller.sync_points_from_gui(self._get_table_data())

        should_close = True
        if not self.undo_stack.isClean():
            reply = QMessageBox.question(self, "Quitter",
                                         "Des modifications n'ont pas été sauvegardées.\nVoulez-vous les enregistrer avant de quitter ?",
                                         QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)

            if reply == QMessageBox.StandardButton.Save:
                if not self._on_save_triggered():
                    should_close = False
            elif reply == QMessageBox.StandardButton.Cancel:
                should_close = False

        if not should_close:
            event.ignore()
            return
        try:
            self.undo_stack.cleanChanged.disconnect()
        except RuntimeError:
            pass
        self.hide()
        if self.telecommande_window:
            self.telecommande_window.close()
        if self.robot_log_window:
            self.robot_log_window.close()
        if self.pulse_log_window:
            self.pulse_log_window.close()
        self.controller.disconnect_robot()
        event.accept()


        event.accept()
        self.hide()
        if self.telecommande_window:
            self.telecommande_window.close()
        if self.robot_log_window:
            self.robot_log_window.close()
        if self.pulse_log_window:
            self.pulse_log_window.close()
        self.controller.disconnect_robot()

    @Slot()
    def _open_point_file_dialog(self):
        """Ouvre une boîte de dialogue pour sélectionner un fichier de points à charger."""
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
        """Gère l'action "Nouveau" pour créer une liste de points vierge."""
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
        """Gère l'action "Enregistrer"."""
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
        """Gère l'action "Enregistrer sous..."."""
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
        """Crée et pousse une commande d'ajout de point sur la pile Undo."""
        point_to_add = self.controller.add_current_position_as_point()
        command = AddPointCommand(self.controller, self, point_to_add if point_to_add else None)
        self.undo_stack.push(command)

    @Slot()
    def _on_delete_points_triggered(self):
        """Crée et pousse une commande de suppression de points sur la pile Undo."""
        selected_rows = sorted(list({item.row() for item in self.points_table.selectedItems()}))
        if not selected_rows: return
        command = DeletePointsCommand(self.controller, self, selected_rows)
        self.undo_stack.push(command)

    @Slot()
    def _on_move_up_triggered(self):
        """Crée et pousse une commande de déplacement de point vers le haut sur la pile Undo."""
        selected_rows = {item.row() for item in self.points_table.selectedItems()}
        if len(selected_rows) == 1:
            index = list(selected_rows)[0]
            if index > 0:
                command = MovePointCommand(self.controller, self, index, "haut")
                self.undo_stack.push(command)

    @Slot()
    def _on_move_down_triggered(self):
        """Crée et pousse une commande de déplacement de point vers le bas sur la pile Undo."""
        selected_rows = {item.row() for item in self.points_table.selectedItems()}
        if len(selected_rows) == 1:
            index = list(selected_rows)[0]
            if index < self.points_table.rowCount() - 1:
                command = MovePointCommand(self.controller, self, index, "bas")
                self.undo_stack.push(command)

    @Slot(QTableWidgetItem)
    def _on_cell_changed(self, item):
        """Crée et pousse une commande de modification de cellule sur la pile Undo."""
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
        """Gère le clic sur le bouton de sauvegarde de mesure manuelle."""
        filename = self.manual_filename_edit.text()
        if not filename:
            QMessageBox.warning(self, "Nom de fichier manquant",
                                "Veuillez entrer un nom de fichier pour la sauvegarde.")
            return
        self.controller.save_manual_measurement(filename)

    @Slot(list)
    def update_points_table(self, points: list):
        """Met à jour le contenu du tableau de points.

        Vide et repeuple le `QTableWidget` avec les données fournies.

        :param points: Une liste de dictionnaires représentant les points à afficher.
        """
        self.points_table.itemChanged.disconnect(self._on_cell_changed)
        self.points_table.setRowCount(0)
        headers = self.controller.get_point_headers()
        if not headers:
            self.points_table.itemChanged.connect(self._on_cell_changed)
            return
        self.points_table.setColumnCount(len(headers))
        display_headers = []
        for h in headers:
            if h == "measurement_file":
                display_headers.append("FICHIER DE MESURE")
            elif h == "num_measurements":
                display_headers.append("NB MESURES")
            else:
                display_headers.append(h.upper().replace("_", " "))

        self.points_table.setHorizontalHeaderLabels(display_headers)

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
        """Met à jour le titre de la fenêtre pour indiquer l'état de modification."""
        title = self.windowTitle().replace(" *", "")
        if is_modified:
            title += " *"
        self.setWindowTitle(title)
        self._update_actions_state()

    @Slot()
    def _open_telecommande(self):
        """Ouvre la fenêtre de la télécommande."""
        if self.telecommande_window is None or not self.telecommande_window.isVisible():
            self.telecommande_window = TelecommandeWindow(self.controller, self)
            self.telecommande_window.show()
            self.update_status_bar("Télécommande ouverte")
        else:
            self.telecommande_window.activateWindow()
            self.telecommande_window.raise_()

    @Slot()
    def _open_config_window(self):
        """Ouvre la fenêtre de configuration."""
        config_dialog = ConfigWindow(self.controller, self)
        config_dialog.exec()
        self.update_status_bar("Fenêtre de configuration fermée.")

    @Slot(str)
    def update_status_bar(self, message: str):
        """Affiche un message dans la barre d'état.

        :param message: Le message à afficher.
        """
        self.status_message_label.setText(message)

    @Slot(dict, dict)
    def update_coordinate_display(self, robot_pos: dict, capsule_pos: dict):
        """Met à jour l'affichage des coordonnées en temps réel dans la barre d'état.

        :param robot_pos: Dictionnaire des coordonnées "robot".
        :param capsule_pos: Dictionnaire des coordonnées "capsule".
        """
        self.status_bar_labels['X'].setText(f"X: {round(capsule_pos.get('X', 0.0))}")
        self.status_bar_labels['Y'].setText(f"Y: {round(capsule_pos.get('Y', 0.0))}")
        self.status_bar_labels['Z'].setText(f"Z: {round(capsule_pos.get('Z', 0.0))}")
        # On utilise robot_pos pour les angles, car ils sont identiques
        self.status_bar_labels['Theta'].setText(f"θ: {round(robot_pos.get('THETA', 0.0))}")
        self.status_bar_labels['Phi'].setText(f"φ: {round(robot_pos.get('PHI', 0.0))}")

    @Slot()
    def _open_robot_log_viewer(self):
        """Ouvre la fenêtre de la visionneuse de logs pour le robot."""
        # on regarde d'abord RobotController (souvent le plus bavard), puis GalilDriver
        path = _get_active_log_file(["RobotApp.RobotController", "RobotApp.GalilDriver"])
        if not path:
            QMessageBox.information(self, "Logs Robot", "Aucun fichier de log Robot n’a été trouvé pour cette session.")
            return
        title = f"Logs Robot & Contrôleur — {path.name}"
        if self.robot_log_window is None or not self.robot_log_window.isVisible():
            self.robot_log_window = LogViewerWindow(str(path), title, "log_robot.png", self)
            self.robot_log_window.show()
        else:
            self.robot_log_window.activateWindow()
            self.robot_log_window.raise_()

    @Slot()
    def _open_pulse_log_viewer(self):
        """Ouvre la fenêtre de la visionneuse de logs pour PULSE."""
        path = _get_active_log_file(["RobotApp.PulseLabshopDriver"])
        if not path:
            QMessageBox.information(self, "Logs PULSE", "Aucun fichier de log PULSE n’a été trouvé pour cette session.")
            return
        title = f"Logs Interface PULSE — {path.name}"
        if self.pulse_log_window is None or not self.pulse_log_window.isVisible():
            self.pulse_log_window = LogViewerWindow(str(path), title, "log_pulse.png", self)
            self.pulse_log_window.show()
        else:
            self.pulse_log_window.activateWindow()
            self.pulse_log_window.raise_()



def run_application():
    """Point d'entrée principal de l'application graphique.

    Gère le cycle de vie de l'application :
    1. Affiche un écran de démarrage (splash screen).
    2. Initialise le MainController.
    3. Tente de se connecter au matériel (robot et PULSE).
    4. Gère les erreurs de connexion et les dialogues de configuration initiaux.
    5. Crée et affiche la fenêtre principale.
    6. Lance la boucle d'événements de l'application.
    """
    import sys
    from pathlib import Path
    from PySide6.QtWidgets import QApplication, QSplashScreen, QMessageBox, QFileDialog
    from PySide6.QtCore import Qt

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
        msg_box.setText(
            "Impossible de communiquer avec le robot Galil.\n\n"
            "Causes possibles :\n"
            "- Le robot est éteint ou non connecté.\n"
            "- Le port COM sélectionné dans la configuration est incorrect."
        )
        config_button = msg_box.addButton("Ouvrir la Configuration", QMessageBox.AcceptRole)
        msg_box.addButton("Quitter", QMessageBox.RejectRole)
        msg_box.exec()

        if msg_box.clickedButton() == config_button:
            config_dialog = ConfigWindow(controller, None)
            config_dialog.exec()
            QMessageBox.information(None, "Redémarrage requis",
                                    "La configuration a été modifiée.\nVeuillez redémarrer l'application.")
        return -1

    # --- NOUVELLE ÉTAPE : CHOIX DU PROJET PULSE ---
    splash.showMessage("Configuration de PULSE Labshop...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    app.processEvents()

    # 1. Charger la config de PULSE pour pouvoir l'afficher et la modifier
    if not controller.load_pulse_config():
        splash.finish(None)
        QMessageBox.critical(None, "Erreur Critique PULSE",
                             "Impossible de trouver le fichier de configuration de PULSE (config.ini).\n"
                             "L'application ne peut pas démarrer.")
        return -1

    # 2. Afficher la boîte de dialogue de choix
    default_project = controller.pulse_config.get('PulseSettings', 'project_path', fallback="Non défini")

    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Question)
    msg_box.setWindowTitle("Sélection du Projet PULSE")
    msg_box.setText("Quel projet PULSE LabShop voulez-vous utiliser ?")
    msg_box.setInformativeText(f"Projet par défaut : {default_project}")

    default_btn = msg_box.addButton("Utiliser le projet par défaut", QMessageBox.AcceptRole)
    choose_btn = msg_box.addButton("Choisir un autre projet...", QMessageBox.ActionRole)
    quit_btn = msg_box.addButton("Quitter", QMessageBox.RejectRole)

    msg_box.exec()
    clicked_button = msg_box.clickedButton()

    # 3. Gérer le choix de l'utilisateur
    if clicked_button == quit_btn or clicked_button is None:
        return -1  # L'utilisateur a cliqué sur "Quitter" ou a fermé la fenêtre

    if clicked_button == choose_btn:
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Sélectionner un projet PULSE",
            str(Path.home()),
            "Projets PULSE (*.pls)"
        )
        if file_path:
            # Mettre à jour la configuration en mémoire dans le contrôleur
            controller.pulse_config.set('PulseSettings', 'project_path', file_path)
            controller.log_message_sent.emit(f"Projet PULSE sélectionné manuellement : {file_path}")
        else:
            # L'utilisateur a annulé la sélection de fichier
            QMessageBox.information(None, "Annulation", "Aucun projet sélectionné. L'application va se fermer.")
            return -1

    # --- VÉRIFICATION / INITIALISATION DE PULSE ---
    splash.showMessage("Initialisation de l'interface PULSE Labshop...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)

    # 4. Lancer l'initialisation de PULSE avec le bon projet
    ok, err, tried_proj = controller.setup_pulse()

    if not ok:
        splash.finish(None)
        QMessageBox.critical(
            None, "Erreur d'Initialisation PULSE",
            f"{err or 'Impossible d’initialiser PULSE LabShop.'}\n\n"
            "Causes possibles :\n"
            "- PULSE LabShop n'est pas installé ou la licence est absente.\n"
            "- Le boîtier d'acquisition est éteint ou non connecté au réseau.\n"
            "- Le projet .pls sélectionné est invalide ou corrompu."
        )
        return -1

    splash.showMessage("Sélection du groupe de fonctions...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)

    function_groups = controller.pulse.get_available_function_groups()
    chosen_fg = None

    if not function_groups:
        splash.finish(None)
        QMessageBox.critical(
            None,
            "Projet PULSE incomplet",
            "Le projet PULSE sélectionné ne contient aucun 'Function Group'.\n\n"
            "La sauvegarde des mesures sera impossible.\n"
            "Veuillez en ajouter un dans PULSE LabShop, enregistrer le projet, puis relancez l'application."
        )
        controller.disconnect_robot()  # Nettoyage
        return -1
    elif len(function_groups) == 1:
        chosen_fg = function_groups[0]
        controller.log_message_sent.emit(f"Groupe de fonctions '{chosen_fg}' sélectionné automatiquement.")
    else:
        # On demande à l'utilisateur de choisir
        from PySide6.QtWidgets import QInputDialog
        chosen_fg, ok = QInputDialog.getItem(
            None,
            "Sélection du Function Group",
            "Plusieurs 'Function Groups' ont été trouvés.\n"
            "Veuillez choisir celui dans lequel sauvegarder les mesures :",
            function_groups,
            0,
            False
        )
        if not ok or not chosen_fg:
            # L'utilisateur a annulé
            splash.finish(None)
            QMessageBox.information(None, "Annulation",
                                    "Aucun groupe de fonctions sélectionné. L'application va se fermer.")
            controller.disconnect_robot()  # Nettoyage
            return -1

    # On configure le driver avec le groupe choisi
    if not controller.pulse.set_function_group_by_name(chosen_fg):
        splash.finish(None)
        QMessageBox.critical(None, "Erreur interne", "Impossible de configurer le groupe de fonctions sélectionné.")
        controller.disconnect_robot()  # Nettoyage
        return -1

    # --- DÉMARRAGE NORMAL ---
    splash.showMessage("Chargement de l'interface...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    fenetre = MainWindow(controller=controller)
    fenetre.setup_controller_and_signals()
    try:
        controller.gui = fenetre
    except Exception:
        pass

    fenetre.show()
    splash.finish(fenetre)

    return app.exec()