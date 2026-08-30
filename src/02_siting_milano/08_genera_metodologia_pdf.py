# -*- coding: utf-8 -*-
"""Genera metodologia_provincia_milano.pdf a partire dal testo di questo
script (nessun dato letto a runtime per il testo: i numeri sono stati
verificati a mano sui risultati reali e incollati qui; le figure invece
sono lette dal disco a ogni rigenerazione). Rigenerare questo file
manualmente se cambia la metodologia o si aggiornano i risultati.

Versione 3 (04/08/2026 sera, definitiva per la condivisione di gruppo):
aggiunge alla v2 (stessa giornata, risultati reali di 05/06/07) le figure
di 09_grafici_presentazione.py e 10_grafico_validazione_controprova.py
(4 esempi in §3-§6, 1 in §7.4), il nuovo §7.4 "Validazione visiva: solo
dentro il confine esatto", i tre limiti emersi dal check dati approfondito
(§8: punteggio di traffico non affidabile come confidenza assoluta, Milano
sotto media di copertura, confronto visivo applicabile solo a 20/74
sezioni), e il nuovo §9 con il rimando alle cartelle grafici/ complete.
"""

from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

OUT_PDF = r"C:\Users\fasanelli michele\OneDrive\Desktop\Progetto4-Master-ProvinciaMilano\metodologia_provincia_milano.pdf"
CARTELLA_PROGETTO = Path(r"C:\Users\fasanelli michele\OneDrive\Desktop\Progetto4-Master-ProvinciaMilano")
CARTELLA_GRAFICI = CARTELLA_PROGETTO / "grafici"
CARTELLA_GRAFICI_VALIDAZIONE = CARTELLA_PROGETTO / "grafici di validazione"

styles = getSampleStyleSheet()
title_style = ParagraphStyle("TitoloDoc", parent=styles["Title"], fontSize=18, leading=22, spaceAfter=6)
subtitle_style = ParagraphStyle("Sottotitolo", parent=styles["Normal"], fontSize=9.5, leading=13,
                                 textColor=colors.HexColor("#444444"), spaceAfter=14)
h1_style = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=13.5, leading=17, spaceBefore=14, spaceAfter=6)
h2_style = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=5)
body_style = ParagraphStyle("Corpo", parent=styles["Normal"], fontSize=9.7, leading=14, alignment=4, spaceAfter=8)
bullet_style = ParagraphStyle("Bullet", parent=body_style, leftIndent=0, spaceAfter=4)
table_header_style = ParagraphStyle("TabHeader", parent=styles["Normal"], fontSize=9.2, leading=12,
                                     textColor=colors.white, fontName="Helvetica-Bold")
table_cell_style = ParagraphStyle("TabCell", parent=styles["Normal"], fontSize=9.2, leading=12.5)
footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, leading=11,
                               textColor=colors.HexColor("#666666"), spaceBefore=16)
caption_style = ParagraphStyle("Didascalia", parent=styles["Normal"], fontSize=8.3, leading=11.5,
                                textColor=colors.HexColor("#666666"), spaceAfter=12, alignment=1)


def p(text):
    return Paragraph(text, body_style)


def immagine(path, larghezza_cm, didascalia):
    """Figura con larghezza fissa e altezza proporzionale (letta dal file al
    momento della generazione, non hardcoded), più didascalia sotto."""
    with PILImage.open(path) as im:
        w_px, h_px = im.size
    larghezza = larghezza_cm * cm
    altezza = larghezza * h_px / w_px
    return [
        Image(str(path), width=larghezza, height=altezza),
        Spacer(1, 4),
        Paragraph(didascalia, caption_style),
    ]


def bullets(items):
    return ListFlowable(
        [ListItem(Paragraph(t, bullet_style), leftIndent=6) for t in items],
        bulletType="bullet", start="•", leftIndent=14, spaceBefore=2, spaceAfter=8,
    )


def tabella(intestazioni, righe, larghezze):
    dati = [[Paragraph(h, table_header_style) for h in intestazioni]]
    for riga in righe:
        dati.append([Paragraph(str(c), table_cell_style) for c in riga])
    t = Table(dati, colWidths=larghezze, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ]))
    return t


story = []

story.append(Paragraph("Metodologia — Modello di siting e validazione, provincia di Milano", title_style))
story.append(Paragraph(
    "Progetto EV Charge Desert | Come si stima quante colonnine servono e dove installarle su scala "
    "provinciale, e come si verifica che il modello funzioni davvero, confrontandolo con colonnine reali "
    "già esistenti", subtitle_style))

