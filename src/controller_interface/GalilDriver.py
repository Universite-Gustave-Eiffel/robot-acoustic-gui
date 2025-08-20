# src/controller_interface/GalilDriver.py

import serial
import time
import logging
import configparser
import math
import os

# --- Constantes ---
AXIS_X_GANTRY_MASTER, AXIS_X_GANTRY_SLAVE = 'A', 'B'
AXIS_Y_TABLE, AXIS_Z_VERTICAL = 'C', 'D'
AXIS_THETA_ROTATION, AXIS_PHI_TILT = 'E', 'F'
ALL_AXES_PHYSICAL = "ABCDEF"
AXES_ORDER = ['A', 'B', 'C', 'D', 'E', 'F']


class GalilDriver:
    def __init__(self, port, baudrate, timeout):
        self.port_name, self.baud_rate, self.timeout = port, baudrate, timeout
        self.ser, self.is_connected, self.echo_disabled = None, False, False
        self.logger = logging.getLogger("RobotApp.GalilDriver")

    def connect(self):
        try:
            self.logger.info(f"Connexion à {self.port_name} @ {self.baud_rate} bauds...")
            self.ser = serial.Serial(port=self.port_name, baudrate=self.baud_rate, timeout=self.timeout)
            time.sleep(0.5)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            self.ser.write(b'\r\r')
            time.sleep(0.25)
            initial_response = self.ser.read_all()
            if b':' in initial_response or b'?' in initial_response:
                self.is_connected = True
                self._disable_echo()
                self.logger.info(f"Connecté avec succès au Galil sur {self.port_name}.")
                return True
            self.logger.error(f"Prompt Galil non reçu. Reçu: {initial_response!r}")
            if self.ser: self.ser.close()
            return False
        except Exception as e:
            self.logger.error(f"Erreur de connexion: {e}", exc_info=True)
            return False

    def disconnect(self):
        if self.is_connected and self.ser and self.ser.is_open:
            try:
                if self.echo_disabled: self.ser.write(b"EO1\r")
                time.sleep(0.1)
                self.ser.close()
                self.logger.info("Port série fermé.")
            except Exception as e:
                self.logger.error(f"Erreur à la déconnexion: {e}")
        self.is_connected = False

    def _disable_echo(self):
        self.ser.reset_input_buffer()
        self.ser.write(b"EO0\r")
        time.sleep(0.2)
        response_bytes = self.ser.read_all().strip()
        if response_bytes.endswith(b':'):
            self.echo_disabled = True
            self.logger.info("Écho désactivé.")
        else:
            self.logger.warning(f"Réponse inattendue à EO0: {response_bytes!r}.")

    def send_cmd(self, command: str, timeout_override: float = None):
        if not self.is_connected: return None
        self.logger.debug(f"CMD> {command}")
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.ser.write((command + '\r').encode('ascii'))
        time.sleep(0.05)
        original_timeout = self.ser.timeout
        if timeout_override: self.ser.timeout = timeout_override
        try:
            response_bytes = self.ser.read_until(b':')
            response_str = response_bytes.decode('ascii', 'ignore').strip()
            if '?' in response_str: self.logger.warning(f"Erreur Galil pour '{command}': {response_str}")
            self.logger.debug(f"RSP< {response_str!r}")
            return response_str
        finally:
            if timeout_override: self.ser.timeout = original_timeout

    def send_query(self, command: str, retries=2):
        for attempt in range(retries + 1):
            response = self.send_cmd(command)
            if response is not None and command in response:
                response = response.split('\r\n')[-1]

            if response is not None and '?' not in response and response.strip() != '':
                return response.replace(':', '').strip()
            self.logger.info(
                f"Requête '{command}' a retourné une réponse invalide/vide: '{response}'. Tentative {attempt + 1}/{retries + 1}")
            if attempt < retries: time.sleep(0.1 + 0.2 * attempt)
        self.logger.error(f"Échec final de la requête '{command}'.")
        return None

    def get_tp_positions(self, axes_str="ABCDEF"):
        operands = ",".join([f"_TP{ax}" for ax in axes_str])
        response = self.send_query(f"MG {operands}")
        if response:
            try:
                positions = [float(val) for val in response.split()]
                return dict(zip(axes_str, positions))
            except (ValueError, IndexError):
                self.logger.error(f"Erreur parsing _TP, réponse: '{response}'")
        return None


