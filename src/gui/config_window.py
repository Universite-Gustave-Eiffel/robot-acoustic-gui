# src/gui/config_window.py

import configparser
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout,
    QLineEdit, QDialogButtonBox, QPushButton, QFileDialog,
    QComboBox, QGroupBox, QMessageBox, QLabel
)

from src.main_controller import MainController


class ConfigWindow(QDialog):
    """
    Fenêtre de dialogue pour configurer les paramètres de l'application
    stockés dans les fichiers .ini.
    """

    def __init__(self, controller: MainController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Configuration de l'application")
        self.setMinimumWidth(600)

        # Layout principal
        self.main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        # Création des onglets
        self.robot_tab = QWidget()
        self.pulse_tab = QWidget()
        self.tabs.addTab(self.robot_tab, "Configuration Robot")
        self.tabs.addTab(self.pulse_tab, "Configuration PULSE")

        # Remplissage des onglets avec les widgets
        self._create_robot_tab()
        self._create_pulse_tab()

        # Boutons OK / Annuler
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.main_layout.addWidget(self.button_box)

        # Charger la configuration actuelle dans les widgets
        self._load_config()

    def _create_robot_tab(self):
        """Crée le contenu de l'onglet de configuration du robot."""
        layout = QFormLayout(self.robot_tab)

        # --- Groupe Connexion Série ---
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

        # --- Groupe Vitesses ---
        speeds_group = QGroupBox("Vitesses et Accélérations")
        speeds_layout = QFormLayout(speeds_group)
        self.jog_xy = QLineEdit()
        self.jog_z = QLineEdit()
        self.jog_rot = QLineEdit()
        speeds_layout.addRow("Jog XY (mm/s):", self.jog_xy)
        speeds_layout.addRow("Jog Z (mm/s):", self.jog_z)
        speeds_layout.addRow("Jog Rotation (°/s):", self.jog_rot)
        layout.addWidget(speeds_group)

        # --- NOUVEAU : Groupe Corrections de position ---
        offsets_group = QGroupBox("Corrections de position (cinématique capsule)")
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

    def _create_pulse_tab(self):
        """Crée le contenu de l'onglet de configuration de PULSE."""
        layout = QFormLayout(self.pulse_tab)

        # --- Groupe Chemins d'accès ---
        paths_group = QGroupBox("Chemins d'accès PULSE")
        paths_layout = QFormLayout(paths_group)

        # Création des sélecteurs de fichiers/dossiers
        self.pulse_project_path_edit, self.pulse_project_path_btn = self._create_path_selector(
            is_dir=False, file_filter="Projet PULSE (*.pls)"
        )
        paths_layout.addRow(QLabel("Projet PULSE (.pls):"), self.pulse_project_path_edit)
        paths_layout.addRow("", self.pulse_project_path_btn)

        self.pulse_save_dir_edit, self.pulse_save_dir_btn = self._create_path_selector(is_dir=True)
        paths_layout.addRow(QLabel("Répertoire de sauvegarde :"), self.pulse_save_dir_edit)
        paths_layout.addRow("", self.pulse_save_dir_btn)

        self.pulse_log_dir_edit, self.pulse_log_dir_btn = self._create_path_selector(is_dir=True)
        paths_layout.addRow(QLabel("Répertoire de logs :"), self.pulse_log_dir_edit)
        paths_layout.addRow("", self.pulse_log_dir_btn)

        self.pulse_fg_name = QLineEdit()
        paths_layout.addRow(QLabel("FunctionGroup à sauver :"), self.pulse_fg_name)

        layout.addWidget(paths_group)

    def _create_path_selector(self, is_dir=False, file_filter="Tous les fichiers (*)"):
        """Fonction utilitaire pour créer un QLineEdit avec un bouton 'Parcourir...'."""
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
        """Charge la configuration actuelle depuis le controller dans les widgets."""
        # Config Robot
        if self.controller.config:
            # SERIAL
            self.robot_port.setText(self.controller.config.get('SERIAL', 'port', fallback=""))
            self.robot_baudrate.setCurrentText(self.controller.config.get('SERIAL', 'baudrate', fallback="38400"))
            self.robot_timeout.setText(self.controller.config.get('SERIAL', 'timeout', fallback="0.5"))
            # SPEEDS
            self.jog_xy.setText(self.controller.config.get('ROBOT_SPEEDS', 'jog_xy_mm_s', fallback=""))
            self.jog_z.setText(self.controller.config.get('ROBOT_SPEEDS', 'jog_z_mm_s', fallback=""))
            self.jog_rot.setText(self.controller.config.get('ROBOT_SPEEDS', 'jog_rot_deg_s', fallback=""))
            # NOUVEAU : OFFSETS
            self.corr_theta_x.setText(self.controller.config.get('OFFSETS', 'correction_theta_x', fallback=""))
            self.corr_theta_y.setText(self.controller.config.get('OFFSETS', 'correction_theta_y', fallback=""))
            self.corr_theta_z.setText(self.controller.config.get('OFFSETS', 'correction_theta_z', fallback=""))
            self.corr_phi_l.setText(self.controller.config.get('OFFSETS', 'correction_phi_l', fallback=""))

        # Config PULSE
        if self.controller.pulse_config:
            self.pulse_project_path_edit.setText(
                self.controller.pulse_config.get('PulseSettings', 'project_path', fallback=""))
            self.pulse_save_dir_edit.setText(
                self.controller.pulse_config.get('PulseSettings', 'save_path_dir', fallback=""))
            self.pulse_log_dir_edit.setText(self.controller.pulse_config.get('PulseSettings', 'log_dir', fallback=""))
            self.pulse_fg_name.setText(
                self.controller.pulse_config.get('PulseSettings', 'function_group_to_save', fallback=""))

    def _save_config(self):
        """Sauvegarde les valeurs des widgets dans les objets de configuration du controller."""
        try:
            # Config Robot
            robot_cfg = self.controller.config
            if not robot_cfg: robot_cfg = configparser.ConfigParser()
            if not robot_cfg.has_section('SERIAL'): robot_cfg.add_section('SERIAL')
            if not robot_cfg.has_section('ROBOT_SPEEDS'): robot_cfg.add_section('ROBOT_SPEEDS')
            if not robot_cfg.has_section('OFFSETS'): robot_cfg.add_section('OFFSETS')  # NOUVEAU

            robot_cfg.set('SERIAL', 'port', self.robot_port.text())
            robot_cfg.set('SERIAL', 'baudrate', self.robot_baudrate.currentText())
            robot_cfg.set('SERIAL', 'timeout', self.robot_timeout.text())
            robot_cfg.set('ROBOT_SPEEDS', 'jog_xy_mm_s', self.jog_xy.text())
            robot_cfg.set('ROBOT_SPEEDS', 'jog_z_mm_s', self.jog_z.text())
            robot_cfg.set('ROBOT_SPEEDS', 'jog_rot_deg_s', self.jog_rot.text())
            # NOUVEAU
            robot_cfg.set('OFFSETS', 'correction_theta_x', self.corr_theta_x.text())
            robot_cfg.set('OFFSETS', 'correction_theta_y', self.corr_theta_y.text())
            robot_cfg.set('OFFSETS', 'correction_theta_z', self.corr_theta_z.text())
            robot_cfg.set('OFFSETS', 'correction_phi_l', self.corr_phi_l.text())

            # Config PULSE
            pulse_cfg = self.controller.pulse_config
            if not pulse_cfg: pulse_cfg = configparser.ConfigParser()
            if not pulse_cfg.has_section('PulseSettings'): pulse_cfg.add_section('PulseSettings')

            pulse_cfg.set('PulseSettings', 'project_path', self.pulse_project_path_edit.text())
            pulse_cfg.set('PulseSettings', 'save_path_dir', self.pulse_save_dir_edit.text())
            pulse_cfg.set('PulseSettings', 'log_dir', self.pulse_log_dir_edit.text())
            pulse_cfg.set('PulseSettings', 'function_group_to_save', self.pulse_fg_name.text())

            # Appeler le controller pour écrire les fichiers sur le disque
            self.controller.save_all_configurations()

            QMessageBox.information(self, "Succès",
                                    "Configuration sauvegardée.\nCertaines modifications nécessiteront un redémarrage de l'application.")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder la configuration : {e}")
            return False

    def accept(self):
        """S'exécute lorsque l'utilisateur clique sur OK."""
        if self._save_config():
            super().accept()