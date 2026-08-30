"""
APPLICAZIONE DELLA CORREZIONE v2 ALLE SEZIONI E RICALCOLO DEL GAP SCORE
=======================================================================

Prende i totali provinciali corretti da `01_correzione_provinciale_v2.py` e li
porta fino al GAP score, senza toccare nulla della pipeline esistente: legge
`sezioni_gap_score_DEFINITIVO.parquet` come sorgente e scrive i propri output
in questa cartella.

--- Cosa cambia e cosa no -----------------------------------------------
Cambia SOLO il totale provinciale da distribuire. Restano identici:
  - l'IDI3 e il moltiplicatore socioeconomico;
  - il peso di ripartizione `peso_EV` (popolazione in eta' di guida x IDI);
  - il cap di plausibilita' per sezione;
  - la correzione di fattibilita' domestica (E27/E3);
  - l'offerta e il suo rango `offerta_norm` (distance-aware): le colonnine non
    dipendono da come sono immatricolate le auto.
Di conseguenza il GAP cambia solo attraverso il lato domanda.

--- I tre passi ---------------------------------------------------------
1. Ridistribuzione del nuovo totale provinciale alle sezioni con gli STESSI
   pesi e cap gia' presenti nel file (stessa funzione della pipeline: allocazione
   proporzionale con cap e redistribuzione iterativa dell'eccedenza).
2. Domanda effettiva = domanda corretta x quota_bisogno_pubblico (E27/E3).
3. GAP = rango(domanda effettiva) - rango(offerta), sullo stesso universo di
   sezioni eleggibili di prima, cosi' i due punteggi restano confrontabili.

Output:
  - sezioni_gap_v2.parquet  (tutte le colonne + domanda e gap v2 + geometria)
  - gap_score_v2.csv        (SEZ2011 + gap_score_v2, leggero)
  - confronto_gap_v1_v2.csv (per provincia: quanto e' cambiato)
"""

import sys
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (CONFIG_DIR, DATA_DIR, OUTPUT_DIR, OVERPASS_CACHE_DIR,
                   TOMTOM_KEY_FILE, assicura, gap_score_definitivo, manca, trova)



GAP_PARQUET = gap_score_definitivo()
PROV_V2 = trova("domanda_provincia_v2_CORRETTA.csv")
OUT_PARQUET = OUTPUT_DIR / "sezioni_gap_v2.parquet"
OUT_CSV = OUTPUT_DIR / "gap_score_v2.csv"
OUT_CONFRONTO = OUTPUT_DIR / "confronto_gap_v1_v2.csv"

CRS = "EPSG:32632"
SOGLIA_DESERTO = 0.429   # soglia del gomito, invariata rispetto alla v1


def _base(s: str) -> str:
    s = str(s).upper().strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.replace("'", " ").replace("-", " ").replace("/", " ")
    return re.sub(r"\s+", " ", s).strip()


def alloca_con_cap(pesi, cap, totale, tol=1e-9):
    """Distribuisce `totale` proporzionalmente a `pesi` senza superare `cap`;
    l'eccedenza di chi tocca il cap viene redistribuita tra le altre sezioni.
    Identica alla funzione usata in produzione: conserva esattamente il totale."""
    pesi = np.asarray(pesi, float)
    cap = np.asarray(cap, float)
    totale = float(totale)
    if totale <= tol:
        return np.zeros_like(pesi)
    if cap.sum() + tol < totale:
        raise ValueError(f"totale {totale:g} superiore alla capacita' {cap.sum():g}")
    alloc = np.zeros_like(pesi)
    residuo = totale
    attive = (pesi > 0) & (cap > 0)
    while residuo > tol:
        capres = cap - alloc
        cand = attive & (capres > tol)
        if not cand.any():
            raise RuntimeError("capacita' esaurita prima di allocare tutto")
        pc = pesi[cand]
        if pc.sum() <= tol:
            pc = capres[cand]
        prop = residuo * pc / pc.sum()
        oltre = prop > capres[cand] + tol
        pos = np.flatnonzero(cand)
        if not oltre.any():
            alloc[pos] += prop
            residuo = 0.0
        else:
            pcap = pos[oltre]
            assegnato = capres[pcap]
            alloc[pcap] += assegnato
            residuo -= assegnato.sum()
            attive[pcap] = False
    return alloc


