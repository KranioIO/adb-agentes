import json
import os
import subprocess
import tempfile

# --- CONFIGURACIÓN ---
TARGET_QA = "dev"
queries_dir = "resources/queries"
alerts_dir = "resources/alerts"

id_mapping = {}

def get_existing_id(resource_type, name):
    """Busca un objeto por nombre con limpieza de strings."""
    # Intentamos el comando más genérico que suele funcionar
    cmd = ["databricks", "queries", "list", "--target", TARGET_QA, "-o", "json"]
    if resource_type == "alerts":
        # Probamos primero 'alerts list', si falla, el bloque except lo manejará
        cmd = ["databricks", "alerts", "list", "--target", TARGET_QA, "-o", "json"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Reintento con 'sql' prefix por si acaso
            cmd.insert(1, "sql")
            result = subprocess.run(cmd, capture_output=True, text=True)
        
        objects = json.loads(result.stdout)
        if isinstance(objects, dict):
            objects = objects.get("res") or objects.get("results") or []

        name_field = "display_name" if resource_type == "alerts" else "name"
        
        for obj in objects:
            existing_name = str(obj.get(name_field)).strip()
            # Comparamos ignorando mayúsculas y espacios
            if existing_name.lower() == name.strip().lower():
                return obj.get("id")
    except Exception:
        pass
    return None

def deploy_queries():
    print("🚀 Procesando Queries...")
    if not os.path.exists(queries_dir): return
    
    files = [f for f in os.listdir(queries_dir) if f.endswith(".json")]
    for file in files:
        with open(os.path.join(queries_dir, file), "r") as f:
            data = json.load(f)
            old_id = data.get("id")
            name = (data.get("name") or data.get("display_name") or "").strip()
            sql_text = data.get("query_text") or data.get("query")
            
            if not sql_text or not name or name == "None": continue

            existing_id = get_existing_id("queries", name)
            
            payload = {"query": {"display_name": name, "query_text": sql_text}}
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
                json.dump(payload, tf)
                temp_path = tf.name

            try:
                if existing_id:
                    print(f"  🔄 Actualizando: '{name}' (ID: {existing_id})")
                    subprocess.run(["databricks", "queries", "edit", existing_id, "--json", f"@{temp_path}", "--target", TARGET_QA], check=True, capture_output=True)
                    id_mapping[old_id] = existing_id
                else:
                    print(f"  🆕 Creando: '{name}' (No se encontró duplicado)")
                    res = subprocess.run(["databricks", "queries", "create", "--json", f"@{temp_path}", "--target", TARGET_QA], capture_output=True, text=True, check=True)
                    output = json.loads(res.stdout)
                    new_id = output.get("id") or output.get("query", {}).get("id")
                    id_mapping[old_id] = new_id
                print(f"  ✅ Map: {old_id} -> {id_mapping[old_id]}")
            except Exception as e:
                print(f"  ❌ Error: {name}")
            finally:
                if os.path.exists(temp_path): os.remove(temp_path)

def deploy_alerts():
    print("\n🚀 Procesando Alertas...")
    if not os.path.exists(alerts_dir): return
    
    files = [f for f in os.listdir(alerts_dir) if f.endswith(".json")]
    for file in files:
        with open(os.path.join(alerts_dir, file), "r") as f:
            data = json.load(f)
            old_query_id = data.get("query_id")
            name = (data.get("display_name") or "").strip()

            if not name or name == "None": continue

            new_query_id = id_mapping.get(old_query_id)
            if not new_query_id:
                print(f"  ⚠️ Alerta '{name}' saltada: Query madre no encontrada.")
                continue

            existing_id = get_existing_id("alerts", name)

            payload = {
                "alert": {
                    "display_name": name,
                    "query_id": new_query_id,
                    "condition": data.get("condition"),
                    "seconds_to_retrigger": data.get("seconds_to_retrigger", 0),
                    "notify_on_ok": data.get("notify_on_ok", False)
                }
            }

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
                json.dump(payload, tf)
                temp_path = tf.name

            try:
                if existing_id:
                    print(f"  🔄 Actualizando Alerta: '{name}'")
                    subprocess.run(["databricks", "alerts", "edit", existing_id, "--json", f"@{temp_path}", "--target", TARGET_QA], check=True, capture_output=True)
                else:
                    print(f"  🆕 Creando Alerta: '{name}'")
                    subprocess.run(["databricks", "alerts", "create", "--json", f"@{temp_path}", "--target", TARGET_QA], check=True, capture_output=True)
                print(f"  ✅ Éxito.")
            except Exception as e:
                print(f"  ❌ Error: {name}")
            finally:
                if os.path.exists(temp_path): os.remove(temp_path)

if __name__ == "__main__":
    deploy_queries()
    deploy_alerts()