"""
Step 2 del progetto di validazione modello di siting (vector tiles sulle
sezioni target della provincia di Milano: 818 critiche + 150 di
controprova, 968 totali, 803 tile) - script principale.

Stessa logica di Progetto3-Master-VectorTiles/SCRIPT/02_monitoraggio_traffico_tile.py
(stesso endpoint, stesso fix del bug y_coord_down, stessa congestione = 1 -
traffic_level), con tre differenze dovute alla scala (968 sezioni, 803
tile invece di 50/63):

1. CADENZA ADATTIVA (5 minuti in punta, 30 fuori punta), non fissa.
   Cadenza fissa a 5 minuti su tutte le 48h costerebbe 803 x 12 x 30h
   (finestra 7-22) = oltre 300.000 chiamate: non sostenibile. Cadenza
   fissa piu' larga rientrerebbe ampiamente in quota ma sacrifica la
   risoluzione proprio dove serve di piu'. La cadenza adattiva (vedi
   FASCE_PUNTA_ORA_LOCALE, INTERVALLO_PUNTA_MINUTI/INTERVALLO_FUORI_PUNTA_MINUTI
   piu' sotto): 5 minuti nelle 2 fasce di punta (mattino/sera, ora locale
   italiana), dove il pattern da catturare e' concentrato, 30 minuti nel
   resto della finestra diurna. Il trigger esterno (cron-job.org) e'
   ristretto a 7-22 ora italiana (stessa finestra di Progetto3,
   "*/5 7-22 * * *"): le ore notturne sono escluse deliberatamente, non
   solo per risparmiare quota - la metrica usata ovunque nel progetto e'
   la CONGESTIONE MASSIMA per segmento, e di notte la circolazione e'
   scorrevole quasi ovunque, quindi quelle letture non risultano quasi mai
   il massimo di un segmento: il loro contributo informativo e'
   trascurabile, il taglio non peggiora la qualita' del dato. E' comunque
   la logica DENTRO lo script (funzione intervallo_corrente) a decidere,
   in base all'ora locale italiana corrente, se lasciar passare il
   tentativo (punta, 5 min) o scartarlo fino al prossimo bucket da 30
   minuti (fuori punta, ma dentro 7-22).

   NOTA SUL VALORE DI INTERVALLO_FUORI_PUNTA_MINUTI: partito a 30, alzato
   a 15 la sera del 02/08 (su richiesta esplicita, per piu' letture
   indipendenti = piu' robustezza, target ~87% quota), poi RIPORTATO a 30
   nel pomeriggio del 03/08 - vedi punto 6 per il perche'.

2. FINESTRA DI CAMPAGNA ESPLICITA (CAMPAGNA_INIZIO/CAMPAGNA_FINE piu'
   sotto): parte lunedi' 03/08/2026 00:00 ora italiana, finisce da sola
   dopo 48 ore (mercoledi' 00:00) - dati piu' verosimili di un lunedi'+
   martedi' "tipici" invece di un giorno scelto a caso (weekend, ponte).
   Il trigger esterno (cron-job.org) puo' restare attivo H24 fin da
   subito: fuori da questa finestra lo script esce senza fare alcuna
   chiamata, quindi accenderlo in anticipo o dimenticarsi di spegnerlo
   dopo non costa quota - a differenza di Progetto3, qui la campagna si
   autolimita.

3. OUTPUT IN PARQUET, PARTIZIONATO PER GIORNO, non un unico CSV in
   append. Motivo: un CSV che cresce all'infinito e viene ri-committato a
   ogni esecuzione, alla scala di questo progetto, arriverebbe a decine o
   centinaia di MB entro pochi giorni - GitHub rifiuta push di file
   singoli sopra i 100MB, l'automazione si romperebbe a meta' campagna. Un
   file Parquet compresso per giorno (traffico_provincia_AAAA-MM-GG.parquet)
   resta piccolo e non cresce mai oltre un giorno di dati: a ogni
   esecuzione il file del giorno corrente viene letto, concatenato con le
   nuove righe e riscritto (Parquet non supporta l'append nativo come il
   CSV, ma riscrivere un giorno di dati resta un'operazione da pochi
   secondi anche a cadenza fitta).

4. ASSEGNAZIONE FALLBACK VETTORIALE (sjoin_nearest), non un ciclo Python
   sezione per sezione. Con 50 sezioni un ciclo "per ogni sezione senza
   segmenti, calcola la distanza da OGNI segmento scaricato" era
   trascurabile; con centinaia di migliaia di segmenti per esecuzione (803
   tile) e cadenza fino a 5 minuti, sarebbe troppo lento - si usa l'indice
   spaziale di geopandas invece del ciclo esplicito.

5. DOWNLOAD DEI TILE IN PARALLELO (ThreadPoolExecutor), non sequenziale
   con pausa. CORREZIONE POST-AVVIO CAMPAGNA (03/08, verificata sul primo
   giorno reale): la versione sequenziale (0,3s di pausa + latenza reale)
   impiegava ~0,73s/tile misurati, quindi ~10 minuti per l'intero giro di
   803 tile - quasi il doppio dell'intervallo di 5 minuti tra un trigger e
   l'altro nelle fasce di punta, con conseguente accumulo di esecuzioni in
   coda ed esecuzioni che si contendevano il push git (~1 su 2 falliva o
   veniva annullata durante la prima fascia di punta della campagna). Un
   test diretto ha mostrato TomTom rispondere in ~0,13s a chiamata: non è
   un limite del server (a differenza dei server pubblici Overpass usati
   per i POI, qui la quota è dedicata alla singola chiave, non condivisa),
   quindi ha senso scaricare più tile insieme invece di uno alla volta.
   Aggiunta anche una SESSIONE HTTP CONDIVISA (requests.Session, con pool
   di connessioni dimensionato sul parallelismo): la sola parallelizzazione
   non bastava sul runner GitHub Actions (un run ha comunque impiegato
   311s), quasi certamente per l'overhead di un nuovo handshake TCP/TLS a
   ogni singola richiesta invece di riusare una connessione gia' aperta -
   overhead trascurabile su una rete a bassa latenza (trascurabile nei
   test locali) ma significativo dal runner. Con entrambi i fix attivi:
   da ~586s a 28-48s per esecuzione, verificato su piu' cicli consecutivi.

6. RIDUZIONE DEL FUORI-PUNTA DA 15 A 30 MINUTI PER MARTEDI' (03/08
   pomeriggio): conseguenza diretta dell'incidente del punto 5. Prima che
   i fix venissero applicati, la fascia di punta serale di lunedi' ha
   avuto ~1 esecuzione su 2 fallita o annullata (accumulo di esecuzioni in
   coda per un run che durava piu' dell'intervallo tra un trigger e
   l'altro) - le esecuzioni FALLITE consumano comunque la quota TomTom
   (la chiamata va a buon fine, e' il commit/push successivo a fallire),
   quindi lo spreco si somma al budget invece di sottrarsi: a meta'
   pomeriggio di lunedi' erano gia' state consumate ~113.000 chiamate,
   piu' dell'intera giornata "pulita" pianificata (86.724). Continuando a
   15 minuti fuori-punta anche martedi' il totale della campagna avrebbe
   superato la quota mensile (proiezione ~211.000, 105,6%) verso la fine
   di martedi' - il momento peggiore per sforare, a campagna quasi
   conclusa. Riportando il fuori-punta a 30 minuti (la punta resta 5
   minuti su entrambi i giorni: nessuna perdita sui dati che contano di
   piu') il totale proiettato scende a ~193.500 (96,8%), con margine.

API key TomTom:
  1. variabile d'ambiente TOMTOM_API_KEY (GitHub Actions, via secret);
  2. altrimenti tomtom_key.txt nella radice del repository (uso locale,
     ignorato da git tramite il pattern **/tomtom_key.txt).

Output: traffico_provincia_AAAA-MM-GG.parquet (uno per giorno). Colonne:
        timestamp_utc, SEZ2011, COMUNE, gap_score, road_type,
        traffic_road_coverage, congestione, lat, lon, assegnazione,
        distanza_m
"""

