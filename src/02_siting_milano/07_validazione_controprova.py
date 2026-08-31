# -*- coding: utf-8 -*-
"""
Step 7 del progetto di validazione modello di siting - controprova finale:
per le 150 sezioni di controprova, confronta il punto di siting
raccomandato dal modello (script 06) con la posizione reale della/e
colonnina/e rimossa/e nella simulazione (script
"Contesto lavoro di gruppo ETL/SCRIPT/seleziona_sezioni_target_validazione.py",
output colonnine_rimosse_controprova.csv).

Il modello non "vede" mai le colonnine esistenti (nessuna categoria POI
corrisponde a una colonnina di ricarica, §3.1 della metodologia): se il
punto raccomandato cade vicino a dove una colonnina è già stata installata
per davvero, è un'evidenza che il criterio di siting (POI livello 1-3 +
punteggio di traffico + diversificazione) individua punti sensati, non
solo teoricamente plausibili.

Metrica: distanza in metri tra il punto raccomandato (rank 1, la scelta
migliore secondo il modello) e la colonnina reale più vicina rimossa in
quella sezione, aggregata su tutte le sezioni di controprova con un
candidato disponibile (mediana, percentuali entro soglie 100/250/500m).
Riportata anche la miglior distanza tra i primi 3 candidati (rank 1-3),
per capire se il modello "ci arriva vicino" anche quando il rank 1 non è
il più vicino in assoluto.

Input: candidati_siting_provincia.csv (script 06),
       Contesto lavoro di gruppo ETL/colonnine_rimosse_controprova.csv
Output: validazione_controprova.csv (SEZ2011, COMUNE, distanza_rank1_m,
        distanza_migliore_m, rank_migliore)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import OUTPUT_DIR, assicura, trova



IN_CANDIDATI = trova("candidati_siting_provincia.csv")
IN_COLONNINE_RIMOSSE = trova("colonnine_rimosse_controprova.csv")
OUT_CSV = assicura(OUTPUT_DIR) / "validazione_controprova.csv"

CRS_WGS84 = "EPSG:4326"
CRS_UTM = "EPSG:32632"
_to_utm = Transformer.from_crs(CRS_WGS84, CRS_UTM, always_xy=True).transform

SOGLIE_M = [100, 250, 500]


def main():
    if not IN_CANDIDATI.exists():
        print(f"{IN_CANDIDATI.name} non esiste ancora: eseguire prima 06_candidati_siting_provincia.py "
              "quando i dati di traffico sono pronti (non e' un errore).")
        return
    if not IN_COLONNINE_RIMOSSE.exists():
        # Uscita pulita invece di un'eccezione: il file non e' versionato
        # (vedi 'Dati NON inclusi' nel README), quindi la sua assenza e'
        # una condizione prevista, non un errore di programmazione.
        print(
            f"{IN_COLONNINE_RIMOSSE.name} non disponibile: la controprova\n"
            "quantitativa non puo' essere calcolata. Il file elenca le\n"
            "colonnine reali rimosse nella simulazione ed e' prodotto dalla\n"
            "selezione delle sezioni target (script non versionato)."
        )
        return

    candidati = pd.read_csv(IN_CANDIDATI)
    candidati = candidati[candidati["gruppo"] == "controprova"].copy()
    if candidati.empty:
        print("Nessun candidato di controprova in candidati_siting_provincia.csv "
              "(nessuna delle 150 sezioni di controprova ha un punto raccomandato).")
        return

    colonnine = pd.read_csv(IN_COLONNINE_RIMOSSE)

    righe = []
    for sez, gruppo_cand in candidati.groupby("SEZ2011"):
        colonnine_sez = colonnine[colonnine["SEZ2011"] == sez]
        if colonnine_sez.empty:
            continue

        cx, cy = _to_utm(colonnine_sez["colonnina_lon"].to_numpy(), colonnine_sez["colonnina_lat"].to_numpy())

        gruppo_cand = gruppo_cand.sort_values("rank")
        distanze_per_rank = {}
        for _, riga in gruppo_cand.iterrows():
            px, py = _to_utm(riga["lon"], riga["lat"])
            d = np.hypot(cx - px, cy - py).min()
            distanze_per_rank[int(riga["rank"])] = float(d)

        distanza_rank1 = distanze_per_rank.get(1)
        rank_migliore = min(distanze_per_rank, key=distanze_per_rank.get)
        distanza_migliore = distanze_per_rank[rank_migliore]

        righe.append({
            "SEZ2011": sez, "COMUNE": gruppo_cand["COMUNE"].iloc[0],
            "n_colonnine_reali_rimosse": len(colonnine_sez),
            "distanza_rank1_m": round(distanza_rank1, 1) if distanza_rank1 is not None else None,
            "distanza_migliore_m": round(distanza_migliore, 1),
            "rank_migliore": rank_migliore,
        })

    out = pd.DataFrame(righe)
    out.to_csv(OUT_CSV, index=False)

    print(f"Salvato: {OUT_CSV} ({len(out)} sezioni di controprova valutate su 150)")
    if out.empty:
        return

    print("\n--- Distanza punto raccomandato (rank 1) vs colonnina reale piu' vicina ---")
    print(f"Mediana: {out['distanza_rank1_m'].median():.0f}m")
    print(f"Media: {out['distanza_rank1_m'].mean():.0f}m")
    for soglia in SOGLIE_M:
        pct = (out["distanza_rank1_m"] <= soglia).mean() * 100
        print(f"  entro {soglia}m: {pct:.0f}%")

    print("\n--- Distanza MIGLIORE tra i primi 3 candidati vs colonnina reale piu' vicina ---")
    print(f"Mediana: {out['distanza_migliore_m'].median():.0f}m")
    for soglia in SOGLIE_M:
        pct = (out["distanza_migliore_m"] <= soglia).mean() * 100
        print(f"  entro {soglia}m: {pct:.0f}%")


if __name__ == "__main__":
    main()
