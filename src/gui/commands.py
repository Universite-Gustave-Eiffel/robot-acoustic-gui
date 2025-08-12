# src/gui/commands.py

from PySide6.QtGui import QUndoCommand
from src.main_controller import MainController


class PointListCommand(QUndoCommand):
    """
    Classe de base pour toutes les commandes qui modifient la liste de points
    et nécessitent de rafraîchir l'interface.
    """

    def __init__(self, controller: MainController, main_window, text, parent=None):
        super().__init__(text, parent)
        self.controller = controller
        self.main_window = main_window

    def redo(self):
        # La logique de l'action sera dans les sous-classes
        pass

    def undo(self):
        # La logique d'annulation sera dans les sous-classes
        pass

    def refresh_ui(self):
        """Notifie le contrôleur et la fenêtre de rafraîchir l'état."""
        # On signale que la liste a changé, ce qui déclenchera la mise à jour du tableau
        self.controller._notify_point_list_changed()
        # On met à jour l'état des boutons (grisés ou non)
        self.main_window._update_actions_state()


class AddPointCommand(PointListCommand):
    def __init__(self, controller: MainController, main_window, point_data=None, index=-1):
        super().__init__(controller, main_window, "Ajouter un point")
        self.point_data = point_data
        self.index = index

    def redo(self):
        self.controller.point_manager.add_point(self.point_data, self.index)
        self.refresh_ui()

    def undo(self):
        # Si on a ajouté à la fin, l'index est la dernière position
        index_to_delete = self.index if self.index != -1 else len(self.controller.point_manager.points) - 1
        self.controller.point_manager.delete_points([index_to_delete])
        self.refresh_ui()


class DeletePointsCommand(PointListCommand):
    def __init__(self, controller: MainController, main_window, indices: list):
        super().__init__(controller, main_window, f"Supprimer {len(indices)} point(s)")
        self.indices = sorted(indices)
        # On sauvegarde les points qu'on va supprimer pour pouvoir les restaurer
        self.deleted_points = [controller.point_manager.points[i] for i in self.indices]

    def redo(self):
        self.controller.point_manager.delete_points(self.indices)
        self.refresh_ui()

    def undo(self):
        # On ré-insère les points supprimés à leurs positions d'origine
        for i, point in zip(self.indices, self.deleted_points):
            self.controller.point_manager.add_point(point, i)
        self.refresh_ui()


class MovePointCommand(PointListCommand):
    def __init__(self, controller: MainController, main_window, index: int, direction: str):
        super().__init__(controller, main_window, f"Déplacer point vers le {direction}")
        self.index = index
        self.direction = direction

    def redo(self):
        if self.direction == "haut":
            self.controller.point_manager.move_point_up(self.index)
        else:  # bas
            self.controller.point_manager.move_point_down(self.index)
        self.refresh_ui()

    def undo(self):
        # On fait simplement le mouvement inverse
        if self.direction == "haut":
            # Le point est maintenant à l'index - 1, on le redescend
            self.controller.point_manager.move_point_down(self.index - 1)
        else:  # bas
            # Le point est maintenant à l'index + 1, on le remonte
            self.controller.point_manager.move_point_up(self.index + 1)
        self.refresh_ui()


class ChangeCellCommand(PointListCommand):
    def __init__(self, controller: MainController, main_window, row: int, col: int, old_value, new_value):
        super().__init__(controller, main_window, f"Modifier cellule [{row + 1}, {col + 1}]")
        self.row = row
        self.col = col
        self.old_value = old_value
        self.new_value = new_value

    def redo(self):
        # On met à jour directement le modèle de données
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
            # En cas d'erreur de conversion, on annule la modification
            setattr(point, header, self.old_value)

        self.refresh_ui()

    def undo(self):
        header = self.controller.get_point_headers()[self.col]
        point = self.controller.point_manager.points[self.row]
        setattr(point, header, self.old_value)
        self.refresh_ui()