#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QToolBar,
    QStatusBar, QMessageBox, QLineEdit, QMenu
)
from PySide6.QtGui import QIcon, QFont, QAction, QCloseEvent
from PySide6.QtCore import Qt, QSize, Slot, Signal


class ResourceManager:
    """Gestionnaire de ressources pour l'application."""

    BASE_DIR = Path(__file__).resolve().parent
    ICONS_DIR = BASE_DIR / 'icons_old'

    @classmethod
    def get_icon_path(cls, icon_name: str) -> str:
        """Retourne le chemin vers une icône."""
        path = cls.ICONS_DIR / icon_name
        if not path.is_file():
            print(f"Avertissement : Icône non trouvée à {path}")
            return ""
        return str(path)

    @classmethod
    def check_resources(cls) -> bool:
        """Vérifie si les ressources nécessaires sont disponibles."""
        return cls.ICONS_DIR.is_dir()


class MainWindow(QMainWindow):
    """Fenêtre principale de l'application de pilotage du robot."""

    def __init__(self) -> None:
        """Initialise la fenêtre principale."""
        super().__init__()

        # Attributs internes
        self._actions: Dict[str, QAction] = {}

        # Configuration de la fenêtre
        self.setWindowTitle('Pilotage du robot')
        self.setGeometry(150, 150, 700, 500)
        self.setWindowIcon(QIcon(ResourceManager.get_icon_path('Window-icon.png')))

        # Initialisation de l'interface
        self._setup_ui()

        # Affichage
        self.show()

    def _setup_ui(self) -> None:
        """Configure l'interface utilisateur."""
        self._create_actions()
        self._create_menus()
        self._create_toolbars()
        self._create_central_widget()
        self._create_statusbar()

    def _create_actions(self) -> None:
        """Crée toutes les actions de l'application."""
        # Actions du menu Fichier
        self._add_action('nouveau', 'document-new.png', '&Nouveau',
                         "Créer un nouveau document")
        self._add_action('ouvrir', 'document-open.png', '&Ouvrir...',
                         "Ouvrir un document existant")
        self._add_action('enregistrer', 'document-save.png', '&Enregistrer',
                         "Enregistrer le document courant", 'Ctrl+S')
        self._add_action('enregistrer_sous', 'document-save-as.png', 'Enregistrer &sous...',
                         "Enregistrer le document sous un nouveau nom")
        self._add_action('proprietes', 'document-properties.png', 'P&ropriétés',
                         "Afficher les propriétés du document")
        self._add_action('quitter', 'system-log-out.png', '&Quitter',
                         "Quitter l'application", 'Ctrl+Q')

        # Actions du menu Édition
        self._add_action('undo', 'edit-undo.png', '&Annuler',
                         "Annuler la dernière action", 'Ctrl+Z')
        self._add_action('redo', 'edit-redo.png', '&Rétablir',
                         "Rétablir la dernière action annulée", 'Ctrl+Y')

        # Actions du menu Outils
        self._add_action('measurement_settings', 'preferences-desktop.png', 'Options Mesures',
                         "Configurer les options de mesure")
        self._add_action('telecommande', 'input-gaming.png', 'Télécommande',
                         "Ouvrir la télécommande")

        # Actions du menu Aide
        self._add_action('apropos', 'help-browser.png', '&À propos...',
                         "Afficher les informations sur l'application")

        # Actions Séquence
        self._add_action('stop_sequence', 'media-playback-stop.png', 'Arrêter séquence',
                         "Arrêter la séquence")
        self._add_action('start_sequence', 'media-playback-start.png', 'Démarrer séquence',
                         "Démarrer la séquence")
        self._add_action('measure_next_point', 'one.png', 'Mesurer point suivant',
                         "Mesurer le prochain point")

        # Actions Pulse
        self._add_action('show_pulse', 'pulse.png', 'Afficher Pulse',
                         "Afficher Pulse")
        self._add_action('start_measurement', 'Start.png', 'Démarrer mesure',
                         "Démarrer la mesure")
        self._add_action('save_measurement', 'Save_Measurement2.png', 'Enregistrer mesure',
                         "Enregistrer la mesure")

        # Actions Robot
        self._add_action('stop_robot', 'media-playback-pause.png', 'Arrêter robot',
                         "Arrêter le robot")
        self._add_action('goto_parking', 'media-eject.png', 'Aller au parking',
                         "Aller au parking")
        self._add_action('goto_zero', 'go-bottom.png', 'Aller au zéro',
                         "Aller au zéro")
        self._add_action('goto_selected', 'go-jump.png', 'Position sélectionnée',
                         "Aller à la position sélectionnée")

        # Connexion des signaux
        self._connect_action_signals()

    def _add_action(self, name: str, icon_file: str, text: str,
                    status_tip: str, shortcut: str = None) -> None:
        """Ajoute une action à la collection d'actions."""
        action = QAction(QIcon(ResourceManager.get_icon_path(icon_file)), text, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.setStatusTip(status_tip)
        self._actions[name] = action

    def _connect_action_signals(self) -> None:
        """Connecte les signaux des actions aux slots."""
        # Fichier
        self._actions['nouveau'].triggered.connect(lambda: self._on_action("Nouveau"))
        self._actions['ouvrir'].triggered.connect(lambda: self._on_action("Ouvrir"))
        self._actions['enregistrer'].triggered.connect(lambda: self._on_action("Enregistrer"))
        self._actions['enregistrer_sous'].triggered.connect(lambda: self._on_action("Enregistrer sous"))
        self._actions['proprietes'].triggered.connect(lambda: self._on_action("Propriétés"))
        self._actions['quitter'].triggered.connect(self.close)

        # Édition
        self._actions['undo'].triggered.connect(lambda: self._on_action("Annuler"))
        self._actions['redo'].triggered.connect(lambda: self._on_action("Rétablir"))

        # Outils
        self._actions['measurement_settings'].triggered.connect(
            lambda: self._on_action("Options Mesures"))
        self._actions['telecommande'].triggered.connect(
            lambda: self._on_action("Télécommande"))

        # Aide
        self._actions['apropos'].triggered.connect(self._on_about)

        # Séquence
        self._actions['stop_sequence'].triggered.connect(
            lambda: self._on_action("Arrêter Séquence"))
        self._actions['start_sequence'].triggered.connect(
            lambda: self._on_action("Démarrer Séquence"))
        self._actions['measure_next_point'].triggered.connect(
            lambda: self._on_action("Mesurer Prochain Point"))

        # Pulse
        self._actions['show_pulse'].triggered.connect(lambda: self._on_action("Afficher Pulse"))
        self._actions['start_measurement'].triggered.connect(
            lambda: self._on_action("Démarrer Mesure"))
        self._actions['save_measurement'].triggered.connect(
            lambda: self._on_action("Enregistrer Mesure"))

        # Robot
        self._actions['stop_robot'].triggered.connect(lambda: self._on_action("Arrêter Robot"))
        self._actions['goto_parking'].triggered.connect(
            lambda: self._on_action("Aller au Parking"))
        self._actions['goto_zero'].triggered.connect(lambda: self._on_action("Aller au Zéro"))
        self._actions['goto_selected'].triggered.connect(
            lambda: self._on_action("Aller à la Position Sélectionnée"))

    def _create_menus(self) -> None:
        """Crée la barre de menu et les menus."""
        menu_bar = self.menuBar()

        # Menu Fichier
        menu_fichier = menu_bar.addMenu('&Fichier')
        menu_fichier.addAction(self._actions['nouveau'])
        menu_fichier.addSeparator()
        menu_fichier.addAction(self._actions['ouvrir'])
        menu_fichier.addAction(self._actions['enregistrer'])
        menu_fichier.addAction(self._actions['enregistrer_sous'])
        menu_fichier.addSeparator()
        menu_fichier.addAction(self._actions['quitter'])

        # Menu Édition
        menu_edition = menu_bar.addMenu('&Édition')
        menu_edition.addAction(self._actions['undo'])
        menu_edition.addAction(self._actions['redo'])

        # Menu Outils
        menu_outils = menu_bar.addMenu('&Outils')
        menu_outils.addAction(self._actions['measurement_settings'])
        menu_outils.addSeparator()
        menu_outils.addAction(self._actions['telecommande'])

        # Menu Aide
        menu_aide = menu_bar.addMenu('&Aide')
        menu_aide.addAction(self._actions['apropos'])

    def _create_toolbars(self) -> None:
        """Crée les barres d'outils."""
        # Toolbar Séquence
        toolbar_sequence = QToolBar("Outils Séquence")
        toolbar_sequence.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar_sequence)
        toolbar_sequence.addWidget(QLabel("Séquence : "))
        toolbar_sequence.addAction(self._actions['stop_sequence'])
        toolbar_sequence.addAction(self._actions['start_sequence'])
        toolbar_sequence.addAction(self._actions['measure_next_point'])

        # Toolbar Pulse
        toolbar_pulse = QToolBar("Outils Pulse")
        toolbar_pulse.setIconSize(QSize(24, 24))
        toolbar_pulse.setFixedWidth(300)
        self.addToolBar(toolbar_pulse)
        toolbar_pulse.addWidget(QLabel("Pulse : "))
        toolbar_pulse.addAction(self._actions['show_pulse'])
        toolbar_pulse.addAction(self._actions['start_measurement'])
        toolbar_pulse.addSeparator()
        toolbar_pulse.addWidget(QLineEdit("Fichier_mesure.txt"))
        toolbar_pulse.addAction(self._actions['save_measurement'])

        # Toolbar Robot (nouvelle rangée)
        toolbar_robot = QToolBar("Outils Robot")
        toolbar_robot.setIconSize(QSize(24, 24))
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        self.addToolBar(toolbar_robot)
        toolbar_robot.addWidget(QLabel("Robot : "))
        toolbar_robot.addAction(self._actions['stop_robot'])
        toolbar_robot.addAction(self._actions['goto_parking'])
        toolbar_robot.addAction(self._actions['goto_zero'])
        toolbar_robot.addAction(self._actions['goto_selected'])

        # Toolbar Fichier
        toolbar_fichier = QToolBar("Outils Fichier")
        toolbar_fichier.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar_fichier)
        toolbar_fichier.addAction(self._actions['nouveau'])
        toolbar_fichier.addAction(self._actions['ouvrir'])
        toolbar_fichier.addAction(self._actions['enregistrer'])

        # Toolbar Édition (barre verticale à gauche)
        toolbar_edition = QToolBar("Outils Édition")
        toolbar_edition.setIconSize(QSize(24, 24))
        toolbar_edition.setOrientation(Qt.Orientation.Vertical)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, toolbar_edition)
        toolbar_edition.addAction(self._actions['undo'])

    def _create_central_widget(self) -> None:
        """Crée le widget central et son contenu."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        layout_principal = QVBoxLayout(central_widget)
        label_central = QLabel("Zone Principale", self)
        label_central.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = label_central.font()
        font.setPointSize(18)
        label_central.setFont(font)
        layout_principal.addWidget(label_central)

    def _create_statusbar(self) -> None:
        """Configure la barre de statut."""
        self.statusBar().showMessage('Prêt')

    # --- Slots ---
    @Slot(str)
    def _on_action(self, action_name: str) -> None:
        """Gère les actions génériques."""
        print(f"Action déclenchée : {action_name}")
        self.statusBar().showMessage(f"Action : {action_name}", 3000)

    @Slot()
    def _on_about(self) -> None:
        """Affiche la boîte de dialogue À propos."""
        print("Action déclenchée : À propos")
        QMessageBox.about(
            self,
            "À propos...",
            "Logiciel de pilotage du robot v0.1\nPour l'UMRAE."
        )

    @Slot(bool)
    def _on_toggle_fullscreen(self, checked: bool) -> None:
        """Bascule l'affichage en plein écran."""
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()
        status = "Plein Écran Activé" if checked else "Plein Écran Désactivé"
        self.statusBar().showMessage(status, 3000)
        print(f"Action déclenchée : {status}")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Gère l'événement de fermeture de la fenêtre."""
        reponse = QMessageBox.question(
            self, 'Confirmation', "Quitter l'application ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reponse == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()


def main() -> int:
    """Fonction principale de l'application."""
    # Vérifier les ressources
    if not ResourceManager.check_resources():
        print(f"Erreur critique : Le dossier d'icônes '{ResourceManager.ICONS_DIR}' est introuvable.")
        return 1

    # Créer et exécuter l'application
    app = QApplication(sys.argv)
    fenetre = MainWindow()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())