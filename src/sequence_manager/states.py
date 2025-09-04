# src/sequence_manager/states.py
import time
import logging
import os


class State:
    """Classe de base abstraite pour tous les états de la machine à états (FSM).

    :param robot: L'instance du contrôleur robot, partagée entre les états.
    """
    def __init__(self, robot):
        """Initialise un état."""
        self.robot = robot
        self.name = self.__class__.__name__
        self.logger = logging.getLogger(f"RobotApp.FSM.{self.name}")

    def execute(self, context):
        """Exécute la logique de l'état.

        Cette méthode doit être implémentée par toutes les sous-classes.

        :param context: Un dictionnaire contenant l'état partagé de la séquence
                        (index du point courant, liste de points, etc.).
        :return: Un tuple contenant la classe du prochain état à exécuter et
                 le contexte mis à jour.
        """
        raise NotImplementedError


class StateIdle(State):
    """État de repos initial. La FSM ne fait rien."""
    def execute(self, context):
        """Ne fait rien et reste dans l'état Idle."""
        return StateIdle, context


class StateStartMove(State):
    """Démarre le mouvement du robot vers le point cible.

    Calcule les coordonnées robot cibles à partir des coordonnées capsule du point.
    Si le mode de sécurité est activé, il décompose le mouvement en plusieurs
    segments (montée, translation, descente).
    Il lance le premier segment de mouvement de manière non-bloquante.
    """

    def execute(self, context):
        point_index = context['current_index']
        point = context['points'][point_index]
        robot_lock = context['robot_lock']
        self.logger.info(f"[DEBUG] sequence_params dans le contexte = {context.get('sequence_params')}")

        # Cible capsule (comme avant)
        capsule_target = {'X': point.x, 'Y': point.y, 'Z': point.z,
                          'THETA': point.theta, 'PHI': point.phi}

        # Paramètres de séquence (issus de la fenêtre Config)
        params = context.get('sequence_params', {}) or {}
        safety_on = bool(params.get('activer_securite_deplacement', False))
        z_safe = float(params.get('hauteur_securite_deplacement_z', 0.0))

        # On nettoie d'éventuels restes d'une séquence précédente
        context.pop('_safety_seq', None)

        if safety_on and z_safe > 0:
            # Position capsule actuelle (si dispo ; fallback neutre sinon)
            try:
                if hasattr(self.robot, "update_positions"):
                    self.robot.update_positions()
                cur_caps = (self.robot.capsule_pos or {}).copy()
            except Exception:
                cur_caps = {'X': 0.0, 'Y': 0.0, 'Z': 0.0, 'THETA': 0.0, 'PHI': 0.0}

            cur_caps = {
                'X': cur_caps.get('X', capsule_target['X']),
                'Y': cur_caps.get('Y', capsule_target['Y']),
                'Z': cur_caps.get('Z', capsule_target['Z']),
                'THETA': cur_caps.get('THETA', capsule_target['THETA']),
                'PHI': cur_caps.get('PHI', capsule_target['PHI']),
            }

            # Construit les segments capsule (seulement ceux utiles)
            seg_caps = []

            # 1) montée à Zsécurité si on est en dessous
            if cur_caps.get('Z', 0.0) < z_safe:
                up = cur_caps.copy()
                up['Z'] = z_safe
                seg_caps.append(up)

            # 2) translation XY/angles vers la cible à Zsécurité
            seg_caps.append({
                'X': capsule_target['X'], 'Y': capsule_target['Y'], 'Z': z_safe,
                'THETA': capsule_target['THETA'], 'PHI': capsule_target['PHI'],
            })

            # 3) descente au Z cible si différent
            if capsule_target['Z'] != z_safe:
                seg_caps.append(capsule_target)

            # Convertit chaque segment en coordonnées robot et les stocke dans le contexte
            context['_safety_seq'] = [
                self.robot.calculate_robot_coords_for_capsule(**c) for c in seg_caps
            ]

            # Démarre le premier segment
            first_robot = context['_safety_seq'].pop(0)
            self.logger.info(f"Trajectoire sécurisée (Z={z_safe} mm) — 1/{1 + len(context['_safety_seq'])} segment(s).")
            with robot_lock:
                self.robot.start_move_to(**first_robot)

            return StateWaitForMove, context

        # ---- CAS NORMAL (inchangé) : déplacement direct en un segment ----
        self.logger.info(f"Calcul des coordonnées robot pour le point capsule {point_index + 1}")
        robot_target = self.robot.calculate_robot_coords_for_capsule(**capsule_target)
        self.logger.info(f"Coordonnées robot calculées : {robot_target}")

        with robot_lock:
            self.logger.info("Démarrage du mouvement.")
            self.robot.start_move_to(**robot_target)

        return StateWaitForMove, context


