"""Completa l'estrazione universale: antenati completi + nomi, IN BATCH.
(La versione monolitica falliva con 413 perché V è troppo grande per un unico
parametro array; qui si spezza in batch da 20k id.)
"""
import os
import pandas as pd
from google.cloud import bigquery

DS = "bigquery-public-data.cms_synthetic_patient_data_omop"
OUT = os.path.dirname(os.path.abspath(__file__))
BATCH = 20000
client = bigquery.Client()

nb = pd.read_csv(os.path.join(OUT, "concept_ancestor_universal.csv"))
uni = pd.read_csv(os.path.join(OUT, "omop_universal.csv"))
S = set()
for c in ["condition_concept_id", "procedure_concept_id", "drug_concept_id", "observation_concept_id"]:
    S.update(int(x) for x in uni[c].dropna().unique())
V = sorted(int(x) for x in (S | set(nb.ancestor_concept_id) | set(nb.descendant_concept_id)) if x != 0)
print(f"|V| (concetti per cui servono gli antenati completi): {len(V)}")


def batched(sql, ids, name="ids"):
    frames = []
    for i in range(0, len(ids), BATCH):
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ArrayQueryParameter(name, "INT64", ids[i:i+BATCH])])
        frames.append(client.query(sql, job_config=cfg).to_dataframe())
        print(f"  batch {i//BATCH+1}/{-(-len(ids)//BATCH)}: {len(frames[-1])} righe", flush=True)
    return pd.concat(frames, ignore_index=True)


print("antenati completi (batch) ...", flush=True)
full = batched(f"""SELECT ancestor_concept_id, descendant_concept_id, min_levels_of_separation
                  FROM `{DS}.concept_ancestor` WHERE descendant_concept_id IN UNNEST(@ids)""", V)
full = full.drop_duplicates(subset=["ancestor_concept_id", "descendant_concept_id"])
full.to_csv(os.path.join(OUT, "concept_ancestor_universal_full.csv"), index=False)
print(f"antenati completi: {len(full)} righe, liv max {full.min_levels_of_separation.max()}")

print("nomi (batch) ...", flush=True)
ids = sorted(set(full.ancestor_concept_id).union(full.descendant_concept_id).union(V))
cn = batched(f"""SELECT concept_id, concept_name, domain_id, vocabulary_id, concept_class_id, standard_concept
                FROM `{DS}.concept` WHERE concept_id IN UNNEST(@ids)""", ids)
cn = cn.drop_duplicates(subset=["concept_id"])
cn.to_csv(os.path.join(OUT, "concept_names_universal.csv"), index=False)
print(f"nomi: {len(cn)} concetti. FATTO.")
