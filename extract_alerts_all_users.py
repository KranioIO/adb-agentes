import requests
import json
import os
import configparser
import base64

# --- CONFIGURATION ---
PROFILE = "dev"  # Change en "dev" ou "qa" selon ton besoin
DOMAIN_FILTER = "@kranio.io"
OUTPUT_DIR = "resources/alerts"

def get_databricks_config(profile):
    config = configparser.ConfigParser()
    config.read(os.path.expanduser("~/.databrickscfg"))
    if profile not in config:
        raise ValueError(f"Profil {profile} non trouvé dans ~/.databrickscfg")
    
    # On gère le cas où la clé est 'token' ou 'access_token' (OAuth)
    host = config[profile].get('host', '').rstrip('/')
    token = config[profile].get('token') or config[profile].get('access_token')
    
    if not host or not token:
        raise ValueError(f"Host ou Token manquant pour le profil {profile}")
    
    return host, token

def extract_via_api():
    host, token = get_databricks_config(PROFILE)
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"--- Scan global des utilisateurs sur {host} ---")

    # 1. Lister tous les dossiers dans /Users
    users_url = f"{host}/api/2.0/workspace/list"
    res_users = requests.get(users_url, headers=headers, params={"path": "/Users"})
    
    if res_users.status_code != 200:
        print(f"Erreur accès /Users : {res_users.text}")
        return

    user_folders = res_users.json().get('objects', [])
    total_count = 0

    for folder in user_folders:
        user_path = folder.get('path')
        
        # Filtrer uniquement les utilisateurs de ton entreprise
        if DOMAIN_FILTER in user_path:
            user_name = os.path.basename(user_path).split('@')[0]
            print(f"\n--- Scan de l'utilisateur : {user_name} ---")
            
            # 2. Lister le contenu du dossier de CET utilisateur
            res_items = requests.get(users_url, headers=headers, params={"path": user_path})
            if res_items.status_code != 200:
                print(f"   [ERREUR] Impossible de lire {user_path}")
                continue
                
            items = res_items.json().get('objects', [])
            
            for item in items:
                if item.get('object_type') == "ALERT":
                    alert_path = item.get('path')
                    
                    # 3. Exporter l'alerte
                    export_url = f"{host}/api/2.0/workspace/export"
                    export_res = requests.get(export_url, headers=headers, params={"path": alert_path, "format": "SOURCE"})
                    
                    if export_res.status_code == 200:
                        content_base64 = export_res.json().get('content')
                        decoded_content = base64.b64decode(content_base64).decode('utf-8')
                        
                        # Nettoyage du nom pour le fichier local
                        alert_name = os.path.basename(alert_path).replace(" ", "_")
                        # On ajoute le nom de l'user pour éviter les doublons de fichiers
                        file_name = f"{user_name}_{alert_name}"
                        if not file_name.endswith(".json"): file_name += ".json"
                        
                        local_path = os.path.join(OUTPUT_DIR, file_name)
                        with open(local_path, "w") as f:
                            f.write(decoded_content)
                        
                        print(f"   [OK] Exporté : {file_name}")
                        total_count += 1
                    else:
                        print(f"   [ERREUR] Export échoué pour {alert_path}")

    print(f"\n--- Terminé ! {total_count} alertes extraites au total ---")

if __name__ == "__main__":
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    try:
        extract_via_api()
    except Exception as e:
        print(f"Erreur fatale : {e}")