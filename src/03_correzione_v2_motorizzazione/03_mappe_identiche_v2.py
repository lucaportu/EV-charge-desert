"""
LE STESSE MAPPE DI `mappe_gap_migliorate.ipynb`, MA CON I DATI CORRETTI v2
==========================================================================

Riproduce **esattamente** le 16 figure del notebook `dati/mappe_gap_migliorate.ipynb`
(stessi costrutti, stesse palette, stesse soglie, stessi tagli), cambiando solo
la sorgente dei dati:

    gap_score  (pipeline v1)   ->   gap_score_v2  (dopo la correzione flotte +
                                                   tasso di motorizzazione)

Il notebook originale NON viene toccato. Le immagini prodotte qui hanno il
prefisso `gapmapv2_` per non confondersi ne' con quelle originali (`gapmap_`,
nella cartella `dati/`) ne' con quelle di `mappe_v2.ipynb` (prefisso `v2_`).

Uso:
    python 03_mappe_identiche_v2.py

Richiede che siano gia' stati eseguiti `01_correzione_provinciale_v2.py` e
`02_sezioni_e_gap_v2.py` (producono `sezioni_gap_v2.parquet`).
"""

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")          # nessuna finestra: lo script salva solo i PNG
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import (BoundaryNorm, LinearSegmentedColormap,
                               ListedColormap, TwoSlopeNorm)
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import MAPPE_V2_DIR, OUTPUT_DIR, assicura, trova


# le 16 figure sono un prodotto della pipeline: vanno in output/mappe_v2,
# non accanto al codice sorgente.
QUI = assicura(MAPPE_V2_DIR)

PARQUET = OUTPUT_DIR / "sezioni_gap_v2.parquet"  # <-- unica differenza sostanziale
PROV_GEOM = trova("province_geom.parquet")
CRS = "EPSG:32632"

# ---------------- CONFIGURAZIONE (identica all'originale) ----------------
SOGLIA = 0.429          # soglia deserto (gomito)
VMIN, VMAX = -0.8, 0.9  # estremi della scala continua
PAL_BASSO = ("#08306b", "#2171b5", "#6baed6", "#deebf7", "#ffffff")
PAL_ALTO = ("#fff7bc", "#fec44f", "#ef6548", "#99000d")

PREFISSO = "gapmapv2_"
SUFFISSO_TITOLO = "  ·  dati corretti v2"   # per non confondere le due serie


def salva(nome):
    plt.tight_layout()
    plt.savefig(QUI / f"{PREFISSO}{nome}", dpi=180, bbox_inches="tight")
    plt.close()
    print(f"   salvato {PREFISSO}{nome}")


# =========================================================================
print("Carico...")
gdf = gpd.read_parquet(PARQUET, columns=[
    "SEZ2011", "PROVINCIA", "COMUNE", "gap_score_v2",
    "popolazione_eta_guida_stimata", "geometry"]).rename(
    columns={"popolazione_eta_guida_stimata": "popg"})
