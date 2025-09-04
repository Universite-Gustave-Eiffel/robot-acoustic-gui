from dataclasses import dataclass, asdict
import csv
import copy


@dataclass
class Point:
    """Représente un unique point de mesure avec ses coordonnées et métadonnées.

    Utilise un `dataclass` pour une définition concise et claire.
    Chaque attribut correspond à une colonne dans le tableau de l'interface
    et dans les fichiers de sauvegarde.

    :param x: Coordonnée X de la capsule (mm).
    :param y: Coordonnée Y de la capsule (mm).
    :param z: Coordonnée Z de la capsule (mm).
    :param theta: Angle de rotation Theta (degrés).
    :param phi: Angle d'inclinaison Phi (degrés).
    :param measurement_file: Nom de base du fichier de mesure associé à ce point.
    :param num_measurements: Nombre de mesures à effectuer à cette position.
    """
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    theta: float = 0.0
    phi: float = 0.0
    measurement_file: str = ""
    num_measurements: int = 1


class PointManager:
    """Gère une liste de points de mesure.

    Cette classe encapsule toutes les opérations sur la liste de points :
    chargement/sauvegarde depuis/vers des fichiers, ajout, suppression,
    et modification des points.
    """
    def __init__(self):
        """Initialise le gestionnaire de points avec une liste vide."""
        self.points = []
        self.headers = list(Point.__annotations__.keys())

    def update_from_list_of_dicts(self, list_of_dicts: list[dict]):
        """Met à jour la liste de points à partir d'une liste de dictionnaires.

        Cette méthode est utilisée pour synchroniser les données internes avec
        les données provenant de l'interface graphique. Elle gère la conversion
        et la validation des types de données.

        :param list_of_dicts: Une liste de dictionnaires, où chaque dictionnaire
                              représente un point.
        """
        self.points.clear()
        for row_dict in list_of_dicts:
            point_data = {}
            for h in self.headers:
                value = row_dict.get(h)
                if h == 'measurement_file':
                    point_data[h] = str(value) if value is not None else ""
                elif h == 'num_measurements':
                    try:
                        point_data[h] = int(value) if value is not None else 1
                    except (ValueError, TypeError):
                        point_data[h] = 1
                else:
                    try:
                        point_data[h] = float(value) if value is not None else 0.0
                    except (ValueError, TypeError):
                        point_data[h] = 0.0
            self.points.append(Point(**point_data))

    def load_from_file(self, file_path: str) -> bool:
        """Charge une liste de points depuis un fichier.

        Tente de détecter automatiquement le format du fichier (CSV, TSV,
        avec ou sans en-tête) en utilisant le `csv.Sniffer`.

        :param file_path: Le chemin vers le fichier de points.
        :return: ``True`` si le chargement a réussi, ``False`` sinon.
        """
        try:
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                try:
                    dialect = csv.Sniffer().sniff(f.read(2048), delimiters=',;\t ')
                    f.seek(0)
                except csv.Error:
                    dialect = csv.excel_tab
                    f.seek(0)
                has_header = csv.Sniffer().has_header(f.read(2048))
                f.seek(0)

                if has_header:
                    reader = csv.DictReader(f, dialect=dialect)
                else:
                    first_line = next(csv.reader(f, dialect=dialect))
                    num_columns = len(first_line)
                    f.seek(0)
                    active_headers = self.headers[:num_columns]
                    reader = csv.DictReader(f, fieldnames=active_headers, dialect=dialect)

                self.update_from_list_of_dicts(list(reader))
            return True
        except Exception as e:
            print(f"Erreur lors du chargement du fichier de points : {e}")
            return False

    def save_to_file(self, file_path: str) -> bool:
        """Sauvegarde la liste de points actuelle dans un fichier CSV.

        :param file_path: Le chemin du fichier de destination.
        :return: ``True`` si la sauvegarde a réussi, ``False`` sinon.
        """
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
        """Retourne la liste de points sous forme de liste de dictionnaires.

        Ce format est facilement utilisable par l'interface graphique pour
        remplir le tableau.

        :return: Une liste de dictionnaires.
        """
        return [asdict(p) for p in self.points]

    def get_points_copy(self):
        """Retourne une copie profonde de la liste des points.

        Utilisé pour passer une copie sûre des points au séquenceur, afin
        d'éviter que des modifications dans la GUI n'affectent une séquence
        en cours d'exécution.

        :return: Une copie de la liste d'objets :class:`Point`.
        """
        return copy.deepcopy(self.points)

    def add_point(self, point: Point = None, index: int = -1):
        """Ajoute un point à la liste.

        :param point: L'objet :class:`Point` à ajouter. Si ``None``, un point
                      par défaut est créé.
        :param index: La position à laquelle insérer le point. Si -1, le point
                      est ajouté à la fin.
        """
        if point is None:
            point = Point()
        if index == -1 or index >= len(self.points):
            self.points.append(point)
        else:
            self.points.insert(index, point)

    def delete_points(self, indices: list[int]):
        """Supprime un ou plusieurs points de la liste par leurs index.

        :param indices: Une liste d'index des points à supprimer.
        """
        for index in sorted(indices, reverse=True):
            if 0 <= index < len(self.points):
                del self.points[index]

    def move_point_up(self, index: int):
        """Déplace un point d'une position vers le haut dans la liste.

        :param index: L'index du point à déplacer.
        """
        if 0 < index < len(self.points):
            self.points[index], self.points[index - 1] = self.points[index - 1], self.points[index]

    def move_point_down(self, index: int):
        """Déplace un point d'une position vers le bas dans la liste.

        :param index: L'index du point à déplacer.
        """
        if 0 <= index < len(self.points) - 1:
            self.points[index], self.points[index + 1] = self.points[index + 1], self.points[index]