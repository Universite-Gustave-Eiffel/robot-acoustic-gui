# main.py
import logging
import time
import os
import configparser
import traceback

# Corriger l'import en fonction de votre structure
# Si main.py est à la racine et GalilDriver.py est dans src/controller_interface
from src.controller_interface.GalilDriver import RobotController, GalilDriver

try:
    import pygame
except ImportError:
    pygame = None
    print("AVERTISSEMENT: Pygame n'est pas installé. Le contrôle manuel au clavier sera indisponible.")


# ==============================================================================
#  FONCTIONS APPLICATIVES
# ==============================================================================
def run_movement_test_sequence(robot: RobotController):
    """Exécute une séquence de test de mouvements absolus."""
    logger = logging.getLogger("RobotApp.TestSequence")
    logger.info("--- Phase de Test: Déplacements Absolus ---")

    accel = robot.config.getint('ROBOT_SPEEDS', 'accel_steps_s2')
    decel = robot.config.getint('ROBOT_SPEEDS', 'decel_steps_s2')
    # Pour SP, une approche simple est de définir une vitesse générique pour les tests
    # La commande complète serait: "SP valA,valB,valC,..."
    # Ici, nous mettons une vitesse globale pour simplifier.
    robot.driver.send_cmd(f"SP {accel // 2}")  # Vitesse = moitié de l'accélération
    robot.driver.send_cmd(f"AC {accel}")
    robot.driver.send_cmd(f"DC {decel}")

    logger.info("Mouvement 1: Déplacement vers X=20, Y=-10...")
    robot.move_to(X=20, Y=-10)
    logger.info(f"Position robot atteinte: X={robot.robot_pos['X']:.1f}, Y={robot.robot_pos['Y']:.1f}")

    time.sleep(1)
    logger.info("Mouvement 2: Déplacement vers Z=15, Theta=20, Phi=-5...")
    robot.move_to(Z=15, THETA=20, PHI=-5)
    logger.info(
        f"Position robot atteinte: Z={robot.robot_pos['Z']:.1f}, Theta={robot.robot_pos['THETA']:.1f}, Phi={robot.robot_pos['PHI']:.1f}")
    logger.info(
        f"Position capsule calculée: X={robot.capsule_pos['X']:.1f}, Y={robot.capsule_pos['Y']:.1f}, Z={robot.capsule_pos['Z']:.1f}")

    time.sleep(1)
    robot.go_home()
    logger.info("--- Tests de déplacement terminés ---")


def run_live_keyboard_control(robot: RobotController):
    """Fonction principale pour le contrôle en direct du robot via le clavier."""
    logger = logging.getLogger("RobotApp.ManualControl")
    if not pygame: logger.error("Pygame non installé."); return

    cfg = robot.config['ROBOT_SPEEDS']
    JOG_SPEEDS = {
        'X': cfg.getfloat('jog_xy_mm_s'), 'Y': cfg.getfloat('jog_xy_mm_s'),
        'Z': cfg.getfloat('jog_z_mm_s'), 'THETA': cfg.getfloat('jog_rot_deg_s'),
        'PHI': cfg.getfloat('jog_rot_deg_s')
    }
    pygame.init();
    screen = pygame.display.set_mode([600, 120]);
    pygame.display.set_caption("Contrôle Robot Manuel")
    logger.info("--- PRÊT POUR LE CONTRÔLE CLAVIER --- (Échap pour quitter)")
    robot.begin_jog_mode()
    key_map = {
        pygame.K_UP: ('Y', JOG_SPEEDS['Y']), pygame.K_DOWN: ('Y', -JOG_SPEEDS['Y']),
        pygame.K_LEFT: ('X', -JOG_SPEEDS['X']), pygame.K_RIGHT: ('X', JOG_SPEEDS['X']),
        pygame.K_KP_PLUS: ('Z', JOG_SPEEDS['Z']), pygame.K_KP_ENTER: ('Z', -JOG_SPEEDS['Z']),
        pygame.K_KP8: ('PHI', JOG_SPEEDS['PHI']), pygame.K_KP2: ('PHI', -JOG_SPEEDS['PHI']),
        pygame.K_KP6: ('THETA', JOG_SPEEDS['THETA']), pygame.K_KP4: ('THETA', -JOG_SPEEDS['THETA']),
    }
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
            if event.type == pygame.KEYDOWN and event.key in key_map: robot.jog(*key_map[event.key])
            if event.type == pygame.KEYUP and event.key in key_map: robot.jog(key_map[event.key][0], 0)
        pygame.display.flip();
        time.sleep(0.02)
    robot.stop_all_motion();
    pygame.quit()


# ==============================================================================
#  CONFIGURATION ET POINT D'ENTRÉE PRINCIPAL
# ==============================================================================
def setup_logging():
    log_dir = "logs"
    if not os.path.exists(log_dir): os.makedirs(log_dir)
    log_filename = f"app_log_{time.strftime('%Y%m%d_%H%M%S')}.log"
    log_filepath = os.path.join(log_dir, log_filename)
    app_logger = logging.getLogger("RobotApp")
    app_logger.setLevel(logging.DEBUG)
    if app_logger.hasHandlers(): app_logger.handlers.clear()
    file_handler = logging.FileHandler(log_filepath, 'w', 'utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - [%(levelname)-8s] %(name)-22s: %(message)s')
    file_handler.setFormatter(file_formatter)
    app_logger.addHandler(file_handler)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    app_logger.addHandler(console_handler)
    app_logger.info(f"Logging configuré. Console: INFO, Fichier: DEBUG -> {log_filepath}")


def main():
    setup_logging()
    logger = logging.getLogger("RobotApp")
    logger.info("Démarrage de l'application Robot Controller.")
    robot_instance = None
    try:
        # Assurez-vous que ce chemin est correct par rapport à l'endroit où vous exécutez main.py
        # Si main.py est à la racine, 'config.ini' est correct.
        config_path = 'config.ini'

        config = configparser.ConfigParser()
        if not config.read(config_path):
            raise FileNotFoundError(f"Fichier {config_path} non trouvé.")

        driver = GalilDriver(
            port=config.get('SERIAL', 'port'),
            baudrate=config.getint('SERIAL', 'baudrate'),
            timeout=config.getfloat('SERIAL', 'timeout')
        )
        # On passe l'objet config déjà chargé
        robot_instance = RobotController(driver, config)

        if robot_instance.connect():
            robot_instance.enable_motors()
            robot_instance.define_current_position_as_zero()

            # --- CHOISIR LE MODE D'EXECUTION ---
            # 1. Lancer la séquence de test
            #run_movement_test_sequence(robot_instance)

            # 2. Lancer le contrôle manuel interactif
            if pygame:
                logger.info("Lancement du contrôle manuel au clavier...")
                time.sleep(1)
                run_live_keyboard_control(robot_instance)
            else:
                logger.warning("Contrôle manuel ignoré car Pygame n'est pas installé.")

    except Exception as e:
        logger.critical(f"Une erreur majeure a interrompu l'application: {e}", exc_info=True)
    finally:
        if robot_instance and robot_instance.driver.is_connected:
            logger.info("Nettoyage final...")
            robot_instance.stop_all_motion()
            robot_instance.disable_motors()
            robot_instance.disconnect()
        if pygame and pygame.get_init():
            pygame.quit()
        logger.info("Application terminée.")


if __name__ == '__main__':
    main()