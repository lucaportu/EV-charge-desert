# -*- coding: utf-8 -*-
"""
Step 9 - grafici per la presentazione, su 2 sezioni di esempio scelte tra le
818 critiche (stessa logica di scelta usata per Mediglia in
Progetto3-Master-VectorTiles/SCRIPT/08_grafico_gap_score_colonnine.py: una
sezione che richiede 3 colonnine per scendere sotto soglia, con dati di
traffico/POI/siting abbastanza "corposi" da fare un buon esempio):

  - SEZ2011 152010000007, San Vittore Olona
  - SEZ2011 151390000005, Mediglia (stessa sezione gia' presentata in
    Progetto3, qui con dati reali di traffico/POI della fase provinciale)

Versione 2 (04/08/2026): mappe con basemap reale (CartoDB Positron via
contextily), stessa identica impostazione visiva delle mappe della cartella
Drive "7-Scraping+POI+Siting" > "Sezione esempio: Mediglia" (script
04_mappa_reale_contextily.py, 11_mappa_poi_sezione.py, 13_mappa_siting_sezione.py
di Progetto3-Master-VectorTiles) - richiede una connessione internet
(contextily scarica le tile al volo). Sostituisce la v1 (assi lat/lon nudi,
senza basemap).

Per ciascuna sezione genera 4 grafici, riusando le funzioni della pipeline
dove possibile (import diretto di 05_quante_colonnine.py e
06_candidati_siting_provincia.py):

  1. traffico_<comune>_<SEZ2011>.png - mappa dei segmenti robusti (>=5
     letture), colore = congestione massima (scala fissa 0-1, confrontabile
     tra sezioni), dimensione = n. letture; i 3 segmenti piu' critici
     etichettati "1°/2°/3°".
  2. poi_<comune>_<SEZ2011>.png - mappa dei POI candidati (livello 1-3)
     dentro il confine esatto, colorati per categoria (palette tab10).
  3. siting_<comune>_<SEZ2011>.png - mappa dei punti di siting raccomandati
     (rank 1-3, script 06), con nome/categoria/distanza in etichetta,
     contesto (segmenti robusti + altri POI candidati non scelti) in grigio.
  4. gap_score_<comune>_<SEZ2011>.png - impatto di 0-3 nuove colonnine sul
     GAP score (nessuna mappa, grafico a barre - stile invariato dalla v1).

Output: output/grafici/*.png
"""

import sys
import importlib.util
from pathlib import Path
from zoneinfo import ZoneInfo

import contextily as ctx
import geopandas as gpd
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (DATA_DIR, GRAFICI_DIR, OUTPUT_DIR, OVERPASS_CACHE_DIR,
                   assicura, gap_score_definitivo, trova)


CARTELLA_SCRIPT = Path(__file__).resolve().parent
# i PNG sono un prodotto della pipeline: vanno in output/ (ignorata da git),
# non accanto al codice sorgente.
CARTELLA_GRAFICI = assicura(GRAFICI_DIR)

IN_GAP_SCORE_NAZIONALE = gap_score_definitivo()

IN_GEOJSON = trova("sezioni_target_validazione.geojson")
IN_CANDIDATI_SITING = trova("candidati_siting_provincia.csv")
RAW_POI_DIR = OVERPASS_CACHE_DIR

SEZIONI_ESEMPIO = [152010000007, 151390000005]  # San Vittore Olona, Mediglia
MIN_LETTURE = 5
N_CANDIDATI_TRAFFICO = 3  # segmenti evidenziati nella mappa traffico
SCENARI_NUOVE_COLONNINE = [0, 1, 2, 3]
FUSO_ITALIA = ZoneInfo("Europe/Rome")
ZOOM_BASEMAP = 16

INK = "#2b2b2b"
MUTED = "#5a5a5a"
GRID = "#e6e6e6"
ACCENT = "#c0392b"
ORDINALI = ["1°", "2°", "3°", "4°", "5°"]

