import serial
import time
import logging

# --- Configuration ---
SERIAL_PORT_DEFAULT = 'COM7'
BAUD_RATE_DEFAULT = 9600
TIMEOUT_DEFAULT = 0.5
COMMAND_SEND_DELAY = 0.05
RESPONSE_READ_DELAY = 0.15
PROMPT_RECEIVE_DELAY = 0.1
XONXOFF_DEFAULT = False
RTSCTS_DEFAULT = False

# --- Constantes des Axes ---
AXIS_X_GANTRY_MASTER = 'A'
AXIS_X_GANTRY_SLAVE = 'B'
AXIS_Y_TABLE = 'C'
AXIS_Z_VERTICAL = 'D'
AXIS_THETA_ROTATION = 'E'
AXIS_PHI_TILT = 'F'
ALL_AXES_PHYSICAL = "ABCDEF"
AXES_ORDER = ['A', 'B', 'C', 'D', 'E', 'F']

# --- Constantes de Déplacement (Exemples, ajuste selon tes besoins) ---
AXIS_X_STEPS = -543000
AXIS_Y_STEPS = -543000
AXIS_Z_STEPS = -360120
AXIS_THETA_STEPS = 82000
AXIS_PHI_STEPS = 25500

# Valeurs utilisées dans __main__ pour les tests
SPEED_TEST = 20000
ACCEL_DECEL_TEST = 15000
DIST_GANTRY_TEST = 10000
DIST_Y_TEST = 1500

POSITION_TOLERANCE_DEFAULT = 300

# Configuration du logger global pour ce script
logger = logging.getLogger("RobotScript")  # Logger principal du script
logger.setLevel(logging.DEBUG)  # Niveau de log pour le logger principal

# Créer un handler pour la console s'il n'y en a pas déjà pour ce logger
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)  # Niveau de log pour ce handler
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Optionnel: Handler pour un fichier
    # fh = logging.FileHandler('galil_driver_test.log', mode='w')
    # fh.setLevel(logging.DEBUG)
    # fh.setFormatter(formatter)
    # logger.addHandler(fh)


