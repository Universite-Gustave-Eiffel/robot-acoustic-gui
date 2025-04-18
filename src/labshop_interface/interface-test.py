import win32com.client
import sys
import os
import time # Utile pour les pauses

# --- Configuration ---
# Le ProgID de l'application Pulse Labshop, confirmé par l'analyse du .tlb.
pulse_progid = 'Pulse.Labshop.Application'

# --- Script de test ---
pulse_app = None
try:
    print(f"Tentative de connexion ou de lancement de Pulse Labshop avec le ProgID : {pulse_progid}...")

    # Tenter de se connecter à une instance existante d'abord
    try:
        # GetActiveObject essaie de trouver une instance déjà lancée
        # Cela échouera avec une erreur spécifique si aucune instance n'est trouvée.
        # Si vous préférez *toujours* lancer une nouvelle instance, supprimez ce bloc try/except et utilisez seulement EnsureDispatch.
        pulse_app = win32com.client.GetActiveObject(pulse_progid)
        print("Connecté à une instance existante de Pulse Labshop.")
    except Exception as e_getactive:
        # win32com.client.pythoncom.com_error: (-2147221020, 'Opération non disponible', None, None)
        # C'est l'erreur typique si GetActiveObject ne trouve pas d'instance.
        print(f"Aucune instance existante trouvée ({e_getactive}). Lancement d'une nouvelle instance...")
        # EnsureDispatch lance une nouvelle instance si nécessaire et configure la liaison anticipée
        # Cela nécessite que le fichier Pulse.tlb soit accessible ou que ses infos soient dans le cache win32com
        pulse_app = win32com.client.gencache.EnsureDispatch(pulse_progid)
        print("Nouvelle instance de Pulse Labshop lancée et connectée.")


    print("-" * 20)
    print("Tests de l'objet Application Pulse :")

    # 1. Tenter d'obtenir le nom ou la version de l'application
    # Le dump .tlb liste 'Version' comme propriété et 'GetPulseVersionName' comme méthode sur IPulseLabShop2.
    # Il liste aussi 'Name' et '_Name' comme propriétés sur IPulseLabShop2.
    try:
        # Testons la propriété 'Version'
        version = pulse_app.Version # ou peut-être pulse_app.GetPulseVersionName()
        print(f"Version de l'application (via .Version ou .GetPulseVersionName()) : {version}")
    except AttributeError:
        print("La propriété 'Version' ou méthode 'GetPulseVersionName()' n'a pas été trouvée/accessible.")
    except Exception as e_version:
        print(f"Erreur lors de l'accès à la version : {e_version}", file=sys.stderr)

    # 2. Tenter de rendre l'application visible
    # La propriété 'Visible' est listée comme membre de IPulseLabShop2 dans le dump (Type 252).
    try:
        # Vérifier si l'application est déjà visible
        is_visible = pulse_app.Visible
        print(f"L'application Pulse est actuellement visible : {is_visible}")

        if not is_visible:
            print("Rendre l'application Pulse visible...")
            # Une petite pause peut aider si une nouvelle instance vient d'être lancée,
            # car l'interface utilisateur peut prendre un moment à se charger.
            time.sleep(1)
            pulse_app.Visible = True
            print("Application Pulse rendue visible.")
        else:
            print("L'application Pulse était déjà visible.")
    except AttributeError:
        print("La propriété 'Visible' n'a pas été trouvée ou n'est pas accessible sur l'objet application.")
    except Exception as e_visible:
         print(f"Erreur lors de l'accès à la propriété 'Visible' : {e_visible}", file=sys.stderr)


    # 3. Tenter d'accéder à l'objet Projet (s'il y a un projet ouvert)
    # La propriété 'Project' est listée sur IPulseLabShop2 (Type 252).
    try:
        # Cette propriété renvoie l'objet Project (instance de IProject2) ou None si aucun projet n'est ouvert
        current_project = pulse_app.Project
        if current_project is not None:
            print(f"Accès à l'objet Project actuel réussi.")
            # Vous pouvez maintenant interagir avec l'objet projet, par exemple obtenir son nom
            try:
                project_name = current_project.Name # 'Name' est une propriété de IProject2 (Type 251)
                print(f"Nom du projet actuel : {project_name}")
            except AttributeError:
                 print("La propriété 'Name' n'a pas été trouvée ou n'est pas accessible sur l'objet project.")
            except Exception as e_project_name:
                print(f"Erreur lors de l'accès au nom du projet : {e_project_name}", file=sys.stderr)
            # Libérer la référence à l'objet projet quand vous n'en avez plus besoin
            current_project = None
        else:
            print("Aucun projet Pulse n'est actuellement ouvert.")
    except AttributeError:
        print("La propriété 'Project' n'a pas été trouvée ou n'est pas accessible sur l'objet application.")
    except Exception as e_project:
         print(f"Erreur lors de l'accès à la propriété 'Project' : {e_project}", file=sys.stderr)


    print("-" * 20)
    # --- Attendre l'utilisateur avant de terminer ---
    print("\nTests de communication de base terminés.")
    print("Vérifiez la fenêtre de Pulse Labshop.")
    print("Appuyez sur Entrée dans cette console pour terminer le script Python.")
    input() # Attendre que l'utilisateur appuie sur Entrée