# 1. Obiettivo
story.append(Paragraph("1. Obiettivo", h1_style))
story.append(p(
    "Le fasi precedenti del progetto (scraping traffico e POI, siting) sono state sviluppate e verificate "
    "su 50 sezioni di censimento scelte come le più critiche dell'area di Milano. Questa fase estende lo "
    "stesso modello a scala provinciale, con due obiettivi distinti: (1) applicarlo davvero alle sezioni "
    "che ne hanno bisogno — quante colonnine servono e dove installarle — e (2) verificarne l'affidabilità "
    "con una controprova quantitativa, non solo un giudizio qualitativo sulle mappe."))
story.append(p(
    "L'idea della controprova: alcune sezioni della provincia sono oggi servite da colonnine reali già "
    "installate. Se si toglie (solo nella simulazione) quella colonnina e si fa finta che la sezione sia "
    "ancora scoperta, il modello dovrebbe proporre un punto di siting vicino a dove quella colonnina si "
    "trova davvero — altrimenti il criterio usato per scegliere i punti non cattura un segnale reale, solo "
    "un'ipotesi plausibile sulla carta."))

# 2. Perché non l'intera provincia
story.append(Paragraph("2. Perché non l'intera provincia", h1_style))
story.append(p(
    "La provincia di Milano ha 13.557 sezioni di censimento. Il modello, però, serve solo su due gruppi "
    "mirati, non su tutte:"))
story.append(bullets([
    "<b>818 sezioni critiche</b> — gap_score sopra la soglia critica nazionale (metodo del gomito, "
    "soglia = 0,4287): qui il modello va applicato per davvero.",
    "<b>150 sezioni di controprova</b> — per la verifica quantitativa (§7).",
]))
story.append(p(
    "Il campione di controprova richiede una spiegazione più lunga. L'idea iniziale era semplice: prendere "
    "le sezioni oggi servite (con almeno una colonnina entro 500m) che \u201ctornerebbero critiche\u201d se "
    "quella colonnina sparisse, e usarle come banco di prova. Per calcolarlo davvero serve sapere DOVE sono "
    "le colonnine reali — informazione che non era ancora stata usata nella pipeline: è stata trovata nel "
    "dataset <i>pun_colonnine_pulito.csv</i> (72.648 colonnine pubbliche reali con coordinate esatte), già "
    "raccolto per la pipeline principale del progetto ma non ancora incrociato con il modello di siting."))
story.append(p(
    "Ricalcolando con le coordinate reali (non con un campo del dataset nazionale che risultava vuoto per "
    "tutte le sezioni servite, si veda §7 per il dettaglio), è emerso un fatto inatteso: il numero di "
    "sezioni che \u201ctornerebbero critiche\u201d rimuovendo le loro colonnine resta alto (tra 4.360 e "
    "5.391) a qualunque soglia minima di colonnine attuali si usi per filtrare. Non è quindi un effetto di "
    "casi limite (sezioni con una sola colonnina isolata): è strutturale al modo in cui il GAP score tratta "
    "l'offerta di colonnine — il salto da \u201cservita\u201d a \u201cnon servita\u201d è un salto di "
    "percentile enorme, non uno scarto morbido. Serviva comunque scegliere un campione deliberato, non un "
    "filtro \u201cnaturale\u201d: 150 sezioni, campionate in modo che nessun singolo comune domini il "
    "campione (124 comuni distinti rappresentati, su un pool di partenza di oltre 5.000 sezioni concentrato "
    "per metà a Milano città)."))
story.append(p(
    "Totale sezioni target: <b>968</b> (818 + 150) — molto meno delle 13.557 della provincia, ma "
    "sufficienti a coprire entrambi gli obiettivi della fase."))

# 3. Raccolta dati di traffico
story.append(Paragraph("3. Raccolta dati di traffico", h1_style))
story.append(p(
    "Stessa pipeline delle fasi precedenti (TomTom Traffic Flow Vector Tile, zoom 15, congestione = "
    "1 − velocità attuale/velocità a flusso libero, soglia di robustezza ≥5 letture per fidarsi di un "
    "segmento), scalata alle 968 sezioni target: <b>803 tile</b> necessari (contro i 2.404 che "
    "servirebbero per l'intera provincia, e i 63 delle 50 sezioni originali — il conteggio scala con "
    "l'area coperta, non con il numero di sezioni)."))

