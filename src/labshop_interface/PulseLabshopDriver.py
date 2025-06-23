# pulse_labshop_driver_v20_filelog_no_hwdetails.py
import comtypes.client
import comtypes.gen._98BA4851_F724_11CE_9645_0020AF34D7AC_0_1_0 as PulseTLB
import pythoncom
import time
import os
import logging
import logging.handlers  # Ajouté pour FileHandler
import gc
import threading

# --- Constantes Globales ---
PULSE_PROGID = 'Pulse.Labshop.Application'
PULSE_STATE_STOPPED = PulseTLB.BKMeasStopped
PULSE_STATE_SUSPENDING = PulseTLB.BKMeasSuspending
PULSE_STATE_RESUMING = PulseTLB.BKMeasResuming
PULSE_STATE_STARTED = PulseTLB.BKMeasStarted
PULSE_STATE_FRONTEND_NOT_DETECTED = PulseTLB.BKMeasFrontEndNotDetected
PULSE_STATE_TEMPLATE_SETTLED = PulseTLB.BKMeasTemplateSetled
PULSE_STATE_AUTORANGE_COMPLETE = PulseTLB.BKMeasTemplateAutorangeComplete
PULSE_STATE_AUTORANGE_DENIED = PulseTLB.BKMeasTemplateAutorangeDenied
TEMPLATE_ACTIVATED_MESSAGE = PulseTLB.BKTemplateActivated
TEMPLATE_MEAS_STATE_MESSAGE = PulseTLB.BKTemplateMeasState

BKNOTIFICATION_NAMES = {getattr(PulseTLB, name): name for name in dir(PulseTLB)
                        if name.startswith('BK') and isinstance(getattr(PulseTLB, name), int)}
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
        if val not in BKNOTIFICATION_NAMES or "RawParamValue" in BKNOTIFICATION_NAMES[val]:
            BKNOTIFICATION_NAMES[val] = f"{name_str_base}({val})"

logger = logging.getLogger("RobotApp.PulseDriver")  # Logger principal de l'application


class PulseTemplateEvents:
    # ... (Identique à la version précédente V19) ...
    def __init__(self, driver_instance):
        self.driver = driver_instance
        logger.debug("PulseTemplateEvents sink instancié.")

    def Notify2(self, NotifierObject, Message, Parameter):
        try:
            event_source_name = "Objet Inconnu"
            if NotifierObject:
                try:
                    event_source_name = getattr(NotifierObject, 'Name', "Objet sans nom")
                except Exception:
                    pass

            message_name = BKNOTIFICATION_NAMES.get(Message, f"RawMsgValue({Message})")
            param_map = _event_param_maps.get(Message, BKNOTIFICATION_NAMES)
            param_name_decoded = param_map.get(Parameter, f"RawParamValue({Parameter})")

            log_level = logging.DEBUG
            if Message == TEMPLATE_MEAS_STATE_MESSAGE or Message == TEMPLATE_ACTIVATED_MESSAGE:
                log_level = logging.INFO

            logger.log(log_level,
                       f"Événement Notify2: Source='{event_source_name}', Message='{message_name}', Parameter='{param_name_decoded}'")

            if Message == TEMPLATE_MEAS_STATE_MESSAGE:
                if Parameter == PULSE_STATE_STARTED:
                    logger.info("  -> Mesure DÉMARRÉE.")
                    self.driver.is_measurement_active = True
                    self.driver.is_measurement_complete = False
                    self.driver.is_template_ready_for_measurement = True
                    self.driver.autorange_in_progress_event = False
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
                    self.driver.autorange_in_progress_event = False
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
                if Parameter == PulseTLB.BKTemplateActive:
                    logger.info("  -> Template confirmé ACTIF (BKTemplateActive). Prêt pour mesure.")
                    self.driver.is_template_ready_for_measurement = True
                elif Parameter == PulseTLB.BKTemplateInactive:
                    logger.info(
                        "  -> Template signalé INACTIF (BKTemplateInactive). État actuel de is_template_ready: %s",
                        self.driver.is_template_ready_for_measurement)
                    if not self.driver._is_activating_template_flag:
                        self.driver.is_template_ready_for_measurement = False
        except Exception as e:
            logger.error(f"Erreur dans Notify2: {e}", exc_info=True)


