# -*- coding: utf-8 -*-
"""
Step 4 del progetto di validazione modello di siting - aggrega la cache
Overpass POI (step 3) in conteggi per sezione e per categoria, per le 968
sezioni target.

Stessa identica logica di
Progetto3-Master-VectorTiles/SCRIPT/10_poi_dati_milano.py: un POI
appartiene alla sezione se cade geometricamente dentro il suo CONFINE
ESATTO (non un raggio fisso dal centroide - vedi quel file per il caso che
ha motivato la scelta, un supermercato reale a Mediglia escluso da un
raggio di 150m pur essendo dentro il confine). Le 10 categorie sono
accorpate in bucket comportamentali (food_drink, fitness, mall).

Output: poi_dati_target.csv (SEZ2011, COMUNE, gap_score, gruppo
        [critica/controprova], centroid_lat, centroid_lon, poi_count_totale,
        poi_count_<categoria> per le 10 categorie)
"""

import sys
import json
from collections import Counter
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import OUTPUT_DIR, OVERPASS_CACHE_DIR, assicura, trova


IN_GEOJSON = trova("sezioni_target_validazione.geojson")
RAW_DIR = OVERPASS_CACHE_DIR
OUT_CSV = assicura(OUTPUT_DIR) / "poi_dati_target.csv"

CATEGORIE = ["parking", "supermarket", "fuel", "office", "hospital",
             "food_drink", "fitness", "park", "mall", "cinema"]


def categoria_poi(tags):
    """Bucket comportamentale del POI, oppure None se non rientra in
    nessuna delle categorie tenute."""
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
    """Nodo: lat/lon diretti. Way: centro calcolato da Overpass
    ('out center'), campo 'center'."""
    if el["type"] == "node":
        return el["lon"], el["lat"]
    centro = el.get("center")
    if centro is None:
        return None
    return centro["lon"], centro["lat"]


def estrai_poi_dentro_confine(data, poligono):
    """Ritorna la lista di categorie dei POI (nodi o way) geometricamente
    dentro il confine esatto della sezione. Dedup su (lat, lon arrotondati
    a 5 decimali, categoria): un edificio mappato sia come way sia con nodi
    propri taggati non deve contare due volte lo stesso POI."""
    visti = set()
    categorie = []
    for el in data["elements"]:
        tags = el.get("tags", {})
        cat = categoria_poi(tags)
        if cat is None:
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
        categorie.append(cat)
    return categorie


def main():
    gdf = gpd.read_file(IN_GEOJSON)

    righe = []
    for _, row in gdf.iterrows():
        sez = row["SEZ2011"]
        raw_path = RAW_DIR / f"{sez}.json"

        if not raw_path.exists():
            print(f"{sez} ({row['COMUNE']}): nessuna cache Overpass")
            conteggi = Counter()
        else:
            with open(raw_path, encoding="utf-8") as f:
                data = json.load(f)
            categorie = estrai_poi_dentro_confine(data, row["geometry"])
            conteggi = Counter(categorie)

        riga = {
            "SEZ2011": sez, "COMUNE": row["COMUNE"], "gap_score": row["gap_score"],
            "gruppo": row["gruppo"],
            "centroid_lat": row["centroid_lat"], "centroid_lon": row["centroid_lon"],
            "poi_count_totale": sum(conteggi.values()),
        }
        riga.update({f"poi_count_{cat}": conteggi.get(cat, 0) for cat in CATEGORIE})
        righe.append(riga)

    df = pd.DataFrame(righe)
    df.to_csv(OUT_CSV, index=False)
    print(f"Salvato: {OUT_CSV} ({len(df)} righe, {len(df.columns)} colonne)")
    print(f"POI totali: {df['poi_count_totale'].sum()} - sezioni con 0 POI: {(df['poi_count_totale']==0).sum()}/{len(df)}")
    print(f"  di cui critiche a 0 POI: {((df['gruppo']=='critica') & (df['poi_count_totale']==0)).sum()} / {(df['gruppo']=='critica').sum()}")
    print(f"  di cui controprova a 0 POI: {((df['gruppo']=='controprova') & (df['poi_count_totale']==0)).sum()} / {(df['gruppo']=='controprova').sum()}")


if __name__ == "__main__":
    main()
