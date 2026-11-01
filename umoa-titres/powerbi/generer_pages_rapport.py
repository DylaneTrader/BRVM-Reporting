# -*- coding: utf-8 -*-
"""
Génère (ou régénère) les pages et visuels du rapport Power BI au format PBIR
(dossier « Reporting BI.Report/definition/pages »).

Pourquoi un générateur ? Le format PBIR décrit chaque visuel dans un fichier
JSON verbeux. Les produire par script garantit une structure cohérente et
permet de reconstruire tout le rapport à l'identique. Le modèle sémantique
(tables, mesures) et le thème ne sont PAS touchés ici.

Usage : python umoa-titres/powerbi/generer_pages_rapport.py
"""
import json
from pathlib import Path

REPORT = Path(__file__).resolve().parent / "Reporting BI.Report"
PAGES_DIR = REPORT / "definition" / "pages"

SCH_VISUAL = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.4.0/schema.json"
SCH_PAGE = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
SCH_PAGES = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json"

NAVY = "#08306B"
BLEU = "#0B5CAB"
BLEU_CLAIR = "#1C86D1"
GRIS = "#5B6B8C"
FONT = "'Segoe UI', wf_segoe-ui_normal, helvetica, arial, sans-serif"

# ---------- helpers bas niveau ----------

def lit(v):
    return {"expr": {"Literal": {"Value": v}}}

def lit_str(s):
    return lit("'" + s.replace("'", "''") + "'")

def lit_num(x):
    return lit(f"{x}D")

def lit_bool(b):
    return lit("true" if b else "false")

def solid(color_literal):
    return {"solid": {"color": color_literal}}

def col_field(entity, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}

def measure_field(entity, prop):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}

def proj(field, entity, prop, active=False):
    p = {"field": field, "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}
    if active:
        p["active"] = True
    return p

def pcol(entity, prop, active=False):
    return proj(col_field(entity, prop), entity, prop, active)

def pmeasure(entity, prop):
    return proj(measure_field(entity, prop), entity, prop)

def container(name, x, y, w, h, visual, z=0, tab=0):
    return {
        "$schema": SCH_VISUAL,
        "name": name,
        "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": tab},
        "visual": visual,
    }

def title_obj(text, size=12, color=NAVY):
    return {"title": [{"properties": {
        "show": lit_bool(True),
        "text": lit_str(text),
        "fontColor": solid(lit_str(color)),
        "fontSize": lit_num(size),
        "titleWrap": lit_bool(False),
    }}]}

def datapoint_color(color):
    return {"dataPoint": [{"properties": {"fill": solid(lit_str(color))}}]}

# ---------- builders de visuels ----------

def textbox(name, x, y, w, h, runs, bg=None, align="left", z=0, tab=0):
    vis = {
        "visualType": "textbox",
        "objects": {"general": [{"properties": {"paragraphs": [
            {"textRuns": runs, "horizontalTextAlignment": align}
        ]}}]},
        "drillFilterOtherVisuals": True,
    }
    if bg:
        vis["visualContainerObjects"] = {"background": [{"properties": {
            "show": lit_bool(True),
            "color": solid(lit_str(bg)),
            "transparency": lit_num(0),
        }}]}
    return container(name, x, y, w, h, vis, z, tab)

def run(value, size=14, bold=False, color="#FFFFFF"):
    style = {"fontSize": f"{size}px", "color": color, "fontFamily": FONT}
    if bold:
        style["fontWeight"] = "bold"
    return {"value": value, "textStyle": style}

def card(name, x, y, w, h, entity, measure, tab=0):
    vis = {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [pmeasure(entity, measure)]}}},
        "objects": {
            "labels": [{"properties": {
                "color": solid(lit_str(NAVY)),
                "fontSize": lit_num(26),
                "bold": lit_bool(True),
            }}],
            "categoryLabels": [{"properties": {
                "show": lit_bool(True),
                "color": solid(lit_str(GRIS)),
                "fontSize": lit_num(10),
            }}],
        },
        "drillFilterOtherVisuals": True,
    }
    return container(name, x, y, w, h, vis, tab=tab)

def chart(name, x, y, w, h, vtype, roles, title=None, color=None, tab=0):
    queryState = dict(roles)  # chaque rôle est déjà {"projections": [...]}
    objects = {}
    if title:
        objects.update(title_obj(title))
    if color:
        objects.update(datapoint_color(color))
    vis = {
        "visualType": vtype,
        "query": {"queryState": queryState},
        "drillFilterOtherVisuals": True,
    }
    if objects:
        vis["objects"] = objects
    return container(name, x, y, w, h, vis, tab=tab)

