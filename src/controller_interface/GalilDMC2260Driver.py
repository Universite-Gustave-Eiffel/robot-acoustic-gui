import serial
import time
import logging
import configparser
import math
import traceback

try:
    import pygame
except ImportError:
    print("La bibliothèque Pygame n'est pas installée. Le contrôle clavier est impossible.")
    pygame = None

# --- Configuration (valeurs par défaut si config.ini est absent) ---
SERIAL_PORT_DEFAULT = 'COM7'
BAUD_RATE_DEFAULT = 9600
TIMEOUT_DEFAULT = 0.5
COMMAND_SEND_DELAY = 0.05
RESPONSE_READ_DELAY = 0.15

# --- Constantes des Axes ---
AXIS_X_GANTRY_MASTER = 'A'
AXIS_X_GANTRY_SLAVE = 'B'
AXIS_Y_TABLE = 'C'
AXIS_Z_VERTICAL = 'D'
AXIS_THETA_ROTATION = 'E'
AXIS_PHI_TILT = 'F'
ALL_AXES_PHYSICAL = "ABCDEF"
AXES_ORDER = ['A', 'B', 'C', 'D', 'E', 'F']
AXIS_MAPPING = {
    'X': AXIS_X_GANTRY_MASTER,
    'Y': AXIS_Y_TABLE,
    'Z': AXIS_Z_VERTICAL,
    'THETA': AXIS_THETA_ROTATION,
    'PHI': AXIS_PHI_TILT
}

POSITION_TOLERANCE_DEFAULT = 300

# --- Configuration du logger global ---
logger = logging.getLogger("RobotScript")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)


