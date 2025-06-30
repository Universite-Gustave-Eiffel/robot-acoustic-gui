# src/controller_interface/GalilDriver.py
import serial
import time
import logging
import configparser
import math
import os

# --- Constantes partagées ---
AXIS_X_GANTRY_MASTER, AXIS_X_GANTRY_SLAVE = 'A', 'B'
AXIS_Y_TABLE, AXIS_Z_VERTICAL = 'C', 'D'
AXIS_THETA_ROTATION, AXIS_PHI_TILT = 'E', 'F'
ALL_AXES_PHYSICAL = "ABCDEF"
AXES_ORDER = ['A', 'B', 'C', 'D', 'E', 'F']


# ==============================================================================
#  CLASSE DRIVER BAS NIVEAU : COMMUNICATION AVEC LE CONTRÔLEUR
# ==============================================================================
class GalilDriver:
    """Couche de communication de bas niveau avec le contrôleur Galil. Parle en commandes et steps."""

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
            if response is not None and '?' not in response:
                return response.replace(':', '').strip()
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
        return {ax: 0.0 for ax in axes_str}

    def wait_motion_complete(self, axes_str, timeout=45.0):
        if not self.is_connected or not axes_str: return
        self.logger.info(f"Attente fin de mouvement pour axes: {axes_str} (timeout={timeout}s)...")
        self.send_cmd(f"AM{axes_str}", timeout_override=timeout)
        self.logger.info(f"Mouvement (AM) terminé pour {axes_str}.")
        time.sleep(0.2)


# ==============================================================================
#  CLASSE CONTRÔLEUR HAUT NIVEAU : API DU ROBOT
# ==============================================================================
class RobotController:
    """Couche d'abstraction du robot. Gère les unités, la cinématique et les commandes de haut niveau."""

    AXIS_MAPPING = {
        'X': AXIS_X_GANTRY_MASTER, 'Y': AXIS_Y_TABLE, 'Z': AXIS_Z_VERTICAL,
        'THETA': AXIS_THETA_ROTATION, 'PHI': AXIS_PHI_TILT
    }

    def __init__(self, driver: GalilDriver, config: configparser.ConfigParser):
        self.driver = driver
        self.config = config
        self.logger = logging.getLogger("RobotApp.RobotController")
        self.robot_pos = {name: 0.0 for name in self.AXIS_MAPPING.keys()}
        self.capsule_pos = {'X': 0.0, 'Y': 0.0, 'Z': 0.0}

    def connect(self):
        return self.driver.connect()

    def disconnect(self):
        self.driver.disconnect()

    def enable_motors(self):
        self.logger.info("Activation des moteurs...")
        self.driver.send_cmd(f"SH{ALL_AXES_PHYSICAL}")

    def disable_motors(self):
        self.logger.info("Désactivation des moteurs...")
        self.driver.send_cmd(f"MO{ALL_AXES_PHYSICAL}")

    def stop_all_motion(self):
        self.logger.warning("Arrêt d'urgence.")
        self.driver.send_cmd(f"ST{ALL_AXES_PHYSICAL}")

    def _to_steps(self, axis_name, value):
        ratio = self.config.getfloat('RATIOS', axis_name.lower())
        return int(value * ratio)

    def _from_steps(self, axis_name, steps):
        ratio = self.config.getfloat('RATIOS', axis_name.lower())
        return steps / ratio if ratio != 0 else 0.0

    def update_positions(self):
        raw_steps = self.driver.get_tp_positions(ALL_AXES_PHYSICAL)
        if raw_steps:
            for name, letter in self.AXIS_MAPPING.items():
                self.robot_pos[name] = self._from_steps(name, raw_steps.get(letter, 0))
            self._calculate_capsule_position()
        return self.robot_pos

    def _calculate_capsule_position(self):
        x_r, y_r, z_r = self.robot_pos['X'], self.robot_pos['Y'], self.robot_pos['Z']
        theta_rad, phi_rad = math.radians(self.robot_pos['THETA']), math.radians(self.robot_pos['PHI'])
        offsets = self.config['OFFSETS']
        corr_t_x = offsets.getfloat('correction_theta_x')
        corr_t_y = offsets.getfloat('correction_theta_y')
        corr_t_z = offsets.getfloat('correction_theta_z')
        corr_p_l = offsets.getfloat('correction_phi_l')
        ct, st, cp, sp = math.cos(theta_rad), math.sin(theta_rad), math.cos(phi_rad), math.sin(phi_rad)
        x_p = x_r + (corr_t_x * ct) - (corr_t_y * st)
        y_p = y_r + (corr_t_x * st) + (corr_t_y * ct)
        z_p = z_r + corr_t_z
        self.capsule_pos['X'] = x_p - (corr_p_l * cp * st)
        self.capsule_pos['Y'] = y_p + (corr_p_l * cp * ct)
        self.capsule_pos['Z'] = z_p - (corr_p_l * sp)

    def move_to(self, **kwargs):
        axes_to_move = set()
        pa_values = [''] * len(AXES_ORDER)
        for name, value in kwargs.items():
            name_up = name.upper()
            if name_up in self.AXIS_MAPPING:
                axis_letter = self.AXIS_MAPPING[name_up]
                steps = self._to_steps(name_up, value)
                pa_values[AXES_ORDER.index(axis_letter)] = str(steps)
                axes_to_move.add(axis_letter)
        if not axes_to_move: self.logger.warning("move_to appelé sans coordonnées valides."); return
        if self.AXIS_MAPPING['X'] in axes_to_move: axes_to_move.add(AXIS_X_GANTRY_SLAVE)
        axes_to_begin_str = "".join(sorted(list(axes_to_move)))
        cmd_pa = f"PA {','.join(pa_values)}"
        self.logger.info(f"Mouvement Absolu: {cmd_pa} | BG {axes_to_begin_str}")
        self.driver.send_cmd(cmd_pa)
        self.driver.send_cmd(f"BG {axes_to_begin_str}")
        self.driver.wait_motion_complete(axes_to_begin_str)
        self.update_positions()

    def go_home(self):
        self.logger.info("Retour à l'origine...")
        self.move_to(X=0, Y=0, Z=0, THETA=0, PHI=0)

    def define_current_position_as_zero(self):
        self.logger.info("Définition position comme nouvelle origine.")
        self.driver.send_cmd("DP 0,0,0,0,0,0")
        self.update_positions()

    def jog(self, axis_name, speed):
        axis_letter = self.AXIS_MAPPING[axis_name.upper()]
        steps_per_sec = self._to_steps(axis_name.upper(), speed)
        self.driver.send_cmd(f"JG{axis_letter}={int(steps_per_sec)}")
        if axis_letter == AXIS_X_GANTRY_MASTER: self.driver.send_cmd(f"JG{AXIS_X_GANTRY_SLAVE}={int(-steps_per_sec)}")

    def begin_jog_mode(self):
        self.logger.info(f"Activation du mode Jogging sur les axes: {ALL_AXES_PHYSICAL}")
        for axis in ALL_AXES_PHYSICAL: self.driver.send_cmd(f"JG{axis}=0")
        self.driver.send_cmd(f"BG{ALL_AXES_PHYSICAL}")