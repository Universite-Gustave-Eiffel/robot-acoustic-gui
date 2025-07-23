# src/main_controller.py

import logging
import configparser
import threading
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, QCoreApplication, QTimer

from src.labshop_interface.PulseLabshopDriver import PulseLabshopDriver
from src.controller_interface.GalilDriver import RobotController, GalilDriver
from src.data_manager import PointManager, Point
from src.sequence_manager.sequence_manager import SequenceManager


def get_config(interface_name: str):
    """Trouve, charge et retourne l'objet de configuration pour une interface donnée."""
    controller_file_path = Path(__file__).resolve()
    config_path = controller_file_path.parent / interface_name / 'config.ini'

    config = configparser.ConfigParser()
    if not config.read(config_path, encoding='utf-8'):
        raise FileNotFoundError(f"Fichier de configuration introuvable à {config_path}")
    return config, str(config_path)


class MainController(QObject):
    """Chef d'orchestre de l'application. Gère les drivers et la logique métier."""

    log_message_sent = Signal(str)
    robot_position_updated = Signal(dict)
    robot_move_completed = Signal(dict)

    point_list_changed = Signal(list)
    document_modified_status_changed = Signal(bool)
    sequence_status_changed = Signal(str)
    highlight_point_in_gui = Signal(int)

    measure_action_completed = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("RobotApp.MainController")
        self.point_manager = PointManager()
        self.current_file_path = None
        self._is_modified = False

        self.robot: RobotController | None = None
        self.config = None
        self.robot_config_path = None

        self.pulse = None
        self.pulse_config = None

        self.position_timer = QTimer(self)
        self.position_timer.setInterval(500)
        self.position_timer.timeout.connect(self.poll_robot_position)

        self.sequence_thread = None
        self.robot_lock = threading.Lock()
        self.pulse_lock = threading.Lock()

    def setup_robot(self):
        try:
            self.config, self.robot_config_path = get_config('controller_interface')
            self.logger.info(f"Configuration robot chargée depuis : {self.robot_config_path}")
            driver = GalilDriver(
                port=self.config.get('SERIAL', 'port'),
                baudrate=self.config.getint('SERIAL', 'baudrate'),
                timeout=self.config.getfloat('SERIAL', 'timeout')
            )
            self.robot = RobotController(driver, self.config)
            self.connect_robot()
        except Exception as e:
            self.logger.critical(f"ERREUR CRITIQUE DÉMARRAGE ROBOT : {e}", exc_info=True)
            self.log_message_sent.emit(f"ERREUR CRITIQUE ROBOT : {e}")
            self.robot = None

    def setup_pulse(self):
        try:
            pulse_config_obj, _ = get_config('labshop_interface')
            self.pulse_config = pulse_config_obj
            self.pulse = PulseLabshopDriver(
                project_path=self.pulse_config.get('PulseSettings', 'project_path'),
                save_path_dir=self.pulse_config.get('PulseSettings', 'save_path_dir'),
                function_group_name_to_save=self.pulse_config.get('PulseSettings', 'function_group_to_save'),
                log_dir=self.pulse_config.get('PulseSettings', 'log_dir')
            )
            if self.pulse.initialize_pulse():
                self.log_message_sent.emit("Interface PULSE LabShop initialisée avec succès.")
            else:
                self.log_message_sent.emit("AVERTISSEMENT: Échec de l'initialisation de PULSE.")
                self.pulse = None
        except Exception as e:
            self.logger.critical(f"ERREUR CRITIQUE DÉMARRAGE PULSE : {e}", exc_info=True)
            self.log_message_sent.emit(f"ERREUR CRITIQUE PULSE : {e}")
            self.pulse = None

    @property
    def is_modified(self):
        return self._is_modified

    @Slot(bool)
    def set_document_modified(self, value: bool):
        if self._is_modified != value:
            self._is_modified = value
            self.document_modified_status_changed.emit(value)

    def _notify_point_list_changed(self):
        self.set_document_modified(True)
        self.point_list_changed.emit(self.point_manager.get_points_as_list_of_dicts())
        self.log_message_sent.emit("Liste de points mise à jour.")

    @Slot()
    def poll_robot_position(self):
        if self.robot and self.robot.driver.is_connected:
            if self.robot_lock.acquire(blocking=False):
                try:
                    positions = self.robot.update_positions()
                    if positions:
                        self.robot_position_updated.emit(positions)
                finally:
                    self.robot_lock.release()

    def connect_robot(self):
        if not self.robot: return
        if self.robot.connect():
            self.log_message_sent.emit("Robot connecté avec succès.")
            self.robot.enable_motors()
            self.log_message_sent.emit("Moteurs du robot activés.")
            if self.position_timer: self.position_timer.start()
        else:
            self.log_message_sent.emit("ERREUR: Impossible de se connecter au robot.")

    def disconnect_robot(self):
        self.stop_sequence()
        if self.position_timer: self.position_timer.stop()
        if self.pulse:
            self.pulse.close()
            self.log_message_sent.emit("Interface PULSE fermée.")
        if self.robot and self.robot.driver.is_connected:
            self.robot.disable_motors()
            self.robot.disconnect()
            self.log_message_sent.emit("Robot déconnecté.")

    def sync_points_from_gui(self, table_data: list[dict]):
        self.point_manager.update_from_list_of_dicts(table_data)

    def process_loaded_file(self, file_path: str):
        if self.point_manager.load_from_file(file_path):
            self.current_file_path = file_path
            self.log_message_sent.emit(f"Fichier '{Path(file_path).name}' chargé.")
            self.point_list_changed.emit(self.point_manager.get_points_as_list_of_dicts())
            self.set_document_modified(False)
        else:
            self.log_message_sent.emit("Erreur lors du chargement du fichier de points.")
            self.point_list_changed.emit([])

    def get_point_headers(self) -> list:
        return self.point_manager.headers if self.point_manager else []

    def save_point_list(self) -> bool:
        if self.current_file_path:
            return self.save_point_list_to_file(self.current_file_path)
        return False

    def save_point_list_to_file(self, file_path: str) -> bool:
        if self.point_manager.save_to_file(file_path):
            self.current_file_path = file_path
            self.log_message_sent.emit(f"Fichier '{Path(file_path).name}' sauvegardé.")
            self.set_document_modified(False)
            return True
        return False

    @Slot()
    def add_new_point(self):
        self.point_manager.add_point()
        self._notify_point_list_changed()

    @Slot()
    def add_current_position_as_point(self):
        if not self.robot: return
        with self.robot_lock:
            current_pos = self.robot.last_positions
            if not any(current_pos.values()):
                current_pos = self.robot.update_positions()
            if not current_pos:
                self.log_message_sent.emit("Position actuelle du robot inconnue.")
                return

            new_point = Point(
                x=round(current_pos.get('X', 0.0)),
                y=round(current_pos.get('Y', 0.0)),
                z=round(current_pos.get('Z', 0.0)),
                theta=round(current_pos.get('THETA', 0.0)),
                phi=round(current_pos.get('PHI', 0.0)),
            )
        self.point_manager.add_point(new_point)
        self._notify_point_list_changed()
        self.log_message_sent.emit("Position actuelle ajoutée à la liste de points.")

    @Slot(list)
    def delete_selected_points(self, indices: list[int]):
        self.point_manager.delete_points(indices)
        self._notify_point_list_changed()

    @Slot(int)
    def move_selected_point_up(self, index: int):
        self.point_manager.move_point_up(index)
        self._notify_point_list_changed()

    @Slot(int)
    def move_selected_point_down(self, index: int):
        self.point_manager.move_point_down(index)
        self._notify_point_list_changed()

    @Slot()
    def start_sequence(self):
        if self.sequence_thread and self.sequence_thread.isRunning(): self.log_message_sent.emit(
            "Une séquence est déjà en cours."); return
        if not self.pulse: self.log_message_sent.emit("ERREUR: Interface PULSE non prête."); return
        if not self.pulse_lock.acquire(blocking=False): self.log_message_sent.emit(
            "Interface PULSE occupée par une mesure manuelle."); return
        points = self.point_manager.points
        if not points:
            self.log_message_sent.emit("Impossible de démarrer : la liste de points est vide.")
            self.pulse_lock.release()
            return
        self.log_message_sent.emit("Démarrage de la séquence de mesure...")
        sequence_params = {
            'activer_securite': self.config.getboolean('SEQUENCE', 'activer_securite_deplacement', fallback=True),
            'hauteur_securite_z': self.config.getfloat('SEQUENCE', 'hauteur_securite_deplacement_z', fallback=20.0),
            'temps_stabilisation_s': self.config.getfloat('SEQUENCE', 'temps_stabilisation_s', fallback=0.5)
        }
        self.sequence_thread = SequenceManager(self.robot, self.pulse, points, sequence_params)
        self.sequence_thread.start_measure_requested.connect(self._on_start_measure_requested)
        self.sequence_thread.stop_measure_requested.connect(self._on_stop_measure_requested)
        self.sequence_thread.save_measure_requested.connect(self._on_save_measure_requested)
        self.measure_action_completed.connect(self.sequence_thread.on_measure_action_completed)
        self.sequence_thread.active_point_changed.connect(self.highlight_point_in_gui)
        self.sequence_thread.status_changed.connect(self.sequence_status_changed)
        self.sequence_thread.sequence_completed.connect(self.on_sequence_finished)
        base_name = Path(self.current_file_path).stem if self.current_file_path else "mesure_sans_nom"
        self.sequence_thread.context['base_filename'] = base_name
        self.sequence_thread.context['robot_lock'] = self.robot_lock
        self.sequence_thread.start()

    @Slot()
    def _on_start_measure_requested(self):
        if not self.pulse: self.measure_action_completed.emit(False, "Pulse non initialisé"); return
        if not self.pulse.start_measurement(): self.measure_action_completed.emit(False,
                                                                                  "Impossible de démarrer la mesure PULSE"); return
        self.measure_action_completed.emit(True, "Mesure démarrée")

    @Slot()
    def _on_stop_measure_requested(self):
        if not self.pulse: self.measure_action_completed.emit(False, "Pulse non initialisé"); return
        if not self.pulse.stop_measurement(): self.measure_action_completed.emit(False,
                                                                                 "Impossible d'arrêter la mesure PULSE"); return
        self.measure_action_completed.emit(True, "Mesure arrêtée")

    @Slot(str)
    def _on_save_measure_requested(self, filename):
        if not self.pulse: self.measure_action_completed.emit(False, "Pulse non initialisé"); return
        if not self.pulse.save_function_group_ascii(filename): self.measure_action_completed.emit(False,
                                                                                                  f"Échec de sauvegarde vers {filename}"); return
        self.measure_action_completed.emit(True, filename)

    @Slot()
    def stop_sequence(self):
        if self.sequence_thread and self.sequence_thread.isRunning():
            self.log_message_sent.emit("Demande d'arrêt de la séquence...")
            self.sequence_thread.stop()

    @Slot(str)
    def on_sequence_finished(self, final_message: str):
        self.log_message_sent.emit(f"Séquence terminée. Statut: {final_message}")
        if self.sequence_thread:
            self.point_manager.points = self.sequence_thread.context['points']
            try:
                self.sequence_thread.start_measure_requested.disconnect()
                self.sequence_thread.stop_measure_requested.disconnect()
                self.sequence_thread.save_measure_requested.disconnect()
                self.measure_action_completed.disconnect(self.sequence_thread.on_measure_action_completed)
            except RuntimeError as e:
                self.logger.warning(f"Erreur lors de la déconnexion des signaux : {e}")
        self.sequence_thread = None
        if self.pulse_lock.locked():
            self.pulse_lock.release()
        self.point_list_changed.emit(self.point_manager.get_points_as_list_of_dicts())
        self.set_document_modified(True)

    @Slot()
    def start_manual_measurement(self):
        if not self.pulse: self.log_message_sent.emit("Impossible de mesurer : interface PULSE non prête."); return
        if not self.pulse_lock.acquire(blocking=False): self.log_message_sent.emit(
            "Interface PULSE occupée par la séquence."); return
        try:
            if self.pulse.is_measurement_active: self.log_message_sent.emit(
                "Une mesure manuelle est déjà en cours."); return
            if not self.pulse.is_template_ready_for_measurement and not self.pulse.autorange():
                self.log_message_sent.emit("Échec de l'autorange.")
                return
            self.pulse.start_measurement()
            self.log_message_sent.emit("Mesure manuelle démarrée.")
        finally:
            if self.pulse_lock.locked(): self.pulse_lock.release()

    @Slot(str)
    def save_manual_measurement(self, filename: str):
        if not self.pulse: self.log_message_sent.emit("Impossible de sauvegarder : interface PULSE non prête."); return
        if not self.pulse_lock.acquire(blocking=False): self.log_message_sent.emit(
            "Interface PULSE occupée par la séquence."); return
        try:
            self.pulse.stop_measurement()
            time.sleep(0.5)
            if self.pulse.save_function_group_ascii(filename):
                self.log_message_sent.emit(f"Mesure manuelle sauvegardée dans '{filename}'.")
            else:
                self.log_message_sent.emit("Erreur lors de la sauvegarde de la mesure manuelle.")
        finally:
            if self.pulse_lock.locked(): self.pulse_lock.release()

    @Slot(dict)
    def move_capsule_absolute(self, capsule_coords: dict):
        if not self.robot: return
        self.log_message_sent.emit(f"Déplacement capsule vers : {capsule_coords}")
        threading.Thread(target=self._execute_move_capsule_absolute, args=(capsule_coords,)).start()

    def _execute_move_capsule_absolute(self, capsule_coords):
        if not self.robot: return
        with self.robot_lock:
            robot_coords = self.robot.calculate_robot_coords_for_capsule(**capsule_coords)
            self.robot.move_to(**robot_coords)
        self.log_message_sent.emit("Déplacement capsule terminé.")
        self.robot_move_completed.emit(self.robot.last_positions)

    @Slot(dict)
    def define_robot_position(self, capsule_coords: dict):
        if not self.robot: return
        self.log_message_sent.emit(f"Assignation de la position actuelle aux coordonnées capsule : {capsule_coords}")
        with self.robot_lock:
            try:
                robot_coords = self.robot.calculate_robot_coords_for_capsule(**capsule_coords)
                self.robot.define_position(**robot_coords)
                self.log_message_sent.emit("Position du robot redéfinie avec succès.")
            except Exception as e:
                self.log_message_sent.emit(f"Erreur lors de l'assignation de la position : {e}")

    def move_robot_relative(self, axis: str, distance: float):
        if not self.robot: return
        self.log_message_sent.emit(f"Déplacement relatif de {distance} sur l'axe {axis}...")
        threading.Thread(target=self._execute_move_relative, args=({axis: distance},)).start()

    def _execute_move_relative(self, move_dict):
        if not self.robot: return
        with self.robot_lock:
            self.robot.move_relative(**move_dict)
        axis = list(move_dict.keys())[0]
        self.log_message_sent.emit(f"Mouvement relatif terminé sur l'axe {axis}.")
        self.robot_move_completed.emit(self.robot.last_positions)

    def move_robot_to_parking(self):
        if not self.robot: return
        self.log_message_sent.emit("Déplacement vers la position de parking...")
        threading.Thread(target=self._execute_move_to_parking).start()

    def _execute_move_to_parking(self):
        if not self.robot: return
        with self.robot_lock:
            self.robot.go_to_parking()
        self.log_message_sent.emit("Position de parking atteinte.")
        self.robot_move_completed.emit(self.robot.last_positions)

    def set_robot_parking_position(self):
        if not self.robot or not self.config: return
        with self.robot_lock:
            self.robot.update_positions()
            self.robot.set_parking()
        try:
            with open(self.robot_config_path, 'w', encoding='utf-8') as configfile:
                self.config.write(configfile)
            self.log_message_sent.emit("Nouvelle position de parking sauvegardée.")
        except Exception as e:
            self.log_message_sent.emit(f"ERREUR: Impossible de sauvegarder le parking: {e}")

    def set_robot_zero_position(self):
        if not self.robot: return
        with self.robot_lock:
            self.robot.define_current_position_as_zero()
            self.robot_move_completed.emit(self.robot.last_positions)
        self.log_message_sent.emit("Position actuelle définie comme Zéro.")

    @Slot(str, float)
    def robot_jog_continuous(self, axis: str, speed: float):
        """Démarre ou arrête un mouvement de jogging continu."""
        if not self.robot: return
        # Le jogging est une commande rapide, on ne la met pas dans un thread séparé
        # pour une meilleure réactivité, mais on utilise le lock.
        with self.robot_lock:
            self.robot.jog_continuous(**{axis: speed})

    def save_all_configurations(self):
        try:
            if self.config and self.robot_config_path:
                with open(self.robot_config_path, 'w', encoding='utf-8') as configfile:
                    self.config.write(configfile)
                self.logger.info(f"Configuration robot sauvegardée dans {self.robot_config_path}")

            if self.pulse_config:
                controller_file_path = Path(__file__).resolve()
                pulse_config_path = controller_file_path.parent / 'labshop_interface' / 'config.ini'
                with open(pulse_config_path, 'w', encoding='utf-8') as configfile:
                    self.pulse_config.write(configfile)
                self.logger.info(f"Configuration PULSE sauvegardée dans {pulse_config_path}")

            self.log_message_sent.emit("Configurations sauvegardées avec succès.")
        except Exception as e:
            self.logger.error(f"Erreur lors de la sauvegarde des configurations : {e}", exc_info=True)
            self.log_message_sent.emit(f"ERREUR: Impossible de sauvegarder les configurations: {e}")