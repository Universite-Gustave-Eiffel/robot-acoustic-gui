# src/gui/telecommande_window.py

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QVBoxLayout, QGridLayout, QFrame,
    QLineEdit, QSpinBox, QPushButton, QFormLayout, QGroupBox, QHBoxLayout,
    QMessageBox, QToolBar
)
from PySide6.QtGui import QIcon, QAction, QDoubleValidator
from PySide6.QtCore import Slot, Qt

from src.gui.resource_manager import ResourceManager
from src.main_controller import MainController


class TelecommandeWindow(QMainWindow):
    """
    Fenêtre dédiée au contrôle manuel avancé, à la définition
    de points et à la calibration des références du robot.
    """

    def __init__(self, controller: MainController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle('Télécommande du robot')
        self.setWindowIcon(QIcon(ResourceManager.get_icon_path('joystick.png')))
        self.setGeometry(200, 200, 750, 600)

        # Dictionnaires pour stocker les widgets par axe pour un accès facile
        self.robot_pos_widgets = {}
        self.capsule_pos_widgets = {}
        self.jog_widgets = {}
        self.capsule_target_widgets = {}
        self.robot_target_widgets = {}

        self._create_ui()

        # Connexions des signaux
        self.controller.robot_position_updated.connect(self.update_position_display)
        self.controller.robot_coords_calculated.connect(self.update_robot_target_fields)

    def _create_ui(self):
        self._create_actions_and_toolbar()

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # Création des différentes sections
        main_layout.addWidget(self._create_position_display_panel())
        main_layout.addWidget(self._create_jogging_panel())
        main_layout.addWidget(self._create_absolute_move_panel())
        main_layout.addWidget(self._create_point_creation_panel())
        main_layout.addStretch()

    def _create_actions_and_toolbar(self):
        toolbar = QToolBar("Commandes de Référence")
        self.addToolBar(toolbar)

        stop_action = QAction(QIcon(ResourceManager.get_icon_path('stop_robot.png')), "Arrêt d'Urgence", self)
        stop_action.triggered.connect(self.controller.robot.stop_all_motion)
        toolbar.addAction(stop_action)

        toolbar.addSeparator()

        set_zero_action = QAction(QIcon(ResourceManager.get_icon_path('set_zero.png')), "Définir Zéro Actuel", self)
        set_zero_action.triggered.connect(self.controller.set_robot_zero_position)
        toolbar.addAction(set_zero_action)

        set_parking_action = QAction(QIcon(ResourceManager.get_icon_path('parking.png')), "Définir Parking Actuel",
                                     self)
        set_parking_action.triggered.connect(self.controller.set_robot_parking_position)
        toolbar.addAction(set_parking_action)

        define_pos_action = QAction(QIcon(ResourceManager.get_icon_path('define_pos.png')), "Forcer Position Robot",
                                    self)
        define_pos_action.setStatusTip("Définit la position du robot aux coordonnées entrées dans les champs 'Robot'")
        define_pos_action.triggered.connect(self._on_define_position)
        toolbar.addAction(define_pos_action)

    def _create_position_display_panel(self) -> QGroupBox:
        group = QGroupBox("Position Actuelle")
        grid = QGridLayout(group)

        headers = ["", "X (mm)", "Y (mm)", "Z (mm)", "Theta (°)", "Phi (°)"]
        for i, header_text in enumerate(headers):
            grid.addWidget(QLabel(f"<b>{header_text}</b>"), 0, i + 1)

        grid.addWidget(QLabel("<b>Robot:</b>"), 1, 0)
        grid.addWidget(QLabel("<b>Capsule:</b>"), 2, 0)

        axes = ['X', 'Y', 'Z', 'THETA', 'PHI']
        for i, axis in enumerate(axes):
            self.robot_pos_widgets[axis] = QLineEdit("N/C")
            self.robot_pos_widgets[axis].setReadOnly(True)
            self.capsule_pos_widgets[axis] = QLineEdit("N/C")
            self.capsule_pos_widgets[axis].setReadOnly(True)
            grid.addWidget(self.robot_pos_widgets[axis], 1, i + 1)
            grid.addWidget(self.capsule_pos_widgets[axis], 2, i + 1)

        return group

    def _create_jogging_panel(self) -> QGroupBox:
        group = QGroupBox("Déplacements Relatifs (Jogging)")
        grid = QGridLayout(group)

        axes = ["X", "Y", "Z", "THETA", "PHI"]
        for i, axis in enumerate(axes):
            label = QLabel(f"<b>Pas {axis}:</b>")
            btn_minus = QPushButton("-")
            btn_minus.setFixedWidth(40)
            spin_box = QLineEdit("10.0")
            spin_box.setValidator(QDoubleValidator())
            btn_plus = QPushButton("+")
            btn_plus.setFixedWidth(40)

            self.jog_widgets[axis] = spin_box  # Store the line edit

            btn_minus.clicked.connect(lambda ch, a=axis, s=-1: self._on_jog(a, s))
            btn_plus.clicked.connect(lambda ch, a=axis, s=1: self._on_jog(a, s))

            grid.addWidget(label, i, 0)
            grid.addWidget(btn_minus, i, 1)
            grid.addWidget(spin_box, i, 2)
            grid.addWidget(btn_plus, i, 3)

        return group

    def _create_absolute_move_panel(self) -> QGroupBox:
        group = QGroupBox("Déplacements Absolus")
        main_layout = QHBoxLayout(group)

        # Panel Capsule
        capsule_panel = QGroupBox("1. Entrer Coords Capsule")
        capsule_layout = QFormLayout(capsule_panel)
        axes = ['X', 'Y', 'Z', 'THETA', 'PHI']
        for axis in axes:
            le = QLineEdit("0.0")
            le.setValidator(QDoubleValidator())
            self.capsule_target_widgets[axis] = le
            unit = " (mm)" if axis in ['X', 'Y', 'Z'] else " (°)"
            capsule_layout.addRow(axis + unit, le)
        main_layout.addWidget(capsule_panel)

        # Panel de contrôle (boutons)
        control_layout = QVBoxLayout()
        control_layout.addStretch()
        calc_button = QPushButton("  ->\nCalculer")
        use_current_button = QPushButton("  <-\nUtiliser Actuelle")
        go_button = QPushButton(QIcon(ResourceManager.get_icon_path('play.png')), "Go")
        control_layout.addWidget(calc_button)
        control_layout.addWidget(use_current_button)
        control_layout.addStretch()
        main_layout.addLayout(control_layout)

        # Panel Robot
        robot_panel = QGroupBox("2. Commander Coords Robot")
        robot_layout = QFormLayout(robot_panel)
        for axis in axes:
            le = QLineEdit("0.0")
            le.setValidator(QDoubleValidator())
            self.robot_target_widgets[axis] = le
            unit = " (mm)" if axis in ['X', 'Y', 'Z'] else " (°)"
            robot_layout.addRow(axis + unit, le)
        robot_layout.addRow(go_button)
        main_layout.addWidget(robot_panel)

        # Connexions
        calc_button.clicked.connect(self._on_calculate_coords)
        use_current_button.clicked.connect(self._on_use_current_pos)
        go_button.clicked.connect(self._on_go_absolute)

        return group

    def _create_point_creation_panel(self) -> QGroupBox:
        group = QGroupBox("Création d'un Point de Mesure")
        layout = QFormLayout(group)
        self.point_name_edit = QLineEdit("mesure")
        self.point_count_edit = QLineEdit("1")
        self.point_count_edit.setValidator(QDoubleValidator(1, 100, 0))

        store_button = QPushButton(QIcon(ResourceManager.get_icon_path('add.png')), "Stocker le point dans la liste")
        store_button.clicked.connect(self._on_store_point)

        layout.addRow("Nom de base de la mesure :", self.point_name_edit)
        # La notion de 'nombre de mesures' est plus liée à la séquence, on la retire pour l'instant
        # layout.addRow("Nombre de mesures :", self.point_count_edit)
        layout.addRow(store_button)
        return group

    # --- SLOTS DE MISE A JOUR DE L'UI ---

    @Slot(dict)
    def update_position_display(self, positions: dict):
        for axis, widget in self.robot_pos_widgets.items():
            widget.setText(f"{positions.get(axis, 0):.3f}")

        if self.controller.robot:
            for axis, widget in self.capsule_pos_widgets.items():
                widget.setText(f"{self.controller.robot.capsule_pos.get(axis, 0):.3f}")

    @Slot(dict)
    def update_robot_target_fields(self, robot_coords: dict):
        for axis, widget in self.robot_target_widgets.items():
            widget.setText(f"{robot_coords.get(axis, 0):.3f}")

    # --- SLOTS D'ACTIONS UTILISATEUR ---

    def _on_jog(self, axis, sign):
        try:
            distance = float(self.jog_widgets[axis].text())
            self.controller.move_robot_relative(axis.lower(), sign * distance)
        except ValueError:
            self.controller.log_message_sent.emit(f"Erreur: Le pas de déplacement pour l'axe {axis} est invalide.")

    def _on_calculate_coords(self):
        try:
            coords = {axis: float(widget.text()) for axis, widget in self.capsule_target_widgets.items()}
            self.controller.calculate_robot_coords(coords)
        except ValueError:
            QMessageBox.warning(self, "Erreur de saisie",
                                "Veuillez entrer des valeurs numériques valides pour les coordonnées de la capsule.")

    def _on_use_current_pos(self):
        # On utilise les coordonnées robot (plus directes) pour remplir les champs cibles
        for axis, widget in self.robot_pos_widgets.items():
            self.capsule_target_widgets[axis].setText(widget.text())

    def _on_go_absolute(self):
        try:
            coords = {axis: float(widget.text()) for axis, widget in self.robot_target_widgets.items()}
            self.controller.move_robot_absolute(coords)
        except ValueError:
            QMessageBox.warning(self, "Erreur de saisie",
                                "Veuillez entrer des valeurs numériques valides pour les coordonnées du robot.")

    def _on_store_point(self):
        self.controller.add_current_position_as_point()

    def _on_define_position(self):
        reply = QMessageBox.question(self, "Confirmation",
                                     "Ceci va redéfinir l'origine du robot à la position spécifiée dans les champs 'Robot'.\n"
                                     "Êtes-vous sûr de vouloir continuer ?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No:
            return

        try:
            coords = {axis: float(widget.text()) for axis, widget in self.robot_target_widgets.items()}
            self.controller.define_robot_position(coords)
        except ValueError:
            QMessageBox.warning(self, "Erreur de saisie",
                                "Veuillez entrer des valeurs numériques valides pour les coordonnées du robot.")