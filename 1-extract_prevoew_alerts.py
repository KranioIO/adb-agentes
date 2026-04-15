import requests
import json
import os
import configparser
import base64

# --- CONFIGURACIÓN ---
PROFILE = "qa"  # Profil en ~/.databrickscfg
DOMAIN_FILTER = "@kranio.io"
OUTPUT_DIR = "resources/alerts/previews"

def get_databricks_config(profile):
    config = configparser.ConfigParser()
    config.read(os.path.expanduser("~/.databrickscfg"))
    if profile not in config:
        raise ValueError(f"Perfil {profile} no encontrado en ~/.databrickscfg")
    host = config[profile].get('host', '').rstrip('/')
    token = config[profile].get('token') or config[profile].get('access_token')
    return host, token

def save_json(data, name):
    """Guarda el JSON en la carpeta de salida."""
    file_name = f"{name.replace(' ', '_').lower()}.json"
    local_path = os.path.join(OUTPUT_DIR, file_name)
    with open(local_path, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"   [OK] Exportado: {file_name}")

def extract_sql_alerts_modern(host, headers):
    """
    Extrae alertas usando la API de SQL (Alertas modernas/Preview).
    """
    print(f"\n--- Escaneando ALERTAS MODERNAS (SQL API) ---")
    # Endpoint para alertas SQL (incluye las de Preview)
    url = f"{host}/api/2.0/sql/alerts"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        alerts = response.json()
        # Dependiendo de la versión, puede venir como lista o dict
        alert_list = alerts if isinstance(alerts, list) else alerts.get('results', [])
        
        for alert in alert_list:
            alert_id = alert.get('id')
            # Obtenemos el detalle completo de la alerta
            detail_res = requests.get(f"{url}/{alert_id}", headers=headers)
            if detail_res.status_code == 200:
                data = detail_res.json()
                # Limpieza básica para evitar conflictos de ID en el destino
                data.pop('id', None)
                data.pop('updated_at', None)
                data.pop('created_at', None)
                save_json(data, f"modern_{data.get('name')}")
    else:
        print(f"      [AVISO] No se pudo acceder a la API de SQL Alerts: {response.text}")

def extract_legacy_alerts(host, headers):
    """
    Extrae alertas antiguas (Legacy) desde las carpetas de /Users.
    """
    print(f"\n--- Escaneando ALERTAS LEGACY (Workspace API) ---")
    users_url = f"{host}/api/2.0/workspace/list"
    res_users = requests.get(users_url, headers=headers, params={"path": "/Users"})
    
    if res_users.status_code != 200: return

    for folder in res_users.json().get('objects', []):
        user_path = folder.get('path')
        if DOMAIN_FILTER in user_path:
            user_name = os.path.basename(user_path).split('@')[0]
            res_items = requests.get(users_url, headers=headers, params={"path": user_path})
            if res_items.status_code != 200: continue
                
            for item in res_items.json().get('objects', []):
                if item.get('object_type') == "ALERT":
                    path = item.get('path')
                    export_res = requests.get(f"{host}/api/2.0/workspace/export", 
                                            headers=headers, params={"path": path, "format": "SOURCE"})
                    
                    if export_res.status_code == 200:
                        content = base64.b64decode(export_res.json().get('content')).decode('utf-8')
                        try:
                            raw_data = json.loads(content)
                            # Reutilizamos tu lógica de transformación para que el loading.py las entienda
                            name = os.path.basename(path)
                            save_json(raw_data, f"legacy_{user_name}_{name}")
                        except: pass

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    host, token = get_databricks_config(PROFILE)
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Extraer las nuevas (Preview/SQL)
    extract_sql_alerts_modern(host, headers)
    
    # 2. Extraer las viejas (Legacy)
    extract_legacy_alerts(host, headers)
    
    print(f"\n--- Proceso de extracción finalizado en {OUTPUT_DIR} ---")

if __name__ == "__main__":
    main()