def slicer(name, x, y, w, h, entity, prop, title=None, tab=0):
    objects = {}
    if title:
        objects.update(title_obj(title, size=11))
    vis = {
        "visualType": "slicer",
        "query": {"queryState": {"Values": {"projections": [pcol(entity, prop)]}}},
        "drillFilterOtherVisuals": True,
    }
    if objects:
        vis["objects"] = objects
    return container(name, x, y, w, h, vis, tab=tab)

def table(name, x, y, w, h, projections, title=None, tab=0):
    objects = {}
    if title:
        objects.update(title_obj(title))
    vis = {
        "visualType": "tableEx",
        "query": {"queryState": {"Values": {"projections": projections}}},
        "drillFilterOtherVisuals": True,
    }
    if objects:
        vis["objects"] = objects
    return container(name, x, y, w, h, vis, tab=tab)

def scatter(name, x, y, w, h, details, x_field, y_field, size_field=None, title=None, tab=0):
    """Nuage de points : X/Y/Size = mesures, Details = colonne (granularité)."""
    roles = {
        "Category": {"projections": [details]},
        "X": {"projections": [x_field]},
        "Y": {"projections": [y_field]},
    }
    if size_field:
        roles["Size"] = {"projections": [size_field]}
    objects = {}
    if title:
        objects.update(title_obj(title))
    vis = {
        "visualType": "scatterChart",
        "query": {"queryState": roles},
        "drillFilterOtherVisuals": True,
    }
    if objects:
        vis["objects"] = objects
    return container(name, x, y, w, h, vis, tab=tab)


def header(page_id, titre, sous_titre):
    """Bandeau navy + sous-titre gris."""
    v = []
    v.append(textbox(f"{page_id}_hdr", 16, 16, 1248, 56,
                     [run(titre, size=24, bold=True, color="#FFFFFF")],
                     bg=NAVY))
    v.append(textbox(f"{page_id}_sub", 16, 76, 1248, 24,
                     [run(sous_titre, size=12, bold=False, color=GRIS)]))
    return v

# ---------- écriture ----------

def write_page(page_id, display_name, order, visuals):
    pdir = PAGES_DIR / page_id
    (pdir / "visuals").mkdir(parents=True, exist_ok=True)
    page = {
        "$schema": SCH_PAGE,
        "name": page_id,
        "displayName": display_name,
        "displayOption": "FitToPage",
        "height": 720,
        "width": 1280,
    }
    (pdir / "page.json").write_text(json.dumps(page, indent=2, ensure_ascii=False), encoding="utf-8")
    for vis in visuals:
        vdir = pdir / "visuals" / vis["name"]
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "visual.json").write_text(json.dumps(vis, indent=2, ensure_ascii=False), encoding="utf-8")
    return page_id


MS = "Marché secondaire"
CAL = "Calendrier"
CT = "Courbes de taux"
BR = "BRVM Obligations"
M = "Mesures"
D = "Dates"
CP = "Courbes pente"

# Les noms de visuels sont déterministes : le script écrase les fichiers en
# place, sans rien supprimer (évite tout problème de verrou OneDrive/Power BI).
# IMPORTANT : fermer le rapport dans Power BI Desktop avant de régénérer.
# Pour retirer un visuel du design, supprimez son dossier à la main puis relancez.
pages_order = []

# ===================== PAGE 1 — ACCUEIL =====================
pid = "8a77cf6ff99605e409b3"
v = header(pid, "Rapport de marché — Titres publics UEMOA & BRVM",
           "CGF Gestion · Tableau de bord destiné aux gestionnaires de portefeuilles")
v.append(card(f"{pid}_maj", 1004, 20, 260, 48, M, "Texte mise à jour"))
kpis = [
    ("Volume global (Mds FCFA)", "kpi1"),
    ("Nb transactions", "kpi2"),
    ("Rendement moyen pondéré", "kpi3"),
    ("Nb émissions à venir", "kpi4"),
    ("Nb obligations cotées", "kpi5"),
]
cx = 16
for measure, key in kpis:
    v.append(card(f"{pid}_{key}", cx, 116, 240, 110, M, measure))
    cx += 250
v.append(chart(f"{pid}_line", 16, 244, 616, 220, "lineChart",
               {"Category": {"projections": [pcol(D, "Année")]},
                "Y": {"projections": [pmeasure(M, "Volume global (Mds FCFA)")]}},
               title="Volume échangé par année (Mds FCFA)", color=BLEU))
