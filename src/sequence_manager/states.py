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
        self.logger.info("En attente de démarrage.")
        return StateIdle, context


class StateSecurityMove(State):
    def execute(self, context):
        sequence_params = context.get('sequence_params', {})
        hauteur_z = sequence_params.get('hauteur_securite_deplacement_z', 20.0)
        self.logger.info(f"Déplacement de sécurité vers Z = {hauteur_z} mm.")
        with context['robot_lock']:
            current_pos = self.robot.last_positions
            self.robot.move_to(z=hauteur_z, x=current_pos.get('X'), y=current_pos.get('Y'),
                               theta=current_pos.get('THETA'), phi=current_pos.get('PHI'))
        return StateMoveToPoint, context


class StateMoveToPoint(State):
    def execute(self, context):
        point_index = context['current_index']
        point = context['points'][point_index]
        robot_lock = context['robot_lock']
        sequence_params = context.get('sequence_params', {})
        activer_securite = sequence_params.get('activer_securite_deplacement', False)
        self.logger.info(f"Calcul des coordonnées robot pour le point capsule {point_index + 1}")
        capsule_target_coords = {'X': point.x, 'Y': point.y, 'Z': point.z, 'THETA': point.theta, 'PHI': point.phi}
        robot_target_coords = self.robot.calculate_robot_coords_for_capsule(**capsule_target_coords)
        self.logger.info(f"Coordonnées robot calculées : {robot_target_coords}")
        with robot_lock:
            if not activer_securite:
                self.logger.info(f"Déplacement direct vers le point robot {point_index + 1}")
                self.robot.move_to(**robot_target_coords)
            else:
                self.logger.info(f"Déplacement (XY, Rot) vers le point robot {point_index + 1}")
                self.robot.move_to(x=robot_target_coords['X'], y=robot_target_coords['Y'],
                                   theta=robot_target_coords['THETA'], phi=robot_target_coords['PHI'])
                time.sleep(0.2)
                self.logger.info(f"Descente en Z vers le point robot {point_index + 1}")
                self.robot.move_to(z=robot_target_coords['Z'])
        return StateStabilize, context


class StateStabilize(State):
    def execute(self, context):
        sequence_params = context.get('sequence_params', {})
        temps_stabilisation = sequence_params.get('temps_stabilisation_s', 0.5)
        if temps_stabilisation > 0:
            self.logger.info(f"Stabilisation pendant {temps_stabilisation} seconde(s)...")
            time.sleep(temps_stabilisation)
        return StateStartMeasure, context


class StateStartMeasure(State):
    def execute(self, context):
        seq_manager = context['sequence_manager']
        self.logger.info(f"Demande de démarrage de la mesure pour le point {context['current_index'] + 1}.")
        seq_manager.action_completed_event.clear()
        seq_manager.action_success = False
        seq_manager.start_measure_requested.emit()
        seq_manager.action_completed_event.wait(timeout=15)
        if not seq_manager.action_success:
            context['error'] = "Échec du démarrage de la mesure PULSE."
            return StateError, context
        return StateWaitForMeasure, context


class StateWaitForMeasure(State):
    def execute(self, context):
        seq_manager = context['sequence_manager']
        pulse = seq_manager.pulse
        timeout = 60
        start_time = time.time()
        self.logger.info("Attente de la fin de la mesure par PULSE...")
        while not pulse.is_measurement_complete:
            if not seq_manager._is_running:
                self.logger.info("Attente de mesure interrompue.")
                return StateEnd, context
            if time.time() - start_time > timeout:
                context['error'] = "Timeout en attendant la fin de la mesure Pulse."
                return StateError, context
            time.sleep(0.1)
        self.logger.info("Mesure PULSE confirmée comme étant terminée.")
        return StateSaveMeasure, context


class StateSaveMeasure(State):
    def execute(self, context):
        seq_manager = context['sequence_manager']
        point_index = context['current_index']
        base_filename = context['points'][point_index].measurement_file
        if not base_filename:
            base_filename = f"{context.get('base_filename', 'mesure')}_point_{point_index + 1:03d}"
        final_filename = base_filename
        self.logger.info(f"Demande de sauvegarde vers '{final_filename}'")
        seq_manager.action_completed_event.clear()
        seq_manager.action_success = False
        seq_manager.save_measure_requested.emit(final_filename)
        seq_manager.action_completed_event.wait(timeout=15)
        if seq_manager.action_success:
            context['points'][point_index].measurement_file = seq_manager.action_message
            return StateNextPoint, context
        else:
            context['error'] = seq_manager.action_message
            return StateError, context


class StateNextPoint(State):
    def execute(self, context):
        seq_manager = context['sequence_manager']
        if seq_manager.single_shot:
            self.logger.info("Mode 'Mesurer Point Suivant' : Séquence terminée après un point.")
            context['current_index'] += 1
            return StateEnd, context

        context['current_index'] += 1
        sequence_params = context.get('sequence_params', {})
        activer_securite = sequence_params.get('activer_securite_deplacement', False)

        if context['current_index'] < len(context['points']):
            self.logger.info("Passage au point suivant.")
            if activer_securite:
                return StateSecurityMove, context
            else:
                return StateMoveToPoint, context
        else:
            self.logger.info("Tous les points ont été mesurés.")
            return StateEnd, context


class StateEnd(State):
    def execute(self, context):
        self.logger.info("Séquence terminée.")
        return StateEnd, context


class StateError(State):
    def execute(self, context):
        error_message = context.get('error', 'Erreur inconnue dans la séquence.')
        self.logger.error(f"État d'erreur atteint : {error_message}")
        return StateEnd, context