# stessa lista/ordine di 06_candidati_siting_provincia.py (LIVELLO), per colori stabili per indice
CATEGORIE_TUTTE = ["parking", "supermarket", "fuel", "office", "hospital",
                    "food_drink", "fitness", "park", "mall", "cinema"]
ETICHETTE_CAT = {
    "parking": "parcheggio", "supermarket": "supermercato", "fuel": "distributore",
    "office": "ufficio/azienda", "hospital": "ospedale", "food_drink": "ristorazione",
    "fitness": "palestra/centro sportivo", "park": "parco", "mall": "centro commerciale",
    "cinema": "cinema",
}
cmap_cat = plt.get_cmap("tab10")
COLORI_CAT = {cat: cmap_cat(i) for i, cat in enumerate(CATEGORIE_TUTTE)}


def _importa(nome_file):
    spec = importlib.util.spec_from_file_location(nome_file.stem, nome_file)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


m05 = _importa(Path(__file__).resolve().parent / "05_quante_colonnine.py")
m06 = _importa(Path(__file__).resolve().parent / "06_candidati_siting_provincia.py")


def slug(comune):
    return comune.lower().replace(" ", "_").replace("'", "")


def carica_traffico():
    file_giorni = sorted(DATA_DIR.glob("traffico_provincia_*.parquet")) + \
        sorted(OUTPUT_DIR.glob("traffico_provincia_*.parquet"))
    return pd.concat([pd.read_parquet(f) for f in file_giorni], ignore_index=True)


def imposta_estensione(ax, poligono_3857, margine_frazione=0.18):
    minx, miny, maxx, maxy = poligono_3857.total_bounds
    margine = margine_frazione * max(maxx - minx, maxy - miny)
    ax.set_xlim(minx - margine, maxx + margine)
    ax.set_ylim(miny - margine, maxy + margine)


def chiudi_e_salva(fig, ax, prefisso, comune, sez):
    ctx.add_basemap(ax, source=ctx.providers.CartoDB.Positron, zoom=ZOOM_BASEMAP)
    ax.set_axis_off()
    fig.subplots_adjust(left=0.01, right=0.99, top=0.95, bottom=0.055)
    out = CARTELLA_GRAFICI / f"{prefisso}_{slug(comune)}_{sez}.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Salvato: {out.name}")


