from pathlib import Path
from PySide6.QtGui import QPixmap, QIcon

class ResourceManager:
    """Gestionnaire de ressources (icônes, images) pour l'application."""
    BASE_DIR = Path(__file__).resolve().parent
    ICONS_DIR = BASE_DIR / 'new_icons'

    @classmethod
    def get_icon_path(cls, icon_name: str) -> str:
        path = cls.ICONS_DIR / icon_name
        if not path.is_file():
            print(f"Avertissement : Icône non trouvée à {path}")
            return ""
        return str(path)

    @classmethod
    def get_pixmap(cls, pixmap_name: str) -> QPixmap:
        path = str(cls.ICONS_DIR / pixmap_name)
        pixmap = QPixmap(path)
        if pixmap.isNull():
            print(f"Avertissement : Image pour splash screen non trouvée à {path}")
        return pixmap