def main():
    print("=== Applicazione della correzione v2 alle sezioni + ricalcolo GAP ===\n")

    df = pd.read_parquet(GAP_PARQUET)
    print(f"Sezioni caricate: {len(df):,} | colonne: {df.shape[1]}")

    prov = pd.read_csv(PROV_V2)
    prov["k"] = prov.Provincia.map(_base)
    totale_v2 = prov.set_index("k")["ev_corretto_v2"]

    # --- 1) ridistribuzione alle sezioni con pesi e cap invariati ---
    df["domanda_v2"] = 0.0
    for provincia, idx in df.groupby("PROVINCIA_EV_2025").groups.items():
        chiave = _base(provincia)
        if chiave not in totale_v2.index:
            continue                       # sezioni senza provincia riconosciuta
        idx = list(idx)
        df.loc[idx, "domanda_v2"] = alloca_con_cap(
            df.loc[idx, "peso_EV"].to_numpy(),
            df.loc[idx, "cap_EV_sezione"].to_numpy(),
            float(totale_v2[chiave]))

    ric = df.groupby("PROVINCIA_EV_2025").domanda_v2.sum()
    atteso = pd.Series({p: totale_v2.get(_base(p), np.nan) for p in ric.index})
    print(f"Max scarto riconciliazione provinciale: {(ric-atteso).abs().max():.2e}")
    print(f"Totale nazionale: {df.domanda_v2.sum():,.0f} "
          f"(originale {df.veicoli_da_ricaricare_stimati.sum():,.0f})")

    # --- 2) domanda effettiva (fattibilita' di ricarica domestica invariata) ---
    eleggibile = df.gap_score.notna()      # stesso universo della v1
    df["domanda_effettiva_v2"] = np.where(
        eleggibile, df.domanda_v2 * df.quota_bisogno_pubblico_sezione, np.nan)

    # --- 3) nuovo GAP: cambia il rango della domanda, l'offerta resta identica ---
    df["domanda_norm_v2"] = np.nan
    df.loc[eleggibile, "domanda_norm_v2"] = df.loc[eleggibile, "domanda_effettiva_v2"].rank(pct=True)
    df["gap_score_v2"] = np.where(eleggibile, df.domanda_norm_v2 - df.offerta_norm, np.nan)

    assert df.loc[eleggibile, "gap_score_v2"].between(-1, 1).all()
    assert df.loc[~eleggibile, "gap_score_v2"].isna().all()

    d1, d2 = df.loc[eleggibile, "gap_score"], df.loc[eleggibile, "gap_score_v2"]
    print(f"\nGAP v1: mediana {d1.median():.3f} | deserti {(d1>SOGLIA_DESERTO).sum():,}")
    print(f"GAP v2: mediana {d2.median():.3f} | deserti {(d2>SOGLIA_DESERTO).sum():,}")
    print(f"Correlazione Spearman v1 vs v2: {d1.corr(d2, method='spearman'):.4f}")

    # --- confronto per provincia (quanto si sposta ogni territorio) ---
    e = df[eleggibile]
    conf = e.groupby("PROVINCIA").apply(lambda g: pd.Series({
        "pop_guida": g.popolazione_eta_guida_stimata.sum(),
        "quota_deserto_v1": g.popolazione_eta_guida_stimata.where(
            g.gap_score > SOGLIA_DESERTO, 0).sum() / g.popolazione_eta_guida_stimata.sum(),
        "quota_deserto_v2": g.popolazione_eta_guida_stimata.where(
            g.gap_score_v2 > SOGLIA_DESERTO, 0).sum() / g.popolazione_eta_guida_stimata.sum(),
    })).reset_index()
    conf["variazione"] = conf.quota_deserto_v2 - conf.quota_deserto_v1
    conf.sort_values("variazione").to_csv(OUT_CONFRONTO, index=False)
    print("\nProvince che cambiano di piu' (quota di popolazione in deserto):")
    estremi = pd.concat([conf.nsmallest(5, "variazione"), conf.nlargest(5, "variazione")])
    print(estremi[["PROVINCIA", "quota_deserto_v1", "quota_deserto_v2",
                   "variazione"]].round(3).to_string(index=False))

    # --- salvataggio ---
    df["geometry"] = gpd.GeoSeries.from_wkb(df["geometry"], crs=CRS)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=CRS)
    gdf.to_parquet(OUT_PARQUET, index=False)
    gdf[["SEZ2011", "gap_score_v2"]].to_csv(OUT_CSV, index=False)
    print(f"\nSalvati: {OUT_PARQUET.name}, {OUT_CSV.name}, {OUT_CONFRONTO.name}")


if __name__ == "__main__":
    main()