# ---------------------------------------------------------------- 1. traffico
def grafico_traffico(sez, comune, poligono, traffico_sez):
    d = traffico_sez.copy()
    d["lat_r"] = d["lat"].round(5)
    d["lon_r"] = d["lon"].round(5)

    per_segmento = d.groupby(["lat_r", "lon_r", "road_type"]).agg(
        congestione_max=("congestione", "max"), n_letture=("congestione", "size")
    ).reset_index()
    punti = gpd.GeoDataFrame(per_segmento, geometry=gpd.points_from_xy(
        per_segmento["lon_r"], per_segmento["lat_r"]), crs="EPSG:4326")
    per_segmento = per_segmento[punti.within(poligono).to_numpy()].copy()

    robusti = per_segmento[per_segmento["n_letture"] >= MIN_LETTURE].sort_values(
        ["congestione_max", "n_letture"], ascending=[False, False])
    non_robusti = per_segmento[per_segmento["n_letture"] < MIN_LETTURE]
    if robusti.empty:
        print(f"  [traffico] SEZ2011={sez}: nessun segmento robusto, salto il grafico.")
        return
    top_n = robusti.head(N_CANDIDATI_TRAFFICO)

    gdf_robusti = gpd.GeoDataFrame(robusti, geometry=gpd.points_from_xy(
        robusti["lon_r"], robusti["lat_r"]), crs="EPSG:4326").to_crs("EPSG:3857")
    gdf_non_robusti = gpd.GeoDataFrame(non_robusti, geometry=gpd.points_from_xy(
        non_robusti["lon_r"], non_robusti["lat_r"]), crs="EPSG:4326").to_crs("EPSG:3857")
    poligono_3857 = gpd.GeoSeries([poligono], crs="EPSG:4326").to_crs("EPSG:3857")
    top_n_3857 = gpd.GeoDataFrame(top_n, geometry=gpd.points_from_xy(
        top_n["lon_r"], top_n["lat_r"]), crs="EPSG:4326").to_crs("EPSG:3857")

    cmap = plt.get_cmap("YlOrRd")
    norm = Normalize(vmin=0, vmax=1)  # scala fissa 0-1, confrontabile tra sezioni

    fig, ax = plt.subplots(figsize=(10, 10), dpi=200)
    poligono_3857.plot(ax=ax, facecolor="none", edgecolor=INK, linewidth=2, zorder=2)
    imposta_estensione(ax, poligono_3857)

    if len(gdf_non_robusti):
        gdf_non_robusti.plot(ax=ax, color="#bdbdbd", markersize=22, alpha=0.7, zorder=3,
                              label=f"< {MIN_LETTURE} letture (dato insufficiente)")

    sizes = 30 + gdf_robusti["n_letture"].clip(upper=60) * 1.5
    gdf_robusti.plot(ax=ax, column="congestione_max", cmap=cmap, vmin=0, vmax=norm.vmax,
                      markersize=sizes, edgecolor="white", linewidth=0.6, zorder=4)

    n_top = len(top_n)
    # offset adattivo sia in orizzontale sia in verticale (non sempre "in alto a destra"): le
    # etichette si irradiano verso il quadrante OPPOSTO a dove cade il cluster dei segmenti piu'
    # critici, cosi' restano lontane sia dalla colorbar (bordo destro) sia dal titolo (bordo
    # alto) - bug osservato su San Vittore Olona, dove i segmenti piu' critici sono vicini
    # all'angolo in alto a destra del poligono.
    centro_x = sum(ax.get_xlim()) / 2
    centro_y = sum(ax.get_ylim()) / 2
    for i in range(n_top):
        punto = top_n_3857.geometry.iloc[i]
        raggio = 600 - i * 110
        ax.scatter([punto.x], [punto.y], marker="o", facecolor="none", edgecolor=ACCENT,
                   s=raggio, linewidth=3 - i * 0.4, zorder=5)
        dy_base = 55 + (n_top - 1 - i) * 48
        a_sinistra = punto.x >= centro_x
        dx = -65 if a_sinistra else 65
        ha = "right" if a_sinistra else "left"
        verso_basso = punto.y >= centro_y
        dy = -dy_base if verso_basso else dy_base
        va = "top" if verso_basso else "bottom"
        ax.annotate(f"{ORDINALI[i]} segmento più critico", (punto.x, punto.y),
                    xytext=(dx, dy), textcoords="offset points", ha=ha, va=va,
                    fontsize=11.5, color=ACCENT, fontweight="bold",
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")],
                    arrowprops=dict(arrowstyle="-", color=ACCENT, linewidth=1.3,
                                     shrinkA=0, shrinkB=8, connectionstyle="arc3,rad=0.12"))

    ax.set_title(f"Congestione massima per segmento — {comune}", fontsize=15,
                 color=INK, loc="left", pad=12, fontweight="bold")

    cbar = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax, fraction=0.04, pad=0.02)
    cbar.set_label(f"congestione massima (min. {MIN_LETTURE} letture)", fontsize=10, color=MUTED)

    riferimenti_letture = [5, 20, 60]
    proxy_dimensioni = [
        Line2D([0], [0], marker="o", linestyle="none", markerfacecolor="#bdbdbd",
               markeredgecolor="white", markeredgewidth=0.6,
               markersize=((30 + min(n, 60) * 1.5) ** 0.5) * 0.62,
               label=f"{n} letture" + (" o più" if n == max(riferimenti_letture) else ""))
        for n in riferimenti_letture
    ]
    legenda_dato = ax.legend(handles=[Line2D([0], [0], marker="o", linestyle="none",
                              markerfacecolor="#bdbdbd", markeredgecolor="none",
                              markersize=6, label=f"< {MIN_LETTURE} letture (dato insufficiente)")],
                              loc="lower right", frameon=True, facecolor="white", framealpha=0.9,
                              edgecolor="none", fontsize=9)
    ax.add_artist(legenda_dato)
    ax.legend(handles=proxy_dimensioni, title="dimensione = n. letture", title_fontsize=8.5,
              loc="lower right", bbox_to_anchor=(1, 0.155), frameon=True, facecolor="white",
              framealpha=0.9, edgecolor="none", fontsize=8.5)

    ultima_data = pd.to_datetime(d["timestamp_utc"]).max().strftime("%d/%m %H:%M UTC")
    fig.text(0.01, 0.014, f"SEZ2011 {sez} · dati raccolta 03-04/08/2026, fino al {ultima_data}",
              fontsize=10, color=INK, path_effects=[pe.withStroke(linewidth=3, foreground="white")])

    chiudi_e_salva(fig, ax, "traffico", comune, sez)


