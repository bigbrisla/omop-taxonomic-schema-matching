"""Operatore di rumore tassonomia-aware per concept_id OMOP.

Sostituisce l'operatore "typo su stringa" del fabricator Valentine per le colonne
`*_concept_id`: invece di un errore di battitura (che modella un evento che non
accade), perturba un concetto scambiandolo con un vicino tassonomico — padre,
figlio o (soprattutto) fratello — modellando il vero processo d'errore del
clinical coding (near-miss, lateralita', granularita').

Dati richiesti (estratti da OMOP CONCEPT_ANCESTOR):
  concept_ancestor.csv: ancestor_concept_id, descendant_concept_id,
                        min_levels_of_separation, max_levels_of_separation

La gerarchia diretta (padre-figlio) sono gli archi con min_levels_of_separation=1.
"""
from __future__ import annotations

import random
from collections import defaultdict

import pandas as pd


class TaxonomyNoise:
    def __init__(self, concept_ancestor: pd.DataFrame, names: pd.DataFrame | None = None,
                 seed: int | None = None):
        self.rng = random.Random(seed)
        ca = concept_ancestor
        direct = ca[ca["min_levels_of_separation"] == 1]

        # mappe gerarchiche dirette
        self.parents: dict[int, list[int]] = defaultdict(list)   # c -> padri
        self.children: dict[int, list[int]] = defaultdict(list)  # c -> figli
        for a, d in zip(direct["ancestor_concept_id"].astype(int),
                        direct["descendant_concept_id"].astype(int)):
            self.children[a].append(d)
            self.parents[d].append(a)

        # ancestor/descendant con distanza, per il vicino a distanza-k
        self.anc_by_desc: dict[int, list[tuple[int, int]]] = defaultdict(list)  # c -> [(ancestor, lvl)]
        self.desc_by_anc: dict[int, list[tuple[int, int]]] = defaultdict(list)  # c -> [(descendant, lvl)]
        for a, d, lvl in zip(ca["ancestor_concept_id"].astype(int),
                             ca["descendant_concept_id"].astype(int),
                             ca["min_levels_of_separation"].astype(int)):
            if lvl >= 1:
                self.anc_by_desc[d].append((a, lvl))
                self.desc_by_anc[a].append((d, lvl))

        # set dei concetti foglia (nessun figlio) per preferire near-miss foglia/foglia-1
        self._has_children = set(self.children.keys())

        # profondita' = distanza massima dalla radice (= max livello tra gli antenati).
        # Alta profondita' -> concetto specifico (vicino alla foglia); 0 -> radice/categoria.
        self._depth: dict[int, int] = {}
        for d, lst in self.anc_by_desc.items():
            self._depth[d] = max(lvl for _, lvl in lst) if lst else 0

        self.names = None
        if names is not None:
            self.names = dict(zip(names["concept_id"].astype(int), names["concept_name"]))

    # ---- selettori di vicino (None se non disponibile) ----
    def parent(self, c: int):
        ps = self.parents.get(c)
        return self.rng.choice(ps) if ps else None

    def child(self, c: int):
        cs = self.children.get(c)
        return self.rng.choice(cs) if cs else None

    def sibling(self, c: int, prefer_leaf: bool = True):
        # fratelli = figli dei padri di c, escluso c stesso
        cands = set()
        for p in self.parents.get(c, []):
            cands.update(self.children.get(p, []))
        cands.discard(c)
        if not cands:
            return None
        cands = list(cands)
        if prefer_leaf:
            # preferisci fratelli foglia (near-miss realistico: lateralita', granularita')
            leaves = [x for x in cands if x not in self._has_children]
            if leaves:
                cands = leaves
        return self.rng.choice(cands)

    def neighbor_at_distance(self, c: int, k: int):
        cands = [a for a, lvl in self.anc_by_desc.get(c, []) if lvl == k]
        cands += [d for d, lvl in self.desc_by_anc.get(c, []) if lvl == k]
        return self.rng.choice(cands) if cands else None

    # ---- perturbazione ----
    DEFAULT_WEIGHTS = {"sibling": 0.55, "parent": 0.25, "child": 0.15, "distance2": 0.05}

    def perturb_concept(self, c: int, weights: dict | None = None):
        """Restituisce un concept_id vicino, o c se nessun vicino disponibile.

        La distribuzione e' sbilanciata verso i fratelli (errore near-miss piu'
        frequente nel clinical coding, paper arXiv:2510.07629).
        """
        if pd.isna(c):
            return c
        c = int(c)
        weights = weights or self.DEFAULT_WEIGHTS
        ops = list(weights.keys())
        w = list(weights.values())
        # prova gli operatori in ordine pesato, con fallback se il vicino manca
        for op in self.rng.sample(ops, k=len(ops)) if False else _weighted_order(self.rng, ops, w):
            if op == "sibling":
                r = self.sibling(c)
            elif op == "parent":
                r = self.parent(c)
            elif op == "child":
                r = self.child(c)
            elif op.startswith("distance"):
                r = self.neighbor_at_distance(c, int(op.replace("distance", "")))
            else:
                r = None
            if r is not None and r != c:
                return r
        return c

    def perturb_series(self, s: pd.Series, prob: float, weights: dict | None = None,
                       min_depth: int = 0) -> pd.Series:
        """Perturba ogni cella con probabilita' `prob`.

        `min_depth`: i concetti con profondita' < min_depth (categorie di alto
        livello, non diagnosi foglia) NON vengono perturbati. Modella il fatto
        che gli errori near-miss si concentrano a livello foglia/foglia-1
        (arXiv:2510.07629), evitando i fratelli semanticamente lontani delle
        categorie generiche.
        """
        out = s.copy()
        for i in out.index:
            v = out[i]
            if pd.isna(v):
                continue
            if min_depth and self.depth(int(v)) < min_depth:
                continue
            if self.rng.random() < prob:
                out[i] = self.perturb_concept(v, weights)
        return out

    # ---- profondita' / foglia / similarita' (riusabili per semantic_similarity_from_hierarchy) ----
    def depth(self, c: int) -> int:
        return self._depth.get(int(c), 0)

    def is_leaf(self, c: int) -> bool:
        return int(c) not in self._has_children

    def levels_of_separation(self, c1: int, c2: int):
        """Distanza gerarchica tra due concetti se uno e' antenato dell'altro, altrimenti None."""
        c1, c2 = int(c1), int(c2)
        for a, lvl in self.anc_by_desc.get(c2, []):
            if a == c1:
                return lvl
        for a, lvl in self.anc_by_desc.get(c1, []):
            if a == c2:
                return lvl
        return None

    def semantic_similarity(self, c1, c2) -> float:
        """Similarita' semantica in [0,1] basata sulla distanza gerarchica.

        1.0 se identici; 1/(1+distanza) se in relazione antenato-discendente;
        altrimenti via antenato comune piu' profondo (LCA). Aggancio iniziale per
        la funzione `semantic_similarity_from_hierarchy` prevista dalle specifiche.
        """
        if pd.isna(c1) or pd.isna(c2):
            return 0.0
        c1, c2 = int(c1), int(c2)
        if c1 == c2:
            return 1.0
        d = self.levels_of_separation(c1, c2)
        if d is not None:
            return 1.0 / (1.0 + d)
        # antenati (id->livello) per ciascuno, cerca antenato comune che minimizza la somma
        a1 = {a: lvl for a, lvl in self.anc_by_desc.get(c1, [])}
        a2 = {a: lvl for a, lvl in self.anc_by_desc.get(c2, [])}
        common = set(a1) & set(a2)
        if not common:
            return 0.0
        dist = min(a1[a] + a2[a] for a in common)
        return 1.0 / (1.0 + dist)

    def name(self, c):
        if self.names is None or pd.isna(c):
            return str(c)
        return self.names.get(int(c), str(c))


