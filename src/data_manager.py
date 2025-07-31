# src/data_manager.py
from dataclasses import dataclass, asdict
import csv
import copy


@dataclass
class Point:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    theta: float = 0.0
    phi: float = 0.0
    measurement_file: str = ""
    # NOUVEAU CHAMP pour la compatibilité avec l'ancien format
    num_measurements: int = 1


class PointManager:
    def __init__(self):
        self.points = []
        # L'ordre des en-têtes est maintenant défini par la dataclass
        self.headers = list(Point.__annotations__.keys())

    def update_from_list_of_dicts(self, list_of_dicts: list[dict]):
        """Met à jour la liste de points à partir d'une liste de dictionnaires."""
        self.points.clear()
        for row_dict in list_of_dicts:
            point_data = {}
            for h in self.headers:
                value = row_dict.get(h)
                # Conversion en type approprié
                if h == 'measurement_file':
                    point_data[h] = str(value) if value is not None else ""
                elif h == 'num_measurements':
                    try:
                        point_data[h] = int(value) if value is not None else 1
                    except (ValueError, TypeError):
                        point_data[h] = 1  # Valeur par défaut
                else:
                    try:
                        point_data[h] = float(value) if value is not None else 0.0
                    except (ValueError, TypeError):
                        point_data[h] = 0.0  # Valeur par défaut si la conversion échoue
            self.points.append(Point(**point_data))

    def load_from_file(self, file_path: str) -> bool:
        """
        Charge une liste de points depuis un fichier, en essayant de détecter
        automatiquement le format (CSV, TSV, avec ou sans en-tête).
        """
        try:
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                # Essayer de deviner le dialecte (séparateur, etc.)
                try:
                    dialect = csv.Sniffer().sniff(f.read(2048), delimiters=',;\t ')
                    f.seek(0)
                except csv.Error:
                    # Si Sniffer échoue, on suppose une tabulation par défaut
                    dialect = csv.excel_tab
                    f.seek(0)

                # Vérifier si le fichier a un en-tête
                has_header = csv.Sniffer().has_header(f.read(2048))
                f.seek(0)

                if has_header:
                    reader = csv.DictReader(f, dialect=dialect)
                else:
                    # Si pas d'en-tête, on utilise nos en-têtes par défaut
                    # en s'assurant de ne pas dépasser le nombre de colonnes du fichier
                    first_line = next(csv.reader(f, dialect=dialect))
                    num_columns = len(first_line)
                    f.seek(0)

                    # On utilise seulement les en-têtes correspondants aux colonnes présentes
                    active_headers = self.headers[:num_columns]
                    reader = csv.DictReader(f, fieldnames=active_headers, dialect=dialect)

                self.update_from_list_of_dicts(list(reader))
            return True
        except Exception as e:
            print(f"Erreur lors du chargement du fichier de points : {e}")
            return False

    def save_to_file(self, file_path: str) -> bool:
        """Sauvegarde la liste de points dans un fichier CSV standard."""
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

    def get_points_copy(self):
        """Retourne une copie profonde de la liste des points."""
        return copy.deepcopy(self.points)

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