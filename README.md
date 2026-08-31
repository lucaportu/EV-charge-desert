# EV Charge Desert

Dove, in Italia, la disponibilità di colonnine di ricarica pubbliche è più lontana
dal bisogno reale della popolazione. Unità di analisi: la sezione di censimento
ISTAT 2011 (402.678 poligoni).

Project Work — Big Data Processing & Data Engineering
Fasanelli S. · La Vacca G. · Portugalli L. · Roscini R.

Risultati e conclusioni: **`PROGETTO_presentazione.pdf`**. Questo repository
contiene il codice e i dati necessari per rieseguirlo.

**L'indicatore.** `GAP_i = rank%(Domanda_i) − rank%(Offerta_i)`, compreso fra −1
(sovraservita) e +1 (deserto). Soglia di criticità 0,4287 (metodo del gomito),
nelle slide arrotondata a 0,429.

---

## Prima cosa da fare, una volta sola

Il codice nasce da tre cartelle di lavoro separate e usava tre convenzioni di
percorso incompatibili più alcuni percorsi assoluti Windows: così com'è, un
clone pulito non parte. La correzione è automatica:

```bash
git clone <url-del-repository> && cd <repository>
git lfs install && git lfs pull               # i file in data/ sono su Git LFS
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/applica_correzioni.py            # anteprima, non scrive nulla
python tools/applica_correzioni.py --scrivi   # applica
```

> Senza `git lfs pull` i file in `data/` restano puntatori di ~130 byte e ogni
> lettura fallisce con un errore di formato: se `ls -l data/` mostra file di
> poche centinaia di byte invece dei MB dichiarati sotto, manca questo passo.

Lo script unifica tutti i percorsi su `src/paths.py`, toglie i percorsi assoluti
e l'indirizzo email personale rimasto nello User-Agent Overpass. Non riscrive un
file alla cieca: verifica che il testo atteso sia presente, salta i file già
corretti e, se il risultato non compila, lascia l'originale intatto e lo segnala.
Con `--backup` tiene una copia `.orig` di ogni file toccato.

> Se il repository è già stato corretto (`git log` mostra il commit relativo),
> questo passo si può saltare: lo script lo rileva da solo e non fa nulla.

---

## Struttura

| Cartella | Contenuto |
| --- | --- |
| `src/paths.py` | **unica** definizione dei percorsi del progetto |
| `src/01_pipeline_nazionale/` | 5 script: download fonti, offerta per sezione, merge |
| `src/02_siting_milano/` | 11 script `00`→`10`: traffico, POI, siting, validazione |
| `src/03_correzione_v2_motorizzazione/` | 3 script: correzione hub di immatricolazione |
| `notebooks/` | 15 notebook: domanda, IDI, GAP score, risultati, cartografia |
| `data/` | dataset di input versionati (letti, mai sovrascritti) |
| `config/` | parametri e lookup (letti, mai sovrascritti) |
| `output/` | **tutto** ciò che la pipeline produce — ignorata da git |
| `tools/` | script di manutenzione una tantum |
| `.github/workflows/` | automazione della campagna traffico |

Convenzione unica dopo la correzione: si legge da `data/` e `config/`, si scrive
sempre in `output/` — figure comprese (`output/grafici/`,
`output/grafici di validazione/`, `output/mappe_v2/`). Gli step che consumano un file lo cercano prima in
`output/` (versione appena rigenerata) e poi in `data/` (copia versionata), così
si può partire da un punto qualsiasi della pipeline senza rieseguire tutto ciò
che sta a monte.

---

## Ambiente

- **Python ≥ 3.9** (serve `zoneinfo`). Testato su 3.11, la versione usata anche
  da GitHub Actions.
- `pip install -r requirements.txt`.
- **`shapely>=2.0` è un requisito stretto**, non una preferenza:
  `04_assegna_colonnine_sezioni.py` usa `STRtree.query(..., predicate=...)` in
  forma bulk e `STRtree.query_nearest()`, API che in shapely 1.x non esistono.