class RobotController:
    AXIS_MAPPING = {'X': 'A', 'Y': 'C', 'Z': 'D', 'THETA': 'E', 'PHI': 'F'}
    AXIS_GANTRY_SLAVE = 'B'
    ALL_AXES = ALL_AXES_PHYSICAL

    def __init__(self, driver: GalilDriver, config: configparser.ConfigParser):
        self.driver = driver
        self.config = config
        self.logger = logging.getLogger("RobotApp.RobotController")
        self.robot_pos = {name: 0.0 for name in self.AXIS_MAPPING.keys()}
        self.capsule_pos = {'X': 0.0, 'Y': 0.0, 'Z': 0.0}
        self.last_positions = {name: 0.0 for name in self.AXIS_MAPPING.keys()}
        self.active_moving_axes = ""

    def connect(self):
        return self.driver.connect()

    def disconnect(self):
        self.driver.disconnect()

    def enable_motors(self):
        self.logger.info("Activation des moteurs...")
        self.driver.send_cmd(f"SH{self.ALL_AXES}")
        self.logger.info("Configuration du Gantry pour les axes A (maître) et B (esclave)...")
        self.driver.send_cmd(f"GA ,{AXIS_X_GANTRY_MASTER}")
        self.driver.send_cmd(f"GR ,-1")
        self.driver.send_cmd(f"GM ,1")
        self.logger.info("Gantry configuré.")

    def disable_motors(self):
        self.driver.send_cmd("ST")
        time.sleep(0.1)
        self.logger.info("Désactivation de tous les moteurs...")
        self.driver.send_cmd("MO")

    def stop_all_motion(self):
        self.logger.warning("Commande ST (Stop) envoyée pour tous les axes.")
        self.driver.send_cmd("ST")
        self.active_moving_axes = ""

    def abort_all_motion(self):
        self.logger.critical("COMMANDE D'ARRÊT D'URGENCE (AB) ENVOYÉE !")
        self.driver.send_cmd("AB")
        self.active_moving_axes = ""

    def reset_jog_mode(self):
        self.logger.info("Réinitialisation de l'état après le mode JOG...")
        self.driver.send_cmd(f"ST {self.ALL_AXES}")
        self.driver.send_cmd(f"MO {self.ALL_AXES}")
        time.sleep(0.5)
        self.driver.send_cmd(f"SH {self.ALL_AXES}")
        self.logger.info("État du servo réinitialisé.")

    def begin_jog_mode(self):
        self.logger.info("Activation du mode JOG...")
        self.driver.send_cmd(f"JG {','.join(['0'] * len(AXES_ORDER))}")
        self.driver.send_cmd(f"BG {self.ALL_AXES}")
        self.logger.info("Mode JOG actif.")

    def jog_continuous(self, **kwargs):
        jg_values = [''] * len(AXES_ORDER)
        for name, speed in kwargs.items():
            name_up = name.upper()
            if name_up in self.AXIS_MAPPING:
                axis_letter = self.AXIS_MAPPING[name_up]
                speed_in_steps = self._to_steps(name_up, speed)
                jg_values[AXES_ORDER.index(axis_letter)] = str(speed_in_steps)
        cmd_jg = f"JG {','.join(jg_values)}"
        self.logger.debug(f"Mise à jour vitesse Jog: {cmd_jg}")
        self.driver.send_cmd(cmd_jg)

    def _to_steps(self, axis_name, value):
        return int(value * self.config.getfloat('RATIOS', axis_name.lower()))

    def _from_steps(self, axis_name, steps):
        ratio = self.config.getfloat('RATIOS', axis_name.lower())
        return steps / ratio if ratio != 0 else 0.0

    def update_positions(self):
        raw_steps = self.driver.get_tp_positions(self.ALL_AXES)
        if raw_steps:
            for name, letter in self.AXIS_MAPPING.items():
                self.robot_pos[name] = self._from_steps(name, raw_steps.get(letter, 0))
            self._calculate_capsule_position()
            self.last_positions = self.robot_pos.copy()
            return self.robot_pos
        self.logger.warning("Impossible de mettre à jour les positions (réponse nulle du driver).")
        return None

    def _calculate_capsule_position(self):
        """
        Calcule la position de la capsule à partir de la position du robot.
        Équations alignées sur l'ancien logiciel VB.NET.
        """
        x_r, y_r, z_r = self.robot_pos['X'], self.robot_pos['Y'], self.robot_pos['Z']
        theta_rad, phi_rad = math.radians(self.robot_pos['THETA']), math.radians(self.robot_pos['PHI'])

        offsets = self.config['OFFSETS']
        corr_t_x = offsets.getfloat('correction_theta_x')
        corr_t_y = offsets.getfloat('correction_theta_y')
        corr_p_l = offsets.getfloat('correction_phi_l')

        ct, st = math.cos(theta_rad), math.sin(theta_rad)
        cp, sp = math.cos(phi_rad), math.sin(phi_rad)

        # Correction = (x_offset_theta) + (y_offset_phi)
        correction_x = (corr_t_x * ct) - (corr_t_y * st) + (corr_p_l * cp * st)
        correction_y = (corr_t_x * st) + (corr_t_y * ct) - (corr_p_l * cp * ct)
        correction_z = -corr_p_l * sp

        # CapsulePosition = RobotPosition + Correction
        self.capsule_pos['X'] = x_r + correction_x
        self.capsule_pos['Y'] = y_r + correction_y
        self.capsule_pos['Z'] = z_r + correction_z

    def calculate_robot_coords_for_capsule(self, X, Y, Z, THETA, PHI):
        """
        Calcule les coordonnées robot nécessaires pour atteindre une cible capsule.
        Équations alignées sur l'ancien logiciel VB.NET.
        """
        theta_rad, phi_rad = math.radians(THETA), math.radians(PHI)

        offsets = self.config['OFFSETS']
        corr_t_x = offsets.getfloat('correction_theta_x')
        corr_t_y = offsets.getfloat('correction_theta_y')
        corr_p_l = offsets.getfloat('correction_phi_l')

        ct, st = math.cos(theta_rad), math.sin(theta_rad)
        cp, sp = math.cos(phi_rad), math.sin(phi_rad)

        # Correction = (x_offset_theta) + (y_offset_phi)
        correction_x = (corr_t_x * ct) - (corr_t_y * st) + (corr_p_l * cp * st)
        correction_y = (corr_t_x * st) + (corr_t_y * ct) - (corr_p_l * cp * ct)
        correction_z = -corr_p_l * sp

        # RobotPosition = CapsulePosition - Correction
        robot_x = X - correction_x
        robot_y = Y - correction_y
        robot_z = Z - correction_z

        return {'X': robot_x, 'Y': robot_y, 'Z': robot_z, 'THETA': THETA, 'PHI': PHI}

    def start_move_to(self, **kwargs) -> str:
        axes_to_command = set()
        pa_values = [''] * len(AXES_ORDER)
        for name, value in kwargs.items():
            name_up = name.upper()
            if name_up in self.AXIS_MAPPING:
                axis_letter = self.AXIS_MAPPING[name_up]
                if axis_letter == AXIS_X_GANTRY_SLAVE: continue
                steps = self._to_steps(name_up, value)
                pa_values[AXES_ORDER.index(axis_letter)] = str(steps)
                axes_to_command.add(axis_letter)

        if not axes_to_command:
            self.logger.warning("start_move_to appelé sans coordonnées valides.")
            return ""

        axes_to_wait_for = axes_to_command.copy()
        if AXIS_X_GANTRY_MASTER in axes_to_command:
            axes_to_wait_for.add(AXIS_X_GANTRY_SLAVE)

        axes_to_begin_str = "".join(sorted(list(axes_to_command)))
        self.active_moving_axes = "".join(sorted(list(axes_to_wait_for)))

        cmd_pa = f"PA {','.join(pa_values)}"
        full_command = f"{cmd_pa};BG {axes_to_begin_str}"
        self.logger.info(f"Démarrage Mouvement Absolu: {full_command}")
        self.driver.send_cmd(full_command)
        return self.active_moving_axes

    def is_motion_complete(self) -> bool:
        if not self.active_moving_axes:
            return True

        for axis in self.active_moving_axes:
            response = self.driver.send_query(f"MG _BG{axis}")
            try:
                if response is not None and float(response) != 0:
                    return False
            except (ValueError, TypeError):
                return False

        self.logger.info(f"Mouvement terminé pour les axes: {self.active_moving_axes}")
        self.active_moving_axes = ""
        self.update_positions()
        return True

    def _wait_for_motion_blocking(self):
        """Méthode de commodité pour les mouvements manuels bloquants."""
        while not self.is_motion_complete():
            time.sleep(0.1)

    def move_to(self, **kwargs):
        self.start_move_to(**kwargs)
        self._wait_for_motion_blocking()

    def go_home(self):
        self.logger.info("Retour à l'origine...")
        self.move_to(X=0, Y=0, Z=0, THETA=0, PHI=0)

    def define_current_position_as_zero(self):
        self.logger.info("Définition position comme nouvelle origine.")
        self.driver.send_cmd("DP 0,0,0,0,0,0")
        self.update_positions()

    def define_position(self, **kwargs):
        dp_values = [''] * len(AXES_ORDER)
        has_args = False
        for name, value in kwargs.items():
            name_up = name.upper()
            if name_up in self.AXIS_MAPPING:
                axis_letter = self.AXIS_MAPPING[name_up]
                steps = self._to_steps(name_up, value)
                dp_values[AXES_ORDER.index(axis_letter)] = str(steps)
                has_args = True

        if not has_args:
            self.logger.warning("define_position appelée sans arguments valides.")
            return

        cmd_dp = f"DP {','.join(dp_values)}"
        self.logger.info(f"Définition de position manuelle : {cmd_dp}")
        self.driver.send_cmd(cmd_dp)
        self.update_positions()

    def set_parking(self):
        self.logger.info("Mise à jour de la configuration de parking en mémoire avec la position actuelle.")
        if not self.config.has_section('ROBOT_POSITIONS'): self.config.add_section('ROBOT_POSITIONS')
        if not self.robot_pos: self.logger.warning(
            "robot_pos est vide. Appelez update_positions() avant set_parking()."); return
        for axis_name, position in self.robot_pos.items():
            config_key = f"parking_{axis_name.lower()}"
            self.config.set('ROBOT_POSITIONS', config_key, f"{position:.4f}")

    def go_to_parking(self):
        self.logger.info("Déplacement vers la position de parking...")
        try:
            parking_coords = {'X': self.config.getfloat('ROBOT_POSITIONS', 'parking_x'),
                              'Y': self.config.getfloat('ROBOT_POSITIONS', 'parking_y'),
                              'Z': self.config.getfloat('ROBOT_POSITIONS', 'parking_z'),
                              'THETA': self.config.getfloat('ROBOT_POSITIONS', 'parking_theta'),
                              'PHI': self.config.getfloat('ROBOT_POSITIONS', 'parking_phi'), }
            self.logger.info(f"Cible Parking: {parking_coords}")
            self.move_to(**parking_coords)
            self.logger.info("Position de parking atteinte.")
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            self.logger.error(f"Position de parking non définie ou incomplète. Erreur: {e}")
        except Exception as e:
            self.logger.error(f"Erreur lors du déplacement vers le parking: {e}")

    def move_relative(self, **kwargs):
        if not kwargs: self.logger.warning("move_relative appelé sans arguments."); return
        self.update_positions()
        target_coords = self.robot_pos.copy()
        for axis, distance in kwargs.items():
            axis_upper = axis.upper()
            if axis_upper in target_coords:
                target_coords[axis_upper] += float(distance)
            else:
                self.logger.warning(f"Axe inconnu dans move_relative : {axis}")
        self.logger.info(f"Déplacement relatif vers les coordonnées cibles : {target_coords}")
        self.move_to(**target_coords)

    def software_reset(self):
        self.logger.warning("Lancement d'une réinitialisation logicielle (RS) du contrôleur...")
        last_pos = self.last_positions.copy()
        self.logger.info(f"Sauvegarde de la position avant reset : {last_pos}")
        self.driver.ser.write(b'RS\r')
        self.driver.ser.flush()
        self.logger.info("Attente de 2 secondes pour le redémarrage du contrôleur...")
        time.sleep(2)
        self.driver.ser.reset_input_buffer()
        self.driver.ser.write(b'\r')
        time.sleep(0.2)
        initial_response = self.driver.ser.read_all()
        self.logger.debug(f"Réponse après reset: {initial_response!r}")
        self.logger.info("Le contrôleur a redémarré. Re-désactivation de l'écho...")
        self.driver._disable_echo()
        if last_pos:
            self.logger.info(f"Restauration de la position : {last_pos}")
            self.define_position(**last_pos)
        self.logger.info("Réinitialisation terminée. Réactivation des moteurs...")
        self.enable_motors()
        self.logger.info("Contrôleur de nouveau opérationnel.")