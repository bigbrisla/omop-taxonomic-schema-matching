"""Driver locale per la versione `valentine-system/engine/fabricator`.

La funzione `valentine_fabricator()` originale scrive su MinIO (object storage).
Qui la rendiamo eseguibile su filesystem locale via monkeypatch della funzione
`write_files_to_minio`, senza toccare la logica di fabbricazione.

Uso:
    python run_fabricator.py <source_data.csv (no header)> <schema.csv (name,type)> \
        <out_dir> <filename> [no_pairs]

Per ogni scenario (Unionable, Joinable, Semantically-Joinable, View-Unionable)
genera `no_pairs` coppie con parametri randomizzati, come nel sistema Valentine.
Output per coppia: <out_dir>/<scenario>/<pair_name>/{source.csv,target.csv,
groundtruth.csv,matches.json}.
"""
import os
import sys
import json

import pandas as pd

import dataset_generator as dg
from dataset import Dataset


def read_schema(infile: str) -> dict:
    lines = open(infile, "r").read().splitlines()
    return {a: lines[a].split(",") for a in range(len(lines))}


def read_data(infile: str) -> pd.DataFrame:
    return pd.read_csv(infile, header=None, delimiter=",")


def write_files_local(target1: Dataset, target2: Dataset, mapping: dict, dir_name: str,
                      client, bucket, group_name: str):
    """Sostituto locale di write_files_to_minio (stessa firma).

    `bucket` qui è interpretato come directory di output radice; `client` è
    ignorato. Scrive source.csv / target.csv / groundtruth.csv / matches.json
    riproducendo la convenzione di TPC_RIDOTTO.
    """
    out_dir = os.path.join(bucket, group_name, dir_name)
    os.makedirs(out_dir, exist_ok=True)

    # schema -> nomi colonne (target1 = source, target2 = target)
    src_cols = [target1.schema[k][0] for k in target1.schema.keys()]
    tgt_cols = [target2.schema[k][0] for k in target2.schema.keys()]

    s = pd.DataFrame(target1.data.values, columns=src_cols)
    t = pd.DataFrame(target2.data.values, columns=tgt_cols)
    s.to_csv(os.path.join(out_dir, "source.csv"), index=False)
    t.to_csv(os.path.join(out_dir, "target.csv"), index=False)

    matches = [mapping[i] for i in mapping.keys()]
    # groundtruth.csv a 2 colonne (come TPC_RIDOTTO)
    gt = pd.DataFrame(
        [(m["source_column"], m["target_column"]) for m in matches],
        columns=["source", "target"],
    )
    gt.to_csv(os.path.join(out_dir, "groundtruth.csv"), index=False)
    # matches.json (mapping completo, formato Valentine)
    json.dump({"matches": matches}, open(os.path.join(out_dir, "matches.json"), "w"), indent=4)


# scenario -> parametri [noisy_instances, noisy_schemata, verbatim_instances, verbatim_schemata]
# NB: nel codice originale Valentine, il ramo View-Unionable produce il
# sottoinsieme di colonne (vertical_split, definizione corretta del paper) SOLO
# con schema verbatim; con schema noisy ricade su horizontal_split (tiene tutte
# le colonne). Per ottenere view-unionable "vero" usiamo quindi schema verbatim.
SCENARIO_PARAMS = {
    "Unionable":             [True, True, True, True],
    "Joinable":              [False, True, True, True],
    "Semantically-Joinable": [True, True, False, True],
    "View-Unionable":        [False, False, True, True],
}


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)
    data_path, schema_path, out_dir, filename = sys.argv[1:5]
    no_pairs = int(sys.argv[5]) if len(sys.argv) > 5 else 4

    in_data = read_data(data_path)
    in_schema = read_schema(schema_path)

    # monkeypatch: MinIO -> filesystem locale
    dg.write_files_to_minio = write_files_local

    for scenario, params in SCENARIO_PARAMS.items():
        dg.valentine_fabricator(
            scenario=scenario,
            parameters=params,
            no_pairs=no_pairs,
            in_data=in_data.copy(),
            in_schema=dict(in_schema),
            group_name=filename,        # cartella di gruppo
            filename=filename,
            client=None,                # ignorato
            bucket=out_dir,             # directory radice di output
        )
        print(f"[{scenario}] {no_pairs} coppie generate")


if __name__ == "__main__":
    main()
