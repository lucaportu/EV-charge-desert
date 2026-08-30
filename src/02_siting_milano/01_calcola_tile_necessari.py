"""
Step 1 del progetto di validazione modello di siting (vector tiles sulle
sezioni target della provincia di Milano). Stessa identica logica di
Progetto3-Master-VectorTiles (01_calcola_tile_necessari.py), input diverso:
le 968 sezioni target (818 critiche + 150 di controprova, vedi
Contesto lavoro di gruppo ETL/SCRIPT/seleziona_sezioni_target_validazione.py)
invece delle 13.557 sezioni dell'intera provincia.

NOTA STORICA: la prima versione di questo progetto (00_esporta_sezioni_provincia.py)
copriva l'INTERA provincia (13.557 sezioni, 2.408 tile) - analizzando lo
scope reale del modello (quante colonnine + dove, validato sulle sole
sezioni critiche + un campione di controprova) e' emerso che copriva un
problema molto piu' grande del necessario. sezioni_target_validazione.geojson
sostituisce sezioni_provincia_milano.geojson come input di questo script.

Output: tile_necessari.csv (colonne: tile_x, tile_y, zoom) e
        sezione_tile.csv (SEZ2011 -> tile_x, tile_y, zoom; una sezione
        puo' comparire su piu' righe se coperta da piu' tile)
"""

import sys
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (CONFIG_DIR, DATA_DIR, OUTPUT_DIR, OVERPASS_CACHE_DIR,
                   TOMTOM_KEY_FILE, assicura, gap_score_definitivo, manca, trova)


IN_GEOJSON = trova("sezioni_target_validazione.geojson")
OUT_TILE = OUTPUT_DIR / "tile_necessari.csv"
OUT_MAPPA = OUTPUT_DIR / "sezione_tile.csv"

ZOOM = 15


def lonlat_to_tile(lon, lat, zoom):
    lat_rad = math.radians(lat)
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def main():
    gdf = gpd.read_file(IN_GEOJSON)
    print(f"Sezioni in input: {len(gdf)}")

    righe_mappa = []
    tutti_i_tile = set()

    for i, row in gdf.iterrows():
        minx, miny, maxx, maxy = row.geometry.bounds
        x1, y1 = lonlat_to_tile(minx, maxy, ZOOM)  # angolo NW
        x2, y2 = lonlat_to_tile(maxx, miny, ZOOM)  # angolo SE

        tile_sezione = set()
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                tile_sezione.add((x, y))

        for x, y in tile_sezione:
            righe_mappa.append({"SEZ2011": row["SEZ2011"], "tile_x": x, "tile_y": y, "zoom": ZOOM})
        tutti_i_tile |= tile_sezione

        if (i + 1) % 2000 == 0 or i + 1 == len(gdf):
            print(f"  [{i+1}/{len(gdf)}] sezioni processate, {len(tutti_i_tile)} tile unici finora")

    pd.DataFrame(righe_mappa).to_csv(OUT_MAPPA, index=False)
    pd.DataFrame(sorted(tutti_i_tile), columns=["tile_x", "tile_y"]).assign(zoom=ZOOM).to_csv(OUT_TILE, index=False)

    print(f"\nTile totali unici necessari: {len(tutti_i_tile)}")
    print(f"Salvati: {OUT_TILE}, {OUT_MAPPA}")


if __name__ == "__main__":
    main()