gdf["PROCOM"] = (gdf.SEZ2011 // 10_000_000).astype("int64")
gdf["CODPRO"] = (gdf.PROCOM // 1000).astype("int64")
gdf["px"] = gdf.geometry.centroid.x
gdf["py"] = gdf.geometry.centroid.y
E = gdf[gdf.gap_score_v2.notna()].copy()
prov_geo = gpd.read_parquet(PROV_GEOM)
print(f"Sezioni {len(gdf):,} | con GAP {len(E):,} | province {len(prov_geo)}")


# ---------- figura 0: la soglia del gomito ----------
v = np.sort(E.gap_score_v2.values)[::-1]
pos = v[v > 0]
n = len(pos)
x = np.arange(n) / (n - 1)
y = (pos - pos.min()) / (pos.max() - pos.min())
i = int(np.argmax(np.abs(y + x - 1) / np.sqrt(2)))
print(f"\nGomito (Kneedle sui GAP positivi): {pos[i]:.4f}   -> soglia usata: {SOGLIA}")
des = E.gap_score_v2 > SOGLIA
print(f"Sezioni deserto: {des.sum():,} ({des.mean():.1%} delle sezioni)")
print(f"Popolazione nei deserti: {E.loc[des,'popg'].sum()/1e6:.2f}M "
      f"({E.loc[des,'popg'].sum()/E.popg.sum():.1%} della popolazione in eta' di guida)")

fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(np.arange(len(pos)), pos, color="#08306b", lw=2)
ax.axhline(SOGLIA, color="crimson", ls="--")
ax.axvline(i, color="crimson", ls=":")
ax.annotate(f"gomito\nGAP={pos[i]:.3f}", (i, pos[i]), xytext=(i * 1.6, pos[i] + 0.22),
            arrowprops=dict(arrowstyle="->", color="crimson"), color="crimson")
ax.set_xlabel("sezioni ordinate per GAP decrescente")
ax.set_ylabel("GAP score")
ax.set_title("Dove finiscono i 'quasi-deserti' e iniziano i deserti veri" + SUFFISSO_TITOLO)
salva("0_soglia.png")


# ---------- helper cromatici (identici all'originale) ----------
def cmap_ancorata(soglia=SOGLIA, vmin=VMIN, vmax=VMAX, basso=PAL_BASSO, alto=PAL_ALTO):
    """Gradiente in cui il viraggio blu->rosso cade esattamente sulla soglia."""
    p = (soglia - vmin) / (vmax - vmin)
    stops = [(p * k / (len(basso) - 1), c) for k, c in enumerate(basso)]
    stops += [(p + (1 - p) * (k + 1) / len(alto), c) for k, c in enumerate(alto)]
    return LinearSegmentedColormap.from_list("ancorata", stops)


BOUNDS = [-1, -0.4, -0.2, 0, 0.2, SOGLIA, 0.6, 1]
COLORI = ["#08306b", "#2171b5", "#9ecae1", "#f7f7f7", "#fee0d2", "#fc9272", "#99000d"]
ETICHETTE = ["molto servita", "servita", "poco servita", "equilibrata",
             "sotto pressione", f"DESERTO (>{SOGLIA})", "deserto grave (>0,6)"]
CMAP_CLASSI, NORM_CLASSI = ListedColormap(COLORI), BoundaryNorm(BOUNDS, len(COLORI))


def legenda_classi(ax, loc="upper right"):
    ax.legend(handles=[Patch(facecolor=c, label=l) for c, l in zip(COLORI, ETICHETTE)],
              loc=loc, fontsize=8, frameon=True, title="classe di GAP")


# =================== A. ITALIA, LIVELLO SEZIONE ===================
print("\n--- A. Italia, livello sezione ---")
geo = gdf[["gap_score_v2", "geometry"]].copy()
geo["geometry"] = geo.geometry.simplify(150)

# A1 gradiente continuo ancorato
fig, ax = plt.subplots(figsize=(10, 12.5))
geo.plot(column="gap_score_v2", cmap=cmap_ancorata(), vmin=VMIN, vmax=VMAX, ax=ax,
         linewidth=0, missing_kwds={"color": "#eeeeee"}, legend=True,
         legend_kwds={"shrink": 0.5, "pad": 0.01,
                      "label": f"GAP score (rosso sopra {SOGLIA})", "extend": "both"})
ax.set_axis_off()
ax.set_title(f"GAP score per sezione — gradiente ancorato a {SOGLIA}\n"
             "blu = ben servita · bianco = soglia · rosso = deserto" + SUFFISSO_TITOLO, fontsize=13)
salva("A1_italia_gradiente.png")

# A2 classi discrete
fig, ax = plt.subplots(figsize=(10, 12.5))
geo.plot(column="gap_score_v2", cmap=CMAP_CLASSI, norm=NORM_CLASSI, ax=ax,
         linewidth=0, missing_kwds={"color": "#eeeeee"})
ax.set_axis_off()
legenda_classi(ax)
ax.set_title("GAP score per sezione — classi discrete" + SUFFISSO_TITOLO, fontsize=13)
salva("A2_italia_classi.png")

# A3 spotlight ad alto contrasto
d = E[E.gap_score_v2 > SOGLIA]
fig, ax = plt.subplots(figsize=(10, 12.5))
gdf[gdf.gap_score_v2.isna()].plot(color="#fbfbfb", ax=ax, linewidth=0)
E[E.gap_score_v2 <= SOGLIA].plot(color="#eaf0f6", ax=ax, linewidth=0)
d.plot(color="#d7191c", edgecolor="#7f0000", linewidth=0.35, ax=ax)
ax.set_axis_off()
ax.legend(handles=[Patch(facecolor="#d7191c", edgecolor="#7f0000", label=f"deserto (GAP > {SOGLIA})"),
                   Patch(facecolor="#eaf0f6", label="sotto soglia"),
                   Patch(facecolor="#fbfbfb", label="nessun dato")],
          loc="upper right", frameon=True, fontsize=9)
ax.set_title(f"Dove sono i deserti di ricarica (GAP > {SOGLIA})\n"
             f"{len(d):,} sezioni · {d.popg.sum()/1e6:.1f}M residenti in eta' di guida "
             f"({d.popg.sum()/E.popg.sum():.0%} del totale)" + SUFFISSO_TITOLO, fontsize=13)
salva("A3_italia_spotlight.png")

# A3-bis due livelli di gravita'
GRAVE = 0.6
fig, ax = plt.subplots(figsize=(10, 12.5))
gdf[gdf.gap_score_v2.isna()].plot(color="#fbfbfb", ax=ax, linewidth=0)
E[E.gap_score_v2 <= SOGLIA].plot(color="#eef3f8", ax=ax, linewidth=0)
d[d.gap_score_v2 <= GRAVE].plot(color="#fdae61", edgecolor="#e08214", linewidth=0.25, ax=ax)
d[d.gap_score_v2 > GRAVE].plot(color="#a50026", edgecolor="#4d0013", linewidth=0.35, ax=ax)
ax.set_axis_off()
ax.legend(handles=[Patch(facecolor="#a50026", edgecolor="#4d0013", label=f"deserto GRAVE (> {GRAVE})"),
                   Patch(facecolor="#fdae61", edgecolor="#e08214", label=f"deserto ({SOGLIA}–{GRAVE})"),
                   Patch(facecolor="#eef3f8", label="sotto soglia")],
          loc="upper right", frameon=True, fontsize=9)
ax.set_title("Deserti per gravita'\n"
             f"{(d.gap_score_v2>GRAVE).sum():,} sezioni in condizione grave" + SUFFISSO_TITOLO, fontsize=13)
salva("A3bis_italia_gravita.png")

# A4 deserti come punti pesati per popolazione
fig, ax = plt.subplots(figsize=(10, 12.5))
prov_geo.plot(color="#fafafa", edgecolor="#d5d5d5", linewidth=0.35, ax=ax)
sc = ax.scatter(d.px, d.py, s=d.popg / 10, c=d.gap_score_v2, cmap="YlOrRd",
                vmin=SOGLIA, vmax=0.9, alpha=0.55, linewidths=0)
ax.set_axis_off()
ax.set_aspect("equal")
ax.set_title("Deserti pesati per popolazione\n(dimensione = residenti coinvolti)" + SUFFISSO_TITOLO, fontsize=13)
fig.colorbar(sc, ax=ax, shrink=0.5, pad=0.01, label="GAP score", extend="max")
for s_, lab in [(500, "500 ab."), (2000, "2.000 ab.")]:
    ax.scatter([], [], s=s_ / 10, c="#cc4c02", alpha=0.6, label=lab)
ax.legend(scatterpoints=1, loc="upper right", title="popolazione", frameon=True, labelspacing=1.4)
salva("A4_italia_punti.png")


# =================== B. GRIGLIA ESAGONALE ===================
print("\n--- B. Griglia esagonale ---")
ext = (E.px.min(), E.px.max(), E.py.min(), E.py.max())
fig, ax = plt.subplots(figsize=(10, 12.5))
# numeratore e denominatore devono usare gli STESSI bin: stesso extent e gridsize
hb_num = ax.hexbin(E.px, E.py, C=(E.popg * (E.gap_score_v2 > SOGLIA)).values,
                   reduce_C_function=np.sum, gridsize=80, extent=ext, mincnt=1, visible=False)
hb_den = ax.hexbin(E.px, E.py, C=E.popg.values,
                   reduce_C_function=np.sum, gridsize=80, extent=ext, mincnt=1, visible=False)
num, den = hb_num.get_array(), hb_den.get_array()
off = hb_num.get_offsets()
quota = np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)
ax.clear()
sc = ax.scatter(off[:, 0], off[:, 1], c=quota, cmap="YlOrRd", s=22, marker="h",
                vmin=0, vmax=0.7, linewidths=0)
ax.set_aspect("equal")
ax.set_axis_off()
ax.set_title("Quota di popolazione che vive in un deserto\n(zone di ~15 km)" + SUFFISSO_TITOLO, fontsize=13)
fig.colorbar(sc, ax=ax, shrink=0.5, pad=0.01, label="% pop. in un deserto", extend="max")
salva("B_italia_hexbin.png")
print(f"   quota mediana per zona: {np.nanmedian(quota):.1%} | "
      f"zone con oltre meta' pop. scoperta: {(quota>0.5).sum()}")


# =================== C. LIVELLO PROVINCIA ===================
print("\n--- C. Livello provincia ---")
agg = E.groupby("CODPRO").agg(
    nome=("PROVINCIA", "first"), pop=("popg", "sum"),
    gap_medio=("gap_score_v2", lambda s: np.average(s, weights=E.loc[s.index, "popg"])))
agg["pop_deserto"] = E.popg.where(E.gap_score_v2 > SOGLIA, 0).groupby(E.CODPRO).sum()
agg["quota"] = agg.pop_deserto / agg["pop"]
MEDIA_NAZ = agg.pop_deserto.sum() / agg["pop"].sum()
agg["scarto"] = agg.quota - MEDIA_NAZ
P = prov_geo.join(agg)
print(f"   Media nazionale: {MEDIA_NAZ:.1%}  |  50% delle province tra "
      f"{agg.quota.quantile(.25):.1%} e {agg.quota.quantile(.75):.1%}")
print(f"   Province sopra la media: {(agg.quota>MEDIA_NAZ).sum()} · sotto: {(agg.quota<MEDIA_NAZ).sum()}")

# C1 scarto dalla media nazionale
fig, ax = plt.subplots(figsize=(10, 12.5))
P.plot(column="scarto", cmap="RdBu_r", norm=TwoSlopeNorm(vmin=-0.20, vcenter=0, vmax=0.35),
       ax=ax, edgecolor="white", linewidth=0.35, legend=True,
       legend_kwds={"shrink": 0.5, "pad": 0.01,
                    "label": "scarto dalla media nazionale", "extend": "both"})
ax.set_axis_off()
ax.set_title(f"Popolazione in un deserto: scarto dalla media italiana ({MEDIA_NAZ:.1%})\n"
             "blu = meglio della media · rosso = peggio" + SUFFISSO_TITOLO, fontsize=13)
salva("C1_province_scarto.png")

# C2 classi per quantili
qs = list(np.quantile(agg.quota, [0, .10, .25, .40, .60, .75, .90, 1.0]))
qc = ["#2166ac", "#67a9cf", "#d1e5f0", "#fddbc7", "#ef8a62", "#d6604d", "#8b0000"]
fig, ax = plt.subplots(figsize=(10, 12.5))
P.plot(column="quota", cmap=ListedColormap(qc), norm=BoundaryNorm(qs, len(qc)),
       ax=ax, edgecolor="white", linewidth=0.35, legend=True,
       legend_kwds={"shrink": 0.5, "pad": 0.01,
                    "label": "% pop. in un deserto (classi per quantili)"})
ax.set_axis_off()
ax.set_title("Quota di popolazione in un deserto — classi per quantili\n"
             "(ogni colore = stesso numero di province)" + SUFFISSO_TITOLO, fontsize=13)
salva("C2_province_quantili.png")

# C2-bis le 15 province prioritarie
agg["rank"] = agg.quota.rank(ascending=False)
P["top15"] = np.where(agg["rank"] <= 15, agg.quota, np.nan)
fig, ax = plt.subplots(figsize=(10, 12.5))
P.plot(color="#f0f2f5", edgecolor="#cfd4da", linewidth=0.3, ax=ax)
sel = P.dropna(subset=["top15"])
sel.plot(column="top15", cmap="YlOrRd", ax=ax, edgecolor="#333333", linewidth=0.5,
         legend=True, legend_kwds={"shrink": 0.5, "pad": 0.01, "label": "% pop. in un deserto"})
for _, r in sel.iterrows():
    c = r.geometry.representative_point()
    ax.annotate(f"{r['nome']}\n{r.top15:.0%}", (c.x, c.y), fontsize=7.5, ha="center",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
ax.set_axis_off()
ax.set_title("Le 15 province con la quota piu' alta di popolazione scoperta" + SUFFISSO_TITOLO, fontsize=13)
salva("C2bis_province_top15.png")

# C3 simboli proporzionali
fig, ax = plt.subplots(figsize=(10, 12.5))
P.plot(color="#f7f7f7", edgecolor="#cccccc", linewidth=0.3, ax=ax)
cen = P.geometry.representative_point()
sc = ax.scatter(cen.x, cen.y, s=P.pop_deserto / 900, c=P.quota, cmap="YlOrRd",
                vmin=0, vmax=0.5, alpha=0.85, edgecolor="black", linewidths=0.4)
ax.set_axis_off()
ax.set_title("Popolazione scoperta per provincia\n"
             "(area = persone in deserto · colore = quota)" + SUFFISSO_TITOLO, fontsize=13)
fig.colorbar(sc, ax=ax, shrink=0.5, pad=0.01, label="quota di popolazione in deserto", extend="max")
for s_, lab in [(100_000, "100k"), (400_000, "400k")]:
    ax.scatter([], [], s=s_ / 900, c="#fdae6b", edgecolor="k", linewidths=0.4, label=lab)
ax.legend(scatterpoints=1, loc="upper right", title="persone in deserto",
          frameon=True, labelspacing=1.6)
salva("C3_province_simboli.png")
print("\n   Top 8 per QUOTA:")
print(agg.nlargest(8, "quota")[["nome", "quota", "pop_deserto"]].round(3).to_string(index=False))
print("\n   Top 8 per PERSONE coinvolte:")
print(agg.nlargest(8, "pop_deserto")[["nome", "quota", "pop_deserto"]].round(3).to_string(index=False))

# C4 GAP medio provinciale
fig, ax = plt.subplots(figsize=(10, 12.5))
P.plot(column="gap_medio", cmap="RdBu_r", norm=TwoSlopeNorm(vmin=-0.12, vcenter=0, vmax=0.42),
       ax=ax, edgecolor="white", linewidth=0.3, legend=True,
       legend_kwds={"shrink": 0.5, "pad": 0.01, "label": "GAP medio (pesato pop.)", "extend": "both"})
ax.set_axis_off()
ax.set_title("GAP medio per provincia\n"
             "blu = mediamente servita · rosso = mediamente scoperta" + SUFFISSO_TITOLO, fontsize=13)
salva("C4_province_gapmedio.png")


# =================== D. PROVINCIA DI MILANO ===================
print("\n--- D. Provincia di Milano ---")
mil = gdf[gdf.PROVINCIA == "Milano"].copy()
mil_e = mil[mil.gap_score_v2.notna()]
mil_com = mil.dissolve(by="PROCOM")
mil_des = mil_e[mil_e.gap_score_v2 > SOGLIA]
print(f"   Milano: {len(mil_e):,} sezioni con GAP | deserti {len(mil_des):,} "
      f"({len(mil_des)/len(mil_e):.1%}) | popolazione nei deserti {mil_des.popg.sum():,.0f}")

# D1-D2 gradiente + classi
fig, axes = plt.subplots(1, 2, figsize=(20, 9))
mil.plot(column="gap_score_v2", cmap=cmap_ancorata(), vmin=VMIN, vmax=VMAX, ax=axes[0],
         linewidth=0, missing_kwds={"color": "#f0f0f0"}, legend=True,
         legend_kwds={"shrink": 0.6, "label": "GAP score", "extend": "both"})
mil_com.boundary.plot(ax=axes[0], color="#777777", linewidth=0.3)
axes[0].set_title(f"D1 — gradiente ancorato a {SOGLIA}", fontsize=12)
mil.plot(column="gap_score_v2", cmap=CMAP_CLASSI, norm=NORM_CLASSI, ax=axes[1],
         linewidth=0, missing_kwds={"color": "#f0f0f0"})
mil_com.boundary.plot(ax=axes[1], color="#777777", linewidth=0.3)
legenda_classi(axes[1], loc="lower left")
axes[1].set_title("D2 — classi discrete", fontsize=12)
for a in axes:
    a.set_axis_off()
fig.suptitle("Provincia di Milano" + SUFFISSO_TITOLO, fontsize=14, y=1.0)
salva("D12_milano.png")

# D3 spotlight
fig, ax = plt.subplots(figsize=(11, 9.5))
mil[mil.gap_score_v2.isna()].plot(color="#f5f5f5", ax=ax, linewidth=0)
mil_e[mil_e.gap_score_v2 <= SOGLIA].plot(color="#e3ecf5", ax=ax, linewidth=0)
mil_des.plot(column="gap_score_v2", cmap="YlOrRd", vmin=SOGLIA, vmax=0.9, ax=ax, linewidth=0,
             legend=True, legend_kwds={"shrink": 0.6, "label": "GAP (solo deserti)", "extend": "max"})
mil_com.boundary.plot(ax=ax, color="#888888", linewidth=0.35)
ax.set_axis_off()
ax.set_title(f"Milano — spotlight sui deserti (GAP > {SOGLIA})" + SUFFISSO_TITOLO, fontsize=13)
salva("D3_milano_spotlight.png")

# D4 punti pesati + comuni etichettati
top_com = (mil_des.groupby("PROCOM").agg(comune=("COMUNE", "first"),
                                         sezioni=("gap_score_v2", "size"), pop=("popg", "sum"))
           .sort_values("pop", ascending=False))
fig, ax = plt.subplots(figsize=(11, 9.5))
mil_com.plot(color="#f7f9fb", edgecolor="#c8c8c8", linewidth=0.4, ax=ax)
sc = ax.scatter(mil_des.px, mil_des.py, s=mil_des.popg / 3, c=mil_des.gap_score_v2,
                cmap="YlOrRd", vmin=SOGLIA, vmax=0.9, alpha=0.75, edgecolor="white", linewidths=0.2)
for pc, r in top_com.head(6).iterrows():
    c = mil_com.loc[pc].geometry.representative_point()
    ax.annotate(r.comune, (c.x, c.y), fontsize=9, fontweight="bold", ha="center",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.75))
ax.set_axis_off()
ax.set_title("Milano — deserti pesati per popolazione\n"
             "(etichette: i 6 comuni con piu' residenti scoperti)" + SUFFISSO_TITOLO, fontsize=13)
fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.01, label="GAP score", extend="max")
salva("D4_milano_punti.png")
print("\n   Comuni della provincia di Milano con piu' popolazione in deserto:")
print(top_com.head(12).round(0).to_string())

