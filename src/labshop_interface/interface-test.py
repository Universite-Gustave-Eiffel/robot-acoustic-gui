import win32com.client
import sys
import os
import time # Utile pour les pauses pour laisser Pulse s'initialiser

# --- Configuration ---
# Le ProgID de l'application Pulse Labshop.
pulse_progid = 'Pulse.Labshop.Application'

# --- Script de test ---
pulse_app = None
current_project = None # Initialiser la référence du projet à None
config_org = None # Initialiser la référence de l'organisateur de configuration à None

try:
    print(f"Tentative de connexion ou de lancement de Pulse Labshop avec le ProgID : {pulse_progid}...")

    # Tenter de se connecter à une instance existante d'abord
    try:
        pulse_app = win32com.client.GetActiveObject(pulse_progid)
        print("Connecté à une instance existante de Pulse Labshop.")
    except Exception:
        # Si aucune instance n'est trouvée, lancer une nouvelle instance en utilisant EnsureDispatch.
        print("Aucune instance existante trouvée. Lancement d'une nouvelle instance...")
        pulse_app = win32com.client.gencache.EnsureDispatch(pulse_progid)
        print("Nouvelle instance de Pulse Labshop lancée et connectée.")

    print("-" * 20)
    print("Informations de l'objet Application Pulse :")

    # Obtenir la version de l'application
    try:
        version = pulse_app.Version
        print(f"Version de l'application : {version}")
    except Exception as e_version:
        print(f"Erreur lors de l'accès à la version : {e_version}", file=sys.stderr)

    # Rendre l'application visible si nécessaire
    try:
        is_visible = pulse_app.Visible
        print(f"L'application Pulse est actuellement visible : {is_visible}")

        if not is_visible:
            print("Rendre l'application Pulse visible...")
            time.sleep(1) # Pause pour laisser l'UI se charger
            pulse_app.Visible = True
            print("Application Pulse rendue visible.")
            time.sleep(1) # Pause supplémentaire après avoir rendu visible
        else:
            print("L'application Pulse était déjà visible.")
    except Exception as e_visible:
         print(f"Erreur lors de l'accès à la propriété 'Visible' : {e_visible}", file=sys.stderr)

    print("-" * 20)
    # --- Créer un nouveau projet ---
    # Votre test a confirmé que NewProject() et l'accès à Project fonctionnent avec une pause.
    print("Création d'un nouveau projet...")
    try:
        pulse_app.NewProject()
        print("Nouveau projet créé.")
        # Pause pour laisser l'application initialiser le nouveau projet et les organisateurs.
        time.sleep(3)

        # Accéder à l'objet Project
        print("\nAccès à l'objet Project...")
        current_project = pulse_app.Project

        if current_project is not None:
            print(f"Accès à l'objet Project actuel réussi.")
            # Accéder au nom du projet
            try:
                project_name = current_project.Name
                print(f"Nom du projet actuel : {project_name}")

                # --- Accéder et interagir avec l'Organisateur de Configuration ---
                # Vous avez vu que current_project.ConfigurationOrganiser renvoie un objet.
                # D'après le dump .tlb, ConfigurationOrganiser (Type 86) implémente IConfigurationSystem (Type 85).
                # IConfigurationSystem a une méthode DetectFrontend().
                print("\nAccès à l'Organisateur de Configuration...")
                try:
                    config_org = current_project.ConfigurationOrganiser
                    print(f"Accès à l'Organisateur de Configuration réussi : {config_org}")

                    print("Appel de la méthode DetectFrontend() sur l'Organisateur de Configuration...")
                    # Appel de la méthode DetectFrontend().
                    # D'après le fichier d'aide (page 33), cela "forces the system to detect the front-end hardware".
                    # La méthode ne semble pas prendre d'arguments basés sur le dump (Type 85).
                    config_org.DetectFrontend()
                    print("Appel de DetectFrontend() terminé.")
                    # Une pause peut être utile ici pour laisser la détection se terminer
                    time.sleep(5) # Ajustez cette pause si nécessaire en fonction du temps de détection réel

                except AttributeError:
                    print("La propriété 'ConfigurationOrganiser' ou la méthode 'DetectFrontend()' n'a pas été trouvée/accessible.")
                except Exception as e_config_org:
                    print(f"Erreur lors de l'accès/appel à l'Organisateur de Configuration : {e_config_org}", file=sys.stderr)

                # --- Vous pouvez ajouter d'autres interactions avec config_org ici ---
                # Ex: config_org.LoadConfiguration("C:\\chemin\\vers\\config.cfg")

            except Exception as e_project_details:
                print(f"Erreur lors de l'accès aux détails du projet : {e_project_details}", file=sys.stderr)

        else:
            print("La propriété 'Project' a renvoyé None (inattendu après NewProject()).")

    except Exception as e_project_creation:
         print(f"Erreur lors de la création ou de l'accès au projet : {e_project_creation}", file=sys.stderr)

    print("-" * 20)
    # --- Attendre l'utilisateur avant de terminer ---
    print("\nTests de communication étendus terminés.")
    print("Vérifiez la fenêtre de Pulse Labshop (un nouveau projet devrait être ouvert et une détection front-end lancée).")
    print("Appuyez sur Entrée dans cette console pour terminer le script Python.")
    input()

except Exception as e_general:
    print(f"\n--- ERREUR FATALE ---", file=sys.stderr)
    print(f"Une erreur générale est survenue : {e_general}", file=sys.stderr)
    print("Impossible de se connecter ou d'interagir avec Pulse Labshop au début du script.", file=sys.stderr)
    print("Vérifiez que le ProgID est correct et que Pulse Labshop est correctement installé.", file=sys.stderr)

finally:
    # Libérer les références aux objets COM.
    # Important pour éviter les fuites de mémoire et permettre à Pulse de s'arrêter proprement si nécessaire.
    if config_org is not None:
        config_org = None
        print("Référence Python à l'Organisateur de Configuration libérée.")

    if current_project is not None:
        current_project = None
        print("Référence Python à l'objet Project libérée.")

    if pulse_app is not None:
        # Ne pas appeler .Exit() ou .Quit() ici si vous voulez laisser l'application ouverte après le script.
        # Si vous voulez la fermer, ajoutez pulse_app.Exit() ou pulse_app.Quit() ici.
        # print("Tentative de fermer Pulse Labshop...")
        # try:
        #     pulse_app.Exit() # ou pulse_app.Quit()
        #     print("Pulse Labshop fermé.")
        # except Exception as quit_e:
        #      print(f"Erreur lors de la tentative de fermeture de Pulse Labshop : {quit_e}", file=sys.stderr)
        pulse_app = None
        print("Référence Python à l'objet Application libérée.")


print("Fin du script de test.")