import sys
import os
from pathlib import Path

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel,
                             QVBoxLayout, QAction, QToolBar, QStatusBar,
                             QMessageBox, QTextEdit) # Ajout QTextEdit pour un central widget plus utile
from PyQt5.QtGui import QIcon, QFont # Ajout QFont
from PyQt5.QtCore import Qt, QSize # Ajout QSize

# --- Déterminer le chemin de base du script ---
BASE_DIR = Path(__file__).resolve().parent
ICONS_DIR = BASE_DIR / 'icons'

# --- Fonction pour créer les QIcon avec gestion des états ---
def create_qicon(base_filename):
    """
    Crée un objet QIcon en utilisant les états normal, disabled et active
    si les fichiers correspondants existent dans le dossier icons.
    """
    normal_path = ICONS_DIR / base_filename
    # Construire les noms potentiels pour disabled/active
    # (Attention: Peut nécessiter ajustement si les noms ne suivent pas *exactement* ce pattern)
    if '.' in base_filename:
        name, ext = base_filename.rsplit('.', 1)
        disabled_filename = f"_disabled__{name}.{ext}"
        active_filename = f"_active__{name}.{ext}"
    else: # Au cas où il n'y aurait pas d'extension (peu probable pour images)
        disabled_filename = f"_disabled__{base_filename}"
        active_filename = f"_active__{base_filename}"

    disabled_path = ICONS_DIR / disabled_filename
    active_path = ICONS_DIR / active_filename

    icon = QIcon() # Crée une icône vide

    # État Normal (Mode=Normal, State=Off)
    if normal_path.is_file():
        icon.addFile(str(normal_path), QSize(), QIcon.Normal, QIcon.Off)
    else:
        print(f"Avertissement: Icône normale non trouvée : {normal_path}")
        # Fallback possible ici si nécessaire

    # État Désactivé (Mode=Disabled, State=Off)
    if disabled_path.is_file():
        icon.addFile(str(disabled_path), QSize(), QIcon.Disabled, QIcon.Off)
        # print(f"Debug: Ajout Disabled: {disabled_path}") # Pour débogage

    # État Actif (survol/focus) (Mode=Active, State=Off)
    if active_path.is_file():
        icon.addFile(str(active_path), QSize(), QIcon.Active, QIcon.Off)
        # print(f"Debug: Ajout Active: {active_path}") # Pour débogage
        # On pourrait aussi l'ajouter pour Selected si pertinent
        # icon.addFile(str(active_path), QSize(), QIcon.Selected, QIcon.Off)

    # Gérer le cas spécifique de Exit.gif vs exit.png (on priorise png ici)
    if base_filename == 'exit.png' and not normal_path.is_file():
         gif_path = ICONS_DIR / 'Exit.gif'
         if gif_path.is_file():
             icon.addFile(str(gif_path), QSize(), QIcon.Normal, QIcon.Off)
             print(f"Info: Utilisation de Exit.gif comme fallback pour exit.png")


    if icon.isNull() and not normal_path.is_file():
         print(f"Erreur: Aucune version de l'icône trouvée pour {base_filename}")


    return icon

