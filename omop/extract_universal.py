"""Costruisce la RELAZIONE UNIVERSALE OMOP per lo schema matching (indicazione prof):
join su person_id di piu' domini, UN concetto per dominio per paziente (il PRIMO
per data). Colonne concettuali di domini DISTINTI (condition/procedure/drug/observation)
-> niente quasi-duplicati _1/_2.
"""
import os
import sys
import pandas as pd
from google.cloud import bigquery

DS = "bigquery-public-data.cms_synthetic_patient_data_omop"
OUT = os.path.dirname(os.path.abspath(__file__))
N = 5000
client = bigquery.Client()

SQL = f"""
WITH
cond AS (
  SELECT person_id,
    ARRAY_AGG(condition_concept_id ORDER BY condition_start_date, condition_concept_id LIMIT 1)[OFFSET(0)] AS condition_concept_id
  FROM `{DS}.condition_occurrence`
  WHERE condition_concept_id IS NOT NULL AND condition_concept_id != 0
  GROUP BY person_id
),
proc AS (
  SELECT person_id,
    ARRAY_AGG(procedure_concept_id ORDER BY procedure_datetime, procedure_concept_id LIMIT 1)[OFFSET(0)] AS procedure_concept_id
  FROM `{DS}.procedure_occurrence`
  WHERE procedure_concept_id IS NOT NULL AND procedure_concept_id != 0
  GROUP BY person_id
),
drug AS (
  SELECT person_id,
    ARRAY_AGG(drug_concept_id ORDER BY drug_exposure_start_date, drug_concept_id LIMIT 1)[OFFSET(0)] AS drug_concept_id
  FROM `{DS}.drug_exposure`
  WHERE drug_concept_id IS NOT NULL AND drug_concept_id != 0
  GROUP BY person_id
),
obs AS (
  SELECT person_id,
    ARRAY_AGG(observation_concept_id ORDER BY observation_date, observation_concept_id LIMIT 1)[OFFSET(0)] AS observation_concept_id
  FROM `{DS}.observation`
  WHERE observation_concept_id IS NOT NULL AND observation_concept_id != 0
  GROUP BY person_id
)
SELECT p.person_id, p.gender_concept_id, p.year_of_birth,
       cond.condition_concept_id, proc.procedure_concept_id,
       drug.drug_concept_id, obs.observation_concept_id
FROM `{DS}.person` p
JOIN cond USING(person_id)
JOIN proc USING(person_id)
JOIN drug USING(person_id)
JOIN obs  USING(person_id)
ORDER BY p.person_id
LIMIT {N}
"""

# stima costo
dry = client.query(SQL, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
print(f"stima scan: {dry.total_bytes_processed/1e9:.2f} GB (free tier 1 TB/mese)")
if "--dry" in sys.argv:
    sys.exit(0)

df = client.query(SQL).to_dataframe()
print(f"relazione universale: {df.shape[0]} righe x {df.shape[1]} colonne")
print(df.head(3).to_string(index=False))

# salva: csv leggibile + formato fabricator (no header) + schema
df.to_csv(os.path.join(OUT, "omop_universal.csv"), index=False)
df.to_csv(os.path.join(OUT, "omop_universal_data.csv"), header=False, index=False)
types = {"person_id": "int", "gender_concept_id": "int", "year_of_birth": "int",
         "condition_concept_id": "int", "procedure_concept_id": "int",
         "drug_concept_id": "int", "observation_concept_id": "int"}
with open(os.path.join(OUT, "omop_universal_schema.csv"), "w") as f:
    for ccol in df.columns:
        f.write(f"{ccol},{types[ccol]}\n")
print("salvati omop_universal.csv / _data.csv / _schema.csv")
