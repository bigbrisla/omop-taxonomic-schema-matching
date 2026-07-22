"""Similarità semantica dalla gerarchia OMOP, allineata al notebook del prof
(Instance_based_Schema_Matching_su_Dati_Sanitari_OMOP_CDM) e alla tesi Tomisani.

Formula (Sanchez et al., ripresa da Tomisani):
    sim(v1,v2) = 1 - log2(1 + (|T(v1) ∪ T(v2)| - |T(v1) ∩ T(v2)|) / |T(v1) ∪ T(v2)|)
dove T(v) = insieme dei subsumers tassonomici di v (tutti i suoi antenati + v stesso).

Differenza rispetto al notebook del prof: lì `ancestor_map` era costruita dalla
gerarchia ARX (k-anonimizzazione); qui viene costruita da CONCEPT_ANCESTOR, dove
gli antenati a ogni livello sono già tutti espliciti (chiusura transitiva).

In questa prima versione le distanze (min/max_levels_of_separation) NON entrano
nella formula: si lavora solo sulla sovrapposizione tra insiemi di antenati
(come indicato dal prof; possibile variante futura per pesarle).
"""
import math
import os
import pandas as pd


def build_ancestor_map_from_concept_ancestor(concept_ancestor: pd.DataFrame) -> dict:
    """concept_id -> insieme dei suoi antenati (T(c)), incluso c stesso.

    T(c) = { ancestor_concept_id : (ancestor, c) ∈ CONCEPT_ANCESTOR } ∪ {c}.
    """
    ancestor_map: dict[int, set] = {}
    for desc, anc in zip(concept_ancestor["descendant_concept_id"].astype(int),
                         concept_ancestor["ancestor_concept_id"].astype(int)):
        ancestor_map.setdefault(desc, set()).add(anc)
    # includi il concetto stesso tra i suoi subsumers
    for c in list(ancestor_map.keys()):
        ancestor_map[c].add(c)
    return ancestor_map


def semantic_similarity_from_hierarchy(v1, v2, ancestor_map: dict):
    """Similarità semantica ∈ [0,1] (None se un concetto non è nella mappa).

    1 = concetti identici; più basso = meno simili. Verbatim dalla formula del
    notebook del prof.
    """
    T_v1 = ancestor_map.get(v1)
    T_v2 = ancestor_map.get(v2)
    if T_v1 is None or T_v2 is None:
        return None
    union_set = T_v1.union(T_v2)
    intersection_set = T_v1.intersection(T_v2)
    union_size = len(union_set)
    if union_size == 0:
        return None
    intersection_size = len(intersection_set)
    return 1 - math.log2(1 + (union_size - intersection_size) / union_size)


if __name__ == "__main__":
    HERE = os.path.dirname(os.path.abspath(__file__))
    ca = pd.read_csv(os.path.join(HERE, "concept_ancestor_full.csv"))
    names = pd.read_csv(os.path.join(HERE, "concept_names.csv"))
    nm = dict(zip(names.concept_id.astype(int), names.concept_name))
    amap = build_ancestor_map_from_concept_ancestor(ca)
    print(f"ancestor_map: {len(amap)} concetti; es. |T(443612)| = {len(amap.get(443612, []))}")

    def sim(a, b):
        return semantic_similarity_from_hierarchy(a, b, amap)

    def show(a, b):
        s = sim(a, b)
        print(f"  sim = {s:.3f}   {nm.get(a,a)}  <->  {nm.get(b,b)}")

    print("\n=== identità (atteso 1.0) ===")
    show(443612, 443612)
    print("\n=== near-miss (fratelli/padre-figlio, attesa ALTA) ===")
    show(443612, 443614)   # CKD stage 4 vs stage 5 (fratelli)
    show(443612, 46271022) # CKD stage 4 vs Chronic kidney disease (padre)
    print("\n=== concetti lontani (attesa BASSA) ===")
    show(443612, 201965)   # CKD stage 4 vs Shock
    show(443612, 40479343) # CKD stage 4 vs Exposure to Human poliovirus
