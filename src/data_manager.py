# src/data_manager.py
from dataclasses import dataclass, asdict
import csv


@dataclass
class Point:
    """Représente un unique point de mesure avec ses coordonnées."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    theta: float = 0.0
    phi: float = 0.0
    # TODO: Ajouter les autres propriétés comme le nom, les répétitions, etc.


class PointManager:
    """Gère la liste des points (chargement, sauvegarde, manipulation)."""

    def __init__(self):
        self.points = []
        self.headers = [field for field in Point.__annotations__]

    def load_from_file(self, file_path: str) -> bool:
        """Charge une liste de points depuis un fichier CSV ou TSV."""
        try:
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                dialect = csv.Sniffer().sniff(f.read(1024))
                f.seek(0)
                reader = csv.DictReader(f, dialect=dialect)

                self.points.clear()
                for row in reader:
                    point_data = {h: float(row.get(h, 0.0)) for h in self.headers}
                    self.points.append(Point(**point_data))
            return True
        except Exception as e:
            print(f"Erreur lors du chargement du fichier de points : {e}")
            return False

    def save_to_file(self, file_path: str) -> bool:
        """Sauvegarde la liste de points dans un fichier CSV."""
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.headers)
                writer.writeheader()
                writer.writerows([asdict(p) for p in self.points])
            return True
        except Exception as e:
            print(f"Erreur lors de la sauvegarde du fichier de points : {e}")
            return False

    def get_points_as_list_of_dicts(self):
        """Retourne les points dans un format simple pour la GUI."""
        return [asdict(p) for p in self.points]

    def add_point(self, point: Point = None, index: int = -1):
        """Ajoute un point à la liste. Par défaut, ajoute un point vide à la fin."""
        if point is None:
            point = Point()

        if index == -1 or index >= len(self.points):
            self.points.append(point)
        else:
            self.points.insert(index, point)

    def delete_points(self, indices: list[int]):
        """Supprime les points aux indices spécifiés."""
        for index in sorted(indices, reverse=True):
            if 0 <= index < len(self.points):
                del self.points[index]

    def move_point_up(self, index: int):
        """Déplace le point à l'index donné d'une position vers le haut."""
        if 0 < index < len(self.points):
            self.points[index], self.points[index - 1] = self.points[index - 1], self.points[index]

    def move_point_down(self, index: int):
        """Déplace le point à l'index donné d'une position vers le bas."""
        if 0 <= index < len(self.points) - 1:
            self.points[index], self.points[index + 1] = self.points[index + 1], self.points[index]