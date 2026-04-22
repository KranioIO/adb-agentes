import json
import os
import subprocess
import tempfile

# --- CONFIGURACIÓN ---
TARGET_QA = "qa"
ALERTS_DIR = "resources/alerts"
# Asegúrate de que este ID sea el correcto para tu entorno de QA
WAREHOUSE_ID_QA = "af6acdfdf7d45afd"

def get_qa_alert_id(display_name):
    """Busca si la alerta ya existe en QA por su nombre."""
    try:
        result = subprocess.run(
            ["databricks", "alerts-v2", "list-alerts", "--target", TARGET_QA, "-o", "json"],
            capture_output=True, text=True, check=True
        )
        alerts = json.loads(result.stdout)
        
        # La respuesta puede variar según la versión, manejamos ambos casos
        if isinstance(alerts, dict):
            alerts = alerts.get("alerts", [])
        
        for a in alerts:
            if a.get("display_name") == display_name:
                return a.get("id")
    except Exception as e:
        print(f"  ⚠️ Error buscando alertas en QA: {e}")
    return None

def deploy_alerts():
    if not os.path.exists(ALERTS_DIR):
        print("❌ No se encontró la carpeta de alertas.")
        return

    for file in os.listdir(ALERTS_DIR):
        if not file.endswith(".json"): continue
        
        with open(os.path.join(ALERTS_DIR, file), "r") as f:
            data = json.load(f)
            
        display_name = data.get("display_name")
        if not display_name:
            continue

        # 1. CAMBIO CLAVE: 'condition' ahora es 'evaluation' en alerts-v2
        evaluation_data = data.get("evaluation") or data.get("condition")
        
        # 2. CONSTRUCCIÓN DEL PAYLOAD
        # Solo enviamos campos que la API reconoce para evitar "unknown field"
        payload = {
            "display_name": display_name,
            "query_text": data.get("query_text"),
            "warehouse_id": WAREHOUSE_ID_QA,
            "evaluation": evaluation_data
        }

        # 3. LÓGICA DE SCHEDULE (Sólo si tiene un cron válido)
        schedule = data.get("schedule")
        has_valid_schedule = schedule and schedule.get("quartz_cron_schedule")
        
        if has_valid_schedule:
            payload["schedule"] = schedule
            mask_list = ["display_name", "query_text", "warehouse_id", "evaluation", "schedule"]
        else:
            mask_list = ["display_name", "query_text", "warehouse_id", "evaluation"]

        # 4. DETERMINAR SI ES CREATE O UPDATE
        qa_id = get_qa_alert_id(display_name)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
            json.dump(payload, tf)
            temp_path = tf.name

        try:
            if qa_id:
                print(f"🔄 Actualizando alerta en QA: '{display_name}' (ID: {qa_id})")
                
                # El update_mask es una cadena de campos separados por coma sin espacios
                update_mask = ",".join(mask_list)
                
                subprocess.run([
                    "databricks", "alerts-v2", "update-alert", 
                    qa_id, 
                    update_mask, 
                    "--json", f"@{temp_path}", 
                    "--target", TARGET_QA
                ], check=True)
            else:
                print(f"🆕 Creando nueva alerta en QA: '{display_name}'")
                subprocess.run([
                    "databricks", "alerts-v2", "create-alert", 
                    "--json", f"@{temp_path}", 
                    "--target", TARGET_QA
                ], check=True)
            
            print(f"✅ Éxito: {display_name}")

        except subprocess.CalledProcessError as e:
            print(f"❌ Error en la llamada CLI para {display_name}")
            # Útil para debug: ver qué respondió la CLI exactamente
            if e.stderr: print(f"Detalle error: {e.stderr}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    deploy_alerts()