class PulseLabshopDriver:
    # ... (__init__ modifié pour les chemins de log, _event_pump_loop) ...
    def __init__(self, project_path=None, save_path_dir=None, function_group_name_to_save="ASauver", log_dir=None):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_path_to_load = project_path if project_path else \
            os.path.join(script_dir, "pulse_projects", "MinimalTest.pls")
        self.save_path_dir = save_path_dir if save_path_dir else \
            os.path.join(script_dir, "mesures_pulse_ascii")
        self.function_group_name_to_save_param = function_group_name_to_save

        self.log_dir_param = log_dir if log_dir else os.path.join(script_dir, "logs_pulse_driver")
        self._setup_file_logging()  # Configurer le logging vers fichier

        logger.info(f"Chemin du projet à charger: {self.project_path_to_load}")
        logger.info(f"Répertoire de sauvegarde des mesures: {self.save_path_dir}")
        logger.info(f"Nom du FunctionGroup pour sauvegarde: {self.function_group_name_to_save_param}")
        logger.info(f"Répertoire des logs du driver: {self.log_dir_param}")

        self.pulse_app = None
        self.project = None
        self.active_template = None
        self.function_group_to_save = None

        self.is_measurement_active = False
        self.is_measurement_complete = True
        self.is_template_ready_for_measurement = False
        self._is_activating_template_flag = False
        self.autorange_in_progress_event = False

        self.on_measurement_started_callback = None
        self.on_measurement_stopped_callback = None

        self.event_sink = None
        self.event_connection = None
        self.event_thread = None
        self.event_thread_running = False
        logger.info("PulseLabshopDriver (V20 - LogFile) instancié.")

    def _setup_file_logging(self):
        """Configure un FileHandler pour le logger principal de cette application."""
        if not os.path.exists(self.log_dir_param):
            try:
                os.makedirs(self.log_dir_param, exist_ok=True)
            except OSError as e:
                logger.error(
                    f"Impossible de créer le répertoire de logs '{self.log_dir_param}': {e}. Les logs fichier seront désactivés.")
                return

        log_filename = f"pulse_driver_log_{time.strftime('%Y%m%d_%H%M%S')}.log"
        log_filepath = os.path.join(self.log_dir_param, log_filename)

        file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
        # Mettre un niveau plus détaillé pour le fichier si souhaité, par exemple DEBUG
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - [%(levelname)s] (%(threadName)s) %(name)s: %(message)s')
        file_handler.setFormatter(formatter)

        # Ajouter ce handler au logger racine ou au logger spécifique de l'application
        # Ici, on l'ajoute au logger spécifique "RobotApp.PulseDriver"
        app_logger = logging.getLogger("RobotApp.PulseDriver")
        app_logger.addHandler(file_handler)
        app_logger.info(f"Logging vers fichier configuré: {log_filepath}")

    def _event_pump_loop(self):
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        logger.debug("Thread de pompage des événements COM dédié démarré.")
        try:
            while self.event_thread_running:
                pythoncom.PumpWaitingMessages()
                time.sleep(0.05)
        except Exception as e:
            logger.error(f"Erreur thread pompe dédié: {e}", exc_info=True)
        finally:
            if self.event_thread_running:
                logger.debug("Thread de pompage des événements COM dédié arrêté.")
            pythoncom.CoUninitialize()

    def initialize_pulse(self):
        logger.info(f"Initialisation de PULSE LabShop avec projet: {self.project_path_to_load}")
        self.is_template_ready_for_measurement = False
        try:
            try:
                self.pulse_app = comtypes.client.GetActiveObject(PULSE_PROGID, dynamic=True)
                if not self.pulse_app: raise pythoncom.com_error
                logger.info("Connecté à instance PULSE existante.")
            except (pythoncom.com_error, OSError):
                logger.info("Lancement nouvelle instance PULSE...")
                self.pulse_app = comtypes.client.CreateObject(PULSE_PROGID, dynamic=True)
                logger.info("Nouvelle instance PULSE lancée.")

            if not self.pulse_app: logger.critical("Échec connexion/création PULSE."); return False
            logger.info(f"Version PULSE: {self.pulse_app.Version}")

            if not self.project_path_to_load or not os.path.exists(self.project_path_to_load):
                logger.error(f"Chemin projet '{self.project_path_to_load}' invalide.")
                self.pulse_app = None
                return False

            logger.info(f"Ouverture du projet PULSE: {self.project_path_to_load}")
            self.project = self.pulse_app.OpenProject(self.project_path_to_load, True)
            if not self.project:
                logger.error(f"Échec ouverture projet '{self.project_path_to_load}'.")
                self.pulse_app = None
                return False

            self.pulse_app.Visible = True
            logger.info(f"Projet '{self.project.Name}' ouvert et Pulse visible.")
            time.sleep(1)

            if not (self.event_thread and self.event_thread.is_alive()):
                self.event_thread_running = True
                self.event_thread = threading.Thread(target=self._event_pump_loop, name="PulseEventPumpDedicated",
                                                     daemon=True)
                self.event_thread.start()
                logger.debug("Thread de pompage des événements dédié démarré.")

            if self.project.ConfigurationOrganiser:
                logger.info("Appel à ConfigurationOrganiser.DetectFrontend()...")
                try:
                    self.project.ConfigurationOrganiser.DetectFrontend()
                    logger.info("DetectFrontend() terminé.")
                    time.sleep(2)
                    # _log_hardware_details est supprimé
                except pythoncom.com_error as e_detect:
                    logger.warning(f"Erreur lors de DetectFrontend: {e_detect}")
            else:
                logger.warning("ConfigurationOrganiser non disponible sur l'objet Project.")

            if self.project.FunctionOrganiser:
                fg_collection = self.project.FunctionOrganiser.FunctionGroups
                if fg_collection and hasattr(fg_collection, 'Count') and fg_collection.Count > 0:
                    try:
                        self.function_group_to_save = fg_collection.Item(self.function_group_name_to_save_param)
                        logger.info(
                            f"FunctionGroup '{self.function_group_name_to_save_param}' trouvé pour la sauvegarde.")
                    except pythoncom.com_error:
                        logger.warning(
                            f"FunctionGroup '{self.function_group_name_to_save_param}' non trouvé. Sauvegarde ASCII non possible.")
                        self.function_group_to_save = None
                else:
                    logger.warning(f"Aucun FunctionGroup dans '{self.project.Name}'.")
            else:
                logger.warning("FunctionOrganiser non disponible.")

            if not self.project.MeasurementOrganiser or not hasattr(self.project.MeasurementOrganiser.Templates,
                                                                    'Count') or self.project.MeasurementOrganiser.Templates.Count == 0:
                logger.error(f"Aucun template dans '{self.project.Name}'.")
                self._close_project_and_app()
                return False

            template_id = 1
            try:
                self.active_template = self.project.MeasurementOrganiser.Templates.Item(template_id)
            except pythoncom.com_error as e:
                logger.error(f"Erreur COM accès template ID {template_id}: {e}")
                self._close_project_and_app()
                return False
            if not self.active_template:
                logger.error(f"Impossible de récupérer template ID {template_id}.")
                self._close_project_and_app()
                return False
            logger.info(f"Utilisation du template '{self.active_template.Name}' (ID/Index: {template_id}).")

            self._log_generator_settings_from_template_setup()  # Log des params générateur

            self.event_sink = PulseTemplateEvents(self)
            self.event_connection = comtypes.client.GetEvents(self.active_template, self.event_sink,
                                                              interface=PulseTLB.INotify2)
            logger.info(f"Connecté aux événements INotify2 du template '{self.active_template.Name}'.")

            self._is_activating_template_flag = True
            logger.info("Activation du template...")
            self.active_template.ActivateTemplate()
            logger.info("Commande ActivateTemplate envoyée.")

            try:
                is_active_sync = self.active_template.Active
                logger.info(f"État synchrone du template (.Active) après ActivateTemplate() : {is_active_sync}")
                if is_active_sync:
                    logger.info("  -> .Active est True, on considère le template prêt (synchrone).")
                    self.is_template_ready_for_measurement = True
            except Exception as e_active_prop:
                logger.warning(f"Impossible de lire active_template.Active : {e_active_prop}")

            timeout_template_ready = 60
            start_wait_template = time.time()
            logger.info(f"Attente que le template devienne prêt via événement (timeout: {timeout_template_ready}s)...")

            while not self.is_template_ready_for_measurement:
                if (time.time() - start_wait_template) > timeout_template_ready:
                    logger.error(
                        f"Timeout: Template non confirmé prêt par événement dans les {timeout_template_ready}s.")
                    self._is_activating_template_flag = False
                    return False

                pythoncom.PumpWaitingMessages()
                time.sleep(0.05)

            self._is_activating_template_flag = False
            logger.info("Template confirmé prêt pour la mesure.")

            # _log_hardware_details est supprimé d'ici aussi
            logger.info("Initialisation PULSE terminée avec succès.")
            return True

        except pythoncom.com_error as e:
            logger.critical(f"Erreur COM majeure lors de l'initialisation: {e}", exc_info=True)
        except Exception as e:
            logger.critical(f"Erreur générale majeure lors de l'initialisation: {e}", exc_info=True)

        self._is_activating_template_flag = False
        if hasattr(self, 'pulse_app') and self.pulse_app:
            self._close_project_and_app(ask_save=False, app_already_set=True)
        return False

    def _log_generator_settings_from_template_setup(self):
        # ... (Identique à V19) ...
        if not self.active_template or not hasattr(self.active_template, "Setup"):
            logger.debug("Impossible de logger les paramètres du générateur: template ou setup non accessible.")
            return

        setup = self.active_template.Setup
        if not setup or not hasattr(setup, "Instruments"):
            logger.debug("Impossible de logger les paramètres du générateur: setup.Instruments non accessible.")
            return

        logger.info("--- Vérification des Paramètres du Générateur dans le Template ---")
        try:
            instruments = setup.Instruments
            found_generator = False
            for i in range(1, instruments.Count + 1):
                instrument = instruments.Item(i)
                if instrument and hasattr(instrument, "Kind") and "Generator" in instrument.Kind:
                    found_generator = True
                    logger.info(
                        f"Instrument Générateur trouvé: {getattr(instrument, 'Name', 'N/A')} (Kind: {instrument.Kind})")
                    if hasattr(setup, "StartGeneratorMode"): logger.info(
                        f"  Setup.StartGeneratorMode: {setup.StartGeneratorMode}")
                    if hasattr(setup, "StopGeneratorMode"): logger.info(
                        f"  Setup.StopGeneratorMode: {setup.StopGeneratorMode}")
                    if hasattr(setup, "MeasurementDelay"): logger.info(
                        f"  Setup.MeasurementDelay: {setup.MeasurementDelay}s")
                    if hasattr(setup, "GeneratorOnTime"): logger.info(
                        f"  Setup.GeneratorOnTime: {setup.GeneratorOnTime}s")

                    if hasattr(instrument, "Signals") and instrument.Signals.Count > 0:
                        gen_signals = instrument.Signals
                        logger.info(f"  Signaux configurés pour '{instrument.Name}':")
                        for j in range(1, gen_signals.Count + 1):
                            gen_signal = gen_signals.Item(j)
                            if gen_signal:
                                sig_name = getattr(gen_signal, "Name", f"SignalGen_{j}")
                                is_active = getattr(gen_signal, "GeneratorActive", "N/A")
                                waveform = getattr(gen_signal, "GeneratorWaveform", "N/A")
                                level1 = getattr(gen_signal, "SignalLevel1", "N/A")
                                freq1 = getattr(gen_signal, "Frequency1", "N/A")
                                logger.info(
                                    f"    Signal: {sig_name}, Active: {is_active}, Waveform: {waveform}, Level1: {level1}, Freq1: {freq1}")
                    else:
                        logger.info(f"  Aucun signal configuré pour l'instrument générateur '{instrument.Name}'.")
                    break
            if not found_generator: logger.info("Aucun instrument Signal Generator trouvé dans le setup du template.")
        except Exception as e:
            logger.error(f"Erreur lors du logging des paramètres du générateur: {e}", exc_info=True)
        logger.info("--- Fin Vérification Paramètres Générateur ---")

    def autorange(self):
        # ... (Identique à V17) ...
        if not self.pulse_app or not self.active_template:
            logger.error("Impossible Autorange: PULSE non initialisé ou template non actif.")
            return False
        if not self.is_template_ready_for_measurement:
            logger.error("Impossible Autorange: template non prêt.")
            return False
        try:
            logger.info("Lancement de l'Autorange PULSE...")
            self.autorange_in_progress_event = True

            com_call_result = self.pulse_app.Autorange()
            logger.info(f"Appel à pulse_app.Autorange() retourné: {com_call_result}")
            logger.info("Commande Autorange envoyée. Attente de l'événement de complétion/refus ou timeout...")

            timeout_autorange = 60
            start_wait_autorange = time.time()

            while self.autorange_in_progress_event and self.is_template_ready_for_measurement:
                pythoncom.PumpWaitingMessages()
                if (time.time() - start_wait_autorange) > timeout_autorange:
                    logger.warning(f"Timeout ({timeout_autorange}s) attente fin autorange par événement.")
                    self.autorange_in_progress_event = False
                    break
                time.sleep(0.1)

            if not self.is_template_ready_for_measurement:
                logger.error("Autorange refusé ou template non prêt après cycle d'attente Autorange.")
                return False

            logger.info(
                f"Autorange terminé (cycle d'attente). État de is_template_ready: {self.is_template_ready_for_measurement}")
            return self.is_template_ready_for_measurement

        except pythoncom.com_error as e:
            logger.error(f"Erreur COM Autorange: {e}", exc_info=True)
            self.autorange_in_progress_event = False
            return False
        except Exception as e:
            logger.error(f"Erreur générale Autorange: {e}", exc_info=True)
            self.autorange_in_progress_event = False
            return False

    def start_measurement(self):
        # ... (Identique à V17) ...
        if not self.pulse_app or not self.active_template:
            logger.error("Impossible de démarrer : PULSE non initialisé ou template non actif.")
            return False
        if not self.is_template_ready_for_measurement:
            logger.error("Impossible de démarrer : le template n'est pas prêt.")
            return False
        try:
            if self.is_measurement_active:
                logger.warning("Tentative de démarrer une mesure déjà active. Ignoré.")
                return True
            logger.info("Démarrage de la mesure PULSE...")
            self.is_measurement_complete = False
            self.pulse_app.Start()
            logger.info("Commande Start envoyée à PULSE (mesure et générateur si configuré).")
            return True
        except Exception as e:
            logger.error(f"Erreur lors du démarrage de la mesure PULSE : {e}", exc_info=True)
            return False

    def stop_measurement(self):
        # ... (Identique à V17) ...
        if not self.pulse_app:
            logger.warning("PULSE non initialisé, impossible d'arrêter.")
            return False
        try:
            if not self.is_measurement_active and self.is_measurement_complete:
                logger.info("Tentative d'arrêter une mesure déjà arrêtée/complète. Ignoré.")
                return True
            logger.info("Arrêt de la mesure PULSE...")
            self.pulse_app.Stop()
            logger.info("Commande Stop envoyée à PULSE (mesure et générateur si configuré).")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt de la mesure PULSE : {e}", exc_info=True)
            return False

    def save_function_group_ascii(self, filename_suffix):
        # ... (Identique à V17) ...
        if not self.function_group_to_save:
            logger.error(
                f"Impossible de sauvegarder (ASCII) : FunctionGroup '{self.function_group_name_to_save_param}' non défini ou non trouvé.")
            return False
        if not self.project or not self.pulse_app:
            logger.error("Impossible de sauvegarder (ASCII) : Projet ou application Pulse non disponibles.")
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
        # ... (Identique à V17) ...
        if self.event_thread and self.event_thread.is_alive():
            logger.debug("Arrêt du thread de pompage des événements dédié (depuis _close_project_and_app)...")
            self.event_thread_running = False
            self.event_thread.join(timeout=2)
            if self.event_thread.is_alive():
                logger.warning("Le thread de pompage des événements dédié n'a pas pu être arrêté proprement.")
            else:
                logger.info("Thread de pompage des événements dédié arrêté.")
        self.event_thread = None

        if self.project and self.pulse_app and app_already_set:
            try:
                project_name_to_log = "Projet Invalide"
                try:
                    project_name_to_log = self.project.Name
                except:
                    pass
                logger.debug(f"Fermeture du projet '{project_name_to_log}'...")
                self.pulse_app.CloseProject(ask_save)
                logger.info(f"Projet '{project_name_to_log}' fermé.")
            except Exception as e_cp:
                logger.warning(f"Erreur lors de la fermeture du projet: {e_cp}")
        self.project = None

        current_pulse_app_ref = self.pulse_app

        if self.pulse_app and app_already_set:
            try:
                logger.debug("Fermeture de l'application PULSE...")
                self.pulse_app.Exit(False)
                logger.info("Commande Exit envoyée à PULSE.")
                time.sleep(1.5)
            except Exception as e_exit:
                logger.warning(f"Erreur lors de Exit(): {e_exit}")

        self.pulse_app = None
        self._release_com_objects()
        if current_pulse_app_ref:
            logger.debug("Référence à pulse_app (current_pulse_app_ref) traitée.")

    def _release_com_objects(self):
        # ... (Identique à V17) ...
        logger.debug("Libération des objets COM internes du driver...")
        if self.event_connection:
            try:
                if hasattr(self.event_connection, 'disconnect'): self.event_connection.disconnect()
                logger.debug("Déconnexion des événements.")
            except Exception:
                pass
            self.event_connection = None
        if self.event_sink: self.event_sink = None; logger.debug("Réf Sink libérée.")
        if self.active_template: self.active_template = None; logger.debug("Réf Template libérée.")
        if self.project: self.project = None; logger.debug("Réf Projet libérée.")
        if self.function_group_to_save: self.function_group_to_save = None; logger.debug("Réf FG libérée.")
        gc.collect()
        gc.collect()
        logger.debug("Garbage collection.")

    def close(self):
        # ... (Identique à V17) ...
        logger.info("Fermeture de la connexion à PULSE LabShop...")
        self._close_project_and_app(ask_save=False, app_already_set=bool(self.pulse_app))
        logger.info("Fermeture du driver PulseLabshop terminée.")

    def kill_pulse_processes(self):
        # ... (Identique à V17) ...
        logger.warning("Tentative de terminer les processus PULSE.exe...")
        try:
            result = os.system('taskkill /F /IM Pulse.exe /T > nul 2>&1')
            if result == 0:
                logger.info("taskkill Pulse.exe OK.")
            elif result == 128:
                logger.info("Aucun processus Pulse.exe trouvé.")
            else:
                logger.warning(f"taskkill Pulse.exe code {result}.")
            return True
        except Exception as e:
            logger.error(f"Erreur kill_pulse_processes: {e}")
            return False


