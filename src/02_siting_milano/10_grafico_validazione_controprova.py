# -*- coding: utf-8 -*-
"""
Step 10 - grafico di validazione a controprova, su 3 sezioni di esempio del
gruppo "controprova" (§7 della metodologia): Solaro (SEZ2011 152130000005),
Trezzo sull'Adda (152210000004), Calvignasco (150420000001) - scelte tra le
74 sezioni di controprova con i 3 candidati di siting pieni, per un buon
numero di colonnine reali rimosse (mappa non spoglia) e una buona distanza
dal reale (esempio "da manuale").

Stessa impostazione visiva delle mappe di 09_grafici_presentazione.py
(basemap CartoDB Positron via contextily, Web Mercator, palette INK/MUTED),
ma qui il confronto e' tra:
  - COLONNINE REALI ESISTENTI nella sezione (rosso), rimosse solo nella
    simulazione (§7.1 della metodologia) - "da spegnere" nell'esperimento
  - PUNTI RACCOMANDATI dal modello di siting (verde, script 06) - "da
    accendere" se il modello avesse dovuto scoprire da zero questa sezione

Una linea tratteggiata collega ogni punto raccomandato alla colonnina reale
piu' vicina, con la distanza in etichetta - stesso principio di
07_validazione_controprova.py, ma NON lo stesso numero: qui il confronto e'
ristretto alle sole colonnine reali dentro il confine ESATTO della sezione
(niente buffer di 500m), un pool piu' piccolo e piu' severo di quello usato
per la metrica ufficiale in validazione_controprova.csv. Le distanze di
questo grafico vanno lette come un confronto "1 colonnina spenta, 1 punto
acceso" illustrativo, non come sostituto della metrica aggregata ufficiale.

Vincolo N=N: se la sezione ha N colonnine reali dentro il confine esatto, si
mostrano i primi N candidati di siting (non fissi a 3) - "se ne spengo N, ne
accendo N". La maggior parte delle sezioni di controprova (54/74, 73%) non
ha NESSUNA colonnina dentro il proprio confine esatto (tutte nel buffer
500m): per quelle sezioni questo grafico non è applicabile e viene saltato.

Le colonnine reali sono deduplicate per coordinata (round a 5 decimali): il
dataset colonnine_rimosse_controprova.csv ha una riga per CONNETTORE
(evse_id), non per stallo fisico - una colonnina con 3 prese comparirebbe
altrimenti come 3 punti sovrapposti, gonfiando visivamente il conteggio.

Input: sezioni_target_validazione.geojson, candidati_siting_provincia.csv
       (script 06), Contesto lavoro di gruppo ETL/colonnine_rimosse_controprova.csv
Output: output/grafici di validazione/*.png
"""

import sys
from pathlib import Path

import contextily as ctx
import geopandas as gpd
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import GRAFICI_VALIDAZIONE_DIR, assicura, trova


# i PNG sono un prodotto della pipeline: vanno in output/ (ignorata da git),
# non accanto al codice sorgente.
CARTELLA_GRAFICI = assicura(GRAFICI_VALIDAZIONE_DIR)


IN_GEOJSON = trova("sezioni_target_validazione.geojson")
IN_CANDIDATI_SITING = trova("candidati_siting_provincia.csv")
IN_COLONNINE_RIMOSSE = trova("colonnine_rimosse_controprova.csv")

FILTRA_A_SOLE_SEZIONI_CON_COLONNINA_DENTRO = True  # se True, SEZIONI_ESEMPIO viene ignorata: si
# generano automaticamente TUTTE le sezioni di controprova con almeno 1 colonnina reale dentro il
# confine esatto (le uniche per cui questo grafico ha senso - vedi nota sopra, 20/74). Mettere a
# False e valorizzare SEZIONI_ESEMPIO per generare solo un sottoinsieme scelto a mano.
SEZIONI_ESEMPIO = [152130000005, 152210000004, 150420000001]  # Solaro, Trezzo sull'Adda, Calvignasco

