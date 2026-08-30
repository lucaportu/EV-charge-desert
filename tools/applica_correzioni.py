#!/usr/bin/env python3
"""
Applica le correzioni dell'audit agli script e ai notebook del repository.
=========================================================================

Va eseguito UNA VOLTA, dalla radice del repository, prima del primo push:

    python tools/applica_correzioni.py            # anteprima, non scrive nulla
    python tools/applica_correzioni.py --scrivi   # applica davvero

Cosa fa, file per file:

 1. Rimuove i percorsi assoluti Windows
    (C:\\Users\\...\\Contesto lavoro di gruppo ETL e Progetto4-Master-...)
    e li sostituisce con percorsi risolti a partire dalla radice del
    repository.

 2. Unifica le tre convenzioni di percorso incompatibili che convivevano nel
    codice (BASE_DIR = src/, CARTELLA_SCRIPT = cartella dello script,
    DATI = src/) su un'unica sorgente: `src/paths.py`.
       data/    input versionati       (letti, mai sovrascritti)
       config/  parametri e lookup     (letti, mai sovrascritti)
       output/  tutto cio' che si produce (ignorato da git)

 3. Corregge i nomi/posizioni sbagliati, in particolare
    `dati/dati/sezioni_censimento_2011_ridotto.csv` ->
    `data/0_sezioni_censimento_2011_ridotto.csv`.

 4. Toglie l'indirizzo email personale dallo User-Agent Overpass, che passa
    alla variabile d'ambiente OVERPASS_CONTACT.

 5. Sposta il file locale della chiave TomTom sulla radice del repository,
    dove il pattern `**/tomtom_key.txt` del .gitignore lo copre davvero.

Sicurezza: lo script NON riscrive un file "alla cieca". Per ogni sostituzione
verifica che il testo atteso sia presente; se non lo trova lo segnala e lascia
il file invariato. E' inoltre idempotente: un file gia' corretto viene saltato.
Con --backup salva accanto a ogni file toccato una copia .orig.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# Dove vive ciascun file: tutto quello che non e' elencato qui e' un OUTPUT
# della pipeline e finisce in output/.
# --------------------------------------------------------------------------
INPUT_VERSIONATI = {
    "sezioni_target_validazione.geojson",
    "tile_necessari.csv",
    "sezione_tile.csv",
    "candidati_siting_provincia.csv",
    "pun_colonnine_pulito.csv",
    "0_sezioni_censimento_2011_ridotto.csv",
    "domanda_ricarica_2025_per_provincia.csv",
    "domanda_provincia_v2_CORRETTA.csv",
    "colonnine_rimosse_controprova.csv",
    "province_geom.parquet",
    "gap_score_definitivo.csv",
}
CONFIG = {
    "parco_circolante_2025_ACI_OPV_raw.json",
    "quota_flotte_ev_2019_per_provincia.json",
}
# Prodotti dalla pipeline ma anche presenti come copia versionata in data/:
# si cercano prima in output/ (rigenerati) e poi in data/.
DOPPIA_SEDE = {
    "offerta_colonnine_per_sezione.parquet",
    "sezioni_censimento_2011_con_geometria.parquet",
    "candidati_siting_provincia.csv",
    "domanda_provincia_v2_CORRETTA.csv",
}
# Il CSV degli indicatori censuari e' versionato con un prefisso che il codice
# non usava.
RINOMINATI = {
    "sezioni_censimento_2011_ridotto.csv": "0_sezioni_censimento_2011_ridotto.csv",
}

BOOTSTRAP = (
    "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n"
    "from paths import (CONFIG_DIR, DATA_DIR, OUTPUT_DIR, OVERPASS_CACHE_DIR,\n"
    "                   TOMTOM_KEY_FILE, assicura, gap_score_definitivo, manca, trova)\n"
)

PATH_ASSOLUTO = re.compile(
    r'^[A-Z_]+ = Path\(r"C:\\Users\\[^"]*"\)\n', re.MULTILINE
)
RIF_PROGETTO = re.compile(r"CARTELLA_PROGETTO_PRINCIPALE\s*/\s*")
RIF_SCRIPT = re.compile(r"CARTELLA_SCRIPT\s*/\s*")
RIF_BASE = re.compile(r"BASE_DIR\s*/\s*")
RIF_DATI = re.compile(r"\bDATI\s*/\s*")


# Costanti con una destinazione fissa, indipendente dal nome del file.
FISSE = {
    "istat_basi_territoriali_2011": "ISTAT_ZIP_DIR",
    "overpass_raw_poi": "OVERPASS_CACHE_DIR",
    "tomtom_key.txt": "TOMTOM_KEY_FILE",
    "sezioni_gap_score_DEFINITIVO.parquet": "gap_score_definitivo()",
}

# Radici di percorso usate dal codice originale, tutte da sostituire.
RADICI = r"(?:CARTELLA_PROGETTO_PRINCIPALE|CARTELLA_SCRIPT|REPO_ROOT|BASE_DIR|DATI|QUI)"

ASSEGNAZIONE = re.compile(
    r"^(?P<lhs>[A-Z_][A-Z0-9_]*) = " + RADICI + r"\s*/\s*(?P<resto>.+?)$",
    re.MULTILINE,
)
NOMI_NEL_RESTO = re.compile(r'"([^"]+)"')


def destinazione(lhs: str, nome: str) -> str:
    """Espressione Python che risolve `nome`, tenendo conto del ruolo.

    Il nome della costante dice se il file e' letto o scritto: `OUT_*` e
    `OUTPUT*` sono cio' che lo script PRODUCE (va in output/), `IN_*` e' cio'
    che CONSUMA (si cerca in output/ e poi in data/). Senza questa distinzione
    un file come tile_necessari.csv, che e' output dello step 01 e input dello
    step 02, finirebbe risolto allo stesso modo in entrambi.
    """
    nome = RINOMINATI.get(nome, nome)
    if lhs in ("OUTPUT_DIR", "DATA_DIR", "CONFIG_DIR"):
        # ridefinire un nome importato da paths lo ombreggerebbe: la
        # sottocartella dedicata non serve piu', tutto va in output/
        return "OUTPUT_DIR"
    if nome in FISSE:
        return FISSE[nome]
    if nome in CONFIG:
        return f'CONFIG_DIR / "{nome}"'
    if lhs.startswith("OUT"):
        return f'OUTPUT_DIR / "{nome}"'
    if lhs.startswith("IN_") or nome in INPUT_VERSIONATI or nome in DOPPIA_SEDE:
        return f'trova("{nome}")'
    return f'OUTPUT_DIR / "{nome}"'


def riscrivi_riferimenti(testo: str) -> tuple[str, int]:
    """Sostituisce <RADICE> / "nome" con la destinazione corretta."""
    n = 0

    def sostituisci(match: re.Match) -> str:
        nonlocal n
        lhs = match.group("lhs")
        resto = match.group("resto")
        nomi = NOMI_NEL_RESTO.findall(resto)
        if not nomi:
            return match.group(0)
        # forme a piu' livelli (DATI / "parco auto ACI" / "file.json"):
        # conta solo il segmento finale, che e' il file vero
        commento = ""
        if "#" in resto:
            resto_senza, _, coda = resto.partition("#")
            if resto_senza.count('"') % 2 == 0:
                commento = "  #" + coda
        n += 1
        return f"{lhs} = {destinazione(lhs, nomi[-1])}{commento}"

    testo = ASSEGNAZIONE.sub(sostituisci, testo)

    # f-string: return CARTELLA_SCRIPT / f"traffico_provincia_{...}.parquet"
    def sostituisci_fstring(match: re.Match) -> str:
        nonlocal n
        n += 1
        prefisso = match.group("prefisso")
        corpo = match.group("corpo")
        radice = "DATA_DIR" if "traffico_provincia" in corpo else "OUTPUT_DIR"
        return f'{prefisso}{radice} / f"{corpo}"'

    testo = re.sub(
        r"(?P<prefisso>return |= )" + RADICI + r'\s*/\s*f"(?P<corpo>[^"]+)"',
        sostituisci_fstring,
        testo,
    )

    # glob sulla cartella dello script
    testo = re.sub(
        RADICI + r'\.glob\("traffico_provincia_\*\.parquet"\)',
        'DATA_DIR.glob("traffico_provincia_*.parquet")',
        testo,
    )

    # stringa nuda usata come percorso di output (03_scarica_parco)
    testo = re.sub(
        r'^OUTPUT = "(?P<nome>[^"]+\.json)"$',
        lambda m: f'OUTPUT = {destinazione("OUTPUT", m.group("nome"))}',
        testo,
        flags=re.MULTILINE,
    )
    return testo, n


def inserisci_bootstrap(testo: str) -> str:
    """Aggiunge `import sys`, `from pathlib import Path` e l'import di paths."""
    if "from paths import" in testo:
        return testo
    if not re.search(r"^import sys$", testo, re.MULTILINE):
        testo = re.sub(
            r"^(import |from )", "import sys\n\\1", testo, count=1, flags=re.MULTILINE
        )
    if not re.search(r"^from pathlib import Path$", testo, re.MULTILINE):
        testo = re.sub(
            r"^import sys$", "import sys\nfrom pathlib import Path", testo,
            count=1, flags=re.MULTILINE,
        )
    # inserisce il bootstrap dopo l'ultimo import di primo livello
    righe = testo.split("\n")
    ultimo = 0
    for i, riga in enumerate(righe):
        if re.match(r"^(import |from )\S", riga):
            ultimo = i
    righe.insert(ultimo + 1, "\n" + BOOTSTRAP)
    return "\n".join(righe)


