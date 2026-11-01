# -*- coding: utf-8 -*-
"""Risque de taux — sensibilité de l'univers aux déformations de courbe.

Tout est pondéré par l'encours, jamais par le volume échangé : le volume est
biaisé par les prints atypiques et par la concentration du secondaire sur
quelques souches, alors que l'encours mesure l'exposition réellement portée.
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.lib import chargement, courbes, referentiel, risque  # noqa: E402

st.set_page_config(page_title="Risque de taux", page_icon="⚖️", layout="wide")


@st.cache_data(show_spinner="Construction du référentiel…")
def _referentiel(reglages: dict) -> pd.DataFrame:
    return referentiel.construire_referentiel(
        params=courbes.ParametresCourbe.depuis_etat(reglages))


def _pourcent(valeur, decimales: int = 2) -> str:
    return "—" if pd.isna(valeur) else f"{valeur * 100:.{decimales}f} %"


def _milliards(valeur, decimales: int = 1) -> str:
    return ("—" if pd.isna(valeur)
            else f"{valeur:,.{decimales}f} Mds".replace(",", " "))


st.title("Risque de taux")
reference = chargement.date_reference()
st.caption(f"Sensibilité de l'univers obligataire au {reference:%d/%m/%Y}, "
           "pondérée par l'encours.")

titres = _referentiel(courbes.parametres_actifs().en_dict())

with st.sidebar:
    st.header("Périmètre")
    pays = st.multiselect("Pays", sorted(titres["Pays"].dropna().unique()),
                          default=sorted(titres["Pays"].dropna().unique()))
    instruments = st.multiselect(
        "Instrument", sorted(titres["Instrument"].dropna().unique()),
        default=sorted(titres["Instrument"].dropna().unique()))

    st.header("Scénario de courbe")
    parallele = st.slider("Choc parallèle (pb)", -300, 300, 100, 25)
    pentification = st.slider(
        "Pentification (pb)", -200, 200, 0, 25,
        help="Appliquée proportionnellement à l'écart au pivot : positive, "
             "elle relève le long et abaisse le court.")
    pivot = st.slider("Pivot de pentification (années)", 1.0, 10.0, 5.0, 0.5,
                      disabled=pentification == 0)

univers = titres[titres["Pays"].isin(pays) & titres["Instrument"].isin(instruments)]
etat_couverture = risque.couverture(univers)
donnees = risque.perimetre(univers)

if donnees.empty:
    st.info("Aucun titre exploitable sur ce périmètre : la mesure de risque "
            "exige à la fois un encours documenté et une duration, donc au "
            "moins une négociation.")
    st.stop()

deformation = risque.Deformation(parallele, pentification, pivot)
mesures = risque.indicateurs(donnees)

# --------------------------------------------------------------------------
# Couverture — affichée avant les résultats, pas après
# --------------------------------------------------------------------------
st.info(
    f"Mesure calculée sur **{etat_couverture['Titres couverts']} titres** sur "
    f"{etat_couverture['Titres vivants']} vivants "
    f"({_pourcent(etat_couverture['Couverture en nombre'], 0)} en nombre), "
    f"représentant **{_pourcent(etat_couverture['Couverture en encours'], 0)} "
    "de l'encours**. La duration n'existe que pour les titres ayant négocié au "
    "moins une fois : la couverture en encours est bien meilleure qu'en nombre, "
    "les grosses souches étant celles qui traitent.")

cartes = st.columns(6)
cartes[0].metric("Encours couvert", _milliards(mesures["Encours (Mds FCFA)"], 0))
cartes[1].metric("Duration modifiée", f"{mesures['Duration modifiée']:.2f}")
cartes[2].metric("Convexité", f"{mesures['Convexité']:.1f}")
cartes[3].metric("Maturité résiduelle", f"{mesures['Maturité résiduelle']:.2f} ans")
cartes[4].metric("DV01", f"{mesures['DV01 (Mds FCFA / pb)']:.2f} Mds / pb",
                 help="Perte de valeur du portefeuille pour 1 pb de hausse "
                      "parallèle des taux.")
detail = risque.impact(donnees, deformation)
impact_total = detail["Impact (Mds FCFA)"].sum(skipna=True)
cartes[5].metric("Impact du scénario", _milliards(impact_total),
                 delta=_pourcent(impact_total / mesures["Encours (Mds FCFA)"]),
                 delta_color="normal")

onglets = st.tabs(["Scénarios", "Contributions", "Profil par maturité",
                   "Détail par titre"])

# --------------------------------------------------------------------------
# Scénarios
# --------------------------------------------------------------------------
with onglets[0]:
    table = risque.table_scenarios(donnees, risque.SCENARIOS_PARALLELES,
                                   pentification, pivot)
    st.altair_chart(
        alt.Chart(table).mark_bar().encode(
            x=alt.X("Choc parallèle (pb):O", title="Choc parallèle (pb)"),
            y=alt.Y("Impact (Mds FCFA):Q", title="Impact (Mds FCFA)"),
            color=alt.condition(alt.datum["Impact (Mds FCFA)"] < 0,
                                alt.value("#b23a3a"), alt.value("#2e7d5b")),
            tooltip=[alt.Tooltip("Choc parallèle (pb):O"),
                     alt.Tooltip("Impact (Mds FCFA):Q", format=".1f"),
                     alt.Tooltip("Impact (%):Q", format=".2%")],
        ).properties(height=340,
                     title="Impact d'un choc parallèle de taux"
                           + (f", avec pentification de {pentification:+} pb"
                              if pentification else "")),
        width="stretch")
    st.dataframe(
        table, hide_index=True, width="stretch",
        column_config={
            "Impact (Mds FCFA)": st.column_config.NumberColumn(format="%.1f"),
            "Impact (%)": st.column_config.NumberColumn(format="percent"),
        })
    st.caption("Approximation d'ordre 2 : ΔP/P = −D\\* · Δy + ½ · C · Δy². "
               "L'asymétrie entre hausse et baisse vient de la convexité. Les "
               "titres sans convexité renseignée sont traités à convexité "
               "nulle, ce qui rend l'estimation légèrement pessimiste plutôt "
               "qu'optimiste.")

    if pentification:
        st.subheader("Forme du choc appliqué")
        grille = pd.DataFrame({"Maturité": np.arange(0.25, 15.25, 0.25)})
        grille["Choc (pb)"] = deformation.choc(grille["Maturité"]) * 10_000
        st.altair_chart(
            alt.Chart(grille).mark_line(color="#1f6f8b").encode(
                x=alt.X("Maturité:Q", title="Maturité (années)"),
                y=alt.Y("Choc (pb):Q", title="Choc (pb)"),
                tooltip=[alt.Tooltip("Maturité:Q", format=".2f"),
                         alt.Tooltip("Choc (pb):Q", format=".0f")],
            ).properties(height=220,
                         title=f"Déformation de courbe — pivot à {pivot:g} ans"),
            width="stretch")

# --------------------------------------------------------------------------
# Contributions
# --------------------------------------------------------------------------
with onglets[1]:
    axe = st.radio("Ventilation", ["Pays", "Classe de maturité", "Instrument"],
                   horizontal=True)
    parts = risque.contributions(donnees, axe, deformation)
    parts_graphique = parts.copy()
    parts_graphique[axe] = parts_graphique[axe].astype(str)
    st.altair_chart(
        alt.Chart(parts_graphique).mark_bar().encode(
            x=alt.X("Impact (Mds FCFA):Q"),
            y=alt.Y(f"{axe}:N", title=None, sort="x"),
            color=alt.condition(alt.datum["Impact (Mds FCFA)"] < 0,
                                alt.value("#b23a3a"), alt.value("#2e7d5b")),
            tooltip=[axe, "Titres",
                     alt.Tooltip("Encours (Mds FCFA):Q", format=".0f"),
                     alt.Tooltip("Duration modifiée:Q", format=".2f"),
                     alt.Tooltip("Impact (Mds FCFA):Q", format=".1f"),
                     alt.Tooltip("Part du risque:Q", format=".1%")],
        ).properties(height=340,
                     title=f"Impact du scénario {parallele:+} pb par "
                           f"{axe.lower()}"),
        width="stretch")
    st.dataframe(
        parts, hide_index=True, width="stretch",
        column_config={
            "Encours (Mds FCFA)": st.column_config.NumberColumn(format="%.0f"),
            "Duration modifiée": st.column_config.NumberColumn(format="%.2f"),
            "Impact (Mds FCFA)": st.column_config.NumberColumn(format="%.1f"),
            "Part du risque": st.column_config.NumberColumn(format="percent"),
        })
    st.caption("`Part du risque` est calculée sur les impacts en valeur "
               "absolue : elle dit d'où vient le risque, pas son signe.")

# --------------------------------------------------------------------------
# Profil par maturité
# --------------------------------------------------------------------------
with onglets[2]:
    profil = risque.contributions(donnees, "Classe de maturité", deformation)
    profil["Classe de maturité"] = profil["Classe de maturité"].astype(str)
    ordre = list(risque.CLASSES_MATURITE[1])
    profil["_ordre"] = profil["Classe de maturité"].map(
        {libelle: rang for rang, libelle in enumerate(ordre)})
    profil = profil.sort_values("_ordre").drop(columns="_ordre")

    gauche, droite = st.columns(2)
    with gauche:
        st.altair_chart(
            alt.Chart(profil).mark_bar(color="#1f6f8b").encode(
                x=alt.X("Classe de maturité:N", title=None, sort=ordre),
                y=alt.Y("Encours (Mds FCFA):Q"),
                tooltip=["Classe de maturité", "Titres",
                         alt.Tooltip("Encours (Mds FCFA):Q", format=".0f")],
            ).properties(height=300, title="Encours par classe de maturité"),
            width="stretch")
    with droite:
        st.altair_chart(
            alt.Chart(profil.dropna(subset=["Duration modifiée"]))
            .mark_bar(color="#c98a2e").encode(
                x=alt.X("Classe de maturité:N", title=None, sort=ordre),
                y=alt.Y("Duration modifiée:Q"),
                tooltip=["Classe de maturité",
                         alt.Tooltip("Duration modifiée:Q", format=".2f")],
            ).properties(height=300, title="Duration modifiée moyenne"),
            width="stretch")

    nuage = donnees.assign(
        **{"Classe de maturité": donnees["Classe de maturité"].astype(str)})
    st.altair_chart(
        alt.Chart(nuage).mark_circle(opacity=0.6).encode(
            x=alt.X("Maturité résiduelle (années):Q"),
            y=alt.Y("Duration modifiée:Q"),
            size=alt.Size("Encours (Mds FCFA):Q", title="Encours",
                          scale=alt.Scale(range=[20, 600])),
            color=alt.Color("Pays:N", title=None),
            tooltip=["Identifiant", "Pays", "Instrument",
                     alt.Tooltip("Maturité résiduelle (années):Q", format=".2f"),
                     alt.Tooltip("Duration modifiée:Q", format=".2f"),
                     alt.Tooltip("Convexité:Q", format=".1f"),
                     alt.Tooltip("Encours (Mds FCFA):Q", format=".1f")],
        ).properties(height=420,
                     title="Duration contre maturité résiduelle — "
                           "taille proportionnelle à l'encours"),
        width="stretch")
    st.caption("L'écart entre duration et maturité mesure l'effet du coupon et "
               "de l'amortissement : une souche amortissable a une duration "
               "nettement inférieure à sa maturité.")

# --------------------------------------------------------------------------
# Détail
# --------------------------------------------------------------------------
with onglets[3]:
    colonnes = ["Identifiant", "ISIN", "Pays", "Instrument", "Coupon",
                "Échéance", "Maturité résiduelle (années)", "Classe de maturité",
                "Encours (Mds FCFA)", "Encours estimé", "Duration modifiée",
                "Convexité", "Choc (pb)", "Variation (%)", "Impact (Mds FCFA)"]
    table = detail[colonnes].sort_values("Impact (Mds FCFA)")
    st.dataframe(
        table, hide_index=True, width="stretch", height=520,
        column_config={
            "Coupon": st.column_config.NumberColumn(format="percent"),
            "Échéance": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Maturité résiduelle (années)": st.column_config.NumberColumn(format="%.2f"),
            "Encours (Mds FCFA)": st.column_config.NumberColumn(format="%.2f"),
            "Duration modifiée": st.column_config.NumberColumn(format="%.2f"),
            "Convexité": st.column_config.NumberColumn(format="%.1f"),
            "Choc (pb)": st.column_config.NumberColumn(format="%.0f"),
            "Variation (%)": st.column_config.NumberColumn(format="percent"),
            "Impact (Mds FCFA)": st.column_config.NumberColumn(format="%.3f"),
        })
    st.download_button(
        "Exporter le détail (CSV)",
        table.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"risque_taux_{parallele:+}pb_{reference:%Y%m%d}.csv",
        mime="text/csv")
