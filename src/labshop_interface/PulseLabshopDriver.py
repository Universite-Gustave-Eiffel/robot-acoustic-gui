# pulse_labshop_driver.py (Version Finale Propre - V19)
import comtypes.client
import comtypes.gen._98BA4851_F724_11CE_9645_0020AF34D7AC_0_1_0 as PulseTLB
import pythoncom
import time
import os
import logging
import gc
import threading

# --- Constantes Globales ---
PULSE_PROGID = 'Pulse.Labshop.Application'

# Valeurs d'état de mesure du Template (tirées de PulseTLB.BKTemplateMeasStateNotification)
PULSE_STATE_STOPPED = PulseTLB.BKMeasStopped  # 0
PULSE_STATE_SUSPENDING = PulseTLB.BKMeasSuspending  # 1
PULSE_STATE_RESUMING = PulseTLB.BKMeasResuming  # 2
PULSE_STATE_STARTED = PulseTLB.BKMeasStarted  # 3
PULSE_STATE_FRONTEND_NOT_DETECTED = PulseTLB.BKMeasFrontEndNotDetected  # 4
PULSE_STATE_TEMPLATE_SETTLED = PulseTLB.BKMeasTemplateSetled  # 5
PULSE_STATE_AUTORANGE_COMPLETE = PulseTLB.BKMeasTemplateAutorangeComplete  # 6
PULSE_STATE_AUTORANGE_DENIED = PulseTLB.BKMeasTemplateAutorangeDenied  # 7

# Messages d'événements principaux que nous surveillons
TEMPLATE_ACTIVATED_MESSAGE = PulseTLB.BKTemplateActivated  # 67174400
TEMPLATE_MEAS_STATE_MESSAGE = PulseTLB.BKTemplateMeasState  # 67239936

# Dictionnaire pour le logging lisible des événements et de leurs paramètres
# Clés: valeurs numériques des constantes, Valeurs: noms des constantes
BKNOTIFICATION_NAMES = {getattr(PulseTLB, name): name for name in dir(PulseTLB)
                        if name.startswith('BK') and isinstance(getattr(PulseTLB, name), int)}

# Ajout de formatage pour les paramètres d'événements spécifiques pour un meilleur logging
_event_param_maps = {
    TEMPLATE_MEAS_STATE_MESSAGE: {
        val: name for name, val in PulseTLB.BKTemplateMeasStateNotification.__dict__.items() if not name.startswith('_')
    },
    TEMPLATE_ACTIVATED_MESSAGE: {
        val: name for name, val in PulseTLB.BKTemplateActivatedResult.__dict__.items() if not name.startswith('_')
    }
}
for msg_type, param_dict in _event_param_maps.items():
    for val, name_str_base in param_dict.items():
        if val not in BKNOTIFICATION_NAMES or "RawParamValue" in BKNOTIFICATION_NAMES[
            val]:  # Évite d'écraser les noms de Message
            BKNOTIFICATION_NAMES[val] = f"{name_str_base}({val})"

logger = logging.getLogger("RobotApp.PulseDriver")