story.append(Paragraph("3.1 Cadenza adattiva, non fissa", h2_style))
story.append(p(
    "Una cadenza fissa a 5 minuti per l'intera raccolta costerebbe più del doppio della quota mensile "
    "disponibile (200.000 chiamate). La soluzione: <b>5 minuti nelle due fasce di punta</b> (7-10 e "
    "17-20, ora locale italiana — dove il pattern da catturare è concentrato) e <b>30 minuti nel resto "
    "della finestra diurna</b>. Le ore notturne (22-7) sono escluse deliberatamente, non solo per "
    "risparmiare quota: la metrica usata ovunque nel progetto è la congestione MASSIMA per segmento, e di "
    "notte la circolazione è scorrevole quasi ovunque — quelle letture non risulterebbero quasi mai il "
    "massimo di un segmento, il taglio non peggiora la qualità del dato."))
story.append(p(
    "Il fuori-punta è stato regolato due volte durante la campagna reale (dettaglio in §3.4): alzato "
    "temporaneamente a 15 minuti per aumentare la robustezza, poi riportato a 30 minuti dopo che un "
    "incidente di performance del primo giorno aveva già consumato più quota del previsto. Con 30 minuti "
    "fuori punta, la proiezione teorica per l'intera finestra di 48 ore è di <b>193.500 chiamate, 96,8% "
    "della quota mensile</b>, con un margine del 3,2% per richieste fallite da ripetere."))

story.append(Paragraph("3.2 Finestra di campagna: si avvia e si ferma da sola", h2_style))
story.append(p(
    "La raccolta è programmata per iniziare <b>lunedì alle 00:00</b> (ora italiana) e coprire esattamente "
    "48 ore (lunedì e martedì) — un giorno feriale \u201ctipico\u201d, non un giorno scelto a caso che "
    "potrebbe cadere di weekend o a ridosso di una festività. La finestra è scritta esplicitamente nello "
    "script: fuori da quell'intervallo, ogni tentativo di raccolta esce subito senza fare alcuna chiamata. "
    "Conseguenza pratica: il trigger esterno che innesca la raccolta può restare attivo H24 anche con "
    "giorni di anticipo (nessun costo prima che inizi la finestra) e non serve disattivarlo alla fine — la "
    "campagna si interrompe da sola, evitando di sforare la quota mensile per dimenticanza."))

story.append(Paragraph("3.3 Formato di salvataggio", h2_style))
story.append(p(
    "I dati vengono salvati in un file compresso per giorno, non in un unico file che cresce all'infinito: "
    "alla scala di questa raccolta un file unico rischierebbe di diventare troppo grande per essere gestito "
    "comodamente col passare dei giorni."))

story.append(Paragraph("3.4 Esito reale della campagna", h2_style))
story.append(p(
    "La raccolta è partita regolarmente lunedì 03/08/2026 alle 00:00. Nel pomeriggio dello stesso giorno "
    "si è verificato un incidente di performance (un'esecuzione poteva impiegare fino a 10 minuti contro i "
    "5 di intervallo tra un trigger e l'altro, causando esecuzioni accodate e fallimenti durante la prima "
    "punta serale): risolto scaricando i tile in parallelo con una sessione HTTP condivisa, portando la "
    "durata di un'esecuzione da ~600 a 28-48 secondi. L'incidente aveva però già consumato più quota del "
    "previsto, da cui la correzione del fuori-punta descritta in §3.1."))
story.append(p(
    "Un secondo problema, di natura diversa, si è manifestato martedì 04/08 nel pomeriggio: la quota "
    "mensile della chiave TomTom dedicata è stata raggiunta (200.000/200.000, confermato dal pannello "
    "MyTomTom), interrompendo la raccolta reale con circa un giorno di anticipo rispetto alla fine "
    "programmata della finestra di 48 ore. Bilancio finale della raccolta:"))
story.append(tabella(
    ["Giorno", "Esecuzioni", "Copertura oraria (UTC)", "Note"],
    [
        ["Lunedì 03/08", "71", "05:01 – 20:30", "Giornata quasi completa, entrambe le punte catturate"],
        ["Martedì 04/08", "53", "05:01 – 15:10", "Punta mattutina completa, punta serale persa per quota esaurita"],
    ],
    [3.0 * cm, 2.6 * cm, 4.4 * cm, 6.8 * cm],
))
story.append(Spacer(1, 6))
story.append(p(
    "Totale: <b>809.823 righe, 124 esecuzioni</b>, tutte le 968 sezioni target coperte a ogni esecuzione. "
    "Rispetto al disegno originale (2 mattine + 2 sere indipendenti, per la soglia di robustezza ≥5 "
    "letture), il dataset finale copre 2 mattine + circa 1,5 sere: una copertura ridotta ma ancora "
    "utilizzabile — vedi §8 per l'impatto sui risultati."))
