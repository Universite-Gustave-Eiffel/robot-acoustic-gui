# src/sequence_manager/sequence_manager.py
import logging
import threading
from PySide6.QtCore import QThread, Signal, Slot

# CORRIGÉ : Import de tous les états utilisés
from .states import StateIdle, StateMoveToPoint, StateEnd, StateError, StateNextPoint, StateStartMeasure, \
    StateStopMeasure, StateSaveMeasure


class SequenceManager(QThread):
    """Gère l'exécution d'une séquence de mesure en émettant des signaux pour les actions matérielles."""

    status_changed = Signal(str)
    active_point_changed = Signal(int)
    sequence_completed = Signal(str)

    start_measure_requested = Signal()
    stop_measure_requested = Signal()
    save_measure_requested = Signal(str)

    def __init__(self, robot, points):
        super().__init__()
        self.robot = robot
        self.current_state = None
        self.context = {
            'points': points,
            'current_index': 0,
            'robot_lock': None,
            'base_filename': 'mesure',
            'sequence_manager': self
        }
        self._is_running = False
        self.logger = logging.getLogger("RobotApp.SequenceManager")

        self.action_completed_event = threading.Event()
        self.action_success = False
        self.action_message = ""

    @Slot(bool, str)
    def on_measure_action_completed(self, success: bool, message: str):
        """Slot qui reçoit le résultat d'une action Pulse depuis le MainController."""
        self.action_success = success
        self.action_message = message
        self.action_completed_event.set()

    def run(self):
        final_message = "Séquence terminée avec succès."
        self._is_running = True
        self.current_state = StateMoveToPoint(self.robot)

        try:
            while self._is_running and not isinstance(self.current_state, StateEnd):
                point_index = self.context['current_index']
                total_points = len(self.context['points'])
                status_message = f"État : {self.current_state.name}"
                if not isinstance(self.current_state, (StateIdle, StateNextPoint)):
                    status_message += f" | Point : {point_index + 1}/{total_points}"

                self.status_changed.emit(status_message)
                self.active_point_changed.emit(self.context['current_index'])

                next_state_class, self.context = self.current_state.execute(self.context)

                # Vérifie si une action a échoué DANS un état qui utilise l'événement
                if not self.action_success and self.current_state.name in ["StateStartMeasure", "StateStopMeasure",
                                                                           "StateSaveMeasure"]:
                    self.context['error'] = self.action_message
                    self.current_state = StateError(self.robot)
                else:
                    self.current_state = next_state_class(self.robot)

        except Exception as e:
            final_message = f"Erreur inattendue dans la séquence : {e}"
            self.logger.critical(final_message, exc_info=True)
            self.context['error'] = final_message
            self.current_state = StateError(self.robot)

        if self.current_state and isinstance(self.current_state, StateError):
            self.current_state.execute(self.context)
            final_message = self.context.get('error', 'Erreur inconnue')

        if not self._is_running and "error" not in self.context:
            final_message = "Séquence arrêtée par l'utilisateur."

        self.status_changed.emit(final_message)
        self.active_point_changed.emit(-1)
        self.sequence_completed.emit(final_message)  # Utilisation du signal personnalisé
        self._is_running = False

    def stop(self):
        """Demande l'arrêt de la séquence."""
        self.logger.info("Demande d'arrêt de la séquence.")
        self._is_running = False
        if self.action_completed_event and not self.action_completed_event.is_set():
            self.action_success = False
            self.action_message = "Séquence arrêtée par l'utilisateur"
            self.action_completed_event.set()