class PulseTemplateEvents:
    """
    Classe "Sink" pour recevoir les événements COM INotify2 du Template PULSE.
    Elle met à jour l'état du PulseLabshopDriver en fonction des notifications reçues.
    """

    def __init__(self, driver_instance):
        self.driver = driver_instance
        logger.debug("PulseTemplateEvents sink instancié.")

    def Notify2(self, NotifierObject, Message, Parameter):
        """
        Méthode de callback pour l'événement INotify2.
        NotifierObject: L'objet COM qui a émis l'événement (ici, le Template).
        Message: L'ID numérique du type de notification (ex: BKTemplateMeasState).
        Parameter: Une valeur numérique associée au message (ex: l'état de mesure actuel).
        """
        try:
            event_source_name = "Objet Inconnu"
            if NotifierObject:
                try:
                    event_source_name = getattr(NotifierObject, 'Name', "Objet sans nom")
                except Exception:
                    pass  # Pas critique si le nom n'est pas récupérable

            message_name = BKNOTIFICATION_NAMES.get(Message, f"RawMsgValue({Message})")
            param_map = _event_param_maps.get(Message,
                                              BKNOTIFICATION_NAMES)  # Utiliser la map spécifique si elle existe
            param_name_decoded = param_map.get(Parameter, f"RawParamValue({Parameter})")

            log_level = logging.DEBUG  # Par défaut
            if Message == TEMPLATE_MEAS_STATE_MESSAGE or Message == TEMPLATE_ACTIVATED_MESSAGE:
                log_level = logging.INFO  # Ces messages sont clés pour le suivi

            logger.log(log_level,
                       f"Événement Notify2: Source='{event_source_name}', Message='{message_name}', Parameter='{param_name_decoded}'")

            # --- Gestion des états basée sur les événements ---
            if Message == TEMPLATE_MEAS_STATE_MESSAGE:
                if Parameter == PULSE_STATE_STARTED:
                    logger.info("  -> Mesure DÉMARRÉE.")
                    self.driver.is_measurement_active = True
                    self.driver.is_measurement_complete = False
                    self.driver.is_template_ready_for_measurement = True  # Mesure démarrée implique template prêt
                    self.driver.autorange_in_progress_event = False  # L'autorange est terminé si la mesure démarre
                    if self.driver.on_measurement_started_callback: self.driver.on_measurement_started_callback()
                elif Parameter == PULSE_STATE_STOPPED:
                    logger.info("  -> Mesure ARRÊTÉE.")
                    self.driver.is_measurement_active = False
                    self.driver.is_measurement_complete = True
                    self.driver.autorange_in_progress_event = False
                    if self.driver.on_measurement_stopped_callback: self.driver.on_measurement_stopped_callback()
                elif Parameter == PULSE_STATE_TEMPLATE_SETTLED:
                    logger.info("  -> Template stabilisé (SETTLED). Prêt pour mesure.")
                    self.driver.is_template_ready_for_measurement = True
                    self.driver.autorange_in_progress_event = False  # Si settlé, l'autorange (si en cours) est fini
                elif Parameter == PULSE_STATE_AUTORANGE_COMPLETE:
                    logger.info("  -> Autoranging TERMINÉ (événement). Prêt pour mesure.")
                    self.driver.is_template_ready_for_measurement = True
                    self.driver.autorange_in_progress_event = False
                elif Parameter == PULSE_STATE_AUTORANGE_DENIED:
                    logger.error("  -> Autoranging REFUSÉ (événement). Template NON prêt.")
                    self.driver.is_template_ready_for_measurement = False
                    self.driver.autorange_in_progress_event = False
                elif Parameter == PULSE_STATE_FRONTEND_NOT_DETECTED:
                    logger.error("  -> ERREUR: Frontend non détecté. Template NON prêt.")
                    self.driver.is_template_ready_for_measurement = False
                    self.driver.is_measurement_active = False
                    self.driver.autorange_in_progress_event = False

            elif Message == TEMPLATE_ACTIVATED_MESSAGE:
                if Parameter == PulseTLB.BKTemplateActive:  # Valeur 1
                    logger.info("  -> Template confirmé ACTIF (BKTemplateActive). Prêt pour mesure.")
                    self.driver.is_template_ready_for_measurement = True
                elif Parameter == PulseTLB.BKTemplateInactive:  # Valeur 0
                    logger.info(
                        "  -> Template signalé INACTIF (BKTemplateInactive). État actuel de is_template_ready: %s",
                        self.driver.is_template_ready_for_measurement)
                    # On ne met à False que si ce n'est pas pendant la phase d'activation initiale
                    if not self.driver._is_activating_template_flag:
                        self.driver.is_template_ready_for_measurement = False
        except Exception as e:
            logger.error(f"Erreur dans le gestionnaire d'événement Notify2: {e}", exc_info=True)