story.append(Spacer(1, 8))
story.extend(immagine(
    CARTELLA_GRAFICI / "traffico_san_vittore_olona_152010000007.png", 13.0,
    "Fig. 1 — Congestione massima per segmento robusto (≥5 letture), San Vittore Olona "
    "(SEZ2011 152010000007), una delle sezioni critiche con dati di traffico più ricchi. I 3 "
    "segmenti più critici sono evidenziati ed etichettati."))

# 4. Raccolta POI
story.append(Paragraph("4. Raccolta dati sui punti di interesse (POI)", h1_style))
story.append(p(
    "Stessa metodologia delle fasi precedenti, sulle 968 sezioni target invece delle 50 originali. Il "
    "traffico dice dove passano le auto, non dove possono fermarsi: i POI servono a individuare i luoghi "
    "dove un'auto sosta per un tempo comparabile a una sessione di ricarica."))
story.append(p(
    "Le categorie sono scelte con tre criteri concreti (tempo di sosta comparabile a una ricarica, area "
    "di sosta associata, visite ricorrenti), raggruppate in tre livelli di confidenza:"))
story.append(tabella(
    ["Livello", "Categorie", "Perché"],
    [
        ["1 — parcheggio quasi certo", "distributore, supermercato, centro commerciale",
         "Area dedicata praticamente garantita, precedente reale di installazione colonnine."],
        ["2 — parcheggio dedicato certo", "parcheggio, ufficio/azienda, ospedale",
         "Area di sosta dedicata certa, spesso con permanenza lunga."],
        ["3 — parcheggio plausibile", "palestra/centro sportivo, ristorazione, cinema",
         "Sosta di durata utile, ma l'area di parcheggio non è sempre garantita."],
    ],
    [4.6 * cm, 5.0 * cm, 6.4 * cm],
))
story.append(Spacer(1, 6))
story.append(p(
    "Un POI appartiene a una sezione se cade dentro il suo confine ESATTO, non entro un raggio arbitrario "
    "dal centroide (le sezioni periferiche superano i 600×700 metri: un raggio fisso coprirebbe solo il "
    "centro del poligono). Per la query grezza ai server OpenStreetMap/Overpass si usa invece un rettangolo "
    "di ricerca (bounding box) più largo del confine, non il contorno esatto della sezione: un test diretto "
    "ha mostrato che il filtro poligonale esatto, su un poligono bufferizzato con oltre 100 vertici, porta "
    "il tempo di risposta del server da 1-2 secondi a 30 secondi e oltre (spesso in timeout) — un costo "
    "enorme senza benefici, perché l'assegnazione precisa avviene comunque nello step successivo, sul "
    "confine vero."))
story.append(p(
    "Per la stessa ragione di dipendenza dal PC (§3.2), lo scraping POI — che alla scala di 968 sezioni "
    "richiede più tempo dei pochi minuti sufficienti per le 50 originali — gira anch'esso su "
    "un'esecuzione automatica esterna invece che sul computer dell'utente, così da non fermarsi se il PC "
    "viene spento."))
story.append(p(
    "Risultato reale: <b>968/968 sezioni</b> con almeno un tentativo di raccolta completato, "
    "<b>3.501 POI totali</b> assegnati (17 categorie), <b>709 sezioni</b> con almeno un POI e "
    "<b>259 sezioni</b> a zero POI (mediana 2 POI per sezione) — normale per sezioni periferiche/"
    "residenziali pure, non un errore di raccolta."))
story.append(Spacer(1, 8))
story.extend(immagine(
    CARTELLA_GRAFICI / "poi_san_vittore_olona_152010000007.png", 13.0,
    "Fig. 2 — POI candidati (livello 1-3) dentro il confine esatto della stessa sezione, colorati "
    "per categoria."))

# 5. Quante colonnine servono
story.append(Paragraph("5. Quante colonnine servono", h1_style))
story.append(p(
    "Stessa simulazione delle fasi precedenti (GAP score = rango percentile nazionale della domanda meno "
    "rango percentile nazionale dell'offerta; installare nuove colonnine entro 500m sposta solo il rango "
    "di offerta, la domanda resta invariata), applicata a tutte le 818 sezioni critiche invece che a una "
    "sola sezione scelta come esempio. Per ciascuna sezione si simula l'aggiunta progressiva di colonnine "
    "(0, 1, 2, …) fino a individuare il primo scenario che fa scendere il GAP score sotto la soglia "
    "critica nazionale."))
story.append(p(
    "Questo calcolo non richiede i dati di traffico o POI (usa solo il dataset nazionale del GAP score) "
    "ed è già stato eseguito su dati reali:"))