- I file in `data/` superano la soglia di warning di GitHub (50 MB). Prima del
  primo push, una volta sola:
  ```bash
  git lfs install
  git lfs track "data/*.csv" "data/*.parquet" "data/*.geojson"
  ```
  I pattern sono già in `.gitattributes`.

### Variabili d'ambiente

| Variabile | Serve a | Quando |
| --- | --- | --- |
| `TOMTOM_API_KEY` | chiave TomTom | campagna traffico (`02`). Su GitHub Actions è un *secret*; in locale, in alternativa, si scrive la chiave in `tomtom_key.txt` nella radice — è coperto da `.gitignore` |
| `OVERPASS_CONTACT` | recapito nello User-Agent | scraping POI (`03`). Overpass chiede un contatto raggiungibile: senza, la richiesta può essere limitata |
| `EV_GAP_PARQUET` | percorso di `sezioni_gap_score_DEFINITIVO.parquet` | se si tiene il file da 593 MB fuori dal repository |
| `EV_DOMANDA_SEZIONE_CSV` | percorso della domanda per sezione | vedi "Dati NON inclusi" |
| `EV_CAMPAGNA_INIZIO` | data di inizio campagna traffico (`YYYY-MM-DD`) | per rieseguire la campagna in una settimana diversa da quella originale |
| `EV_INDICATORI_ISTAT_DIR` | cartella dei 20 CSV di indicatori censuari ISTAT (`R01_indicatori_2011_sezioni.csv` …) | notebook `01_sezioni_censimento.ipynb`; senza, li cerca in `output/indicatori_istat_2011/` |

---

## Ordine di esecuzione

### 1 · Pipeline nazionale

| # | Eseguire | Legge | Produce |
| --- | --- | --- | --- |
| 1 | `src/01_pipeline_nazionale/01_scarica_basi_territoriali_2011.py` | ISTAT (web) | 20 ZIP di confini in `output/` |
| 2 | `src/01_pipeline_nazionale/02_unisci_basi_territoriali_sezioni.py` | ZIP + `data/0_sezioni_censimento_2011_ridotto.csv` | `sezioni_censimento_2011_con_geometria.parquet` |
| 3 | `src/01_pipeline_nazionale/03_scarica_parco_2025_ACI_OPV.py` | ACI OPV (web) | `config/parco_circolante_2025_ACI_OPV_raw.json` |
| 4 | `notebooks/02_parco_auto.ipynb` | JSON ACI | `domanda_ricarica_2025_per_provincia.csv` |
| 5 | `notebooks/04_correzione_flotte_aci.ipynb` | parco ACI/MIT 2019 | `quota_flotte_ev_2019_per_provincia.json` |
| 6 | `notebooks/03_colonnine_pun.ipynb` | PUN (web) | `pun_colonnine_pulito.csv` |
| 7 | `src/01_pipeline_nazionale/04_assegna_colonnine_sezioni.py` | parquet sezioni + `pun_colonnine_pulito.csv` | `offerta_colonnine_per_sezione.parquet` |
| 8 | `notebooks/05` `06` `07` (IDI) | parquet sezioni | `domanda_ricarica_2025_per_sezione_IDI3_beta050.csv` |
| 9 | `src/01_pipeline_nazionale/05_merge_auto_colonnine_geo.py` | i tre output sopra | `sezioni_offerta_domanda_merged.parquet` |
| 10 | `notebooks/08_gap_score_DEFINITIVO.ipynb` | parquet merged + quote flotte | `sezioni_gap_score_DEFINITIVO.parquet` |

> **Passo 10.** Il notebook `08_gap_score_DEFINITIVO.ipynb` cercava un file
> chiamato `sezioni_gap_score.parquet`, cioè il parquet del passo 9
> (`sezioni_offerta_domanda_merged.parquet`) con un altro nome, e andava
> rinominato a mano. Ora la prima cella accetta entrambi i nomi e li cerca in
> `output/` e poi in `data/`: **la rinomina manuale non serve più**.

Lo step 3 usa Selenium: `opv.aci.it` è una dashboard Pentaho/CDF senza endpoint
scaricabile, i dati si leggono dallo stato interno del componente. Se ACI
aggiorna la dashboard i selettori nel docstring dello script vanno adattati.

