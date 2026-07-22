"""Fase 3-4: matcher instance-based (value-overlap) esatto vs esteso semantico,
valutati con Recall@ground_truth (metrica Valentine), sulle coppie OMOP fabbricate.

Il matcher esteso semantico è adattato dal notebook del prof
(extended_value_overlap_sim_SemSim / value_overlap_extended_jaccard_SemSim): per
ogni coppia di colonne, due valori sono "in overlap" se la loro similarità
semantica >= soglia, poi si applica Jaccard = |I| / (|I| + soloX + soloY).

Il baseline esatto è la stessa struttura con uguaglianza esatta (= Jaccard classico
sui set di valori), che è ciò che un matcher instance-based standard vedrebbe.
"""
import os
import pandas as pd

from semantic_similarity import (
    build_ancestor_map_from_concept_ancestor,
    semantic_similarity_from_hierarchy,
)


def column_values(df: pd.DataFrame, col: str) -> set:
    """Insieme dei valori distinti non nulli della colonna (concept_id come int)."""
    s = df[col].dropna()
    out = set()
    for v in s:
        try:
            out.add(int(v))
        except (ValueError, TypeError):
            out.add(v)
    return out


# ---------- baseline ESATTO (Jaccard classico sui valori) ----------
def value_overlap_exact(A: set, B: set) -> float:
    if not A and not B:
        return 0.0
    return len(A & B) / len(A | B)


# ---------- esteso SEMANTICO (dal notebook del prof) ----------
def value_overlap_semantic(A: set, B: set, ancestor_map: dict, threshold: float,
                           cache: dict) -> float:
    """|I| / (|I| + soloX + soloY), I = coppie (a,b) con sim semantica >= soglia."""
    matched_A, matched_B, inter = set(), set(), 0
    for a in A:
        for b in B:
            key = (a, b) if a <= b else (b, a)
            sim = cache.get(key)
            if sim is None:
                sim = semantic_similarity_from_hierarchy(a, b, ancestor_map)
                sim = 0.0 if sim is None else sim
                cache[key] = sim
            if sim >= threshold:
                inter += 1
                matched_A.add(a)
                matched_B.add(b)
    solo_x = len(A - matched_A)
    solo_y = len(B - matched_B)
    denom = inter + solo_x + solo_y
    return inter / denom if denom else 0.0


CLINICAL_DOMAINS = ("condition", "procedure", "drug", "observation", "measurement", "device")


def is_concept_column(name: str) -> bool:
    """Colonne clinico-concettuali (prendono similarità semantica). Consapevole del
    dominio: esclude i _concept_id demografici piatti (gender/race/ethnicity)."""
    base = name[:-len("_concept_id")] if name.endswith("_concept_id") else name
    return base.split("_")[0] in CLINICAL_DOMAINS


def match_all_pairs(source: pd.DataFrame, target: pd.DataFrame, ancestor_map: dict,
                    threshold: float):
    """Per ogni coppia di colonne: overlap esatto, semantico e IBRIDO.

    Ibrido = semantico se ENTRAMBE le colonne sono concettuali, altrimenti esatto
    (i "due modelli per due famiglie di colonne" applicati al matcher).
    """
    valsA = {c: column_values(source, c) for c in source.columns}
    valsB = {c: column_values(target, c) for c in target.columns}
    cache = {}
    rows = []
    for ca in source.columns:
        for cb in target.columns:
            ex = value_overlap_exact(valsA[ca], valsB[cb])
            se = value_overlap_semantic(valsA[ca], valsB[cb], ancestor_map, threshold, cache)
            hy = se if (is_concept_column(ca) and is_concept_column(cb)) else ex
            rows.append((ca, cb, ex, se, hy))
    return pd.DataFrame(rows, columns=["source", "target", "sim_exact", "sim_semantic", "sim_hybrid"])


# ---------- Recall@ground_truth (metrica Valentine) ----------
def recall_at_ground_truth(ranked: pd.DataFrame, score_col: str, ground_truth: set) -> float:
    """Frazione delle coppie di ground truth presenti nei primi k = |GT| risultati."""
    k = len(ground_truth)
    top = ranked.sort_values(score_col, ascending=False).head(k)
    top_pairs = set(zip(top["source"], top["target"]))
    return len(top_pairs & ground_truth) / k if k else 0.0