import sys
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import mapbox_vector_tile
import pandas as pd
import requests
from shapely.geometry import LineString, MultiLineString

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import DATA_DIR, TOMTOM_KEY_FILE, trova


IN_GEOJSON = trova("sezioni_target_validazione.geojson")
IN_TILE = trova("tile_necessari.csv")
KEY_PATH = TOMTOM_KEY_FILE

TOMTOM_TILE_URL = "https://api.tomtom.com/traffic/map/4/tile/flow/relative/{zoom}/{x}/{y}.pbf"
MAX_WORKER_PARALLELI = 20  # richieste concorrenti verso TomTom (vedi punto 5 sopra)
BUFFER_SEZIONE_METRI = 50

# Cadenza ADATTIVA, non fissa: 803 tile a 5 minuti fissi per 48h costerebbero
# 462.528 chiamate (231% della quota mensile TomTom, 200.000) - non
# sostenibile. A cadenza oraria fissa si rientra ampiamente in quota, ma si
# perde la risoluzione fine sui picchi di punta, che e' dove il pattern
# conta davvero (la soglia di robustezza del progetto, >= 5 letture, serve
# proprio a distinguere un pattern vero da un episodio isolato: per farlo
# bene servono PIU' picchi osservati, non un solo picco campionato fitto).
# Compromesso: 5 minuti nelle 2 fasce di punta (mattino/sera, dove la
# congestione da catturare e' concentrata), 30 minuti nel resto della
# finestra diurna (il trigger esterno e' comunque ristretto a 7-22, vedi
# workflow yml: le ore notturne sono escluse, la congestione MASSIMA che
# usiamo come metrica non e' quasi mai raggiunta di notte). Due mattine e
# due sere indipendenti a piena risoluzione su 48h. Il fuori-punta e'
# stato per qualche ora a 15 minuti (piu' letture = piu' robustezza), poi
# RIPORTATO a 30 il pomeriggio del 03/08 per compensare lo spreco di quota
# causato da un run troppo lento (vedi docstring in cima al file, punti 5
# e 6): a 15 minuti la proiezione totale campagna avrebbe superato la
# quota mensile (~105,6%), a 30 minuti resta sotto con margine (~96,8%).
#
# Le fasce sono in ora locale italiana (Europe/Rome, gestisce CEST/CET da
# solo via zoneinfo): il traffico di punta segue gli orari di lavoro locali,
# non l'orario UTC.
FASCE_PUNTA_ORA_LOCALE = [(7, 10), (17, 20)]  # [ora_inizio, ora_fine) coppie
INTERVALLO_PUNTA_MINUTI = 5
INTERVALLO_FUORI_PUNTA_MINUTI = 30
FUSO_ITALIA = ZoneInfo("Europe/Rome")

