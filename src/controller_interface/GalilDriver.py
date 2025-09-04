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
    """Gère la communication de bas niveau avec le contrôleur Galil via une liaison série.

    Cette classe est responsable de l'établissement de la connexion, de l'envoi de
    commandes textuelles brutes, et de la lecture des réponses. Elle n'a aucune
    connaissance de la cinématique du robot ou de la signification des axes.

    :param port: Le nom du port série (ex: 'COM7').
    :param baudrate: Le débit en bauds (ex: 38400).
    :param timeout: Le timeout pour les lectures sur le port série, en secondes.
    """
    def __init__(self, port, baudrate, timeout):
        """Initialise le driver Galil."""
        self.port_name, self.baud_rate, self.timeout = port, baudrate, timeout
        self.ser, self.is_connected, self.echo_disabled = None, False, False
        self.logger = logging.getLogger("RobotApp.GalilDriver")

    def connect(self):
        """Établit la connexion avec le contrôleur sur le port série.

        Tente d'ouvrir le port, vérifie la présence du prompt Galil (':'),
        et désactive l'écho des commandes pour simplifier la communication.

        :return: ``True`` si la connexion est établie avec succès, ``False`` sinon.
        """
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
        """Ferme la connexion série avec le contrôleur."""
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
        """Envoie la commande 'EO0' pour désactiver l'écho des commandes. (Interne)"""
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
        """Envoie une commande au contrôleur Galil et lit la réponse.

        Ajoute le retour chariot '\\r' nécessaire à la fin de la commande.

        :param command: La commande à envoyer (sans le '\\r').
        :param timeout_override: Un timeout optionnel pour cette commande spécifique.
        :return: La réponse du contrôleur sous forme de chaîne de caractères,
                 ou ``None`` si non connecté.
        """
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
        """Envoie une commande "query" (qui retourne une valeur) et parse la réponse.

        Cette méthode est plus robuste que :meth:`send_cmd` pour les requêtes
        qui doivent retourner une valeur. Elle gère les tentatives multiples
        et nettoie la réponse pour ne retourner que la valeur utile.

        :param command: La commande de requête (ex: 'MG _TPA').
        :param retries: Le nombre de tentatives en cas de réponse invalide.
        :return: La valeur retournée par le contrôleur, ou ``None`` en cas d'échec.
        """
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
        """Récupère la position actuelle (en pas) de plusieurs axes.

        Utilise la commande 'MG _TP...' pour interroger la position des axes.

        :param axes_str: Une chaîne contenant les lettres des axes à interroger (ex: 'ACD').
        :return: Un dictionnaire avec les lettres des axes comme clés et leurs
                 positions en pas comme valeurs, ou ``None`` en cas d'échec.
        """
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
    """Contrôleur de haut niveau pour le robot acoustique.

    Cette classe utilise un :class:`GalilDriver` pour communiquer avec le matériel.
    Elle implémente la logique de haut niveau, y compris :
    - La conversion entre unités physiques (mm, degrés) et pas moteur.
    - La cinématique directe et inverse pour gérer les coordonnées "capsule".
    - Les commandes de mouvement complexes (absolu, relatif, parking).
    - La gestion du mode "jog" pour le contrôle manuel.

    :param driver: Une instance de :class:`GalilDriver` configurée.
    :param config: Une instance de `configparser.ConfigParser` contenant les
                   sections [RATIOS], [OFFSETS], etc.
    """
    AXIS_MAPPING = {'X': 'A', 'Y': 'C', 'Z': 'D', 'THETA': 'E', 'PHI': 'F'}
    AXIS_GANTRY_SLAVE = 'B'
    ALL_AXES = ALL_AXES_PHYSICAL

    def __init__(self, driver: GalilDriver, config: configparser.ConfigParser):
        """Initialise le contrôleur du robot."""
        self.driver = driver
        self.config = config
        self.logger = logging.getLogger("RobotApp.RobotController")
        self.robot_pos = {name: 0.0 for name in self.AXIS_MAPPING.keys()}
        self.capsule_pos = {'X': 0.0, 'Y': 0.0, 'Z': 0.0}
        self.last_positions = {name: 0.0 for name in self.AXIS_MAPPING.keys()}
        self.active_moving_axes = ""

    def connect(self):
        """Connecte le driver sous-jacent."""
        return self.driver.connect()

    def disconnect(self):
        """Déconnecte le driver sous-jacent."""
        self.driver.disconnect()

    def enable_motors(self):
        """Active les moteurs du robot (commande 'SH') et configure le mode Gantry."""
        self.logger.info("Activation des moteurs...")
        self.driver.send_cmd(f"SH{self.ALL_AXES}")
        self.logger.info("Configuration du Gantry pour les axes A (maître) et B (esclave)...")
        self.driver.send_cmd(f"GA ,{AXIS_X_GANTRY_MASTER}")
        self.driver.send_cmd(f"GR ,-1")
        self.driver.send_cmd(f"GM ,1")
        self.logger.info("Gantry configuré.")

    def disable_motors(self):
        """Désactive les moteurs du robot (commande 'MO')."""
        self.driver.send_cmd("ST")
        time.sleep(0.1)
        self.logger.info("Désactivation de tous les moteurs...")
        self.driver.send_cmd("MO")

    def stop_all_motion(self):
        """Arrête tous les mouvements en cours de manière contrôlée (commande 'ST')."""
        self.logger.warning("Commande ST (Stop) envoyée pour tous les axes.")
        self.driver.send_cmd("ST")
        self.active_moving_axes = ""

    def abort_all_motion(self):
        """Provoque un arrêt d'urgence de tous les mouvements (commande 'AB')."""
        self.logger.critical("COMMANDE D'ARRÊT D'URGENCE (AB) ENVOYÉE !")
        self.driver.send_cmd("AB")
        self.active_moving_axes = ""

    def reset_jog_mode(self):
        """Lance une réinitialisation logicielle du contrôleur Galil (commande 'RS').

        Cette opération redémarre le contrôleur. La position est sauvegardée avant
        le reset et restaurée après pour conserver le référentiel.
        """
        self.logger.info("Réinitialisation de l'état après le mode JOG...")
        self.driver.send_cmd(f"ST {self.ALL_AXES}")
        self.driver.send_cmd(f"MO {self.ALL_AXES}")
        time.sleep(0.5)
        self.driver.send_cmd(f"SH {self.ALL_AXES}")
        self.logger.info("État du servo réinitialisé.")

    def begin_jog_mode(self):
        """Active le mode JOG sur le contrôleur pour les mouvements continus."""
        self.logger.info("Activation du mode JOG...")
        self.driver.send_cmd(f"JG {','.join(['0'] * len(AXES_ORDER))}")
        self.driver.send_cmd(f"BG {self.ALL_AXES}")
        self.logger.info("Mode JOG actif.")

    def jog_continuous(self, **kwargs):
        """Met à jour les vitesses pour le mode JOG continu.

        :param kwargs: Dictionnaire où les clés sont les noms d'axes ('X', 'Y', etc.)
                       et les valeurs sont les vitesses souhaitées en unités physiques
                       (mm/s ou deg/s). Une vitesse de 0 arrête l'axe.
        """
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
        """Convertit une valeur en unités physiques (mm ou deg) en pas moteur. (Interne)"""
        return int(value * self.config.getfloat('RATIOS', axis_name.lower()))

    def _from_steps(self, axis_name, steps):
        """Convertit une valeur en pas moteur en unités physiques. (Interne)"""
        ratio = self.config.getfloat('RATIOS', axis_name.lower())
        return steps / ratio if ratio != 0 else 0.0

    def update_positions(self):
        """Met à jour les positions internes du robot (robot et capsule).

        Interroge le contrôleur pour les positions en pas, les convertit en
        unités physiques, puis calcule la position de la capsule via la
        cinématique directe.

        :return: Un dictionnaire de la position "robot" ou ``None`` si la lecture échoue.
        """
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
        """Calcule la position de la capsule à partir de la position du robot. (Cinématique directe)"""
        x_r, y_r, z_r = self.robot_pos['X'], self.robot_pos['Y'], self.robot_pos['Z']
        theta_rad, phi_rad = math.radians(self.robot_pos['THETA']), math.radians(self.robot_pos['PHI'])

        offsets = self.config['OFFSETS']
        corr_t_x = offsets.getfloat('correction_theta_x')
        corr_t_y = offsets.getfloat('correction_theta_y')
        corr_t_z = offsets.getfloat('correction_theta_z', fallback=0.0)
        corr_p_l = offsets.getfloat('correction_phi_l')

        c_theta, s_theta = math.cos(theta_rad), math.sin(theta_rad)
        c_phi, s_phi = math.cos(phi_rad), math.sin(phi_rad)

        # Vecteur local avant rotation par Theta
        x_local = corr_t_x + corr_p_l * math.sin(phi_rad)  # sin(phi) car phi=0 -> horizontal
        y_local = corr_t_y

        # Calcul du vecteur de correction total après rotation
        corr_x = (x_local * c_theta) - (y_local * s_theta)
        corr_y = (x_local * s_theta) + (y_local * c_theta)
        corr_z = corr_t_z - (corr_p_l * math.cos(phi_rad))  # cos(phi) pour la composante Z

        self.capsule_pos['X'] = x_r + corr_x
        self.capsule_pos['Y'] = y_r + corr_y
        self.capsule_pos['Z'] = z_r + corr_z

    def calculate_robot_coords_for_capsule(self, X, Y, Z, THETA, PHI):
        """Calcule les coordonnées robot nécessaires pour atteindre une cible capsule. (Cinématique inverse)

        Cette méthode est au cœur de la simplification de l'interface. Elle prend
        en entrée une position souhaitée pour le microphone et retourne les
        consignes à envoyer aux moteurs.

        :param X, Y, Z, THETA, PHI: Coordonnées de la cible "capsule".
        :return: Un dictionnaire des coordonnées "robot" correspondantes.
        """
        theta_rad, phi_rad = math.radians(THETA), math.radians(PHI)

        offsets = self.config['OFFSETS']
        corr_t_x = offsets.getfloat('correction_theta_x')
        corr_t_y = offsets.getfloat('correction_theta_y')
        corr_t_z = offsets.getfloat('correction_theta_z', fallback=0.0)
        corr_p_l = offsets.getfloat('correction_phi_l')

        c_theta, s_theta = math.cos(theta_rad), math.sin(theta_rad)
        c_phi, s_phi = math.cos(phi_rad), math.sin(phi_rad)

        # Calcul du même vecteur de correction avec les angles cibles
        x_local = corr_t_x + corr_p_l * s_phi
        y_local = corr_t_y

        corr_x = (x_local * c_theta) - (y_local * s_theta)
        corr_y = (x_local * s_theta) + (y_local * c_theta)
        corr_z = corr_t_z - (corr_p_l * c_phi)

        # Calcul inverse
        robot_x = X - corr_x
        robot_y = Y - corr_y
        robot_z = Z - corr_z

        return {'X': robot_x, 'Y': robot_y, 'Z': robot_z, 'THETA': THETA, 'PHI': PHI}

    def start_move_to(self, **kwargs) -> str:
        """Démarre un mouvement absolu non-bloquant.

        Envoie les commandes de position ('PA') et de début de mouvement ('BG')
        au contrôleur, mais ne bloque pas l'exécution.

        :param kwargs: Dictionnaire des coordonnées "robot" cibles.
        :return: Une chaîne contenant les lettres des axes en mouvement.
        """
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
        """Vérifie si le mouvement démarré avec :meth:`start_move_to` est terminé.

        Interroge le statut de chaque axe en mouvement (`_BG...`).

        :return: ``True`` si tous les axes ont atteint leur cible, ``False`` sinon.
        """
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
        """Attend la fin du mouvement en cours de manière bloquante. (Interne)"""
        while not self.is_motion_complete():
            time.sleep(0.1)

    def move_to(self, **kwargs):
        """Exécute un mouvement absolu et attend sa complétion (bloquant).

        :param kwargs: Dictionnaire des coordonnées "robot" cibles.
        """
        self.start_move_to(**kwargs)
        self._wait_for_motion_blocking()

    def go_home(self):
        """Déplace le robot à la position d'origine (0,0,0,0,0) robot."""
        self.logger.info("Retour à l'origine...")
        self.move_to(X=0, Y=0, Z=0, THETA=0, PHI=0)

    def define_current_position_as_zero(self):
        """Définit la position physique actuelle comme la nouvelle origine robot (0,0,0,0,0).

        Envoie la commande 'DP 0,0,0,0,0,0' au contrôleur Galil.
        """
        self.logger.info("Définition position comme nouvelle origine.")
        self.driver.send_cmd("DP 0,0,0,0,0,0")
        self.update_positions()

    def define_position(self, **kwargs):
        """Définit la position actuelle du robot à des coordonnées "robot" spécifiées (commande 'DP').

        Utilisé pour la calibration ou la restauration de position après un reset.

        :param kwargs: Dictionnaire des coordonnées "robot" à assigner.
        """
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
        """Sauvegarde la position CAPSULE actuelle comme nouvelle position de parking en mémoire."""
        self.logger.info("Mise à jour de la configuration de parking en mémoire avec la position CAPSULE actuelle.")
        if not self.config.has_section('CAPSULE_POSITIONS'): self.config.add_section('CAPSULE_POSITIONS')

        self.update_positions()
        if not self.capsule_pos:
            self.logger.warning("capsule_pos est vide. Impossible de définir le parking.")
            return

        self.config.set('CAPSULE_POSITIONS', 'parking_x', f"{self.capsule_pos.get('X', 0.0):.4f}")
        self.config.set('CAPSULE_POSITIONS', 'parking_y', f"{self.capsule_pos.get('Y', 0.0):.4f}")
        self.config.set('CAPSULE_POSITIONS', 'parking_z', f"{self.capsule_pos.get('Z', 0.0):.4f}")
        self.config.set('CAPSULE_POSITIONS', 'parking_theta', f"{self.robot_pos.get('THETA', 0.0):.4f}")
        self.config.set('CAPSULE_POSITIONS', 'parking_phi', f"{self.robot_pos.get('PHI', 0.0):.4f}")

    def go_to_parking(self):
        """Déplace le robot vers la position de parking (basée sur les coordonnées capsule)."""
        self.logger.info("Déplacement vers la position de parking (coordonnées capsule)...")
        try:
            parking_capsule_coords = {
                'X': self.config.getfloat('CAPSULE_POSITIONS', 'parking_x'),
                'Y': self.config.getfloat('CAPSULE_POSITIONS', 'parking_y'),
                'Z': self.config.getfloat('CAPSULE_POSITIONS', 'parking_z'),
                'THETA': self.config.getfloat('CAPSULE_POSITIONS', 'parking_theta'),
                'PHI': self.config.getfloat('CAPSULE_POSITIONS', 'parking_phi'),
            }
            self.logger.info(f"Cible Parking Capsule: {parking_capsule_coords}")

            # On utilise la cinématique inverse pour trouver les coordonnées robot correspondantes
            robot_target_coords = self.calculate_robot_coords_for_capsule(**parking_capsule_coords)
            self.logger.info(f"Déplacement robot vers: {robot_target_coords}")
            self.move_to(**robot_target_coords)

            self.logger.info("Position de parking atteinte.")
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            self.logger.error(f"Position de parking non définie ou incomplète. Erreur: {e}")
        except Exception as e:
            self.logger.error(f"Erreur lors du déplacement vers le parking: {e}")

    def move_relative(self, **kwargs):
        """Exécute un mouvement relatif par rapport à la position robot actuelle.

        :param kwargs: Dictionnaire avec un ou plusieurs axes et la distance
                       de déplacement souhaitée (ex: `move_relative(X=10, Z=-5)`).
        """
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
        """Lance une réinitialisation logicielle du contrôleur Galil (commande 'RS').

        Cette opération redémarre le contrôleur. La position est sauvegardée avant
        le reset et restaurée après pour conserver le référentiel. C'est une
        opération utile pour sortir de certains états d'erreur ou après un
        mode JOG intensif.
        """
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