def _weighted_order(rng: random.Random, ops: list, w: list):
    """Genera gli operatori in ordine casuale pesato (per il fallback a cascata)."""
    ops = ops[:]
    w = w[:]
    while ops:
        i = rng.choices(range(len(ops)), weights=w, k=1)[0]
        yield ops[i]
        ops.pop(i)
        w.pop(i)


if __name__ == "__main__":
    import os
    HERE = os.path.dirname(os.path.abspath(__file__))
    ca = pd.read_csv(os.path.join(HERE, "concept_ancestor.csv"))
    names = pd.read_csv(os.path.join(HERE, "concept_names.csv"))
    patients = pd.read_csv(os.path.join(HERE, "omop_patients.csv"))

    tn = TaxonomyNoise(ca, names, seed=42)

    # mostra il vicinato per alcuni concetti clinici reali con dei fratelli
    print("=== Esempi di vicinato tassonomico (concept reali del dataset) ===\n")
    shown = 0
    for c in patients["condition_1"].dropna().astype(int).unique():
        sib = tn.sibling(c)
        par = tn.parent(c)
        if sib is None or par is None:
            continue
        print(f"CONCETTO  {c}: {tn.name(c)}")
        print(f"  padre     {par}: {tn.name(par)}")
        print(f"  fratello  {sib}: {tn.name(sib)}")
        ch = tn.child(c)
        if ch is not None:
            print(f"  figlio    {ch}: {tn.name(ch)}")
        print()
        shown += 1
        if shown >= 5:
            break

    # dimostra l'effetto del filtro di profondita' (min_depth) sulla qualita'
    col = patients["condition_1"].dropna().astype(int).head(12).reset_index(drop=True)
    for md in (0, 4):
        print(f"=== Perturbazione condition_1 (prob=1.0, min_depth={md}) ===")
        noisy = tn.perturb_series(col, prob=1.0, min_depth=md)
        for orig, new in zip(col, noisy):
            if orig == new:
                tag = f"INVARIATO (depth={tn.depth(orig)} < {md})" if md else "INVARIATO"
            else:
                tag = f"sim={tn.semantic_similarity(orig, new):.2f}"
            print(f"  d{tn.depth(orig)} {orig} ({tn.name(orig)})  ->  {new} ({tn.name(new)})  [{tag}]")
        print()

    # similarita' semantica: esempi
    print("=== semantic_similarity (aggancio a semantic_similarity_from_hierarchy) ===")
    c = int(col.iloc[0])
    par, sib, ch = tn.parent(c), tn.sibling(c), tn.child(c)
    for other, lab in [(c, "se stesso"), (par, "padre"), (ch, "figlio"), (sib, "fratello")]:
        if other is not None:
            print(f"  sim({tn.name(c)}, {tn.name(other)}) [{lab}] = {tn.semantic_similarity(c, other):.3f}")
