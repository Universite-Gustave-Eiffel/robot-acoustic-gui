# src/sequence_manager/states.py
import time
import logging


class State:
    """Classe de base abstraite pour tous les états."""

    def __init__(self, robot, pulse):
        self.robot = robot
        self.pulse = pulse
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

        # Le bloc 'with' garantit que le verrou est acquis avant le mouvement
        # et relâché automatiquement après, même en cas d'erreur.
        with robot_lock:
            self.robot.move_to(x=point.x, y=point.y, z=point.z, theta=point.theta, phi=point.phi)

        return StateMeasure, context


class StateMeasure(State):
    """Simule la prise de mesure."""

    def execute(self, context):
        point_index = context['current_index']
        self.logger.info(f"Début de la mesure au point {point_index + 1}.")

        # Simulation d'une mesure de 2 secondes.
        # Cette pause ne nécessite pas de verrou car elle n'utilise pas le robot.
        time.sleep(2)

        self.logger.info("Mesure terminée.")
        return StateNextPoint, context


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