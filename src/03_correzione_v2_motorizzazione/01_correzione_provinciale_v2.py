"""
CORREZIONE v2 DEI TOTALI EV PROVINCIALI — flotte + tasso di motorizzazione
==========================================================================

Questo script NON modifica nulla della pipeline esistente: legge i file di
input gia' presenti in `dati/` e scrive i propri output dentro questa cartella.

--- Il problema ---------------------------------------------------------
Il totale EV per provincia (ACI 2025) e' per provincia di IMMATRICOLAZIONE,
non di circolazione. Alcune province funzionano da "hub di targa" e risultano
con densita' di EV implausibili. La correzione v1 (gia' in produzione) usava
il campo `uso` del parco ACI/MIT 2019 per riconoscere le flotte di noleggio.
Funziona su Trento (89% di EV intestati a societa' di noleggio) ma NON su
Aosta, dove le auto sono intestate come `PROPRIO` da concessionari e societa'
locali: il campo `uso` non le distingue da quelle di un privato.

--- La soluzione: un secondo indicatore ---------------------------------
Il tasso di motorizzazione (auto immatricolate ogni 1.000 residenti in eta' di
guida) intercetta il fenomeno a prescindere da come l'auto e' intestata:
    Italia 993 auto/1.000   |   Trento 2.292 (2,31x)   |   Aosta 2.178 (2,19x)
Aosta e Trento sono le uniche due province oltre quota 2.000 (mediana 989).

--- Salvaguardia contro i falsi positivi --------------------------------
Un'anomalia provinciale isolata di solito segnala un DENOMINATORE sbagliato,
non immatricolazioni gonfiate. Esempio reale: Sud Sardegna risulta a 1,38x, ma
l'intera Sardegna e' a 0,95x -> l'anomalia viene dal crosswalk approssimato
delle province sarde riformate nel 2016 (la popolazione 2011 e' mappata male),
non da un hub di immatricolazione. Correggerla sarebbe un errore.
Per questo una provincia e' "hub" solo se anomala LEI **e** la SUA REGIONE.

--- Regola finale -------------------------------------------------------
Per ogni provincia si calcolano due fattori di ritenzione (quota di EV che
resta alla provincia; piu' basso = correzione piu' forte) e si applica il piu'
severo dei due, MAI la somma (altrimenti Trento verrebbe corretta due volte):

    ritenzione = min( 1 - quota_flotta_2019 ,  1 / indice_motorizzazione )

Gli EV sottratti confluiscono in un unico bacino nazionale e vengono
ridistribuiti in proporzione alla popolazione in eta' di guida: il totale
nazionale resta identico al veicolo (e' una ridistribuzione geografica, non
un taglio).

Output: domanda_provincia_v2_CORRETTA.csv
"""

import sys
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import CONFIG_DIR, OUTPUT_DIR, assicura, gap_score_definitivo, trova



PARCO_RAW = CONFIG_DIR / "parco_circolante_2025_ACI_OPV_raw.json"
QUOTE_FLOTTE = CONFIG_DIR / "quota_flotte_ev_2019_per_provincia.json"
DOMANDA_PROV = trova("domanda_ricarica_2025_per_provincia.csv")
GAP_PARQUET = gap_score_definitivo()
OUTPUT = assicura(OUTPUT_DIR) / "domanda_provincia_v2_CORRETTA.csv"

# --- parametri della regola (espliciti, cosi' sono discutibili e replicabili) ---
SOGLIA_PROVINCIA = 1.25   # oltre +25% sulla media nazionale la provincia e' sospetta
SOGLIA_REGIONE = 1.15     # ...ma serve conferma a livello regionale (anti falso positivo)
MIN_EV_2019 = 200         # sotto questa soglia la quota-flotta 2019 non e' affidabile


def _base(s: str) -> str:
    """Normalizza un nome per il confronto tra fonti diverse."""
    s = str(s).upper().strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.replace("'", " ").replace("-", " ").replace("/", " ")
    return re.sub(r"\s+", " ", s).strip()