story.append(tabella(
    ["Colonnine necessarie", "N. sezioni"],
    [["1", "400"], ["2", "344"], ["3", "74"]],
    [8.0 * cm, 8.0 * cm],
))
story.append(Spacer(1, 6))
story.append(p("Nessuna delle 818 sezioni critiche richiede più di 3 colonnine per scendere sotto soglia."))
story.append(Spacer(1, 8))
story.extend(immagine(
    CARTELLA_GRAFICI / "gap_score_san_vittore_olona_152010000007.png", 10.5,
    "Fig. 3 — Impatto di 0-3 nuove colonnine sul GAP score per San Vittore Olona: scende sotto "
    "soglia (0,429) con 3 nuove colonnine, da 0,5631 a 0,3545."))

# 6. Dove installarle
story.append(Paragraph("6. Dove installarle", h1_style))
story.append(p(
    "Stessa metodologia delle fasi precedenti, applicata alle 968 sezioni target. Il criterio è un imbuto "
    "in due fasi, non un punteggio unico che media traffico e POI insieme (il rischio di mediare: il punto "
    "risultante può cadere in un luogo senza senso fisico, né una strada né un'area di sosta)."))
story.append(bullets([
    "<b>Fase 1 — quali punti sono installabili.</b> Solo i POI di livello 1-3 sono candidati: un punto "
    "deve avere un'area di sosta plausibile.",
    "<b>Fase 2 — quali candidati hanno domanda reale confermata.</b> Il traffico vicino a ciascun "
    "candidato fa da classifica, con un peso che decresce linearmente con la distanza (zero oltre 300m) "
    "invece di un cutoff netto — un cutoff netto è fragile: un candidato molto vicino alla domanda reale "
    "può sparire dalla classifica solo per un arrotondamento sulla soglia.",
]))
story.append(p(
    "Una selezione finale scarta i candidati troppo vicini a uno già scelto nella stessa sezione "
    "(diversificazione spaziale, entro 100m), per evitare di raccomandare due punti che sono di fatto lo "
    "stesso incrocio."))
story.append(p(
    "Punto importante per la validazione (§7): tra le categorie di POI usate come candidati non compare "
    "mai \u201ccolonnina di ricarica\u201d. Il modello è quindi strutturalmente cieco alle colonnine "
    "esistenti — non serve nessuna maschera aggiuntiva per la controprova."))
story.append(p("Risultato reale sulle 968 sezioni target:"))
story.append(tabella(
    ["Esito", "N. sezioni", "% sul totale del gruppo"],
    [
        ["Sezioni critiche con almeno un candidato", "271 / 818", "33%"],
        ["Sezioni di controprova con almeno un candidato", "74 / 150", "49%"],
        ["Totale sezioni target con almeno un candidato", "345 / 968", "35,6%"],
    ],
    [7.6 * cm, 4.0 * cm, 4.4 * cm],
))
story.append(Spacer(1, 6))
story.append(p(
    "Il file finale (665 righe, fino a 3 candidati per sezione) copre quindi poco più di un terzo delle "
    "sezioni target. Il motivo, verificato sul funnel completo: 292 sezioni non hanno nessun POI di "
    "livello 1-3 nel confine (il vincolo più stretto), 220 hanno POI ma nessun segmento di traffico "
    "abbastanza robusto (≥5 letture) nello stesso poligono, e 111 hanno sia POI sia traffico robusto ma "
    "sempre a più di 300m di distanza. Verificato anche che alzare la soglia di distanza a 500m o "
    "abbassare la robustezza traffico a ≥3 letture recupera solo un margine molto piccolo (rispettivamente "
    "+5 e +23 sezioni su 968): il limite di copertura è strutturale, legato soprattutto alla disponibilità "
    "di POI idonei, non un problema di parametri regolabili — vedi §8."))
story.append(p(
    "Guardando quali categorie vincono più spesso (rank 1) tra i 345 candidati: il parcheggio domina "
    "(232/345, 67%), seguito da ristorazione (77, 22%). Per livello di confidenza il quadro è meno "
    "rassicurante: il livello 1 (“parcheggio quasi certo” — distributore/supermercato/mall) vince "
    "solo <b>18/345 volte (5%)</b>, il livello 2 domina con 247/345 (72%) e il livello 3 (“plausibile"
    "”) vince comunque 80/345 volte (23%) — il modello si affida spesso a candidati di confidenza "
    "intermedia o bassa per semplice assenza di alternative migliori nella sezione, non perché siano "
    "oggettivamente i più affidabili."))
