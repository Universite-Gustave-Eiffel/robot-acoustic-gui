# src/gui/config_window.py

import configparser
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout,
    QLineEdit, QDialogButtonBox, QPushButton, QFileDialog,
    QComboBox, QGroupBox, QMessageBox, QLabel, QScrollArea, QCheckBox
)
from PySide6.QtCore import Qt

from src.main_controller import MainController


class ConfigWindow(QDialog):
    """
    Fenêtre de dialogue pour configurer les paramètres de l'application
    stockés dans les fichiers .ini, avec zone de défilement.
    """

    def __init__(self, controller: MainController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Configuration de l'application")
        self.setMinimumWidth(600)
        self.setMaximumHeight(800)

        # Stocker les valeurs critiques initiales pour détecter les changements
        self.initial_robot_port = ""
        self.initial_robot_baudrate = ""
        self.initial_pulse_project = ""

        # Layout principal
        self.main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        # Widgets conteneurs et ScrollArea pour chaque onglet
        self.robot_tab_widget = QWidget()
        self.pulse_tab_widget = QWidget()

        self.robot_scroll = QScrollArea()
        self.robot_scroll.setWidgetResizable(True)
        self.robot_scroll.setWidget(self.robot_tab_widget)

        self.pulse_scroll = QScrollArea()
        self.pulse_scroll.setWidgetResizable(True)
        self.pulse_scroll.setWidget(self.pulse_tab_widget)

        self.tabs.addTab(self.robot_scroll, "Configuration Robot")
        self.tabs.addTab(self.pulse_scroll, "Configuration PULSE")

        # Remplir les onglets
        self._create_robot_tab()
        self._create_pulse_tab()

        # Boutons de la boîte de dialogue
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.main_layout.addWidget(self.button_box)

        self._load_config()

    def _create_robot_tab(self):
        """Crée le contenu de l'onglet de configuration du robot."""
        layout = QVBoxLayout(self.robot_tab_widget)

        serial_group = QGroupBox("Connexion Série")
        serial_layout = QFormLayout(serial_group)
        self.robot_port = QLineEdit()
        self.robot_baudrate = QComboBox()
        self.robot_baudrate.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.robot_timeout = QLineEdit()
        serial_layout.addRow("Port (ex: COM7):", self.robot_port)
        serial_layout.addRow("Baudrate:", self.robot_baudrate)
        serial_layout.addRow("Timeout (s):", self.robot_timeout)
        layout.addWidget(serial_group)

        movement_group = QGroupBox("Parking")
        movement_layout = QFormLayout(movement_group)
        self.parking_x = QLineEdit()
        self.parking_y = QLineEdit()
        self.parking_z = QLineEdit()
        self.parking_theta = QLineEdit()
        self.parking_phi = QLineEdit()
        movement_layout.addRow("Parking X (mm):", self.parking_x)
        movement_layout.addRow("Parking Y (mm):", self.parking_y)
        movement_layout.addRow("Parking Z (mm):", self.parking_z)
        movement_layout.addRow("Parking Theta (°):", self.parking_theta)
        movement_layout.addRow("Parking Phi (°):", self.parking_phi)
        layout.addWidget(movement_group)

        jog_group = QGroupBox("Vitesses de Contrôle Manuel (Jog)")
        jog_layout = QFormLayout(jog_group)
        self.jog_xy_speed = QLineEdit()
        self.jog_z_speed = QLineEdit()
        self.jog_rot_speed = QLineEdit()
        jog_layout.addRow("Vitesse XY (mm/s):", self.jog_xy_speed)
        jog_layout.addRow("Vitesse Z (mm/s):", self.jog_z_speed)
        jog_layout.addRow("Vitesse Rotation (degré/s):", self.jog_rot_speed)
        layout.addWidget(jog_group)

        sequence_group = QGroupBox("Paramètres de Séquence")
        sequence_layout = QFormLayout(sequence_group)
        self.seq_activer_securite = QCheckBox()
        self.seq_hauteur_securite = QLineEdit()
        self.seq_temps_stabilisation = QLineEdit()
        sequence_layout.addRow("Activer la sécurité de déplacement :", self.seq_activer_securite)
        sequence_layout.addRow("Hauteur de sécurité (axe Z, en mm) :", self.seq_hauteur_securite)
        sequence_layout.addRow("Temps de stabilisation sur position (s) :", self.seq_temps_stabilisation)
        layout.addWidget(sequence_group)

        calib_group = QGroupBox("Calibration et Dynamique")
        calib_layout = QFormLayout(calib_group)
        self.ratio_x = QLineEdit()
        self.ratio_y = QLineEdit()
        self.ratio_z = QLineEdit()
        self.ratio_theta = QLineEdit()
        self.ratio_phi = QLineEdit()
        self.accel = QLineEdit()
        self.decel = QLineEdit()
        calib_layout.addRow("Ratio X (pas/mm):", self.ratio_x)
        calib_layout.addRow("Ratio Y (pas/mm):", self.ratio_y)
        calib_layout.addRow("Ratio Z (pas/mm):", self.ratio_z)
        calib_layout.addRow("Ratio Theta (pas/°):", self.ratio_theta)
        calib_layout.addRow("Ratio Phi (pas/°):", self.ratio_phi)
        calib_layout.addRow("Accélération (pas/s²):", self.accel)
        calib_layout.addRow("Décélération (pas/s²):", self.decel)
        layout.addWidget(calib_group)

        offsets_group = QGroupBox("Corrections Géométriques (Cinématique Capsule)")
        offsets_layout = QFormLayout(offsets_group)
        self.corr_theta_x = QLineEdit()
        self.corr_theta_y = QLineEdit()
        self.corr_theta_z = QLineEdit()
        self.corr_phi_l = QLineEdit()
        offsets_layout.addRow("Correction Theta X (mm):", self.corr_theta_x)
        offsets_layout.addRow("Correction Theta Y (mm):", self.corr_theta_y)
        offsets_layout.addRow("Correction Theta Z (mm):", self.corr_theta_z)
        offsets_layout.addRow("Correction Phi L (mm):", self.corr_phi_l)
        layout.addWidget(offsets_group)

        layout.addStretch()

    def _create_pulse_tab(self):
        layout = QFormLayout(self.pulse_tab_widget)

        paths_group = QGroupBox("Chemins d'accès PULSE")
        paths_layout = QFormLayout(paths_group)

        self.pulse_project_path_edit, self.pulse_project_path_btn = self._create_path_selector(
            is_dir=False, file_filter="Projet PULSE (*.pls)"
        )
        paths_layout.addRow(QLabel("Projet PULSE (.pls):"), self.pulse_project_path_edit)
        paths_layout.addRow("", self.pulse_project_path_btn)

        self.pulse_save_dir_edit, self.pulse_save_dir_btn = self._create_path_selector(is_dir=True)
        paths_layout.addRow(QLabel("Répertoire de sauvegarde :"), self.pulse_save_dir_edit)
        paths_layout.addRow("", self.pulse_save_dir_btn)

        self.pulse_fg_name = QLineEdit()
        paths_layout.addRow(QLabel("FunctionGroup à sauver :"), self.pulse_fg_name)

        layout.addWidget(paths_group)

    def _create_path_selector(self, is_dir=False, file_filter="Tous les fichiers (*)"):
        line_edit = QLineEdit()
        browse_button = QPushButton("Parcourir...")

        def browse():
            if is_dir:
                path = QFileDialog.getExistingDirectory(self, "Sélectionner un répertoire")
            else:
                path, _ = QFileDialog.getOpenFileName(self, "Sélectionner un fichier", "", file_filter)
            if path:
                line_edit.setText(path.replace("/", "\\"))

        browse_button.clicked.connect(browse)
        return line_edit, browse_button

    def _load_config(self):
        if self.controller.config:
            cfg = self.controller.config
            self.initial_robot_port = cfg.get('SERIAL', 'port', fallback="")
            self.initial_robot_baudrate = cfg.get('SERIAL', 'baudrate', fallback="38400")
            self.robot_port.setText(self.initial_robot_port)
            self.robot_baudrate.setCurrentText(self.initial_robot_baudrate)
            self.robot_timeout.setText(cfg.get('SERIAL', 'timeout', fallback="0.5"))
            self.parking_x.setText(cfg.get('CAPSULE_POSITIONS', 'parking_x', fallback=""))
            self.parking_y.setText(cfg.get('CAPSULE_POSITIONS', 'parking_y', fallback=""))
            self.parking_z.setText(cfg.get('CAPSULE_POSITIONS', 'parking_z', fallback=""))
            self.parking_theta.setText(cfg.get('CAPSULE_POSITIONS', 'parking_theta', fallback=""))
            self.parking_phi.setText(cfg.get('CAPSULE_POSITIONS', 'parking_phi', fallback=""))
            self.jog_xy_speed.setText(cfg.get('ROBOT_SPEEDS', 'jog_xy_mm_s', fallback="92"))
            self.jog_z_speed.setText(cfg.get('ROBOT_SPEEDS', 'jog_z_mm_s', fallback="55"))
            self.jog_rot_speed.setText(cfg.get('ROBOT_SPEEDS', 'jog_rot_deg_s', fallback="65"))
            self.seq_activer_securite.setChecked(
                cfg.getboolean('SEQUENCE', 'activer_securite_deplacement', fallback=True))
            self.seq_hauteur_securite.setText(cfg.get('SEQUENCE', 'hauteur_securite_deplacement_z', fallback="20.0"))
            self.seq_temps_stabilisation.setText(cfg.get('SEQUENCE', 'temps_stabilisation_s', fallback="0.5"))
            self.ratio_x.setText(cfg.get('RATIOS', 'x', fallback=""))
            self.ratio_y.setText(cfg.get('RATIOS', 'y', fallback=""))
            self.ratio_z.setText(cfg.get('RATIOS', 'z', fallback=""))
            self.ratio_theta.setText(cfg.get('RATIOS', 'theta', fallback=""))
            self.ratio_phi.setText(cfg.get('RATIOS', 'phi', fallback=""))
            self.accel.setText(cfg.get('ROBOT_SPEEDS', 'accel_steps_s2', fallback=""))
            self.decel.setText(cfg.get('ROBOT_SPEEDS', 'decel_steps_s2', fallback=""))
            self.corr_theta_x.setText(cfg.get('OFFSETS', 'correction_theta_x', fallback=""))
            self.corr_theta_y.setText(cfg.get('OFFSETS', 'correction_theta_y', fallback=""))
            self.corr_theta_z.setText(cfg.get('OFFSETS', 'correction_theta_z', fallback=""))
            self.corr_phi_l.setText(cfg.get('OFFSETS', 'correction_phi_l', fallback=""))

        if self.controller.pulse_config:
            p_cfg = self.controller.pulse_config
            self.initial_pulse_project = p_cfg.get('PulseSettings', 'project_path', fallback="")
            self.pulse_project_path_edit.setText(self.initial_pulse_project)
            self.pulse_save_dir_edit.setText(p_cfg.get('PulseSettings', 'save_path_dir', fallback=""))
            self.pulse_fg_name.setText(p_cfg.get('PulseSettings', 'function_group_to_save', fallback=""))

    def _ensure_sections(self, cfg, sections):
        for section in sections:
            if not cfg.has_section(section):
                cfg.add_section(section)

    def _save_config(self) -> bool:
        restart_needed = False
        if self.robot_port.text() != self.initial_robot_port or \
                self.robot_baudrate.currentText() != self.initial_robot_baudrate or \
                self.pulse_project_path_edit.text() != self.initial_pulse_project:
            restart_needed = True

        try:
            robot_cfg = self.controller.config
            if not robot_cfg: robot_cfg = configparser.ConfigParser()
            self._ensure_sections(robot_cfg,
                                  ['SERIAL', 'CAPSULE_POSITIONS', 'SEQUENCE', 'RATIOS', 'ROBOT_SPEEDS', 'OFFSETS'])

            robot_cfg.set('SERIAL', 'port', self.robot_port.text())
            robot_cfg.set('SERIAL', 'baudrate', self.robot_baudrate.currentText())
            robot_cfg.set('SERIAL', 'timeout', self.robot_timeout.text())
            robot_cfg.set('CAPSULE_POSITIONS', 'parking_x', self.parking_x.text())
            robot_cfg.set('CAPSULE_POSITIONS', 'parking_y', self.parking_y.text())
            robot_cfg.set('CAPSULE_POSITIONS', 'parking_z', self.parking_z.text())
            robot_cfg.set('CAPSULE_POSITIONS', 'parking_theta', self.parking_theta.text())
            robot_cfg.set('CAPSULE_POSITIONS', 'parking_phi', self.parking_phi.text())
            robot_cfg.set('SEQUENCE', 'activer_securite_deplacement',
                          'yes' if self.seq_activer_securite.isChecked() else 'no')
            robot_cfg.set('SEQUENCE', 'hauteur_securite_deplacement_z', self.seq_hauteur_securite.text())
            robot_cfg.set('SEQUENCE', 'temps_stabilisation_s', self.seq_temps_stabilisation.text())
            robot_cfg.set('RATIOS', 'x', self.ratio_x.text())
            robot_cfg.set('RATIOS', 'y', self.ratio_y.text())
            robot_cfg.set('RATIOS', 'z', self.ratio_z.text())
            robot_cfg.set('RATIOS', 'theta', self.ratio_theta.text())
            robot_cfg.set('RATIOS', 'phi', self.ratio_phi.text())
            robot_cfg.set('ROBOT_SPEEDS', 'jog_xy_mm_s', self.jog_xy_speed.text())
            robot_cfg.set('ROBOT_SPEEDS', 'jog_z_mm_s', self.jog_z_speed.text())
            robot_cfg.set('ROBOT_SPEEDS', 'jog_rot_deg_s', self.jog_rot_speed.text())
            robot_cfg.set('ROBOT_SPEEDS', 'accel_steps_s2', self.accel.text())
            robot_cfg.set('ROBOT_SPEEDS', 'decel_steps_s2', self.decel.text())
            robot_cfg.set('OFFSETS', 'correction_theta_x', self.corr_theta_x.text())
            robot_cfg.set('OFFSETS', 'correction_theta_y', self.corr_theta_y.text())
            robot_cfg.set('OFFSETS', 'correction_theta_z', self.corr_theta_z.text())
            robot_cfg.set('OFFSETS', 'correction_phi_l', self.corr_phi_l.text())

            pulse_cfg = self.controller.pulse_config
            if not pulse_cfg: pulse_cfg = configparser.ConfigParser()
            self._ensure_sections(pulse_cfg, ['PulseSettings'])

            pulse_cfg.set('PulseSettings', 'project_path', self.pulse_project_path_edit.text())
            pulse_cfg.set('PulseSettings', 'save_path_dir', self.pulse_save_dir_edit.text())
            pulse_cfg.set('PulseSettings', 'function_group_to_save', self.pulse_fg_name.text())

            self.controller.save_all_configurations()

            if restart_needed:
                QMessageBox.warning(self, "Redémarrage nécessaire",
                                    "Configuration sauvegardée.\n\nCertaines modifications (port, baudrate, projet PULSE) nécessitent un redémarrage complet de l'application pour être prises en compte.")
            else:
                QMessageBox.information(self, "Succès",
                                        "Configuration sauvegardée.\nLes modifications ont été appliquées.")

            return True
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder la configuration : {e}")
            return False

    def accept(self):
        if self._save_config():
            super().accept()