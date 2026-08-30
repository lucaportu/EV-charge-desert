"""
Scarica il parco AUTOVETTURE 2025 per provincia e alimentazione da
ACI "Open Parco Veicoli" (opv.aci.it).

opv.aci.it non espone un endpoint scaricabile con una semplice
richiesta HTTP: e' una dashboard Pentaho/CDF interattiva, con i
filtri (Anno, Dimensioni, Categorie) implementati come <select
multiple> nascosti dietro un widget di selezione a checkbox. La
tabella vera e propria vive dentro un <iframe> (Pentaho Launcher) e i
dati gia' calcolati sono accessibili leggendo lo stato interno del
componente CDF (Dashboards.components[...].rawData) via JavaScript,
non con una richiesta diretta al backend (i tentativi di chiamare
direttamente l'endpoint /pentaho/plugin/cda/api/doQuery indovinando i
parametri non hanno funzionato in modo affidabile).

Filtri usati (uguali a quelli impostati manualmente nella sessione
che ha prodotto parco_circolante_2025_ACI_OPV_raw.json):
  Anno = 2025
  Dimensioni = ALIMENTAZIONE, SOLO PROVINCE
  Categorie = AUTOVETTURE (AV)

Richiede: selenium (pip install selenium). Selenium Manager scarica
da solo un Chrome/Chromedriver compatibile se non gia' presenti nel
sistema.

Nota di fragilita': questo script dipende dalla struttura HTML/JS
attuale di opv.aci.it (id dei <select>, nome del componente CDF
"render_TabellaDinamica"). Se ACI aggiorna la dashboard, i selettori
qui sotto potrebbero dover essere adattati.
"""

import sys
from pathlib import Path
import json
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (CONFIG_DIR, DATA_DIR, OUTPUT_DIR, OVERPASS_CACHE_DIR,
                   TOMTOM_KEY_FILE, assicura, gap_score_definitivo, manca, trova)


URL = "http://opv.aci.it/WEBDMCircolante/"
OUTPUT = CONFIG_DIR / "parco_circolante_2025_ACI_OPV_raw.json"

ANNO = "2025"
DIMENSIONI = ["ALIMENTAZIONE", "SOLO PROVINCE"]
CATEGORIA = "AV"  # AUTOVETTURE, vedi legenda.html per le altre sigle


def imposta_select(driver, select_id, valori):
    """Seleziona le opzioni date in un <select multiple> via JS e
    scatena l'evento 'change' affinche' il widget di selezione
    (e la dashboard CDF che vi e' agganciata) si aggiornino."""
    driver.execute_script(
        """
        const sel = document.getElementById(arguments[0]);
        const valori = arguments[1];
        for (const opt of sel.options) {
            opt.selected = valori.includes(opt.value);
        }
        sel.dispatchEvent(new Event('change', {bubbles: true}));
        """,
        select_id, valori,
    )


def main():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "anni-select"))
        )

        imposta_select(driver, "anni-select", [ANNO])
        imposta_select(driver, "dimensioni-select", DIMENSIONI)
        imposta_select(driver, "misure-select", [CATEGORIA])

        driver.find_element(By.XPATH, "//button[contains(., 'Applica')]").click()

        # La tabella vive dentro l'iframe della dashboard Pentaho;
        # attendiamo che il componente abbia finito di caricare i dati
        # (piu' di una sola riga = header/placeholder gia' superato).
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script(
                """
                const iframe = document.querySelector('iframe');
                if (!iframe || !iframe.contentWindow.Dashboards) return false;
                const comp = iframe.contentWindow.Dashboards.components
                    .find(c => c.name === 'render_TabellaDinamica');
                return !!(comp && comp.rawData && comp.rawData.resultset.length > 1);
                """
            )
        )

        raw = driver.execute_script(
            """
            const iframe = document.querySelector('iframe');
            const comp = iframe.contentWindow.Dashboards.components
                .find(c => c.name === 'render_TabellaDinamica');
            return comp.rawData;
            """
        )

        with open(OUTPUT, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)
        print(f"Salvato: {OUTPUT} ({len(raw['resultset'])} righe)")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