story.append(p(
    "Un'osservazione dal dettaglio geografico: <b>Milano città ha una copertura sotto la media "
    "provinciale</b> — 130 sezioni target nel comune, solo 25 con un candidato (19,2%, contro il 35,6% "
    "medio). L'ipotesi più plausibile non è una carenza di POI (Milano è densissima), ma la granularità "
    "delle sezioni di censimento: nella griglia urbana fitta della città le sezioni sono molto più piccole "
    "che altrove, quindi anche con molti POI nei dintorni pochi cadono esattamente dentro il confine "
    "stretto — lo stesso vale per i segmenti di traffico robusti entro 300m."))
story.append(Spacer(1, 8))
story.extend(immagine(
    CARTELLA_GRAFICI / "siting_san_vittore_olona_152010000007.png", 13.0,
    "Fig. 4 — Punti di siting raccomandati (rank 1-3) per San Vittore Olona, con il contesto che li "
    "genera: segmenti di traffico robusti e POI candidati non scelti, in grigio/rosa chiaro sullo sfondo."))

# 7. Validazione a controprova
story.append(Paragraph("7. Validazione a controprova", h1_style))
story.append(p(
    "È la parte nuova di questa fase rispetto a quelle precedenti: una verifica quantitativa, non solo un "
    "giudizio visivo sulle mappe."))

story.append(Paragraph("7.1 Come si costruisce il campione", h2_style))
story.append(p(
    "Punto di partenza: le sezioni oggi servite da almeno una colonnina reale entro 500m. Per ciascuna si "
    "simula la rimozione delle colonnine locali e si ricalcola il GAP score usando come nuova \u201cdistanza "
    "dalla colonnina più vicina\u201d quella verso la colonnina reale più vicina rimasta fuori dal raggio di "
    "500m (calcolata sulle coordinate esatte di <i>pun_colonnine_pulito.csv</i>, non su un campo del "
    "dataset nazionale che per queste sezioni risultava sistematicamente vuoto — la distanza dalla "
    "colonnina più vicina viene normalmente calcolata solo per le sezioni già scoperte, non serviva finora "
    "per quelle servite). Le sezioni il cui GAP score simulato risale sopra la soglia critica formano il "
    "pool eleggibile; da questo pool si campionano le 150 sezioni di controprova, distribuite su 124 "
    "comuni diversi (§2)."))

story.append(Paragraph("7.2 Come si valuta il modello", h2_style))
story.append(p(
    "Per ciascuna delle 150 sezioni di controprova, si applica il modello di siting (§6) esattamente come "
    "per una sezione critica qualunque — con la sola differenza che qui esiste già una risposta nota (dove "
    "sta davvero la colonnina rimossa). Si misura la distanza in metri tra il punto raccomandato dal "
    "modello (il primo in classifica) e la colonnina reale più vicina, aggregata su tutte le sezioni "
    "valutate: mediana, e percentuale di casi entro 100m, 250m e 500m. Si registra anche la distanza del "
    "candidato migliore tra i primi 3 raccomandati, per distinguere \u201cil primo in classifica è quello "
    "giusto\u201d da \u201cil modello ci arriva vicino, ma non lo mette al primo posto\u201d."))
story.append(p(
    "Perché è una prova valida e non circolare: il modello non riceve mai in input la posizione delle "
    "colonnine reali (§6) — se nonostante questo i punti raccomandati cadono vicino a dove le colonnine "
    "sono state installate per davvero, è un'evidenza indipendente che il criterio di siting cattura un "
    "segnale reale legato alla domanda di ricarica, non solo un'ipotesi plausibile sulla carta."))

story.append(Paragraph("7.3 Risultati reali", h2_style))
story.append(p(
    "Delle 150 sezioni di controprova, <b>74 hanno ottenuto almeno un candidato</b> dal modello di siting "
    "(§6) e sono quindi le uniche confrontabili con la colonnina reale rimossa — le altre 76 non hanno "
    "nessun punto raccomandato per mancanza di POI idonei o traffico robusto abbastanza vicino (stesso "
    "limite di copertura descritto in §6), non per un errore nella validazione."))
