# main.py
import configparser
import logging
import os
import time

import pythoncom
import threading

# Importer la classe du driver depuis le fichier bibliothèque
from PulseLabshopDriver import PulseLabshopDriver


def setup_logging():
    """Configure les loggers pour l'application."""
    log_format = '%(asctime)s - [%(levelname)s] (%(threadName)s) %(name)s: %(message)s'

    # Le logger racine gère tous les messages par défaut
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Handler pour la console, montre les messages INFO et plus importants
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    if not root_logger.handlers:  # Ajouter le handler console seulement s'il n'y en a pas
        root_logger.addHandler(console_handler)

    # Réduire le bruit de comtypes sur la console
    logging.getLogger('comtypes').setLevel(logging.WARNING)
    # Le FileHandler sera ajouté par le driver lui-même


def main():
    """
    Point d'entrée principal de l'application.
    """
    setup_logging()
    logger = logging.getLogger("RobotApp.Main")

    logger.info("--- Démarrage de l'application principale ---")

    # Lire la configuration
    config = configparser.ConfigParser()
    config_path = 'config.ini'
    if not os.path.exists(config_path):
        logger.critical(f"Fichier de configuration '{config_path}' introuvable. Arrêt.")
        return

    config.read(config_path)
    pulse_settings = config['PulseSettings']

    project_path = pulse_settings.get('project_path')
    save_dir = pulse_settings.get('save_path_dir')
    fg_name = pulse_settings.get('function_group_to_save')
    log_dir = pulse_settings.get('log_dir')

    # Initialisation COM pour le thread principal
    try:
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        logger.debug("COM initialisé pour le thread principal.")
    except pythoncom.com_error:
        logger.debug("COM déjà initialisé pour le thread principal.")

    pulse_driver = None
    try:
        # Instancier le driver avec les paramètres du fichier de config
        pulse_driver = PulseLabshopDriver(
            project_path=project_path,
            save_path_dir=save_dir,
            function_group_name_to_save=fg_name,
            log_dir=log_dir
        )

        if pulse_driver.initialize_pulse():
            logger.info("<<<<< DRIVER PULSE INITIALISÉ AVEC SUCCÈS >>>>>")

            # Ici, vous pouvez intégrer la logique de votre application (GUI, séquence de tests, etc.)
            # Exemple de séquence :
            if pulse_driver.autorange():
                if pulse_driver.start_measurement():
                    # Attendre que la mesure se fasse
                    time.sleep(5)
                    pulse_driver.stop_measurement()

                    # Attendre la fin de la mesure via événement
                    timeout_completion = 10
                    start_wait = time.time()
                    while not pulse_driver.is_measurement_complete:
                        pythoncom.PumpWaitingMessages()
                        if (time.time() - start_wait) > timeout_completion:
                            logger.error("Timeout en attente de la complétion de la mesure.")
                            break
                        time.sleep(0.1)

                    if pulse_driver.is_measurement_complete:
                        logger.info("Mesure terminée. Sauvegarde des résultats...")
                        filename = f"Resultat_{time.strftime('%Y%m%d_%H%M%S')}.txt"
                        pulse_driver.save_function_group_ascii(filename)

            else:
                logger.error("Échec de l'autorange, la séquence de mesure est annulée.")

        else:
            logger.error("<<<<< ÉCHEC DE L'INITIALISATION DU DRIVER PULSE >>>>>")

    except Exception as e:
        logger.critical(f"Une erreur non gérée est survenue dans l'application principale : {e}", exc_info=True)
    finally:
        if pulse_driver:
            logger.info("Fermeture du driver PULSE...")
            pulse_driver.close()

        try:
            if threading.current_thread() is threading.main_thread():
                pythoncom.CoUninitialize()
                logger.debug("COM désinitialisé pour le thread principal.")
        except Exception:
            pass

        logger.info("--- Application principale terminée ---")


if __name__ == "__main__":
    main()