# nomi provincia (censimento 2011 / ACI 2019) -> nomi provincia ACI 2025.
# Include la riforma sarda 2016, necessaria per attribuire la regione a
# Sud Sardegna (che nel 2011 non esisteva) e far scattare la salvaguardia.
ALIAS = {
    "VALLE D AOSTA VALLEE D AOSTE": "AOSTA",
    "BOLZANO BOZEN": "BOLZANO",
    "REGGIO DI CALABRIA": "REGGIO CALABRIA",
    "REGGIO NELL EMILIA": "REGGIO EMILIA",
    "MONZA E DELLA BRIANZA": "MONZA BRIANZA",
    "BARLETTA ANDRIA TRANI": "BARLETTA TRANI",
    "FORLI": "FORLI CESENA",
    "PESARO": "PESARO E URBINO",
    "VERBANIA": "VERBANO CUSIO OSSOLA",
    "CARBONIA IGLESIAS": "SUD SARDEGNA",
    "MEDIO CAMPIDANO": "SUD SARDEGNA",
    "OGLIASTRA": "NUORO",
    "OLBIA TEMPIO": "SASSARI",
}


def norm(s: str) -> str:
    b = _base(s)
    return ALIAS.get(b, b)


def carica_parco_totale() -> pd.DataFrame:
    """Parco AUTOVETTURE 2025 per provincia (serve il TOTALE, non solo gli EV)."""
    raw = json.load(open(PARCO_RAW, encoding="utf-8"))
    colonne = [m["colName"].strip() for m in raw["metadata"]]
    df = pd.DataFrame(raw["resultset"], columns=colonne)

    def to_int(x):
        # i numeri arrivano in formato italiano ("734.272") oppure gia' interi
        if isinstance(x, str):
            x = x.strip().replace(".", "")
            return int(x) if x else 0
        return int(x)

    for c in colonne:
        if c not in ("Anno", "Provincia"):
            df[c] = df[c].apply(to_int)
    df = df[~df.Provincia.isin(["Totale", "NON DEFINITO"])].copy()
    df["k"] = df.Provincia.map(norm)
    return df[["k", "Provincia", "Totale", "EL"]]


