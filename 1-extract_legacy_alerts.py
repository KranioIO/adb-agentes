import requests
import json
import os
import configparser
import base64

# --- CONFIGURATION ---
PROFILE = "qa"  # On extrait du DEV pour aller vers QA
DOMAIN_FILTER = "@kranio.io"
OUTPUT_DIR = "resources/alerts"

def get_databricks_config(profile):
    config = configparser.ConfigParser()
    config.read(os.path.expanduser("~/.databrickscfg"))
    if profile not in config:
        raise ValueError(f"Profil {profile} non trouvé dans ~/.databrickscfg")
    host = config[profile].get('host', '').rstrip('/')
    token = config[profile].get('token') or config[profile].get('access_token')
    return host, token

def transform_to_sql_format(raw_json_str, alert_name):
    """
    Transforme le format 'Workspace' (evaluation/query_lines) 
    en format 'SQL API' (options/custom_sql).
    """
    try:
        raw_data = json.loads(raw_json_str)
        eval_data = raw_data.get("evaluation", {})
        
        # Mapping des opérateurs Workspace vers SQL Store
        op_mapping = {
            "EQUAL": "==",
            "GREATER_THAN": ">",
            "LESS_THAN": "<",
            "GREATER_THAN_OR_EQUAL": ">=",
            "LESS_THAN_OR_EQUAL": "<="
        }
        
        # On construit la structure que l'API SQL de destination comprendra
        clean_json = {
            "name": alert_name,
            "options": {
                "column": "count(*)", # Valeur par défaut pour les alertes basiques
                "op": op_mapping.get(eval_data.get("comparison_operator"), ">"),
                "value": eval_data.get("threshold", {}).get("value", "0"),
                "muted": False
            },
            # On stocke le SQL brut ici pour que le script de déploiement 
            # puisse créer la Query SQL associée en QA.
            "custom_sql": " ".join(raw_data.get("query_lines", []))
        }
        return clean_json
    except Exception as e:
        print(f"      [ERREUR TRANSFORMATION] {e}")
        return None

def extract_via_api():
    host, token = get_databricks_config(PROFILE)
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"--- Scan global et TRADUCTION des alertes sur {host} ---")

    users_url = f"{host}/api/2.0/workspace/list"
    res_users = requests.get(users_url, headers=headers, params={"path": "/Users"})
    
    if res_users.status_code != 200:
        print(f"Erreur accès /Users : {res_users.text}")
        return

    user_folders = res_users.json().get('objects', [])
    total_count = 0

    for folder in user_folders:
        user_path = folder.get('path')
        
        if DOMAIN_FILTER in user_path:
            user_name = os.path.basename(user_path).split('@')[0]
            res_items = requests.get(users_url, headers=headers, params={"path": user_path})
            
            if res_items.status_code != 200: continue
                
            items = res_items.json().get('objects', [])
            for item in items:
                if item.get('object_type') == "ALERT":
                    alert_path = item.get('path')
                    
                    export_url = f"{host}/api/2.0/workspace/export"
                    export_res = requests.get(export_url, headers=headers, params={"path": alert_path, "format": "SOURCE"})
                    
                    if export_res.status_code == 200:
                        content_base64 = export_res.json().get('content')
                        decoded_content = base64.b64decode(content_base64).decode('utf-8')
                        
                        # --- LA TRADUCTION SE FAIT ICI ---
                        clean_alert_name = os.path.basename(alert_path)
                        translated_data = transform_to_sql_format(decoded_content, clean_alert_name)
                        
                        if translated_data:
                            file_name = f"{user_name}_{clean_alert_name.replace(' ', '_')}.json"
                            local_path = os.path.join(OUTPUT_DIR, file_name)
                            
                            with open(local_path, "w", encoding='utf-8') as f:
                                json.dump(translated_data, f, indent=2)
                            
                            print(f"   [OK] Traduit et Exporté : {file_name}")
                            total_count += 1

    print(f"\n--- Terminé ! {total_count} alertes prêtes pour l'importation ---")

if __name__ == "__main__":
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    extract_via_api()