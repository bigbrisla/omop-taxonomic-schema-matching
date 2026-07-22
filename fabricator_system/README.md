# Fabricator (versione `valentine-system`) — copia locale eseguibile

Questa è la versione del dataset fabricator **indicata dal prof**:
`delftdata/valentine-system` → `engine/fabricator/`. È la versione canonica del
progetto. Contiene l'orchestratore `valentine_fabricator()` che, per ogni
scenario di relatedness, genera N coppie con parametri randomizzati — la stessa
pipeline che ha prodotto benchmark come TPC_RIDOTTO.

L'originale scrive l'output su **MinIO** (object storage) e usa import di package
(`from .module import ...`). Qui è reso **eseguibile in locale** senza modificare
la logica di fabbricazione.

## Adattamenti rispetto all'originale

1. Import relativi (`from .x import`) → import flat (eseguibile come script).
2. Dipendenza **MinIO resa opzionale** (`try/except`, `from __future__ import
   annotations` per non valutare l'annotazione `client: Minio`). La scrittura su
   object storage è sostituita da scrittura su filesystem via monkeypatch nel
   driver `run_fabricator.py`.
3. Fix compatibilità **pandas 2.x** (gli stessi della versione standalone):
   - `DataFrame.append()` → `pd.concat()` in `horizontal_transformations.py`;
   - rumore typo sulle stringhe saltato perché in pandas 2.x il dtype è `'str'`
     e non `'object'` → in `add_noise_data.sub_job()` ora si accettano
     `('object','str','string')`.

> Nota: questa versione ha `update_values` **seriale** (niente multiprocessing),
> quindi NON soffre del fork-bomb `spawn` su macOS.

## Esecuzione

```bash
source ../.venv/bin/activate
cd fabricator_system
python run_fabricator.py <source_data.csv (no header)> <schema.csv (name,type)> \
    <out_dir> <filename> [no_pairs]
```

Esempio (riproducibile):
```bash
python run_fabricator.py ../experiments/source/patients.csv \
    ../experiments/source/patients_schema.csv ../experiments/target_system patients 4
```

Output per coppia in `<out_dir>/<filename>/<Scenario>/<pair_name>/`:
`source.csv`, `target.csv`, `groundtruth.csv` (2 colonne, come TPC_RIDOTTO),
`matches.json` (mapping completo formato Valentine).

## Validazione (su patients 40×6)

| Scenario | source | target | match | sottoinsieme colonne |
|---|---|---|---|---|
| Unionable | 20×6 | 20×6 | 6 | no (split orizzontale, tutte le colonne) |
| Joinable | 40×5 | 40×5 | ≤cols | sì (split verticale) |
| Semantically-Joinable | 40×4 | 40×5 | ≤cols | sì (vert. + rumore istanze) |
| View-Unionable | 20×5 | 20×5 | 4 | sì (vert. + righe disgiunte) |

## Finding importante sul codice originale (View-Unionable)

Nel ramo View-Unionable di `valentine_fabricator` c'è un'**incoerenza**: la
sotto-branca con schema *verbatim* usa `vertical_split` (sottoinsieme di colonne
= view-unionable corretto secondo il paper), mentre la sotto-branca con schema
*noisy* usa solo `horizontal_split` (tiene tutte le colonne = di fatto
unionable). Per ottenere view-unionable "vero" bisogna quindi usare schema
verbatim (vedi `SCENARIO_PARAMS` in `run_fabricator.py`). È una caratteristica
dell'implementazione di riferimento, non un effetto dell'adattamento.

## Rapporto con `../fabricator/`

`../fabricator/` è la versione **standalone** (`valentine-data-fabricator`,
config.ini-driven), usata inizialmente per capire e validare velocemente la
logica e scoprire i bug pandas 2.x. La logica di trasformazione è identica.
Da qui in avanti la versione canonica è **questa** (`fabricator_system/`),
allineata a quella indicata dal prof.