class GalilDMC2260Driver:
    def __init__(self, port=SERIAL_PORT_DEFAULT, baud=BAUD_RATE_DEFAULT, timeout=TIMEOUT_DEFAULT,
                 config_file='config.ini'):
        self.port_name = port
        self.baud_rate = baud
        self.timeout = timeout
        self.ser = None
        self.is_connected = False
        self.logger = logging.getLogger("RobotScript.GalilDMC2260Driver")
        self.echo_disabled_confirmed = False

        self.config = configparser.ConfigParser()
        if not self.config.read(config_file):
            self.logger.error(
                f"Fichier de configuration '{config_file}' non trouvé. Utilisation de valeurs par défaut.")
            self._load_default_config()

        self.current_robot_tp = {axis: 0.0 for axis in ALL_AXES_PHYSICAL}

    def _load_default_config(self):
        """Charge une configuration par défaut si le fichier .ini est manquant."""
        self.config['RATIOS'] = {
            'X': '542.873', 'Y': '-539.153', 'Z': '360.120',
            'THETA': '227.544', 'PHI': '-69.958'
        }
        self.config['OFFSETS'] = {
            'CORRECTION_THETA_X': '48.0', 'CORRECTION_THETA_Y': '37.0',
            'CORRECTION_THETA_Z': '0.0', 'CORRECTION_PHI_L': '53.0'
        }

    # --- Méthodes de Conversion ---
    def mm_to_steps(self, axis_name, mm_value):
        ratio = self.config.getfloat('RATIOS', axis_name)
        return int(mm_value * ratio)

    def degrees_to_steps(self, axis_name, degrees_value):
        ratio = self.config.getfloat('RATIOS', axis_name)
        return int(degrees_value * ratio)

    def steps_to_mm(self, axis_name, steps_value):
        ratio = self.config.getfloat('RATIOS', axis_name)
        if ratio == 0: return 0.0
        return steps_value / ratio

    def steps_to_degrees(self, axis_name, steps_value):
        ratio = self.config.getfloat('RATIOS', axis_name)
        if ratio == 0: return 0.0
        return steps_value / ratio

    # --- Gestion des Coordonnées ---
    def get_robot_position_mm_deg(self):
        self.update_all_tp_positions()
        return {
            'X': self.steps_to_mm('X', self.current_robot_tp['A']),
            'Y': self.steps_to_mm('Y', self.current_robot_tp['C']),
            'Z': self.steps_to_mm('Z', self.current_robot_tp['D']),
            'THETA': self.steps_to_degrees('THETA', self.current_robot_tp['E']),
            'PHI': self.steps_to_degrees('PHI', self.current_robot_tp['F']),
        }

    def get_capsule_position_mm(self):
        robot_pos = self.get_robot_position_mm_deg()
        x, y, z = robot_pos['X'], robot_pos['Y'], robot_pos['Z']
        theta_rad = math.radians(robot_pos['THETA'])
        phi_rad = math.radians(robot_pos['PHI'])
        corr_theta_x = self.config.getfloat('OFFSETS', 'CORRECTION_THETA_X')
        corr_phi_l = self.config.getfloat('OFFSETS', 'CORRECTION_PHI_L')

        capsule_x = x + (corr_theta_x * math.cos(theta_rad)) - (corr_phi_l * math.cos(phi_rad) * math.sin(theta_rad))
        capsule_y = y + (corr_theta_x * math.sin(theta_rad)) + (corr_phi_l * math.cos(phi_rad) * math.cos(theta_rad))
        capsule_z = z - (corr_phi_l * math.sin(phi_rad))
        return {'X': capsule_x, 'Y': capsule_y, 'Z': capsule_z}

    # --- Méthodes de Communication et Contrôle ---
    def connect(self):
        if self.is_connected: return True
        try:
            self.logger.info(f"Tentative de connexion à {self.port_name} à {self.baud_rate} bauds...")
            self.ser = serial.Serial(port=self.port_name, baudrate=self.baud_rate, bytesize=serial.EIGHTBITS,
                                     parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=self.timeout,
                                     xonxoff=False, rtscts=False)
            time.sleep(0.5)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            self.logger.info(f"Port série {self.ser.name} ouvert.")
            self.ser.write(b'\r\r')
            time.sleep(0.25)
            initial_response = self.ser.read_all()
            if b':' in initial_response or b'?' in initial_response:
                self.logger.info(f"Prompt initial reçu: {initial_response!r}")
                self.is_connected = True
                if not self._disable_echo(): self.logger.warning("Confirmation de désactivation de l'écho échouée.")
                self.update_all_tp_positions()
                self.logger.info(f"Connecté avec succès au Galil sur {self.port_name}.")
                return True
            else:
                self.logger.error(f"Échec de connexion : Prompt non reçu. Reçu: {initial_response!r}")
                if self.ser: self.ser.close()
                return False
        except serial.SerialException as e:
            self.logger.error(f"Erreur Serial lors de la connexion: {e}")
        except Exception as e:
            self.logger.error(f"Erreur inattendue lors de la connexion: {e}")
        self.is_connected = False
        return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            try:
                if self.echo_disabled_confirmed:
                    self.logger.info("Tentative de réactivation de l'écho (EO1)...")
                    self.ser.write(b"EO1\r")
                    time.sleep(0.1)
                self.ser.close()
                self.logger.info(f"Port série {self.port_name} fermé.")
            except Exception as e:
                self.logger.error(f"Erreur lors de la déconnexion: {e}")
        self.is_connected = False

    def _disable_echo(self):
        self.logger.info("Désactivation de l'écho (EO0)...")
        self.ser.reset_input_buffer()
        self.ser.write(b"EO0\r")
        time.sleep(0.2)
        response_bytes = self.ser.read_all()
        stripped_response = response_bytes.strip()
        if stripped_response == b':' or stripped_response.endswith(b':'):
            self.logger.info("Écho désactivé avec succès ou était déjà désactivé.")
            self.echo_disabled_confirmed = True
            return True
        self.logger.warning(f"Réponse inattendue à EO0: {response_bytes!r}.")
        return False

    def send_rcv(self, command, expected_terminator=':', read_multiple_lines=False, timeout_override=None, retries=0):
        if not self.is_connected:
            self.logger.error(f"Non connecté. Commande ignorée: {command}")
            return None if not read_multiple_lines else []
        self.logger.debug(f"CMD: {command}")
        if self.echo_disabled_confirmed: self.ser.reset_input_buffer()
        self.ser.write((command + '\r').encode('ascii'))
        time.sleep(COMMAND_SEND_DELAY if not command.startswith("AM") else 0.01)
        original_ser_timeout = self.ser.timeout
        current_timeout = timeout_override if timeout_override is not None else self.timeout
        if command.startswith("AM"): current_timeout = timeout_override if timeout_override is not None else 10.0
        self.ser.timeout = current_timeout
        response_data = b''
        response_str_or_list = None
        try:
            if read_multiple_lines:
                if command == chr(18) + chr(22):
                    time.sleep(0.3)
                    response_data = self.ser.read_all()
                else:
                    response_data = self.ser.read_until(expected_terminator.encode('ascii'))
                lines = [ln.strip() for ln in response_data.decode('ascii', errors='ignore').splitlines() if ln.strip()]
                if lines and lines[-1] == expected_terminator and len(lines) > 1:
                    lines.pop()
                elif lines and lines[-1] == expected_terminator and len(lines) == 1:
                    lines = []
                response_str_or_list = lines
            else:
                response_data = self.ser.read_until(expected_terminator.encode('ascii'))
                response_str = response_data.decode('ascii', errors='ignore').strip()
                if response_str.endswith(expected_terminator):
                    response_str = response_str[:-len(expected_terminator)].strip()
                response_str_or_list = response_str
        except serial.SerialTimeoutException:
            self.logger.error(f"Timeout pour '{command}'. Reçu: {response_data!r}")
        except Exception as e:
            self.logger.error(f"Erreur lecture pour '{command}': {e}. Reçu: {response_data!r}")
        finally:
            self.ser.timeout = original_ser_timeout
        if command.startswith("MG") and not response_str_or_list and retries < 2:
            self.logger.warning(f"Réponse vide pour '{command}', nouvelle tentative ({retries + 1}/2)...")
            time.sleep(RESPONSE_READ_DELAY * (retries + 1) * 3)
            return self.send_rcv(command, expected_terminator, read_multiple_lines, timeout_override, retries + 1)
        if response_str_or_list is None or (isinstance(response_str_or_list, list) and not response_str_or_list):
            if not any(cmd_start in command for cmd_start in
                       ["BG", "MO", "SH", "ST", "PR", "JG", "GA", "GR", "GM", "DP", "AC", "SP", "DC", "EO", "AM",
                        "WT"]):
                self.logger.warning(f"Aucune réponse de contenu ou timeout pour '{command}'.")
        elif isinstance(response_str_or_list, str) and '?' in response_str_or_list:
            self.logger.warning(f"Erreur Galil ('?') pour '{command}'. Réponse: {response_str_or_list}")
        self.logger.debug(f"RSP: {response_str_or_list!r}")
        return response_str_or_list

    def update_all_tp_positions(self, axes_str=ALL_AXES_PHYSICAL):
        if not axes_str: return self.current_robot_tp.copy()
        axes_for_cmd = "".join(sorted(list(set(str(axes_str)))))
        if not axes_for_cmd: return self.current_robot_tp.copy()
        operands = ",".join([f"_TP{ax}" for ax in axes_for_cmd])
        response = self.send_rcv(f"MG {operands}")
        if response and '?' not in response:
            values = response.split()
            if len(values) == len(axes_for_cmd):
                for i, ax_char in enumerate(axes_for_cmd):
                    try:
                        self.current_robot_tp[ax_char] = float(values[i])
                    except ValueError:
                        self.logger.error(f"Err conv TP multi pour {ax_char}: '{values[i]}'")
            elif response.strip() != "":
                self.logger.warning(
                    f"MG _TP multi: Nbre valeurs ({len(values)}) != Nbre axes ({len(axes_for_cmd)}). Cmd: MG {operands}, Réponse: {response!r}")
        return self.current_robot_tp.copy()

    def enable_motor_drivers(self, axes_str=ALL_AXES_PHYSICAL):
        for axis_char in axes_str: self.send_rcv(f"SH{axis_char}")
        return True

    def stop_motion(self, axes_str=ALL_AXES_PHYSICAL):
        return self.send_rcv(f"ST{axes_str}")

    def disable_motor_drivers(self, axes_str=ALL_AXES_PHYSICAL):
        for axis_char in axes_str:
            self.send_rcv(f"ST{axis_char}")
            time.sleep(0.1)
            response = self.send_rcv(f"MO{axis_char}")
            if response == '?':
                tc_error = self.send_rcv("TC")
                self.logger.error(f"Erreur sur MO{axis_char}. Code TC général: {tc_error}")
        return True

    def set_jog_speed(self, axis, speed_steps):
        self.logger.debug(f"Définition vitesse Jog : Axe {axis}, Vitesse {int(speed_steps)} steps/s")
        return self.send_rcv(f"JG{axis}={int(speed_steps)}")

    def begin_jog(self, axes_str):
        self.logger.info(f"Démarrage du profil de Jogging sur les axes : {axes_str}")
        return self.send_rcv(f"BG{axes_str}")

    def move_absolute_steps(self, axis_steps_dict):
        if not axis_steps_dict: return ""
        axes_to_begin = ""
        pa_values = [''] * len(AXES_ORDER)
        for axis_letter, steps in axis_steps_dict.items():
            if axis_letter in AXES_ORDER:
                axis_index = AXES_ORDER.index(axis_letter)
                pa_values[axis_index] = str(int(steps))
                axes_to_begin += axis_letter
        if AXIS_X_GANTRY_MASTER in axes_to_begin and AXIS_X_GANTRY_SLAVE not in axes_to_begin:
            axes_to_begin += AXIS_X_GANTRY_SLAVE
        cmd_pa = f"PA {','.join(pa_values)}"
        self.logger.info(f"Mouvement Absolu : {cmd_pa}")
        self.send_rcv(cmd_pa)
        self.send_rcv(f"BG {axes_to_begin}")
        return "".join(sorted(list(set(axes_to_begin))))

    def wait_motion_complete(self, axes_str, timeout=30.0):
        if not self.is_connected or not axes_str:
            return
        self.logger.info(f"Attente de la fin du mouvement pour les axes : {axes_str} ...")
        self.send_rcv(f"AM {axes_str}", timeout_override=timeout)
        self.logger.info(f"Mouvement (AM) terminé pour {axes_str}.")
        time.sleep(0.2)

        # Fiabilisation de la communication
        self.ser.reset_input_buffer()
        self.ser.write(b'\r')
        time.sleep(0.1)
        initial_response = self.ser.read_until(b':')
        if b':' not in initial_response:
            self.logger.warning(
                f"N'a pas reçu de prompt ':' après AM. Reçu: {initial_response!r}. On continue quand même.")
        self.ser.reset_input_buffer()

        self.update_all_tp_positions(axes_str)