# --------------------------------------------------------------------- 2. POI
def grafico_poi(sez, comune, poligono):
    raw_path = RAW_POI_DIR / f"{sez}.json"
    if not raw_path.exists():
        print(f"  [poi] SEZ2011={sez}: nessuna cache Overpass, salto il grafico.")
        return
    import json
    with open(raw_path, encoding="utf-8") as f:
        data = json.load(f)

    visti = set()
    poi = []
    for el in data["elements"]:
        tags = el.get("tags", {})
        cat = m06.categoria_poi(tags)
        if cat is None:
            continue
        coords = m06.lonlat_elemento(el)
        if coords is None:
            continue
        lon, lat = coords
        if not poligono.contains(Point(lon, lat)):
            continue
        chiave = (round(lat, 5), round(lon, 5), cat)
        if chiave in visti:
            continue
        visti.add(chiave)
        poi.append((lon, lat, cat, tags.get("name", "")))

    if not poi:
        print(f"  [poi] SEZ2011={sez}: nessun POI dentro il confine esatto, salto il grafico.")
        return

    gdf_poi = gpd.GeoDataFrame(
        poi, columns=["lon", "lat", "categoria", "nome"],
        geometry=gpd.points_from_xy([p[0] for p in poi], [p[1] for p in poi]), crs="EPSG:4326"
    ).to_crs("EPSG:3857")
    poligono_3857 = gpd.GeoSeries([poligono], crs="EPSG:4326").to_crs("EPSG:3857")

    fig, ax = plt.subplots(figsize=(10, 10), dpi=200)
    poligono_3857.plot(ax=ax, facecolor="none", edgecolor=INK, linewidth=2, zorder=2)
    imposta_estensione(ax, poligono_3857)

    for cat in CATEGORIE_TUTTE:
        sotto = gdf_poi[gdf_poi["categoria"] == cat]
        if sotto.empty:
            continue
        sotto.plot(ax=ax, color=COLORI_CAT[cat], markersize=110, edgecolor="white",
                   linewidth=0.9, zorder=4, label=f"{ETICHETTE_CAT[cat]} ({len(sotto)})")

    ax.set_title(f"POI rilevanti per il siting — {comune}", fontsize=15,
                 color=INK, loc="left", pad=12, fontweight="bold")
    ax.legend(loc="lower right", frameon=True, facecolor="white", framealpha=0.9,
              edgecolor="none", fontsize=9, title="categoria (n. POI)", title_fontsize=9.5)

    fig.text(0.01, 0.014,
              f"SEZ2011 {sez} · {len(poi)} POI dentro il confine esatto · fonte OpenStreetMap/Overpass",
              fontsize=10, color=INK, path_effects=[pe.withStroke(linewidth=3, foreground="white")])

    chiudi_e_salva(fig, ax, "poi", comune, sez)


