"""Estrae la gerarchia CONCEPT_ANCESTOR per i concetti della relazione universale.

Di default produce solo il file necessario alla pipeline:
  - concept_ancestor_universal.csv      : vicinato (per il rumore tassonomico)

Con l'opzione `--full` produce anche due dump completi, NON usati dagli
esperimenti (`phase3_universal.py` si scarica gli antenati al volo da BigQuery
per i soli valori che servono). Sono pesanti: ~45 minuti e ~1 GB su disco.
  - concept_ancestor_universal_full.csv : antenati completi
  - concept_names_universal.csv         : nomi

Query separate e leggere (JOIN di uguaglianza) + array param a batch (evita lo
shuffle, il limite di testo SQL e il limite di dimensione della richiesta).
"""
import os
import sys
import pandas as pd
from google.cloud import bigquery

FULL = "--full" in sys.argv

DS = "bigquery-public-data.cms_synthetic_patient_data_omop"
OUT = os.path.dirname(os.path.abspath(__file__))
CONCEPT_COLS = ["condition_concept_id", "procedure_concept_id", "drug_concept_id", "observation_concept_id"]
client = bigquery.Client()

uni = pd.read_csv(os.path.join(OUT, "omop_universal.csv"))
S = set()
for c in CONCEPT_COLS:
    S.update(int(x) for x in uni[c].dropna().unique())
S.discard(0)
S = sorted(S)
print(f"concetti clinici distinti nella relazione universale: {len(S)}")


def q(sql, params):
    cfg = bigquery.QueryJobConfig(query_parameters=params)
    return client.query(sql, job_config=cfg).to_dataframe()


def arr(name, vals):
    return bigquery.ArrayQueryParameter(name, "INT64", [int(x) for x in vals])


def q_batched(sql, ids, chunk=20000):
    """Esegue `sql` (con parametro @ids) a batch: una lista di id molto grande
    (es. il vicinato di un concetto generico, decine/centinaia di migliaia di
    elementi) supera il limite di dimensione della richiesta HTTP se passata
    tutta insieme come singolo ArrayQueryParameter (errore 413)."""
    ids = sorted(int(x) for x in ids)
    frames = [q(sql, [arr("ids", ids[i:i + chunk])]) for i in range(0, len(ids), chunk)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# 1) VICINATO (per il rumore): ancestors/descendants entro 6 livelli + fratelli
anc = q(f"""SELECT ancestor_concept_id, descendant_concept_id, min_levels_of_separation, max_levels_of_separation
           FROM `{DS}.concept_ancestor`
           WHERE descendant_concept_id IN UNNEST(@ids) AND min_levels_of_separation BETWEEN 1 AND 6""",
        [arr("ids", S)])
desc = q(f"""SELECT ancestor_concept_id, descendant_concept_id, min_levels_of_separation, max_levels_of_separation
            FROM `{DS}.concept_ancestor`
            WHERE ancestor_concept_id IN UNNEST(@ids) AND min_levels_of_separation BETWEEN 1 AND 6""",
         [arr("ids", S)])
parents = sorted(set(anc.loc[anc.min_levels_of_separation == 1, "ancestor_concept_id"].astype(int)))
print(f"len(parents) = {len(parents)}")
sib = q_batched(f"""SELECT ancestor_concept_id, descendant_concept_id, min_levels_of_separation, max_levels_of_separation
           FROM `{DS}.concept_ancestor`
           WHERE ancestor_concept_id IN UNNEST(@ids) AND min_levels_of_separation = 1""", parents)
nb = pd.concat([anc, desc, sib], ignore_index=True).drop_duplicates(
    subset=["ancestor_concept_id", "descendant_concept_id"])
nb.to_csv(os.path.join(OUT, "concept_ancestor_universal.csv"), index=False)
print(f"vicinato: {len(nb)} righe -> concept_ancestor_universal.csv")

if not FULL:
    print("FATTO. (dump completi omessi: usare --full per generarli)")
    sys.exit()

# 2) V = concetti che possono comparire come valore (S + vicini)
V = set(S) | set(nb.ancestor_concept_id) | set(nb.descendant_concept_id)
V = sorted(int(x) for x in V)
print(f"len(V) = {len(V)}")

# 3) ANTENATI COMPLETI (tutti i livelli) per V -- batch
full = q_batched(f"""SELECT ancestor_concept_id, descendant_concept_id, min_levels_of_separation
            FROM `{DS}.concept_ancestor`
            WHERE descendant_concept_id IN UNNEST(@ids)""", V)
full = full.drop_duplicates(subset=["ancestor_concept_id", "descendant_concept_id"])
full.to_csv(os.path.join(OUT, "concept_ancestor_universal_full.csv"), index=False)
print(f"antenati completi: {len(full)} righe, liv max {full.min_levels_of_separation.max()} -> _full.csv")

# 4) NOMI per tutti gli id coinvolti (batch)
ids = sorted(set(full.ancestor_concept_id).union(full.descendant_concept_id).union(V))
cn = q_batched(f"""SELECT concept_id, concept_name, domain_id, vocabulary_id, concept_class_id, standard_concept
                       FROM `{DS}.concept` WHERE concept_id IN UNNEST(@ids)""", ids)
cn = cn.drop_duplicates(subset=["concept_id"])
cn.to_csv(os.path.join(OUT, "concept_names_universal.csv"), index=False)
print(f"nomi: {len(cn)} concetti -> concept_names_universal.csv")
print("FATTO.")
