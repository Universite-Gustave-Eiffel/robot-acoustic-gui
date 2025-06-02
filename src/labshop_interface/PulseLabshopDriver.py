# pulse_labshop_driver_minimal_project_v9_autorange_fix3.py
import comtypes.client
import comtypes.gen._98BA4851_F724_11CE_9645_0020AF34D7AC_0_1_0 as PulseTLB
import pythoncom
import time
import os
import logging
import gc
import threading

PULSE_PROGID = 'Pulse.Labshop.Application'

# Définition des constantes globales à partir de PulseTLB
PULSE_STATE_STOPPED = PulseTLB.BKMeasStopped  # 0
PULSE_STATE_SUSPENDING = PulseTLB.BKMeasSuspending  # 1
PULSE_STATE_RESUMING = PulseTLB.BKMeasResuming  # 2
PULSE_STATE_STARTED = PulseTLB.BKMeasStarted  # 3
PULSE_STATE_FRONTEND_NOT_DETECTED = PulseTLB.BKMeasFrontEndNotDetected  # 4
PULSE_STATE_TEMPLATE_SETTLED = PulseTLB.BKMeasTemplateSetled  # 5
PULSE_STATE_AUTORANGE_COMPLETE = PulseTLB.BKMeasTemplateAutorangeComplete  # 6
PULSE_STATE_AUTORANGE_DENIED = PulseTLB.BKMeasTemplateAutorangeDenied  # 7

TEMPLATE_ACTIVATED_MESSAGE = PulseTLB.BKTemplateActivated
TEMPLATE_MEAS_STATE_MESSAGE = PulseTLB.BKTemplateMeasState

# Dictionnaire inversé initial pour les noms d'événements/états
BKNOTIFICATION_NAMES = {getattr(PulseTLB, name): name for name in dir(PulseTLB)
                        if name.startswith('BK') and isinstance(getattr(PulseTLB, name), int)}

# Surcharger/Ajouter des entrées pour plus de clarté, en utilisant les constantes globales déjà définies
BKNOTIFICATION_NAMES[
    PULSE_STATE_STOPPED] = f"PULSE_STATE_STOPPED({PULSE_STATE_STOPPED})"  # Utiliser les variables globales
BKNOTIFICATION_NAMES[PULSE_STATE_SUSPENDING] = f"PULSE_STATE_SUSPENDING({PULSE_STATE_SUSPENDING})"
BKNOTIFICATION_NAMES[PULSE_STATE_RESUMING] = f"PULSE_STATE_RESUMING({PULSE_STATE_RESUMING})"
BKNOTIFICATION_NAMES[PULSE_STATE_STARTED] = f"PULSE_STATE_STARTED({PULSE_STATE_STARTED})"
BKNOTIFICATION_NAMES[
    PULSE_STATE_FRONTEND_NOT_DETECTED] = f"PULSE_STATE_FRONTEND_NOT_DETECTED({PULSE_STATE_FRONTEND_NOT_DETECTED})"
BKNOTIFICATION_NAMES[PULSE_STATE_TEMPLATE_SETTLED] = f"PULSE_STATE_TEMPLATE_SETTLED({PULSE_STATE_TEMPLATE_SETTLED})"
BKNOTIFICATION_NAMES[
    PULSE_STATE_AUTORANGE_COMPLETE] = f"PULSE_STATE_AUTORANGE_COMPLETE({PULSE_STATE_AUTORANGE_COMPLETE})"
BKNOTIFICATION_NAMES[PULSE_STATE_AUTORANGE_DENIED] = f"PULSE_STATE_AUTORANGE_DENIED({PULSE_STATE_AUTORANGE_DENIED})"

BKNOTIFICATION_NAMES[PulseTLB.BKTemplateActive] = f"BKTemplateActive({PulseTLB.BKTemplateActive})"
BKNOTIFICATION_NAMES[PulseTLB.BKTemplateInactive] = f"BKTemplateInactive({PulseTLB.BKTemplateInactive})"

