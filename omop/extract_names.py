"""Estrae i concept_name per gli id presenti in concept_ancestor.csv.

Usa ArrayQueryParameter (gli id viaggiano fuori dal testo SQL) a batch, per
evitare il limite di 1MB di lunghezza della query.
"""
import os
import pandas as pd
from google.cloud import bigquery

DS = "bigquery-public-data.cms_synthetic_patient_data_omop"
OUT = os.path.dirname(os.path.abspath(__file__))
BATCH = 20000

client = bigquery.Client()
ca = pd.read_csv(os.path.join(OUT, "concept_ancestor.csv"))
ids = sorted(set(ca.ancestor_concept_id).union(ca.descendant_concept_id))
print(f"id da nominare: {len(ids)}")

sql = f"""
SELECT c.concept_id, c.concept_name, c.domain_id, c.vocabulary_id,
       c.concept_class_id, c.standard_concept
FROM `{DS}.concept` c
JOIN UNNEST(@ids) AS cid ON c.concept_id = cid
"""
frames = []
for i in range(0, len(ids), BATCH):
    chunk = [int(x) for x in ids[i:i + BATCH]]
    cfg = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("ids", "INT64", chunk)])
    frames.append(client.query(sql, job_config=cfg).to_dataframe())
    print(f"  batch {i//BATCH + 1}: {len(frames[-1])} righe")

cn = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["concept_id"])
cn.to_csv(os.path.join(OUT, "concept_names.csv"), index=False)
print(f"concept_names.csv: {len(cn)} concetti. FATTO.")
