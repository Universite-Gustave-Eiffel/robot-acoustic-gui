# src/gui/telecommande_window.py

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QVBoxLayout, QGridLayout, QFrame,
    QLineEdit, QSpinBox, QPushButton, QFormLayout, QGroupBox, QHBoxLayout,
    QMessageBox, QToolBar
)
from PySide6.QtGui import QIcon, QAction, QKeyEvent, QCloseEvent
from PySide6.QtCore import Slot, Qt
import configparser

from src.gui.resource_manager import ResourceManager
from src.main_controller import MainController


class TelecommandeWindow(QMainWindow):
    """
    Fenêtre de contrôle manuel avancé, avec mode de contrôle clavier en temps réel.
    """

    def __init__(self, controller: MainController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle('Télécommande du robot')
        self.setWindowIcon(QIcon(ResourceManager.get_icon_path('joystick.png')))
        self.setGeometry(200, 200, 750, 600)

        self.robot_pos_widgets = {}
        self.capsule_pos_widgets = {}
        self.jog_widgets = {}
        self.absolute_target_widgets = {}

        self.keyboard_control_active = False
        self.active_jogs = {}

        # Mappage des touches (ZQSD pour AZERTY)
        self.key_mapping = {
            Qt.Key_Up: ('Y', 1),
            Qt.Key_Down: ('Y', -1),
            Qt.Key_Left: ('X', -1),
            Qt.Key_Right: ('X', 1),
            Qt.Key_PageUp: ('Z', 1),
            Qt.Key_PageDown: ('Z', -1),
            Qt.Key_D: ('THETA', 1),
            Qt.Key_Q: ('THETA', -1),
            Qt.Key_Z: ('PHI', 1),
            Qt.Key_S: ('PHI', -1),
        }

        self._create_ui()

        self.controller.robot_position_updated.connect(self.update_position_display)
        self.controller.robot_move_completed.connect(self.update_target_fields_after_event)

        self._on_use_current_pos()

    def _create_ui(self):
        self._create_actions_and_toolbar()

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        main_layout.addWidget(self._create_position_display_panel())
        main_layout.addWidget(self._create_realtime_control_panel())
        main_layout.addWidget(self._create_jogging_panel())
        main_layout.addWidget(self._create_absolute_move_panel())
        main_layout.addWidget(self._create_point_creation_panel())
        main_layout.addStretch()

        self._update_widgets_state()

    def _create_actions_and_toolbar(self):
        toolbar = QToolBar("Commandes de Référence")
        self.addToolBar(toolbar)
        stop_action = QAction(QIcon(ResourceManager.get_icon_path('stop.png')), "Arrêt d'Urgence", self)
        stop_action.triggered.connect(
            lambda: self.controller.robot.stop_all_motion() if self.controller.robot else None)
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
        for i, header_text in enumerate(headers): grid.addWidget(QLabel(f"<b>{header_text}</b>"), 0, i)
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

    def _create_key_label(self, text):
        label = QLabel(text)
        label.setFrameStyle(QFrame.Box | QFrame.Raised)
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumSize(40, 40)
        label.setStyleSheet("background-color: #DDD; border-radius: 4px; font-weight: bold;")
        return label

    def _create_realtime_control_panel(self) -> QGroupBox:
        group = QGroupBox("Contrôle Clavier Temps Réel")
        main_layout = QVBoxLayout(group)
        self.keyboard_control_button = QPushButton("Activer le Contrôle Clavier")
        self.keyboard_control_button.setCheckable(True)
        self.keyboard_control_button.toggled.connect(self._on_keyboard_control_toggled)
        main_layout.addWidget(self.keyboard_control_button)
        self.keyboard_layout_widget = QWidget()
        controls_layout = QHBoxLayout(self.keyboard_layout_widget)
        rotation_group = QGroupBox("Rotations")
        rotation_layout = QGridLayout(rotation_group)
        rotation_layout.addWidget(self._create_key_label("Z (Phi+)"), 0, 1)
        rotation_layout.addWidget(self._create_key_label("Q (Th-)"), 1, 0)
        rotation_layout.addWidget(self._create_key_label("S (Phi-)"), 1, 1)
        rotation_layout.addWidget(self._create_key_label("D (Th+)"), 1, 2)
        controls_layout.addWidget(rotation_group)
        altitude_group = QGroupBox("Altitude")
        altitude_layout = QVBoxLayout(altitude_group)
        altitude_layout.addWidget(self._create_key_label("PgUp (Z+)"))
        altitude_layout.addWidget(self._create_key_label("PgDn (Z-)"))
        altitude_layout.addStretch()
        controls_layout.addWidget(altitude_group)
        translation_group = QGroupBox("Translation")
        translation_layout = QGridLayout(translation_group)
        translation_layout.addWidget(self._create_key_label("↑ (Y+)"), 0, 1)
        translation_layout.addWidget(self._create_key_label("← (X-)"), 1, 0)
        translation_layout.addWidget(self._create_key_label("↓ (Y-)"), 1, 1)
        translation_layout.addWidget(self._create_key_label("→ (X+)"), 1, 2)
        controls_layout.addWidget(translation_group)
        main_layout.addWidget(self.keyboard_layout_widget)
        self.keyboard_layout_widget.hide()
        return group

    def _create_jogging_panel(self) -> QGroupBox:
        self.jogging_group = QGroupBox("Déplacements Relatifs (Pas-à-pas)")
        grid = QGridLayout(self.jogging_group)
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
        return self.jogging_group

    def _create_absolute_move_panel(self) -> QGroupBox:
        self.absolute_move_group = QGroupBox("Déplacement Absolu (Coordonnées Capsule)")
        layout = QHBoxLayout(self.absolute_move_group)
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
        return self.absolute_move_group

    def _create_point_creation_panel(self) -> QGroupBox:
        self.point_creation_group = QGroupBox("Ajout de Point à la Séquence")
        layout = QHBoxLayout(self.point_creation_group)
        store_button = QPushButton(QIcon(ResourceManager.get_icon_path('add.png')),
                                   "Ajouter la position actuelle du robot à la liste")
        store_button.clicked.connect(self.controller.add_current_position_as_point)
        layout.addWidget(store_button)
        return self.point_creation_group

    def _update_widgets_state(self):
        is_locked = self.keyboard_control_active
        self.jogging_group.setEnabled(not is_locked)
        self.absolute_move_group.setEnabled(not is_locked)
        self.point_creation_group.setEnabled(not is_locked)

    @Slot(bool)
    def _on_keyboard_control_toggled(self, checked):
        self.keyboard_control_active = checked
        self._update_widgets_state()
        self.keyboard_layout_widget.setVisible(checked)

        if checked:
            self.keyboard_control_button.setText("Désactiver le Contrôle Clavier (FOCUS)")
            if self.controller.robot:
                self.controller.robot.begin_jog_mode()
            self.setFocus()
        else:
            self.keyboard_control_button.setText("Activer le Contrôle Clavier")
            if self.controller.robot:
                self.controller.robot.reset_jog_mode()
            self.active_jogs.clear()

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
        for axis, widget in self.capsule_pos_widgets.items():
            try:
                current_val = int(float(widget.text()))
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
        if reply == QMessageBox.No: return
        try:
            coords = {axis: widget.value() for axis, widget in self.absolute_target_widgets.items()}
            self.controller.define_robot_position(coords)
        except ValueError:
            QMessageBox.warning(self, "Erreur de saisie", "Valeurs numériques invalides.")

    def keyPressEvent(self, event: QKeyEvent):
        if not self.keyboard_control_active or event.isAutoRepeat():
            super().keyPressEvent(event)
            return

        key = event.key()
        if key == Qt.Key_W: key = Qt.Key_Z
        if key == Qt.Key_A: key = Qt.Key_Q

        if key in self.key_mapping:
            axis, direction = self.key_mapping[key]
            speed_key_map = {'X': 'jog_xy_mm_s', 'Y': 'jog_xy_mm_s', 'Z': 'jog_z_mm_s', 'THETA': 'jog_rot_deg_s',
                             'PHI': 'jog_rot_deg_s'}
            speed_config_key = speed_key_map.get(axis)
            try:
                speed = self.controller.config.getfloat('ROBOT_SPEEDS', speed_config_key)
                if self.active_jogs.get(axis) != direction:
                    self.controller.robot_jog_continuous(**{axis.lower(): direction * speed})
                    self.active_jogs[axis] = direction
            except (configparser.NoOptionError, ValueError) as e:
                self.controller.log_message_sent.emit(f"Erreur de config vitesse Jog pour l'axe {axis}: {e}")
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if not self.keyboard_control_active or event.isAutoRepeat():
            super().keyReleaseEvent(event)
            return

        key = event.key()
        if key == Qt.Key_W: key = Qt.Key_Z
        if key == Qt.Key_A: key = Qt.Key_Q

        if key in self.key_mapping:
            axis, _ = self.key_mapping[key]
            if self.active_jogs.get(axis) != 0:
                self.controller.robot_jog_continuous(**{axis.lower(): 0})
                self.active_jogs[axis] = 0
        else:
            super().keyReleaseEvent(event)

    def closeEvent(self, event: QCloseEvent):
        """Surchargé pour s'assurer de sortir proprement du mode Jog."""
        if self.keyboard_control_active and self.controller.robot:
            self.controller.log_message_sent.emit("Fermeture de la télécommande: réinitialisation du mode Jog.")
            self.controller.robot.reset_jog_mode()
        event.accept()