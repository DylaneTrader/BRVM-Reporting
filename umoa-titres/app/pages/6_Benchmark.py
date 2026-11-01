# -*- coding: utf-8 -*-
"""Benchmark obligataire : indices coté et non coté, et leur composite à pondération libre.

Base 100 au 31/12/2019. Les limites méthodologiques connues sont affichées dans
la page, pas reléguées en annexe : elles conditionnent la lecture de toute
mesure de risque dérivée de l'indice.
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.lib import benchmark  # noqa: E402

st.set_page_config(page_title="Benchmark obligataire", page_icon="📊",
                   layout="wide")


def _pourcent(valeur, decimales: int = 2) -> str:
    return "—" if pd.isna(valeur) else f"{valeur * 100:.{decimales}f} %"


st.title("Benchmark obligataire")

serie = benchmark.serie()
if serie.empty:
    st.error("`data/benchmark/benchmark_obligataire.csv` de Scraper-UMOA-Titres est absent. Lancer "
             "`python scripts/construire_benchmark.py` pour le régénérer.")
    st.stop()

st.caption(f"Benchmark obligataire, base 100 au {serie['Date'].iloc[0]:%d/%m/%Y} — "
           f"dernière valeur au {serie['Date'].iloc[-1]:%d/%m/%Y}.")

LIBELLE = None  # fixé après le choix de la part du coté
NOMS: dict = {}

with st.sidebar:
    st.header("Composition")
    part_cote = st.slider(
        "Part de l'indice coté (%)", 0, 100, 30, 5,
        help="0 : non coté seul ; 100 : coté seul. Les deux sous-indices sont construits "
             "automatiquement à chaque actualisation de Scraper-UMOA-Titres (le non coté sur les "
             "adjudications retenues) ; seule leur pondération change ici, mois par mois.")
    poids_cote = part_cote / 100
    LIBELLE = benchmark.libelle_composite(poids_cote)
    NOMS["Indice obligataire (30/70)"] = LIBELLE
    st.header("Périmètre")
    annees = sorted(serie["Date"].dt.year.unique())
    debut, fin = st.select_slider("Période", annees, value=(annees[0], annees[-1]))
    indices = st.multiselect("Indices affichés", list(benchmark.INDICES),
                             default=list(benchmark.INDICES),
                             format_func=lambda k: NOMS.get(k, k))
    rebase = st.toggle(
        "Rebaser à 100 en début de période", value=False,
        help="Utile pour comparer les trajectoires sur une sous-période sans "
             "l'effet du niveau accumulé depuis 2019.")

# Le composite est recomposé à la part choisie ; les colonnes internes gardent leur nom.
COMPOSITE = benchmark.composite(serie, poids_cote)
serie = serie.copy()
serie["Indice obligataire (30/70)"] = COMPOSITE["Indice"].to_numpy()
serie["Rendement obligataire"] = COMPOSITE["Rendement"].to_numpy()
COULEURS = {NOMS.get(k, k): c for k, c in benchmark.INDICES.items()}

periode = serie[serie["Date"].dt.year.between(debut, fin)].reset_index(drop=True)
if periode.empty:
    st.info("Aucune donnée sur cette période.")
    st.stop()

synthese = benchmark.resume(periode)

# --------------------------------------------------------------------------
# Synthèse
# --------------------------------------------------------------------------
cartes = st.columns(5)
cartes[0].metric(
    LIBELLE,
    f"{synthese['Indice obligataire (30/70) — niveau']:.2f}",
    help="Niveau au dernier mois de la période.")
cartes[1].metric(
    "Performance période",
    _pourcent(synthese["Indice obligataire (30/70) — performance"]),
    help=f"Du {synthese['Date de début']:%d/%m/%Y} au "
         f"{synthese['Date de fin']:%d/%m/%Y}.")
cartes[2].metric(
    "Annualisée",
    _pourcent(synthese["Indice obligataire (30/70) — annualisée"]))
cartes[3].metric("Coté — performance",
                 _pourcent(synthese["Indice coté — performance"]))
cartes[4].metric("Non coté — performance",
                 _pourcent(synthese["Indice non coté — performance"]))

if synthese["Mois sans cotation BRVM"]:
    st.warning(
        f"**{synthese['Mois sans cotation BRVM']} mois** de la période n'ont pas "
        "de bulletin BRVM exploitable. Sur ces mois, le composite se replie sur "
        f"le seul indice non coté : la part de {poids_cote:.0%} du coté n'est pas appliquée, "
        "elle est reportée sur le non coté (l'indice coté seul reste à son niveau). Ces mois sont signalés dans le "
        "graphique des contributions.")

onglets = st.tabs(["Trajectoire", "Rendements", "Contributions",
                   "Performances annuelles", "Taux par classe", "Limites"])

# --------------------------------------------------------------------------
# Trajectoire
# --------------------------------------------------------------------------
with onglets[0]:
    if not indices:
        st.info("Sélectionner au moins un indice.")
    else:
        trace = periode[["Date"] + indices].copy()
        if rebase:
            for indice in indices:
                base = trace[indice].iloc[0]
                if base:
                    trace[indice] = trace[indice] / base * 100
        longue = trace.melt(id_vars="Date", var_name="Indice", value_name="Niveau")
        longue["Indice"] = longue["Indice"].replace(NOMS)
        st.altair_chart(
            alt.Chart(longue).mark_line().encode(
                x=alt.X("Date:T", title=None),
                y=alt.Y("Niveau:Q", title="Base 100",
                        scale=alt.Scale(zero=False)),
                color=alt.Color("Indice:N", title=None,
                                scale=alt.Scale(
                                    domain=list(COULEURS),
                                    range=list(COULEURS.values()))),
                tooltip=["Indice", alt.Tooltip("Date:T", format="%m/%Y"),
                         alt.Tooltip("Niveau:Q", format=".2f")],
            ).properties(height=420,
                         title="Trajectoire des indices"
                               + (" (rebasés)" if rebase else "")),
            width="stretch")

        st.subheader("Nombre de lignes cotées retenues")
        lignes = periode.dropna(subset=["Lignes cotées"])
        if lignes.empty:
            st.info("Aucun mois avec bulletin BRVM sur cette période.")
        else:
            st.altair_chart(
                alt.Chart(lignes).mark_area(
                    color="#c98a2e", opacity=0.4,
                    line={"color": "#c98a2e"}).encode(
                    x=alt.X("Date:T", title=None),
                    y=alt.Y("Lignes cotées:Q", title="Lignes"),
                    tooltip=[alt.Tooltip("Date:T", format="%m/%Y"),
                             "Lignes cotées"],
                ).properties(height=200),
                width="stretch")
            st.caption("Le nombre de lignes conditionne le poids 1/N de chacune "
                       "dans l'indice coté : une entrée ou une sortie déplace "
                       "mécaniquement le poids de toutes les autres.")

# --------------------------------------------------------------------------
# Rendements
# --------------------------------------------------------------------------
with onglets[1]:
    mensuels = benchmark.rendements_mensuels(periode)
    mensuels = mensuels[mensuels["Indice"].isin(indices)].copy()
    mensuels["Indice"] = mensuels["Indice"].replace(NOMS)
    if mensuels.empty:
        st.info("Aucun rendement sur ce périmètre.")
    else:
        st.altair_chart(
            alt.Chart(mensuels).mark_bar().encode(
                x=alt.X("Date:T", title=None),
                y=alt.Y("Rendement:Q", axis=alt.Axis(format="%")),
                color=alt.Color("Indice:N", title=None,
                                scale=alt.Scale(
                                    domain=list(COULEURS),
                                    range=list(COULEURS.values()))),
                xOffset=alt.XOffset("Indice:N"),
                tooltip=["Indice", alt.Tooltip("Date:T", format="%m/%Y"),
                         alt.Tooltip("Rendement:Q", format=".3%")],
            ).properties(height=340, title="Rendements mensuels"),
            width="stretch")

        statistiques = mensuels.groupby("Indice")["Rendement"].agg(
            **{"Mois": "size", "Moyenne mensuelle": "mean",
               "Écart-type mensuel": "std", "Minimum": "min",
               "Maximum": "max"}).reset_index()
        statistiques["Volatilité annualisée"] = (
            statistiques["Écart-type mensuel"] * np.sqrt(12))
        st.dataframe(
            statistiques, hide_index=True, width="stretch",
            column_config={
                "Moyenne mensuelle": st.column_config.NumberColumn(format="percent"),
                "Écart-type mensuel": st.column_config.NumberColumn(format="percent"),
                "Minimum": st.column_config.NumberColumn(format="percent"),
                "Maximum": st.column_config.NumberColumn(format="percent"),
                "Volatilité annualisée": st.column_config.NumberColumn(format="percent"),
            })
        st.caption("La volatilité de l'indice non coté est structurellement "
                   "sous-estimée : faute d'effet prix, il se comporte en carry "
                   "pur entre deux rééquilibrages (limite n° 2).")

# --------------------------------------------------------------------------
# Contributions
# --------------------------------------------------------------------------
with onglets[2]:
    parts = benchmark.contributions(periode, poids_cote)
    longue = parts.melt(
        id_vars=["Date", "Repli"],
        value_vars=["Contribution cotée", "Contribution non cotée"],
        var_name="Jambe", value_name="Contribution")
    st.altair_chart(
        alt.Chart(longue).mark_bar().encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("Contribution:Q", title="Contribution au rendement mensuel",
                    axis=alt.Axis(format="%")),
            color=alt.Color("Jambe:N", title=None,
                            scale=alt.Scale(
                                domain=["Contribution cotée", "Contribution non cotée"],
                                range=["#c98a2e", "#2e7d5b"])),
            opacity=alt.condition(alt.datum.Repli, alt.value(0.45), alt.value(1.0)),
            tooltip=["Jambe", alt.Tooltip("Date:T", format="%m/%Y"),
                     alt.Tooltip("Contribution:Q", format=".3%"), "Repli"],
        ).properties(height=380,
                     title=f"Décomposition à {poids_cote:.0%} / "
                           f"{1 - poids_cote:.0%}"),
        width="stretch")
    st.caption("Les barres estompées sont les mois de repli : sans bulletin "
               "BRVM, la totalité du rendement vient du non coté.")

    cumul = parts[["Contribution cotée", "Contribution non cotée"]].sum()
    total = cumul.sum()
    if total:
        resume_contributions = pd.DataFrame({
            "Jambe": cumul.index,
            "Contribution cumulée": cumul.values,
            "Part": cumul.values / total,
        })
        st.dataframe(
            resume_contributions, hide_index=True, width="stretch",
            column_config={
                "Contribution cumulée": st.column_config.NumberColumn(format="percent"),
                "Part": st.column_config.NumberColumn(format="percent"),
            })

# --------------------------------------------------------------------------
# Performances annuelles
# --------------------------------------------------------------------------
with onglets[3]:
    annuelles = benchmark.performances()
    if annuelles.empty:
        st.info("Le classeur `benchmark_obligataire.xlsx` est absent : les "
                "performances annuelles en proviennent.")
    else:
        filtrees = annuelles[annuelles["Année"].between(debut, fin)]
        # Le classeur publie le 30/70 : la ligne du composite est recalculée à la part choisie.
        comp = COMPOSITE.assign(Année=COMPOSITE["Date"].dt.year)
        comp = comp[comp["Année"].between(max(debut, 2020), fin)]
        recalcul = comp.groupby("Année").agg(
            Performance=("Rendement", lambda x: (1 + x).prod() - 1),
            **{"Volatilité annualisée": ("Rendement", lambda x: x.std() * np.sqrt(12)),
               "Mois observés": ("Rendement", "size"),
               "Valeur fin d'année": ("Indice", "last")}).reset_index()
        recalcul.insert(1, "Indice", LIBELLE)
        filtrees = pd.concat([recalcul, filtrees[filtrees["Indice"] != "Indice obligataire (30/70)"]],
                             ignore_index=True)[[c for c in filtrees.columns]]
        filtrees["Indice"] = filtrees["Indice"].replace(NOMS)
        st.altair_chart(
            alt.Chart(filtrees).mark_bar().encode(
                x=alt.X("Année:O", title=None),
                y=alt.Y("Performance:Q", axis=alt.Axis(format="%")),
                color=alt.Color("Indice:N", title=None,
                                scale=alt.Scale(
                                    domain=list(COULEURS),
                                    range=list(COULEURS.values()))),
                xOffset=alt.XOffset("Indice:N"),
                tooltip=["Indice", "Année",
                         alt.Tooltip("Performance:Q", format=".2%"),
                         alt.Tooltip("Volatilité annualisée:Q", format=".2%"),
                         "Mois observés"],
            ).properties(height=340, title="Performance annuelle"),
            width="stretch")
        st.dataframe(
            filtrees, hide_index=True, width="stretch",
            column_config={
                "Performance": st.column_config.NumberColumn(format="percent"),
                "Volatilité annualisée": st.column_config.NumberColumn(format="percent"),
                "Valeur fin d'année": st.column_config.NumberColumn(format="%.2f"),
            })
        st.caption("« Mois observés » signale les années incomplètes : 2019 ne "
                   "compte que le mois de base, et l'année en cours s'arrête au "
                   "dernier mois publié.")

# --------------------------------------------------------------------------
# Taux par classe
# --------------------------------------------------------------------------
with onglets[4]:
    classes = benchmark.taux_par_classe()
    if classes.empty:
        st.info("Le classeur `benchmark_obligataire.xlsx` est absent : les taux "
                "par classe en proviennent.")
    else:
        classes = classes.copy()
        classes["Date"] = pd.to_datetime(classes["Mois"], format="%Y-%m",
                                         errors="coerce")
        filtrees = classes[classes["Date"].dt.year.between(debut, fin)]
        colonnes_classes = [c for c in classes.columns
                            if c not in ("Mois", "Date", "Date de rééquilibrage",
                                         "Classes alimentées",
                                         "Taux moyen des 29 classes")]
        longue = filtrees.melt(
            id_vars="Date", value_vars=colonnes_classes,
            var_name="Classe", value_name="Taux").dropna(subset=["Taux"])
        st.altair_chart(
            alt.Chart(longue).mark_rect().encode(
                x=alt.X("Date:T", title=None),
                y=alt.Y("Classe:N", title=None, sort=colonnes_classes),
                color=alt.Color("Taux:Q", title="Taux",
                                scale=alt.Scale(scheme="viridis")),
                tooltip=["Classe", alt.Tooltip("Date:T", format="%m/%Y"),
                         alt.Tooltip("Taux:Q", format=".3%")],
            ).properties(height=560,
                         title="Taux de référence par classe de maturité"),
            width="stretch")
        st.altair_chart(
            alt.Chart(filtrees).mark_line(color="#1f6f8b", point=True).encode(
                x=alt.X("Date:T", title=None),
                y=alt.Y("Classes alimentées:Q", title="Classes"),
                tooltip=[alt.Tooltip("Date:T", format="%m/%Y"),
                         "Classes alimentées",
                         alt.Tooltip("Taux moyen des 29 classes:Q", format=".3%")],
            ).properties(height=200,
                         title="Nombre de classes effectivement alimentées"),
            width="stretch")
        st.caption("Sur 29 classes possibles, une vingtaine seulement sont "
                   "alimentées chaque mois : les autres sont interpolées. "
                   "Au-delà de 7 ans, un unique bucket couvre jusqu'à 15 ans "
                   "(limite n° 3).")

# --------------------------------------------------------------------------
# Limites
# --------------------------------------------------------------------------
with onglets[5]:
    st.markdown(
        "Ces limites sont documentées dans "
        "`Limites_Methodologie_Benchmark_Obligataire.md`. Elles ne sont pas des "
        "réserves de forme : les deux premières faussent structurellement toute "
        "mesure de risque dérivée de l'indice.")
    for rang, (titre, constat, consequence) in enumerate(benchmark.LIMITES, start=1):
        with st.expander(f"{rang}. {titre}", expanded=rang <= 2):
            st.markdown(f"**Constat.** {constat}")
            st.markdown(f"**Conséquence / piste.** {consequence}")

    fiche = benchmark.methodologie()
    if not fiche.empty:
        st.subheader("Méthodologie publiée avec l'indice")
        st.dataframe(fiche, hide_index=True, width="stretch", height=420)
