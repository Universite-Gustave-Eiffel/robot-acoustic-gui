Guide du Développeur
====================

Ce document décrit l'architecture technique du logiciel de pilotage du robot acoustique. Il a pour objectif de faciliter la prise en main du code source pour sa maintenance et son évolution.

1. Architecture Logicielle
--------------------------

Le logiciel est fondé sur une architecture modulaire visant à découpler les différentes responsabilités : l'interface utilisateur (GUI), la logique de contrôle principale, la gestion des séquences et les interfaces matérielles.

Le flux d'interaction est orchestré par le ``MainController``, qui utilise le système de signaux et slots de Qt pour une communication asynchrone entre les composants, notamment pour ne pas figer l'interface durant les opérations matérielles.

**Décomposition des modules (``src/``)**

- **``main_controller.py``** : Le contrôleur principal. Il centralise la logique applicative et orchestre les interactions entre la GUI et les modules back-end.
- **``gui/``** : L'interface utilisateur, développée avec PySide6. Ce module est responsable de la présentation des données et de la capture des interactions utilisateur.
- **``sequence_manager/``** : Gère l'exécution des séquences de mesure automatisées via une Machine à États Finis (FSM).
- **``controller_interface/``** : Gère la communication série (RS-22) avec le contrôleur robot Galil et encapsule la logique de cinématique.
- **``labshop_interface/``** : Gère l'interfaçage avec PULSE LabShop via l'API COM de Windows.
- **``data_manager.py``** : Définit la structure des points de mesure et gère leur sérialisation.

2. Environnement de Développement
---------------------------------

**Prérequis**

- **Python 3.12** ou supérieur.

**Instructions**

1. **Cloner le dépôt :**

   .. code-block:: bash

      git clone [URL_DU_DEPOT_GIT_DU_PROJET]
      cd universite-gustave-eiffel-robot-acoustic-gui

2. **Créer et activer un environnement virtuel :**

   .. code-block:: bash

      python -m venv .venv
      # Sur Windows (PowerShell)
      .venv\Scripts\Activate.ps1

3. **Installer les dépendances :**

   .. code-block:: bash

      pip install -e .[dev]

4. **Lancer l'application :**

   .. code-block:: bash

      python launcher.py