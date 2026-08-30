"""
Left join tra:
  1) sezioni_censimento_2011_con_geometria.parquet (tabella di sinistra: tutte
     le 402.678 sezioni, con geometria nativa in EPSG:32632)
  2) offerta_colonnine_per_sezione.parquet (offerta_colonnine_500m e
     distanza_colonnina_piu_vicina_m, prodotto da assegna_colonnine_sezioni.py)
  3) domanda_ricarica_2025_per_sezione_IDI3_beta050.csv (IDI3, percentili di
     deprivazione/benessere, veicoli_da_ricaricare_stimati per sezione)

Chiave di join per entrambi i merge: SEZ2011.

Sezioni come tabella di sinistra (stessa convenzione di
unisci_basi_territoriali_sezioni.py): si mantengono tutte le 402.678 righe,
incluse quelle senza corrispondenza in offerta o in domanda (NaN, non zero
o buco: "nessun dato" resta esplicito).

Colonne sovrapposte tra sezioni e domanda (CODREG, REGIONE, CODPRO,
PROVINCIA, CODCOM, COMUNE, PROCOM, NSEZ, P1, popolazione_eta_guida_stimata):
prima di scartare la versione duplicata proveniente da domanda, il valore
viene confrontato riga per riga con quello di sezioni_censimento (unica
fonte affidabile perche' costruita dai poligoni ISTAT). Se coincidono
ovunque, si tiene solo la versione di sezioni_censimento; se ci sono
discrepanze, entrambe le versioni vengono mantenute (suffisso "_IDI" su
quella di domanda) e le discrepanze vengono riportate esplicitamente, senza
sceglierne una arbitrariamente.

sezione_convenzionale_case_sparse e' gia' identica per costruzione in
offerta_colonnine_per_sezione.parquet (copiata as-is da sezioni_censimento
in assegna_colonnine_sezioni.py): la colonna duplicata viene scartata senza
bisogno di verifica riga per riga.

Geometria: tenuta come bytes WKB grezzi per tutta la fase di merge (nessuna
decodifica in oggetti shapely, per risparmiare RAM); viene ricostruita come
GeoSeries solo una volta, alla fine, prima di salvare il GeoParquet di
output (cosi' il file resta apribile con gpd.read_parquet).
"""

import sys
import gc
import os
import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (CONFIG_DIR, DATA_DIR, OUTPUT_DIR, OVERPASS_CACHE_DIR,
                   TOMTOM_KEY_FILE, assicura, gap_score_definitivo, manca, trova)



SEZIONI_PARQUET = trova("sezioni_censimento_2011_con_geometria.parquet")
OFFERTA_PARQUET = trova("offerta_colonnine_per_sezione.parquet")
# La domanda per sezione (output dei notebook 05-06-07, passo 8) non e'
# versionata: e' il file mancante che interrompeva la pipeline. Si accettano
# anche i nomi alternativi presenti nell'archivio di progetto, e la variabile
# EV_DOMANDA_SEZIONE_CSV permette di indicarne uno qualsiasi.
_NOMI_DOMANDA = (
    "domanda_ricarica_2025_per_sezione_IDI3_beta050.csv",
    "domanda_ricarica_2025_per_sezione_IDI3_beta050_CORRETTA.csv",
    "domanda_ricarica_2025_per_sezione_IDI.csv",
)


def _trova_domanda():
    da_env = os.environ.get("EV_DOMANDA_SEZIONE_CSV")
    if da_env:
        return Path(da_env).expanduser()
    for nome in _NOMI_DOMANDA:
        for cartella in (OUTPUT_DIR, DATA_DIR):
            if (cartella / nome).exists():
                return cartella / nome
    return OUTPUT_DIR / _NOMI_DOMANDA[0]


DOMANDA_CSV = _trova_domanda()

OUTPUT_PARQUET = OUTPUT_DIR / "sezioni_offerta_domanda_merged.parquet"

CRS_METRICO = "EPSG:32632"

COLONNE_SOVRAPPOSTE = [
    "CODREG",
    "REGIONE",
    "CODPRO",
    "PROVINCIA",
    "CODCOM",
    "COMUNE",
    "PROCOM",
    "NSEZ",
    "P1",
    "popolazione_eta_guida_stimata",
]


