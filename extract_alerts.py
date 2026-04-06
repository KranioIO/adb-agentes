import requests
import json
import os
import configparser
import base64

# --- CONFIGURATION ---
PROFILE = "qa"
USER_PATH = "/Users/stephane@kranio.io"
OUTPUT_DIR = "resources/alerts"

def get_databricks_config(profile):
    config = configparser.ConfigParser()
    config.read(os.path.expanduser("~/.databrickscfg"))
    if profile not in config:
        raise ValueError(f"Profil {profile} non trouvé dans ~/.databrickscfg")
    return config[profile]['host'].rstrip('/'), config[profile]['token']

def extract_via_api():
    host, token = get_databricks_config(PROFILE)
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"--- Extraction via API REST ({host}) ---")

    # 1. Lister le contenu du dossier
    list_url = f"{host}/api/2.0/workspace/list"
    res = requests.get(list_url, headers=headers, params={"path": USER_PATH})
    
    if res.status_code != 200:
        print(f"Erreur lors du listage : {res.text}")
        return

    items = res.json().get('objects', [])
    count = 0

    for item in items:
        if item.get('object_type') == "ALERT":
            path = item.get('path')
            # 2. Exporter le contenu (format HTML/DBC/SOURCE)
            # Pour les alertes, on demande l'export format SOURCE
            export_url = f"{host}/api/2.0/workspace/export"
            export_res = requests.get(export_url, headers=headers, params={"path": path, "format": "SOURCE"})
            
            if export_res.status_code == 200:
                content_base64 = export_res.json().get('content')
                # Le contenu est encodé en base64
                decoded_content = base64.b64decode(content_base64).decode('utf-8')
                
                file_name = os.path.basename(path).replace(" ", "_")
                if not file_name.endswith(".json"): file_name += ".json"
                
                local_path = os.path.join(OUTPUT_DIR, file_name)
                with open(local_path, "w") as f:
                    f.write(decoded_content)
                
                print(f"[OK] Exporté : {file_name}")
                count += 1
            else:
                print(f"[ERREUR] Impossible d'exporter {path} : {export_res.text}")

    print(f"\nTerminé ! {count} alertes extraites dans {OUTPUT_DIR}")

if __name__ == "__main__":
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    try:
        extract_via_api()
    except Exception as e:
        print(f"Erreur fatale : {e}")