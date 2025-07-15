# src/gui/telecommande_window.py
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QVBoxLayout, QGridLayout, QFrame,
    QLineEdit, QSpinBox, QPushButton, QFormLayout
)
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Slot

from src.gui.resource_manager import ResourceManager
from src.main_controller import MainController


class TelecommandeWindow(QMainWindow):
    """
    Fenêtre dédiée au contrôle manuel et à l'affichage
    détaillé de la position du robot.
    """
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

    def _create_frame_with_title(self, title_text: str) -> tuple[QFrame, QVBoxLayout]:
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