def main():
    print("=== CORREZIONE v2: flotte + tasso di motorizzazione ===\n")

    parco = carica_parco_totale()
    domanda = pd.read_csv(DOMANDA_PROV)
    domanda["k"] = domanda.Provincia.map(norm)

    quote = json.load(open(QUOTE_FLOTTE, encoding="utf-8"))
    quota_flotta = {norm(k): v["quota_flotta_2019"] for k, v in quote.items()}
    ev_2019 = {norm(k): v["ev_2019"] for k, v in quote.items()}
    quota_naz = (sum(v["ev_flotta_2019"] for v in quote.values())
                 / sum(v["ev_2019"] for v in quote.values()))

    # popolazione in eta' di guida e regione, dalle sezioni eleggibili
    sez = pd.read_parquet(GAP_PARQUET, columns=[
        "SEZ2011", "PROVINCIA", "REGIONE", "popolazione_eta_guida_stimata",
        "flag_eleggibile_EV"])
    sez = sez[sez.flag_eleggibile_EV == True]
    sez["k"] = sez.PROVINCIA.map(norm)
    agg = sez.groupby("k").agg(pop_guida=("popolazione_eta_guida_stimata", "sum"),
                               regione=("REGIONE", "first")).reset_index()

    m = domanda.merge(parco[["k", "Totale"]], on="k").merge(agg, on="k")
    assert len(m) == len(domanda), f"province perse nel merge: {len(domanda)-len(m)}"

    # ---------- indicatore 1: quota di flotta (campo `uso`, ACI/MIT 2019) ----------
    m["quota_flotta"] = m.k.map(quota_flotta)
    m["ev_2019"] = m.k.map(ev_2019)
    m["quota_flotta"] = np.where((m.ev_2019 >= MIN_EV_2019) & m.quota_flotta.notna(),
                                 m.quota_flotta, quota_naz)

    # ---------- indicatore 2: tasso di motorizzazione ----------
    m["auto_per_1000"] = m.Totale / m.pop_guida * 1000
    tasso_naz = m.Totale.sum() / m.pop_guida.sum() * 1000
    m["indice_motorizzazione"] = m.auto_per_1000 / tasso_naz

    # stesso indice calcolato a livello di REGIONE (la salvaguardia)
    reg = (m.groupby("regione")
             .apply(lambda d: d.Totale.sum() / d.pop_guida.sum() * 1000 / tasso_naz))
    m["indice_regione"] = m.regione.map(reg)

    m["hub_immatricolazione"] = (
        (m.indice_motorizzazione > SOGLIA_PROVINCIA)
        & (m.indice_regione > SOGLIA_REGIONE)
        & m.indice_regione.notna()
    )

    # ---------- regola: il piu' severo dei due, mai la somma ----------
    m["ritenzione_uso"] = 1 - m.quota_flotta
    m["ritenzione_motor"] = np.where(m.hub_immatricolazione,
                                     1 / m.indice_motorizzazione, 1.0)
    m["ritenzione"] = np.minimum(m.ritenzione_uso, m.ritenzione_motor)
    m["criterio_applicato"] = np.where(
        m.ritenzione_motor < m.ritenzione_uso, "motorizzazione",
        np.where(m.ritenzione_uso < 1, "uso (flotte)", "nessuno"))

    # ---------- deflazione + redistribuzione a somma costante ----------
    m["ev_residenti"] = m.veicoli_da_ricaricare * m.ritenzione
    bacino = (m.veicoli_da_ricaricare - m.ev_residenti).sum()
    m["ev_da_bacino"] = bacino * m.pop_guida / m.pop_guida.sum()
    m["ev_corretto_v2"] = m.ev_residenti + m.ev_da_bacino

    m["ev_per_1000_originale"] = m.veicoli_da_ricaricare / m.pop_guida * 1000
    m["ev_per_1000_v2"] = m.ev_corretto_v2 / m.pop_guida * 1000

    assert abs(m.ev_corretto_v2.sum() - m.veicoli_da_ricaricare.sum()) < 1.0, \
        "il totale nazionale non e' conservato"

    # ---------- report ----------
    print(f"Tasso di motorizzazione nazionale: {tasso_naz:.0f} auto ogni 1.000 residenti\n")
    print("HUB DI IMMATRICOLAZIONE riconosciuti (provincia E regione anomale):")
    print(m[m.hub_immatricolazione][
        ["Provincia", "auto_per_1000", "indice_motorizzazione", "indice_regione",
         "quota_flotta", "ritenzione", "criterio_applicato"]].round(3).to_string(index=False))

    scartate = m[(m.indice_motorizzazione > SOGLIA_PROVINCIA) & (~m.hub_immatricolazione)]
    if len(scartate):
        print("\nESCLUSE dalla salvaguardia (provincia anomala ma regione normale:")
        print("probabile problema di denominatore/crosswalk, non un hub):")
        print(scartate[["Provincia", "regione", "indice_motorizzazione",
                        "indice_regione"]].round(3).to_string(index=False))

    print(f"\nTotale nazionale: {m.veicoli_da_ricaricare.sum():,.0f} -> "
          f"{m.ev_corretto_v2.sum():,.0f} (conservato)")
    print(f"Bacino ridistribuito: {bacino:,.0f} EV ({bacino/m.veicoli_da_ricaricare.sum():.1%})")

    cambia = (m.ev_per_1000_v2 - m.ev_per_1000_originale).abs() / m.ev_per_1000_originale > 0.05
    print(f"\nProvince che cambiano oltre il 5% rispetto al dato grezzo: {cambia.sum()}")
    print(m[cambia][["Provincia", "ev_per_1000_originale", "ev_per_1000_v2"]]
          .round(0).to_string(index=False))

    colonne_out = ["Provincia", "veicoli_da_ricaricare", "pop_guida", "Totale",
                   "auto_per_1000", "indice_motorizzazione", "indice_regione",
                   "hub_immatricolazione", "quota_flotta", "ritenzione_uso",
                   "ritenzione_motor", "ritenzione", "criterio_applicato",
                   "ev_residenti", "ev_da_bacino", "ev_corretto_v2",
                   "ev_per_1000_originale", "ev_per_1000_v2"]
    m[colonne_out].rename(columns={"veicoli_da_ricaricare": "ev_originale",
                                   "Totale": "parco_auto_totale"}).to_csv(OUTPUT, index=False)
    print(f"\nSalvato: {OUTPUT.name}")


if __name__ == "__main__":
    main()
