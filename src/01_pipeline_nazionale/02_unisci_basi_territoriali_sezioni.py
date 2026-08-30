"""
Left join tra le basi territoriali 2011 (geometria delle sezioni di
censimento, 20 shapefile regionali) e sezioni_censimento_2011_ridotto.csv
(indicatori socio-demografici, gia' unito a livello nazionale), seguito dalla
pulizia del risultato.

Left = basi territoriali -> si tengono tutti i 402.678 poligoni, incluse le
~35.815 sezioni non residenziali (industriali, laghi, aree disabitate) che
non hanno indicatori: per quelle le colonne di sezioni_censimento_2011_ridotto
restano NaN. E' una scelta consapevole (non un bug): la mappa finale deve
rappresentare il territorio italiano come superficie continua, senza buchi;
le sezioni senza dati vanno colorate come "nessun dato", mai come zero.

Chiave di join: SEZ2011, presente identica in entrambe le fonti (verificato:
0 sezioni orfane sul lato CSV, ogni riga del CSV ha sempre un poligono
corrispondente nello shapefile).

Dopo il join, il merge viene pulito in due modi. In entrambi i casi non viene
rimossa nessuna riga: il dataset finale deve restare a 402.678 poligoni, e i
join spaziali successivi (colonnine, POI, EV) decidono chi includere tramite
i flag qui aggiunti, non tramite cancellazioni a monte.

1) Geometrie non valide (102 righe, self-intersection nei poligoni ISTAT)
   Riparate con shapely.make_valid (verificato: restituisce sempre Polygon o
   MultiPolygon per queste 102 righe, mai punti/linee residui da scartare).
   Senza questo fix, area/centroide/buffer calcolati su queste sezioni nei
   join spaziali successivi (§ 7.3-7.5 della documentazione di progetto)
   risultano sbagliati o sollevano errori in GEOS.
   Flag 'geometria_riparata' (bool): traccia quali righe sono state toccate,
   per poterle escludere da un controllo a campione o da un audit successivo.

2) Sezioni convenzionali per case sparse (1.084 righe)
   ISTAT aggrega la popolazione dispersa/non contigua di un comune (case
   sparse, non raggruppabili in una sezione ordinaria) in una sezione
   convenzionale con NSEZ nella forma 8888888 (e varianti 88888XY per i
   comuni con piu' cluster di case sparse). Il poligono associato non
   rappresenta la posizione reale della popolazione: e' un frammento minuscolo
   (area mediana 401 mq contro ~35.000 mq delle sezioni ordinarie, minimo
   5,9 mq). Calcolare densita' = popolazione/area su queste sezioni produce
   valori assurdi (fino a 53 milioni ab/km2), e assegnare loro colonnine/EV
   tramite buffer di 1 km sul centroide non avrebbe senso geografico: il
   centroide di un poligono fittizio non e' un luogo reale.
   La popolazione resta nel dataset (serve ai totali comunali/provinciali),
   ma va esclusa dai join spaziali con colonnine e dalla disaggregazione
   provincia -> sezione delle auto elettriche (join 4 della documentazione).
   Flag 'sezione_convenzionale_case_sparse' (bool).

   Regola di identificazione (verificata empiricamente su questo file, non
   dedotta da una tabella ISTAT ufficiale): NSEZ i cui primi 5 caratteri sono
   "88888". Una soglia piu' larga (qualunque NSEZ tra 8.000.000 e 8.999.999)
   e' stata scartata: include anche ~99 sezioni con area normale (mediana
   ~26.000 mq) che appartengono a una diversa numerazione ISTAT, non alle
   case sparse - includerle nel flag le avrebbe escluse ingiustamente dai
   join spaziali.

Output, due formati dallo stesso merge pulito:
  - GeoParquet (sezioni_censimento_2011_con_geometria.parquet): geometria
    nativa, compresso, va ricaricato con gpd.read_parquet() - da usare per
    tutti gli step successivi (join spaziale, mappa). E' il formato di
    riferimento: molto piu' leggero e veloce da ricaricare del CSV.
  - CSV (sezioni_censimento_2011_con_geometria.csv): stessa tabella con la
    geometria serializzata in WKT (colonna "geometry"), tenuto solo per
    ispezione manuale/compatibilita' con strumenti che non leggono parquet.
    Per ricaricarlo come GeoDataFrame:
        import geopandas as gpd, pandas as pd
        df = pd.read_csv(output_csv)
        gdf = gpd.GeoDataFrame(df, geometry=gpd.GeoSeries.from_wkt(df["geometry"]), crs="EPSG:32632")
"""

import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.validation import make_valid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (CONFIG_DIR, DATA_DIR, OUTPUT_DIR, OVERPASS_CACHE_DIR,
                   TOMTOM_KEY_FILE, assicura, gap_score_definitivo, manca, trova)



SHP_ZIP_DIR = ISTAT_ZIP_DIR
SHP_EXTRACT_DIR = SHP_ZIP_DIR / "estratti"
RIDOTTO_CSV = trova("0_sezioni_censimento_2011_ridotto.csv")
OUTPUT_PARQUET = OUTPUT_DIR / "sezioni_censimento_2011_con_geometria.parquet"
OUTPUT_CSV = OUTPUT_DIR / "sezioni_censimento_2011_con_geometria.csv"

