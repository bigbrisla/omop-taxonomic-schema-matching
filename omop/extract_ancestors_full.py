"""Estrae gli antenati COMPLETI (tutti i livelli, senza cap) da CONCEPT_ANCESTOR,
per costruire T(c) = insieme dei subsumers usato nella similarita' semantica di
Sanchez/Tomisani.

Un'unica query: gli id viaggiano come ArrayQueryParameter (fuori dal testo SQL),
quindi un solo scan della tabella (~2.8 GB, free tier 1 TB/mese).
"""
import os
import pandas as pd
from google.cloud import bigquery

DS = "bigquery-public-data.cms_synthetic_patient_data_omop"
OUT = os.path.dirname(os.path.abspath(__file__))
client = bigquery.Client()

# concetti che possono comparire come valore (originali + vicini) = tutti gli id
# gia' presenti nel nostro concept_ancestor.csv, piu' i concept clinici dei pazienti.
ca_old = pd.read_csv(os.path.join(OUT, "concept_ancestor.csv"))
ids = set(ca_old.ancestor_concept_id).union(ca_old.descendant_concept_id)
pat = pd.read_csv(os.path.join(OUT, "omop_patients.csv"))
for c in ["condition_1", "condition_2", "observation_1", "observation_2", "procedure_1", "procedure_2"]:
    ids.update(int(x) for x in pat[c].dropna().unique())
ids.discard(0)
ids = sorted(int(x) for x in ids)
print(f"concetti per cui estraggo gli antenati completi: {len(ids)}")

sql = f"""
SELECT ancestor_concept_id, descendant_concept_id, min_levels_of_separation
FROM `{DS}.concept_ancestor`
WHERE descendant_concept_id IN UNNEST(@ids)
"""
cfg = bigquery.QueryJobConfig(
    query_parameters=[bigquery.ArrayQueryParameter("ids", "INT64", ids)])
job = client.query(sql, job_config=cfg)
df = job.result().to_dataframe()
print(f"righe antenati (tutti i livelli): {len(df)}  |  livello max = {df.min_levels_of_separation.max()}")
df.to_csv(os.path.join(OUT, "concept_ancestor_full.csv"), index=False)
print("salvato concept_ancestor_full.csv")