### 2 · Lettura dei risultati

| Eseguire | Produce |
| --- | --- |
| `notebooks/09_Ranking_Sezioni_Critiche_GAP_Score.ipynb` | soglia del gomito |
| `notebooks/10_Mediana_GAP_Score_per_Provincia.ipynb` | classifica delle province |
| `notebooks/11_Simulazione_Impatto_*.ipynb` | scenari da 0 a 7 nuove colonnine |
| `notebooks/12_validazione_ev_charge_desert.ipynb` | controlli di coerenza |

### 3 · Siting, provincia di Milano

`src/02_siting_milano/`, in ordine da `00` a `10`.

Lo step `02_monitoraggio_traffico_tile.py` è una campagna di 48 ore su TomTom
che gira da sola su GitHub Actions (`.github/workflows/`, avviata a mano con
*Run workflow* e ripetuta da un trigger esterno cron-job.org): serve il secret
`TOMTOM_API_KEY`. **I due giorni già raccolti sono in `data/`, quindi si può
partire direttamente dallo step `03`.** Per rieseguire la campagna in una
settimana diversa si passa `EV_CAMPAGNA_INIZIO`: senza, lo script esce subito
perché la finestra originale (3–5 agosto 2026) è chiusa.

### 4 · Correzione v2 e cartografia

`src/03_correzione_v2_motorizzazione/01` → `02` → `03`, poi i notebook `13` `14` `15`.

---

## Dati inclusi

| File in `data/` | Serve a |
| --- | --- |
| `0_sezioni_censimento_2011_ridotto.csv` (57 MB) | passo 2 — indicatori censuari |
| `pun_colonnine_pulito.csv` | passo 7 — registro colonnine |
| `offerta_colonnine_per_sezione.parquet` | passo 9 |
| `domanda_ricarica_2025_per_provincia.csv` | correzione v2, script `01` |
| `domanda_provincia_v2_CORRETTA.csv` | correzione v2, script `02` |
| `sezioni_target_validazione.geojson` | siting, script `01` `03` `05` `06` `09` `10` |
| `tile_necessari.csv`, `sezione_tile.csv` | siting, script `02` |
| `traffico_provincia_2026-08-03.parquet`, `…-08-04.parquet` | siting, script `06` `09` |
| `candidati_siting_provincia.csv` | siting, script `07` `09` `10` |
| `gap_score_definitivo.csv` | notebook dei risultati |

| File in `config/` | Serve a |
| --- | --- |
| `parco_circolante_2025_ACI_OPV_raw.json` | passo 4, correzione v2 |
| `quota_flotte_ev_2019_per_provincia.json` | passo 10, correzione v2 |

Gli output finali (classifica provinciale, quante colonnine servono, validazione
della controprova, mappe) non sono versionati: si rigenerano in `output/`
eseguendo la pipeline.

## Dati NON inclusi

### Troppo grandi per GitHub (limite 100 MB per file)

`sezioni_censimento_2011_con_geometria.parquet` (552 MB) ·
`sezioni_offerta_domanda_merged.parquet` (574 MB) ·
`sezioni_gap_score_DEFINITIVO.parquet` (593 MB) · `sezioni_gap_v2.parquet` (605 MB)

Sono **derivati**, non fonti: si rigenerano rispettivamente ai passi 2, 9, 10 e
con `src/03_correzione_v2_motorizzazione/02_sezioni_e_gap_v2.py`. Chi ne ha già
una copia può puntarci senza rimetterla nel repository:

```bash
EV_GAP_PARQUET=/percorso/a/sezioni_gap_score_DEFINITIVO.parquet \
  python src/02_siting_milano/05_quante_colonnine.py
```

### Rigenerabile

La cache `output/overpass_raw_poi/` (≈968 file JSON, uno per sezione), prodotta
da `03_scarico_poi_overpass.py` e letta da `04` `06` `09`. Costa circa 35 minuti
(968 query con 2 s di pausa di cortesia verso il server pubblico Overpass) ed è
incrementale: rilanciando lo script si riprende da dove si era interrotto.

### Assenti anche dall'archivio di progetto

Vanno recuperati prima di eseguire gli step che li usano.