def pulisci_definizioni_morte(testo: str) -> str:
    """Toglie le costanti di percorso ormai inutilizzate."""
    testo = PATH_ASSOLUTO.sub("", testo)
    testo = re.sub(r"^REPO_ROOT = BASE_DIR\.parent\n", "", testo, flags=re.MULTILINE)
    testo = re.sub(r"^DATI = QUI\.parent[^\n]*\n", "", testo, flags=re.MULTILINE)
    for nome in ("CARTELLA_SCRIPT", "BASE_DIR", "REPO_ROOT", "QUI", "DATI"):
        # rimuove la definizione solo se il nome non e' piu' usato altrove
        definizione = re.compile(
            rf"^{nome} = Path\(__file__\)\.resolve\(\)\.parent(\.parent)?"
            r"(\s*#[^\n]*)?\n",
            re.MULTILINE,
        )
        senza = definizione.sub("", testo)
        if senza != testo and not re.search(rf"\b{nome}\b", senza):
            testo = senza
    testo = re.sub(r"^DATI = QUI\.parent[^\n]*\n", "", testo, flags=re.MULTILINE)
    testo = re.sub(r"^REPO_ROOT = BASE_DIR\.parent\n", "", testo, flags=re.MULTILINE)
    return testo


# --------------------------------------------------------------------------
# Correzioni puntuali, oltre alla riscrittura dei percorsi
# --------------------------------------------------------------------------
PUNTUALI: dict[str, list[tuple[str, str]]] = {
    "src/02_siting_milano/03_scarico_poi_overpass.py": [
        (
            '"User-Agent": "ProgettoEVChargeDesert/1.0 '
            '(progetto universitario Unimib; contatto nome.cognome@campus.unimib.it)"',
            '"User-Agent": (\n'
            '        "ProgettoEVChargeDesert/1.0 (progetto universitario Unimib"\n'
            '        + (f"; contatto {CONTATTO}" if CONTATTO else "")\n'
            '        + ")"\n'
            "    )",
        ),
        (
            "OVERPASS_URL = \"https://overpass-api.de/api/interpreter\"\n",
            "OVERPASS_URL = \"https://overpass-api.de/api/interpreter\"\n\n"
            "# Overpass chiede un contatto nello User-Agent per poter segnalare un uso\n"
            "# anomalo. Va indicato un recapito RAGGIUNGIBILE, impostato via ambiente,\n"
            "# cosi' nessun indirizzo personale resta scritto nel repository pubblico:\n"
            '#     export OVERPASS_CONTACT="nome.cognome@campus.unimib.it"\n'
            'CONTATTO = os.environ.get("OVERPASS_CONTACT", "").strip()\n',
        ),
        ("import json\nimport time\n", "import json\nimport os\nimport time\n"),
    ],
    "src/02_siting_milano/02_monitoraggio_traffico_tile.py": [
        (
            "  2. altrimenti SCRIPT/tomtom_key.txt (uso locale).",
            "  2. altrimenti tomtom_key.txt nella radice del repository (uso locale,\n"
            "     ignorato da git tramite il pattern **/tomtom_key.txt).",
        ),
        (
            "    return KEY_PATH.read_text(encoding=\"utf-8\").strip()",
            "    if not KEY_PATH.exists():\n"
            "        raise SystemExit(\n"
            '            "Chiave API TomTom non trovata.\\n"\n'
            '            "  Su GitHub Actions: secret TOMTOM_API_KEY del repository.\\n"\n'
            '            f"  In locale: scrivere la chiave in {KEY_PATH}\\n"\n'
            '            "  (il file e\' ignorato da git tramite **/tomtom_key.txt)."\n'
            "        )\n"
            "    return KEY_PATH.read_text(encoding=\"utf-8\").strip()",
        ),
        (
            'CAMPAGNA_INIZIO = datetime(2026, 8, 3, 0, 0, tzinfo=FUSO_ITALIA)',
            "# Data di inizio PARAMETRIZZABILE: con la data fissa nel codice lo script\n"
            "# oggi esce sempre senza fare nulla (\"campagna terminata\"), quindi la\n"
            "# campagna non sarebbe ripetibile. Per rieseguirla si indica un nuovo\n"
            "# lunedi':  EV_CAMPAGNA_INIZIO=2026-09-07 python ...\n"
            "def _campagna_inizio():\n"
            '    giorno = os.environ.get("EV_CAMPAGNA_INIZIO", "2026-08-03").strip()\n'
            "    try:\n"
            '        a, m, g = (int(x) for x in giorno.split("-"))\n'
            "    except ValueError:\n"
            '        raise SystemExit(f"EV_CAMPAGNA_INIZIO non valida: {giorno!r} '
            '(formato YYYY-MM-DD)")\n'
            "    return datetime(a, m, g, 0, 0, tzinfo=FUSO_ITALIA)\n"
            "\n"
            "\nCAMPAGNA_INIZIO = _campagna_inizio()",
        ),
        (
            "CAMPAGNA_DURATA_ORE = 48",
            'CAMPAGNA_DURATA_ORE = int(os.environ.get("EV_CAMPAGNA_ORE", "48"))',
        ),
        (
            'return OUTPUT_DIR / f"traffico_provincia_{data.isoformat()}.parquet"',
            "# i parquet giornalieri restano in data/: sono dati raccolti (non\n"
            "    # rigenerabili a posteriori) e il workflow li committa a fine run\n"
            '    return DATA_DIR / f"traffico_provincia_{data.isoformat()}.parquet"',
        ),
    ],
    "src/02_siting_milano/07_validazione_controprova.py": [
        (
            "        raise FileNotFoundError(f\"Manca {IN_COLONNINE_RIMOSSE} "
            "(prodotto da seleziona_sezioni_target_validazione.py)\")",
            "        # Uscita pulita invece di un'eccezione: il file non e' versionato\n"
            "        # (vedi 'Dati NON inclusi' nel README), quindi la sua assenza e'\n"
            "        # una condizione prevista, non un errore di programmazione.\n"
            "        print(\n"
            "            f\"{IN_COLONNINE_RIMOSSE.name} non disponibile: la controprova\\n\"\n"
            "            \"quantitativa non puo' essere calcolata. Il file elenca le\\n\"\n"
            "            \"colonnine reali rimosse nella simulazione ed e' prodotto dalla\\n\"\n"
            "            \"selezione delle sezioni target (script non versionato).\"\n"
            "        )\n"
            "        return",
        ),
    ],
    "src/02_siting_milano/06_candidati_siting_provincia.py": [
        (
            'file_giorni = sorted(CARTELLA_SCRIPT.glob("traffico_provincia_*.parquet"))',
            'file_giorni = sorted(DATA_DIR.glob("traffico_provincia_*.parquet")) + \\\n'
            '        sorted(OUTPUT_DIR.glob("traffico_provincia_*.parquet"))',
        ),
    ],
    "src/02_siting_milano/09_grafici_presentazione.py": [
        (
            'file_giorni = sorted(CARTELLA_SCRIPT.glob("traffico_provincia_*.parquet"))',
            'file_giorni = sorted(DATA_DIR.glob("traffico_provincia_*.parquet")) + \\\n'
            '        sorted(OUTPUT_DIR.glob("traffico_provincia_*.parquet"))',
        ),
        (
            'm05 = _importa(CARTELLA_SCRIPT / "05_quante_colonnine.py")',
            'm05 = _importa(Path(__file__).resolve().parent / "05_quante_colonnine.py")',
        ),
        (
            'm06 = _importa(CARTELLA_SCRIPT / "06_candidati_siting_provincia.py")',
            'm06 = _importa(Path(__file__).resolve().parent / '
            '"06_candidati_siting_provincia.py")',
        ),
    ],
    "src/02_siting_milano/08_genera_metodologia_pdf.py": [
        (
            "github.com/sfasanelli-svg/Progetto4-Master",
            "questo repository",
        ),
    ],
    "src/01_pipeline_nazionale/05_merge_auto_colonnine_geo.py": [
        (
            'DOMANDA_CSV = OUTPUT_DIR / "domanda_ricarica_2025_per_sezione_IDI3_beta050.csv"',
            "# La domanda per sezione (output dei notebook 05-06-07, passo 8) non e'\n"
            "# versionata: e' il file mancante che interrompeva la pipeline. Si accettano\n"
            "# anche i nomi alternativi presenti nell'archivio di progetto, e la variabile\n"
            "# EV_DOMANDA_SEZIONE_CSV permette di indicarne uno qualsiasi.\n"
            "_NOMI_DOMANDA = (\n"
            '    "domanda_ricarica_2025_per_sezione_IDI3_beta050.csv",\n'
            '    "domanda_ricarica_2025_per_sezione_IDI3_beta050_CORRETTA.csv",\n'
            '    "domanda_ricarica_2025_per_sezione_IDI.csv",\n'
            ")\n"
            "\n"
            "\n"
            "def _trova_domanda():\n"
            '    da_env = os.environ.get("EV_DOMANDA_SEZIONE_CSV")\n'
            "    if da_env:\n"
            "        return Path(da_env).expanduser()\n"
            "    for nome in _NOMI_DOMANDA:\n"
            "        for cartella in (OUTPUT_DIR, DATA_DIR):\n"
            "            if (cartella / nome).exists():\n"
            "                return cartella / nome\n"
            "    return OUTPUT_DIR / _NOMI_DOMANDA[0]\n"
            "\n"
            "\n"
            "DOMANDA_CSV = _trova_domanda()",
        ),
        ("import gc\n", "import gc\nimport os\n"),
    ],
}


