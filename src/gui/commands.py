from PySide6.QtGui import QUndoCommand
from main_controller import MainController


class PointListCommand(QUndoCommand):
    """Classe de base pour toutes les commandes qui modifient la liste de points.

    Cette classe hérite de :class:`QUndoCommand` et fournit une structure
    commune pour les actions réversibles (Undo/Redo) affectant la liste de points.
    Chaque commande d'édition (ajouter, supprimer, etc.) hérite de cette classe.

    Elle centralise la logique de rafraîchissement de l'interface utilisateur
    après l'exécution d'une commande.

    :param controller: L'instance du :class:`~src.main_controller.MainController`.
    :param main_window: L'instance de la :class:`~src.gui.new_gui.MainWindow`.
    :param text: La description de la commande, affichée dans les menus Annuler/Rétablir.
    """

    def __init__(self, controller: MainController, main_window, text, parent=None):
        """Initialise la commande de base."""
        super().__init__(text, parent)
        self.controller = controller
        self.main_window = main_window

    def redo(self):
        """Exécute ou ré-exécute la commande."""
        # La logique de l'action sera dans les sous-classes
        pass

    def undo(self):
        """Annule la commande."""
        # La logique d'annulation sera dans les sous-classes
        pass

    def refresh_ui(self):
        """Notifie le contrôleur et la fenêtre de rafraîchir l'état de l'interface."""
        # On signale que la liste a changé, ce qui déclenchera la mise à jour du tableau
        self.controller._notify_point_list_changed()
        # On met à jour l'état des boutons (grisés ou non)
        self.main_window._update_actions_state()


class AddPointCommand(PointListCommand):
    """Commande pour ajouter un point à la liste."""
    def __init__(self, controller: MainController, main_window, point_data=None, index=-1):
        """Initialise la commande d'ajout.

        :param point_data: L'objet :class:`~src.data_manager.Point` à ajouter.
        :param index: L'index où insérer le point (-1 pour la fin).
        """
        super().__init__(controller, main_window, "Ajouter un point")
        self.point_data = point_data
        self.index = index

    def redo(self):
        """Ajoute le point à la liste."""
        self.controller.point_manager.add_point(self.point_data, self.index)
        self.refresh_ui()

    def undo(self):
        """Supprime le point qui vient d'être ajouté."""
        # Si on a ajouté à la fin, l'index est la dernière position
        index_to_delete = self.index if self.index != -1 else len(self.controller.point_manager.points) - 1
        self.controller.point_manager.delete_points([index_to_delete])
        self.refresh_ui()


class DeletePointsCommand(PointListCommand):
    """Commande pour supprimer un ou plusieurs points de la liste."""
    def __init__(self, controller: MainController, main_window, indices: list):
        """Initialise la commande de suppression.

        :param indices: La liste des index des points à supprimer.
        """
        super().__init__(controller, main_window, f"Supprimer {len(indices)} point(s)")
        self.indices = sorted(indices)
        # On sauvegarde les points qu'on va supprimer pour pouvoir les restaurer
        self.deleted_points = [controller.point_manager.points[i] for i in self.indices]

    def redo(self):
        """Supprime les points de la liste."""
        self.controller.point_manager.delete_points(self.indices)
        self.refresh_ui()

    def undo(self):
        """Réinsère les points précédemment supprimés à leurs positions d'origine."""
        # On ré-insère les points supprimés à leurs positions d'origine
        for i, point in zip(self.indices, self.deleted_points):
            self.controller.point_manager.add_point(point, i)
        self.refresh_ui()


class MovePointCommand(PointListCommand):
    """Commande pour déplacer un point vers le haut ou le bas dans la liste."""
    def __init__(self, controller: MainController, main_window, index: int, direction: str):
        """Initialise la commande de déplacement.

        :param index: L'index du point à déplacer.
        :param direction: La direction du mouvement ('haut' or 'bas').
        """
        super().__init__(controller, main_window, f"Déplacer point vers le {direction}")
        self.index = index
        self.direction = direction

    def redo(self):
        """Exécute le déplacement."""
        if self.direction == "haut":
            self.controller.point_manager.move_point_up(self.index)
        else:
            self.controller.point_manager.move_point_down(self.index)
        self.refresh_ui()

    def undo(self):
        """Annule le déplacement en effectuant le mouvement inverse."""
        if self.direction == "haut":
            self.controller.point_manager.move_point_down(self.index - 1)
        else:
            self.controller.point_manager.move_point_up(self.index + 1)
        self.refresh_ui()


class ChangeCellCommand(PointListCommand):
    """Commande pour modifier la valeur d'une cellule dans le tableau de points."""
    def __init__(self, controller: MainController, main_window, row: int, col: int, old_value, new_value):
        """Initialise la commande de modification de cellule.

        :param row: L'index de la ligne de la cellule modifiée.
        :param col: L'index de la colonne de la cellule modifiée.
        :param old_value: La valeur de la cellule avant la modification.
        :param new_value: La nouvelle valeur de la cellule.
        """
        super().__init__(controller, main_window, f"Modifier cellule [{row + 1}, {col + 1}]")
        self.row = row
        self.col = col
        self.old_value = old_value
        self.new_value = new_value

    def redo(self):
        """Applique la nouvelle valeur à la cellule."""
        header = self.controller.get_point_headers()[self.col]
        point = self.controller.point_manager.points[self.row]

        # Conversion en type approprié
        try:
            if header == 'num_measurements':
                value = int(self.new_value)
            elif header != 'measurement_file':
                value = float(self.new_value)
            else:
                value = self.new_value
            setattr(point, header, value)
        except (ValueError, TypeError):
            setattr(point, header, self.old_value)

        self.refresh_ui()

    def undo(self):
        """Restaure l'ancienne valeur de la cellule."""
        header = self.controller.get_point_headers()[self.col]
        point = self.controller.point_manager.points[self.row]
        setattr(point, header, self.old_value)
        self.refresh_ui()