# 1. Définir la classe de la fenêtre principale
class MaFenetrePrincipale(QMainWindow):

    def __init__(self):
        super().__init__()
        # Variable pour stocker l'état "modifié" (pour activer/désactiver Save)
        self.document_modifie = False
        self.initialiserUI()
        self.update_actions_state() # Mettre à jour état initial des actions


    def initialiserUI(self):
        # --- Configuration générale de la fenêtre ---
        self.setWindowTitle('Éditeur Basique PyQt5')
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(create_qicon('document.png')) # Icône de l'application

        # --- Création des Actions ---
        self.new_action = QAction(create_qicon('new.png'), '&Nouveau', self)
        self.new_action.setShortcut('Ctrl+N')
        self.new_action.setStatusTip("Créer un nouveau document")
        self.new_action.triggered.connect(self.action_nouveau)

        self.open_action = QAction(create_qicon('open.png'), '&Ouvrir...', self)
        self.open_action.setShortcut('Ctrl+O')
        self.open_action.setStatusTip("Ouvrir un document existant")
        self.open_action.triggered.connect(self.action_ouvrir)

        self.save_action = QAction(create_qicon('save.png'), '&Enregistrer', self)
        self.save_action.setShortcut('Ctrl+S')
        self.save_action.setStatusTip("Enregistrer le document actuel")
        self.save_action.triggered.connect(self.action_enregistrer)

        self.save_as_action = QAction(create_qicon('save_as.png'), 'Enregistrer &sous...', self)
        self.save_as_action.setStatusTip("Enregistrer le document actuel sous un nouveau nom")
        self.save_as_action.triggered.connect(self.action_enregistrer_sous)

        # On utilise 'exit.png' (la fonction create_qicon gère le fallback vers Exit.gif)
        self.quit_action = QAction(create_qicon('exit.png'), '&Quitter', self)
        self.quit_action.setShortcut('Ctrl+Q')
        self.quit_action.setStatusTip("Quitter l'application")
        self.quit_action.triggered.connect(self.close) # self.close est une méthode de QWidget

        self.undo_action = QAction(create_qicon('undo.png'), '&Annuler', self)
        self.undo_action.setShortcut('Ctrl+Z')
        self.undo_action.setStatusTip("Annuler la dernière action")
        # Connecté directement au slot undo du QTextEdit

        self.redo_action = QAction(create_qicon('redo.png'), '&Rétablir', self)
        self.redo_action.setShortcut('Ctrl+Y') # Ou Ctrl+Shift+Z
        self.redo_action.setStatusTip("Rétablir la dernière action annulée")
        # Connecté directement au slot redo du QTextEdit

        self.cut_action = QAction(create_qicon('cut.png'), 'Co&uper', self)
        self.cut_action.setShortcut('Ctrl+X')
        self.cut_action.setStatusTip("Couper la sélection vers le presse-papiers")
        # Connecté directement au slot cut du QTextEdit

        self.copy_action = QAction(create_qicon('copy.png'), '&Copier', self)
        self.copy_action.setShortcut('Ctrl+C')
        self.copy_action.setStatusTip("Copier la sélection vers le presse-papiers")
        # Connecté directement au slot copy du QTextEdit

        # Note: 'past.png' ou 'paste.png'? J'utilise 'paste.png'
        self.paste_action = QAction(create_qicon('paste.png'), 'Co&ller', self)
        self.paste_action.setShortcut('Ctrl+V')
        self.paste_action.setStatusTip("Coller le contenu du presse-papiers")
        # Connecté directement au slot paste du QTextEdit

        # On utilise 'about_(info).png'
        self.about_action = QAction(create_qicon('about_(info).png'), '&À Propos', self)
        self.about_action.setStatusTip("Afficher la boîte À Propos")
        self.about_action.triggered.connect(self.action_afficher_apropos)

        # On utilise 'help.png'
        self.help_action = QAction(create_qicon('help.png'), 'Aide &Contenu', self)
        self.help_action.setShortcut('F1')
        self.help_action.setStatusTip("Afficher l'aide")
        self.help_action.triggered.connect(self.action_afficher_aide)

        # --- Création de la MenuBar ---
        menu_bar = self.menuBar()

        fichier_menu = menu_bar.addMenu('&Fichier')
        fichier_menu.addAction(self.new_action)
        fichier_menu.addAction(self.open_action)
        fichier_menu.addAction(self.save_action)
        fichier_menu.addAction(self.save_as_action)
        fichier_menu.addSeparator()
        fichier_menu.addAction(self.quit_action)

        edition_menu = menu_bar.addMenu('&Édition')
        edition_menu.addAction(self.undo_action)
        edition_menu.addAction(self.redo_action)
        edition_menu.addSeparator()
        edition_menu.addAction(self.cut_action)
        edition_menu.addAction(self.copy_action)
        edition_menu.addAction(self.paste_action)

        aide_menu = menu_bar.addMenu('&Aide')
        aide_menu.addAction(self.help_action)
        aide_menu.addSeparator()
        aide_menu.addAction(self.about_action)

        # --- Création de la ToolBar ---
        toolbar = QToolBar("Barre d'outils Fichier")
        self.addToolBar(toolbar)
        toolbar.addAction(self.new_action)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)

        toolbar_edit = QToolBar("Barre d'outils Édition")
        self.addToolBar(toolbar_edit) # Ajoute une seconde toolbar
        toolbar_edit.addAction(self.cut_action)
        toolbar_edit.addAction(self.copy_action)
        toolbar_edit.addAction(self.paste_action)
        toolbar_edit.addSeparator()
        toolbar_edit.addAction(self.undo_action)
        toolbar_edit.addAction(self.redo_action)


        # --- Création du Central Widget ---
        # Utilisation d'un QTextEdit comme widget central simple
        self.text_edit = QTextEdit(self)
        self.text_edit.setFont(QFont("Monospace", 10)) # Police simple
        self.setCentralWidget(self.text_edit)

        # Connecter les signaux de QTextEdit aux actions standards et à la gestion de l'état modifié
        self.text_edit.undoAvailable.connect(self.undo_action.setEnabled)
        self.text_edit.redoAvailable.connect(self.redo_action.setEnabled)
        self.text_edit.copyAvailable.connect(self.cut_action.setEnabled)
        self.text_edit.copyAvailable.connect(self.copy_action.setEnabled)
        # Activer Coller si le presse-papier n'est pas vide (approximatif ici)
        self.paste_action.setEnabled(QApplication.clipboard().mimeData().hasText())
        QApplication.clipboard().dataChanged.connect(
            lambda: self.paste_action.setEnabled(QApplication.clipboard().mimeData().hasText())
        )

        # Détecter les modifications pour activer/désactiver "Enregistrer"
        self.text_edit.textChanged.connect(self.on_text_changed)

        # Connecter les actions d'édition directement aux slots de QTextEdit
        self.undo_action.triggered.connect(self.text_edit.undo)
        self.redo_action.triggered.connect(self.text_edit.redo)
        self.cut_action.triggered.connect(self.text_edit.cut)
        self.copy_action.triggered.connect(self.text_edit.copy)
        self.paste_action.triggered.connect(self.text_edit.paste)

        # --- Création de la StatusBar ---
        self.statusBar().showMessage('Prêt')

        # --- Afficher la fenêtre ---
        self.show()

    # --- Slots personnalisés ---
    def action_nouveau(self):
        print("Action: Nouveau")
        # Logique pour vérifier si le document actuel doit être sauvegardé
        self.text_edit.clear()
        self.document_modifie = False
        self.update_actions_state()
        self.statusBar().showMessage("Nouveau document créé", 2000)

    def action_ouvrir(self):
        print("Action: Ouvrir")
        # Logique pour ouvrir un fichier (QFileDialog.getOpenFileName)
        self.statusBar().showMessage("Fonction Ouvrir non implémentée", 2000)
        # Si chargement réussi:
        # self.document_modifie = False
        # self.update_actions_state()

    def action_enregistrer(self):
        print("Action: Enregistrer")
        # Logique pour enregistrer (vérifier si nom existe, sinon comme Enregistrer Sous)
        self.statusBar().showMessage("Document enregistré (simulé)", 2000)
        self.document_modifie = False
        self.update_actions_state()


    def action_enregistrer_sous(self):
        print("Action: Enregistrer sous")
        # Logique pour enregistrer sous (QFileDialog.getSaveFileName)
        self.statusBar().showMessage("Document enregistré sous... (simulé)", 2000)
        self.document_modifie = False
        self.update_actions_state()

    def action_afficher_apropos(self):
        QMessageBox.about(self,
                          "À Propos de Éditeur Basique",
                          "<b>Éditeur Basique v0.1</b><br>"
                          "Exemple d'application PyQt5<br>"
                          "Utilisant des icônes personnalisées.")

    def action_afficher_aide(self):
        print("Action: Afficher Aide")
        QMessageBox.information(self, "Aide", "Fonction d'aide non implémentée.")

    def on_text_changed(self):
        """Appelé quand le texte dans QTextEdit change."""
        if not self.document_modifie:
            self.document_modifie = True
            self.update_actions_state()

    def update_actions_state(self):
        """Met à jour l'état activé/désactivé des actions."""
        self.save_action.setEnabled(self.document_modifie)

        # Utiliser document().isUndoAvailable() et document().isRedoAvailable() à la place
        self.undo_action.setEnabled(self.text_edit.document().isUndoAvailable())
        self.redo_action.setEnabled(self.text_edit.document().isRedoAvailable())

        has_selection = self.text_edit.textCursor().hasSelection()
        self.cut_action.setEnabled(has_selection)
        self.copy_action.setEnabled(has_selection)

    # --- Gestion de la fermeture ---
    def closeEvent(self, event):
        """
        Surcharge de l'événement de fermeture pour demander à sauvegarder
        si le document a été modifié.
        """
        if self.document_modifie:
            reponse = QMessageBox.question(self, 'Quitter',
                                           "Le document a été modifié.\nVoulez-vous enregistrer les modifications ?",
                                           QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                           QMessageBox.Save) # Bouton par défaut

            if reponse == QMessageBox.Save:
                self.action_enregistrer() # Essayer de sauvegarder
                # Si la sauvegarde échoue (ex: cancel dans la dialog), on ne ferme pas
                if self.document_modifie: # Vérifier si la sauvegarde a réussi (flag remis à False)
                     event.ignore() # Empêche la fermeture
                else:
                     event.accept() # Accepte la fermeture
            elif reponse == QMessageBox.Discard:
                event.accept() # Accepte la fermeture sans sauvegarder
            else: # Cancel
                event.ignore() # Empêche la fermeture
        else:
            event.accept() # Accepte la fermeture normalement


# 2. Point d'entrée de l'application
if __name__ == '__main__':
    # Vérifier si le dossier d'icônes existe
    if not ICONS_DIR.is_dir():
        print(f"Erreur critique : Le dossier d'icônes '{ICONS_DIR}' est introuvable.")
        print("Assurez-vous que le dossier 'icons' existe au même niveau que le script.")
        sys.exit(1) # Quitte avec un code d'erreur

    app = QApplication(sys.argv)
    fenetre = MaFenetrePrincipale()
    sys.exit(app.exec_())