# FINESTRA DI CAMPAGNA: inizio fissato a lunedi' (dati piu' verosimili di un
# giorno feriale "tipico" - lunedi'+martedi' invece di un giorno scelto a
# caso, che potrebbe cadere di sabato/domenica o a ridosso di un ponte), fine
# automatica dopo CAMPAGNA_DURATA_ORE. Il trigger esterno (cron-job.org) puo'
# restare attivo H24 fin da subito: fuori da questa finestra lo script esce
# immediatamente senza fare alcuna chiamata TomTom (vedi main()), quindi
# accenderlo in anticipo non consuma quota. Idem al termine delle 48 ore: la
# raccolta si ferma da sola, non serve ricordarsi di disattivare il job.
# Data di inizio PARAMETRIZZABILE: con la data fissa nel codice lo script
# oggi esce sempre senza fare nulla ("campagna terminata"), quindi la
# campagna non sarebbe ripetibile. Per rieseguirla si indica un nuovo
# lunedi':  EV_CAMPAGNA_INIZIO=2026-09-07 python ...
def _campagna_inizio():
    giorno = os.environ.get("EV_CAMPAGNA_INIZIO", "2026-08-03").strip()
    try:
        a, m, g = (int(x) for x in giorno.split("-"))
    except ValueError:
        raise SystemExit(f"EV_CAMPAGNA_INIZIO non valida: {giorno!r} (formato YYYY-MM-DD)")
    return datetime(a, m, g, 0, 0, tzinfo=FUSO_ITALIA)


CAMPAGNA_INIZIO = _campagna_inizio()  # lunedi' 03/08/2026, 00:00 ora italiana
CAMPAGNA_DURATA_ORE = int(os.environ.get("EV_CAMPAGNA_ORE", "48"))
CAMPAGNA_FINE = CAMPAGNA_INIZIO + timedelta(hours=CAMPAGNA_DURATA_ORE)

