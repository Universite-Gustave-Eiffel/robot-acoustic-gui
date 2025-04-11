import sys
from pathlib import Path

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel,
                             QVBoxLayout, QAction, QToolBar, QStatusBar,
                             QMessageBox, QLineEdit)
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt, QSize

# --- Chemins et fonction get_icon_path (inchangés) ---
BASE_DIR = Path(__file__).resolve().parent
ICONS_DIR = BASE_DIR / 'icons_old'

def get_icon_path(icon_name):
    path = ICONS_DIR / icon_name
    if not path.is_file():
        print(f"Avertissement : Icône non trouvée à {path}")
        return ""
    return str(path)

# 1. Classe de la fenêtre principale
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._create_actions()     # 1. Créer les objets Action
        self._initialiseUI()     # 2. Configurer la fenêtre et appeler les autres helpers

    def _initialiseUI(self):
        # --- Configuration générale ---
        self.setWindowTitle('Pilotage du robot (Old)')
        self.setGeometry(150, 150, 700, 500)
        self.setWindowIcon(QIcon(get_icon_path('Window-icon.png')))

        # --- Appeler les méthodes helper ---
        self._create_menus()       # Créer les menus
        self._create_toolbars()    # Créer les toolbars
        self._create_central_widget() # Créer la zone centrale
        self._create_statusbar()   # Créer la status bar
        self._connect_signals() # Connecte les signaux restants (si pas déjà fait dans _creer_actions)

        # --- Afficher la fenêtre ---
        self.show()

    # --- Méthodes Helper ---

    def _create_actions(self):
        """Crée toutes les QAction de l'application."""
        # == Actions Fichier ==
        self.act_nouveau = QAction(QIcon(get_icon_path('document-new.png')), '&Nouveau', self)
        self.act_ouvrir = QAction(QIcon(get_icon_path('document-open.png')), '&Ouvrir...', self)
        self.act_enregistrer = QAction(QIcon(get_icon_path('document-save.png')), '&Enregistrer', self)
        self.act_enregistrer.setShortcut('Ctrl+S')
        self.act_enregistrer_sous = QAction(QIcon(get_icon_path('document-save-as.png')), 'Enregistrer &sous...', self)
        self.act_proprietes = QAction(QIcon(get_icon_path('document-properties.png')), 'P&ropriétés', self)
        self.act_quitter = QAction(QIcon(get_icon_path('system-log-out.png')), '&Quitter', self)
        self.act_quitter.setShortcut('Ctrl+Q')

        # == Actions Édition ==
        self.act_undo = QAction(QIcon(get_icon_path('edit-undo.png')), '&Annuler', self)
        self.act_undo.setShortcut('Ctrl+Z')
        self.act_redo = QAction(QIcon(get_icon_path('edit-redo.png')), '&Rétablir', self)
        self.act_redo.setShortcut('Ctrl+Y')

        # == Actions Outils ==
        self.act_measurement_settings = QAction(QIcon(get_icon_path('preferences-desktop.png')), 'Options Mesures', self)
        self.act_telecommande = QAction(QIcon(get_icon_path('input-gaming.png')), 'Télécommande', self)

        # == Actions Aide ==
        self.act_apropos = QAction(QIcon(get_icon_path('help-browser.png')), '&À propos...', self)

        # == Actions Séquence ==
        self.act_stop_sequence = QAction(QIcon(get_icon_path('media-playback-stop.png')), '&Séquence', self)
        self.act_start_sequence = QAction(QIcon(get_icon_path('media-playback-start.png')), '&Séquence', self)
        self.act_measure_next_point = QAction(QIcon(get_icon_path('one.png')), '&Mesurer', self)

        # == Actions Pulse ==
        self.act_show_pulse = QAction(QIcon(get_icon_path('pulse.png')), '&Afficher Pulse', self)
        self.act_start_measurement = QAction(QIcon(get_icon_path('Start.png')), '&Démarrer la mesure', self)
        self.act_save_measurement = QAction(QIcon(get_icon_path('Save_Measurement2.png')), '&Enregistrer la mesure', self)

        # == Actions Robot ==
        self.act_stop_robot = QAction(QIcon(get_icon_path('media-playback-pause.png')), '&Arrêter le robot', self)
        self.act_goto_parking = QAction(QIcon(get_icon_path('media-eject.png')), '&Aller au parking', self)
        self.act_goto_zero = QAction(QIcon(get_icon_path('go-bottom.png')), '&Aller au zéro', self)
        self.act_goto_selected = QAction(QIcon(get_icon_path('go-jump.png')), '&Aller à la position sélectionnée', self)

        # Ajouter les StatusTips ici ou dans une méthode séparée si ça devient long
        self.act_nouveau.setStatusTip("Créer un nouveau document")
        self.act_ouvrir.setStatusTip("Ouvrir un document existant")
        self.act_enregistrer.setStatusTip("Enregistrer le document courant")
        self.act_enregistrer_sous.setStatusTip("Enregistrer le document sous un nouveau nom")
        self.act_proprietes.setStatusTip("Afficher les propriétés du document")
        self.act_quitter.setStatusTip("Quitter l'application")
        self.act_undo.setStatusTip("Annuler la dernière action")
        self.act_redo.setStatusTip("Rétablir la dernière action annulée")
        self.act_measurement_settings.setStatusTip("Configurer les options de mesure")
        self.act_telecommande.setStatusTip("Ouvrir la télécommande")
        self.act_apropos.setStatusTip("Afficher les informations sur l'application")
        self.act_stop_sequence.setStatusTip("Arrêter la séquence")
        self.act_start_sequence.setStatusTip("Démarrer la séquence")
        self.act_measure_next_point.setStatusTip("Mesurer le prochain point")
        self.act_show_pulse.setStatusTip("Afficher Pulse")
        self.act_start_measurement.setStatusTip("Démarrer la mesure")
        self.act_save_measurement.setStatusTip("Enregistrer la mesure")
        self.act_stop_robot.setStatusTip("Arrêter le robot")
        self.act_goto_parking.setStatusTip("Aller au parking")
        self.act_goto_zero.setStatusTip("Aller au zéro")
        self.act_goto_selected.setStatusTip("Aller à la position sélectionnée")
        # ... (etc. pour toutes les actions)

    def _create_menus(self):
        """Crée la barre de menu et les menus."""
        menu_bar = self.menuBar()

        menu_fichier = menu_bar.addMenu('&Fichier')
        menu_fichier.addAction(self.act_nouveau)
        menu_fichier.addSeparator()
        menu_fichier.addAction(self.act_ouvrir)
        menu_fichier.addAction(self.act_enregistrer)
        menu_fichier.addAction(self.act_enregistrer_sous)
        menu_fichier.addSeparator()
        menu_fichier.addAction(self.act_quitter)

        menu_edition = menu_bar.addMenu('&Édition')
        menu_edition.addAction(self.act_undo)
        menu_edition.addAction(self.act_redo)


        menu_outils = menu_bar.addMenu('&Outils')
        menu_outils.addAction(self.act_measurement_settings)
        menu_outils.addSeparator()
        menu_outils.addAction(self.act_telecommande)

        menu_aide = menu_bar.addMenu('&Aide')
        menu_aide.addAction(self.act_apropos)
        # ... (actions aide) ...

    def _create_toolbars(self):
        """Crée les barres d'outils."""
        toolbar_sequence = QToolBar("Outils Séquence")
        toolbar_sequence.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar_sequence)
        toolbar_sequence.addWidget(QLabel("Séquence : "))
        toolbar_sequence.addAction(self.act_stop_sequence)
        toolbar_sequence.addAction(self.act_start_sequence)
        toolbar_sequence.addAction(self.act_measure_next_point)

        toolbar_pulse = QToolBar("Outils Pulse")
        toolbar_pulse.setIconSize(QSize(24, 24))
        toolbar_pulse.setFixedWidth(300)
        self.addToolBar(toolbar_pulse)
        toolbar_pulse.addWidget(QLabel("Pulse : "))
        toolbar_pulse.addAction(self.act_show_pulse)
        toolbar_pulse.addAction(self.act_start_measurement)
        toolbar_pulse.addSeparator()
        toolbar_pulse.addWidget(QLineEdit("Fichier_mesure.txt"))
        toolbar_pulse.addAction(self.act_save_measurement)

        toolbar_robot = QToolBar("Outils Robot")
        toolbar_robot.setIconSize(QSize(24, 24))
        self.addToolBarBreak(Qt.TopToolBarArea) # S'assure que la barre de robot est en haut
        self.addToolBar(toolbar_robot)
        toolbar_robot.addWidget(QLabel("Robot : "))
        toolbar_robot.addAction(self.act_stop_robot)
        toolbar_robot.addAction(self.act_goto_parking)
        toolbar_robot.addAction(self.act_goto_zero)
        toolbar_robot.addAction(self.act_goto_selected)

        toolbar_fichier = QToolBar("Outils Fichier")
        toolbar_fichier.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar_fichier)
        toolbar_fichier.addAction(self.act_nouveau)
        toolbar_fichier.addAction(self.act_ouvrir)
        toolbar_fichier.addAction(self.act_enregistrer)

        toolbar_edition = QToolBar("Outils Édition")
        toolbar_edition.setIconSize(QSize(24, 24))
        toolbar_edition.setOrientation(Qt.Vertical)
        self.addToolBar(Qt.LeftToolBarArea,toolbar_edition) # S'ajoute à côté ou en dessous par défaut
        toolbar_edition.addAction(self.act_undo)

    def _create_central_widget(self):
        """Crée le widget central et son contenu."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        layout_principal = QVBoxLayout(central_widget)
        label_central = QLabel("Zone Principale", self)
        label_central.setAlignment(Qt.AlignCenter)
        font = label_central.font()
        font.setPointSize(18)
        label_central.setFont(font)
        layout_principal.addWidget(label_central)

    def _create_statusbar(self):
        """Configure la barre de statut."""
        self.statusBar().showMessage('Prêt')

    def _connect_signals(self):
        """Connecte les signaux des actions aux slots."""
        # Fichier
        self.act_nouveau.triggered.connect(lambda: self.simuler_action("Nouveau"))
        self.act_ouvrir.triggered.connect(lambda: self.simuler_action("Ouvrir"))
        self.act_enregistrer.triggered.connect(lambda: self.simuler_action("Enregistrer"))
        self.act_enregistrer_sous.triggered.connect(lambda: self.simuler_action("Enregistrer sous"))
        self.act_proprietes.triggered.connect(lambda: self.simuler_action("Propriétés"))
        self.act_quitter.triggered.connect(self.close)

        # Édition
        self.act_undo.triggered.connect(lambda: self.simuler_action("Annuler (Undo)"))
        self.act_redo.triggered.connect(lambda: self.simuler_action("Rétablir (Redo)"))

        # Outils
        self.act_measurement_settings.triggered.connect(lambda: self.simuler_action("Options Mesures"))
        self.act_telecommande.triggered.connect(lambda: self.simuler_action("Télécommande"))

        # Aide
        self.act_apropos.triggered.connect(self.afficher_apropos)

        # Séquence
        self.act_stop_sequence.triggered.connect(lambda: self.simuler_action("Arrêter Séquence"))
        self.act_start_sequence.triggered.connect(lambda: self.simuler_action("Démarrer Séquence"))
        self.act_measure_next_point.triggered.connect(lambda: self.simuler_action("Mesurer Prochain Point"))

        # Pulse
        self.act_show_pulse.triggered.connect(lambda: self.simuler_action("Afficher Pulse"))
        self.act_start_measurement.triggered.connect(lambda: self.simuler_action("Démarrer Mesure"))
        self.act_save_measurement.triggered.connect(lambda: self.simuler_action("Enregistrer Mesure"))

        # Robot
        self.act_stop_robot.triggered.connect(lambda: self.simuler_action("Arrêter Robot"))
        self.act_goto_parking.triggered.connect(lambda: self.simuler_action("Aller au Parking"))
        self.act_goto_zero.triggered.connect(lambda: self.simuler_action("Aller au Zéro"))
        self.act_goto_selected.triggered.connect(lambda: self.simuler_action("Aller à la Position Sélectionnée"))


    # --- Slots (inchangés) ---
    def simuler_action(self, nom_action):
        print(f"Action déclenchée : {nom_action}")
        self.statusBar().showMessage(f"Action : {nom_action}", 3000)

    def basculer_plein_ecran(self, checked):
        if checked: self.showFullScreen()
        else: self.showNormal()
        status = "Plein Écran Activé" if checked else "Plein Écran Désactivé"
        self.statusBar().showMessage(status, 3000)
        print(f"Action déclenchée : {status}")


    def afficher_apropos(self):
        print("Action déclenchée : À propos")
        QMessageBox.about(self, "À propos...", "Logiciel de pilotage du robot v0.1\nPour l'UMRAE.")

    def closeEvent(self, event):
         reponse = QMessageBox.question(self, 'Confirmation', "Quitter ?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
         if reponse == QMessageBox.Yes: event.accept()
         else: event.ignore()

# --- Point d'entrée (inchangé) ---
if __name__ == '__main__':
    if not ICONS_DIR.is_dir():
        print(f"Erreur Critique : Le dossier d'icônes '{ICONS_DIR}' est introuvable.")
        sys.exit(1)
    app = QApplication(sys.argv)
    fenetre = MainWindow()
    sys.exit(app.exec_())