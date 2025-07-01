#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QToolBar,
    QStatusBar, QMessageBox, QLineEdit, QMenu, QGridLayout, QFrame, QSplitter, QListWidget, QSizePolicy, QFormLayout,
    QSpinBox, QHBoxLayout, QTableWidget, QHeaderView, QTableWidgetItem, QPushButton
)
from PySide6.QtGui import QIcon, QFont, QAction, QCloseEvent
from PySide6.QtCore import Qt, QSize, Slot, Signal


class ResourceManager:
    """Gestionnaire de ressources pour l'application."""

    BASE_DIR = Path(__file__).resolve().parent
    ICONS_DIR = BASE_DIR / 'new_icons'

    @classmethod
    def get_icon_path(cls, icon_name: str) -> str:
        """Retourne le chemin vers une icône."""
        path = cls.ICONS_DIR / icon_name
        if not path.is_file():
            print(f"Avertissement : Icône non trouvée à {path}")
            return ""
        return str(path)

    @classmethod
    def check_resources(cls) -> bool:
        """Vérifie si les ressources nécessaires sont disponibles."""
        return cls.ICONS_DIR.is_dir()


class TelecommandeWindow(QMainWindow):
    """Fenêtre de télécommande pour contrôler le robot manuellement."""

    def __init__(self, parent=None):
        """Initialise la fenêtre de télécommande."""
        super().__init__(parent)
        self.setWindowTitle('Télécommande du robot')
        self.setWindowIcon(QIcon(ResourceManager.get_icon_path('joystick.png')))
        self.setGeometry(200, 200, 650, 400)  # Taille ajustée
        self.setMinimumSize(600, 550)

        self._actions = {}
        self._create_actions()
        self._create_toolbars()
        self._create_menus()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QGridLayout(central_widget)
        main_layout.setSpacing(10)

        # Création des différents panneaux
        position_panel = self._create_position_display_panel()
        absolute_panel = self._create_absolute_control_panel()
        relative_panel = self._create_relative_control_panel()
        store_panel = self._create_store_point_panel()

        # Ajout des panneaux à la grille principale
        main_layout.addWidget(position_panel, 0, 0, 1, 2)  # S'étend sur 2 colonnes
        main_layout.addWidget(absolute_panel, 1, 0)
        main_layout.addWidget(relative_panel, 1, 1)
        main_layout.addWidget(store_panel, 2, 0, 1, 2)  # S'étend sur 2 colonnes

        # Rendre les colonnes redimensionnables de manière équilibrée
        main_layout.setColumnStretch(0, 1)
        main_layout.setColumnStretch(1, 1)

    def _create_frame_with_title(self, title_text: str) -> (QFrame, QVBoxLayout):
        """Crée un cadre avec un titre pour regrouper les widgets."""
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setFrameShadow(QFrame.Raised)

        layout = QVBoxLayout(frame)
        title_label = QLabel(title_text)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 5px;")
        layout.addWidget(title_label)

        return frame, layout

    def _create_position_display_panel(self) -> QWidget:
        """Crée le panneau d'affichage des positions actuelles."""
        frame, layout = self._create_frame_with_title("Position Actuelle")

        grid = QGridLayout()
        layout.addLayout(grid)

        # Entêtes de colonnes
        headers = ["", "X (mm)", "Y (mm)", "Z (mm)", "Theta (°)", "Phi (°)"]
        for i, header_text in enumerate(headers):
            grid.addWidget(QLabel(f"<b>{header_text}</b>"), 0, i)

        # Ligne Position Robot
        grid.addWidget(QLabel("<b>Robot:</b>"), 1, 0)
        self.pos_robot_x = QLineEdit("0.00")
        self.pos_robot_x.setReadOnly(True)
        self.pos_robot_x.setMaximumWidth(80)
        self.pos_robot_y = QLineEdit("0.00")
        self.pos_robot_y.setReadOnly(True)
        self.pos_robot_y.setMaximumWidth(80)
        self.pos_robot_z = QLineEdit("0.00")
        self.pos_robot_z.setReadOnly(True)
        self.pos_robot_z.setMaximumWidth(80)
        self.pos_robot_theta = QLineEdit("0.00")
        self.pos_robot_theta.setReadOnly(True)
        self.pos_robot_theta.setMaximumWidth(80)
        self.pos_robot_phi = QLineEdit("0.00")
        self.pos_robot_phi.setReadOnly(True)
        self.pos_robot_phi.setMaximumWidth(80)

        grid.addWidget(self.pos_robot_x, 1, 1)
        grid.addWidget(self.pos_robot_y, 1, 2)
        grid.addWidget(self.pos_robot_z, 1, 3)
        grid.addWidget(self.pos_robot_theta, 1, 4)
        grid.addWidget(self.pos_robot_phi, 1, 5)

        # Ligne Position Capsule (corrigée)
        grid.addWidget(QLabel("<b>Capsule:</b>"), 2, 0)
        self.pos_capsule_x = QLineEdit("0.00")
        self.pos_capsule_x.setReadOnly(True)
        self.pos_capsule_x.setMaximumWidth(80)
        self.pos_capsule_y = QLineEdit("0.00")
        self.pos_capsule_y.setReadOnly(True)
        self.pos_capsule_y.setMaximumWidth(80)
        self.pos_capsule_z = QLineEdit("0.00")
        self.pos_capsule_z.setReadOnly(True)
        self.pos_capsule_z.setMaximumWidth(80)

        grid.addWidget(self.pos_capsule_x, 2, 1)
        grid.addWidget(self.pos_capsule_y, 2, 2)
        grid.addWidget(self.pos_capsule_z, 2, 3)

        # Ajouter une colonne "stretch" pour pousser tout vers la gauche
        grid.setColumnStretch(6, 1)

        return frame

    def _create_absolute_control_panel(self) -> QWidget:
        """Crée le panneau pour les déplacements absolus."""
        frame, main_frame_layout = self._create_frame_with_title("Déplacements Absolus")

        # Layout principal du panneau : horizontal
        h_layout = QHBoxLayout()
        main_frame_layout.addLayout(h_layout)

        # Partie gauche : les champs de saisie
        form_layout = QFormLayout()
        self.target_x = QLineEdit("0")
        form_layout.addRow("X:", self.target_x)
        self.target_y = QLineEdit("0")
        form_layout.addRow("Y:", self.target_y)
        self.target_z = QLineEdit("0")
        form_layout.addRow("Z:", self.target_z)
        self.target_theta = QLineEdit("0")
        form_layout.addRow("Theta:", self.target_theta)
        self.target_phi = QLineEdit("0")
        form_layout.addRow("Phi:", self.target_phi)

        # Partie droite : les boutons d'action
        buttons_layout = QVBoxLayout()
        btn_copy_pos = QPushButton(QIcon(ResourceManager.get_icon_path("arrow_down.png")), " Copier Pos. Actuelle")
        btn_go = QPushButton(QIcon(ResourceManager.get_icon_path("goto_point.png")), " Aller à la position")
        btn_go.setStyleSheet("font-weight: bold;")

        buttons_layout.addWidget(btn_copy_pos)
        buttons_layout.addWidget(btn_go)
        buttons_layout.addStretch()  # Pousse les boutons vers le haut

        h_layout.addLayout(form_layout)
        h_layout.addLayout(buttons_layout)

        return frame

    def _create_relative_control_panel(self) -> QWidget:
        """Crée le panneau pour les déplacements relatifs."""
        frame, layout = self._create_frame_with_title("Déplacements Relatifs (pas-à-pas)")

        grid = QGridLayout()
        layout.addLayout(grid)

        axes = ["X", "Y", "Z", "Theta", "Phi"]
        for i, axis in enumerate(axes):
            label = QLabel(f"<b>{axis}:</b>")
            btn_minus = QPushButton(f"-")
            btn_minus.setFixedWidth(30)
            spin_box = QSpinBox()
            spin_box.setRange(1, 1000)
            spin_box.setValue(10)
            spin_box.setMaximumWidth(70)
            btn_plus = QPushButton(f"+")
            btn_plus.setFixedWidth(30)

            grid.addWidget(label, i, 0)
            grid.addWidget(btn_minus, i, 1)
            grid.addWidget(spin_box, i, 2)
            grid.addWidget(btn_plus, i, 3)

        # Pousser les widgets vers la gauche
        grid.setColumnStretch(4, 1)

        return frame

    def _create_store_point_panel(self) -> QWidget:
        """Crée le panneau pour stocker un point de mesure."""
        frame, layout = self._create_frame_with_title("Ajouter un point à la liste")

        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        self.mesure_name = QLineEdit("Mesure_A")
        self.mesure_count = QSpinBox()
        self.mesure_count.setRange(1, 100)
        self.mesure_count.setValue(1)

        btn_store = QPushButton(QIcon(ResourceManager.get_icon_path("add.png")), " Stocker le point dans la liste")

        form_layout.addRow("Nom de la mesure:", self.mesure_name)
        form_layout.addRow("Nombre de mesures:", self.mesure_count)
        layout.addWidget(btn_store)

        return frame

    def _create_actions(self) -> None:
        """Crée les actions spécifiques à la télécommande."""
        self._add_action('set_zero', 'set_zero.png', 'Définition du ZERO', "Définir la position actuelle comme origine")
        self._add_action('set_parking', 'parking.png', 'Définition du Parking',
                         "Définir la position actuelle comme parking")
        self._add_action('set_position', 'set_position.png', "Définition d'une position",
                         "Recaler le système à la position actuelle")
        self._add_action('stop_robot', 'stop.png', 'Arrêt Urgence', "Arrêter immédiatement tous les moteurs")

    def _add_action(self, name: str, icon_file: str, text: str, status_tip: str) -> None:
        """Ajoute une action."""
        action = QAction(QIcon(ResourceManager.get_icon_path(icon_file)), text, self)
        action.setStatusTip(status_tip)
        self._actions[name] = action

    def _create_menus(self) -> None:
        """Crée la barre de menu."""
        menu_bar = self.menuBar()
        menu_ref = menu_bar.addMenu("&Points de Références")
        menu_ref.addAction(self._actions['set_zero'])
        menu_ref.addAction(self._actions['set_parking'])
        menu_ref.addSeparator()
        menu_ref.addAction(self._actions['set_position'])

    def _create_toolbars(self) -> None:
        """Crée la barre d'outils d'urgence."""
        toolbar = QToolBar("Urgence")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        stop_action = self._actions['stop_robot']
        stop_button = QPushButton(stop_action.icon(), stop_action.text())
        stop_button.setStyleSheet("background-color: #D32F2F; color: white; font-weight: bold; padding: 4px;")
        stop_button.setToolTip(stop_action.statusTip())
        stop_button.clicked.connect(lambda: print("Arrêt d'urgence !"))

        toolbar.addWidget(stop_button)


