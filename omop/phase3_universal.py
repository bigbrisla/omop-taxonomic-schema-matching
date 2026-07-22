"""Fase 3-4 sulla RELAZIONE UNIVERSALE (colonne-concetto di domini distinti, EC).

Approccio pulito: (1) fabbrica tutte le coppie e raccoglie i valori che compaiono
davvero; (2) estrae da BigQuery gli antenati COMPLETI solo per quei valori (poche
migliaia); (3) valuta esatto vs semantico vs ibrido con Recall@ground_truth medio.
"""
import os
import sys
import json
import statistics
import pandas as pd
from google.cloud import bigquery

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fabricator_omop import fabricate_semantically_joinable, is_concept_column
from taxonomy_noise import TaxonomyNoise
from semantic_similarity import build_ancestor_map_from_concept_ancestor
from phase3_matcher import match_all_pairs, recall_at_ground_truth

DS = "bigquery-public-data.cms_synthetic_patient_data_omop"
N_SAMPLE = 400
THRESHOLD = 0.45
MIN_DEPTH = 2
NOISE_LEVELS = [0.2, 0.5, 0.8, 1.0]
SEEDS = [1, 2, 3, 4, 5]

data = pd.read_csv(os.path.join(HERE, "omop_universal_data.csv"), header=None).head(N_SAMPLE)
sample_path = os.path.join(HERE, "omop_universal_sample_data.csv")
data.to_csv(sample_path, header=False, index=False)
ca_noise = pd.read_csv(os.path.join(HERE, "concept_ancestor_universal.csv"))

# 1) fabbrica tutte le coppie, raccogli i valori concettuali reali
print("fabbricazione coppie ...", flush=True)
pairs = {}
values = set()
for noise in NOISE_LEVELS:
    for seed in SEEDS:
        tn = TaxonomyNoise(ca_noise, None, seed=seed)
        info = fabricate_semantically_joinable(
            sample_path, os.path.join(HERE, "omop_universal_schema.csv"),
            os.path.join(HERE, "..", "experiments", "target_universal"),
            f"pair_{noise}_{seed}", tn, common=0.5, noise_prob=noise, min_depth=MIN_DEPTH, seed=seed)
        d = info["dir"]
        source = pd.read_csv(os.path.join(d, "source.csv"))
        target = pd.read_csv(os.path.join(d, "target.csv"))
        gt = {(m["source_column"], m["target_column"])
              for m in json.load(open(os.path.join(d, "matches.json")))["matches"]}
        pairs[(noise, seed)] = (source, target, gt)
        for df in (source, target):
            for c in df.columns:
                if is_concept_column(c):
                    values.update(int(x) for x in df[c].dropna())
values.discard(0)
V = sorted(values)
print(f"valori concettuali reali che compaiono nelle coppie: {len(V)}")

# 2) antenati completi SOLO per V (da BigQuery, batch, int nativi)
client = bigquery.Client()
frames = []
for i in range(0, len(V), 20000):
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ArrayQueryParameter("ids", "INT64", [int(x) for x in V[i:i+20000]])])
    frames.append(client.query(
        f"""SELECT ancestor_concept_id, descendant_concept_id
            FROM `{DS}.concept_ancestor` WHERE descendant_concept_id IN UNNEST(@ids)""",
        job_config=cfg).to_dataframe())
full = pd.concat(frames, ignore_index=True)
full["min_levels_of_separation"] = 1  # colonna non usata dalla formula
print(f"antenati completi per V: {len(full)} righe")
amap = build_ancestor_map_from_concept_ancestor(full)

# 3) valutazione
print(f"\n{'noise':>6} | {'exact':>6} {'semantic':>8} {'hybrid':>6}   (Recall@GT medio su", len(SEEDS), "coppie)")
print("-" * 48)
for noise in NOISE_LEVELS:
    r_ex, r_se, r_hy = [], [], []
    for seed in SEEDS:
        source, target, gt = pairs[(noise, seed)]
        res = match_all_pairs(source, target, amap, THRESHOLD)
        r_ex.append(recall_at_ground_truth(res, "sim_exact", gt))
        r_se.append(recall_at_ground_truth(res, "sim_semantic", gt))
        r_hy.append(recall_at_ground_truth(res, "sim_hybrid", gt))
    print(f"{noise:>6.1f} | {statistics.mean(r_ex):>6.2f} {statistics.mean(r_se):>8.2f} {statistics.mean(r_hy):>6.2f}", flush=True)

print("\nLegenda: exact=value-overlap classico, semantic=value-overlap esteso (sim. semantica),")
print("hybrid=semantico sulle colonne-concetto (domini clinici) ed esatto sulle altre.")
