# Instance-based Schema Matching su dati sanitari OMOP-CDM

Baseline in chiaro per lo schema matching instance-based su dati clinici OMOP-CDM,
con un operatore di rumore e una similarità semantica tassonomia-aware costruiti
sulla gerarchia SNOMED (tabella `CONCEPT_ANCESTOR`). Basato sul framework
[Valentine](https://github.com/delftdata/valentine) (fabricator + metrica
Recall@ground truth).

## Struttura del progetto

```
omop/                 codice principale: estrazione dati, rumore tassonomico,
                       similarità semantica, matcher, esperimenti
fabricator_system/     fabricator Valentine adattato (split verticale/orizzontale),
                       usato da omop/fabricator_omop.py
experiments/           output degli esperimenti di fabbricazione (coppie source/
                       target con ground truth, per i vari scenari)
```

`omop/` non è autosufficiente: importa moduli da `fabricator_system/`
(`dataset.py`, `vertical_transformations.py`, `add_noise_schema.py`), quindi le
due cartelle vanno mantenute insieme con la stessa struttura relativa.

## Requisiti

- Python 3.13 (o comunque 3.10+)
- Pacchetti: `pandas`, `google-cloud-bigquery`, `db-dtypes`, `Unidecode`

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas google-cloud-bigquery db-dtypes Unidecode
```

### Autenticazione BigQuery

Alcuni script leggono dal dataset pubblico
`bigquery-public-data.cms_synthetic_patient_data_omop` (costo di query ~0, dati
pubblici). Serve comunque un account Google con un progetto GCP di quota
associato per l'autenticazione:

```bash
gcloud auth application-default login
```

Senza questa autenticazione, gli script che interrogano BigQuery dal vivo
(`extract_universal.py`, `extract_universal_hierarchy.py`, e il passo di
estrazione antenati dentro `phase3_universal.py`) falliscono in fase di query.
Gli script che lavorano solo sui CSV già estratti in `omop/` non richiedono
questa autenticazione.

## Esecuzione

I dati clinici sono già estratti come CSV in `omop/` (`omop_universal_data.csv`,
`omop_universal_schema.csv`). La gerarchia dei concetti
(`concept_ancestor_universal.csv`, ~65 MB) è troppo grande per il repository e va
rigenerata una volta prima di eseguire l'esperimento:

```bash
cd omop

# gerarchia dei concetti da BigQuery (~3 minuti, richiede l'autenticazione sopra)
python extract_universal_hierarchy.py

# esperimento principale: fabbrica le coppie, valuta esatto/semantico/ibrido,
# stampa la Recall@ground truth media per livello di rumore (~40 minuti)
python phase3_universal.py

# analisi di dettaglio a soglia di accettazione (punteggi assoluti)
python phase3_universal_detail.py
```

`phase3_universal.py` si scarica da BigQuery gli antenati completi solo per i
valori che compaiono davvero nelle coppie fabbricate, quindi non serve alcun dump
completo della gerarchia. Per rigenerare anche la relazione universale di partenza
si può eseguire `python extract_universal.py`.

Altri script utili:

```bash
python taxonomy_noise.py       # self-test dell'operatore di rumore tassonomico
python fabricator_omop.py      # genera una singola coppia source/target con ground truth
```
