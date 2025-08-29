import logging
import configparser
import threading
import time
import os
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, QCoreApplication, QTimer

from src.labshop_interface.PulseLabshopDriver import PulseLabshopDriver
from src.controller_interface.GalilDriver import RobotController, GalilDriver
from src.data_manager import PointManager, Point
from src.sequence_manager.sequence_manager import SequenceManager


def get_config(interface_name: str):
    controller_file_path = Path(__file__).resolve()
    config_path = controller_file_path.parent / interface_name / 'config.ini'
    config = configparser.ConfigParser()
    if not config.read(config_path, encoding='utf-8'):
        raise FileNotFoundError(f"Fichier de configuration introuvable à {config_path}")
    return config, str(config_path)


class MainController(QObject):
    log_message_sent = Signal(str)
    # Émet les coordonnées robot ET les coordonnées capsule
    robot_position_updated = Signal(dict, dict)
    robot_move_completed = Signal(dict,dict)
    point_list_changed = Signal(list)
    document_modified_status_changed = Signal(bool)
    sequence_status_changed = Signal(str)
    highlight_point_in_gui = Signal(int)
    measure_action_completed = Signal(bool, str)
    sequence_finished_with_next_point = Signal(str, int)

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

    def setup_robot(self) -> bool:
        """Prépare l'objet RobotController à partir de la configuration. Ne se connecte pas."""
        try:
            self.config, self.robot_config_path = get_config('controller_interface')
            self.logger.info(f"Configuration robot chargée depuis : {self.robot_config_path}")
            driver = GalilDriver(
                port=self.config.get('SERIAL', 'port'),
                baudrate=self.config.getint('SERIAL', 'baudrate'),
                timeout=self.config.getfloat('SERIAL', 'timeout')
            )
            self.robot = RobotController(driver, self.config)
            return True
        except Exception as e:
            self.logger.critical(f"ERREUR CRITIQUE DÉMARRAGE ROBOT : {e}", exc_info=True)
            self.log_message_sent.emit(f"ERREUR CRITIQUE ROBOT : {e}")
            self.robot = None
            return False

    def setup_pulse(self) -> bool:
        """Prépare et initialise l'interface PULSE. Retourne True en cas de succès."""
        try:
            pulse_config_obj, _ = get_config('labshop_interface')
            self.pulse_config = pulse_config_obj
            self.pulse = PulseLabshopDriver(
                project_path=self.pulse_config.get('PulseSettings', 'project_path'),
                save_path_dir=self.pulse_config.get('PulseSettings', 'save_path_dir'),
                function_group_name_to_save=self.pulse_config.get('PulseSettings', 'function_group_to_save')
            )
            if self.pulse.initialize_pulse():
                self.log_message_sent.emit("Interface PULSE LabShop initialisée avec succès.")
                return True
            else:
                self.log_message_sent.emit("AVERTISSEMENT: Échec de l'initialisation de PULSE. Vérifiez la connexion du boîtier d'acquisition.")
                self.pulse = None
                return False
        except Exception as e:
            self.logger.critical(f"ERREUR CRITIQUE DÉMARRAGE PULSE : {e}", exc_info=True)
            self.log_message_sent.emit(f"ERREUR CRITIQUE PULSE : {e}")
            self.pulse = None
            return False

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
                    robot_pos = self.robot.update_positions()
                    if robot_pos:
                        capsule_pos = self.robot.capsule_pos
                        self.robot_position_updated.emit(robot_pos, capsule_pos)
                finally:
                    self.robot_lock.release()

    def connect_robot(self):
        if not self.robot: return False
        if self.robot.connect():
            self.log_message_sent.emit("Robot connecté avec succès.")
            self.robot.enable_motors()
            self.log_message_sent.emit("Moteurs du robot activés.")
            if self.position_timer: self.position_timer.start()
            return True
        else:
            self.log_message_sent.emit(f"ERREUR: Impossible de se connecter au robot sur le port {self.config.get('SERIAL', 'port')}.")
            return False

    def disconnect_robot(self):
        if self.sequence_thread and self.sequence_thread.isRunning():
            self.emergency_stop()

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

    def create_new_point_list(self):
        """Réinitialise le gestionnaire de points pour une nouvelle liste."""
        self.point_manager.points.clear()
        self.current_file_path = None
        self.log_message_sent.emit("Nouvelle liste de points créée.")

    def add_current_position_as_point(self) -> Point:
        if not self.robot: return None
        with self.robot_lock:
            current_pos = self.robot.update_positions()
            if not current_pos:
                self.log_message_sent.emit("Position actuelle du robot inconnue.")
                return None
            capsule_pos = self.robot.capsule_pos
            new_point = Point(
                x=round(capsule_pos.get('X', 0.0)),
                y=round(capsule_pos.get('Y', 0.0)),
                z=round(capsule_pos.get('Z', 0.0)),
                theta=round(current_pos.get('THETA', 0.0)),
                phi=round(current_pos.get('PHI', 0.0)),
            )
        self.log_message_sent.emit("Position capsule actuelle récupérée.")
        return new_point

    def validate_filenames(self) -> list[int]:
        missing_indices = []
        for i, point in enumerate(self.point_manager.points):
            if not point.measurement_file:
                missing_indices.append(i)
        return missing_indices

    def autofill_filenames(self):
        for i, point in enumerate(self.point_manager.points):
            if not point.measurement_file:
                sanitized_coords = [
                    str(round(c)).replace('-', 'm') for c in
                    [point.x, point.y, point.z, point.theta, point.phi]
                ]
                point.measurement_file = f"point_{i + 1}_{'_'.join(sanitized_coords)}"
        self.log_message_sent.emit("Noms de fichiers auto-remplis.")
        self._notify_point_list_changed()

    def _start_sequence_thread(self, points, start_index=0, single_shot=False):
        if self.sequence_thread and self.sequence_thread.isRunning():
            self.log_message_sent.emit("Une séquence est déjà en cours.")
            return

        if not self.pulse:
            self.log_message_sent.emit("ERREUR: Interface PULSE non prête.")
            return

        if not self.pulse_lock.acquire(blocking=False):
            self.log_message_sent.emit("Interface PULSE occupée.")
            return

        if not points:
            self.log_message_sent.emit("Impossible de démarrer : la liste de points est vide.")
            self.pulse_lock.release()
            return

        if start_index >= len(points):
            self.log_message_sent.emit(f"L'index de départ ({start_index + 1}) est hors limites.")
            self.pulse_lock.release()
            return

        self.log_message_sent.emit(f"Démarrage de la séquence au point {start_index + 1}...")

        sequence_params = {
            'activer_securite_deplacement': self.config.getboolean('SEQUENCE', 'activer_securite_deplacement',
                                                                   fallback=True),
            'hauteur_securite_deplacement_z': self.config.getfloat('SEQUENCE', 'hauteur_securite_deplacement_z',
                                                                   fallback=20.0),
            'temps_stabilisation_s': self.config.getfloat('SEQUENCE', 'temps_stabilisation_s', fallback=0.5)
        }

        self.sequence_thread = SequenceManager(self.robot, self.pulse, points, sequence_params, single_shot)
        self.sequence_thread.context['current_index'] = start_index

        self.sequence_thread.sequence_completed.connect(self.on_sequence_finished)
        self.sequence_thread.start_measure_requested.connect(self._on_start_measure_requested)
        self.sequence_thread.save_measure_requested.connect(self._on_save_measure_requested)
        self.sequence_thread.stop_robot_requested.connect(self.robot.stop_all_motion)
        self.measure_action_completed.connect(self.sequence_thread.on_measure_action_completed)
        self.sequence_thread.active_point_changed.connect(self.highlight_point_in_gui)
        self.sequence_thread.status_changed.connect(self.sequence_status_changed)

        base_name = Path(self.current_file_path).stem if self.current_file_path else "mesure"
        self.sequence_thread.context['base_filename'] = base_name
        self.sequence_thread.context['robot_lock'] = self.robot_lock

        self.sequence_thread.start()

    @Slot(int)
    def start_full_sequence(self, start_index: int = 0):
        points_copy = self.point_manager.get_points_copy()
        self._start_sequence_thread(points_copy, start_index, single_shot=False)

    @Slot(int)
    def start_single_point_sequence(self, index: int):
        points_copy = self.point_manager.get_points_copy()
        self._start_sequence_thread(points_copy, index, single_shot=True)

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
    def _on_save_measure_requested(self, filename: str):
        """Exécute une demande de sauvegarde unique et atomique pour la FSM."""
        if not self.pulse:
            self.measure_action_completed.emit(False, "Pulse non initialisé")
            return

        # S'assurer que le nom de fichier a une extension (mesure de sécurité)
        base, ext = os.path.splitext(filename)
        if not ext:
            filename = f"{base}.txt"

        success = self.pulse.save_function_group_ascii(filename)

        if success:
            saved_filename = f"Sauvegarde réussie : {filename}"
        else:
            saved_filename = f"Échec de sauvegarde vers {filename}"

        self.measure_action_completed.emit(success, saved_filename)

    @Slot()
    def stop_sequence(self):
        if self.sequence_thread and self.sequence_thread.isRunning():
            self.log_message_sent.emit("Demande d'arrêt (doux) de la séquence...")
            self.sequence_thread.stop()

    @Slot()
    def toggle_pause_sequence(self):
        if self.sequence_thread and self.sequence_thread.isRunning():
            self.sequence_thread.toggle_pause()

    @Slot()
    def emergency_stop(self):
        self.log_message_sent.emit("ARRÊT D'URGENCE DÉCLENCHÉ !")
        if self.sequence_thread and self.sequence_thread.isRunning():
            self.sequence_thread.stop()
        if self.robot:
            threading.Thread(target=self.robot.abort_all_motion, daemon=True).start()
        if self.pulse_lock.locked():
            self.pulse_lock.release()

    @Slot(str, int)
    def on_sequence_finished(self, final_message: str, next_point_index: int):
        self.log_message_sent.emit(f"Séquence terminée. Statut: {final_message}")
        self.sequence_finished_with_next_point.emit(final_message, next_point_index)

        if self.sequence_thread:
            try:
                self.sequence_thread.start_measure_requested.disconnect()
                self.sequence_thread.save_measure_requested.disconnect()
                self.sequence_thread.stop_robot_requested.disconnect()
                self.measure_action_completed.disconnect(self.sequence_thread.on_measure_action_completed)
            except RuntimeError as e:
                self.logger.warning(f"Erreur lors de la déconnexion des signaux : {e}")
        self.sequence_thread = None
        if self.pulse_lock.locked():
            self.pulse_lock.release()

    @Slot()
    def start_manual_measurement(self):
        if not self.pulse:
            self.log_message_sent.emit("Impossible de mesurer : interface PULSE non prête.")
            return

        if not self.pulse_lock.acquire(blocking=False):
            self.log_message_sent.emit("Interface PULSE occupée.")
            return

        try:
            if self.pulse.is_measurement_active:
                self.log_message_sent.emit("Une mesure est déjà en cours.")
                return

            self.log_message_sent.emit("Démarrage mesure manuelle...")
            if not self.pulse.is_template_ready_for_measurement:
                self.log_message_sent.emit("Autorange nécessaire...")
                if not self.pulse.autorange():
                    self.log_message_sent.emit("Échec de l'autorange.")
                    return

            if not self.pulse.start_measurement():
                self.log_message_sent.emit("Erreur lors du démarrage de la mesure manuelle.")
            else:
                self.log_message_sent.emit("Mesure manuelle démarrée.")

        finally:
            if self.pulse_lock.locked():
                self.pulse_lock.release()


    @Slot(str)
    def save_manual_measurement(self, filename: str):
        if not self.pulse: self.log_message_sent.emit("Impossible de sauvegarder : interface PULSE non prête."); return
        if not self.pulse_lock.acquire(blocking=False): self.log_message_sent.emit("Interface PULSE occupée."); return
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
        self.robot_move_completed.emit(self.robot.robot_pos, self.robot.capsule_pos)

    @Slot(dict)
    def move_to_point_data(self, point_data: dict):
        if not self.robot:
            self.log_message_sent.emit("ERREUR: Le robot n'est pas connecté.")
            return
        if self.sequence_thread and self.sequence_thread.isRunning():
            self.log_message_sent.emit("Veuillez arrêter la séquence avant de lancer un mouvement manuel.")
            return
        capsule_coords = {
            'X': float(point_data.get('x', 0.0)),
            'Y': float(point_data.get('y', 0.0)),
            'Z': float(point_data.get('z', 0.0)),
            'THETA': float(point_data.get('theta', 0.0)),
            'PHI': float(point_data.get('phi', 0.0))
        }
        self.move_capsule_absolute(capsule_coords)

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
            self.robot.update_positions()
        axis = list(move_dict.keys())[0]
        self.log_message_sent.emit(f"Mouvement relatif terminé sur l'axe {axis}.")
        self.robot_move_completed.emit(self.robot.robot_pos, self.robot.capsule_pos)

    def move_robot_to_parking(self):
        if not self.robot: return
        self.log_message_sent.emit("Déplacement vers la position de parking...")
        threading.Thread(target=self._execute_move_to_parking).start()

    def _execute_move_to_parking(self):
        if not self.robot: return
        with self.robot_lock:
            self.robot.go_to_parking()
        self.log_message_sent.emit("Position de parking atteinte.")
        self.robot_move_completed.emit(self.robot.robot_pos, self.robot.capsule_pos)

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
        capsule_zero_coords = {'X': 0.0, 'Y': 0.0, 'Z': 0.0, 'THETA': 0.0, 'PHI': 0.0}
        self.log_message_sent.emit("Assignation de la position actuelle aux coordonnées capsule Zéro.")
        with self.robot_lock:
            try:
                robot_coords_for_zero = self.robot.calculate_robot_coords_for_capsule(**capsule_zero_coords)
                self.robot.define_position(**robot_coords_for_zero)
                self.robot.update_positions()
                self.robot_move_completed.emit(self.robot.robot_pos, self.robot.capsule_pos)
                self.log_message_sent.emit("Position actuelle définie comme Zéro Capsule.")
            except Exception as e:
                self.log_message_sent.emit(f"Erreur lors de l'assignation de la position Zéro : {e}")

    @Slot()
    def robot_jog_continuous(self, **kwargs):
        if not self.robot: return
        with self.robot_lock:
            self.robot.jog_continuous(**kwargs)

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

    @Slot()
    def toggle_pulse_visibility(self):
        """Affiche ou cache la fenêtre de l'application PULSE LabShop."""
        if not self.pulse or not self.pulse.pulse_app:
            self.log_message_sent.emit("ERREUR: L'interface PULSE n'est pas connectée.")
            return

        try:
            # On inverse l'état de visibilité actuel
            is_visible = self.pulse.pulse_app.Visible
            self.pulse.pulse_app.Visible = not is_visible

            new_state = "affichée" if not is_visible else "cachée"
            self.log_message_sent.emit(f"Fenêtre PULSE LabShop {new_state}.")
        except Exception as e:
            self.logger.error(f"Erreur lors du changement de visibilité de PULSE : {e}")
            self.log_message_sent.emit("ERREUR: Impossible de contrôler la fenêtre PULSE.")