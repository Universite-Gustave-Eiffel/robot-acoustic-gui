# src/sequence_manager/sequence_manager.py
import logging
import threading
import time
from PySide6.QtCore import QThread, Signal, Slot

from .states import StateIdle, StateStartMove, StateEnd, StateError


class SequenceManager(QThread):
    """Gère l'exécution d'une séquence de mesure dans un thread séparé.

    Cette classe implémente une machine à états finis (FSM) pour orchestrer
    le cycle de mesure : déplacement du robot, stabilisation, acquisition PULSE,
    et sauvegarde. Elle communique son état à l'application principale
    via des signaux Qt.

    :param robot: L'instance du :class:`~src.controller_interface.GalilDriver.RobotController`.
    :param pulse: L'instance du :class:`~src.labshop_interface.PulseLabshopDriver.PulseLabshopDriver`.
    :param points: La liste d'objets :class:`~src.data_manager.Point` à traiter.
    :param sequence_params: Un dictionnaire contenant les paramètres de la séquence
                            (ex: hauteur de sécurité, temps de stabilisation).
    :param single_shot: Si ``True``, la séquence s'arrête après avoir traité un seul point.
    """
    status_changed = Signal(str)
    active_point_changed = Signal(int)
    sequence_completed = Signal(str, int)
    start_measure_requested = Signal()
    save_measure_requested = Signal(str)

    # Nouveau signal pour demander un arrêt doux
    stop_robot_requested = Signal()

    def __init__(self, robot, pulse, points, sequence_params, single_shot=False):
        """Initialise le gestionnaire de séquence."""
        super().__init__()
        self.robot = robot
        self.pulse = pulse
        self.single_shot = single_shot
        self.context = {
            'points': points,
            'current_index': 0,
            'robot_lock': None,
            'base_filename': 'mesure',
            'sequence_manager': self,
            'sequence_params': sequence_params,
        }
        self._is_running = False
        self._is_paused = False
        self.logger = logging.getLogger("RobotApp.SequenceManager")
        self.action_completed_event = threading.Event()
        self.action_success = False
        self.action_message = ""

    @Slot(bool, str)
    def on_measure_action_completed(self, success: bool, message: str):
        """Slot pour recevoir le résultat d'une action asynchrone demandée à PULSE.

        Le :class:`~src.main_controller.MainController` appelle ce slot lorsque PULSE a terminé
        une opération (démarrage, sauvegarde). Ce mécanisme de callback via un
        `threading.Event` permet à la FSM de se mettre en attente sans bloquer.

        :param success: ``True`` si l'action a réussi, ``False`` sinon.
        :param message: Message de statut associé à l'action.
        """
        self.action_success = success
        self.action_message = message
        self.action_completed_event.set()

    def run(self):
        """Point d'entrée principal du thread. Exécute la machine à états.

        Cette méthode est appelée automatiquement lors du `start()` du thread.
        Elle boucle à travers les états jusqu'à atteindre un état final
        (:class:`~.states.StateEnd`) ou jusqu'à ce que l'arrêt soit demandé.
        """
        final_message = "Séquence terminée avec succès."
        self._is_running = True
        self._is_paused = False
        self.current_state = StateStartMove(self.robot)

        try:
            while self._is_running and not isinstance(self.current_state, (StateEnd, StateIdle)):

                # Gestion de la pause
                while self._is_paused and self._is_running:
                    time.sleep(0.2)

                if not self._is_running:
                    break

                point_index = self.context['current_index']
                total_points = len(self.context['points'])
                status_message = f"État : {self.current_state.name}"
                if not isinstance(self.current_state, (StateEnd, StateIdle)):
                    status_message += f" | Point : {point_index + 1}/{total_points}"

                self.status_changed.emit(status_message)

                if "Move" in self.current_state.name or "Measure" in self.current_state.name or "Stabilize" in self.current_state.name:
                    self.active_point_changed.emit(self.context['current_index'])
                else:
                    self.active_point_changed.emit(-1)

                next_state_class, self.context = self.current_state.execute(self.context)
                self.current_state = next_state_class(self.robot)

                # Tick de la machine à états
                time.sleep(0.05)


        except Exception as e:
            final_message = f"Erreur inattendue dans la séquence : {e}"
            self.logger.critical(final_message, exc_info=True)
            self.context['error'] = final_message
            self.current_state = StateError(self.robot)

        if isinstance(self.current_state, StateError):
            final_message = self.context.get('error', 'Erreur inconnue')
            self.status_changed.emit(f"ERREUR : {final_message}")
        elif not self._is_running:
            final_message = "Séquence arrêtée par l'utilisateur."
            self.status_changed.emit(final_message)
        else:
            self.status_changed.emit(final_message)

        next_point_index = self.context.get('current_index', 0)
        self.active_point_changed.emit(-1)
        self.sequence_completed.emit(final_message, next_point_index)
        self._is_running = False

    def stop(self):
        """Demande l'arrêt propre (doux) de la séquence.

        Positionne un drapeau qui sera détecté par la boucle `run()` pour
        terminer l'exécution.
        """
        self.logger.info("Demande d'arrêt de la séquence.")
        self._is_running = False
        if self.action_completed_event and not self.action_completed_event.is_set():
            self.action_success = False
            self.action_message = "Séquence arrêtée par l'utilisateur"
            self.action_completed_event.set()
        self.stop_robot_requested.emit()

    def toggle_pause(self):
        """Met en pause ou reprend l'exécution de la séquence."""
        self._is_paused = not self._is_paused
        state = "en pause" if self._is_paused else "reprise"
        self.logger.info(f"Séquence mise {state}.")
        self.status_changed.emit(f"Séquence {state}")