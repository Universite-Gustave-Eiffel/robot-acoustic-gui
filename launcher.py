from src.gui.new_gui import run_application, setup_logging
import sys

if __name__ == "__main__":
    """
        Point d'entrée principal de l'application Robot Acoustique GUI.

        Ce script a deux responsabilités uniques :
        1. Configurer le système de logging pour toute l'application.
        2. Lancer la boucle principale de l'application Qt.

        Toute la logique de l'application se trouve dans le module `src`.
        """
    setup_logging()
    sys.exit(run_application())
