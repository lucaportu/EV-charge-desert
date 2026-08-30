# -*- coding: utf-8 -*-
"""
Step 3 del progetto di validazione modello di siting - scarico POI
(Overpass API) per le 968 sezioni target (818 critiche + 150 di
controprova), da incrociare con i dati di traffico per il modello di
siting (quante colonnine + dove).

Stessa identica logica e stesse categorie di
Progetto3-Master-VectorTiles/SCRIPT/09_scarico_poi_overpass.py (vedi quel
file per la motivazione delle categorie: tempo di sosta comparabile a una
ricarica, area di sosta associata, visite ricorrenti). Unica differenza:
input le 968 sezioni target di questo progetto invece delle 50 sezioni
critiche di Progetto3.

Categorie tenute:
  - amenity=parking, fuel, hospital, cinema
  - amenity=restaurant/cafe/fast_food + shop=coffee -> "food_drink"
  - shop=supermarket
  - shop=mall, department_store
  - office=* (qualsiasi sottotipo)
  - leisure=fitness_centre, sports_centre, park

Nodi E way (centri commerciali, palestre e parchi sono quasi sempre
mappati come way su OpenStreetMap: una query solo sui nodi li perde
sistematicamente); per i way si usa "out center" per una coppia lat/lon
utilizzabile.

CORREZIONE POST-SMOKE-TEST (02/08/2026): la prima versione usava il filtro
poligonale esatto di Overpass QL (`poly:"..."`) sul poligono bufferizzato -
per una sezione reale, con ~107 vertici dopo il buffer, la query misurata
impiegava **33+ secondi ed entrava spesso in timeout (504)** sul mirror
pubblico (maps.mail.ru). Con lo stesso identico filtro tag ma un
BOUNDING BOX al posto del poligono esatto (test diretto sulla stessa
sezione reale), la query scende a **1,4 secondi sul server ufficiale
Overpass (overpass-api.de)**: il costo che esplodeva era la valutazione
punto-in-poligono su un contorno complesso, non il volume di dati. Usare
un bbox e' sicuro qui: l'assegnazione ESATTA alla sezione avviene comunque
nello step successivo (04, sul confine vero del poligono originale), il
bbox e' solo un prefiltro piu' grezzo (include qualche POI in piu' nei
quattro angoli, scartato dopo).

Con 968 sezioni la pausa di cortesia (968 x 1s = ~16 minuti) resta la
componente dominante del tempo totale - e' uno scraping una tantum (non
ripetuto come quello del traffico), non soggetto alla stessa pressione di
quota di TomTom.

Output: overpass_raw_poi/<SEZ2011>.json (cache grezza, una per sezione)
"""

import sys
import json
import os
import time
from pathlib import Path

import geopandas as gpd
import requests
from pyproj import Transformer
from shapely.ops import transform

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (CONFIG_DIR, DATA_DIR, OUTPUT_DIR, OVERPASS_CACHE_DIR,
                   TOMTOM_KEY_FILE, assicura, gap_score_definitivo, manca, trova)


IN_GEOJSON = trova("sezioni_target_validazione.geojson")
OUT_DIR = OVERPASS_CACHE_DIR

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Overpass chiede un contatto nello User-Agent per poter segnalare un uso
# anomalo. Va indicato un recapito RAGGIUNGIBILE, impostato via ambiente,
# cosi' nessun indirizzo personale resta scritto nel repository pubblico:
#     export OVERPASS_CONTACT="nome.cognome@campus.unimib.it"
CONTATTO = os.environ.get("OVERPASS_CONTACT", "").strip()

# Overpass chiede un contatto nello User-Agent per poter segnalare un uso
# anomalo. Va indicato un recapito RAGGIUNGIBILE, impostato via ambiente,
# cosi' nessun indirizzo personale resta scritto nel repository pubblico:
#     export OVERPASS_CONTACT="nome.cognome@campus.unimib.it"
CONTATTO = os.environ.get("OVERPASS_CONTACT", "").strip()
HEADERS = {
    "User-Agent": (
        "ProgettoEVChargeDesert/1.0 (progetto universitario Unimib"
        + (f"; contatto {CONTATTO}" if CONTATTO else "")
        + ")"
    )
}
BUFFER_METRI = 80  # margine attorno al poligono della sezione (query grezza; l'assegnazione
                    # esatta alla sezione avviene nello step successivo, sul confine vero)
PAUSA_TRA_RICHIESTE_S = 2.0  # cortesia verso il server pubblico Overpass - alzata da 1.0
                              # dopo aver osservato 429 (troppe richieste) ripetuti a quella cadenza

AMENITY_TAGS = ("parking", "fuel", "hospital", "cinema", "restaurant", "cafe", "fast_food")
SHOP_TAGS = ("supermarket", "mall", "department_store", "coffee")
LEISURE_TAGS = ("fitness_centre", "sports_centre", "park")

CRS_WGS84 = "EPSG:4326"
CRS_UTM = "EPSG:32632"

