# Guide du Développeur

Ce document décrit l'architecture technique du logiciel de pilotage du robot acoustique. Il a pour objectif de faciliter la prise en main du code source pour sa maintenance et son évolution.

## 1. Architecture Logicielle

Le logiciel est fondé sur une architecture modulaire visant à découpler les différentes responsabilités : l'interface utilisateur (GUI), la logique de contrôle principale, la gestion des séquences et les interfaces matérielles.

Le flux d'interaction est orchestré par le `MainController`, qui utilise le système de signaux et slots de Qt pour une communication asynchrone entre les composants, notamment pour ne pas figer l'interface durant les opérations matérielles.

### Décomposition des modules (`src/`)

-   **`main_controller.py`** : Le contrôleur principal. Il centralise la logique applicative et orchestre les interactions entre la GUI et les modules back-end.
-   **`gui/`** : L'interface utilisateur, développée avec PySide6. Ce module est responsable de la présentation des données et de la capture des interactions utilisateur, qui sont ensuite transmises au `MainController` via des signaux Qt.
-   **`sequence_manager/`** : Gère l'exécution des séquences de mesure automatisées. Sa logique est implémentée sous la forme d'une Machine à États Finis (FSM) où chaque état (`states.py`) représente une étape du processus (déplacement, stabilisation, mesure, etc.). Le séquenceur s'exécute dans un thread dédié.
-   **`controller_interface/`** : Gère la communication série (RS-232) avec le contrôleur robot Galil.
    -   `RobotController` encapsule la logique de haut niveau, notamment la cinématique inverse pour la conversion des coordonnées "capsule" en consignes moteur.
-   **`labshop_interface/`** : Gère l'interfaçage avec PULSE LabShop via l'API COM de Windows. Ce module pilote l'ouverture des projets, le déclenchement des mesures et la sauvegarde des données.
-   **`data_manager.py`** : Définit la structure des points de mesure et gère leur sérialisation/désérialisation depuis/vers des fichiers (CSV, texte).

## 2. Environnement de Développement

### Prérequis
-   **Python 3.12** ou supérieur (le projet a été développé et testé avec cette version).

### Instructions
1.  **Cloner le dépôt :**
    ```bash
    git clone [URL_DU_DEPOT_GIT_DU_PROJET]
    cd universite-gustave-eiffel-robot-acoustic-gui
    ```

2.  **Créer et activer un environnement virtuel :**
    ```bash
    python -m venv .venv
    # Sur Windows (PowerShell)
    .venv\Scripts\Activate.ps1
    ```

3.  **Installer les dépendances :**
    Les dépendances du projet, y compris celles pour le développement, sont définies dans `pyproject.toml`.
    ```bash
    pip install -e .[dev]
    ```
    Cette commande utilise le `pyproject.toml` pour une installation en mode "éditable", ce qui permet de tester les modifications du code sans réinstallation.

4.  **Lancer l'application :**
    ```bash
    python launcher.py
    ```

## 3. Dépendances et Packaging

Le projet utilise `setuptools` avec un fichier `pyproject.toml` pour la gestion des métadonnées, des dépendances et de l'installation.

-   **Dépendances de production :** Elles sont listées sous la clé `[project.dependencies]`.
-   **Dépendances de développement :** Elles sont listées sous la clé `[project.optional-dependencies.dev]`.

---