logger = logging.getLogger("RobotApp.PulseMinimalProjectV9")


# Le reste du code (PulseTemplateEvents, PulseLabshopDriver, if __name__ == '__main__')
# reste identique à la version précédente (v8).
# ... (Collez ici le reste du code de la version v8)
# ...

class PulseTemplateEvents:
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
            param_name_decoded = BKNOTIFICATION_NAMES.get(Parameter, f"RawParamValue({Parameter})")

            logger.info(
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
                    logger.error("  -> Autoranging REFUSÉ (événement).")
                    self.driver.is_template_ready_for_measurement = False
                    self.driver.autorange_in_progress_event = False
                elif Parameter == PULSE_STATE_FRONTEND_NOT_DETECTED:
                    logger.error("  -> ERREUR: Frontend non détecté.")
                    self.driver.is_template_ready_for_measurement = False
                    self.driver.is_measurement_active = False
                    self.driver.autorange_in_progress_event = False

            elif Message == TEMPLATE_ACTIVATED_MESSAGE:
                if Parameter == PulseTLB.BKTemplateActive:
                    logger.info("  -> Template confirmé ACTIF (BKTemplateActive Parameter=1). Prêt pour mesure.")
                    self.driver.is_template_ready_for_measurement = True
                elif Parameter == PulseTLB.BKTemplateInactive:
                    logger.info(
                        "  -> Template signalé INACTIF (BKTemplateActivated Parameter=0). État actuel de is_template_ready: %s",
                        self.driver.is_template_ready_for_measurement)
                    if not self.driver._is_activating_template_flag:
                        self.driver.is_template_ready_for_measurement = False
        except Exception as e:
            logger.error(f"Erreur dans Notify2: {e}", exc_info=True)


class PulseLabshopDriver:
    def __init__(self, project_path):
        self.project_path_to_load = project_path
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
        logger.info("PulseLabshopDriver (MinimalProject test V9) instancié.")

    def _event_pump_loop(self):
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        logger.info("Thread de pompage des événements COM démarré.")
        try:
            while self.event_thread_running:
                pythoncom.PumpWaitingMessages()
                time.sleep(0.05)
        except Exception as e:
            logger.error(f"Erreur thread pompe: {e}", exc_info=True)
        finally:
            if self.event_thread_running:
                logger.info("Thread de pompage des événements COM arrêté.")
            pythoncom.CoUninitialize()

    def _log_hardware_details(self, config_organiser_obj, source_description):
        if not config_organiser_obj:
            logger.warning(f"Objet ConfigurationOrganiser ({source_description}) est None.")
            return

        try:
            frontend_name = getattr(config_organiser_obj, "Frontend", "N/A")
            logger.info(f"{source_description} - Frontend principal: {frontend_name}")

            if hasattr(config_organiser_obj, "Frames") and config_organiser_obj.Frames:
                frames_collection = config_organiser_obj.Frames
                logger.info(f"{source_description} - Nombre de châssis: {frames_collection.Count}")
                for i in range(1, frames_collection.Count + 1):
                    frame = frames_collection.Item(i)
                    frame_name = getattr(frame, "Name", f"Châssis_{i}")
                    frame_type = getattr(frame, "Type", "Type Inconnu")
                    logger.info(f"  Châssis {i}: Nom='{frame_name}', Type='{frame_type}'")
                    if hasattr(frame, "Modules") and frame.Modules:
                        modules_collection = frame.Modules
                        logger.info(f"    Modules dans '{frame_name}': {modules_collection.Count}")
                        for j in range(1, modules_collection.Count + 1):
                            module = modules_collection.Item(j)
                            module_name = getattr(module, "Name", f"Module_{j}")
                            module_type = getattr(module, "Type", "Type Inconnu")
                            logger.info(f"      Module {j}: Nom='{module_name}', Type='{module_type}'")
                            if hasattr(module, "Channels") and module.Channels:
                                channels_collection = module.Channels
                                logger.info(f"        Canaux dans '{module_name}': {channels_collection.Count}")
                                for k in range(1, channels_collection.Count + 1):
                                    channel = channels_collection.Item(k)
                                    channel_name = getattr(channel, "Name", f"Canal_{k}")
                                    channel_type_prop = None
                                    if hasattr(channel, "ChannelType"):
                                        channel_type_prop = getattr(channel, "ChannelType", "Type Inconnu")
                                    elif hasattr(channel, "Type"):
                                        channel_type_prop = getattr(channel, "Type", "Type Inconnu (via Type)")
                                    else:
                                        channel_type_prop = "Type Canal Indisponible"
                                    logger.info(
                                        f"          Canal {k}: Nom='{channel_name}', Type='{channel_type_prop}'")
                                    if hasattr(channel, "GetTransducer"):
                                        transducer = channel.GetTransducer()
                                        if transducer:
                                            trans_name = getattr(transducer, "Name", "N/A")
                                            trans_serial = getattr(transducer, "SerialNumber", "N/A")
                                            trans_type = getattr(transducer, "Type", "N/A")
                                            logger.info(
                                                f"            Transducteur: Nom='{trans_name}', Type='{trans_type}', S/N='{trans_serial}'")
                                    else:
                                        trans_name_proxy = getattr(channel, "TransducerName", None)
                                        if trans_name_proxy:
                                            trans_type_proxy = getattr(channel, "TransducerType", "N/A")
                                            trans_serial_proxy = getattr(channel, "TransducerSerialNo", "N/A")
                                            logger.info(
                                                f"            Transducteur (via Proxy): Nom='{trans_name_proxy}', Type='{trans_type_proxy}', S/N='{trans_serial_proxy}'")
            else:
                logger.info(f"{source_description} - Aucun châssis (Frames) trouvé.")
        except Exception as e_hw_log:
            logger.error(f"Erreur lors du logging des détails matériels pour {source_description}: {e_hw_log}",
                         exc_info=True)

    def initialize_pulse(self):
        logger.info("Initialisation de PULSE LabShop (chargement projet minimal V9)...")
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
            # self.pulse_app.Visible = True # Déplacé
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

            self.pulse_app.Visible = True  # Maintenant que le projet est ouvert
            logger.info(f"Projet '{self.project.Name}' ouvert et Pulse visible.")
            time.sleep(1)

            if self.project.ConfigurationOrganiser:
                logger.info("Appel explicite à ConfigurationOrganiser.DetectFrontend()...")
                try:
                    self.project.ConfigurationOrganiser.DetectFrontend()
                    logger.info("DetectFrontend() terminé.")
                    time.sleep(1)
                except pythoncom.com_error as e_detect:
                    logger.warning(f"Erreur lors de DetectFrontend: {e_detect}")
            else:
                logger.warning("ConfigurationOrganiser non disponible.")

            if not (self.event_thread and self.event_thread.is_alive()):
                self.event_thread_running = True
                self.event_thread = threading.Thread(target=self._event_pump_loop, name="PulseEventPump", daemon=True)
                self.event_thread.start()
                logger.info("Thread de pompage des événements démarré AVANT activation template.")

            if not self.project.MeasurementOrganiser or self.project.MeasurementOrganiser.Templates.Count == 0:
                logger.error(f"Aucun template dans '{self.project.Name}'.")
                self._close_project_and_app(ask_save=False)
                return False

            template_id = 1
            try:
                self.active_template = self.project.MeasurementOrganiser.Templates.Item(template_id)
            except pythoncom.com_error as e:
                logger.error(f"Erreur COM accès template ID {template_id}: {e}")
                self._close_project_and_app(ask_save=False)
                return False
            if not self.active_template:
                logger.error(f"Impossible de récupérer template ID {template_id}.")
                self._close_project_and_app(ask_save=False)
                return False
            logger.info(f"Template '{self.active_template.Name}' (ID/Index: {template_id}) trouvé.")

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
                logger.info(
                    f"État synchrone du template après ActivateTemplate() : active_template.Active = {is_active_sync}")
                if is_active_sync:
                    logger.info("  -> La propriété .Active est True, on considère le template prêt.")
                    self.is_template_ready_for_measurement = True
            except Exception as e_active_prop:
                logger.warning(f"Impossible de lire la propriété active_template.Active : {e_active_prop}")

            timeout_template_ready = 30
            start_wait_template = time.time()
            logger.info(f"Attente que le template devienne prêt via événement (timeout: {timeout_template_ready}s)...")
            while not self.is_template_ready_for_measurement:
                if (time.time() - start_wait_template) > timeout_template_ready:
                    logger.error(
                        f"Timeout: Template non confirmé prêt par événement dans les {timeout_template_ready}s.")
                    self._is_activating_template_flag = False
                    self._close_project_and_app(ask_save=False)
                    return False
                time.sleep(0.1)

            self._is_activating_template_flag = False
            logger.info("Template confirmé prêt pour la mesure (is_template_ready_for_measurement = True).")

            logger.info("Initialisation PULSE avec projet minimal V9 terminée.")
            return True

        except pythoncom.com_error as e:
            logger.critical(f"Erreur COM init: {e}", exc_info=True)
        except Exception as e:
            logger.critical(f"Erreur générale init: {e}", exc_info=True)

        self._is_activating_template_flag = False
        self._close_project_and_app(ask_save=False, app_already_set=bool(self.pulse_app))
        return False

    def autorange(self):
        if not self.pulse_app or not self.active_template:
            logger.error("Impossible de lancer l'autorange : PULSE non initialisé ou template non actif.")
            return False
        if not self.is_template_ready_for_measurement:
            logger.error("Impossible de lancer l'autorange : le template n'est pas prêt.")
            return False
        try:
            logger.info("Lancement de l'Autorange PULSE...")
            self.autorange_in_progress_event = True

            com_call_result = self.pulse_app.Autorange()
            if com_call_result is False:
                logger.error("L'appel COM à Autorange a retourné False explicitement.")
                self.autorange_in_progress_event = False
                return False

            logger.info("Commande Autorange envoyée. Attente de l'événement de complétion/refus ou timeout...")

            timeout_autorange = 30  # Augmenté
            start_wait_autorange = time.time()

            while self.autorange_in_progress_event:
                if (time.time() - start_wait_autorange) > timeout_autorange:
                    logger.warning(f"Timeout ({timeout_autorange}s) en attente de la fin de l'autorange par événement.")
                    self.autorange_in_progress_event = False
                    break
                time.sleep(0.1)

            if not self.is_template_ready_for_measurement:
                logger.error(
                    "L'autorange a été refusé ou a rendu le template non prêt (flag is_template_ready_for_measurement est False).")
                return False

            logger.info(
                f"Autorange terminé (soit par événement, soit par timeout). État de is_template_ready: {self.is_template_ready_for_measurement}")
            return self.is_template_ready_for_measurement

        except pythoncom.com_error as e:
            logger.error(f"Erreur COM lors de l'Autorange PULSE : {e}", exc_info=True)
            self.autorange_in_progress_event = False
            return False
        except Exception as e:
            logger.error(f"Erreur générale lors de l'Autorange PULSE : {e}", exc_info=True)
            self.autorange_in_progress_event = False
            return False

    def start_measurement(self):
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
            logger.info("Commande Start envoyée à PULSE.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors du démarrage de la mesure PULSE : {e}", exc_info=True)
            return False

    def stop_measurement(self):
        if not self.pulse_app:
            logger.warning("PULSE non initialisé, impossible d'arrêter.")
            return False
        try:
            if not self.is_measurement_active and self.is_measurement_complete:
                logger.warning("Tentative d'arrêter une mesure déjà arrêtée. Ignoré.")
                return True
            logger.info("Arrêt de la mesure PULSE...")
            self.pulse_app.Stop()
            logger.info("Commande Stop envoyée à PULSE.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt de la mesure PULSE : {e}", exc_info=True)
            return False

    def _close_project_and_app(self, ask_save=False, app_already_set=True):
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

    def _release_com_objects(self):
        logger.debug("Libération des objets COM PULSE...")
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
        logger.info("Fermeture de la connexion à PULSE LabShop...")
        if self.event_thread and self.event_thread.is_alive():
            self.event_thread_running = False
            self.event_thread.join(timeout=2)
            if self.event_thread.is_alive():
                logger.warning("Thread pompe événements non arrêté.")
            else:
                logger.info("Thread pompe événements arrêté.")
        self.event_thread = None
        self._close_project_and_app(ask_save=False, app_already_set=bool(self.pulse_app))
        logger.info("Fermeture du driver PulseLabshop terminée.")

    def kill_pulse_processes(self):
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
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - [%(levelname)s] (%(threadName)s) %(name)s: %(message)s')
    try:
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    except pythoncom.com_error:
        pass

    pulse_driver = None
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_file_path = os.path.join(script_dir, "pulse_projects", "MinimalTest.pls")

        if not os.path.exists(project_file_path):
            logger.critical(f"ERREUR: '{project_file_path}' introuvable. ")
        else:
            pulse_driver = PulseLabshopDriver(project_file_path)

            if pulse_driver.initialize_pulse():
                logger.info("PULSE (projet minimal) initialisé.")
                if pulse_driver.pulse_app: pulse_driver.pulse_app.Visible = True
                time.sleep(1)


                def measurement_started_cb():
                    logger.info("CALLBACK: Mesure (projet minimal) démarrée !")


                def measurement_stopped_cb():
                    logger.info("CALLBACK: Mesure (projet minimal) terminée !")


                pulse_driver.on_measurement_started_callback = measurement_started_cb
                pulse_driver.on_measurement_stopped_callback = measurement_stopped_cb

                if pulse_driver.is_template_ready_for_measurement:
                    logger.info("Tentative d'Autorange avant de démarrer la mesure...")
                    autorange_success = pulse_driver.autorange()

                    if autorange_success:
                        logger.info("Autorange a réussi (ou n'a pas été explicitement refusé et n'a pas timeout).")
                        if not pulse_driver.is_template_ready_for_measurement:
                            logger.error(
                                "Problème: Autorange a retourné True, mais le template n'est plus prêt. Mesure annulée.")
                        elif pulse_driver.start_measurement():
                            logger.info("start_measurement envoyé après autorange.")
                            timeout_start = 15
                            start_time_wait = time.time()
                            while not pulse_driver.is_measurement_active and (
                                    time.time() - start_time_wait) < timeout_start:
                                time.sleep(0.1)

                            if pulse_driver.is_measurement_active:
                                logger.info("Mesure confirmée ACTIVE post-autorange.")
                                time.sleep(5)
                                pulse_driver.stop_measurement()
                                logger.info("stop_measurement envoyé.")
                                timeout_stop = 10
                                stop_time_wait = time.time()
                                while not pulse_driver.is_measurement_complete and (
                                        time.time() - stop_time_wait) < timeout_stop:
                                    time.sleep(0.1)
                                if pulse_driver.is_measurement_complete:
                                    logger.info("Mesure confirmée COMPLÈTE.")
                                else:
                                    logger.error("Timeout: Mesure non confirmée complète post-stop.")
                            else:
                                logger.error("Timeout/Échec: Mesure non active post-autorange/start.")
                        else:
                            logger.error("Échec envoi commande start_measurement post-autorange.")
                    else:
                        logger.error("Échec de la commande Autorange ou Autorange a été refusé. Mesure non tentée.")
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
            pythoncom.CoUninitialize()
            logger.debug("COM désinitialisé pour le thread principal (fin).")
        except Exception:
            pass

        logger.info("Fin du test.")