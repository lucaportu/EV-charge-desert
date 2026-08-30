"""
Scarica i 20 shapefile regionali delle sezioni di censimento 2011 (basi
territoriali ISTAT), con geometria poligonale in proiezione WGS84 UTM 32N.

Fonte: https://www.istat.it/notizia/basi-territoriali-e-variabili-censuarie/
Pattern URL (verificato il 2026-07-17, HTTP 200):
https://www.istat.it/storage/cartografia/basi_territoriali/WGS_84_UTM/2011/R{XX}_11_WGS84.zip
dove {XX} e' il codice regione a 2 cifre (01 = Piemonte ... 20 = Sardegna),
stessa numerazione dei CSV R01...R20_indicatori_2011_sezioni.csv gia' in uso.

Ogni zip contiene lo shapefile (.shp/.dbf/.shx/.prj) con il confine di ogni
sezione di censimento della regione. La chiave da usare per il merge con i
CSV indicatori (campo SEZ2011) va verificata nell'attributo del layer (in
alcune versioni si chiama SEZ2011, in altre PRO_COM_T + SEZ) prima di fare
il join. Verificare inoltre il CRS dichiarato (gdf.crs) di ogni regione
prima di assumere che siano tutte coerenti, nonostante il nome del file
dichiari gia' WGS84.

Nessuna autenticazione richiesta: file pubblici scaricabili con una normale
richiesta HTTP GET.
"""

import sys
from pathlib import Path
from urllib.request import urlretrieve

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (CONFIG_DIR, DATA_DIR, OUTPUT_DIR, OVERPASS_CACHE_DIR,
                   TOMTOM_KEY_FILE, assicura, gap_score_definitivo, manca, trova)


BASE_URL = "https://www.istat.it/storage/cartografia/basi_territoriali/WGS_84_UTM/2011/R{:02d}_11_WGS84.zip"

OUT_DIR = ISTAT_ZIP_DIR

REGIONI = {
    1: "Piemonte", 2: "Valle d'Aosta", 3: "Lombardia", 4: "Trentino-Alto Adige",
    5: "Veneto", 6: "Friuli-Venezia Giulia", 7: "Liguria", 8: "Emilia-Romagna",
    9: "Toscana", 10: "Umbria", 11: "Marche", 12: "Lazio", 13: "Abruzzo",
    14: "Molise", 15: "Campania", 16: "Puglia", 17: "Basilicata", 18: "Calabria",
    19: "Sicilia", 20: "Sardegna",
}


def scarica_regione(codice: int, force: bool = False) -> Path:
    url = BASE_URL.format(codice)
    out_file = OUT_DIR / f"R{codice:02d}_11_WGS84.zip"
    if out_file.exists() and not force:
        print(f"R{codice:02d} ({REGIONI[codice]}) gia' presente, salto.")
        return out_file
    print(f"Scarico R{codice:02d} ({REGIONI[codice]})...")
    urlretrieve(url, out_file)
    return out_file


def main(force: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for codice in REGIONI:
        scarica_regione(codice, force=force)
    print(f"\n=== Fatto: 20 shapefile regionali in {OUT_DIR} ===")


if __name__ == "__main__":
    main()