v.append(chart(f"{pid}_bar", 648, 244, 616, 220, "clusteredBarChart",
               {"Category": {"projections": [pcol(MS, "Émetteur")]},
                "Y": {"projections": [pmeasure(M, "Volume global (Mds FCFA)")]}},
               title="Volume échangé par émetteur (Mds FCFA)", color=BLEU))
v.append(chart(f"{pid}_bar2", 16, 476, 616, 220, "clusteredColumnChart",
               {"Category": {"projections": [pcol(MS, "Émetteur")]},
                "Y": {"projections": [pmeasure(M, "Rendement moyen pondéré")]}},
               title="Rendement moyen pondéré par émetteur", color=BLEU_CLAIR))
v.append(chart(f"{pid}_donut", 648, 476, 616, 220, "donutChart",
               {"Category": {"projections": [pcol(MS, "Instrument")]},
                "Y": {"projections": [pmeasure(M, "Volume global (Mds FCFA)")]}},
               title="Répartition du volume par instrument"))
pages_order.append(write_page(pid, "Accueil", 0, v))

# ===================== PAGE 2 — MARCHÉ SECONDAIRE =====================
pid = "c1000000000000000002"
v = header(pid, "Marché secondaire des titres publics",
           "Transactions, volumes et rendements — source UMOA-Titres")
v.append(slicer(f"{pid}_slc_annee", 16, 116, 200, 120, D, "Année", title="Année"))
v.append(slicer(f"{pid}_slc_pays", 16, 244, 200, 220, MS, "Émetteur", title="Émetteur"))
v.append(slicer(f"{pid}_slc_instr", 16, 472, 200, 160, MS, "Instrument", title="Instrument"))
v.append(chart(f"{pid}_line", 232, 116, 1032, 240, "lineChart",
               {"Category": {"projections": [pcol(D, "Année-Mois")]},
                "Y": {"projections": [pmeasure(M, "Volume global (Mds FCFA)")]}},
               title="Évolution du volume échangé (Mds FCFA)", color=BLEU))
v.append(chart(f"{pid}_bar", 232, 364, 508, 260, "clusteredBarChart",
               {"Category": {"projections": [pcol(MS, "Émetteur")]},
                "Y": {"projections": [pmeasure(M, "Rendement moyen pondéré")]}},
               title="Rendement moyen pondéré par émetteur", color=BLEU_CLAIR))
v.append(table(f"{pid}_tbl", 756, 364, 508, 260,
               [pcol(MS, "Émetteur"), pcol(MS, "Instrument"),
                pmeasure(M, "Volume global (Mds FCFA)"),
                pmeasure(M, "Rendement moyen pondéré"),
                pmeasure(M, "Nb transactions")],
               title="Détail par émetteur / instrument"))
pages_order.append(write_page(pid, "Marché secondaire", 1, v))

# ===================== PAGE 3 — COURBES DE TAUX =====================
pid = "c1000000000000000003"
v = header(pid, "Courbes des taux des émetteurs UEMOA",
           "Taux zéro coupon et taux après lissage par maturité — source UMOA-Titres")
v.append(slicer(f"{pid}_slc_pays", 16, 116, 200, 260, CT, "Pays", title="Pays"))
v.append(slicer(f"{pid}_slc_date", 16, 384, 200, 240, CT, "Date", title="Date de publication"))
v.append(chart(f"{pid}_curve", 232, 116, 1032, 300, "lineChart",
               {"Category": {"projections": [pcol(CT, "Maturité (années)")]},
                "Series": {"projections": [pcol(CT, "Pays")]},
                "Y": {"projections": [pmeasure(M, "Taux dernière courbe")]}},
               title="Courbe des taux — dernière publication (par pays)"))
v.append(chart(f"{pid}_evo", 232, 424, 508, 200, "lineChart",
               {"Category": {"projections": [pcol(D, "Année-Mois")]},
                "Series": {"projections": [pcol(CT, "Pays")]},
                "Y": {"projections": [pmeasure(M, "Taux après lissage moyen")]}},
               title="Évolution du taux moyen par pays"))
v.append(table(f"{pid}_tbl", 756, 424, 508, 200,
               [pcol(CT, "Pays"), pcol(CT, "Maturité"),
                pcol(CT, "Taux zéro coupon"), pcol(CT, "Taux après lissage")],
               title="Détail de la courbe"))
pages_order.append(write_page(pid, "Courbes de taux", 2, v))