def correggi_python(percorso: Path, scrivi: bool, backup: bool) -> str:
    testo = originale = percorso.read_text(encoding="utf-8")
    if "from paths import" in testo:
        return "gia' corretto"

    testo = testo.replace("\r\n", "\n")
    problemi = []
    for vecchio, nuovo in PUNTUALI.get(
        percorso.relative_to(REPO).as_posix(), []
    ):
        if vecchio in testo:
            testo = testo.replace(vecchio, nuovo, 1)
        else:
            # non blocca: alcune sostituzioni valgono solo dopo la riscrittura
            problemi.append(vecchio.splitlines()[0][:60])

    testo, n = riscrivi_riferimenti(testo)
    # seconda passata per le sostituzioni puntuali che agiscono su testo riscritto
    for vecchio, nuovo in PUNTUALI.get(
        percorso.relative_to(REPO).as_posix(), []
    ):
        if vecchio in testo:
            testo = testo.replace(vecchio, nuovo, 1)
            problemi = [p for p in problemi if not vecchio.startswith(p)]

    testo = re.sub(r"^OUTPUT_DIR = OUTPUT_DIR\n", "", testo, flags=re.MULTILINE)
    testo = pulisci_definizioni_morte(testo)
    testo = inserisci_bootstrap(testo)

    try:
        compile(testo, str(percorso), "exec")
    except SyntaxError as e:
        return f"ERRORE: il risultato non compila (riga {e.lineno}: {e.msg}) - non scritto"

    if scrivi:
        if backup:
            percorso.with_suffix(percorso.suffix + ".orig").write_text(
                originale, encoding="utf-8"
            )
        percorso.write_text(testo, encoding="utf-8")
    esito = f"{n} percorsi riscritti"
    if problemi:
        esito += f" | non trovati: {len(problemi)}"
    return esito