INK = "#2b2b2b"
MUTED = "#5a5a5a"
ROSSO = "#c0392b"   # colonnina reale, da spegnere nella simulazione
VERDE = "#1a9850"   # punto raccomandato dal modello, da accendere
ORDINALI = ["1°", "2°", "3°", "4°", "5°"]
ZOOM_BASEMAP = 16

CRS_WGS84 = "EPSG:4326"
CRS_UTM = "EPSG:32632"
_to_utm = Transformer.from_crs(CRS_WGS84, CRS_UTM, always_xy=True).transform


def slug(comune):
    return comune.lower().replace(" ", "_").replace("'", "")


def imposta_estensione(ax, *geoseries_3857, margine_frazione=0.18):
    """Estensione della mappa sull'UNIONE di tutte le geometrie passate (poligono +
    colonnine reali + candidati), non sul solo poligono della sezione: le colonnine
    reali rimosse possono trovarsi fino a 500m dal confine (assegnate per buffer, non
    per appartenenza al poligono - vedi §7.1 della metodologia), quindi zoomare solo
    sul poligono le taglierebbe fuori dall'inquadratura."""
    bounds = np.array([g.total_bounds for g in geoseries_3857 if len(g)])
    minx, miny = bounds[:, 0].min(), bounds[:, 1].min()
    maxx, maxy = bounds[:, 2].max(), bounds[:, 3].max()
    margine = margine_frazione * max(maxx - minx, maxy - miny)
    ax.set_xlim(minx - margine, maxx + margine)
    ax.set_ylim(miny - margine, maxy + margine)


