"""Vista dettagliata su UNA coppia della relazione universale (rumore forte):
mostra i punteggi assoluti esatto vs semantico per ogni coppia di colonne, per
evidenziare che sul match vero l'overlap esatto e' molto basso (sotto soglia di
accettazione) mentre la similarita' semantica lo riconosce.
"""
import os
import sys
import json
import pandas as pd
from google.cloud import bigquery

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fabricator_omop import fabricate_semantically_joinable, is_concept_column
from taxonomy_noise import TaxonomyNoise
from semantic_similarity import build_ancestor_map_from_concept_ancestor
from phase3_matcher import match_all_pairs

DS = "bigquery-public-data.cms_synthetic_patient_data_omop"
data = pd.read_csv(os.path.join(HERE, "omop_universal_data.csv"), header=None).head(400)
sp = os.path.join(HERE, "omop_universal_sample_data.csv")
data.to_csv(sp, header=False, index=False)
tn = TaxonomyNoise(pd.read_csv(os.path.join(HERE, "concept_ancestor_universal.csv")), None, seed=1)
info = fabricate_semantically_joinable(
    sp, os.path.join(HERE, "omop_universal_schema.csv"),
    os.path.join(HERE, "..", "experiments", "target_universal_detail"),
    "detail", tn, common=0.5, noise_prob=1.0, min_depth=2, seed=1)
d = info["dir"]
source = pd.read_csv(os.path.join(d, "source.csv"))
target = pd.read_csv(os.path.join(d, "target.csv"))
gt = {(m["source_column"], m["target_column"])
      for m in json.load(open(os.path.join(d, "matches.json")))["matches"]}

vals = set()
for df in (source, target):
    for c in df.columns:
        if is_concept_column(c):
            vals.update(int(x) for x in df[c].dropna())
vals.discard(0)
V = sorted(vals)
client = bigquery.Client()
frames = []
for i in range(0, len(V), 20000):
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ArrayQueryParameter("ids", "INT64", [int(x) for x in V[i:i+20000]])])
    frames.append(client.query(
        f"SELECT ancestor_concept_id, descendant_concept_id FROM `{DS}.concept_ancestor` "
        f"WHERE descendant_concept_id IN UNNEST(@ids)", job_config=cfg).to_dataframe())
full = pd.concat(frames, ignore_index=True)
full["min_levels_of_separation"] = 1
amap = build_ancestor_map_from_concept_ancestor(full)

res = match_all_pairs(source, target, amap, 0.45)
res["GT"] = res.apply(lambda r: "<-- match vero" if (r.source, r.target) in gt else "", axis=1)

print("Colonne source:", list(source.columns))
print("Colonne target:", list(target.columns))
print("\n=== SOLO le coppie di ground truth (diagonale) ===")
gtrows = res[res.GT != ""].sort_values("sim_exact", ascending=False)
print(gtrows[["source", "target", "sim_exact", "sim_semantic"]].to_string(index=False))

print("\n=== Se si applicasse una soglia di accettazione 0.30 (stile dataset discovery) ===")
acc_ex = gtrows[gtrows.sim_exact >= 0.30]
acc_se = gtrows[gtrows.sim_semantic >= 0.30]
print(f"  match veri ACCETTATI da ESATTO   (>=0.30): {len(acc_ex)}/{len(gtrows)}")
print(f"  match veri ACCETTATI da SEMANTICO(>=0.30): {len(acc_se)}/{len(gtrows)}")
