# -*- coding: utf-8 -*-
"""
Step 0 del progetto provincia (vector tiles su tutta la provincia di
Milano, non solo le 50 sezioni critiche). Esporta le sezioni di censimento
della provincia dal dataset nazionale della pipeline principale in un
GeoJSON in WGS84, nello stesso formato di top50_sezioni_critiche_milano.geojson
(SEZ2011, COMUNE, gap_score, centroid_lat, centroid_lon, geometry), cosi'
gli script 01/02 possono essere praticamente identici a quelli di
Progetto3-Master-VectorTiles, solo con un input piu' grande.

Attenzione: la colonna "geometry" del parquet e' in EPSG:32632 (UTM 32N,
metri), NON in lon/lat gradi come nel GeoJSON delle 50 sezioni - va
riproiettata esplicitamente, altrimenti qualunque calcolo lon/lat (incluso
il calcolo dei tile in 01) produce risultati assurdi (verificato: un primo
tentativo di calcolo tile senza questa conversione e' andato in loop per
decine di minuti, i "gradi" da centinaia di migliaia mandavano in overflow
il conto dei tile).

Uso pyarrow con filtro a livello di lettura (filters=[('PROVINCIA','=','Milano')])
invece di pandas.read_parquet + filtro dopo: leggere prima tutte le ~400k
righe nazionali e filtrare dopo e' molto piu' lento (letture di parecchi
minuti contro pochi secondi), perche' il filtro Arrow evita di
materializzare in Python le righe delle altre province.

Output: sezioni_provincia_milano.geojson
"""

import sys
from pathlib import Path

import pyarrow.parquet as pq
import shapely
import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (CONFIG_DIR, DATA_DIR, OUTPUT_DIR, OVERPASS_CACHE_DIR,
                   TOMTOM_KEY_FILE, assicura, gap_score_definitivo, manca, trova)


IN_PARQUET = gap_score_definitivo()

OUT_GEOJSON = OUTPUT_DIR / "sezioni_provincia_milano.geojson"

CRS_SORGENTE = "EPSG:32632"
CRS_WGS84 = "EPSG:4326"


def main():
    tbl = pq.read_table(
        IN_PARQUET,
        columns=["SEZ2011", "COMUNE", "gap_score", "geometry"],
        filters=[("PROVINCIA", "=", "Milano")],
    )
    df = tbl.to_pandas()
    print(f"Sezioni lette (provincia di Milano): {len(df)}")

    geoms = shapely.from_wkb(df["geometry"].to_numpy())
    gdf = gpd.GeoDataFrame(df.drop(columns=["geometry"]), geometry=geoms, crs=CRS_SORGENTE)

    # centroide calcolato mentre la geometria e' ancora in UTM (metri): il
    # centroide di un poligono va calcolato in un CRS metrico, non in gradi
    # (altrimenti la distorsione della proiezione lo sposta leggermente)
    centro_utm = gdf.geometry.centroid
    centro_wgs84 = centro_utm.to_crs(CRS_WGS84)
    gdf["centroid_lon"] = centro_wgs84.x
    gdf["centroid_lat"] = centro_wgs84.y

    gdf = gdf.to_crs(CRS_WGS84)

    gdf = gdf.dropna(subset=["geometry"])
    gdf = gdf[~gdf.geometry.is_empty]
    print(f"Sezioni con geometria valida: {len(gdf)}")

    gdf.to_file(OUT_GEOJSON, driver="GeoJSON")
    print(f"Salvato: {OUT_GEOJSON}")
    print(f"Comuni distinti: {gdf['COMUNE'].nunique()}")


if __name__ == "__main__":
    main()