def grafico_validazione(sez, comune, poligono, candidati_scelti, colonnine_sez):
    # dedup colonnine reali per coordinata (round 5 decimali): un evse_id per connettore,
    # una colonnina fisica puo' averne piu' di uno sulla stessa coordinata
    reali = colonnine_sez[["colonnina_lat", "colonnina_lon"]].round(5).drop_duplicates()
    reali = reali.rename(columns={"colonnina_lat": "lat", "colonnina_lon": "lon"})

    # SOLO le colonnine reali DENTRO il confine esatto della sezione: il dataset di
    # partenza le assegna per buffer di 500m dal poligono (§7.1 della metodologia), non
    # per appartenenza al poligono stesso - la maggior parte delle colonnine "rimosse"
    # nella controprova si trova infatti fuori dal confine esatto (verificato: 54/74
    # sezioni di controprova non ne hanno NESSUNA dentro il confine esatto). Qui si
    # mostra solo il sottoinsieme "dentro", per un confronto 1:1 leggibile: se la
    # sezione ha N colonnine reali dentro il confine, si mostrano i primi N candidati
    # di siting (non fissi a 3) - "se ne spengo N, ne accendo N".
    dentro = reali.apply(lambda r: poligono.contains(Point(r["lon"], r["lat"])), axis=1)
    reali = reali[dentro].reset_index(drop=True)
    n_reali = len(reali)
    if n_reali == 0:
        print(f"  SEZ2011={sez}: nessuna colonnina reale dentro il confine esatto, salto.")
        return
    candidati_scelti = candidati_scelti.head(n_reali)
    if len(candidati_scelti) < n_reali:
        print(f"  SEZ2011={sez}: attenzione, solo {len(candidati_scelti)} candidati di siting "
              f"disponibili contro {n_reali} colonnine reali dentro il confine (mostro quelli disponibili).")

    rx, ry = _to_utm(reali["lon"].to_numpy(), reali["lat"].to_numpy())
    reali_utm = np.column_stack([rx, ry])

    gdf_reali = gpd.GeoDataFrame(reali, geometry=gpd.points_from_xy(reali["lon"], reali["lat"]),
                                  crs=CRS_WGS84).to_crs("EPSG:3857")
    gdf_scelti = gpd.GeoDataFrame(candidati_scelti, geometry=gpd.points_from_xy(
        candidati_scelti["lon"], candidati_scelti["lat"]), crs=CRS_WGS84).to_crs("EPSG:3857")
    poligono_3857 = gpd.GeoSeries([poligono], crs=CRS_WGS84).to_crs("EPSG:3857")

    fig, ax = plt.subplots(figsize=(10, 10), dpi=200)
    poligono_3857.plot(ax=ax, facecolor="none", edgecolor=INK, linewidth=2, zorder=2)
    imposta_estensione(ax, poligono_3857, gdf_reali, gdf_scelti)

    gdf_reali.plot(ax=ax, color=ROSSO, marker="X", markersize=170, edgecolor="white",
                    linewidth=1.1, zorder=4,
                    label=f"colonnina reale dentro il confine, spenta nella simulazione ({n_reali})")

    # linea tratteggiata verso la colonnina reale piu' vicina + etichetta di distanza (stessa
    # metrica di 07_validazione_controprova.py: distanza minima punto-per-punto in UTM)
    for i, (_, riga) in enumerate(candidati_scelti.iterrows()):
        px, py = _to_utm(riga["lon"], riga["lat"])
        dist = np.hypot(reali_utm[:, 0] - px, reali_utm[:, 1] - py)
        i_vicina = int(np.argmin(dist))
        d_metri = float(dist[i_vicina])

        punto_3857 = gdf_scelti.geometry.iloc[i]
        vicina_3857 = gdf_reali.geometry.iloc[i_vicina]
        ax.plot([punto_3857.x, vicina_3857.x], [punto_3857.y, vicina_3857.y],
                color=MUTED, linestyle=(0, (4, 3)), linewidth=1.3, zorder=3)
        mx, my = (punto_3857.x + vicina_3857.x) / 2, (punto_3857.y + vicina_3857.y) / 2
        ax.annotate(f"{d_metri:.0f}m", (mx, my), fontsize=9, color=MUTED, fontweight="bold",
                    ha="center", va="center",
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")], zorder=4)

    gdf_scelti.plot(ax=ax, color=VERDE, markersize=170, edgecolor="white", linewidth=1.1, zorder=5)
    for i, (_, riga) in enumerate(candidati_scelti.iterrows()):
        punto = gdf_scelti.geometry.iloc[i]
        nome = riga["nome"] if isinstance(riga["nome"], str) and riga["nome"] else riga["categoria"]
        etichetta = f"{ORDINALI[i]} raccomandato — {nome}"
        dy = 30 + (len(candidati_scelti) - 1 - i) * 40
        ax.annotate(etichetta, (punto.x, punto.y), xytext=(20, dy), textcoords="offset points",
                    ha="left", va="bottom", fontsize=9.5, color=VERDE, fontweight="bold",
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")],
                    arrowprops=dict(arrowstyle="-", color=VERDE, linewidth=1.2,
                                     shrinkA=0, shrinkB=9, connectionstyle="arc3,rad=0.1"))

    ctx.add_basemap(ax, source=ctx.providers.CartoDB.Positron, zoom=ZOOM_BASEMAP)
    ax.set_axis_off()
    ax.set_title(f"Controprova: colonnine reali vs punti raccomandati — {comune}",
                 fontsize=14.5, color=INK, loc="left", pad=12, fontweight="bold")

    handles, labels = ax.get_legend_handles_labels()
    handles.append(plt.Line2D([0], [0], marker="o", linestyle="none", markerfacecolor=VERDE,
                               markeredgecolor="white", markersize=10,
                               label=f"punto raccomandato dal modello, mai visto le colonnine reali ({len(candidati_scelti)})"))
    ax.legend(handles=handles, loc="lower right", frameon=True, facecolor="white", framealpha=0.9,
              edgecolor="none", fontsize=8.5)

    mediana_d = np.median([np.hypot(reali_utm[:, 0] - px, reali_utm[:, 1] - py).min()
                            for px, py in zip(*_to_utm(candidati_scelti["lon"].to_numpy(),
                                                        candidati_scelti["lat"].to_numpy()))])
    fig.text(0.01, 0.014,
              f"SEZ2011 {sez} · {n_reali} colonnine reali dentro il confine esatto (stalli fisici, "
              f"connettori multipli deduplicati) · {len(candidati_scelti)} candidati mostrati (1 per "
              f"colonnina reale) · distanza mediana candidato→colonnina più vicina: {mediana_d:.0f}m",
              fontsize=9.5, color=INK, path_effects=[pe.withStroke(linewidth=3, foreground="white")])

    fig.subplots_adjust(left=0.01, right=0.99, top=0.95, bottom=0.055)
    out = CARTELLA_GRAFICI / f"controprova_{slug(comune)}_{sez}.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Salvato: {out.name} (distanza mediana {mediana_d:.0f}m)")


