"""Valutazione Fase 4 su piu' coppie e livelli di rumore.

Come in Valentine, la performance si misura mediando su molte coppie fabbricate.
Qui si varia l'intensita' del rumore tassonomico e si media il Recall@ground_truth
di tre matcher: esatto, semantico, ibrido (semantico su concept, esatto altrove).
Attesa: al crescere del rumore l'esatto crolla, la semantica/ibrido reggono.
"""
import os
import sys
import json
import statistics
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fabricator_omop import fabricate_semantically_joinable
from taxonomy_noise import TaxonomyNoise
from semantic_similarity import build_ancestor_map_from_concept_ancestor
from phase3_matcher import match_all_pairs, recall_at_ground_truth

N_SAMPLE = 150
THRESHOLD = 0.45
MIN_DEPTH = 2                     # perturba anche concetti meno profondi -> rumore piu' forte
NOISE_LEVELS = [0.2, 0.5, 0.8, 1.0]
SEEDS = [1, 2, 3, 4, 5]

# dati e mappe caricati una volta
data = pd.read_csv(os.path.join(HERE, "omop_patients_data.csv"), header=None).head(N_SAMPLE)
sample_path = os.path.join(HERE, "omop_sample_data.csv")
data.to_csv(sample_path, header=False, index=False)
ca_noise = pd.read_csv(os.path.join(HERE, "concept_ancestor.csv"))
names = pd.read_csv(os.path.join(HERE, "concept_names.csv"))
print("costruzione ancestor_map ...", flush=True)
amap = build_ancestor_map_from_concept_ancestor(pd.read_csv(os.path.join(HERE, "concept_ancestor_full.csv")))

print(f"\n{'noise':>6} | {'exact':>6} {'semantic':>8} {'hybrid':>6}   (Recall@GT medio su", len(SEEDS), "coppie)")
print("-" * 48)
summary = []
for noise in NOISE_LEVELS:
    r_ex, r_se, r_hy = [], [], []
    for seed in SEEDS:
        tn = TaxonomyNoise(ca_noise, names, seed=seed)
        info = fabricate_semantically_joinable(
            sample_path, os.path.join(HERE, "omop_patients_schema.csv"),
            os.path.join(HERE, "..", "experiments", "target_omop_sweep"),
            f"pair_{noise}_{seed}", tn, common=0.5, noise_prob=noise,
            min_depth=MIN_DEPTH, seed=seed)
        d = info["dir"]
        source = pd.read_csv(os.path.join(d, "source.csv"))
        target = pd.read_csv(os.path.join(d, "target.csv"))
        gt = {(m["source_column"], m["target_column"])
              for m in json.load(open(os.path.join(d, "matches.json")))["matches"]}
        res = match_all_pairs(source, target, amap, THRESHOLD)
        r_ex.append(recall_at_ground_truth(res, "sim_exact", gt))
        r_se.append(recall_at_ground_truth(res, "sim_semantic", gt))
        r_hy.append(recall_at_ground_truth(res, "sim_hybrid", gt))
    me, ms, mh = statistics.mean(r_ex), statistics.mean(r_se), statistics.mean(r_hy)
    summary.append((noise, me, ms, mh))
    print(f"{noise:>6.1f} | {me:>6.2f} {ms:>8.2f} {mh:>6.2f}", flush=True)

print("\nLegenda: exact=value-overlap classico, semantic=value-overlap esteso (sim. semantica),")
print("hybrid=semantico sulle colonne-concetto ed esatto sulle altre.")