# ----------------------------------------------------------------- 3. siting
def grafico_siting(sez, comune, poligono, traffico_sez, candidati_scelti):
    candidati_scelti = candidati_scelti.sort_values("rank")

    robusti = m06.segmenti_robusti_sezione(traffico_sez, poligono)
    tutti_poi = m06.poi_candidati_sezione(sez, poligono)

    gdf_poi_contesto = gpd.GeoDataFrame(
        tutti_poi, geometry=gpd.points_from_xy([p["lon"] for p in tutti_poi], [p["lat"] for p in tutti_poi]),
        crs="EPSG:4326").to_crs("EPSG:3857") if tutti_poi else gpd.GeoDataFrame(geometry=[], crs="EPSG:3857")
    gdf_traffico_contesto = gpd.GeoDataFrame(
        robusti, geometry=gpd.points_from_xy(robusti["lon_r"], robusti["lat_r"]), crs="EPSG:4326"
    ).to_crs("EPSG:3857") if len(robusti) else gpd.GeoDataFrame(geometry=[], crs="EPSG:3857")
    gdf_scelti = gpd.GeoDataFrame(
        candidati_scelti, geometry=gpd.points_from_xy(candidati_scelti["lon"], candidati_scelti["lat"]),
        crs="EPSG:4326").to_crs("EPSG:3857")
    poligono_3857 = gpd.GeoSeries([poligono], crs="EPSG:4326").to_crs("EPSG:3857")

    fig, ax = plt.subplots(figsize=(10, 10), dpi=200)
    poligono_3857.plot(ax=ax, facecolor="none", edgecolor=INK, linewidth=2, zorder=2)
    imposta_estensione(ax, poligono_3857)

    if len(gdf_traffico_contesto):
        gdf_traffico_contesto.plot(ax=ax, marker="s", color="#f0b0a8", markersize=26, alpha=0.75,
                                    zorder=3, label="segmento di traffico robusto")
    if len(gdf_poi_contesto):
        gdf_poi_contesto.plot(ax=ax, color="#bdbdbd", markersize=26, alpha=0.75,
                               zorder=3, label="altro POI candidato (livello 1-3, non scelto)")

    gdf_scelti.plot(ax=ax, color=ACCENT, markersize=140, edgecolor="white", linewidth=1, zorder=5)

    # etichette irradiate verso l'esterno rispetto al centroide dei soli punti scelti (non un
    # offset fisso): la diversificazione spaziale (>100m) puo' mettere due candidati vicini sullo
    # schermo nella stessa direzione, un offset fisso li farebbe collidere - vedi
    # 13_mappa_siting_sezione.py in Progetto3 per lo stesso ragionamento
    cx = gdf_scelti.geometry.x.mean()
    cy = gdf_scelti.geometry.y.mean()
    DISTANZA_ETICHETTA_PT = 95
    for i, (_, riga) in enumerate(candidati_scelti.iterrows()):
        punto = gdf_scelti.geometry.iloc[i]
        raggio = 650 - i * 110
        ax.scatter([punto.x], [punto.y], marker="o", facecolor="none", edgecolor=ACCENT,
                   s=raggio, linewidth=3 - i * 0.4, zorder=5)
        nome = riga["nome"] if isinstance(riga["nome"], str) and riga["nome"] else ETICHETTE_CAT[riga["categoria"]]
        etichetta = (f"{ORDINALI[i]} — {nome}\n"
                     f"({ETICHETTE_CAT[riga['categoria']]}, {riga['distanza_segmento_top_m']:.0f}m dal traffico)")

        dx_dir, dy_dir = punto.x - cx, punto.y - cy
        norma = (dx_dir ** 2 + dy_dir ** 2) ** 0.5
        if norma < 1:
            dx_dir, dy_dir = 1.0, 1.0
            norma = 2 ** 0.5
        dx_dir, dy_dir = dx_dir / norma, dy_dir / norma
        xytext = (dx_dir * DISTANZA_ETICHETTA_PT, dy_dir * DISTANZA_ETICHETTA_PT + 18)
        ha = "left" if dx_dir >= 0 else "right"
        va = "bottom" if dy_dir >= 0 else "top"

        ax.annotate(etichetta, (punto.x, punto.y),
                    xytext=xytext, textcoords="offset points", ha=ha, va=va,
                    fontsize=10, color=ACCENT, fontweight="bold",
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")],
                    arrowprops=dict(arrowstyle="-", color=ACCENT, linewidth=1.3,
                                     shrinkA=0, shrinkB=9, connectionstyle="arc3,rad=0.12"))

    ax.set_title(f"Punti di siting raccomandati — {comune}", fontsize=15,
                 color=INK, loc="left", pad=12, fontweight="bold")
    ax.legend(loc="lower right", frameon=True, facecolor="white", framealpha=0.9,
              edgecolor="none", fontsize=8.5)

    fig.text(0.01, 0.014,
              f"SEZ2011 {sez} · traffico + POI incrociati (script 06) · "
              "punteggio = congestione robusta pesata per distanza, diversificazione spaziale >100m",
              fontsize=8.5, color=INK, path_effects=[pe.withStroke(linewidth=3, foreground="white")])

    chiudi_e_salva(fig, ax, "siting", comune, sez)


