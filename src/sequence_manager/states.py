# src/sequence_manager/states.py
import time
import logging


# L'import de pythoncom n'est plus nécessaire ici.

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
        seq_manager.action_completed_event.wait()  # Attend la réponse du MainController

        if not seq_manager.action_success:
            return StateError, context

        return StateStopMeasure, context


class StateStopMeasure(State):
    """Demande l'arrêt de la mesure PULSE."""

    def execute(self, context):
        seq_manager = context['sequence_manager']
        self.logger.info("Demande d'arrêt de la mesure.")

        # La durée de l'acquisition est gérée par le template PULSE.
        # Ici on attend simplement un peu que la mesure se fasse avant de demander l'arrêt.
        time.sleep(2.0)

        seq_manager.action_completed_event.clear()
        seq_manager.action_success = False
        seq_manager.stop_measure_requested.emit()
        seq_manager.action_completed_event.wait()

        if not seq_manager.action_success:
            return StateError, context

        return StateSaveMeasure, context


class StateSaveMeasure(State):
    """Demande la sauvegarde des données de la mesure PULSE."""

    def execute(self, context):
        seq_manager = context['sequence_manager']
        point_index = context['current_index']
        base_filename = context.get('base_filename', 'mesure')

        filename = f"{base_filename}_point_{point_index + 1}.txt"
        self.logger.info(f"Demande de sauvegarde vers '{filename}'")

        seq_manager.action_completed_event.clear()
        seq_manager.action_success = False
        seq_manager.save_measure_requested.emit(filename)
        seq_manager.action_completed_event.wait()

        if seq_manager.action_success:
            context['points'][point_index].measurement_file = filename
            return StateNextPoint, context
        else:
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
        return StateEnd, context