CRS_WGS84 = "EPSG:4326"
CRS_UTM = "EPSG:32632"


def dentro_finestra_campagna(adesso_utc):
    return CAMPAGNA_INIZIO <= adesso_utc <= CAMPAGNA_FINE


def intervallo_corrente(adesso_utc):
    """Cadenza da applicare ADESSO: 5 minuti se l'ora locale italiana cade
    in una fascia di punta, 30 minuti altrimenti."""
    ora_locale = adesso_utc.astimezone(FUSO_ITALIA).hour
    in_punta = any(inizio <= ora_locale < fine for inizio, fine in FASCE_PUNTA_ORA_LOCALE)
    return INTERVALLO_PUNTA_MINUTI if in_punta else INTERVALLO_FUORI_PUNTA_MINUTI


def leggi_api_key():
    da_env = os.environ.get("TOMTOM_API_KEY")
    if da_env:
        return da_env.strip()
    if not KEY_PATH.exists():
        raise SystemExit(
            "Chiave API TomTom non trovata.\n"
            "  Su GitHub Actions: secret TOMTOM_API_KEY del repository.\n"
            f"  In locale: scrivere la chiave in {KEY_PATH}\n"
            "  (il file e' ignorato da git tramite **/tomtom_key.txt)."
        )
    return KEY_PATH.read_text(encoding="utf-8").strip()


def out_path_giorno(data):
    return DATA_DIR / f"traffico_provincia_{data.isoformat()}.parquet"


def bucket(dt, intervallo_minuti):
    """Chiave dell'intervallo temporale (data, ora, minuto arrotondato
    per difetto a multipli di intervallo_minuti) a cui appartiene dt."""
    minuto_arrotondato = (dt.minute // intervallo_minuti) * intervallo_minuti
    return (dt.date(), dt.hour, minuto_arrotondato)


def intervallo_gia_coperto(adesso, intervallo_minuti):
    """True se l'ultima riga del parquet del giorno corrente cade nello
    stesso intervallo temporale (bucket) di 'adesso'."""
    path = out_path_giorno(adesso.date())
    if not path.exists():
        return False
    df = pd.read_parquet(path, columns=["timestamp_utc"])
    if df.empty:
        return False
    ultimo_dt = datetime.fromisoformat(df["timestamp_utc"].iloc[-1])
    return bucket(ultimo_dt, intervallo_minuti) == bucket(adesso, intervallo_minuti)


def tile_px_to_lonlat(x_tile, y_tile, zoom, px, py, extent):
    n = 2 ** zoom
    lon = (x_tile + px / extent) / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y_tile + py / extent) / n)))
    lat = math.degrees(lat_rad)
    return lon, lat


def scarica_e_decodifica_tile(sessione, x, y, zoom, api_key, tentativi=3):
    for tentativo in range(1, tentativi + 1):
        r = sessione.get(TOMTOM_TILE_URL.format(zoom=zoom, x=x, y=y),
                          params={"key": api_key}, timeout=20)
        if r.status_code == 200:
            if not r.content:
                return []
            # y_coord_down=True: stesso fix di Progetto3-Master-VectorTiles, vedi
            # quel repository per la spiegazione completa del bug (doppio flip
            # verticale corretto usando questa opzione di mapbox_vector_tile.decode).
            return mapbox_vector_tile.decode(r.content, default_options={"y_coord_down": True})
        if r.status_code == 429:
            print("    rate limit (429), attendo 10s e riprovo...")
            time.sleep(10)
            continue
        print(f"    tentativo {tentativo}: HTTP {r.status_code} - {r.text[:200]}")
        time.sleep(3)
    return None