N_REGIONI = 20
PREFISSO_CASE_SPARSE = "88888"


def estrai_shapefile(codice: int) -> Path:
    nome = f"R{codice:02d}_11_WGS84"
    cartella = SHP_EXTRACT_DIR / nome
    shp_path = cartella / f"{nome}.shp"
    if shp_path.exists():
        return shp_path
    zip_path = SHP_ZIP_DIR / f"{nome}.zip"
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(SHP_EXTRACT_DIR)
    return shp_path


def carica_basi_territoriali_nazionali() -> gpd.GeoDataFrame:
    pezzi = []
    crs_visti = set()
    for codice in range(1, N_REGIONI + 1):
        shp_path = estrai_shapefile(codice)
        gdf = gpd.read_file(shp_path, columns=["SEZ2011"])
        crs_visti.add(str(gdf.crs))
        gdf["SEZ2011"] = gdf["SEZ2011"].astype("int64")
        pezzi.append(gdf)
        print(f"R{codice:02d}: {len(gdf):>6} poligoni, CRS={gdf.crs}")

    if len(crs_visti) > 1:
        raise ValueError(f"CRS non coerente tra le regioni: {crs_visti} - normalizzare prima di unire")

    nazionale = gpd.GeoDataFrame(pd.concat(pezzi, ignore_index=True), crs=pezzi[0].crs)
    duplicati = nazionale["SEZ2011"].duplicated().sum()
    if duplicati:
        raise ValueError(f"{duplicati} SEZ2011 duplicati nelle basi territoriali - da investigare prima del join")
    return nazionale


def ripara_geometrie(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    non_valide = ~gdf.geometry.is_valid
    print(f"Geometrie non valide trovate: {non_valide.sum():,}")

    gdf["geometria_riparata"] = non_valide
    gdf.loc[non_valide, "geometry"] = gdf.loc[non_valide, "geometry"].apply(make_valid)

    tipi_dopo_fix = gdf.loc[non_valide, "geometry"].geom_type.value_counts()
    print(f"Tipi di geometria dopo il fix: {dict(tipi_dopo_fix)}")

    ancora_non_valide = (~gdf.geometry.is_valid).sum()
    if ancora_non_valide:
        raise ValueError(
            f"{ancora_non_valide} geometrie restano non valide dopo make_valid - da investigare a mano"
        )
    return gdf


def marca_case_sparse(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    nsez_str = gdf["NSEZ"].astype("Int64").astype(str)
    flag = nsez_str.str.startswith(PREFISSO_CASE_SPARSE).fillna(False)

    gdf["sezione_convenzionale_case_sparse"] = flag
    print(f"Sezioni convenzionali per case sparse marcate: {flag.sum():,}")
    print(f"  di cui con popolazione (P1) valorizzata: {gdf.loc[flag, 'P1'].notna().sum():,}")
    print(f"  di cui con P1 > 0: {(gdf.loc[flag, 'P1'] > 0).sum():,}")
    return gdf


def main():
    print("--- Carico basi territoriali (geometria) ---")
    basi = carica_basi_territoriali_nazionali()
    print(f"Totale poligoni nazionali: {len(basi):,}")

    print("\n--- Carico sezioni_censimento_2011_ridotto.csv (indicatori) ---")
    indicatori = pd.read_csv(RIDOTTO_CSV, dtype={"SEZ2011": "int64"})
    print(f"Totale righe indicatori: {len(indicatori):,}")

    print("\n--- Left join su SEZ2011 (basi territoriali come tabella sinistra) ---")
    merged = basi.merge(indicatori, on="SEZ2011", how="left")

    con_dati = merged["P1"].notna().sum()
    senza_dati = merged["P1"].isna().sum()
    print(f"Sezioni con indicatori: {con_dati:,}")
    print(f"Sezioni senza indicatori (non residenziali - NaN, non zero): {senza_dati:,}")

    print("\n--- Riparo le geometrie non valide ---")
    merged = ripara_geometrie(merged)

    print("\n--- Marco le sezioni convenzionali per case sparse ---")
    merged = marca_case_sparse(merged)

    OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)

    print("\n--- Salvo GeoParquet (geometria nativa, formato di riferimento) ---")
    merged.to_parquet(OUTPUT_PARQUET)
    dimensione_parquet = OUTPUT_PARQUET.stat().st_size / 1024 / 1024
    print(f"Salvato: {OUTPUT_PARQUET} ({dimensione_parquet:.1f} MB)")

    print("\n--- Serializzo geometria in WKT e salvo CSV (solo ispezione) ---")
    merged["geometry"] = merged["geometry"].apply(lambda g: g.wkt if g is not None else None)
    merged.to_csv(OUTPUT_CSV, index=False)
    dimensione_csv = OUTPUT_CSV.stat().st_size / 1024 / 1024
    print(f"Salvato: {OUTPUT_CSV} ({dimensione_csv:.1f} MB)")
    print(f"Righe: {len(merged):,} | Colonne: {len(merged.columns)}")


if __name__ == "__main__":
    main()
