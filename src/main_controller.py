# src/main_controller.py

import logging
import configparser
import threading  # Import du module de threading
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer, Slot

from src.controller_interface.GalilDriver import RobotController, GalilDriver
from src.data_manager import PointManager
from src.sequence_manager.sequence_manager import SequenceManager


def get_config():
    """Trouve, charge et retourne l'objet de configuration et son chemin."""
    controller_file_path = Path(__file__).resolve()
    config_path = controller_file_path.parent / 'controller_interface' / 'config.ini'

    config = configparser.ConfigParser()
    if not config.read(config_path):
        raise FileNotFoundError(f"Fichier de configuration introuvable à {config_path}")

    return config, str(config_path)


class MainController(QObject):
    """Chef d'orchestre de l'application."""

    # --- Signaux pour informer la GUI ---
    log_message_sent = Signal(str)
    robot_position_updated = Signal(dict)
    point_list_changed = Signal(list)
    document_modified_status_changed = Signal(bool)
    sequence_status_changed = Signal(str)
    highlight_point_in_gui = Signal(int)

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("RobotApp.MainController")

        # --- Attributs ---
        self.point_manager = PointManager()
        self.current_file_path = None
        self._is_modified = False
        self.sequence_thread = None

        # --- AJOUT DU VERROU ---
        self.robot_lock = threading.Lock()

        try:
            self.config, self.config_path = get_config()
            self.logger.info(f"Configuration chargée depuis : {self.config_path}")

            driver = GalilDriver(
                port=self.config.get('SERIAL', 'port'),
                baudrate=self.config.getint('SERIAL', 'baudrate'),
                timeout=self.config.getfloat('SERIAL', 'timeout')
            )
            self.robot = RobotController(driver, self.config)

            self.position_timer = QTimer(self)
            self.position_timer.setInterval(500)
            self.position_timer.timeout.connect(self.poll_robot_position)

            self.connect_robot()

        except Exception as e:
            self.logger.critical(f"ERREUR CRITIQUE AU DÉMARRAGE : {e}", exc_info=True)
            self.log_message_sent.emit(f"ERREUR CRITIQUE : {e}")
            self.config = None
            self.robot = None

    @property
    def is_modified(self):
        return self._is_modified

    @is_modified.setter
    def is_modified(self, value: bool):
        if self._is_modified != value:
            self._is_modified = value
            self.document_modified_status_changed.emit(value)

    def _notify_point_list_changed(self):
        """Méthode privée pour émettre le signal de mise à jour de la liste."""
        self.is_modified = True
        self.point_list_changed.emit(self.point_manager.get_points_as_list_of_dicts())
        self.log_message_sent.emit("Liste de points mise à jour.")

    @Slot()
    def poll_robot_position(self):
        """Méthode appelée par le QTimer pour rafraîchir la position."""
        if self.robot and self.robot.driver.is_connected:
            if self.robot_lock.acquire(blocking=False):
                try:
                    positions = self.robot.update_positions()
                    if positions:
                        self.robot_position_updated.emit(positions)
                finally:
                    self.robot_lock.release()
            else:
                self.logger.debug("Le verrou du robot est occupé, la mise à jour de la position est ignorée.")

    def connect_robot(self):
        """Tente de connecter le robot et d'activer les moteurs."""
        if not self.robot:
            self.log_message_sent.emit("Contrôleur robot non initialisé.")
            return

        if self.robot.connect():
            self.log_message_sent.emit("Robot connecté avec succès.")
            self.robot.enable_motors()
            self.log_message_sent.emit("Moteurs du robot activés.")
            self.position_timer.start()
        else:
            self.log_message_sent.emit("ERREUR: Impossible de se connecter au robot.")

    def disconnect_robot(self):
        """Déconnecte proprement le robot."""
        self.stop_sequence()
        self.position_timer.stop()
        if self.robot and self.robot.driver.is_connected:
            self.robot.disable_motors()
            self.robot.disconnect()
            self.log_message_sent.emit("Robot déconnecté.")

    def process_loaded_file(self, file_path: str):
        """Logique de chargement appelée par la GUI après sélection d'un fichier."""
        if self.point_manager.load_from_file(file_path):
            self.current_file_path = file_path
            self.log_message_sent.emit(f"Fichier '{Path(file_path).name}' chargé.")
            self.point_list_changed.emit(self.point_manager.get_points_as_list_of_dicts())
            self.is_modified = False
        else:
            self.log_message_sent.emit("Erreur lors du chargement du fichier de points.")
            self.point_list_changed.emit([])

    def get_point_headers(self) -> list:
        """Retourne la liste ordonnée des en-têtes de colonnes."""
        return self.point_manager.headers if self.point_manager else []

    def save_point_list(self) -> bool:
        """Tente de sauvegarder dans le fichier actuel. Renvoie False s'il n'y a pas de chemin."""
        if self.current_file_path:
            return self.save_point_list_to_file(self.current_file_path)
        else:
            self.log_message_sent.emit("Aucun fichier de destination, utiliser 'Enregistrer sous'.")
            return False

    def save_point_list_to_file(self, file_path: str) -> bool:
        """Sauvegarde la liste de points vers un chemin spécifique."""
        if self.point_manager.save_to_file(file_path):
            self.current_file_path = file_path
            self.log_message_sent.emit(f"Fichier '{Path(file_path).name}' sauvegardé.")
            self.is_modified = False
            return True
        else:
            self.log_message_sent.emit("Erreur lors de la sauvegarde du fichier.")
            return False

    @Slot()
    def add_new_point(self):
        """Ajoute un nouveau point vide à la fin de la liste."""
        self.point_manager.add_point()
        self._notify_point_list_changed()

    @Slot(list)
    def delete_selected_points(self, indices: list[int]):
        """Supprime les points dont les indices sont fournis par la GUI."""
        self.point_manager.delete_points(indices)
        self._notify_point_list_changed()

    @Slot(int)
    def move_selected_point_up(self, index: int):
        """Déplace le point sélectionné vers le haut."""
        self.point_manager.move_point_up(index)
        self._notify_point_list_changed()

    @Slot(int)
    def move_selected_point_down(self, index: int):
        """Déplace le point sélectionné vers le bas."""
        self.point_manager.move_point_down(index)
        self._notify_point_list_changed()

    @Slot()
    def start_sequence(self):
        """Lance la séquence de mesure automatique."""
        if self.sequence_thread and self.sequence_thread.isRunning():
            self.log_message_sent.emit("Une séquence est déjà en cours.")
            return

        points = self.point_manager.points
        if not points:
            self.log_message_sent.emit("Impossible de démarrer : la liste de points est vide.")
            return

        self.log_message_sent.emit("Démarrage de la séquence de mesure...")
        self.sequence_thread = SequenceManager(self.robot, None, points)

        self.sequence_thread.active_point_changed.connect(self.highlight_point_in_gui)

        self.sequence_thread.context['robot_lock'] = self.robot_lock

        self.sequence_thread.status_changed.connect(self.sequence_status_changed)
        self.sequence_thread.finished.connect(self.on_sequence_finished)

        self.sequence_thread.start()

    @Slot()
    def stop_sequence(self):
        """Arrête la séquence en cours."""
        if self.sequence_thread and self.sequence_thread.isRunning():
            self.sequence_thread.stop()
        else:
            self.log_message_sent.emit("Aucune séquence en cours.")

    @Slot()
    def on_sequence_finished(self):
        """Slot appelé quand le thread de la séquence se termine."""
        self.log_message_sent.emit("Le thread de la séquence s'est terminé.")
        self.sequence_thread = None

    def move_robot_to_parking(self):
        """Slot pour le bouton 'Aller au parking'."""
        if not self.robot: return
        self.log_message_sent.emit("Déplacement vers la position de parking...")
        with self.robot_lock:
            self.robot.go_to_parking()
        self.log_message_sent.emit("Position de parking atteinte.")

    def set_robot_parking_position(self):
        """Slot pour le menu 'Définir Parking' dans la télécommande."""
        if not self.robot or not self.config: return
        with self.robot_lock:
            self.robot.update_positions()
            self.robot.set_parking()
        try:
            with open(self.config_path, 'w') as configfile:
                self.config.write(configfile)
            self.log_message_sent.emit("Nouvelle position de parking sauvegardée.")
        except Exception as e:
            self.log_message_sent.emit(f"ERREUR: Impossible de sauvegarder le parking: {e}")
            self.logger.error(f"Impossible de sauvegarder la position de parking dans {self.config_path}: {e}")

    def set_robot_zero_position(self):
        """Slot pour le menu 'Définir Zéro'."""
        if not self.robot: return
        with self.robot_lock:
            self.robot.define_current_position_as_zero()
        self.log_message_sent.emit("Position actuelle définie comme Zéro.")

    def move_robot_relative(self, axis: str, distance: float):
        """Slot pour les boutons de déplacement relatif."""
        if not self.robot: return
        self.log_message_sent.emit(f"Déplacement relatif de {distance} sur l'axe {axis}...")
        with self.robot_lock:
            self.robot.move_relative(**{axis: distance})
        self.log_message_sent.emit(f"Mouvement relatif terminé sur l'axe {axis}.")