story.append(tabella(
    ["Metrica", "Rank 1 (scelta migliore)", "Migliore tra i primi 3"],
    [
        ["Distanza mediana", "284 m", "233 m"],
        ["Distanza media", "302 m", "—"],
        ["Entro 100 m", "14%", "22%"],
        ["Entro 250 m", "38%", "53%"],
        ["Entro 500 m", "86%", "91%"],
    ],
    [5.4 * cm, 5.4 * cm, 5.4 * cm],
))
story.append(Spacer(1, 6))
story.append(p(
    "Lettura dei risultati: il modello individua il \u201cquartiere giusto\u201d in modo solido (86-91% "
    "dei casi entro 500m dalla colonnina reale) ma non il punto esatto (14-22% entro 100m). È un risultato "
    "ragionevole per un modello che non vede mai le colonnine esistenti e si basa solo su POI e pattern di "
    "traffico: la distanza tipica di 250-300m è compatibile con l'incertezza intrinseca del criterio "
    "(un incrocio o un isolato di differenza), non con un errore di sistema — anche i primi 3 candidati "
    "insieme, non solo il primo, mostrano lo stesso ordine di grandezza."))
story.append(p(
    "Un approfondimento ha verificato se il punteggio di traffico (quanto il modello è “sicuro” della sua "
    "scelta) predice davvero l'accuratezza posizionale: la correlazione tra <i>punteggio_traffico</i> e la "
    "distanza reale dell'errore, sulle 74 sezioni, è debolissima (<b>r = -0,12</b>). Confermato con un "
    "numero concreto: in <b>24 sezioni su 74 (32%)</b> il candidato di rank 1 (il punteggio di traffico più "
    "alto) NON è il più vicino alla colonnina reale tra i primi 3 — un altro candidato, con punteggio più "
    "basso, sarebbe stato geograficamente più corretto. Il punteggio di traffico va quindi letto come un "
    "criterio di ranking tra candidati della stessa sezione, non come una misura di confidenza assoluta "
    "sulla correttezza del punto — vedi §8."))

story.append(Paragraph("7.4 Validazione visiva: solo dentro il confine esatto", h2_style))
story.append(p(
    "Il dataset delle colonnine rimosse nella controprova assegna una colonnina reale a una sezione se "
    "cade entro 500m dal suo confine (stessa logica di <i>offerta_colonnine_500m</i>, usata ovunque nel "
    "GAP score), non se cade dentro il poligono stesso. Per un confronto visivo punto-per-punto, più diretto "
    "di una tabella aggregata, ha senso restringersi alle sole colonnine reali che cadono davvero dentro il "
    "confine esatto — “se ne spengo N dentro la sezione, ne accendo N con il modello”."))
story.append(p(
    "Verificato: solo <b>20 sezioni di controprova su 74 (27%)</b> hanno almeno una colonnina reale dentro "
    "il proprio confine esatto (il massimo osservato è 2, anche per la sezione con più colonnine in "
    "assoluto nel buffer, Carugate, che ne ha 19 nel raggio di 500m ma solo 2 dentro il confine). Per "
    "queste 20 sezioni è stata generata una mappa dedicata (colonnine reali in rosso vs punti raccomandati "
    "in verde, con la distanza alla colonnina più vicina in etichetta): <b>mediana delle 20 distanze "
    "mediane per sezione 186m</b>, media 204m, dal minimo di Carpiano (33m) al massimo di Trezzo sull'Adda "
    "(464m — sezione molto allungata, dove le uniche colonnine dentro il confine sono lontane dai punti "
    "raccomandati). Questi numeri non sono direttamente confrontabili con la tabella di §7.3 (che usa il "
    "pool più ampio del buffer 500m su tutte le 74 sezioni): vanno letti come un secondo controllo "
    "illustrativo, coerente nell'ordine di grandezza col risultato aggregato, non come sostituto."))
story.append(Spacer(1, 8))
story.extend(immagine(
    CARTELLA_GRAFICI_VALIDAZIONE / "controprova_carpiano_150500000002.png", 12.5,
    "Fig. 5 — Carpiano (SEZ2011 150500000002), il caso con il match più preciso tra le 20 sezioni "
    "validabili: colonnine reali dentro il confine esatto (rosso) vs punti raccomandati dal modello "
    "(verde), mai avendo visto le colonnine reali."))

