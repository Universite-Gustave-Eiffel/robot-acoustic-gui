# src/sequence_manager/sequence_manager.py
import logging
from PySide6.QtCore import QThread, Signal

from .states import StateIdle, StateMoveToPoint, StateEnd, StateError, StateNextPoint


class SequenceManager(QThread):
    """Gère l'exécution d'une séquence de mesure dans un thread séparé."""

    # Signaux pour communiquer avec le MainController/GUI
    status_changed = Signal(str)
    sequence_finished = Signal()
    active_point_changed = Signal(int)

    def __init__(self, robot, pulse, points):
        super().__init__()
        self.robot = robot
        self.pulse = pulse

        self.current_state = StateIdle(robot, pulse)
        self.context = {
            'points': points,
            'current_index': 0,
            'robot_lock': None  # Le verrou sera ajouté par le MainController
        }
        self._is_running = False
        self.logger = logging.getLogger("RobotApp.SequenceManager")

    def run(self):
        """Méthode principale du thread, exécute la FSM."""
        if not self.context.get('points'):
            self.status_changed.emit("Erreur : Aucun point à mesurer.")
            return

        self._is_running = True
        # L'état initial de la séquence est de se déplacer vers le premier point
        self.current_state = StateMoveToPoint(self.robot, self.pulse)

        while self._is_running and not isinstance(self.current_state, StateEnd):

            # Formate un message de statut plus clair
            point_index = self.context['current_index']
            total_points = len(self.context['points'])
            status_message = f"État : {self.current_state.name}"
            if not isinstance(self.current_state, StateNextPoint):
                status_message += f" | Point : {point_index + 1}/{total_points}"

            self.status_changed.emit(status_message)
            self.active_point_changed.emit(self.context['current_index'])

            try:
                # Exécute l'état actuel, qui retourne la classe du prochain état
                next_state_class, self.context = self.current_state.execute(self.context)
                self.current_state = next_state_class(self.robot, self.pulse)
            except Exception as e:
                self.logger.error(f"Erreur durant l'état {self.current_state.name}: {e}", exc_info=True)
                self.context['error'] = str(e)
                self.current_state = StateError(self.robot, self.pulse)

        # La boucle est terminée (soit par la fin, soit par un arrêt)
        if isinstance(self.current_state, StateEnd):
            self.status_changed.emit("Séquence terminée.")
        else:
            self.status_changed.emit("Séquence arrêtée par l'utilisateur.")

        self.active_point_changed.emit(-1)

        self.sequence_finished.emit()
        self._is_running = False

    def stop(self):
        """Demande l'arrêt de la séquence."""
        self.logger.info("Demande d'arrêt de la séquence.")
        self._is_running = False