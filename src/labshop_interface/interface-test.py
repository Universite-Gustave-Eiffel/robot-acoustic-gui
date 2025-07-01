import win32com.client
import sys
import os
import time

# --- Configuration ---
pulse_progid = 'Pulse.Labshop.Application'

# Chemin vers un fichier de configuration Pulse (.cfg) existant.
# REMPLACEZ CE CHEMIN par un chemin valide sur votre système.
# Cherchez dans les répertoires de projets prédéfinis de votre installation Pulse.
# Exemple: r'C:\Program Files (x86)\Bruel and Kjaer\PULSE\Projects\Smart Start\Smart Start_Config.cfg'
config_file_path = r'pulse_configurations/test-configuration.cfg' # <--- À REMPLACER !

# --- Script de test ---
pulse_app = None
current_project = None
config_org = None

try:
    print(f"Tentative de connexion ou de lancement de Pulse Labshop avec le ProgID : {pulse_progid}...")
    try:
        pulse_app = win32com.client.GetActiveObject(pulse_progid)
        print("Connecté à une instance existante de Pulse Labshop.")
    except Exception:
        print("Pas d'instance existante trouvée. Lancement d'une nouvelle instance...")
        pulse_app = win32com.client.gencache.EnsureDispatch(pulse_progid)
        print("Nouvelle instance de Pulse Labshop lancée et connectée.")

    print("-" * 20)
    print("Informations de l'objet Application Pulse :")
    try:
        version = pulse_app.Version
        print(f"Version de l'application : {version}")
    except Exception as e_version:
        print(f"Erreur lors de l'accès à la version : {e_version}", file=sys.stderr)

    try:
        is_visible = pulse_app.Visible
        print(f"L'application Pulse est actuellement visible : {is_visible}")
        if not is_visible:
            print("Rendre l'application Pulse visible...")
            time.sleep(1)
            pulse_app.Visible = True
            time.sleep(1)
        else:
            print("L'application Pulse était déjà visible.")
    except Exception as e_visible:
         print(f"Erreur lors de l'accès à la propriété 'Visible' : {e_visible}", file=sys.stderr)

    print("-" * 20)
    # Votre test a confirmé que NewProject() et l'accès à Project fonctionnent avec une pause.
    print("Création d'un nouveau projet...")
    try:
        pulse_app.NewProject()
        print("Nouveau projet créé.")
        time.sleep(3) # Pause pour initialisation

        print("\nAccès à l'objet Project...")
        current_project = pulse_app.Project

        if current_project is not None:
            print(f"Accès à l'objet Project actuel réussi.")
            try:
                project_name = current_project.Name
                print(f"Nom du projet actuel : {project_name}")

                # --- Accéder à l'Organisateur de Configuration et tester des méthodes ---
                print("\nAccès à l'Organisateur de Configuration...")
                try:
                    config_org = current_project.ConfigurationOrganiser
                    print(f"Accès à l'Organisateur de Configuration réussi.")

                    # Test: Appeler DetectFrontend() - Votre test a confirmé que cela fonctionne.
                    print("Test : Appel de la méthode DetectFrontend() sur l'Organisateur de Configuration...")
                    config_org.DetectFrontend()
                    print("Appel de DetectFrontend() terminé.")
                    time.sleep(5) # Pause pour laisser la détection se terminer

                    # Test: Appeler LoadConfiguration() - Nouvelle étape à vérifier
                    if os.path.exists(config_file_path):
                        print(f"\nTest : Chargement de la configuration depuis le fichier : {config_file_path}...")
                        try:
                            # LoadConfiguration est listée dans IConfigurationSystem (Type 85)
                            # Elle prend le chemin du fichier .cfg comme argument.
                            config_org.LoadConfiguration(config_file_path)
                            print("Chargement de la configuration terminé.")
                            time.sleep(2) # Pause pour mise à jour de l'UI

                        except Exception as e_load_config:
                             print(f"Erreur lors du test de chargement de la configuration : {e_load_config}", file=sys.stderr)
                             print("Vérifiez que le chemin du fichier .cfg est correct et que le fichier est valide pour cette version de Pulse.", file=sys.stderr)
                    else:
                        print(f"\nATTENTION : Le fichier de configuration spécifié n'existe pas : {config_file_path}", file=sys.stderr)
                        print("Impossible de tester LoadConfiguration(). Veuillez modifier le chemin dans le script.", file=sys.stderr)

                    # --- Ajoutez ici des tests pour d'autres méthodes de config_org si nécessaire ---
                    # Ex: config_org.AddSignal("Input 1", "NewSignalName")
                    # Ex: config_org.GetNoOfInputChannels()
                    # Référez-vous au dump IConfigurationSystem (Type 85) pour les noms.


                except AttributeError:
                    print("La propriété 'ConfigurationOrganiser' ou une méthode testée sur cet objet n'a pas été trouvée/accessible.")
                except Exception as e_config_org_access:
                    print(f"Erreur lors de l'accès/appel à l'Organisateur de Configuration : {e_config_org_access}", file=sys.stderr)


            except Exception as e_project_details:
                print(f"Erreur lors de l'accès aux détails du projet : {e_project_details}", file=sys.stderr)

        else:
            print("La propriété 'Project' a renvoyé None (inattendu après NewProject()).")

    except Exception as e_project_creation:
         print(f"Erreur lors de la création ou de l'accès au projet : {e_project_creation}", file=sys.stderr)

    print("-" * 20)
    print("\nTests de communication étendus terminés.")
    print("Vérifiez la fenêtre de Pulse Labshop.")
    print("Appuyez sur Entrée dans cette console pour terminer le script Python.")
    input()

except Exception as e_general:
    print(f"\n--- ERREUR FATALE ---", file=sys.stderr)
    print(f"Une erreur générale est survenue : {e_general}", file=sys.stderr)
    print("Impossible de se connecter ou d'interagir avec Pulse Labshop au début du script.", file=sys.stderr)
    print("Vérifiez que le ProgID est correct et que Pulse Labshop est correctement installé.", file=sys.stderr)

finally:
    if config_org is not None:
        config_org = None
        print("Référence Python à l'Organisateur de Configuration libérée.")

    if current_project is not None:
        current_project = None
        print("Référence Python à l'objet Project libérée.")

    if pulse_app is not None:
        # Pour fermer l'application à la fin, décommentez la section ci-dessous
        # print("Tentative de fermer Pulse Labshop...")
        # try:
        #     pulse_app.Exit() # ou pulse_app.Quit()
        #     print("Pulse Labshop fermé.")
        # except Exception as quit_e:
        #      print(f"Erreur lors de la tentative de fermeture de Pulse Labshop : {quit_e}", file=sys.stderr)
        pulse_app = None
        print("Référence Python à l'objet Application libérée.")

print("Fin du script de test.")