def sezioni_con_colonnina_dentro(sezioni, candidati, colonnine):
    """Tutte le sezioni di controprova con almeno un candidato di siting (script 06) E almeno
    una colonnina reale dentro il confine esatto (non solo nel buffer di 500m) - le uniche per
    cui il confronto 1:1 di questo grafico e' applicabile."""
    controprova_con_candidati = candidati.loc[candidati["gruppo"] == "controprova", "SEZ2011"].unique()
    trovate = []
    for sez in sorted(controprova_con_candidati):
        riga_sez = sezioni[sezioni["SEZ2011"] == sez]
        if riga_sez.empty:
            continue
        poligono = riga_sez.iloc[0].geometry
        sub = colonnine[colonnine["SEZ2011"] == sez][["colonnina_lat", "colonnina_lon"]].round(5).drop_duplicates()
        if sub.empty:
            continue
        dentro = sub.apply(lambda r: poligono.contains(Point(r["colonnina_lon"], r["colonnina_lat"])), axis=1)
        if dentro.sum() >= 1:
            trovate.append(int(sez))
    return trovate


def main():
    sezioni = gpd.read_file(IN_GEOJSON)
    sezioni["SEZ2011"] = sezioni["SEZ2011"].astype(int)
    candidati = pd.read_csv(IN_CANDIDATI_SITING)
    colonnine = pd.read_csv(IN_COLONNINE_RIMOSSE)

    if FILTRA_A_SOLE_SEZIONI_CON_COLONNINA_DENTRO:
        sezioni_da_fare = sezioni_con_colonnina_dentro(sezioni, candidati, colonnine)
        print(f"Sezioni di controprova con almeno 1 colonnina reale dentro il confine esatto: "
              f"{len(sezioni_da_fare)}\n")
    else:
        sezioni_da_fare = SEZIONI_ESEMPIO

    for sez in sezioni_da_fare:
        riga_sez = sezioni[sezioni["SEZ2011"] == sez]
        if riga_sez.empty:
            print(f"SEZ2011={sez} non trovata nel geojson target, salto.")
            continue
        riga_sez = riga_sez.iloc[0]
        comune = riga_sez["COMUNE"]
        poligono = riga_sez.geometry
        print(f"=== SEZ2011 {sez} ({comune}) ===")

        candidati_scelti = candidati[candidati["SEZ2011"] == sez].sort_values("rank")
        if candidati_scelti.empty:
            print(f"  Nessun candidato di siting per SEZ2011={sez}, salto.")
            continue
        colonnine_sez = colonnine[colonnine["SEZ2011"] == sez]
        if colonnine_sez.empty:
            print(f"  Nessuna colonnina reale rimossa per SEZ2011={sez}, salto.")
            continue

        grafico_validazione(sez, comune, poligono, candidati_scelti, colonnine_sez)

    print(f"\nTutti i grafici sono in: {CARTELLA_GRAFICI}")


if __name__ == "__main__":
    main()
