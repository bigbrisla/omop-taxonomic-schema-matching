"""Fabricator OMOP: estende il fabricator Valentine con rumore tassonomico.

Realizza il raffinamento indicato dal prof: due modelli di rumore per due
famiglie di colonne.
  - colonne `*_concept_id` (clinical concepts) -> rumore TASSONOMICO
    (padre/fratello/figlio via CONCEPT_ANCESTOR) -> taxonomy_noise.TaxonomyNoise
  - altre colonne (testo libero / numeri)        -> rumore LESSICALE Valentine

Riusa lo split verticale di Valentine (`fabricator_system`) per costruire una
coppia OMOP *semantically-joinable*: le colonne comuni (la "chiave di join")
restano con lo stesso nome ma nel target i concept_id vengono perturbati. Cosi'
un join per uguaglianza fallisce, mentre la similarita' semantica (stessa
gerarchia) puo' recuperare il match. Ground truth = mapping colonna->colonna.
"""
import os
import sys
import json
import copy

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "fabricator_system"))

from dataset import Dataset                      # noqa: E402
from vertical_transformations import split as vertical_split  # noqa: E402
from add_noise_schema import approximate_column_names         # noqa: E402
from taxonomy_noise import TaxonomyNoise          # noqa: E402


def read_schema(path):
    lines = open(path).read().splitlines()
    return {i: lines[i].split(",") for i in range(len(lines))}


CLINICAL_DOMAINS = ("condition", "procedure", "drug", "observation", "measurement", "device")


def is_concept_column(name: str) -> bool:
    """Colonne clinico-concettuali (rumore/similarità tassonomica).

    Consapevole del dominio: esclude i _concept_id demografici a vocabolario
    piatto (gender/race/ethnicity), che NON sono gerarchici.
    """
    base = name[:-len("_concept_id")] if name.endswith("_concept_id") else name
    return base.split("_")[0] in CLINICAL_DOMAINS


def fabricate_semantically_joinable(data_path, schema_path, out_dir, name,
                                    tn: TaxonomyNoise, common=0.5, noise_prob=0.7,
                                    min_depth=4, noisy_schema=False, seed=0):
    schema = read_schema(schema_path)
    data = pd.read_csv(data_path, header=None)
    src = Dataset(schema, data)

    # split verticale SENZA rumore Valentine (lo applichiamo noi, tassonomico)
    t1, t2, common_idx = vertical_split(copy.deepcopy(src), 0, common, False, 0)

    # quali colonne comuni sono concept_id? (per indice -> nome via schema)
    concept_common = [i for i in common_idx if is_concept_column(schema[i][0])]
    concept_names = [schema[i][0] for i in concept_common]

    # applica rumore tassonomico SOLO alle colonne-concetto comuni del TARGET (t2)
    n_changed = 0
    for idx in concept_common:
        before = t2.data[idx].copy()
        t2.data[idx] = tn.perturb_series(t2.data[idx], prob=noise_prob, min_depth=min_depth)
        n_changed += int((before.values != t2.data[idx].values).sum())

    if noisy_schema:
        t2 = approximate_column_names(t2, name, 3)

    # ground truth: corrispondenza colonne comuni source->target
    matches = []
    for i in common_idx:
        matches.append({"source_column": t1.schema[i][0], "target_column": t2.schema[i][0]})

    # scrittura
    d = os.path.join(out_dir, name)
    os.makedirs(d, exist_ok=True)
    pd.DataFrame(t1.data.values, columns=[t1.schema[k][0] for k in t1.schema]).to_csv(
        os.path.join(d, "source.csv"), index=False)
    pd.DataFrame(t2.data.values, columns=[t2.schema[k][0] for k in t2.schema]).to_csv(
        os.path.join(d, "target.csv"), index=False)
    pd.DataFrame([(m["source_column"], m["target_column"]) for m in matches],
                 columns=["source", "target"]).to_csv(os.path.join(d, "groundtruth.csv"), index=False)
    json.dump({"matches": matches}, open(os.path.join(d, "matches.json"), "w"), indent=2)

    return dict(dir=d, concept_columns=concept_names, cells_changed=n_changed,
                common=len(common_idx), matches=len(matches))


if __name__ == "__main__":
    ca = pd.read_csv(os.path.join(HERE, "concept_ancestor.csv"))
    names = pd.read_csv(os.path.join(HERE, "concept_names.csv"))
    tn = TaxonomyNoise(ca, names, seed=42)

    info = fabricate_semantically_joinable(
        os.path.join(HERE, "omop_patients_data.csv"),
        os.path.join(HERE, "omop_patients_schema.csv"),
        os.path.join(HERE, "..", "experiments", "target_omop"),
        "omop_semjoinable_1", tn, common=0.5, noise_prob=0.7, min_depth=4, seed=42)

    print("Coppia OMOP semantically-joinable generata:")
    for k, v in info.items():
        print(f"  {k}: {v}")

    # verifica: mostra alcune celle perturbate tassonomicamente con la similarita'
    print("\nVerifica rumore tassonomico sulle colonne-concetto comuni:")
    s = pd.read_csv(os.path.join(info["dir"], "source.csv"))
    t = pd.read_csv(os.path.join(info["dir"], "target.csv"))
    shown = 0
    for col in info["concept_columns"]:
        if col not in t.columns:
            continue
        for i in range(len(s)):
            a, b = s[col][i], t[col][i]
            if pd.notna(a) and pd.notna(b) and int(a) != int(b):
                print(f"  [{col}] {int(a)} ({tn.name(a)})  ->  {int(b)} ({tn.name(b)})"
                      f"  sim={tn.semantic_similarity(a, b):.2f}")
                shown += 1
                break
        if shown >= 5:
            break