class StateWaitForMove(State):
    """Attend la fin du mouvement du robot en cours.

    Cet état interroge l'état du robot sans bloquer la FSM. Si le mouvement
    est un mouvement de sécurité multi-segments, il enchaîne le segment
    suivant une fois le précédent terminé.
    """

    def execute(self, context):
        robot_lock = context['robot_lock']

        # On attend la fin du mouvement courant (segment en cours)
        with robot_lock:
            if not self.robot.is_motion_complete():
                return StateWaitForMove, context

        # Si on était en mode "sécurité", enchaîner les segments restants
        safety_seq = context.get('_safety_seq')
        if safety_seq:
            next_robot = safety_seq.pop(0)
            self.logger.info("Segment terminé, démarrage du segment suivant.")
            with robot_lock:
                self.robot.start_move_to(**next_robot)
            return StateWaitForMove, context

        # Sinon, fin de mouvement "classique" → stabilisation (inchangé)
        self.logger.info("Mouvement terminé.")
        return StateStabilize, context


class StateStabilize(State):
    """Marque une pause pour permettre la stabilisation mécanique du robot.

    La durée de la stabilisation est définie dans les paramètres de la séquence.
    """

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
    """Demande le démarrage d'une mesure à PULSE.

    Émet un signal (`start_measure_requested`) vers le MainController
    et passe à un état d'attente de la confirmation.
    """

    def execute(self, context):
        seq_manager = context['sequence_manager']
        # Initialiser le compteur de mesures pour ce point si ce n'est pas déjà fait
        context.setdefault('measurement_count', 0)

        self.logger.info(
            f"Démarrage de la mesure #{context['measurement_count'] + 1} pour le point {context['current_index'] + 1}.")
        seq_manager.action_completed_event.clear()
        seq_manager.action_success = False
        seq_manager.start_measure_requested.emit()

        context['previous_state'] = self.__class__
        return StateWaitingForMeasureAction, context


class StateWaitingForMeasureAction(State):
    """Attend qu'une action PULSE (démarrage, sauvegarde) soit terminée.

    Cet état se met en pause, attendant que le MainController signale la fin
    de l'opération PULSE via l'événement `action_completed_event`.
    """

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
    """Attend que la mesure PULSE soit physiquement terminée.

    Interroge l'état du driver PULSE (``is_measurement_complete``) jusqu'à
    ce que la mesure soit finie.
    """

    def execute(self, context):
        pulse = context['sequence_manager'].pulse
        if pulse.is_measurement_complete:
            self.logger.info("Mesure PULSE terminée.")
            return StateSaveMeasure, context
        else:
            return StateWaitForMeasure, context


class StateSaveMeasure(State):
    """Demande la sauvegarde des données de la mesure PULSE.

    Construit le nom de fichier final (en gérant les mesures multiples pour
    un même point) et émet un signal (`save_measure_requested`) vers le
    MainController.
    """

    def execute(self, context):
        seq_manager = context['sequence_manager']
        point_index = context['current_index']
        point = context['points'][point_index]
        num_measurements = point.num_measurements

        base_filename = point.measurement_file
        if not base_filename:
            base_filename = f"{context.get('base_filename', 'mesure')}_point_{point_index + 1:03d}"

        # Gérer les noms de fichiers multiples
        final_filename = base_filename
        if num_measurements > 1:
            base, ext = os.path.splitext(base_filename)
            if not ext:
                ext = ".txt"
            current_count = context.get('measurement_count', 0)
            final_filename = f"{base}_{current_count + 1}{ext}"

        self.logger.info(f"Demande de sauvegarde vers '{final_filename}'")
        seq_manager.action_completed_event.clear()
        seq_manager.action_success = False

        seq_manager.save_measure_requested.emit(final_filename)
        context['previous_state'] = StateSaveMeasure
        return StateWaitingForMeasureAction, context


class StateNextPoint(State):
    """Décide de la prochaine action après une sauvegarde réussie.

    Incrémente le compteur de mesures. S'il reste des mesures à faire pour
    le point courant, il retourne à l'état `StateStartMeasure`. Sinon, il
    passe au point suivant (retour à `StateStartMove`) ou termine la séquence
    si tous les points ont été traités ou si le mode `single_shot` est actif.
    """

    def execute(self, context):
        seq_manager = context['sequence_manager']
        point_index = context['current_index']
        point = context['points'][point_index]

        # Incrémenter le compteur de mesures pour le point actuel
        context['measurement_count'] = context.get('measurement_count', 0) + 1
        self.logger.info(
            f"{context['measurement_count']} sur {point.num_measurements} mesure(s) effectuée(s) pour ce point.")

        # Vérifier si on doit faire d'autres mesures sur le même point
        if context['measurement_count'] < point.num_measurements:
            self.logger.info("Bouclage pour la prochaine mesure sur le même point.")
            return StateStartMeasure, context

        # Si toutes les mesures pour ce point sont faites, on passe à la suite
        self.logger.info("Toutes les mesures pour ce point sont terminées.")

        # Réinitialiser le compteur pour le prochain point
        context['measurement_count'] = 0

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
    """État final de la séquence. Marque la fin de l'exécution."""
    def execute(self, context):
        return StateEnd, context


class StateError(State):
    """État atteint en cas d'erreur critique durant la séquence.

    Cet état termine immédiatement la séquence. Le message d'erreur est
    stocké dans le contexte pour être affiché à l'utilisateur.
    """
    def execute(self, context):
        error_message = context.get('error', 'Erreur inconnue.')
        self.logger.error(f"État d'erreur atteint : {error_message}")
        return StateEnd, context