class GalilDMC2260Driver:
    def __init__(self, port=SERIAL_PORT_DEFAULT, baud=BAUD_RATE_DEFAULT,
                 timeout=TIMEOUT_DEFAULT):  # logger enlevé des params
        self.port_name = port
        self.baud_rate = baud
        self.timeout = timeout
        self.ser = None
        self.is_connected = False
        # Chaque instance de driver utilise le logger configuré globalement pour ce script
        self.logger = logging.getLogger("RobotScript.GalilDMC2260Driver")  # Logger enfant
        self.echo_disabled_confirmed = False
        self.current_tp = {axis: 0.0 for axis in ALL_AXES_PHYSICAL}

    def connect(self):
        if self.is_connected: return True
        try:
            self.logger.info(f"Tentative de connexion à {self.port_name} à {self.baud_rate} bauds...")
            self.ser = serial.Serial(
                port=self.port_name, baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE, timeout=self.timeout,
                xonxoff=False, rtscts=False
            )
            time.sleep(0.5)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            self.logger.info(f"Port série {self.ser.name} ouvert.")
            self.ser.write(b'\r\r')
            time.sleep(PROMPT_RECEIVE_DELAY + 0.1)
            initial_response = self.ser.read_all()
            if b':' in initial_response or b'?' in initial_response:
                self.logger.info(f"Prompt initial reçu: {initial_response!r}")
                self.is_connected = True
                if not self._disable_echo():
                    self.logger.warning("Confirmation de désactivation de l'écho échouée.")
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
        if self.echo_disabled_confirmed:
            self.ser.reset_input_buffer()

        self.ser.write((command + '\r').encode('ascii'))
        time.sleep(COMMAND_SEND_DELAY if not command.startswith("AM") else 0.01)

        original_ser_timeout = self.ser.timeout
        current_timeout = timeout_override if timeout_override is not None else self.timeout
        if command.startswith("AM"):
            current_timeout = timeout_override if timeout_override is not None else 10.0
        self.ser.timeout = current_timeout

        response_data = b''
        response_str_or_list = None
        try:
            if read_multiple_lines:
                if command == chr(18) + chr(22):  # REV
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
                       ["BG", "MO", "SH", "ST", "PR", "GA", "GR", "GM", "DP", "AC", "SP", "DC", "EO", "AM", "WT"]):
                self.logger.warning(f"Aucune réponse de contenu ou timeout pour '{command}'.")
        elif isinstance(response_str_or_list, str) and '?' in response_str_or_list:
            self.logger.warning(f"Erreur Galil ('?') pour '{command}'. Réponse: {response_str_or_list}")
        self.logger.debug(f"RSP: {response_str_or_list!r}")
        return response_str_or_list

    def get_firmware_revision(self):
        return self.send_rcv(chr(18) + chr(22), read_multiple_lines=True, timeout_override=1.0)

    def define_position_as_zero(self, axes_str=ALL_AXES_PHYSICAL):
        if not axes_str: self.logger.warning("DP: Aucun axe spécifié."); return None
        num_axes_in_order = len(AXES_ORDER)
        zero_values_str = ','.join(['0'] * num_axes_in_order)
        cmd = f"DP {zero_values_str}"
        response = self.send_rcv(cmd)
        if response is not None and '?' not in response:
            for axis_char in AXES_ORDER:
                if axis_char in self.current_tp:
                    self.current_tp[axis_char] = 0.0
        else:
            self.logger.error(f"Échec de la commande DP: '{cmd}' avec réponse '{response}'")
        return response

    def set_parameters_for_axes(self, command_prefix, value, axes_str=ALL_AXES_PHYSICAL):
        if not axes_str: return None
        if axes_str == ALL_AXES_PHYSICAL:
            return self.send_rcv(f"{command_prefix}*={value}")
        else:
            responses = {}
            for ax in axes_str:
                responses[ax] = self.send_rcv(f"{command_prefix}{ax}={value}")
            return responses

    def set_speed(self, speed, axes_str=ALL_AXES_PHYSICAL):
        return self.set_parameters_for_axes("SP", speed, axes_str)

    def set_acceleration(self, accel, axes_str=ALL_AXES_PHYSICAL):
        return self.set_parameters_for_axes("AC", accel, axes_str)

    def set_deceleration(self, decel, axes_str=ALL_AXES_PHYSICAL):
        return self.set_parameters_for_axes("DC", decel, axes_str)

    def configure_gantry(self, master_axis, slave_axis, gear_ratio=-1):
        self.logger.info(f"Configuration Gantry: Maître={master_axis}, Esclave={slave_axis}, Ratio={gear_ratio}")
        self.stop_motion(master_axis + slave_axis)
        time.sleep(0.1)
        self.send_rcv(f"GA{slave_axis}={master_axis}")
        self.send_rcv(f"GR{slave_axis}={gear_ratio}")
        self.send_rcv(f"GM{slave_axis}=1")
        time.sleep(0.1)
        gm_status = self.send_rcv(f"MG _GM{slave_axis}")
        gr_status = self.send_rcv(f"MG _GR{slave_axis}")
        ga_master_for_slave_status = self.send_rcv(f"MG _GA{slave_axis}")
        expected_master_code = str(float(AXES_ORDER.index(master_axis)))
        if '.' not in expected_master_code: expected_master_code += ".0000"
        self.logger.info(
            f"Statut Gantry après config: _GM{slave_axis}={gm_status}, _GR{slave_axis}={gr_status}, _GA{slave_axis} (maître pour esclave)={ga_master_for_slave_status} (attendu: {expected_master_code})")

    def move_relative(self, axis, distance):
        self.logger.info(f"Mouvement relatif: Axe {axis}, Distance {distance}")
        current_pos_val = self.get_tp_position(axis)
        if current_pos_val is None:
            self.logger.error(f"move_relative: Impossible de lire TP de {axis} avant PR.")
            return None
        # self.tp_at_pr_start[axis] = current_pos_val # Ligne supprimée
        expected_target_tp = current_pos_val + float(distance)

        self.send_rcv(f"PR{axis}={distance}")
        self.send_rcv(f"BG{axis}")
        return expected_target_tp

    def wait_motion_complete(self, axes_str):
        self.logger.info(f"Attente fin de mouvement pour : {axes_str} ...")
        if not axes_str: return
        time.sleep(0.05)
        self.send_rcv(f"AM{axes_str}", timeout_override=max(10, self.timeout * 10))
        self.logger.info(f"Mouvement AM terminé pour {axes_str}.")
        time.sleep(0.45)
        self.update_all_tp_positions(axes_str)

    def get_tp_position(self, axis):
        for attempt in range(3):
            response = self.send_rcv(f"MG _TP{axis}", timeout_override=0.3)
            if response and '?' not in response and response.strip() != "":
                try:
                    pos = float(response)
                    self.current_tp[axis] = pos
                    return pos
                except ValueError:
                    self.logger.error(f"Tentative {attempt + 1}: Erreur conversion TP '{response}' pour {axis}")
            elif response == '':
                self.logger.warning(f"Tentative {attempt + 1}: Réponse vide pour MG _TP{axis}")
            if attempt < 2: time.sleep(RESPONSE_READ_DELAY * (attempt + 1) * 2.5)
        self.logger.error(f"Échec final lecture TP pour l'axe {axis}.")
        return self.current_tp.get(axis, None)

    def update_all_tp_positions(self, axes_str=ALL_AXES_PHYSICAL):
        if not axes_str: return self.current_tp.copy()
        axes_for_cmd = "".join(sorted(list(set(str(axes_str)))))
        if not axes_for_cmd: return self.current_tp.copy()
        operands = ",".join([f"_TP{ax}" for ax in axes_for_cmd])
        response = self.send_rcv(f"MG {operands}")
        if response and '?' not in response:
            values = response.split()
            if len(values) == len(axes_for_cmd):
                for i, ax_char in enumerate(axes_for_cmd):
                    try:
                        self.current_tp[ax_char] = float(values[i])
                    except ValueError:
                        self.logger.error(f"Err conv TP multi pour {ax_char}: '{values[i]}'")
            else:
                if response.strip() != "":
                    self.logger.warning(
                        f"MG _TP multi: Nbre valeurs ({len(values)}) != Nbre axes ({len(axes_for_cmd)}). Cmd: MG {operands}, Réponse: {response!r}")
        return self.current_tp.copy()

    def check_position_reached(self, axis, target_position, tolerance=POSITION_TOLERANCE_DEFAULT):
        actual_pos = self.current_tp.get(axis)
        if actual_pos is None:
            self.logger.warning(
                f"Axe {axis}: Position actuelle non dispo (None) pour check (cible: {target_position}).")
            return False
        if target_position is None:
            self.logger.error(f"Axe {axis}: Position cible non définie (None) pour check.")
            return False
        diff = abs(actual_pos - target_position)
        if diff <= tolerance:
            self.logger.info(
                f"  Axe {axis}: Position OK (Attendu: {target_position:.1f}, Actuel: {actual_pos:.1f}, Diff: {diff:.2f})")
            return True
        else:
            self.logger.warning(
                f"  AVERTISSEMENT Axe {axis}: ÉCART (Attendu: {target_position:.1f}, Actuel: {actual_pos:.1f}, Diff: {diff:.2f} > Tol: {tolerance})")
            return False

    def disable_motor_drivers(self, axes_str=ALL_AXES_PHYSICAL):
        for axis_char in axes_str:
            self.send_rcv(f"ST{axis_char}")
            time.sleep(0.1)
            response = self.send_rcv(f"MO{axis_char}")
            if response == '?':
                tc_error = self.send_rcv(f"TC")
                self.logger.error(f"Erreur sur MO{axis_char}. Code TC général: {tc_error}")
        return True

    def enable_motor_drivers(self, axes_str=ALL_AXES_PHYSICAL):
        for axis_char in axes_str:
            self.send_rcv(f"SH{axis_char}")
        return True

    def stop_motion(self, axes_str=ALL_AXES_PHYSICAL):
        return self.send_rcv(f"ST{axes_str}")