def estrai_segmenti_lonlat(tile_decodificato, x, y, zoom):
    """Ritorna una lista di dict {geometry (shapely, lon/lat), road_type,
    traffic_road_coverage, congestione} per tutti i segmenti del tile."""
    segmenti = []
    if not tile_decodificato:
        return segmenti

    for layer in tile_decodificato.values():
        extent = layer.get("extent", 4096)
        for feat in layer["features"]:
            props = feat["properties"]
            traffic_level = props.get("traffic_level")
            if traffic_level is None:
                continue
            geom = feat["geometry"]

            def converti_linea(coords_px):
                return [tile_px_to_lonlat(x, y, zoom, px, py, extent) for px, py in coords_px]

            if geom["type"] == "LineString":
                linea = LineString(converti_linea(geom["coordinates"]))
            elif geom["type"] == "MultiLineString":
                parti = [LineString(converti_linea(c)) for c in geom["coordinates"] if len(c) >= 2]
                if not parti:
                    continue
                linea = MultiLineString(parti) if len(parti) > 1 else parti[0]
            else:
                continue

            segmenti.append({
                "geometry": linea,
                "road_type": props.get("road_type"),
                "traffic_road_coverage": props.get("traffic_road_coverage"),
                "congestione": 1 - traffic_level,
            })
    return segmenti