# --------------------------------------------------------------- 4. gap score
def grafico_gap_score(sez, comune, gap_nazionale, parametri, soglia_critica):
    riga = gap_nazionale[gap_nazionale["SEZ2011"] == sez]
    if riga.empty:
        print(f"  [gap_score] SEZ2011={sez}: non trovata nel dataset nazionale, salto il grafico.")
        return
    sezione = riga.iloc[0]

    offerta_norm_iniziale = m05.offerta_norm_da_conteggio(
        [sezione["offerta_colonnine_500m"]], [sezione["distanza_colonnina_piu_vicina_m"]], parametri)[0]
    domanda_norm = sezione["gap_score"] + offerta_norm_iniziale

    risultati = []
    for n_nuove in SCENARI_NUOVE_COLONNINE:
        colonnine_simulate = sezione["offerta_colonnine_500m"] + n_nuove
        offerta_norm_sim = m05.offerta_norm_da_conteggio(
            [colonnine_simulate], [sezione["distanza_colonnina_piu_vicina_m"]], parametri)[0]
        risultati.append({"nuove_colonnine": n_nuove, "gap_score": domanda_norm - offerta_norm_sim})
    scenari = pd.DataFrame(risultati)

    scarto = abs(scenari.loc[scenari["nuove_colonnine"] == 0, "gap_score"].iloc[0] - sezione["gap_score"])
    assert scarto < 1e-6, f"Scenario 0 non riproduce il gap_score originale (scarto {scarto:.2e})"

    cmap = plt.get_cmap("YlOrRd")
    vmax = float(np.ceil(scenari["gap_score"].max() * 20) / 20)
    norm = Normalize(vmin=0, vmax=vmax)

    fig, ax = plt.subplots(figsize=(7.5, 5.5), dpi=200)
    colori = [cmap(norm(v)) for v in scenari["gap_score"]]
    barre = ax.bar(scenari["nuove_colonnine"], scenari["gap_score"], color=colori,
                    edgecolor="white", linewidth=1.2, width=0.62, zorder=3)
    for barra, valore in zip(barre, scenari["gap_score"]):
        ax.annotate(f"{valore:.3f}", (barra.get_x() + barra.get_width() / 2, valore),
                    xytext=(0, 6), textcoords="offset points", ha="center", va="bottom",
                    fontsize=10, color=INK, fontweight="bold")

    ax.axhline(soglia_critica, color=ACCENT, linestyle=(0, (5, 3)), linewidth=1.6, zorder=2)
    ax.text(0.015, soglia_critica, f"soglia critica (gomito) = {soglia_critica:.3f}",
            transform=ax.get_yaxis_transform(), ha="left", va="bottom", fontsize=9.5,
            color=ACCENT, fontweight="bold", path_effects=[pe.withStroke(linewidth=2.5, foreground="white")])

    idx_sotto_soglia = next((i for i, v in enumerate(scenari["gap_score"]) if v < soglia_critica), None)
    ax.set_xticks(scenari["nuove_colonnine"])
    ax.set_xlabel("nuove colonnine installate entro 500 m", fontsize=10, color=MUTED)
    ax.set_ylabel("GAP score", fontsize=10, color=MUTED)
    ax.set_ylim(0, max(vmax, soglia_critica) * 1.12)
    ax.set_title(f"Impatto di nuove colonnine sul GAP score — {comune}",
                 fontsize=14, color=INK, loc="left", pad=14, fontweight="bold")
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color(GRID)
    ax.tick_params(colors=MUTED)

    n_sotto = None
    if idx_sotto_soglia is not None:
        n_sotto = int(scenari["nuove_colonnine"].iloc[idx_sotto_soglia])
        for etichetta in ax.get_xticklabels():
            if etichetta.get_text() == str(n_sotto):
                etichetta.set_color(ACCENT)
                etichetta.set_fontweight("bold")

    nota_soglia = (f" · scende sotto soglia con {n_sotto} nuove colonnin{'a' if n_sotto == 1 else 'e'}"
                   if n_sotto is not None else "")
    fig.text(0.01, 0.01,
              f"SEZ2011 {sez} ({comune}) · simulazione: solo la componente di offerta cambia, "
              f"la domanda resta invariata{nota_soglia}", fontsize=7.6, color=MUTED)

    plt.tight_layout(rect=(0, 0.035, 1, 1))
    out = CARTELLA_GRAFICI / f"gap_score_{slug(comune)}_{sez}.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Salvato: {out.name}")
    print(scenari.round(4).to_string(index=False))


