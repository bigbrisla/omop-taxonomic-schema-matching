"""Estrazione mirata da BigQuery (CMS synthetic OMOP).

Produce, in cartella di output:
  - omop_patients.csv         : tabella denormalizzata pazienti (con header)
  - omop_patients_data.csv    : stessi dati SENZA header (input fabricator)
  - omop_patients_schema.csv  : schema "colonna,tipo" (input fabricator)
  - concept_ancestor.csv      : vicinato gerarchico dei concept_id presenti
  - concept_names.csv         : concept_id -> concept_name/domain per leggibilita'

Usa l'autenticazione gcloud ADC esistente. Le query sono su dataset pubblico
(bigquery-public-data), costo ~0 (pochi MB, free tier 1TB/mese).
"""
import os
import sys

import pandas as pd
from google.cloud import bigquery

DS = "bigquery-public-data.cms_synthetic_patient_data_omop"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
N_PATIENTS = int(sys.argv[2]) if len(sys.argv) > 2 else 2000

client = bigquery.Client()

# 1) Tabella pazienti denormalizzata (fino a 2 concetti per dominio + demografici)
patients_sql = f"""
WITH
  cond AS (
    SELECT person_id, ARRAY_AGG(DISTINCT condition_concept_id IGNORE NULLS LIMIT 2) AS v
    FROM `{DS}.condition_occurrence` WHERE condition_concept_id > 0 GROUP BY person_id
  ),
  proc AS (
    SELECT person_id, ARRAY_AGG(DISTINCT procedure_concept_id IGNORE NULLS LIMIT 2) AS v
    FROM `{DS}.procedure_occurrence` WHERE procedure_concept_id > 0 GROUP BY person_id
  ),
  obs AS (
    SELECT person_id, ARRAY_AGG(DISTINCT observation_concept_id IGNORE NULLS LIMIT 2) AS v
    FROM `{DS}.observation` WHERE observation_concept_id > 0 GROUP BY person_id
  )
SELECT
  p.person_id,
  p.gender_concept_id,
  p.race_concept_id,
  p.year_of_birth,
  cond.v[SAFE_OFFSET(0)] AS condition_1,
  cond.v[SAFE_OFFSET(1)] AS condition_2,
  obs.v[SAFE_OFFSET(0)]  AS observation_1,
  obs.v[SAFE_OFFSET(1)]  AS observation_2,
  proc.v[SAFE_OFFSET(0)] AS procedure_1,
  proc.v[SAFE_OFFSET(1)] AS procedure_2
FROM `{DS}.person` p
JOIN cond ON cond.person_id = p.person_id
JOIN proc ON proc.person_id = p.person_id
JOIN obs  ON obs.person_id  = p.person_id
WHERE ARRAY_LENGTH(cond.v)=2 AND ARRAY_LENGTH(proc.v)=2 AND ARRAY_LENGTH(obs.v)=2
LIMIT {N_PATIENTS}
"""
print("Estrazione pazienti...")
df = client.query(patients_sql).to_dataframe()
print(f"  pazienti: {len(df)}  colonne: {list(df.columns)}")
os.makedirs(OUT, exist_ok=True)
df.to_csv(os.path.join(OUT, "omop_patients.csv"), index=False)
# formato fabricator: dati senza header + schema colonna,tipo
df.to_csv(os.path.join(OUT, "omop_patients_data.csv"), header=False, index=False)
types = {c: ("int" if pd.api.types.is_integer_dtype(df[c]) else
             ("float" if pd.api.types.is_float_dtype(df[c]) else "str"))
         for c in df.columns}
with open(os.path.join(OUT, "omop_patients_schema.csv"), "w") as f:
    for c in df.columns:
        f.write(f"{c},{types[c]}\n")

# 2) concept_id clinici distinti
clinical_cols = ["condition_1", "condition_2", "observation_1", "observation_2",
                 "procedure_1", "procedure_2"]
concepts = set()
for c in clinical_cols:
    concepts.update(int(x) for x in df[c].dropna().unique())
concepts.discard(0)
print(f"  concept_id clinici distinti: {len(concepts)}")
concept_list = ",".join(str(c) for c in sorted(concepts))

# 3) Vicinato gerarchico da CONCEPT_ANCESTOR:
#    a) antenati dei nostri concetti (per padri e distanza-k verso l'alto)
#    b) discendenti dei nostri concetti (figli, distanza-k verso il basso)
#    c) figli diretti dei padri = concetti stessi + fratelli
ca_sql = f"""
WITH S AS (SELECT concept_id FROM UNNEST([{concept_list}]) AS concept_id),
parents AS (
  SELECT DISTINCT ca.ancestor_concept_id AS pid
  FROM `{DS}.concept_ancestor` ca JOIN S ON ca.descendant_concept_id = S.concept_id
  WHERE ca.min_levels_of_separation = 1
)
SELECT DISTINCT ancestor_concept_id, descendant_concept_id,
       min_levels_of_separation, max_levels_of_separation
FROM `{DS}.concept_ancestor` ca
WHERE ca.descendant_concept_id IN (SELECT concept_id FROM S)      -- antenati di S
   OR ca.ancestor_concept_id   IN (SELECT concept_id FROM S)      -- discendenti di S
   OR (ca.ancestor_concept_id IN (SELECT pid FROM parents)        -- figli dei padri
       AND ca.min_levels_of_separation = 1)
"""
print("Estrazione concept_ancestor (vicinato)...")
ca = client.query(ca_sql).to_dataframe()
ca.to_csv(os.path.join(OUT, "concept_ancestor.csv"), index=False)
print(f"  righe concept_ancestor: {len(ca)}")

# 4) Nomi dei concetti coinvolti (per leggibilita')
all_ids = set(ca["ancestor_concept_id"]).union(ca["descendant_concept_id"]).union(concepts)
ids_sql = ",".join(str(int(x)) for x in sorted(all_ids))
cn_sql = f"""
SELECT concept_id, concept_name, domain_id, vocabulary_id, concept_class_id, standard_concept
FROM `{DS}.concept`
WHERE concept_id IN ({ids_sql})
"""
print("Estrazione nomi concetti...")
cn = client.query(cn_sql).to_dataframe()
cn.to_csv(os.path.join(OUT, "concept_names.csv"), index=False)
print(f"  concetti con nome: {len(cn)}")
print("FATTO. Output in:", OUT)