def test_absolute_moves(robot):
    """Teste les déplacements absolus en utilisant des coordonnées en mm et degrés."""
    logger.info("--- Phase 2: Test des déplacements absolus ---")
    robot.send_rcv("SP 50000,50000,20000,20000,20000,20000")
    robot.send_rcv("AC 100000,100000,50000,50000,50000,50000")
    robot.send_rcv("DC 100000,100000,50000,50000,50000,50000")

    target_pos_mm = {'X': 50, 'Y': -30}
    logger.info(f"Déplacement vers la cible (mm): {target_pos_mm}")
    target_steps = {AXIS_MAPPING['X']: robot.mm_to_steps('X', target_pos_mm['X']),
                    AXIS_MAPPING['Y']: robot.mm_to_steps('Y', target_pos_mm['Y'])}
    moved_axes = robot.move_absolute_steps(target_steps)
    robot.wait_motion_complete(moved_axes)
    final_pos = robot.get_robot_position_mm_deg()
    logger.info(f"Position finale atteinte (mm/deg): X={final_pos['X']:.2f}, Y={final_pos['Y']:.2f}")

    time.sleep(1)
    target_pos_deg = {'Z': 20, 'THETA': 10, 'PHI': -10}
    logger.info(f"Déplacement vers la cible (mm/deg): {target_pos_deg}")
    target_steps = {AXIS_MAPPING['Z']: robot.mm_to_steps('Z', target_pos_deg['Z']),
                    AXIS_MAPPING['THETA']: robot.degrees_to_steps('THETA', target_pos_deg['THETA']),
                    AXIS_MAPPING['PHI']: robot.degrees_to_steps('PHI', target_pos_deg['PHI'])}
    moved_axes = robot.move_absolute_steps(target_steps)
    robot.wait_motion_complete(moved_axes)
    final_pos = robot.get_robot_position_mm_deg()
    logger.info(
        f"Position finale atteinte (mm/deg): Z={final_pos['Z']:.2f}, Theta={final_pos['THETA']:.2f}, Phi={final_pos['PHI']:.2f}")

    time.sleep(1)
    logger.info("Retour à l'origine...")
    target_steps_origin = {letter: 0 for letter in 'ACDEF'}
    moved_axes = robot.move_absolute_steps(target_steps_origin)
    robot.wait_motion_complete(ALL_AXES_PHYSICAL, timeout=45.0)
    final_pos = robot.get_robot_position_mm_deg()
    logger.info(f"Position finale après retour à l'origine: { {k: round(v, 2) for k, v in final_pos.items()} }")
    logger.info("--- Test de déplacement terminé ---")


