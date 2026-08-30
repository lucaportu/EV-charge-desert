# -*- coding: utf-8 -*-
"""
Step 5 del progetto di validazione modello di siting - "quante colonnine
servono", per tutte le 818 sezioni critiche (non una sola sezione esempio
come Progetto3-Master-VectorTiles/SCRIPT/08_grafico_gap_score_colonnine.py,
di cui questo script riusa la stessa identica metodologia).

Stessa logica: GAP score = rango percentile nazionale della domanda meno
rango percentile nazionale dell'offerta di colonnine; installare nuove
colonnine entro 500m della sezione sposta solo il suo rango di offerta,
lasciando invariata la domanda. Per ciascuna sezione critica si simula
l'aggiunta progressiva di colonnine (0, 1, 2, ... fino a MAX_SCENARI) e si
registra il primo scenario che fa scendere il gap_score sotto la soglia
critica nazionale (metodo del gomito).

Non richiede i dati di traffico/POI: usa solo
sezioni_gap_score_DEFINITIVO.parquet (universo nazionale eleggibile) e la
lista delle 818 sezioni critiche (dal geojson target, gruppo=='critica') -
puo' quindi girare gia' ora, indipendentemente da traffico/POI.

Output: quante_colonnine_critiche.csv (SEZ2011, COMUNE, gap_score,
        colonnine_necessarie, gap_score_dopo, per ciascuna delle 818
        sezioni critiche)
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (CONFIG_DIR, DATA_DIR, OUTPUT_DIR, OVERPASS_CACHE_DIR,
                   TOMTOM_KEY_FILE, assicura, gap_score_definitivo, manca, trova)


IN_GAP_SCORE_NAZIONALE = gap_score_definitivo()
IN_GEOJSON_TARGET = trova("sezioni_target_validazione.geojson")
OUT_CSV = OUTPUT_DIR / "quante_colonnine_critiche.csv"

MAX_SCENARI = 8  # scenari 0..8 nuove colonnine; se una sezione non scende sotto
                  # soglia nemmeno a +8 resta segnalata (colonnine_necessarie = None)


def trova_gomito(y_ordinato):
    """Stessa implementazione usata in tutta la pipeline gap_score: indice
    del punto di massima distanza dalla corda che unisce primo e ultimo
    punto della curva ordinata."""
    n = len(y_ordinato)
    x = np.arange(n, dtype=float)
    y = np.asarray(y_ordinato, dtype=float)
    x_n = (x - x.min()) / (x.max() - x.min())
    y_n = (y - y.min()) / (y.max() - y.min())
    x1, y1, x2, y2 = x_n[0], y_n[0], x_n[-1], y_n[-1]
    num = np.abs((y2 - y1) * x_n - (x2 - x1) * y_n + x2 * y1 - y2 * x1)
    den = np.sqrt((y2 - y1) ** 2 + (x2 - x1) ** 2)
    return int(np.argmax(num / den))


def costruisci_parametri_offerta(eleggibili_df):
    servite = eleggibili_df["offerta_colonnine_500m"] > 0
    non_servite = ~servite
    return {
        "N": len(eleggibili_df),
        "Z": int(non_servite.sum()),
        "servite_sorted": np.sort(eleggibili_df.loc[servite, "offerta_colonnine_500m"].to_numpy()),
        "non_servite_negdist_sorted": np.sort(
            -eleggibili_df.loc[non_servite, "distanza_colonnina_piu_vicina_m"].to_numpy()),
    }


def _rango_medio(valori, riferimento_ordinato):
    valori = np.asarray(valori, dtype=float)
    sx = np.searchsorted(riferimento_ordinato, valori, side="left")
    dx = np.searchsorted(riferimento_ordinato, valori, side="right")
    return (sx + dx + 1) / 2.0


def offerta_norm_da_conteggio(conteggio, distanza, parametri):
    conteggio = np.asarray(conteggio, dtype=float)
    distanza = np.asarray(distanza, dtype=float)
    servita = conteggio > 0
    rango_servite = parametri["Z"] + _rango_medio(conteggio, parametri["servite_sorted"])
    rango_non_servite = _rango_medio(-np.nan_to_num(distanza, nan=0.0), parametri["non_servite_negdist_sorted"])
    rango = np.where(servita, rango_servite, rango_non_servite)
    return rango / parametri["N"]


def main():
    gap_nazionale = pd.read_parquet(
        IN_GAP_SCORE_NAZIONALE,
        columns=["SEZ2011", "gap_score", "offerta_colonnine_500m", "distanza_colonnina_piu_vicina_m"])
    eleggibili = gap_nazionale.dropna(subset=["gap_score"]).copy()

    critiche_ord = eleggibili[eleggibili["gap_score"] > 0].sort_values("gap_score", ascending=False)
    soglia_critica = float(critiche_ord["gap_score"].to_numpy()[trova_gomito(critiche_ord["gap_score"].to_numpy())])
    print(f"Soglia critica (gomito nazionale): {soglia_critica:.4f}")

    target = gpd.read_file(IN_GEOJSON_TARGET)
    critiche_sez = target.loc[target["gruppo"] == "critica", "SEZ2011"].astype(int)

    dettaglio = eleggibili[eleggibili["SEZ2011"].isin(critiche_sez)].copy()
    print(f"Sezioni critiche trovate nel dataset eleggibile: {len(dettaglio)} / {len(critiche_sez)}")

    parametri = costruisci_parametri_offerta(eleggibili)
    comuni_by_sez = dict(zip(target["SEZ2011"].astype(int), target["COMUNE"]))

    righe = []
    for _, sezione in dettaglio.iterrows():
        offerta_norm_iniziale = offerta_norm_da_conteggio(
            [sezione["offerta_colonnine_500m"]], [sezione["distanza_colonnina_piu_vicina_m"]], parametri)[0]
        domanda_norm = sezione["gap_score"] + offerta_norm_iniziale

        colonnine_necessarie = None
        gap_score_dopo = None
        for n_nuove in range(0, MAX_SCENARI + 1):
            colonnine_simulate = sezione["offerta_colonnine_500m"] + n_nuove
            offerta_norm_sim = offerta_norm_da_conteggio(
                [colonnine_simulate], [sezione["distanza_colonnina_piu_vicina_m"]], parametri)[0]
            gap_sim = domanda_norm - offerta_norm_sim
            if gap_sim < soglia_critica:
                colonnine_necessarie = n_nuove
                gap_score_dopo = gap_sim
                break

        righe.append({
            "SEZ2011": int(sezione["SEZ2011"]),
            "COMUNE": comuni_by_sez.get(int(sezione["SEZ2011"]), ""),
            "gap_score": round(float(sezione["gap_score"]), 4),
            "colonnine_necessarie": colonnine_necessarie,
            "gap_score_dopo": round(float(gap_score_dopo), 4) if gap_score_dopo is not None else None,
        })

    out = pd.DataFrame(righe).sort_values("gap_score", ascending=False)
    out.to_csv(OUT_CSV, index=False)

    n_senza_soluzione = out["colonnine_necessarie"].isna().sum()
    print(f"\nSalvato: {OUT_CSV} ({len(out)} righe)")
    print(f"Sezioni che non scendono sotto soglia nemmeno a +{MAX_SCENARI} colonnine: {n_senza_soluzione}")
    print("\nDistribuzione colonnine_necessarie:")
    print(out["colonnine_necessarie"].value_counts(dropna=False).sort_index().to_string())


if __name__ == "__main__":
    main()
