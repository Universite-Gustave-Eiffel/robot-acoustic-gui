# src/data_manager.py
from dataclasses import dataclass, asdict
import csv

@dataclass
class Point:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    theta: float = 0.0
    phi: float = 0.0
    measurement_file: str = ""

class PointManager:
    def __init__(self):
        self.points = []
        self.headers = list(Point.__annotations__.keys())

    def update_from_list_of_dicts(self, list_of_dicts: list[dict]):
        """Met à jour la liste de points à partir d'une liste de dictionnaires."""
        self.points.clear()
        for row_dict in list_of_dicts:
            point_data = {}
            for h in self.headers:
                value = row_dict.get(h)
                # Conversion en float, sauf pour le champ de fichier
                if h == 'measurement_file':
                    point_data[h] = str(value) if value is not None else ""
                else:
                    try:
                        point_data[h] = float(value) if value is not None else 0.0
                    except (ValueError, TypeError):
                        point_data[h] = 0.0 # Valeur par défaut si la conversion échoue
            self.points.append(Point(**point_data))

    def load_from_file(self, file_path: str) -> bool:
        try:
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                dialect = csv.Sniffer().sniff(f.read(1024))
                f.seek(0)
                reader = csv.DictReader(f, dialect=dialect)
                self.update_from_list_of_dicts(list(reader))
            return True
        except Exception as e:
            print(f"Erreur lors du chargement du fichier de points : {e}")
            return False

    def save_to_file(self, file_path: str) -> bool:
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
        return [asdict(p) for p in self.points]

    def add_point(self, point: Point = None, index: int = -1):
        if point is None:
            point = Point()
        if index == -1 or index >= len(self.points):
            self.points.append(point)
        else:
            self.points.insert(index, point)

    def delete_points(self, indices: list[int]):
        for index in sorted(indices, reverse=True):
            if 0 <= index < len(self.points):
                del self.points[index]

    def move_point_up(self, index: int):
        if 0 < index < len(self.points):
            self.points[index], self.points[index - 1] = self.points[index - 1], self.points[index]

    def move_point_down(self, index: int):
        if 0 <= index < len(self.points) - 1:
            self.points[index], self.points[index + 1] = self.points[index + 1], self.points[index]