# ===================== PAGE 4 — CALENDRIER DES ÉMISSIONS =====================
pid = "c1000000000000000004"
v = header(pid, "Calendrier des émissions",
           "Émissions passées et à venir par pays et instrument — source UMOA-Titres")
v.append(slicer(f"{pid}_slc_statut", 16, 116, 200, 120, CAL, "Statut", title="Statut"))
v.append(slicer(f"{pid}_slc_pays", 16, 244, 200, 220, CAL, "Pays", title="Pays"))
v.append(slicer(f"{pid}_slc_annee", 16, 472, 200, 152, CAL, "Année", title="Année"))
v.append(chart(f"{pid}_bar_pays", 232, 116, 508, 240, "clusteredColumnChart",
               {"Category": {"projections": [pcol(CAL, "Pays")]},
                "Y": {"projections": [pmeasure(M, "Nb émissions total")]}},
               title="Nombre d'émissions par pays", color=BLEU))
v.append(chart(f"{pid}_bar_instr", 756, 116, 508, 240, "clusteredBarChart",
               {"Category": {"projections": [pcol(CAL, "Instrument")]},
                "Y": {"projections": [pmeasure(M, "Nb émissions total")]}},
               title="Nombre d'émissions par instrument", color=BLEU_CLAIR))
v.append(table(f"{pid}_tbl", 232, 364, 1032, 260,
               [pcol(CAL, "Date"), pcol(CAL, "Statut"), pcol(CAL, "Pays"),
                pcol(CAL, "Instrument"), pcol(CAL, "Titre")],
               title="Détail des émissions"))
pages_order.append(write_page(pid, "Calendrier des émissions", 3, v))

# ===================== PAGE 5 — COTATIONS BRVM =====================
pid = "c1000000000000000005"
v = header(pid, "Cotations obligataires — BRVM",
           "Journée de cotation des obligations (cours différés) — source BRVM")
v.append(card(f"{pid}_k1", 16, 116, 220, 110, M, "Nb obligations cotées"))
v.append(card(f"{pid}_k2", 246, 116, 220, 110, M, "Taux facial moyen (BRVM)"))
v.append(card(f"{pid}_k3", 476, 116, 220, 110, M, "Dernière cotation BRVM"))
v.append(chart(f"{pid}_bar_cat", 716, 116, 548, 240, "clusteredColumnChart",
               {"Category": {"projections": [pcol(BR, "Catégorie")]},
                "Y": {"projections": [pmeasure(M, "Nb obligations cotées")]}},
               title="Obligations cotées par catégorie", color=BLEU))
v.append(table(f"{pid}_tbl", 16, 244, 1248, 380,
               [pcol(BR, "Code obligation"), pcol(BR, "Nom"),
                pcol(BR, "Catégorie"), pcol(BR, "Taux facial"),
                pcol(BR, "Cours du jour"), pcol(BR, "Coupon couru")],
               title="Obligations cotées"))
pages_order.append(write_page(pid, "Cotations BRVM", 4, v))

# ===================== PAGE 6 — STRUCTURE PAR TERME & SPREADS =====================
# Approche : comparaison de courbes par ANNÉE DE RÉFÉRENCE (dernière courbe de chaque
# année) au lieu d'une courbe moyenne sur une période. Périmètre agrégat UEMOA
# (mesures basées sur « Taux moyen UEMOA »), le slicer Pays permet de drill sur un émetteur.
pid = "c1000000000000000006"
v = header(pid, "Structure par terme & spreads de taux",
           "Comparaison des courbes de rendement UEMOA par année de référence — source UMOA-Titres")
v.append(slicer(f"{pid}_slc_annee", 16, 112, 200, 74, D, "Année", title="Année(s) de référence"))
v.append(slicer(f"{pid}_slc_pays", 232, 112, 300, 74, CT, "Pays", title="Pays (défaut : UEMOA)"))
# Courbe superposée : taux par maturité, une série par année de référence
v.append(chart(f"{pid}_curve", 16, 196, 760, 250, "lineChart",
               {"Category": {"projections": [pcol(CT, "Maturité (années)")]},
                "Series": {"projections": [pcol(D, "Année")]},
                "Y": {"projections": [pmeasure(M, "Taux courbe de réf.")]}},
               title="Courbe des taux UEMOA par année de référence"))
