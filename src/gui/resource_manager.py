from pathlib import Path
import sys
from PySide6.QtGui import QPixmap, QIcon

class ResourceManager:
    """Gestionnaire de ressources statiques (icônes, images) de l'application.

    Cette classe fournit des méthodes statiques pour obtenir les chemins d'accès
    aux fichiers de ressources. Sa principale responsabilité est de résoudre
    correctement l'emplacement du dossier des icônes, que l'application soit
    lancée en mode développement (depuis les sources) ou en mode production
    (depuis un exécutable PyInstaller).

    Elle utilise la variable `sys._MEIPASS` pour détecter si le programme
    est "gelé" par PyInstaller.
    """

    @staticmethod
    def _icons_candidates() -> list[Path]:
        """Retourne les chemins possibles du dossier des icônes. (Interne)

        Construit une liste de chemins candidats en fonction du contexte
        d'exécution (développement vs. production).

        :return: Une liste d'objets `Path`.
        """
        candidates: list[Path] = []
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            base = Path(sys._MEIPASS)
            # Emplacements probables en exécutable
            candidates += [
                base / "gui" / "new_icons",   # correspond à ('src/gui/new_icons', 'gui/new_icons')
                base / "new_icons",           # fallback
                Path.cwd() / "gui" / "new_icons",  # au cas où l'app soit lancée depuis un autre cwd
            ]
        else:
            # Mode développement (exécution depuis les sources)
            base = Path(__file__).resolve().parent
            candidates += [
                base / "new_icons",           # src/gui/new_icons
                base.parent / "new_icons",    # src/new_icons (fallback)
            ]
        return candidates

    # Résout une fois pour toutes
    ICONS_DIR: Path = next((p for p in _icons_candidates.__func__() if p.is_dir()),
                           (_icons_candidates.__func__()[0]))

    @classmethod
    def get_icon_path(cls, icon_name: str) -> str:
        """Construit le chemin absolu vers un fichier d'icône.

        :param icon_name: Le nom du fichier de l'icône (ex: 'play.png').
        :return: Le chemin complet sous forme de chaîne de caractères.
        """
        path = cls.ICONS_DIR / icon_name
        if not path.is_file():
            print(f"Avertissement : Icône non trouvée à {path}")
            return ""
        return str(path)

    @classmethod
    def get_pixmap(cls, pixmap_name: str) -> QPixmap:
        """Charge une image depuis les ressources et la retourne comme un objet QPixmap.

        :param pixmap_name: Le nom du fichier de l'image (ex: 'splash.png').
        :return: Un objet :class:`QPixmap`.
        """
        path = cls.ICONS_DIR / pixmap_name
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            print(f"Avertissement : Image non trouvée à {path}")
        return pixmap