| File | Serve a | Come ottenerlo |
| --- | --- | --- |
| `domanda_ricarica_2025_per_sezione_IDI3_beta050.csv` | passo 9 (merge) | È l'output dei notebook `05` `06` `07`: rieseguirli produce il file. Sull'archivio di progetto esistono due varianti (`…_IDI.csv`, `…_beta050_CORRETTA.csv`): lo script le accetta entrambe, oppure si indica il file con `EV_DOMANDA_SEZIONE_CSV=/percorso/file.csv` |
| `province_geom.parquet` | mappe: `03_mappe_identiche_v2.py`, notebook `13` | Confini provinciali ISTAT, dissolti per `CODPRO` a partire dalle basi territoriali scaricate al passo 1 |
| `colonnine_rimosse_controprova.csv` | siting: script `07` e `10` | Prodotto dalla selezione delle sezioni target, **script mai versionato**. Senza, `07` e `10` escono con un messaggio e la controprova quantitativa non è calcolabile: è l'unico ramo della pipeline che resta non riproducibile |
| `04_correzione_v3_composizione.py` | terza correzione | Mai versionato |
| I 20 CSV di indicatori censuari ISTAT per regione (`R01_indicatori_2011_sezioni.csv` …) | notebook `01_sezioni_censimento.ipynb` | Download manuale dal portale ISTAT (nessuno script lo automatizza). Vanno messi in `output/indicatori_istat_2011/` o indicati con `EV_INDICATORI_ISTAT_DIR`. Il derivato che alimenta la pipeline (`data/0_sezioni_censimento_2011_ridotto.csv`) è comunque già versionato |

---

## Note di merito

- **Sistema di riferimento.** Le geometrie sono in EPSG:32632 (UTM 32N, metri),
  non in gradi: tutte le distanze del progetto (buffer 500 m, decadimento 300 m)
  lo richiedono. Riproiettare esplicitamente prima di qualunque operazione in
  lon/lat.
- **Non rinominare** `05_quante_colonnine.py` e `06_candidati_siting_provincia.py`:
  `09_grafici_presentazione.py` li importa per nome file.
- **Tre generazioni di mappe.** I notebook `13` `14` `15` disegnano le stesse
  figure su versioni diverse della correzione della domanda e danno due valori
  diversi per la Valle d'Aosta. Il `13` è quello che corrisponde alle mappe
  delle slide 12 e 14.
- **Sezioni senza dati.** Le ~35.815 sezioni non residenziali restano a NaN, mai
  a zero: la mappa deve rappresentare il territorio come superficie continua, e
  "nessun dato" è diverso da "nessuna offerta".

---

## Fonti dei dati

| Fonte | Licenza | Link |
| --- | --- | --- |
| ISTAT — Basi territoriali e variabili censuarie 2011 | CC BY 4.0 | <https://www.istat.it/notizia/basi-territoriali-e-variabili-censuarie/> |
| ACI — Open Parco Veicoli 2025 | termini ACI | <http://opv.aci.it/WEBDMCircolante/> |
| ACI/MIT — composizione d'uso del parco 2019 | termini ACI | <https://www.aci.it/laci/studi-e-ricerche/dati-e-statistiche.html> |
| PUN — Piattaforma Unica Nazionale (MASE) | termini MASE | <https://www.piattaformaunicanazionale.it/> |
| TomTom Traffic Flow (Vector Tile) | TomTom Developer | <https://developer.tomtom.com/traffic-api/documentation/traffic-flow/vector-flow-tiles> |
| OpenStreetMap / Overpass API | **ODbL 1.0** | <https://overpass-api.de/> |
| UNRAE (quota di ibride plug-in) | termini UNRAE | <https://unrae.it/dati-statistici> |

I dati derivati che incorporano OpenStreetMap ricadono sotto **ODbL 1.0** e
richiedono l'attribuzione «© OpenStreetMap contributors».

## Licenza

Codice: **MIT** (vedi `LICENSE`). I dati ridistribuiti in `data/` e `config/`
restano soggetti ai termini delle rispettive fonti, elencati sopra e ripresi in
coda al file `LICENSE`.
