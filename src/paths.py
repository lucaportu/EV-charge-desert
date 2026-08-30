"""
Percorsi centralizzati del repository EV Charge Desert.
=======================================================

Unico punto in cui e' definita la posizione di dati, configurazione e output.
Prima di questa modifica ogni gruppo di script usava una convenzione diversa
(tre radici relative incompatibili piu' un percorso assoluto Windows), e
nessuna delle quattro puntava alle cartelle `data/` e `config/` reali: il
repository non era eseguibile da un clone pulito.

Uso negli script (i file di `src/<gruppo>/` non sono un package, quindi si
aggiunge `src/` al sys.path prima dell'import):

    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from paths import DATA_DIR, OUTPUT_DIR, trova

Convenzione adottata in tutta la pipeline:

  - `data/`    input versionati nel repository (letti, mai sovrascritti)
  - `config/`  parametri e lookup (letti, mai sovrascritti)
  - `output/`  TUTTO cio' che la pipeline produce (ignorato da git)

Gli step intermedi scrivono quindi sempre in `output/`, e leggono con
`trova()`, che cerca prima in `output/` (risultato appena rigenerato) e poi
in `data/` (copia versionata). Cosi' si puo' partire da un punto qualsiasi
della pipeline senza dover rieseguire tutto quello che sta a monte.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SRC_DIR = REPO_ROOT / "src"
DATA_DIR = REPO_ROOT / "data"
CONFIG_DIR = REPO_ROOT / "config"
OUTPUT_DIR = REPO_ROOT / "output"

# sottocartelle di lavoro, tutte dentro output/ (ignorate da git)
ISTAT_ZIP_DIR = OUTPUT_DIR / "istat_basi_territoriali_2011"
OVERPASS_CACHE_DIR = OUTPUT_DIR / "overpass_raw_poi"
GRAFICI_DIR = OUTPUT_DIR / "grafici"
GRAFICI_VALIDAZIONE_DIR = OUTPUT_DIR / "grafici di validazione"
MAPPE_V2_DIR = OUTPUT_DIR / "mappe_v2"

# chiave TomTom per l'uso locale: fuori da src/, alla radice del repository, e
# coperta da `**/tomtom_key.txt` nel .gitignore. Su GitHub Actions si usa
# invece la variabile d'ambiente TOMTOM_API_KEY (secret del repository).
TOMTOM_KEY_FILE = REPO_ROOT / "tomtom_key.txt"


def assicura(cartella: Path) -> Path:
    """Crea la cartella se non esiste e la restituisce."""
    cartella.mkdir(parents=True, exist_ok=True)
    return cartella


def trova(nome: str, *cartelle: Path) -> Path:
    """Primo percorso esistente fra `cartelle`, altrimenti il primo candidato.

    Restituire comunque un percorso (anziche' sollevare) lascia al chiamante la
    scelta fra uscire con un messaggio esplicativo e fallire: e' la convenzione
    gia' usata in tutta la pipeline (vedi `06_candidati_siting_provincia.py`,
    che esce pulito quando la campagna traffico non ha ancora prodotto dati).
    """
    cartelle = cartelle or (OUTPUT_DIR, DATA_DIR)
    for cartella in cartelle:
        candidato = cartella / nome
        if candidato.exists():
            return candidato
    return cartelle[0] / nome


def gap_score_definitivo() -> Path:
    """Percorso di `sezioni_gap_score_DEFINITIVO.parquet` (~593 MB).

    Non e' versionato (limite GitHub di 100 MB per file): si rigenera con il
    passo 10 della pipeline (`notebooks/08_gap_score_DEFINITIVO.ipynb`).
    La variabile d'ambiente EV_GAP_PARQUET permette di puntare a una copia
    tenuta fuori dal repository senza modificare il codice.
    """
    da_env = os.environ.get("EV_GAP_PARQUET")
    if da_env:
        return Path(da_env).expanduser()
    return trova("sezioni_gap_score_DEFINITIVO.parquet", OUTPUT_DIR, DATA_DIR)


def manca(percorso: Path, prodotto_da: str) -> str:
    """Messaggio di errore uniforme per un input non ancora disponibile."""
    return (
        f"File non trovato: {percorso}\n"
        f"  Prodotto da: {prodotto_da}\n"
        f"  Vedi la sezione 'Dati NON inclusi' del README per come ottenerlo."
    )