_to_utm = Transformer.from_crs(CRS_WGS84, CRS_UTM, always_xy=True).transform
_to_wgs84 = Transformer.from_crs(CRS_UTM, CRS_WGS84, always_xy=True).transform


def bbox_string(geom_wgs84):
    """Buffer in UTM (metri) del poligono, poi bounding box del risultato
    come stringa 'minlat,minlon,maxlat,maxlon' per Overpass QL. Vedi nota
    in cima al file sul perche' bbox e non poly:"...": stesso identico
    filtro tag, query 20x+ piu' veloce, nessuna perdita di precisione
    (l'assegnazione esatta e' nello step 04)."""
    geom_utm = transform(_to_utm, geom_wgs84)
    geom_utm_buff = geom_utm.buffer(BUFFER_METRI)
    geom_buff_wgs84 = transform(_to_wgs84, geom_utm_buff)

    minlon, minlat, maxlon, maxlat = geom_buff_wgs84.bounds
    return f"{minlat:.6f},{minlon:.6f},{maxlat:.6f},{maxlon:.6f}"


def build_query(bbox):
    amenity_regex = "^(" + "|".join(AMENITY_TAGS) + ")$"
    shop_regex = "^(" + "|".join(SHOP_TAGS) + ")$"
    leisure_regex = "^(" + "|".join(LEISURE_TAGS) + ")$"
    return f"""
[out:json][timeout:60];
(
  node["amenity"~"{amenity_regex}"]({bbox});
  way["amenity"~"{amenity_regex}"]({bbox});
  node["shop"~"{shop_regex}"]({bbox});
  way["shop"~"{shop_regex}"]({bbox});
  node["office"]({bbox});
  way["office"]({bbox});
  node["leisure"~"{leisure_regex}"]({bbox});
  way["leisure"~"{leisure_regex}"]({bbox});
);
out center tags;
""".strip()


def query_overpass(query, tentativi=5):
    """429 (troppe richieste) e' trattato diversamente dagli altri errori:
    non ha senso ritentare dopo pochi secondi come per un 504/errore di
    connessione transitorio, perche' il rate limit del server ha una
    finestra piu' lunga - ritentare subito peggiora la situazione. Attesa
    piu' lunga (30s, raddoppiata a ogni tentativo) per il 429, rispettando
    l'header Retry-After se il server lo fornisce; 5s per gli altri casi
    (comportamento invariato)."""
    ultimo_errore = None
    attesa_429 = 30
    for tentativo in range(1, tentativi + 1):
        try:
            r = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=100)
        except requests.exceptions.RequestException as e:
            ultimo_errore = e
            print(f"  tentativo {tentativo}: errore di connessione ({e}), riprovo tra 5s...")
            time.sleep(5)
            continue
        if r.status_code == 200:
            return r.json()
        ultimo_errore = None
        if r.status_code == 429:
            attesa = int(r.headers.get("Retry-After", attesa_429))
            print(f"  tentativo {tentativo}: HTTP 429 (rate limit), attendo {attesa}s...")
            time.sleep(attesa)
            attesa_429 *= 2
            continue
        print(f"  tentativo {tentativo}: HTTP {r.status_code}, riprovo tra 5s...")
        time.sleep(5)
    if ultimo_errore:
        raise ultimo_errore
    r.raise_for_status()


def main(limite_sezioni=None, forza=False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    gdf = gpd.read_file(IN_GEOJSON)
    if limite_sezioni:
        gdf = gdf.head(limite_sezioni)

    falliti = []
    for i, row in gdf.iterrows():
        sez = row["SEZ2011"]
        out_path = OUT_DIR / f"{sez}.json"
        if out_path.exists() and not forza:
            print(f"[{i+1}/{len(gdf)}] {sez} ({row['COMUNE']}): gia' in cache, salto")
            continue

        # una sezione che continua a fallire (es. rate limit persistente) non
        # deve far morire l'intero script: si segna come fallita e si
        # prosegue con le altre 967 - basta rilanciare lo script (la cache
        # esistente fa saltare quelle gia' fatte) per ritentare le rimaste.
        try:
            bbox = bbox_string(row["geometry"])
            query = build_query(bbox)

            print(f"[{i+1}/{len(gdf)}] {sez} ({row['COMUNE']}): interrogo Overpass...")
            data = query_overpass(query)

            n_nodi = sum(1 for e in data["elements"] if e["type"] == "node")
            n_way = sum(1 for e in data["elements"] if e["type"] == "way")
            print(f"    -> {n_nodi} nodi, {n_way} way")

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"    FALLITA ({e}), proseguo con la prossima")
            falliti.append(sez)

        time.sleep(PAUSA_TRA_RICHIESTE_S)

    print(f"\nCompletato. Sezioni fallite (da ritentare rilanciando lo script): {len(falliti)}")
    if falliti:
        print(falliti)


if __name__ == "__main__":
    import sys
    limite = int(sys.argv[1]) if len(sys.argv) > 1 else None
    forza = "--forza" in sys.argv
    main(limite_sezioni=limite, forza=forza)
