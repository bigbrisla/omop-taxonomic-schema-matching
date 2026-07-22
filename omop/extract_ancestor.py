"""Estrazione vicinato CONCEPT_ANCESTOR in query separate e leggere.

Evita il fallimento "Resources exceeded (shuffle)" della versione monolitica:
ogni query e' un singolo JOIN di uguaglianza (hash join con build side piccolo),
nessun OR + CTE che materializza shuffle giganti.

Input:  omop/omop_patients.csv (gia' estratto)
Output: omop/concept_ancestor.csv, omop/concept_names.csv
"""
import os
import sys
import pandas as pd
from google.cloud import bigquery

DS = "bigquery-public-data.cms_synthetic_patient_data_omop"
OUT = os.path.dirname(os.path.abspath(__file__))
MAXLVL = 6  # bound per distanza-k (ancestors/descendants)

client = bigquery.Client()

df = pd.read_csv(os.path.join(OUT, "omop_patients.csv"))
cols = ["condition_1", "condition_2", "observation_1", "observation_2", "procedure_1", "procedure_2"]
S = set()
for c in cols:
    S.update(int(x) for x in df[c].dropna().unique())
S.discard(0)
S = sorted(S)
print(f"concept_id in S: {len(S)}")
S_arr = "[" + ",".join(map(str, S)) + "]"


def run(label, sql):
    dry = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
    print(f"  [{label}] stima scan: {dry.total_bytes_processed/1e6:.1f} MB ...", end=" ", flush=True)
    out = client.query(sql).to_dataframe()
    print(f"righe: {len(out)}")
    return out

# 1) Antenati di S (per padri e distanza-k verso l'alto)
anc = run("ancestors", f"""
SELECT ca.ancestor_concept_id, ca.descendant_concept_id,
       ca.min_levels_of_separation, ca.max_levels_of_separation
FROM `{DS}.concept_ancestor` ca
JOIN UNNEST({S_arr}) AS sid ON ca.descendant_concept_id = sid
WHERE ca.min_levels_of_separation BETWEEN 1 AND {MAXLVL}
""")

# 2) Discendenti di S (figli e distanza-k verso il basso)
desc = run("descendants", f"""
SELECT ca.ancestor_concept_id, ca.descendant_concept_id,
       ca.min_levels_of_separation, ca.max_levels_of_separation
FROM `{DS}.concept_ancestor` ca
JOIN UNNEST({S_arr}) AS sid ON ca.ancestor_concept_id = sid
WHERE ca.min_levels_of_separation BETWEEN 1 AND {MAXLVL}
""")

# 3) Fratelli: figli diretti (min_levels=1) dei padri diretti di S
parents = sorted(set(anc.loc[anc.min_levels_of_separation == 1, "ancestor_concept_id"].astype(int)))
print(f"padri diretti: {len(parents)}")
P_arr = "[" + ",".join(map(str, parents)) + "]"
sib = run("siblings", f"""
SELECT ca.ancestor_concept_id, ca.descendant_concept_id,
       ca.min_levels_of_separation, ca.max_levels_of_separation
FROM `{DS}.concept_ancestor` ca
JOIN UNNEST({P_arr}) AS pid ON ca.ancestor_concept_id = pid
WHERE ca.min_levels_of_separation = 1
""")

ca = pd.concat([anc, desc, sib], ignore_index=True).drop_duplicates(
    subset=["ancestor_concept_id", "descendant_concept_id"])
ca.to_csv(os.path.join(OUT, "concept_ancestor.csv"), index=False)
print(f"concept_ancestor totale (dedup): {len(ca)} righe -> concept_ancestor.csv")

# 4) Nomi dei concetti coinvolti
ids = sorted(set(ca.ancestor_concept_id).union(ca.descendant_concept_id).union(S))
print(f"concetti da nominare: {len(ids)}")
I_arr = "[" + ",".join(map(str, map(int, ids))) + "]"
cn = run("concept_names", f"""
SELECT c.concept_id, c.concept_name, c.domain_id, c.vocabulary_id,
       c.concept_class_id, c.standard_concept
FROM `{DS}.concept` c
JOIN UNNEST({I_arr}) AS cid ON c.concept_id = cid
""")
cn.to_csv(os.path.join(OUT, "concept_names.csv"), index=False)
print("FATTO.")