class MainWindow(QMainWindow):
    """Fenêtre principale de l'application de pilotage du robot."""

    def __init__(self) -> None:
        """Initialise la fenêtre principale."""
        super().__init__()

        # Attributs internes
        self._actions: Dict[str, QAction] = {}
        self.telecommande_window: Optional[TelecommandeWindow] = None

        # Configuration de la fenêtre
        self.setWindowTitle('Pilotage du robot')
        self.setGeometry(150, 150, 700, 500)
        self.setWindowIcon(QIcon(ResourceManager.get_icon_path('Window-icon.png')))

        # Initialisation de l'interface
        self._setup_ui()

        # Affichage
        self.show()

    def _setup_ui(self) -> None:
        """Configure l'interface utilisateur responsive."""
        self._create_actions()
        self._create_menus()
        self._create_toolbars()
        self._create_central_widget()
        self._create_statusbar()

        # Configuration de base pour le responsive design
        self.setMinimumSize(500, 400)  # Taille minimale raisonnable
        QApplication.instance().setStyle("Fusion")  # Style moderne et adaptable

    def _create_actions(self) -> None:
        """Crée toutes les actions de l'application."""
        # Actions du menu Fichier
        self._add_action('nouveau', 'new_file.png', '&Nouveau',
                         "Créer un nouveau document")
        self._add_action('ouvrir', 'load_file.png', '&Ouvrir...',
                         "Ouvrir un document existant")
        self._add_action('enregistrer', 'save_file.png', '&Enregistrer',
                         "Enregistrer le document courant", 'Ctrl+S')
        self._add_action('enregistrer_sous', 'save_as.png', 'Enregistrer &sous...',
                         "Enregistrer le document sous un nouveau nom")
        self._add_action('proprietes', 'settings.png', 'P&ropriétés',
                         "Afficher les propriétés du document")
        self._add_action('quitter', 'exit.png', '&Quitter',
                         "Quitter l'application", 'Ctrl+Q')

        # Actions du menu Édition
        self._add_action('undo', 'undo.png', '&Annuler',
                         "Annuler la dernière action", 'Ctrl+Z')
        self._add_action('redo', 'redo.png', '&Rétablir',
                         "Rétablir la dernière action annulée", 'Ctrl+Y')

        # Actions du menu Outils
        self._add_action('measurement_settings', 'settings.png', 'Options Mesures',
                         "Configurer les options de mesure")
        self._add_action('telecommande', 'joystick.png', 'Télécommande',
                         "Ouvrir la télécommande")

        # Actions du menu Aide
        self._add_action('apropos', 'help.png', '&À propos...',
                         "Afficher les informations sur l'application")

        # Actions Séquence
        self._add_action('stop_sequence', 'pause.png', 'Arrêter séquence',
                         "Arrêter la séquence")
        self._add_action('start_sequence', 'play.png', 'Démarrer séquence',
                         "Démarrer la séquence")
        self._add_action('measure_next_point', 'next.png', 'Mesurer point suivant',
                         "Mesurer le prochain point")

        # Actions Pulse
        self._add_action('show_pulse', 'pulse.png', 'Afficher Pulse',
                         "Afficher Pulse")
        self._add_action('start_measurement', 'start_measurement.png', 'Démarrer mesure',
                         "Démarrer la mesure")
        self._add_action('save_measurement', 'save_measurement.png', 'Enregistrer mesure',
                         "Enregistrer la mesure")
        self._add_action('log_pulse', 'log_pulse_5.png', 'Log Pulse',
                         "Voir les logs de Pulse", 'Ctrl+P')

        # Actions Robot
        self._add_action('stop_robot', 'stop.png', 'Arrêter robot',
                         "Arrêter le robot")
        self._add_action('goto_parking', 'goto_parking.png', 'Aller au parking',
                         "Aller au parking")
        self._add_action('goto_zero', 'goto_zero.png', 'Aller au zéro',
                         "Aller au zéro")
        self._add_action('goto_selected', 'goto_point.png', 'Position sélectionnée',
                         "Aller à la position sélectionnée")
        self._add_action('log_robot', 'log_robot.png', 'Log Robot',
                         "Voir les logs du robot", 'Ctrl+R')

        # Actions Édition de la liste de points
        self._add_action('delete_point', 'minus.png', 'Supprimer un point',
                         "Supprimer le point sélectionné")
        self._add_action('add_point', 'add.png', 'Ajouter un point',
                         "Ajouter un nouveau point")
        self._add_action('move_point_up', 'arrow_up.png', 'Déplacer un point vers le haut',
                         "Déplacer le point sélectionné vers le haut")
        self._add_action('move_point_down', 'arrow_down.png', 'Déplacer un point vers le bas',
                         "Déplacer le point sélectionné vers le bas")

        # Connexion des signaux
        self._connect_action_signals()

    def _add_action(self, name: str, icon_file: str, text: str, status_tip: str, shortcut: str = None) -> None:
        """Ajoute une action à la collection d'actions."""
        action = QAction(QIcon(ResourceManager.get_icon_path(icon_file)), text, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.setStatusTip(status_tip)
        self._actions[name] = action

    def _connect_action_signals(self) -> None:
        """Connecte les signaux des actions aux slots."""
        # Fichier
        self._actions['nouveau'].triggered.connect(lambda: self._on_action("Nouveau"))
        self._actions['ouvrir'].triggered.connect(lambda: self._on_action("Ouvrir"))
        self._actions['enregistrer'].triggered.connect(lambda: self._on_action("Enregistrer"))
        self._actions['enregistrer_sous'].triggered.connect(lambda: self._on_action("Enregistrer sous"))
        self._actions['proprietes'].triggered.connect(lambda: self._on_action("Propriétés"))
        self._actions['quitter'].triggered.connect(self.close)

        # Édition
        self._actions['undo'].triggered.connect(lambda: self._on_action("Annuler"))
        self._actions['redo'].triggered.connect(lambda: self._on_action("Rétablir"))

        # Outils
        self._actions['measurement_settings'].triggered.connect(
            lambda: self._on_action("Options Mesures"))
        self._actions['telecommande'].triggered.connect(self._open_telecommande)

        # Aide
        self._actions['apropos'].triggered.connect(self._on_about)

        # Séquence
        self._actions['stop_sequence'].triggered.connect(
            lambda: self._on_action("Arrêter Séquence"))
        self._actions['start_sequence'].triggered.connect(
            lambda: self._on_action("Démarrer Séquence"))
        self._actions['measure_next_point'].triggered.connect(
            lambda: self._on_action("Mesurer Prochain Point"))

        # Pulse
        self._actions['show_pulse'].triggered.connect(lambda: self._on_action("Afficher Pulse"))
        self._actions['start_measurement'].triggered.connect(
            lambda: self._on_action("Démarrer Mesure"))
        self._actions['save_measurement'].triggered.connect(
            lambda: self._on_action("Enregistrer Mesure"))
        self._actions['log_pulse'].triggered.connect(lambda: self._on_action("Voir les Logs de Pulse"))

        # Robot
        self._actions['stop_robot'].triggered.connect(lambda: self._on_action("Arrêter Robot"))
        self._actions['goto_parking'].triggered.connect(
            lambda: self._on_action("Aller au Parking"))
        self._actions['goto_zero'].triggered.connect(lambda: self._on_action("Aller au Zéro"))
        self._actions['goto_selected'].triggered.connect(
            lambda: self._on_action("Aller à la Position Sélectionnée"))
        self._actions['log_robot'].triggered.connect(lambda: self._on_action("Voir les Logs du Robot"))

        # Point list edition
        self._actions['delete_point'].triggered.connect(lambda: self._on_action("Supprimer un Point"))
        self._actions['add_point'].triggered.connect(lambda: self._on_action("Ajouter un Point"))
        self._actions['move_point_up'].triggered.connect(lambda: self._on_action("Déplacer un Point vers le Haut"))
        self._actions['move_point_down'].triggered.connect(lambda: self._on_action("Déplacer un Point vers le Bas"))

        self._actions['delete_point'].triggered.connect(self._delete_point)
        self._actions['add_point'].triggered.connect(self._add_point)
        self._actions['move_point_up'].triggered.connect(self._move_point_up)
        self._actions['move_point_down'].triggered.connect(self._move_point_down)

    def _open_telecommande(self):
        """Ouvre la fenêtre de télécommande."""
        # Crée une seule instance ou la ramène au premier plan si elle existe déjà
        if self.telecommande_window is None or not self.telecommande_window.isVisible():
            self.telecommande_window = TelecommandeWindow()
            self.telecommande_window.show()
            self.statusBar().showMessage("Télécommande ouverte", 3000)
        else:
            self.telecommande_window.activateWindow()
            self.telecommande_window.raise_()

    def _create_menus(self) -> None:
        """Crée la barre de menu et les menus."""
        menu_bar = self.menuBar()

        # Menu Fichier
        menu_fichier = menu_bar.addMenu('&Fichier')
        menu_fichier.addAction(self._actions['nouveau'])
        menu_fichier.addSeparator()
        menu_fichier.addAction(self._actions['ouvrir'])
        menu_fichier.addAction(self._actions['enregistrer'])
        menu_fichier.addAction(self._actions['enregistrer_sous'])
        menu_fichier.addSeparator()
        menu_fichier.addAction(self._actions['quitter'])

        # Menu Édition
        menu_edition = menu_bar.addMenu('&Édition')
        menu_edition.addAction(self._actions['undo'])
        menu_edition.addAction(self._actions['redo'])

        # Menu Outils
        menu_outils = menu_bar.addMenu('&Outils')
        menu_outils.addAction(self._actions['measurement_settings'])
        menu_outils.addSeparator()
        menu_outils.addAction(self._actions['telecommande'])

        # Menu Aide
        menu_aide = menu_bar.addMenu('&Aide')
        menu_aide.addAction(self._actions['apropos'])

    def _create_toolbars(self) -> None:
        """Crée les barres d'outils."""
        # Toolbar Séquence
        toolbar_sequence = QToolBar("Outils Séquence")
        toolbar_sequence.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar_sequence)
        toolbar_sequence.addWidget(QLabel("Séquence : "))
        toolbar_sequence.addAction(self._actions['stop_sequence'])
        toolbar_sequence.addAction(self._actions['start_sequence'])
        toolbar_sequence.addAction(self._actions['measure_next_point'])

        # Toolbar Pulse
        toolbar_pulse = QToolBar("Outils Pulse")
        toolbar_pulse.setIconSize(QSize(24, 24))
        toolbar_pulse.setFixedWidth(300)
        self.addToolBar(toolbar_pulse)
        toolbar_pulse.addWidget(QLabel("Pulse : "))
        toolbar_pulse.addAction(self._actions['show_pulse'])
        toolbar_pulse.addAction(self._actions['start_measurement'])
        toolbar_pulse.addSeparator()
        toolbar_pulse.addWidget(QLineEdit("Fichier_mesure.txt"))
        toolbar_pulse.addAction(self._actions['save_measurement'])
        toolbar_pulse.addAction(self._actions['log_pulse'])

        # Toolbar Robot (nouvelle rangée)
        toolbar_robot = QToolBar("Outils Robot")
        toolbar_robot.setIconSize(QSize(24, 24))
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        self.addToolBar(toolbar_robot)
        toolbar_robot.addWidget(QLabel("Robot : "))
        toolbar_robot.addAction(self._actions['stop_robot'])
        toolbar_robot.addAction(self._actions['goto_parking'])
        toolbar_robot.addAction(self._actions['goto_zero'])
        toolbar_robot.addAction(self._actions['goto_selected'])
        toolbar_robot.addAction(self._actions['log_robot'])

        # Toolbar Édition (barre verticale à gauche)
        toolbar_edition = QToolBar("Outils Édition")
        toolbar_edition.setIconSize(QSize(24, 24))
        toolbar_edition.setOrientation(Qt.Orientation.Vertical)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, toolbar_edition)
        toolbar_edition.addAction(self._actions['delete_point'])
        toolbar_edition.addAction(self._actions['add_point'])
        toolbar_edition.addSeparator()
        toolbar_edition.addAction(self._actions['move_point_up'])
        toolbar_edition.addAction(self._actions['move_point_down'])
        toolbar_edition.addSeparator()
        toolbar_edition.addAction(self._actions['undo'])
        toolbar_edition.addAction(self._actions['redo'])

    def _create_central_widget(self) -> None:
        """Crée un widget central avec un tableau de points."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Titre du tableau
        title_label = QLabel("Liste des points à mesurer")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        # Création du tableau
        self.points_table = QTableWidget()
        self.points_table.setColumnCount(5)  # 5 colonnes au lieu de 6
        self.points_table.setHorizontalHeaderLabels(["X (mm)", "Y (mm)", "Z (mm)", "θ (°)", "φ (°)"])

        # Activer les numéros de ligne par défaut
        self.points_table.verticalHeader().setVisible(True)

        # Configuration du tableau pour qu'il soit responsive
        self.points_table.horizontalHeader().setStretchLastSection(True)
        self.points_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.points_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Exemple de données
        self._populate_table_with_sample_data()

        main_layout.addWidget(self.points_table)

        # Connecter les signaux pour la manipulation des points
        self.points_table.itemSelectionChanged.connect(self._update_point_actions_state)

    def _populate_table_with_sample_data(self) -> None:
        """Remplit le tableau avec des données d'exemple."""
        sample_points = [
            (50.0, 100.0, 150.0, 30.0, 45.0),
            (75.0, 125.0, 175.0, 40.0, 50.0),
            (100.0, 150.0, 200.0, 50.0, 55.0),
            (125.0, 175.0, 225.0, 60.0, 60.0),
        ]

        self.points_table.setRowCount(len(sample_points))

        for row, point in enumerate(sample_points):
            # Coordonnées X, Y, Z, θ, φ
            for col, value in enumerate(point):
                item = QTableWidgetItem(f"{value:.2f}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.points_table.setItem(row, col, item)

    def _update_point_actions_state(self) -> None:
        """Met à jour l'état des actions liées aux points en fonction de la sélection."""
        selected_rows = self.points_table.selectionModel().selectedRows()
        has_selection = len(selected_rows) > 0

        # Activer/désactiver les actions de manipulation des points
        self._actions['delete_point'].setEnabled(has_selection)
        self._actions['goto_selected'].setEnabled(has_selection)

        # Activer/désactiver les actions de déplacement selon la position
        if has_selection:
            row = selected_rows[0].row()
            self._actions['move_point_up'].setEnabled(row > 0)
            self._actions['move_point_down'].setEnabled(row < self.points_table.rowCount() - 1)
        else:
            self._actions['move_point_up'].setEnabled(False)
            self._actions['move_point_down'].setEnabled(False)

    def _move_point_up(self) -> None:
        """Déplace le point sélectionné vers le haut dans la liste."""
        selected_rows = self.points_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        current_row = selected_rows[0].row()
        if current_row <= 0:
            return

        # Échanger les données entre lignes
        for col in range(self.points_table.columnCount()):
            current_item = self.points_table.item(current_row, col)
            above_item = self.points_table.item(current_row - 1, col)

            if current_item and above_item:
                current_text = current_item.text()
                above_text = above_item.text()

                current_item.setText(above_text)
                above_item.setText(current_text)

        # Sélectionner la ligne déplacée
        self.points_table.selectRow(current_row - 1)

    def _move_point_down(self) -> None:
        """Déplace le point sélectionné vers le bas dans la liste."""
        selected_rows = self.points_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        current_row = selected_rows[0].row()
        if current_row >= self.points_table.rowCount() - 1:
            return

        # Échanger les données entre lignes
        for col in range(self.points_table.columnCount()):
            current_item = self.points_table.item(current_row, col)
            below_item = self.points_table.item(current_row + 1, col)

            if current_item and below_item:
                current_text = current_item.text()
                below_text = below_item.text()

                current_item.setText(below_text)
                below_item.setText(current_text)

        # Sélectionner la ligne déplacée
        self.points_table.selectRow(current_row + 1)

    def _add_point(self) -> None:
        """Ajoute un nouveau point à la liste."""
        row_count = self.points_table.rowCount()
        self.points_table.insertRow(row_count)

        # Remplir les nouvelles cellules avec des valeurs par défaut
        for col in range(self.points_table.columnCount()):
            item = QTableWidgetItem("0.00")
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.points_table.setItem(row_count, col, item)

        # Sélectionner la nouvelle ligne
        self.points_table.selectRow(row_count)

    def _delete_point(self) -> None:
        """Supprime le point sélectionné de la liste."""
        selected_rows = self.points_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        # Supprimer les lignes sélectionnées (en commençant par la dernière pour éviter les décalages)
        for row in sorted(selected_rows, reverse=True):
            self.points_table.removeRow(row.row())

        # Mettre à jour l'état des actions
        self._update_point_actions_state()

    def _create_statusbar(self) -> None:
        """Configure la barre d'état responsive."""
        status_bar = self.statusBar()
        status_bar.showMessage('Prêt')

        # Widget de coordonnées avec layout
        coord_widget = QWidget()
        coord_layout = QHBoxLayout(coord_widget)
        coord_layout.setContentsMargins(5, 0, 5, 0)
        coord_layout.setSpacing(30)  # Espacement entre les éléments X:50mm---Y:100mm etc

        # Labels pour chaque coordonnée avec politiques de taille
        self.coord_values = {}
        for coord, unit in [('X', 'mm'), ('Y', 'mm'), ('Z', 'mm'), ('θ', '°'), ('φ', '°')]:
            coord_container = QWidget()
            container_layout = QHBoxLayout(coord_container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(2)  # Espacement entre les éléments X:---50---mm etc

            # Label avec le nom de la coordonnée
            label = QLabel(f"{coord}:")

            # Label pour la valeur
            value = QLabel("0.00")
            value.setMinimumWidth(40)  # Largeur minimale au lieu de fixe
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            value.setFrameStyle(QFrame.Panel | QFrame.Sunken)
            value.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            self.coord_values[coord] = value

            # Label pour l'unité
            unit_label = QLabel(unit)

            # Ajouter au layout du conteneur
            container_layout.addWidget(label)
            container_layout.addWidget(value)
            container_layout.addWidget(unit_label)

            # Ajouter le conteneur au layout principal
            coord_layout.addWidget(coord_container)

        self.update_robot_coordinates(50, 100, 150, 30, 45)  # Exemple de mise à jour des coordonnées

        # Ajouter le widget à la barre d'état
        status_bar.addPermanentWidget(coord_widget)

    def update_robot_coordinates(self, x=0, y=0, z=0, theta=0, phi=0) -> None:
        """Met à jour l'affichage des coordonnées du robot."""
        coords = {'X': x, 'Y': y, 'Z': z, 'θ': theta, 'φ': phi}
        for key, value in coords.items():
            if key in self.coord_values:
                self.coord_values[key].setText(f"{value:.2f}")

    # --- Slots ---
    @Slot(str)
    def _on_action(self, action_name: str) -> None:
        """Gère les actions génériques."""
        print(f"Action déclenchée : {action_name}")
        self.statusBar().showMessage(f"Action : {action_name}", 3000)

    @Slot()
    def _on_about(self) -> None:
        """Affiche la boîte de dialogue À propos."""
        print("Action déclenchée : À propos")
        QMessageBox.about(
            self,
            "À propos...",
            "Logiciel de pilotage du robot v0.1\nPour l'UMRAE."
        )

    @Slot(bool)
    def _on_toggle_fullscreen(self, checked: bool) -> None:
        """Bascule l'affichage en plein écran."""
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()
        status = "Plein Écran Activé" if checked else "Plein Écran Désactivé"
        self.statusBar().showMessage(status, 3000)
        print(f"Action déclenchée : {status}")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Gère l'événement de fermeture de la fenêtre."""
        if self.telecommande_window and self.telecommande_window.isVisible():
            self.telecommande_window.close()

        reponse = QMessageBox.question(
            self, 'Confirmation', "Quitter l'application ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reponse == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()


def main() -> int:
    """Fonction principale de l'application."""
    # Vérifier les ressources
    if not ResourceManager.check_resources():
        print(f"Erreur critique : Le dossier d'icônes '{ResourceManager.ICONS_DIR}' est introuvable.")
        return 1

    # Créer et exécuter l'application
    app = QApplication(sys.argv)
    fenetre = MainWindow()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())