def main(forza=False):
    ora_corrente = datetime.now(timezone.utc)

    if not forza and not dentro_finestra_campagna(ora_corrente):
        if ora_corrente < CAMPAGNA_INIZIO:
            print(f"Campagna non ancora iniziata (parte {CAMPAGNA_INIZIO.isoformat()}, "
                  f"adesso {ora_corrente.astimezone(FUSO_ITALIA).isoformat()}): nessuna chiamata TomTom, esco.")
        else:
            print(f"Campagna terminata (finita {CAMPAGNA_FINE.isoformat()}, "
                  f"adesso {ora_corrente.astimezone(FUSO_ITALIA).isoformat()}): nessuna chiamata TomTom, esco.")
        return

    intervallo_minuti = intervallo_corrente(ora_corrente)

    if not forza and intervallo_gia_coperto(ora_corrente, intervallo_minuti):
        print(f"Intervallo di {intervallo_minuti} minuti (cadenza "
              f"{'di punta' if intervallo_minuti == INTERVALLO_PUNTA_MINUTI else 'fuori punta'}) "
              f"gia' coperto da un'esecuzione precedente "
              f"({ora_corrente.isoformat(timespec='minutes')}): nessuna chiamata TomTom, esco.")
        return

    api_key = leggi_api_key()
    timestamp_utc = ora_corrente.isoformat(timespec="seconds")

    sezioni = gpd.read_file(IN_GEOJSON)[["SEZ2011", "COMUNE", "gap_score", "geometry"]]
    sezioni_utm = sezioni.to_crs(CRS_UTM)
    sezioni_buff_utm = sezioni_utm.copy()
    sezioni_buff_utm["geometry"] = sezioni_utm.geometry.buffer(BUFFER_SEZIONE_METRI)
    sezioni_buff = gpd.GeoDataFrame(
        sezioni_buff_utm[["SEZ2011", "COMUNE", "gap_score"]],
        geometry=sezioni_buff_utm.geometry, crs=CRS_UTM
    ).to_crs(CRS_WGS84)

    tile_df = pd.read_csv(IN_TILE)
    print(f"Tile da scaricare: {len(tile_df)} (fino a {MAX_WORKER_PARALLELI} in parallelo)")

    # sessione condivisa con pool di connessioni dimensionato sul numero di
    # worker: senza una sessione condivisa ogni requests.get() apre una
    # nuova connessione (handshake TCP+TLS completo) invece di riusarne una
    # gia' aperta - costo trascurabile in locale (rete veloce, verificato:
    # 803 tile in 6-8s), ma su un runner GitHub Actions con latenza di rete
    # piu' alta verso TomTom questo overhead per-richiesta si e' rivelato
    # il vero collo di bottiglia (~300s misurati contro gli 8s locali, a
    # parita' di codice/parallelismo - unica differenza plausibile).
    sessione = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=MAX_WORKER_PARALLELI,
                                             pool_maxsize=MAX_WORKER_PARALLELI)
    sessione.mount("https://", adapter)

    def scarica_tile_completo(row):
        x, y, zoom = int(row["tile_x"]), int(row["tile_y"]), int(row["zoom"])
        tile_decodificato = scarica_e_decodifica_tile(sessione, x, y, zoom, api_key)
        return estrai_segmenti_lonlat(tile_decodificato, x, y, zoom)

    tutti_i_segmenti = []
    completati = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKER_PARALLELI) as executor:
        future_per_riga = {executor.submit(scarica_tile_completo, row): row for _, row in tile_df.iterrows()}
        for future in as_completed(future_per_riga):
            tutti_i_segmenti.extend(future.result())
            completati += 1
            if completati % 200 == 0 or completati == len(tile_df):
                print(f"  [{completati}/{len(tile_df)}] tile scaricati, {len(tutti_i_segmenti)} segmenti finora")

    if not tutti_i_segmenti:
        print("Nessun segmento scaricato, esco senza scrivere output.")
        return

    gdf_segmenti = gpd.GeoDataFrame(tutti_i_segmenti, geometry="geometry", crs=CRS_WGS84)
    gdf_segmenti_utm = gdf_segmenti.to_crs(CRS_UTM)

    # assegna ciascun segmento alla/e sezione/i con cui interseca (poligono bufferizzato)
    join = gpd.sjoin(gdf_segmenti, sezioni_buff, how="inner", predicate="intersects")

    righe = []
    for _, r in join.iterrows():
        centro = r["geometry"].centroid
        righe.append({
            "timestamp_utc": timestamp_utc,
            "SEZ2011": r["SEZ2011"],
            "COMUNE": r["COMUNE"],
            "gap_score": r["gap_score"],
            "road_type": r["road_type"],
            "traffic_road_coverage": r["traffic_road_coverage"],
            "congestione": r["congestione"],
            "lat": centro.y,
            "lon": centro.x,
            "assegnazione": "dentro_sezione",
            "distanza_m": 0.0,
        })

    # fallback "distance-aware" per le sezioni senza alcun segmento dentro il
    # buffer: assegna il segmento scaricato piu' vicino, segnalando la
    # distanza. sjoin_nearest usa l'indice spaziale di geopandas (molto piu'
    # veloce, alla scala della provincia, del ciclo "distanza da ogni
    # segmento" usato nella versione a 50 sezioni - vedi punto 3 in cima).
    sezioni_coperte = set(r["SEZ2011"] for r in righe)
    sezioni_mancanti_utm = sezioni_utm[~sezioni_utm["SEZ2011"].isin(sezioni_coperte)].copy()

    if len(sezioni_mancanti_utm):
        gdf_segmenti_utm_idx = gdf_segmenti_utm.reset_index(drop=True)
        vicini = gpd.sjoin_nearest(
            sezioni_mancanti_utm[["SEZ2011", "COMUNE", "gap_score", "geometry"]],
            gdf_segmenti_utm_idx[["road_type", "traffic_road_coverage", "congestione", "geometry"]],
            distance_col="distanza_m",
        )
        for _, r in vicini.iterrows():
            seg_geom_wgs84 = gdf_segmenti.geometry.iloc[r["index_right"]]
            centro = seg_geom_wgs84.centroid
            righe.append({
                "timestamp_utc": timestamp_utc,
                "SEZ2011": r["SEZ2011"],
                "COMUNE": r["COMUNE"],
                "gap_score": r["gap_score"],
                "road_type": r["road_type"],
                "traffic_road_coverage": r["traffic_road_coverage"],
                "congestione": r["congestione"],
                "lat": centro.y,
                "lon": centro.x,
                "assegnazione": "piu_vicino_esterno",
                "distanza_m": round(r["distanza_m"], 1),
            })

    out = pd.DataFrame(righe)
    n_sezioni_coperte = out["SEZ2011"].nunique() if len(out) else 0
    print(f"\nSegmenti totali scaricati: {len(gdf_segmenti)}")
    print(f"Righe assegnate a una sezione: {len(out)}")
    print(f"Sezioni con almeno un segmento: {n_sezioni_coperte} / {len(sezioni)}")

    path_giorno = out_path_giorno(ora_corrente.date())
    if path_giorno.exists():
        out_precedente = pd.read_parquet(path_giorno)
        out = pd.concat([out_precedente, out], ignore_index=True)
    out.to_parquet(path_giorno, compression="gzip", index=False)
    print(f"Salvate {len(out)} righe totali (oggi) in: {path_giorno}")


if __name__ == "__main__":
    import sys
    forza = "--forza" in sys.argv
    main(forza=forza)
