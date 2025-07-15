# src/sequence_manager/states.py
import time
import logging


class State:
    """Classe de base abstraite pour tous les états."""

    def __init__(self, robot):
        self.robot = robot
        self.name = self.__class__.__name__
        self.logger = logging.getLogger(f"RobotApp.FSM.{self.name}")

    def execute(self, context):
        """Exécute la logique de l'état et retourne la classe du prochain état et le contexte mis à jour."""
        raise NotImplementedError


class StateIdle(State):
    """État d'attente initial."""

    def execute(self, context):
        self.logger.info("En attente de démarrage.")
        return StateIdle, context


class StateMoveToPoint(State):
    """Déplace le robot vers un point spécifique."""

    def execute(self, context):
        point_index = context['current_index']
        point = context['points'][point_index]
        robot_lock = context['robot_lock']
        self.logger.info(f"Déplacement vers le point {point_index + 1}: {point}")

        with robot_lock:
            # L'attente de fin de mouvement est maintenant gérée robustement dans move_to
            self.robot.move_to(x=point.x, y=point.y, z=point.z, theta=point.theta, phi=point.phi)

        return StateStartMeasure, context


class StateStartMeasure(State):
    """Demande le démarrage de la mesure PULSE."""

    def execute(self, context):
        seq_manager = context['sequence_manager']
        self.logger.info(f"Demande de démarrage de la mesure pour le point {context['current_index'] + 1}.")

        seq_manager.action_completed_event.clear()
        seq_manager.action_success = False
        seq_manager.start_measure_requested.emit()
        seq_manager.action_completed_event.wait()  # Attend juste la confirmation du Lancement

        if not seq_manager.action_success:
            return StateError, context

        # CORRECTION: On passe à l'attente de la fin de mesure, pas à l'arrêt.
        return StateWaitForMeasure, context


# L'ÉTAT StateStopMeasure n'est plus utilisé par la séquence principale car PULSE s'arrête tout seul.
# On le laisse au cas où pour une utilisation future, mais on le retire du flux.
class StateStopMeasure(State):
    """Demande l'arrêt de la mesure PULSE. (Actuellement non utilisé dans le flux standard)"""

    def execute(self, context):
        seq_manager = context['sequence_manager']
        self.logger.info("Demande d'arrêt de la mesure.")

        seq_manager.action_completed_event.clear()
        seq_manager.action_success = False
        seq_manager.stop_measure_requested.emit()
        seq_manager.action_completed_event.wait()

        if not seq_manager.action_success:
            return StateError, context

        return StateWaitForMeasure, context


class StateWaitForMeasure(State):
    """Attend que PULSE confirme que la mesure est bien terminée."""

    def execute(self, context):
        seq_manager = context['sequence_manager']
        pulse = seq_manager.pulse
        # Le timeout doit être supérieur à la durée de mesure configurée dans PULSE
        timeout = 60  # secondes
        start_time = time.time()

        self.logger.info("Attente de la fin de la mesure par PULSE...")

        # On attend que le flag is_measurement_complete passe à True
        # suite aux événements COM traités par le thread principal.
        while not pulse.is_measurement_complete:
            if not seq_manager._is_running:  # Permet l'arrêt par l'utilisateur
                self.logger.info("Attente de mesure interrompue.")
                return StateEnd, context

            if time.time() - start_time > timeout:
                self.logger.error("Timeout en attendant l'arrêt de la mesure Pulse.")
                context['error'] = "Timeout en attendant l'arrêt de la mesure Pulse."
                return StateError, context

            # On laisse le thread dormir un peu pour ne pas consommer 100% du CPU
            time.sleep(0.1)
            #self.robot.driver.ser.read_all()  # Garde le port série "vivant"

        self.logger.info("Mesure PULSE confirmée comme étant terminée.")
        return StateSaveMeasure, context


class StateSaveMeasure(State):
    """Demande la sauvegarde des données de la mesure PULSE."""

    def execute(self, context):
        seq_manager = context['sequence_manager']
        point_index = context['current_index']
        base_filename = context.get('base_filename', 'mesure')

        # Création d'un nom de fichier unique pour la mesure
        filename = f"{base_filename}_point_{point_index + 1}.txt"
        self.logger.info(f"Demande de sauvegarde vers '{filename}'")

        seq_manager.action_completed_event.clear()
        seq_manager.action_success = False
        seq_manager.save_measure_requested.emit(filename)
        seq_manager.action_completed_event.wait()

        if seq_manager.action_success:
            # message est le nom du fichier si succès
            context['points'][point_index].measurement_file = seq_manager.action_message
            return StateNextPoint, context
        else:
            context['error'] = seq_manager.action_message
            return StateError, context


class StateNextPoint(State):
    """Passe au point suivant ou termine la séquence."""

    def execute(self, context):
        context['current_index'] += 1
        if context['current_index'] < len(context['points']):
            self.logger.info("Passage au point suivant.")
            return StateMoveToPoint, context
        else:
            self.logger.info("Tous les points ont été mesurés.")
            return StateEnd, context


class StateEnd(State):
    """État final de la séquence."""

    def execute(self, context):
        self.logger.info("Séquence terminée.")
        return StateEnd, context


class StateError(State):
    """État d'erreur qui arrête la séquence."""

    def execute(self, context):
        error_message = context.get('error', 'Erreur inconnue dans la séquence.')
        self.logger.error(f"État d'erreur atteint : {error_message}")
        # Cet état mène à la fin de la séquence
        return StateEnd, context