# src/gui/telecommande_window.py

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QVBoxLayout, QGridLayout, QFrame,
    QLineEdit, QSpinBox, QPushButton, QFormLayout, QGroupBox, QHBoxLayout,
    QMessageBox, QToolBar
)
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Slot, Qt

from src.gui.resource_manager import ResourceManager
from src.main_controller import MainController


class TelecommandeWindow(QMainWindow):
    """
    Fenêtre de contrôle manuel avancé, simplifiée autour des coordonnées de la capsule.
    """

    def __init__(self, controller: MainController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle('Télécommande du robot')
        self.setWindowIcon(QIcon(ResourceManager.get_icon_path('joystick.png')))
        self.setGeometry(200, 200, 750, 550)

        # Dictionnaires pour stocker les widgets par axe pour un accès facile
        self.robot_pos_widgets = {}
        self.capsule_pos_widgets = {}
        self.jog_widgets = {}
        self.absolute_target_widgets = {}

        self._create_ui()

        # Connexions des signaux
        self.controller.robot_position_updated.connect(self.update_position_display)
        self.controller.robot_move_completed.connect(self.update_target_fields_after_event)

        # Mise à jour initiale des champs cibles à l'ouverture
        self._on_use_current_pos()

    def _create_ui(self):
        self._create_actions_and_toolbar()

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        main_layout.addWidget(self._create_position_display_panel())
        main_layout.addWidget(self._create_jogging_panel())
        main_layout.addWidget(self._create_absolute_move_panel())
        main_layout.addWidget(self._create_point_creation_panel())
        main_layout.addStretch()

    def _create_actions_and_toolbar(self):
        toolbar = QToolBar("Commandes de Référence")
        self.addToolBar(toolbar)

        stop_action = QAction(QIcon(ResourceManager.get_icon_path('stop.png')), "Arrêt d'Urgence", self)
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

        define_pos_action = QAction(QIcon(ResourceManager.get_icon_path('set_position.png')), "Forcer Position", self)
        define_pos_action.setStatusTip(
            "Définit la position physique actuelle du robot aux coordonnées capsule spécifiées dans les champs 'Aller à'")
        define_pos_action.triggered.connect(self._on_define_position)
        toolbar.addAction(define_pos_action)

    def _create_position_display_panel(self) -> QGroupBox:
        group = QGroupBox("Position Actuelle")
        grid = QGridLayout(group)

        headers = ["", "X (mm)", "Y (mm)", "Z (mm)", "Theta (°)", "Phi (°)"]
        for i, header_text in enumerate(headers):
            grid.addWidget(QLabel(f"<b>{header_text}</b>"), 0, i)

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
        group = QGroupBox("Déplacements Relatifs (Pas-à-pas)")
        grid = QGridLayout(group)

        axes = ["X", "Y", "Z", "THETA", "PHI"]
        for i, axis in enumerate(axes):
            label = QLabel(f"<b>Pas {axis}:</b>")
            btn_minus = QPushButton("-")
            btn_minus.setFixedWidth(40)
            spin_box = QSpinBox()
            spin_box.setRange(-1000, 1000)
            spin_box.setValue(10)
            unit = " mm" if axis in ['X', 'Y', 'Z'] else " °"
            spin_box.setSuffix(unit)

            btn_plus = QPushButton("+")
            btn_plus.setFixedWidth(40)

            self.jog_widgets[axis] = spin_box

            btn_minus.clicked.connect(lambda ch, a=axis, s=-1: self._on_jog(a, s))
            btn_plus.clicked.connect(lambda ch, a=axis, s=1: self._on_jog(a, s))

            grid.addWidget(label, i, 0)
            grid.addWidget(btn_minus, i, 1)
            grid.addWidget(spin_box, i, 2)
            grid.addWidget(btn_plus, i, 3)

        return group

    def _create_absolute_move_panel(self) -> QGroupBox:
        group = QGroupBox("Déplacement Absolu (Coordonnées Capsule)")
        layout = QHBoxLayout(group)

        form_layout = QFormLayout()
        axes = ['X', 'Y', 'Z', 'THETA', 'PHI']
        for axis in axes:
            spin_box = QSpinBox()
            spin_box.setRange(-10000, 10000)
            self.absolute_target_widgets[axis] = spin_box
            unit = " (mm)" if axis in ['X', 'Y', 'Z'] else " (°)"
            form_layout.addRow(axis + unit, spin_box)
        layout.addLayout(form_layout)

        control_layout = QVBoxLayout()
        control_layout.addStretch()
        use_current_button = QPushButton("Utiliser Actuelle")
        use_current_button.setStatusTip("Copie la position actuelle de la capsule dans les champs de destination")
        go_button = QPushButton(QIcon(ResourceManager.get_icon_path('play.png')), "Aller à la position")
        control_layout.addWidget(use_current_button)
        control_layout.addWidget(go_button)
        control_layout.addStretch()
        layout.addLayout(control_layout)

        use_current_button.clicked.connect(self._on_use_current_pos)
        go_button.clicked.connect(self._on_go_absolute_capsule)

        return group

    def _create_point_creation_panel(self) -> QGroupBox:
        group = QGroupBox("Ajout de Point à la Séquence")
        layout = QHBoxLayout(group)
        store_button = QPushButton(QIcon(ResourceManager.get_icon_path('add.png')),
                                   "Ajouter la position actuelle du robot à la liste")
        store_button.clicked.connect(self.controller.add_current_position_as_point)
        layout.addWidget(store_button)
        return group

    @Slot(dict)
    def update_position_display(self, positions: dict):
        for axis, widget in self.robot_pos_widgets.items():
            widget.setText(f"{round(positions.get(axis.upper(), 0.0))}")

        if self.controller.robot:
            self.controller.robot._calculate_capsule_position()
            for axis, widget in self.capsule_pos_widgets.items():
                widget.setText(f"{round(self.controller.robot.capsule_pos.get(axis.upper(), 0.0))}")

    @Slot(dict)
    def update_target_fields_after_event(self, last_robot_position: dict):
        """Met à jour les champs de destination avec la position capsule finale après un événement."""
        if not self.controller.robot: return

        self.controller.robot.robot_pos = last_robot_position
        self.controller.robot._calculate_capsule_position()

        for axis, widget in self.absolute_target_widgets.items():
            capsule_pos = self.controller.robot.capsule_pos.get(axis.upper(), 0.0)
            widget.setValue(round(capsule_pos))

    def _on_jog(self, axis, sign):
        distance = self.jog_widgets[axis].value()
        self.controller.move_robot_relative(axis.lower(), sign * distance)

    def _on_use_current_pos(self):
        """Remplit les champs de destination avec la position actuelle de la capsule."""
        for axis, widget in self.capsule_pos_widgets.items():
            try:
                current_val = int(widget.text())
                self.absolute_target_widgets[axis].setValue(current_val)
            except (ValueError, TypeError):
                continue

    def _on_go_absolute_capsule(self):
        try:
            coords = {axis: widget.value() for axis, widget in self.absolute_target_widgets.items()}
            self.controller.move_capsule_absolute(coords)
        except ValueError:
            QMessageBox.warning(self, "Erreur de saisie", "Valeurs numériques invalides.")

    def _on_define_position(self):
        reply = QMessageBox.question(self, "Forcer la Position",
                                     "Cette action va assigner les coordonnées capsule entrées à la position physique actuelle du robot.\n"
                                     "Utilisez cette fonction pour la calibration manuelle.\n\n"
                                     "Êtes-vous sûr de vouloir continuer ?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return

        try:
            coords = {axis: widget.value() for axis, widget in self.absolute_target_widgets.items()}
            self.controller.define_robot_position(coords)
        except ValueError:
            QMessageBox.warning(self, "Erreur de saisie", "Valeurs numériques invalides.")