# Matrice : niveaux de taux par maturité × année + écart annuel (pb)
v.append(chart(f"{pid}_matrix", 788, 196, 476, 250, "pivotTable",
               {"Rows": {"projections": [pcol(CT, "Maturité")]},
                "Columns": {"projections": [pcol(D, "Année")]},
                "Values": {"projections": [pmeasure(M, "Taux courbe de réf."),
                                           pmeasure(M, "Écart taux a/a (pb)")]}},
               title="Taux par maturité et écart annuel"))
# Variation de taux vs année précédente, sur toute la courbe (généralise « Ecart 2026-2025 »)
v.append(chart(f"{pid}_ecart", 16, 456, 760, 248, "clusteredBarChart",
               {"Category": {"projections": [pcol(CT, "Maturité (années)")]},
                "Y": {"projections": [pmeasure(M, "Écart taux a/a (pb)")]}},
               title="Variation de taux vs année précédente (pb)", color=BLEU_CLAIR))
# Spreads entre maturités par année de référence (table de l'image)
v.append(chart(f"{pid}_spreads", 788, 456, 476, 248, "pivotTable",
               {"Rows": {"projections": [pcol(D, "Année")]},
                "Values": {"projections": [pmeasure(M, "Pente 1-3 ans réf. (pb)"),
                                           pmeasure(M, "Pente 5-7 ans réf. (pb)"),
                                           pmeasure(M, "Pente 7-10 ans réf. (pb)"),
                                           pmeasure(M, "Pente 2-10 ans réf. (pb)")]}},
               title="Spreads entre maturités par année (pb)"))
pages_order.append(write_page(pid, "Structure par terme & spreads", 5, v))

# ===================== PAGE 7 — DURATION, CONVEXITÉ & YTM =====================
pid = "c1000000000000000007"
v = header(pid, "Duration, convexité & YTM",
           "Sensibilité obligataire (conventions actuarielles UMOA) — source marché secondaire")
v.append(slicer(f"{pid}_slc_periode", 16, 112, 300, 74, D, "Date", title="Période (début / fin)"))
v.append(slicer(f"{pid}_slc_emet", 324, 112, 220, 74, MS, "Émetteur", title="Émetteur"))
v.append(slicer(f"{pid}_slc_instr", 552, 112, 180, 74, MS, "Instrument", title="Instrument"))
v.append(slicer(f"{pid}_slc_meth", 740, 112, 236, 74, MS, "Méthode", title="Méthode de calcul"))
# KPI
kpis7 = [("YTM moyen pondéré", "k1"), ("Duration modifiée moyenne", "k2"),
         ("Convexité moyenne", "k3"), ("Maturité résiduelle moyenne", "k4")]
cx = 16
for measure, key in kpis7:
    v.append(card(f"{pid}_{key}", cx, 196, 300, 92, M, measure))
    cx += 312
# Nuage duration vs YTM (par ISIN, taille = volume)
v.append(scatter(f"{pid}_scatter", 16, 300, 620, 244,
                 pcol(MS, "ISIN"),
                 pmeasure(M, "Duration modifiée moyenne"),
                 pmeasure(M, "YTM moyen pondéré"),
                 pmeasure(M, "Volume nominal échangé"),
                 title="Duration modifiée vs YTM (taille = volume échangé)"))
# Duration modifiée moyenne par émetteur
v.append(chart(f"{pid}_dur_emet", 648, 300, 616, 244, "clusteredBarChart",
               {"Category": {"projections": [pcol(MS, "Émetteur")]},
                "Y": {"projections": [pmeasure(M, "Duration modifiée moyenne")]}},
               title="Duration modifiée moyenne par émetteur", color=BLEU))
# Table détail par ligne
v.append(table(f"{pid}_tbl", 16, 548, 1248, 156,
               [pcol(MS, "ISIN"), pcol(MS, "Émetteur"), pcol(MS, "Instrument"),
                pcol(MS, "Méthode"), pcol(MS, "Maturité résiduelle (années)"),
                pmeasure(M, "YTM moyen pondéré"), pmeasure(M, "Duration modifiée moyenne"),
                pmeasure(M, "Convexité moyenne")],
               title="Détail par ligne obligataire"))
pages_order.append(write_page(pid, "Duration, convexité & YTM", 6, v))

# ===================== pages.json =====================
pages_meta = {"$schema": SCH_PAGES, "pageOrder": pages_order, "activePageName": pages_order[0]}
(PAGES_DIR / "pages.json").write_text(json.dumps(pages_meta, indent=2, ensure_ascii=False), encoding="utf-8")

print("Pages générées :", pages_order)
print("Total visuels :", sum(len(list((PAGES_DIR / p / "visuals").iterdir())) for p in pages_order))