def correggi_notebook(percorso: Path, scrivi: bool, backup: bool) -> str:
    grezzo = originale = percorso.read_text(encoding="utf-8")
    # nel JSON grezzo il backslash e' raddoppiato: C:\\Users\\...
    if "C:\\\\Users" not in grezzo:
        return "nessun percorso assoluto"

    try:
        nb = json.loads(grezzo)
    except json.JSONDecodeError:
        return "ERRORE: JSON non valido - non toccato"

    sostituzioni = 0
    for cella in nb.get("cells", []):
        if cella.get("cell_type") != "code":
            continue
        nuove = []
        for riga in cella.get("source", []):
            # qui `riga` e' gia' de-escapizzata da json.loads: il percorso
            # compare con backslash singoli
            if "C:\\Users\\" in riga and "Path(" in riga:
                nuove.append(
                    "CARTELLA_PROGETTO = Path.cwd().parent / \"output\"  "
                    "# radice output del repository\n"
                )
                sostituzioni += 1
            else:
                nuove.append(riga)
        cella["source"] = nuove

    # rimuove i metadata Colab che contengono identificativi personali
    nb.get("metadata", {}).pop("colab", None)
    nb.get("metadata", {}).pop("widgets", None)

    if sostituzioni == 0:
        return "nessun percorso assoluto in celle di codice"
    if scrivi:
        if backup:
            percorso.with_suffix(".ipynb.orig").write_text(originale, encoding="utf-8")
        percorso.write_text(
            json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    return f"{sostituzioni} percorsi assoluti sostituiti"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scrivi", action="store_true", help="applica le modifiche")
    ap.add_argument("--backup", action="store_true", help="salva una copia .orig")
    args = ap.parse_args()

    if not (REPO / "src" / "paths.py").exists():
        print("src/paths.py non trovato: eseguire dalla radice del repository.")
        return 1

    print("ANTEPRIMA (nessuna modifica scritta)\n" if not args.scrivi else "APPLICO\n")
    errori = 0

    for percorso in sorted((REPO / "src").rglob("*.py")):
        if percorso.name == "paths.py":
            continue
        esito = correggi_python(percorso, args.scrivi, args.backup)
        errori += esito.startswith("ERRORE")
        print(f"  {percorso.relative_to(REPO)}: {esito}")

    cartella_nb = REPO / "notebooks"
    if cartella_nb.exists():
        print()
        for percorso in sorted(cartella_nb.glob("*.ipynb")):
            esito = correggi_notebook(percorso, args.scrivi, args.backup)
            errori += esito.startswith("ERRORE")
            print(f"  {percorso.relative_to(REPO)}: {esito}")

    print()
    if errori:
        print(f"{errori} file NON modificati per errore: vanno guardati a mano.")
    elif not args.scrivi:
        print("Tutto verificato. Rilanciare con --scrivi per applicare.")
    else:
        print("Fatto. Controllare `git diff` prima di committare.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