except Exception as e_general:
    # Cette erreur générale attrape les problèmes *avant* ou *pendant* la connexion/instanciation
    print(f"\n--- ERREUR FATALE ---", file=sys.stderr)
    print(f"Une erreur générale est survenue : {e_general}", file=sys.stderr)
    print("Impossible de se connecter ou d'interagir avec Pulse Labshop au début du script.", file=sys.stderr)
    print("\nCauses possibles :", file=sys.stderr)
    print(f"- Le ProgID '{pulse_progid}' est incorrect ou Pulse Labshop n'est pas correctement enregistré.", file=sys.stderr)
    print("- L'application Pulse Labshop n'est peut-être pas installée.", file=sys.stderr)
    print("- L'utilisateur n'a peut-être pas les permissions nécessaires pour l'interaction COM.", file=sys.stderr)
    print("- Un problème inattendu avec le système COM.", file=sys.stderr)


finally:
    # Libérer la référence à l'objet COM.
    # Il est généralement bon de le faire explicitement à la fin du script.
    # Si vous souhaitez que le script ferme l'application Pulse Labshop à la fin,
    # vous devriez décommenter la partie ci-dessous et vous assurer que c'est le comportement souhaité.
    # (Utiliser Exit() ou Quit() - Quit() est plus courant pour fermer les applications COM,
    # mais le dump liste Exit() sur IPulseLabShop2, donc essayons Exit() si vous voulez fermer).
    #
    # print("\nTentative de fermer Pulse Labshop...")
    # try:
    #     if pulse_app is not None:
    #         # Vérifiez le dump ou l'explorateur pour la méthode de fermeture correcte (Exit/Quit)
    #         if hasattr(pulse_app, 'Exit'):
    #             pulse_app.Exit()
    #             print("Pulse Labshop fermé avec succès (via Exit()).")
    #         elif hasattr(pulse_app, 'Quit'): # Moins probable basé sur le dump IPulseLabShop2
    #              pulse_app.Quit()
    #              print("Pulse Labshop fermé avec succès (via Quit()).")
    #         else:
    #              print("Aucune méthode de fermeture 'Exit' ou 'Quit' trouvée sur l'objet application.")
    #     else:
    #         print("Aucune instance Pulse Labshop à fermer.")
    # except Exception as quit_e:
    #      print(f"Erreur lors de la tentative de fermeture de Pulse Labshop : {quit_e}", file=sys.stderr)

    # Libérer la référence Python (important même si l'application n'est pas fermée)
    if pulse_app is not None:
        # Décrémente le compteur de références de l'objet COM
        pulse_app = None
        print("\nRéférence Python à l'objet Pulse libérée.")

print("Fin du script de test.")