def main():
    sezioni = gpd.read_file(IN_GEOJSON)
    sezioni["SEZ2011"] = sezioni["SEZ2011"].astype(int)
    candidati = pd.read_csv(IN_CANDIDATI_SITING)
    traffico = carica_traffico()

    gap_nazionale = pd.read_parquet(
        IN_GAP_SCORE_NAZIONALE,
        columns=["SEZ2011", "gap_score", "offerta_colonnine_500m", "distanza_colonnina_piu_vicina_m"])
    eleggibili = gap_nazionale.dropna(subset=["gap_score"]).copy()
    critiche_ord = eleggibili[eleggibili["gap_score"] > 0].sort_values("gap_score", ascending=False)
    soglia_critica = float(critiche_ord["gap_score"].to_numpy()[m05.trova_gomito(critiche_ord["gap_score"].to_numpy())])
    parametri = m05.costruisci_parametri_offerta(eleggibili)
    print(f"Soglia critica (gomito nazionale): {soglia_critica:.4f}\n")

    for sez in SEZIONI_ESEMPIO:
        riga_sez = sezioni[sezioni["SEZ2011"] == sez]
        if riga_sez.empty:
            print(f"SEZ2011={sez} non trovata nel geojson target, salto.")
            continue
        riga_sez = riga_sez.iloc[0]
        comune = riga_sez["COMUNE"]
        poligono = riga_sez.geometry
        print(f"=== SEZ2011 {sez} ({comune}) ===")

        traffico_sez = traffico[traffico["SEZ2011"] == sez]
        grafico_traffico(sez, comune, poligono, traffico_sez)
        grafico_poi(sez, comune, poligono)

        scelti = candidati[candidati["SEZ2011"] == sez]
        if scelti.empty:
            print(f"  [siting] SEZ2011={sez}: nessun candidato in {IN_CANDIDATI_SITING.name}, salto il grafico.")
        else:
            grafico_siting(sez, comune, poligono, traffico_sez, scelti)

        grafico_gap_score(sez, comune, gap_nazionale, parametri, soglia_critica)
        print()

    print(f"Tutti i grafici sono in: {CARTELLA_GRAFICI}")


if __name__ == "__main__":
    main()