def run_live_keyboard_control(robot_instance):
    """Fonction principale pour le contrôle en direct du robot via le clavier."""
    robot = robot_instance
    JOG_SPEED_XY, JOG_SPEED_Z, JOG_SPEED_ROT = 50000, 20000, 15000
    CONTROL_AXIS_X_MASTER, CONTROL_AXIS_X_SLAVE, CONTROL_AXIS_Y, CONTROL_AXIS_Z, CONTROL_AXIS_THETA, CONTROL_AXIS_PHI = AXES_ORDER
    controlled_axes = ALL_AXES_PHYSICAL

    try:
        logger.info("Configuration pour le contrôle en direct...")
        robot.stop_motion(controlled_axes)

        pygame.init()
        screen = pygame.display.set_mode([600, 200])
        pygame.display.set_caption("Contrôle Robot Galil")
        logger.info("--- PRÊT POUR LE CONTRÔLE CLAVIER ---")
        logger.info("XY (Portique/Table) : Flèches directionnelles")
        logger.info("Z (Vertical)        : '+' et 'Entrée' du pavé numérique")
        logger.info("Phi (Tilt)          : '8' et '2' du pavé numérique")
        logger.info("Theta (Rotation)    : '4' et '6' du pavé numérique")
        logger.info("Fermez la fenêtre ou pressez ÉCHAP pour arrêter.")

        for axis in controlled_axes: robot.set_jog_speed(axis, 0)
        robot.begin_jog(controlled_axes)

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP:
                        robot.set_jog_speed(CONTROL_AXIS_Y, JOG_SPEED_XY)
                    elif event.key == pygame.K_DOWN:
                        robot.set_jog_speed(CONTROL_AXIS_Y, -JOG_SPEED_XY)
                    elif event.key == pygame.K_LEFT:
                        robot.set_jog_speed(CONTROL_AXIS_X_MASTER, -JOG_SPEED_XY); robot.set_jog_speed(
                            CONTROL_AXIS_X_SLAVE, JOG_SPEED_XY)
                    elif event.key == pygame.K_RIGHT:
                        robot.set_jog_speed(CONTROL_AXIS_X_MASTER, JOG_SPEED_XY); robot.set_jog_speed(
                            CONTROL_AXIS_X_SLAVE, -JOG_SPEED_XY)
                    elif event.key == pygame.K_KP_PLUS:
                        robot.set_jog_speed(CONTROL_AXIS_Z, JOG_SPEED_Z)
                    elif event.key == pygame.K_KP_ENTER:
                        robot.set_jog_speed(CONTROL_AXIS_Z, -JOG_SPEED_Z)
                    elif event.key == pygame.K_KP8:
                        robot.set_jog_speed(CONTROL_AXIS_PHI, JOG_SPEED_ROT)
                    elif event.key == pygame.K_KP2:
                        robot.set_jog_speed(CONTROL_AXIS_PHI, -JOG_SPEED_ROT)
                    elif event.key == pygame.K_KP6:
                        robot.set_jog_speed(CONTROL_AXIS_THETA, JOG_SPEED_ROT)
                    elif event.key == pygame.K_KP4:
                        robot.set_jog_speed(CONTROL_AXIS_THETA, -JOG_SPEED_ROT)
                if event.type == pygame.KEYUP:
                    if event.key in [pygame.K_UP, pygame.K_DOWN]:     robot.set_jog_speed(CONTROL_AXIS_Y, 0)
                    if event.key in [pygame.K_LEFT, pygame.K_RIGHT]:  robot.set_jog_speed(CONTROL_AXIS_X_MASTER,
                                                                                          0); robot.set_jog_speed(
                        CONTROL_AXIS_X_SLAVE, 0)
                    if event.key in [pygame.K_KP_PLUS, pygame.K_KP_ENTER]: robot.set_jog_speed(CONTROL_AXIS_Z, 0)
                    if event.key in [pygame.K_KP8, pygame.K_KP2]:         robot.set_jog_speed(CONTROL_AXIS_PHI, 0)
                    if event.key in [pygame.K_KP6, pygame.K_KP4]:         robot.set_jog_speed(CONTROL_AXIS_THETA, 0)
            pygame.display.flip()
            time.sleep(0.02)
    except Exception as e:
        logger.critical(f"Une erreur critique est survenue pendant le contrôle: {e}")
        logger.error(traceback.format_exc())


if __name__ == '__main__':
    logger.info("--- Début du script de contrôle Robot ---")
    robot = GalilDMC2260Driver()

    if robot.connect():
        try:
            robot.enable_motor_drivers(ALL_AXES_PHYSICAL)

            test_absolute_moves(robot)

            logger.info("--- Lancement du contrôle manuel au clavier ---")
            time.sleep(2)
            if pygame:
                run_live_keyboard_control(robot)
            else:
                logger.warning("Pygame non installé, le contrôle clavier ne peut pas être lancé.")

        except Exception as e:
            logger.critical(f"Erreur critique non gérée: {e}")
            logger.error(traceback.format_exc())

        finally:
            logger.info("Nettoyage final...")
            if robot.is_connected:
                robot.stop_motion()
                robot.disable_motor_drivers()
                robot.disconnect()
            if pygame and pygame.get_init():
                pygame.quit()
    else:
        logger.error("Échec de la connexion initiale au contrôleur.")

    logger.info("Programme principal terminé.")