if __name__ == '__main__':
    # robot va utiliser le logger "RobotScript.GalilDMC2260Driver"
    # et les logs de __main__ utiliseront "RobotScript"
    robot = GalilDMC2260Driver()

    if robot.connect():
        try:
            logger.info("--- Début Séquence de Test Robot ---")  # Utilise le logger global du script
            rev_info = robot.get_firmware_revision()
            if rev_info: logger.info(f"Révision du firmware: {' '.join(rev_info)}")

            robot.disable_motor_drivers(ALL_AXES_PHYSICAL)
            robot.configure_gantry(AXIS_X_GANTRY_MASTER, AXIS_X_GANTRY_SLAVE, gear_ratio=-1)
            robot.enable_motor_drivers(ALL_AXES_PHYSICAL)

            robot.update_all_tp_positions()
            initial_positions_after_sh = robot.current_tp.copy()
            logger.info(f"Positions après SH et avant DP0: {initial_positions_after_sh}")

            robot.define_position_as_zero(ALL_AXES_PHYSICAL)
            time.sleep(0.3)
            robot.update_all_tp_positions()
            initial_positions_after_dp0 = robot.current_tp.copy()
            logger.info(f"Positions après DP0: {initial_positions_after_dp0}")
            for ax_char_loop in ALL_AXES_PHYSICAL:
                robot.check_position_reached(ax_char_loop, 0.0, tolerance=POSITION_TOLERANCE_DEFAULT)

            logger.info(f"Définition V={SPEED_TEST}, A/D={ACCEL_DECEL_TEST}")
            robot.set_speed(SPEED_TEST, ALL_AXES_PHYSICAL)
            robot.set_acceleration(ACCEL_DECEL_TEST, ALL_AXES_PHYSICAL)
            robot.set_deceleration(ACCEL_DECEL_TEST, ALL_AXES_PHYSICAL)

            # --- Test Gantry ---
            logger.info(f"--- Test Mouvement Gantry ---")
            dist_gantry_test = DIST_GANTRY_TEST

            initial_tp_A_fwd = initial_positions_after_dp0[AXIS_X_GANTRY_MASTER]
            initial_tp_B_fwd = initial_positions_after_dp0[AXIS_X_GANTRY_SLAVE]
            logger.info(
                f"Mouvement Gantry X de {dist_gantry_test}... (Depuis A={initial_tp_A_fwd}, B={initial_tp_B_fwd})")

            expected_target_A_fwd = robot.move_relative(AXIS_X_GANTRY_MASTER, dist_gantry_test)
            if expected_target_A_fwd is None: raise Exception("move_relative gantry fwd failed")
            robot.wait_motion_complete(AXIS_X_GANTRY_MASTER + AXIS_X_GANTRY_SLAVE)

            robot.check_position_reached(AXIS_X_GANTRY_MASTER, expected_target_A_fwd)
            expected_target_B_fwd = initial_tp_B_fwd + (dist_gantry_test * -1)
            robot.check_position_reached(AXIS_X_GANTRY_SLAVE, expected_target_B_fwd)
            time.sleep(1)

            # --- Test Axe Y (C) ---
            logger.info(f"--- Test Mouvement Axe Y ({AXIS_Y_TABLE}) ---")
            dist_y_test = DIST_Y_TEST
            initial_tp_C_fwd = initial_positions_after_dp0[AXIS_Y_TABLE]
            logger.info(f"Mouvement Axe Y ({AXIS_Y_TABLE}) de {dist_y_test}... (Depuis C={initial_tp_C_fwd})")
            expected_target_C_fwd = robot.move_relative(AXIS_Y_TABLE, dist_y_test)
            if expected_target_C_fwd is None: raise Exception("move_relative Y fwd failed")
            robot.wait_motion_complete(AXIS_Y_TABLE)
            robot.check_position_reached(AXIS_Y_TABLE, expected_target_C_fwd)
            time.sleep(1)

            # --- Retour Gantry ---
            logger.info(f"Retour Gantry X de {-dist_gantry_test}...")
            # Les positions de départ pour ce mouvement sont les positions finales du mouvement précédent
            # qui sont dans self.current_tp car wait_motion_complete appelle update_all_tp_positions
            expected_target_A_ret = robot.move_relative(AXIS_X_GANTRY_MASTER, -dist_gantry_test)
            if expected_target_A_ret is None: raise Exception("move_relative gantry ret failed")
            robot.wait_motion_complete(AXIS_X_GANTRY_MASTER + AXIS_X_GANTRY_SLAVE)

            robot.check_position_reached(AXIS_X_GANTRY_MASTER, initial_positions_after_dp0[AXIS_X_GANTRY_MASTER])
            robot.check_position_reached(AXIS_X_GANTRY_SLAVE, initial_positions_after_dp0[AXIS_X_GANTRY_SLAVE])
            time.sleep(1)

            # --- Retour Axe Y ---
            logger.info(f"Retour Axe Y ({AXIS_Y_TABLE}) de {-dist_y_test}...")
            expected_target_C_ret = robot.move_relative(AXIS_Y_TABLE, -dist_y_test)
            if expected_target_C_ret is None: raise Exception("move_relative Y ret failed")
            robot.wait_motion_complete(AXIS_Y_TABLE)
            robot.check_position_reached(AXIS_Y_TABLE, initial_positions_after_dp0[AXIS_Y_TABLE])
            time.sleep(1)

            # ... (Ajouter les tests pour Z, Theta, Phi si nécessaire, en suivant le modèle de Y/C)

            logger.info("--- Fin Séquence de Test ---")

        except KeyboardInterrupt:
            logger.info("Interruption par l'utilisateur.")
            if robot.is_connected:
                try:
                    robot.stop_motion()
                except:
                    pass
                try:
                    robot.disable_motor_drivers()
                except:
                    pass
        except Exception as e_main:
            logger.critical(f"Erreur critique: {e_main}")
            import traceback

            traceback.print_exc()
        finally:
            if robot.is_connected:
                robot.disconnect()
            else:
                logger.info("Le robot n'était pas connecté, pas de déconnexion nécessaire.")
    else:
        logger.error("Échec de la connexion initiale au contrôleur.")

    print("Programme TestDMC2260 terminé.")