"""Esegue il confronto Fase 3-4 su una coppia OMOP semantically-joinable:
matcher value-overlap ESATTO vs ESTESO SEMANTICO, valutati con Recall@ground_truth.
"""
import os
import sys
import json
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fabricator_omop import fabricate_semantically_joinable
from taxonomy_noise import TaxonomyNoise
from semantic_similarity import build_ancestor_map_from_concept_ancestor
from phase3_matcher import match_all_pairs, recall_at_ground_truth

N_SAMPLE = 300
THRESHOLD = 0.45   # soglia del matcher esteso (come Tomisani / notebook prof)

# 1) campione piccolo in formato fabricator (no header) + schema
data = pd.read_csv(os.path.join(HERE, "omop_patients_data.csv"), header=None)
sample = data.head(N_SAMPLE)
sample_path = os.path.join(HERE, "omop_sample_data.csv")
sample.to_csv(sample_path, header=False, index=False)

# 2) fabbrica la coppia semantically-joinable (rumore tassonomico sui concept_id)
ca_full = pd.read_csv(os.path.join(HERE, "concept_ancestor_full.csv"))
names = pd.read_csv(os.path.join(HERE, "concept_names.csv"))
tn = TaxonomyNoise(pd.read_csv(os.path.join(HERE, "concept_ancestor.csv")), names, seed=1)
info = fabricate_semantically_joinable(
    sample_path, os.path.join(HERE, "omop_patients_schema.csv"),
    os.path.join(HERE, "..", "experiments", "target_omop"),
    "omop_semjoinable_eval", tn, common=0.5, noise_prob=0.8, min_depth=4, seed=1)
print("Coppia fabbricata:", {k: info[k] for k in ("concept_columns", "cells_changed", "common", "matches")})

d = info["dir"]
source = pd.read_csv(os.path.join(d, "source.csv"))
target = pd.read_csv(os.path.join(d, "target.csv"))
matches = json.load(open(os.path.join(d, "matches.json")))["matches"]
ground_truth = {(m["source_column"], m["target_column"]) for m in matches}

# 3) ancestor_map completa e matcher
print("costruzione ancestor_map ...", flush=True)
amap = build_ancestor_map_from_concept_ancestor(ca_full)
print("matching (esatto + semantico) ...", flush=True)
res = match_all_pairs(source, target, amap, THRESHOLD)

# 4) valutazione
rec_exact = recall_at_ground_truth(res, "sim_exact", ground_truth)
rec_sem = recall_at_ground_truth(res, "sim_semantic", ground_truth)
rec_hyb = recall_at_ground_truth(res, "sim_hybrid", ground_truth)

print("\n=== Ground truth (coppie di colonne corrette) ===")
for s, t in sorted(ground_truth):
    print(f"  {s}  <->  {t}")

print("\n=== Top match per SIMILARITÀ ESATTA (value overlap classico) ===")
print(res.sort_values("sim_exact", ascending=False).head(len(ground_truth) + 3).to_string(index=False))

print("\n=== Top match per SIMILARITÀ SEMANTICA (value overlap esteso) ===")
print(res.sort_values("sim_semantic", ascending=False).head(len(ground_truth) + 3).to_string(index=False))

print("\n=== Top match per IBRIDO (semantico su concept, esatto altrove) ===")
print(res.sort_values("sim_hybrid", ascending=False).head(len(ground_truth) + 3).to_string(index=False))

print("\n=== RISULTATO: Recall@ground_truth ===")
print(f"  Matcher ESATTO   : {rec_exact:.2f}")
print(f"  Matcher SEMANTICO: {rec_sem:.2f}")
print(f"  Matcher IBRIDO   : {rec_hyb:.2f}")

# focus: coppie di ground truth sulle colonne-concetto (dove il rumore morde)
print("\n=== Dettaglio sulle colonne-concetto (ground truth) ===")
concept_gt = [(s, t) for (s, t) in ground_truth if any(
    s.startswith(p) for p in ("condition_", "observation_", "procedure_"))]
for s, t in sorted(concept_gt):
    r = res[(res.source == s) & (res.target == t)].iloc[0]
    print(f"  {s:<14} exact={r.sim_exact:.3f}  semantic={r.sim_semantic:.3f}")