# 8. Limiti e uso corretto
story.append(Paragraph("8. Limiti e uso corretto", h1_style))
story.append(bullets([
    "Il campione di controprova <b>effettivamente valutabile è di 74 sezioni su 150</b> (non l'intero "
    "campione disegnato in §2), perché il modello propone un candidato solo per una sezione su tre in "
    "media — vedi il punto successivo. I risultati vanno letti come un'indicazione affidabile ma non "
    "esaustiva della bontà del modello, su un campione più piccolo del previsto.",
    "<b>La copertura del siting è strutturalmente limitata</b>: solo 345/968 sezioni target (35,6%) "
    "ottengono almeno un candidato. Verificato che il collo di bottiglia principale è l'assenza di POI di "
    "livello 1-3 nel confine della sezione (292 sezioni su 968), non la soglia di robustezza del traffico "
    "né la distanza massima di 300m (entrambe testate con soglie più permissive, con guadagni marginali).",
    "<b>La quota mensile della chiave TomTom dedicata si è esaurita</b> nel pomeriggio del secondo giorno "
    "di raccolta (§3.4), interrompendo la campagna con un giorno di anticipo: il dataset finale copre 2 "
    "mattine di punta ma solo 1,5 sere di punta invece delle 2 previste. Non invalida i risultati (la "
    "soglia di robustezza ≥5 letture è comunque rispettata ovunque venga usata), ma riduce il numero di "
    "picchi indipendenti osservati rispetto al disegno originale.",
    "Il modello non vede mai le colonnine esistenti, ma un confondimento resta possibile: un'area già "
    "scelta in passato per installare una colonnina spesso ha anche più POI in generale (più parcheggi, "
    "più negozi) — una correlazione di sfondo che nessun disegno sperimentale di questo tipo può "
    "eliminare del tutto.",
    "I POI vengono da OpenStreetMap, una fonte volontaria: la copertura è tipicamente meno completa fuori "
    "dai grandi centri urbani (verificato in una fase precedente: un centro fitness locale realmente "
    "esistente, assente dalla mappa).",
    "Il calcolo di \u201cquante colonnine servono\u201d (§5) modifica solo la componente di offerta della "
    "sezione simulata, lasciando invariata la domanda: misura un effetto sul rango percentile nazionale, "
    "non una stima diretta della domanda fisica di ricarica soddisfatta.",
    "Il siting (§6) raccomanda i punti migliori TRA i candidati disponibili in una sezione, non garantisce "
    "che ogni sezione ne abbia: dipende dalla presenza di POI idonei e di traffico robusto abbastanza "
    "vicino.",
    "<b>Il punteggio di traffico non è una misura di confidenza assoluta</b> (§7.3): correlazione debole "
    "con l'errore posizionale reale (r=-0,12) e, nel 32% delle sezioni di controprova, il rank 1 non è il "
    "candidato più vicino alla colonnina reale tra i primi 3. Va usato per confrontare candidati "
    "all'interno della stessa sezione, non per giudicare quanto ci si può fidare di una raccomandazione.",
    "<b>Milano città ha una copertura di siting sotto la media</b> (19,2% contro il 35,6% provinciale, §6), "
    "verosimilmente per la granularità fine delle sezioni di censimento urbane, non per carenza di POI.",
    "<b>Il confronto visivo “dentro il confine esatto” (§7.4) è applicabile solo a 20 sezioni di controprova "
    "su 74</b>: la maggioranza delle colonnine reali usate nella validazione aggregata di §7.3 si trova "
    "fuori dal poligono della sezione, nel buffer di 500m — un limite del dataset di origine, non del "
    "modello di siting.",
]))

# 9. Materiale grafico supplementare
story.append(Paragraph("9. Materiale grafico supplementare", h1_style))
story.append(p(
    "Le figure di questo documento sono un campione ridotto, scelto per illustrare la metodologia. Il set "
    "completo — generato con gli script <i>SCRIPT/09_grafici_presentazione.py</i> e "
    "<i>SCRIPT/10_grafico_validazione_controprova.py</i> del repository, entrambi rieseguibili su dati "
    "aggiornati — comprende:"))
story.append(bullets([
    "<b>8 grafici</b> (traffico, POI, siting, impatto sul GAP score) per le due sezioni critiche di "
    "esempio, San Vittore Olona e Mediglia — cartella <i>grafici/</i>.",
    "<b>20 grafici di validazione a controprova</b> (§7.4), una per ciascuna delle sezioni con almeno una "
    "colonnina reale dentro il confine esatto — cartella <i>“grafici di validazione/”</i>.",
]))
story.append(p(
    "Entrambe le cartelle sono nel repository "
    "<i>github.com/sfasanelli-svg/Progetto4-Master</i>, insieme a tutti i CSV di output citati in "
    "questo documento (<i>quante_colonnine_critiche.csv</i>, <i>candidati_siting_provincia.csv</i>, "
    "<i>validazione_controprova.csv</i>)."))

story.append(Paragraph(
    "Progetto EV Charge Desert — documento generato a supporto della documentazione di gruppo.",
    footer_style))

doc = SimpleDocTemplate(
    OUT_PDF, pagesize=A4,
    topMargin=1.8 * cm, bottomMargin=1.8 * cm, leftMargin=2.0 * cm, rightMargin=2.0 * cm,
)
doc.build(story)
print(f"Salvato: {OUT_PDF}")