# D5 zoom sul cluster peggiore
peg = mil_des.nlargest(300, "gap_score_v2")
minx, miny, maxx, maxy = peg.total_bounds
mx, my = (maxx - minx) * 0.06, (maxy - miny) * 0.06
box = mil.cx[minx - mx:maxx + mx, miny - my:maxy + my]
fig, ax = plt.subplots(figsize=(12, 10))
box.plot(column="gap_score_v2", cmap=cmap_ancorata(), vmin=VMIN, vmax=VMAX, ax=ax,
         linewidth=0.06, edgecolor="#999999", missing_kwds={"color": "#f0f0f0"}, legend=True,
         legend_kwds={"shrink": 0.6, "label": "GAP score", "extend": "both"})
mil_com.boundary.plot(ax=ax, color="#555555", linewidth=0.5)
peg.boundary.plot(ax=ax, color="black", linewidth=0.5)
for pc, r in top_com.head(8).iterrows():
    c = mil_com.loc[pc].geometry.representative_point()
    if minx - mx < c.x < maxx + mx and miny - my < c.y < maxy + my:
        ax.annotate(r.comune, (c.x, c.y), fontsize=9, fontweight="bold", ha="center",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))
ax.set_xlim(minx - mx, maxx + mx)
ax.set_ylim(miny - my, maxy + my)
ax.set_axis_off()
ax.set_title("Milano — zoom sull'area dei deserti peggiori\n"
             "(contorno nero = 300 sezioni col GAP piu' alto)" + SUFFISSO_TITOLO, fontsize=13)
salva("D5_milano_zoom.png")

print(f"\n=== FATTO: 16 figure salvate in {QUI.name}/ con prefisso '{PREFISSO}' ===")