def confronta_e_riduci_duplicati(df: pd.DataFrame) -> pd.DataFrame:
    """Per ogni colonna sovrapposta sezioni/domanda (suffisso '_IDI' su quella
    di domanda), confronta i valori sulle righe dove entrambe le fonti sono
    presenti. Se non ci sono discrepanze scarta la colonna '_IDI', altrimenti
    la mantiene e segnala il numero di righe discordanti."""
    print("\n--- Confronto colonne sovrapposte (sezioni vs domanda_IDI) ---")
    da_scartare = []
    for col in COLONNE_SOVRAPPOSTE:
        col_idi = f"{col}_IDI"
        if col_idi not in df.columns:
            print(f"  {col}: colonna '_IDI' assente (nessuna sovrapposizione), salto")
            continue

        entrambe_presenti = df[col_idi].notna()
        n_confrontabili = entrambe_presenti.sum()

        if pd.api.types.is_numeric_dtype(df[col]) and pd.api.types.is_numeric_dtype(df[col_idi]):
            uguali = np.isclose(
                df.loc[entrambe_presenti, col].astype("float64"),
                df.loc[entrambe_presenti, col_idi].astype("float64"),
                equal_nan=True,
            )
        else:
            uguali = (
                df.loc[entrambe_presenti, col].astype(str)
                == df.loc[entrambe_presenti, col_idi].astype(str)
            )

        n_discordanti = (~uguali).sum()
        print(f"  {col}: {n_confrontabili:,} righe confrontabili, {n_discordanti:,} discordanti")

        if n_discordanti == 0:
            da_scartare.append(col_idi)
        else:
            esempi = df.loc[entrambe_presenti].loc[~uguali, [col, col_idi]].head(5)
            print(f"    ATTENZIONE: {col} e {col_idi} non coincidono sempre, tengo entrambe. Esempi:")
            print(esempi.to_string())

    if da_scartare:
        print(f"\nScarto le colonne duplicate confermate identiche: {da_scartare}")
        df = df.drop(columns=da_scartare)
    return df


def main():
    print("--- Carico sezioni_censimento_2011_con_geometria.parquet (tabella di sinistra) ---")
    sezioni = pq.read_table(SEZIONI_PARQUET).to_pandas()
    print(f"Sezioni: {len(sezioni):,} righe, {len(sezioni.columns)} colonne")

    print("\n--- Carico offerta_colonnine_per_sezione.parquet ---")
    offerta = pd.read_parquet(OFFERTA_PARQUET)
    offerta = offerta.drop(columns=["sezione_convenzionale_case_sparse"])
    print(f"Offerta: {len(offerta):,} righe")
    print(f"SEZ2011 in offerta non presenti in sezioni: {(~offerta['SEZ2011'].isin(sezioni['SEZ2011'])).sum():,}")

    print("\n--- Carico domanda_ricarica_2025_per_sezione_IDI3_beta050.csv ---")
    domanda = pd.read_csv(DOMANDA_CSV)
    print(f"Domanda: {len(domanda):,} righe")
    print(f"SEZ2011 in domanda non presenti in sezioni: {(~domanda['SEZ2011'].isin(sezioni['SEZ2011'])).sum():,}")

    print("\n--- Left join sezioni <- offerta_colonnine (su SEZ2011) ---")
    merged = sezioni.merge(offerta, on="SEZ2011", how="left")
    del offerta
    gc.collect()
    print(f"Righe dopo il join con offerta: {len(merged):,}")
    print(f"Sezioni senza corrispondenza in offerta (NaN): {merged['offerta_colonnine_500m'].isna().sum():,}")

    print("\n--- Left join risultato <- domanda_ricarica (su SEZ2011) ---")
    merged = merged.merge(domanda, on="SEZ2011", how="left", suffixes=("", "_IDI"))
    del domanda, sezioni
    gc.collect()
    print(f"Righe dopo il join con domanda: {len(merged):,}")
    print(f"Sezioni senza corrispondenza in domanda (NaN, es. flag_abitata): {merged['flag_abitata'].isna().sum():,}")
    print(
        "Sezioni con IDI3_winsor NaN (include sia le non corrisposte sopra, sia le "
        f"sezioni abitate ma con flag_IDI_calcolabile=False): {merged['IDI3_winsor'].isna().sum():,}"
    )

    merged = confronta_e_riduci_duplicati(merged)

    print("\n--- Ricostruzione geometria e salvataggio GeoParquet ---")
    merged["geometry"] = gpd.GeoSeries.from_wkb(merged["geometry"], crs=CRS_METRICO)
    gdf = gpd.GeoDataFrame(merged, geometry="geometry", crs=CRS_METRICO)
    del merged
    gc.collect()

    print(f"Righe finali: {len(gdf):,} | Colonne finali: {len(gdf.columns)}")
    print(f"Colonne: {list(gdf.columns)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(OUTPUT_PARQUET)
    dimensione = OUTPUT_PARQUET.stat().st_size / 1024 / 1024
    print(f"\nSalvato: {OUTPUT_PARQUET} ({dimensione:.1f} MB)")


if __name__ == "__main__":
    main()
