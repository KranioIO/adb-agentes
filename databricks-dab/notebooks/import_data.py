# Lecture du fichier depuis le Volume Unity Catalog
# Le chemin sera : /Volumes/<catalog>/<schema>/<volume_name>/data_source.csv

import os

# Ces variables seront passées par le Bundle ou configurées
catalog = dbutils.widgets.get("catalog")
schema = "default"
volume_name = "mon_volume_entree"

path = f"/Volumes/{catalog}/{schema}/{volume_name}/data_source.csv"

df = spark.read.format("csv").option("header", "true").load(path)

# Création de la table
table_name = f"{catalog}.{schema}.ma_table_scores"
df.write.mode("overwrite").saveAsTable(table_name)

print(f"Table {table_name} créée avec succès !")
