# -*- coding: utf-8 -*-
"""
Step 6 del progetto di validazione modello di siting - "dove installarle",
per tutte le 968 sezioni target (818 critiche + 150 di controprova).

Stessa identica metodologia di
Progetto3-Master-VectorTiles/SCRIPT/12_candidati_siting_colonnine.py (vedi
quel file per la motivazione estesa: imbuto a due fasi, POI di livello 1-3
come candidati installabili, punteggio di traffico con decadimento
lineare fino a 300m, diversificazione spaziale a 100m). Adattamenti per
questo progetto:

  - Il traffico non e' un unico CSV ma piu' file Parquet, uno per giorno
    (traffico_provincia_AAAA-MM-GG.parquet, script 02): carica_traffico()
    li legge tutti e li concatena.
  - Il GeoJSON di input ha una colonna "gruppo" (critica/controprova) in
    piu': viene riportata in output per poter separare le due analisi
    a valle (validazione controprova vs uso reale sulle critiche).

Se nessun file di traffico esiste ancora (prima dell'inizio della
campagna, o mentre e' in corso), lo script lo segnala chiaramente ed esce
senza errori, invece di fallire - permette di rilanciarlo cosi' com'e' non
appena i dati sono pronti, senza modifiche.

Input: sezioni_target_validazione.geojson,
       traffico_provincia_*.parquet (script 02),
       overpass_raw_poi/<SEZ2011>.json (script 03)
Output: candidati_siting_provincia.csv (SEZ2011, COMUNE, gruppo, gap_score,
        rank, categoria, livello, nome, lat, lon, punteggio_traffico,
        distanza segmento top, congestione/n_letture del segmento che
        genera il punteggio)
"""

import sys
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (CONFIG_DIR, DATA_DIR, OUTPUT_DIR, OVERPASS_CACHE_DIR,
                   TOMTOM_KEY_FILE, assicura, gap_score_definitivo, manca, trova)


IN_GEOJSON = trova("sezioni_target_validazione.geojson")
RAW_POI_DIR = OVERPASS_CACHE_DIR
OUT_CSV = OUTPUT_DIR / "candidati_siting_provincia.csv"

MIN_LETTURE = 5
DISTANZA_MASSIMA_M = 300
SEPARAZIONE_MINIMA_M = 100
N_CANDIDATI = 3

LIVELLO = {
    "fuel": 1, "supermarket": 1, "mall": 1,
    "parking": 2, "office": 2, "hospital": 2,
    "fitness": 3, "food_drink": 3, "cinema": 3,
}

CRS_WGS84 = "EPSG:4326"
CRS_UTM = "EPSG:32632"
_to_utm = Transformer.from_crs(CRS_WGS84, CRS_UTM, always_xy=True).transform


def carica_traffico():
    """Concatena tutti i traffico_provincia_AAAA-MM-GG.parquet presenti.
    None se non ne esiste ancora nessuno (campagna non ancora iniziata/in corso)."""
    file_giorni = sorted(DATA_DIR.glob("traffico_provincia_*.parquet")) + \
        sorted(OUTPUT_DIR.glob("traffico_provincia_*.parquet"))
    if not file_giorni:
        return None
    pezzi = [pd.read_parquet(f) for f in file_giorni]
    print(f"Traffico: {len(file_giorni)} file giorno letti ({[f.name for f in file_giorni]}), "
          f"{sum(len(p) for p in pezzi)} righe totali")
    return pd.concat(pezzi, ignore_index=True)


def categoria_poi(tags):
    amenity = tags.get("amenity")
    shop = tags.get("shop")
    leisure = tags.get("leisure")
    if amenity in ("restaurant", "cafe", "fast_food") or shop == "coffee":
        return "food_drink"
    if amenity == "parking":
        return "parking"
    if amenity == "fuel":
        return "fuel"
    if amenity == "hospital":
        return "hospital"
    if amenity == "cinema":
        return "cinema"
    if shop == "supermarket":
        return "supermarket"
    if shop in ("mall", "department_store"):
        return "mall"
    if tags.get("office") is not None:
        return "office"
    if leisure in ("fitness_centre", "sports_centre"):
        return "fitness"
    if leisure == "park":
        return "park"
    return None


def lonlat_elemento(el):
    if el["type"] == "node":
        return el["lon"], el["lat"]
    centro = el.get("center")
    return (centro["lon"], centro["lat"]) if centro else None


def segmenti_robusti_sezione(df_traffico, poligono):
    if df_traffico.empty:
        return pd.DataFrame(columns=["lat_r", "lon_r", "congestione_max", "n_letture"])
    d = df_traffico.copy()
    d["lat_r"] = d["lat"].round(5)
    d["lon_r"] = d["lon"].round(5)
    per_segmento = d.groupby(["lat_r", "lon_r"]).agg(
        congestione_max=("congestione", "max"), n_letture=("congestione", "size")
    ).reset_index()
    pts = gpd.GeoDataFrame(per_segmento, geometry=gpd.points_from_xy(
        per_segmento["lon_r"], per_segmento["lat_r"]), crs=CRS_WGS84)
    per_segmento = per_segmento[pts.within(poligono).to_numpy()]
    return per_segmento[per_segmento["n_letture"] >= MIN_LETTURE].reset_index(drop=True)


