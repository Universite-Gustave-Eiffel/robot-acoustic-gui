from pathlib import Path
import sys
from PySide6.QtGui import QPixmap, QIcon

class ResourceManager:
    """Gestionnaire de ressources (icônes, images) pour l'application."""

    @staticmethod
    def _icons_candidates() -> list[Path]:
        """
        Retourne les chemins possibles du dossier des icônes, en dev et en exécutable PyInstaller.
        Dans le build (onedir), les datas sont copiées sous 'gui/new_icons' (voir .spec).
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
        path = cls.ICONS_DIR / icon_name
        if not path.is_file():
            print(f"Avertissement : Icône non trouvée à {path}")
            return ""
        return str(path)

    @classmethod
    def get_pixmap(cls, pixmap_name: str) -> QPixmap:
        path = cls.ICONS_DIR / pixmap_name
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            print(f"Avertissement : Image non trouvée à {path}")
        return pixmap