class PulseLabshopDriver:
    """
    Driver pour contrôler PULSE LabShop via COM, en utilisant la gestion d'événements.
    """

    def __init__(self, project_path=None, save_path_dir=None, function_group_name_to_save="ASauver"):
        """
        Initialise le driver.
        :param project_path: Chemin complet vers le fichier projet PULSE (.pls) à charger.
                             Si None, un chemin par défaut est utilisé.
        :param save_path_dir: Répertoire de base pour sauvegarder les mesures en ASCII.
                              Si None, un chemin par défaut est utilisé.
        :param function_group_name_to_save: Nom du FunctionGroup à utiliser pour la sauvegarde ASCII.
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_path_to_load = project_path if project_path else \
            os.path.join(script_dir, "pulse_projects", "MinimalTest.pls")
        self.save_path_dir = save_path_dir if save_path_dir else \
            os.path.join(script_dir, "mesures_pulse_ascii")
        self.function_group_name_to_save_param = function_group_name_to_save

        logger.info(f"Chemin du projet à charger: {self.project_path_to_load}")
        logger.info(f"Répertoire de sauvegarde des mesures: {self.save_path_dir}")
        logger.info(f"Nom du FunctionGroup pour sauvegarde: {self.function_group_name_to_save_param}")

        self.pulse_app = None
        self.project = None
        self.active_template = None
        self.function_group_to_save = None  # L'objet COM réel

        # Drapeaux d'état internes
        self.is_measurement_active = False
        self.is_measurement_complete = True
        self.is_template_ready_for_measurement = False
        self._is_activating_template_flag = False  # Utilisé pour gérer les événements pendant l'activation
        self.autorange_in_progress_event = False  # Utilisé pour suivre l'autorange basé sur les événements

        # Callbacks pour l'application externe
        self.on_measurement_started_callback = None
        self.on_measurement_stopped_callback = None

        # Gestion des événements COM
        self.event_sink = None
        self.event_connection = None
        self.event_thread = None
        self.event_thread_running = False
        logger.info("PulseLabshopDriver instancié.")

    def _event_pump_loop(self):
        """Boucle exécutée dans un thread séparé pour pomper les messages COM."""
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        logger.debug("Thread de pompage des événements COM dédié démarré.")
        try:
            while self.event_thread_running:
                pythoncom.PumpWaitingMessages()
                time.sleep(0.05)  # Petit délai pour éviter une utilisation CPU excessive
        except Exception as e:
            logger.error(f"Erreur dans le thread de pompage dédié: {e}", exc_info=True)
        finally:
            if self.event_thread_running:  # Log seulement si on ne s'attendait pas à ce qu'il s'arrête
                logger.info("Thread de pompage des événements COM dédié arrêté.")
            pythoncom.CoUninitialize()

    def initialize_pulse(self):
        """
        Initialise la connexion à PULSE LabShop, ouvre le projet spécifié,
        active le premier template et se connecte à ses événements.
        Retourne True en cas de succès, False sinon.
        """
        logger.info(f"Initialisation de PULSE LabShop avec projet: {self.project_path_to_load}")
        self.is_template_ready_for_measurement = False  # Réinitialiser l'état
        try:
            # Connexion ou création de l'application PULSE
            try:
                self.pulse_app = comtypes.client.GetActiveObject(PULSE_PROGID, dynamic=True)
                if not self.pulse_app: raise pythoncom.com_error  # GetActiveObject peut retourner None
                logger.info("Connecté à une instance PULSE existante.")
            except (pythoncom.com_error, OSError):  # OSError pour "Invalid class string" si non enregistré
                logger.info("Aucune instance PULSE existante trouvée ou erreur. Lancement d'une nouvelle instance...")
                self.pulse_app = comtypes.client.CreateObject(PULSE_PROGID, dynamic=True)
                logger.info("Nouvelle instance PULSE lancée.")

            if not self.pulse_app:
                logger.critical("Échec de la connexion ou de la création de l'application PULSE.")
                return False

            logger.info(f"Version de PULSE LabShop : {self.pulse_app.Version}")

            # Ouverture du projet
            if not self.project_path_to_load or not os.path.exists(self.project_path_to_load):
                logger.error(f"Chemin du projet PULSE non valide ou fichier inexistant : '{self.project_path_to_load}'")
                self.pulse_app = None  # Libérer la référence si l'ouverture échoue
                return False

            logger.info(f"Ouverture du projet PULSE : {self.project_path_to_load}")
            self.project = self.pulse_app.OpenProject(self.project_path_to_load, True)  # True = ferme projet précédent
            if not self.project:
                logger.error(f"Échec de l'ouverture du projet PULSE '{self.project_path_to_load}'.")
                self.pulse_app = None
                return False

            self.pulse_app.Visible = True  # Rendre visible après l'ouverture réussie
            logger.info(f"Projet '{self.project.Name}' ouvert et Pulse rendu visible.")
            time.sleep(1)  # Laisser le temps à l'interface de se mettre à jour

            # Démarrer le thread de pompage des événements dédié
            # Il est démarré tôt pour attraper tous les événements dès le début des interactions
            if not (self.event_thread and self.event_thread.is_alive()):
                self.event_thread_running = True
                self.event_thread = threading.Thread(target=self._event_pump_loop, name="PulseEventPumpDedicated",
                                                     daemon=True)
                self.event_thread.start()
                logger.debug("Thread de pompage des événements dédié démarré.")

            # Détection du matériel (optionnel mais recommandé pour s'assurer que Pulse voit bien le matériel)
            if self.project.ConfigurationOrganiser:
                logger.info("Appel à ConfigurationOrganiser.DetectFrontend()...")
                try:
                    self.project.ConfigurationOrganiser.DetectFrontend()
                    logger.info("DetectFrontend() terminé.")
                    time.sleep(2)  # Laisser le temps pour que les informations se propagent
                except pythoncom.com_error as e_detect:
                    logger.warning(f"Erreur lors de DetectFrontend: {e_detect}. Poursuite de l'initialisation.")
            else:
                logger.warning("ConfigurationOrganiser non disponible sur l'objet Project.")

            # Localisation du FunctionGroup pour la sauvegarde
            if self.project.FunctionOrganiser:
                fg_collection = self.project.FunctionOrganiser.FunctionGroups
                if fg_collection and fg_collection.Count > 0:
                    try:
                        self.function_group_to_save = fg_collection.Item(self.function_group_name_to_save_param)
                        logger.info(
                            f"FunctionGroup '{self.function_group_name_to_save_param}' trouvé pour la sauvegarde.")
                    except pythoncom.com_error:
                        logger.warning(
                            f"FunctionGroup '{self.function_group_name_to_save_param}' non trouvé dans le projet. La sauvegarde ASCII ne sera pas effectuée avec ce groupe.")
                        self.function_group_to_save = None
                else:
                    logger.warning(
                        f"Aucun FunctionGroup trouvé dans l'Organisateur de Fonctions du projet '{self.project.Name}'.")
            else:
                logger.warning("FunctionOrganiser non disponible dans le projet. Sauvegarde ASCII impossible.")

            # Accès et activation du template
            if not self.project.MeasurementOrganiser or self.project.MeasurementOrganiser.Templates.Count == 0:
                logger.error(f"Aucun template de mesure trouvé dans le projet '{self.project.Name}'.")
                self._close_project_and_app(ask_save=False, app_already_set=True)  # Nettoyer
                return False

            template_id = 1  # On suppose que le premier template est celui à utiliser pour ce driver
            try:
                self.active_template = self.project.MeasurementOrganiser.Templates.Item(template_id)
            except pythoncom.com_error as e:
                logger.error(f"Erreur COM lors de l'accès au template (ID/Index: {template_id}): {e}")
                self._close_project_and_app(ask_save=False, app_already_set=True)
                return False
            if not self.active_template:
                logger.error(f"Impossible de récupérer le template (ID/Index: {template_id}).")
                self._close_project_and_app(ask_save=False, app_already_set=True)
                return False
            logger.info(f"Utilisation du template '{self.active_template.Name}' (ID/Index: {template_id}).")

            # Connexion aux événements du template
            self.event_sink = PulseTemplateEvents(self)
            self.event_connection = comtypes.client.GetEvents(self.active_template, self.event_sink,
                                                              interface=PulseTLB.INotify2)
            logger.info(f"Connecté aux événements INotify2 du template '{self.active_template.Name}'.")

            self._is_activating_template_flag = True  # Indique qu'on attend l'activation
            logger.info("Activation du template...")
            self.active_template.ActivateTemplate()  # Opération asynchrone
            logger.info("Commande ActivateTemplate envoyée.")

            # Vérification synchrone de la propriété .Active (peut donner une indication rapide)
            try:
                is_active_sync = self.active_template.Active
                logger.info(
                    f"État synchrone du template (propriété .Active) juste après l'appel à ActivateTemplate() : {is_active_sync}")
                if is_active_sync:  # Peu probable, mais si c'est le cas, on est prêt
                    logger.info("  -> La propriété .Active est True, template considéré prêt (synchrone).")
                    self.is_template_ready_for_measurement = True
            except Exception as e_active_prop:
                logger.warning(f"Impossible de lire la propriété active_template.Active : {e_active_prop}")

            # Boucle d'attente pour que le template devienne prêt, basée sur les événements
            timeout_template_ready = 60  # secondes
            start_wait_template = time.time()
            logger.info(f"Attente que le template devienne prêt via événement (timeout: {timeout_template_ready}s)...")

            while not self.is_template_ready_for_measurement:
                if (time.time() - start_wait_template) > timeout_template_ready:
                    logger.error(f"Timeout ({timeout_template_ready}s): Template non confirmé prêt par événement.")
                    self._is_activating_template_flag = False
                    return False  # Échec de l'initialisation car le template n'est pas devenu prêt

                pythoncom.PumpWaitingMessages()  # Pompage dans le thread principal
                time.sleep(0.05)

            self._is_activating_template_flag = False  # Fin de la phase d'activation
            logger.info("Template confirmé prêt pour la mesure.")

            logger.info("Initialisation de PULSE terminée avec succès.")
            return True

        except pythoncom.com_error as e:
            logger.critical(f"Erreur COM majeure lors de l'initialisation: {e}", exc_info=True)
        except Exception as e:
            logger.critical(f"Erreur générale majeure lors de l'initialisation: {e}", exc_info=True)

        # Nettoyage en cas d'exception avant un retour réussi
        self._is_activating_template_flag = False
        if hasattr(self, 'pulse_app') and self.pulse_app:  # S'assurer que pulse_app a été assigné
            self._close_project_and_app(ask_save=False, app_already_set=True)
        return False

    def autorange(self):
        """Lance l'autorange et attend sa complétion via événement."""
        if not self.pulse_app or not self.active_template:
            logger.error("Impossible de lancer l'Autorange: PULSE non initialisé ou template non actif.")
            return False
        if not self.is_template_ready_for_measurement:
            logger.error("Impossible de lancer l'Autorange: le template n'est pas initialement prêt.")
            return False
        try:
            logger.info("Lancement de l'Autorange PULSE...")
            self.autorange_in_progress_event = True  # Indique au gestionnaire d'événements que l'on attend la fin de l'autorange

            com_call_result = self.pulse_app.Autorange()
            logger.info(f"Appel à pulse_app.Autorange() retourné: {com_call_result}")
            logger.info("Commande Autorange envoyée. Attente de l'événement de complétion/refus ou timeout...")

            timeout_autorange = 60  # secondes
            start_wait_autorange = time.time()

            while self.autorange_in_progress_event and self.is_template_ready_for_measurement:
                pythoncom.PumpWaitingMessages()  # Pompage dans le thread principal pendant l'attente
                if (time.time() - start_wait_autorange) > timeout_autorange:
                    logger.warning(f"Timeout ({timeout_autorange}s) en attente de la fin de l'autorange par événement.")
                    self.autorange_in_progress_event = False  # Forcer la sortie de la boucle
                    # L'état de is_template_ready_for_measurement sera vérifié après la boucle
                    break
                time.sleep(0.1)

            if not self.is_template_ready_for_measurement:
                logger.error("Autorange a été refusé ou a rendu le template non prêt.")
                return False

            logger.info(
                f"Cycle d'attente de l'Autorange terminé. État de is_template_ready: {self.is_template_ready_for_measurement}")
            return self.is_template_ready_for_measurement

        except pythoncom.com_error as e:
            logger.error(f"Erreur COM lors de l'Autorange: {e}", exc_info=True)
            self.autorange_in_progress_event = False
            return False
        except Exception as e:
            logger.error(f"Erreur générale lors de l'Autorange: {e}", exc_info=True)
            self.autorange_in_progress_event = False
            return False

    def start_measurement(self):
        """Démarre la mesure sur le template actif."""
        if not self.pulse_app or not self.active_template:
            logger.error("Impossible de démarrer la mesure: PULSE non initialisé ou template non actif.")
            return False
        if not self.is_template_ready_for_measurement:
            logger.error("Impossible de démarrer la mesure: le template n'est pas prêt.")
            return False
        try:
            if self.is_measurement_active:
                logger.warning("Tentative de démarrer une mesure déjà active. Ignoré.")
                return True
            logger.info("Démarrage de la mesure PULSE...")
            self.is_measurement_complete = False  # La mesure va commencer
            self.pulse_app.Start()
            logger.info("Commande Start envoyée à PULSE.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors du démarrage de la mesure: {e}", exc_info=True)
            return False

    def stop_measurement(self):
        """Arrête la mesure en cours."""
        if not self.pulse_app:
            logger.warning("PULSE non initialisé, impossible d'arrêter la mesure.")
            return False
        try:
            if not self.is_measurement_active and self.is_measurement_complete:
                logger.info("Tentative d'arrêter une mesure déjà arrêtée/complète. Ignoré.")
                return True  # Considéré comme un succès car l'état désiré est atteint
            logger.info("Arrêt de la mesure PULSE...")
            self.pulse_app.Stop()
            logger.info("Commande Stop envoyée à PULSE.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt de la mesure: {e}", exc_info=True)
            return False

    def save_function_group_ascii(self, filename_suffix):
        """
        Sauvegarde le FunctionGroup spécifié dans __init__ en format ASCII.
        :param filename_suffix: Suffixe à ajouter au nom du fichier (ex: "data_run_1.txt").
        """
        if not self.function_group_to_save:
            logger.error(
                f"Impossible de sauvegarder (ASCII): FunctionGroup '{self.function_group_name_to_save_param}' non défini ou non trouvé.")
            return False
        if not self.project or not self.pulse_app:  # Vérification supplémentaire
            logger.error("Impossible de sauvegarder (ASCII): Projet ou application Pulse non disponibles.")
            return False

        if not os.path.isdir(self.save_path_dir):
            try:
                os.makedirs(self.save_path_dir, exist_ok=True)
                logger.info(f"Création du répertoire de sauvegarde : {self.save_path_dir}")
            except OSError as e:
                logger.error(f"Impossible de créer le répertoire de sauvegarde '{self.save_path_dir}': {e}")
                return False

        if filename_suffix.startswith(("\\", "/")):
            filename_suffix = os.path.basename(filename_suffix)

        full_file_path = os.path.join(self.save_path_dir, filename_suffix)

        fg_name_log = getattr(self.function_group_to_save, 'Name', self.function_group_name_to_save_param)
        logger.info(f"Sauvegarde du FunctionGroup '{fg_name_log}' en ASCII vers : {full_file_path}")
        try:
            success = self.function_group_to_save.SavePulseAscii(full_file_path)
            if success:
                logger.info(f"FunctionGroup sauvegardé avec succès en ASCII dans '{full_file_path}'.")
            else:
                logger.error(
                    f"Échec de la sauvegarde ASCII du FunctionGroup vers '{full_file_path}' (méthode a retourné False).")
            return success
        except pythoncom.com_error as e:
            logger.error(f"Erreur COM lors de la sauvegarde ASCII vers '{full_file_path}': {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Erreur générale lors de la sauvegarde ASCII vers '{full_file_path}': {e}", exc_info=True)
            return False

    def _close_project_and_app(self, ask_save=False, app_already_set=True):
        """Méthode interne pour fermer le projet et l'application PULSE."""
        # Arrêter le thread d'événements en premier
        if self.event_thread and self.event_thread.is_alive():
            logger.debug("Arrêt du thread de pompage des événements dédié...")
            self.event_thread_running = False
            self.event_thread.join(timeout=2)
            if self.event_thread.is_alive():
                logger.warning("Le thread de pompage des événements dédié n'a pas pu être arrêté proprement.")
            else:
                logger.info("Thread de pompage des événements dédié arrêté.")
        self.event_thread = None

        # Fermer le projet
        if self.project and self.pulse_app and app_already_set:
            try:
                project_name_to_log = "Projet Invalide"
                try:
                    project_name_to_log = self.project.Name
                except:
                    pass  # Si l'objet est déjà invalide
                logger.debug(f"Fermeture du projet '{project_name_to_log}'...")
                self.pulse_app.CloseProject(ask_save)  # False pour ne pas sauvegarder
                logger.info(f"Projet '{project_name_to_log}' fermé.")
            except Exception as e_cp:
                logger.warning(f"Erreur lors de la fermeture du projet: {e_cp}")
        self.project = None  # Libérer la référence

        # Quitter l'application
        current_pulse_app_ref = self.pulse_app  # Garder une référence pour Exit
        if current_pulse_app_ref and app_already_set:
            try:
                logger.debug("Fermeture de l'application PULSE...")
                current_pulse_app_ref.Exit(False)  # False pour ne pas sauvegarder et fermer
                logger.info("Commande Exit envoyée à PULSE.")
                time.sleep(1.5)  # Laisser le temps à Pulse de se fermer
            except Exception as e_exit:
                logger.warning(f"Erreur lors de Exit(): {e_exit}")

        self.pulse_app = None  # S'assurer que la référence du driver est nulle
        self._release_com_objects()  # Nettoyer les autres références COM du driver
        if current_pulse_app_ref:
            logger.debug("Référence locale à pulse_app (current_pulse_app_ref) libérée après Exit.")

    def _release_com_objects(self):
        """Libère les références aux objets COM internes."""
        logger.debug("Libération des objets COM internes du driver...")
        if self.event_connection:
            try:
                if hasattr(self.event_connection, 'disconnect'): self.event_connection.disconnect()
                logger.debug("Déconnexion des événements.")
            except Exception:
                pass  # Ignorer les erreurs ici, l'objet pourrait déjà être invalide
            self.event_connection = None
        if self.event_sink: self.event_sink = None; logger.debug("Référence au Sink d'événements libérée.")
        if self.active_template: self.active_template = None; logger.debug("Référence au Template actif libérée.")
        if self.project: self.project = None; logger.debug("Référence au Projet libérée.")
        if self.function_group_to_save: self.function_group_to_save = None; logger.debug(
            "Référence au FunctionGroup à sauvegarder libérée.")

        # self.pulse_app est normalement mis à None par _close_project_and_app
        # Mais au cas où cette méthode est appelée directement :
        if self.pulse_app: self.pulse_app = None; logger.debug("Référence à l'application Pulse libérée.")

        gc.collect()
        gc.collect()  # Forcer le garbage collection
        logger.debug("Garbage collection effectué.")

    def close(self):
        """Ferme proprement la connexion à PULSE LabShop et libère les ressources."""
        logger.info("Fermeture de la connexion à PULSE LabShop...")
        self._close_project_and_app(ask_save=False, app_already_set=bool(self.pulse_app))
        logger.info("Fermeture du driver PulseLabshop terminée.")

    def kill_pulse_processes(self):
        """Tente de terminer tous les processus Pulse.exe en cours."""
        logger.warning("Tentative de terminer les processus PULSE.exe...")
        try:
            result = os.system('taskkill /F /IM Pulse.exe /T > nul 2>&1')
            if result == 0:
                logger.info("Commande taskkill pour Pulse.exe exécutée avec succès.")
            elif result == 128:
                logger.info("Aucun processus Pulse.exe trouvé à terminer.")
            else:
                logger.warning(f"La commande taskkill pour Pulse.exe a retourné le code {result}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la tentative de terminer les processus PULSE: {e}")
            return False


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - [%(levelname)s] (%(threadName)s) %(name)s: %(message)s')
    logging.getLogger('comtypes').setLevel(logging.WARNING)  # Réduire bruit comtypes
    logger.setLevel(logging.DEBUG)  # Mettre en DEBUG pour voir tous les messages du driver pendant le test

    try:
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        logger.debug("COM initialisé pour le thread principal.")
    except pythoncom.com_error:
        pass

    pulse_driver = None
    try:
        # Test avec les chemins et nom de FG par défaut définis dans le constructeur
        pulse_driver = PulseLabshopDriver()

        if not os.path.exists(pulse_driver.project_path_to_load):
            logger.critical(
                f"ERREUR: Le fichier projet par défaut '{pulse_driver.project_path_to_load}' est introuvable. "
                "Veuillez le créer manuellement ou spécifier un chemin valide lors de l'instanciation du driver.")
        elif pulse_driver.initialize_pulse():
            logger.info("PULSE (projet minimal) initialisé avec succès.")
            # pulse_app.Visible est déjà géré dans initialize_pulse
            time.sleep(1)


            def measurement_started_cb():
                logger.info("CALLBACK: Mesure démarrée !")


            def measurement_stopped_cb():
                logger.info("CALLBACK: Mesure terminée !")


            pulse_driver.on_measurement_started_callback = measurement_started_cb
            pulse_driver.on_measurement_stopped_callback = measurement_stopped_cb

            if pulse_driver.is_template_ready_for_measurement:
                logger.info("Tentative d'Autorange...")
                autorange_completed_successfully = pulse_driver.autorange()

                if autorange_completed_successfully:
                    logger.info("Autorange a réussi.")
                    if not pulse_driver.is_template_ready_for_measurement:  # Double check
                        logger.error("Problème: Autorange OK, mais template non prêt ensuite. Mesure annulée.")
                    elif pulse_driver.start_measurement():
                        logger.info("start_measurement envoyé après autorange.")
                        timeout_start = 30
                        start_time_wait = time.time()
                        while not pulse_driver.is_measurement_active and (
                                time.time() - start_time_wait) < timeout_start:
                            pythoncom.PumpWaitingMessages()
                            time.sleep(0.1)

                        if pulse_driver.is_measurement_active:
                            logger.info("Mesure confirmée ACTIVE.")
                            logger.info("Simulation durée de mesure de 5 secondes...")
                            time.sleep(5)
                            pulse_driver.stop_measurement()
                            logger.info("stop_measurement envoyé.")
                            timeout_stop = 10
                            stop_time_wait = time.time()
                            while not pulse_driver.is_measurement_complete and (
                                    time.time() - stop_time_wait) < timeout_stop:
                                pythoncom.PumpWaitingMessages()
                                time.sleep(0.1)
                            if pulse_driver.is_measurement_complete:
                                logger.info("Mesure confirmée COMPLÈTE.")
                                filename_suffix = f"MinTest_FG_{pulse_driver.function_group_name_to_save_param}_{time.strftime('%Y%m%d_%H%M%S')}.txt"
                                pulse_driver.save_function_group_ascii(filename_suffix)
                            else:
                                logger.error("Timeout: Mesure non confirmée complète post-stop.")
                        else:
                            logger.error("Timeout/Échec: Mesure non active post-autorange/start.")
                    else:
                        logger.error("Échec envoi commande start_measurement post-autorange.")
                else:
                    logger.error("Échec Autorange ou template non prêt. Mesure non tentée.")
            else:
                logger.error("Template non prêt après initialize_pulse. Test de mesure annulé.")
            time.sleep(1)
        else:
            logger.error("Échec initialisation PULSE avec projet minimal.")

    except Exception as e_main_test:
        logger.critical(f"Erreur critique test principal: {e_main_test}", exc_info=True)
    finally:
        if pulse_driver:
            pulse_driver.close()
        try:
            if threading.current_thread() is threading.main_thread():
                pythoncom.CoUninitialize()
                logger.debug("COM désinitialisé pour le thread principal (fin).")
        except Exception:
            pass

        logger.info(f"Fin du test V18 (sans _log_hardware_details).")