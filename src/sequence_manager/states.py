# src/sequence_manager/states.py
import time
import logging


class State:
    def __init__(self, robot):
        self.robot = robot
        self.name = self.__class__.__name__
        self.logger = logging.getLogger(f"RobotApp.FSM.{self.name}")

    def execute(self, context):
        raise NotImplementedError


class StateIdle(State):
    def execute(self, context):
        return StateIdle, context


class StateStartMove(State):
    """Démarre le mouvement du robot vers un point et passe immédiatement à l'attente."""

    def execute(self, context):
        point_index = context['current_index']
        point = context['points'][point_index]
        robot_lock = context['robot_lock']

        self.logger.info(f"Calcul des coordonnées robot pour le point capsule {point_index + 1}")
        capsule_target_coords = {'X': point.x, 'Y': point.y, 'Z': point.z, 'THETA': point.theta, 'PHI': point.phi}
        robot_target_coords = self.robot.calculate_robot_coords_for_capsule(**capsule_target_coords)
        self.logger.info(f"Coordonnées robot calculées : {robot_target_coords}")

        with robot_lock:
            self.logger.info(f"Démarrage du mouvement vers le point robot {point_index + 1}")
            self.robot.start_move_to(**robot_target_coords)

        return StateWaitForMove, context


class StateWaitForMove(State):
    """Attend la fin du mouvement en cours sans bloquer."""

    def execute(self, context):
        robot_lock = context['robot_lock']
        with robot_lock:
            if self.robot.is_motion_complete():
                self.logger.info("Mouvement terminé.")
                return StateStabilize, context
            else:
                # Le mouvement n'est pas terminé, on reste dans cet état
                return StateWaitForMove, context


class StateStabilize(State):
    """Attend un temps défini pour la stabilisation mécanique."""

    def execute(self, context):
        if 'stabilize_end_time' not in context:
            sequence_params = context.get('sequence_params', {})
            temps_stabilisation = sequence_params.get('temps_stabilisation_s', 0.5)
            self.logger.info(f"Stabilisation pendant {temps_stabilisation}s...")
            context['stabilize_end_time'] = time.time() + temps_stabilisation
            return StateStabilize, context

        if time.time() >= context['stabilize_end_time']:
            self.logger.info("Stabilisation terminée.")
            del context['stabilize_end_time']
            return StateStartMeasure, context
        else:
            return StateStabilize, context


class StateStartMeasure(State):
    """Demande le démarrage de la mesure PULSE."""

    def execute(self, context):
        seq_manager = context['sequence_manager']
        self.logger.info(f"Démarrage de la mesure pour le point {context['current_index'] + 1}.")
        seq_manager.action_completed_event.clear()
        seq_manager.action_success = False
        seq_manager.start_measure_requested.emit()

        context['previous_state'] = self.__class__
        return StateWaitingForMeasureAction, context


class StateWaitingForMeasureAction(State):
    """Attend que l'action PULSE (démarrage, sauvegarde) soit terminée."""

    def execute(self, context):
        seq_manager = context['sequence_manager']
        if seq_manager.action_completed_event.wait(timeout=0.1):  # Attente non-bloquante
            if not seq_manager.action_success:
                context['error'] = f"Action PULSE a échoué: {seq_manager.action_message}"
                return StateError, context

            # Détermine le prochain état en fonction de l'état précédent
            if context.get('previous_state') == StateStartMeasure:
                return StateWaitForMeasure, context
            elif context.get('previous_state') == StateSaveMeasure:
                return StateNextPoint, context

        # L'action n'est pas finie, on reste dans cet état
        return StateWaitingForMeasureAction, context


class StateWaitForMeasure(State):
    """Attend que la mesure PULSE soit physiquement terminée."""

    def execute(self, context):
        pulse = context['sequence_manager'].pulse
        if pulse.is_measurement_complete:
            self.logger.info("Mesure PULSE terminée.")
            return StateSaveMeasure, context
        else:
            return StateWaitForMeasure, context


class StateSaveMeasure(State):
    """Demande la sauvegarde des données de la mesure PULSE."""

    def execute(self, context):
        seq_manager = context['sequence_manager']
        point_index = context['current_index']

        base_filename = context['points'][point_index].measurement_file
        if not base_filename:
            base_filename = f"{context.get('base_filename', 'mesure')}_point_{point_index + 1:03d}"

        self.logger.info(f"Demande de sauvegarde vers '{base_filename}'")
        seq_manager.action_completed_event.clear()
        seq_manager.action_success = False

        seq_manager.save_measure_requested.emit(base_filename)
        context['previous_state'] = StateSaveMeasure
        return StateWaitingForMeasureAction, context


class StateNextPoint(State):
    """Passe au point suivant, ou termine."""

    def execute(self, context):
        seq_manager = context['sequence_manager']

        if seq_manager.single_shot:
            self.logger.info("Mode 'Point Suivant' : Séquence terminée.")
            context['current_index'] += 1
            return StateEnd, context

        context['current_index'] += 1
        if context['current_index'] < len(context['points']):
            self.logger.info("Passage au point suivant.")
            return StateStartMove, context
        else:
            self.logger.info("Tous les points ont été mesurés.")
            return StateEnd, context


class StateEnd(State):
    def execute(self, context):
        return StateEnd, context


class StateError(State):
    def execute(self, context):
        error_message = context.get('error', 'Erreur inconnue.')
        self.logger.error(f"État d'erreur atteint : {error_message}")
        return StateEnd, context