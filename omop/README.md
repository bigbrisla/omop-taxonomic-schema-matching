# OMOP: rumore tassonomico + fabricator semantico

Estensione del fabricator Valentine a dati OMOP-CDM, secondo la direzione del prof:
sostituire il "typo su stringa" con un operatore **tassonomia-aware** sui
`*_concept_id`, modellando i veri errori near-miss del clinical coding
(fratello/padre/figlio nella gerarchia SNOMED), e tenere il rumore lessicale per
le colonne di testo libero.

## Dati (estratti da BigQuery, CMS synthetic OMOP)

| file | contenuto |
|---|---|
| `omop_patients.csv` | 2000 pazienti, 10 col (demografici + condition/observation/procedure_1/2) |
| `omop_patients_data.csv` / `_schema.csv` | stessi dati in formato fabricator (no header + schema) |
| `concept_ancestor.csv` | ~340k archi gerarchici (ancestor, descendant, min/max_levels_of_separation) |
| `concept_names.csv` | ~130k concept_id → nome/dominio/vocabolario |

Script di estrazione: `extract_omop.py`, `extract_ancestor.py`, `extract_names.py`
(auth gcloud ADC; dataset pubblico, costo ~0).

## Operatore di rumore: `taxonomy_noise.py`

`TaxonomyNoise(concept_ancestor, names)` con:
- selettori `parent`, `child`, `sibling` (preferisce fratelli foglia), `neighbor_at_distance(k)`;
- `perturb_series(col, prob, min_depth)`: perturba ogni cella con prob. `prob`;
  **`min_depth`** salta i concetti troppo generici (categorie), concentrando il
  rumore a livello foglia/foglia−1 dove avvengono gli errori reali
  (arXiv:2510.07629). Senza il filtro, i fratelli di una categoria generica sono
  semanticamente lontani; con `min_depth=4` le perturbazioni sono near-miss
  realistici (es. *Chronic kidney disease stage 4 → stage 5*).
- `semantic_similarity(c1, c2)` ∈ [0,1] dalla distanza gerarchica (1/(1+dist)) —
  aggancio a `semantic_similarity_from_hierarchy` delle specifiche; usa la STESSA
  gerarchia del rumore.

Self-test: `python taxonomy_noise.py`.

## Fabricator OMOP: `fabricator_omop.py`

Riusa lo split verticale di Valentine (`fabricator_system`) e applica i **due
rumori per due famiglie di colonne**: tassonomico sulle colonne-concetto comuni,
lessicale altrove. Produce una coppia *semantically-joinable* con ground truth:
le colonne di join hanno lo stesso nome ma nel target i concept_id sono
perturbati → join per uguaglianza fallisce, similarità semantica recupera.

Esecuzione: `python fabricator_omop.py` → output in
`../experiments/target_omop/omop_semjoinable_1/` (source.csv, target.csv,
groundtruth.csv, matches.json).

## Prossimo passo

Estendere un matcher instance-based (ExtendedJaccard) usando
`semantic_similarity` al posto dell'uguaglianza esatta sui concept_id, e valutarlo
su queste coppie con Recall@ground_truth (metrica Valentine).