def poi_candidati_sezione(sez, poligono):
    raw_path = RAW_POI_DIR / f"{sez}.json"
    if not raw_path.exists():
        return []
    with open(raw_path, encoding="utf-8") as f:
        data = json.load(f)

    visti = set()
    candidati = []
    for el in data["elements"]:
        tags = el.get("tags", {})
        cat = categoria_poi(tags)
        if cat is None or cat not in LIVELLO:
            continue
        coords = lonlat_elemento(el)
        if coords is None:
            continue
        lon, lat = coords
        if not poligono.contains(Point(lon, lat)):
            continue
        chiave = (round(lat, 5), round(lon, 5), cat)
        if chiave in visti:
            continue
        visti.add(chiave)
        candidati.append({"categoria": cat, "livello": LIVELLO[cat],
                           "nome": tags.get("name", ""), "lat": lat, "lon": lon})
    return candidati


def punteggio_traffico(robusti_utm, ex, ey):
    if robusti_utm.empty:
        return 0.0, None
    dx = robusti_utm["x"].to_numpy() - ex
    dy = robusti_utm["y"].to_numpy() - ey
    dist = np.hypot(dx, dy)
    peso = np.clip(1 - dist / DISTANZA_MASSIMA_M, 0, None)
    punteggi = robusti_utm["congestione_max"].to_numpy() * peso
    i = int(np.argmax(punteggi))
    if punteggi[i] <= 0:
        return 0.0, None
    return float(punteggi[i]), {
        "distanza_m": round(float(dist[i]), 1),
        "congestione_segmento": float(robusti_utm["congestione_max"].iloc[i]),
        "n_letture_segmento": int(robusti_utm["n_letture"].iloc[i]),
    }


def diversifica(candidati_ordinati, n_max):
    accettati = []
    for c in candidati_ordinati:
        troppo_vicino = any(
            np.hypot(c["_x"] - a["_x"], c["_y"] - a["_y"]) < SEPARAZIONE_MINIMA_M
            for a in accettati
        )
        if troppo_vicino:
            continue
        accettati.append(c)
        if len(accettati) >= n_max:
            break
    return accettati


def main():
    sezioni = gpd.read_file(IN_GEOJSON)
    traffico = carica_traffico()
    if traffico is None:
        print("Nessun file traffico_provincia_*.parquet trovato: la campagna non ha ancora "
              "prodotto dati (non e' un errore - rilanciare questo script quando i parquet "
              "esistono, nessuna modifica necessaria).")
        return

    righe_out = []
    n_zero_candidati, n_zero_poi, n_zero_traffico = 0, 0, 0

    for _, sezione in sezioni.iterrows():
        sez = int(sezione["SEZ2011"])
        poligono = sezione.geometry

        candidati = poi_candidati_sezione(sez, poligono)
        if not candidati:
            n_zero_poi += 1
            continue

        robusti = segmenti_robusti_sezione(traffico[traffico["SEZ2011"] == sez], poligono)
        if robusti.empty:
            n_zero_traffico += 1
            continue

        rx, ry = _to_utm(robusti["lon_r"].to_numpy(), robusti["lat_r"].to_numpy())
        robusti_utm = robusti.assign(x=rx, y=ry)

        for c in candidati:
            ex, ey = _to_utm(c["lon"], c["lat"])
            c["_x"], c["_y"] = ex, ey
            c["punteggio_traffico"], c["_segmento_top"] = punteggio_traffico(robusti_utm, ex, ey)

        candidati = [c for c in candidati if c["punteggio_traffico"] > 0]
        if not candidati:
            n_zero_candidati += 1
            continue

        candidati.sort(key=lambda c: (-c["punteggio_traffico"], c["livello"]))
        scelti = diversifica(candidati, N_CANDIDATI)

        for rank, c in enumerate(scelti, start=1):
            seg = c["_segmento_top"]
            righe_out.append({
                "SEZ2011": sez, "COMUNE": sezione["COMUNE"], "gruppo": sezione["gruppo"],
                "gap_score": sezione["gap_score"],
                "rank": rank, "categoria": c["categoria"], "livello_confidenza": c["livello"],
                "nome": c["nome"], "lat": c["lat"], "lon": c["lon"],
                "punteggio_traffico": round(c["punteggio_traffico"], 4),
                "distanza_segmento_top_m": seg["distanza_m"],
                "congestione_segmento_top": round(seg["congestione_segmento"], 3),
                "n_letture_segmento_top": seg["n_letture_segmento"],
            })

    out = pd.DataFrame(righe_out)
    out.to_csv(OUT_CSV, index=False)

    n_sezioni_con_candidati = out["SEZ2011"].nunique() if len(out) else 0
    print(f"Salvato: {OUT_CSV} ({len(out)} righe)")
    print(f"Sezioni con almeno 1 candidato: {n_sezioni_con_candidati} / {len(sezioni)}")
    print(f"Sezioni senza POI candidati (livello 1-3): {n_zero_poi}")
    print(f"Sezioni con POI ma senza segmenti di traffico robusti: {n_zero_traffico}")
    print(f"Sezioni con POI e traffico ma punteggio sempre a 0 (>300m da ogni segmento robusto): {n_zero_candidati}")
    if len(out):
        for gruppo in ["critica", "controprova"]:
            n = out.loc[out["gruppo"] == gruppo, "SEZ2011"].nunique()
            tot = (sezioni["gruppo"] == gruppo).sum()
            print(f"  di cui {gruppo}: {n} / {tot} con almeno un candidato")


if __name__ == "__main__":
    main()
