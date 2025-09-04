# docs/conf.py

# -- Path setup --------------------------------------------------------------
# Cette section est cruciale. Elle indique à Sphinx où trouver le code source
# de ton application (le dossier 'src') pour qu'il puisse lire les docstrings.
import os
import sys
# On ajoute le chemin '../src' au PYTHONPATH.
# os.path.abspath('.') donne le chemin du dossier 'docs'.
# os.path.abspath('..') remonte d'un niveau (à la racine du projet).
# Donc, os.path.abspath('../src') pointe bien vers le dossier 'src'.
sys.path.insert(0, os.path.abspath('../src'))


# -- Project information -----------------------------------------------------
project = 'Robot Acoustic GUI'
copyright = '2025, Antoine Riaublanc'
author = 'Antoine Riaublanc'
release = '0.1.0'


# -- General configuration ---------------------------------------------------

# Ajoutez ici toutes les extensions Sphinx que vous souhaitez utiliser.
extensions = [
    'sphinx.ext.autodoc',            # Extension principale pour lire les docstrings.
    'sphinx.ext.viewcode',           # Ajoute un lien "Voir le code source" sur chaque page d'API.
    'sphinx.ext.napoleon',           # Permet de comprendre d'autres styles de docstrings (ex: Google style).
    'sphinx_autodoc_typehints',      # Affiche joliment les annotations de type (ex: -> bool).
    'sphinx.ext.todo',               # Permet d'utiliser des blocs ".. todo::" pour marquer des tâches.
]

# Les dossiers à ignorer lors de la recherche de fichiers sources.
exclude_patterns = []

# La langue de la documentation (pour les textes générés par Sphinx).
language = 'fr'


# -- Options for HTML output -------------------------------------------------

# Le thème HTML à utiliser. 'sphinx_rtd_theme' est moderne et très populaire.
html_theme = 'sphinx_rtd_theme'

# Les dossiers contenant des fichiers statiques (images, CSS personnalisé) qui
# seront copiés dans le dossier de sortie.
# Pour l'instant, nous n'en avons pas besoin, mais le dossier est là.
html_static_path = ['_static']

# Si True, les blocs ".. todo::" seront affichés dans la documentation.
todo_include_todos = True