if __name__ == '__main__':
    # --- Configuration du Logging ---
    # Niveau de logging pour la console (peut être INFO pour moins de détails)
    CONSOLE_LOG_LEVEL = logging.INFO
    # Niveau de logging pour le fichier (peut être DEBUG pour tous les détails)
    FILE_LOG_LEVEL = logging.DEBUG

    # Créer le logger principal de l'application
    app_logger = logging.getLogger("RobotApp.PulseDriver")
    app_logger.setLevel(
        min(CONSOLE_LOG_LEVEL, FILE_LOG_LEVEL))  # Le logger doit être au niveau le plus bas des handlers

    # Supprimer les handlers existants pour éviter la duplication si le script est ré-exécuté dans un interpréteur
    # for handler in app_logger.handlers[:]:
    #     app_logger.removeHandler(handler)

    # Handler pour la console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(CONSOLE_LOG_LEVEL)
    console_formatter = logging.Formatter('%(asctime)s - [%(levelname)s] (%(threadName)s) %(name)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    if not any(isinstance(h, logging.StreamHandler) for h in app_logger.handlers):  # Éviter d'ajouter plusieurs fois
        app_logger.addHandler(console_handler)

    # Configuration du logger comtypes pour être moins verbeux sur la console
    logging.getLogger('comtypes').setLevel(logging.WARNING)

    # --- Fin Configuration Logging ---

    try:
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        logger.debug("COM initialisé pour le thread principal.")
    except pythoncom.com_error:
        logger.debug("COM déjà initialisé pour le thread principal ou erreur CoInitializeEx.")
        pass

    pulse_driver = None
    try:
        # Test avec les chemins et nom de FG par défaut définis dans le constructeur
        # Le driver va maintenant configurer son propre logging fichier dans __init__
        pulse_driver = PulseLabshopDriver()

        if not os.path.exists(pulse_driver.project_path_to_load):
            logger.critical(
                f"ERREUR: Le fichier projet par défaut '{pulse_driver.project_path_to_load}' est introuvable. "
                "Veuillez le créer manuellement ou spécifier un chemin valide lors de l'instanciation du driver.")
        elif pulse_driver.initialize_pulse():
            logger.info("PULSE (projet minimal) initialisé avec succès.")
            if pulse_driver.pulse_app: pulse_driver.pulse_app.Visible = True
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
                    if not pulse_driver.is_template_ready_for_measurement:
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
            pulse_driver.close()  # close s'occupe d'arrêter le thread et de libérer COM

        # CoUninitialize pour le thread principal est important s'il a été initialisé.
        # Il est préférable de le faire ici plutôt que dans close() du driver,
        # car le driver pourrait être utilisé par un thread qui n'est pas le principal.
        try:
            if threading.current_thread() is threading.main_thread():
                pythoncom.CoUninitialize()
                logger.debug("COM désinitialisé pour le thread principal (fin).")
        except Exception as e_final_co:  # pythoncom peut parfois lever une erreur si déjà désinitialisé
            logger.debug(f"Erreur CoUninitialize final (peut être normal): {e_final_co}")

        logger.info(f"Fin du test V19 (intégrant générateur implicite).")