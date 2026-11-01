# -*- coding: utf-8 -*-
"""Marché secondaire — activité, liquidité et qualité d'exécution.

Toutes les mesures de rendement sont déclinées sur deux univers : complet, et
hors lignes classées atypiques. L'écart entre les deux est affiché comme une
mesure à part entière, pas comme une note de bas de page.
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.lib import (chargement, courbes, qualite_prix, referentiel,  # noqa: E402
                     secondaire)

st.set_page_config(page_title="Marché secondaire", page_icon="🔄", layout="wide")


@st.cache_data(show_spinner="Évaluation des transactions…")
def _transactions(seuils: dict, niveau: str, reglages: dict) -> pd.DataFrame:
    return secondaire.transactions(
        qualite_prix.ParametresQualite.depuis_etat(seuils), niveau,
        courbes.ParametresCourbe.depuis_etat(reglages))


@st.cache_data(show_spinner=False)
def _referentiel(reglages: dict) -> pd.DataFrame:
    return referentiel.construire_referentiel(
        params=courbes.ParametresCourbe.depuis_etat(reglages))


def _pourcent(valeur, decimales: int = 2) -> str:
    return "—" if pd.isna(valeur) else f"{valeur * 100:.{decimales}f} %"


def _milliards(valeur, decimales: int = 0) -> str:
    return ("—" if pd.isna(valeur)
            else f"{valeur:,.{decimales}f} Mds".replace(",", " "))


st.title("Marché secondaire")
reference = chargement.date_reference()
st.caption(f"Transactions sur titres publics UMOA au {reference:%d/%m/%Y}, "
           "au grain d'un titre par séance.")

reglages_courbe = courbes.parametres_actifs().en_dict()

with st.sidebar:
    st.header("Périmètre")
    defauts = qualite_prix.ParametresQualite()
    niveau = st.selectbox(
        "Courbe de référence", list(courbes.LIBELLES_NIVEAUX),
        index=list(courbes.LIBELLES_NIVEAUX).index(courbes.NIVEAU_OFFICIELLE),
        format_func=lambda n: courbes.LIBELLES_NIVEAUX[n])

    st.header("Seuils de fiabilité")
    seuils = {
        "seuil_courbe_b": st.slider("Écart à la courbe → B (pb)", 50, 500,
                                    int(defauts.seuil_courbe_b), 25),
        "seuil_courbe_c": st.slider("Écart à la courbe → C (pb)", 100, 900,
                                    int(defauts.seuil_courbe_c), 25),
        "min_transactions": st.slider("Transactions minimum", 1, 5,
                                      defauts.min_transactions),
        "seuil_adjudication": st.slider("Écart à l'adjudication (pb)", 50, 900,
                                        int(defauts.seuil_adjudication), 25),
    }

toutes = _transactions(seuils, niveau, reglages_courbe)

with st.sidebar:
    annees = sorted(toutes["Année"].dropna().unique().astype(int))
    debut, fin = st.select_slider(
        "Période", annees, value=(max(annees[0], annees[-1] - 4), annees[-1]))
    pays = st.multiselect("Pays", sorted(toutes["Pays"].dropna().unique()),
                          default=sorted(toutes["Pays"].dropna().unique()))
    instruments = st.multiselect(
        "Instrument", sorted(toutes["Instrument"].dropna().unique()),
        default=sorted(toutes["Instrument"].dropna().unique()))

filtre = (toutes["Pays"].isin(pays) & toutes["Instrument"].isin(instruments)
          & toutes["Année"].between(debut, fin))
donnees = toutes[filtre]
if donnees.empty:
    st.info("Aucune transaction sur ce périmètre.")
    st.stop()

# --------------------------------------------------------------------------
# Synthèse
# --------------------------------------------------------------------------
synthese = secondaire.resume(donnees)

cartes = st.columns(6)
cartes[0].metric("Volume", _milliards(synthese["Volume (Mds FCFA)"]))
cartes[1].metric("Transactions",
                 f"{synthese['Transactions']:,}".replace(",", " "),
                 help=f"{synthese['Séances-titres']} couples titre-séance.")
cartes[2].metric("Titres négociés", synthese["Titres négociés"])
cartes[3].metric("Rendement (univers retenu)",
                 _pourcent(synthese["Rendement (univers retenu)"]),
                 delta=f"{synthese['Écart des univers (pb)']:+.0f} pb vs univers complet",
                 delta_color="off",
                 help="Pondéré par le volume, hors lignes classées atypiques.")
cartes[4].metric("Duration modifiée",
                 f"{synthese['Duration modifiée moyenne']:.2f}")
cartes[5].metric("Volume atypique",
                 _pourcent(synthese["Part du volume atypique"], 1),
                 help=f"{synthese['Lignes atypiques']} lignes, "
                      f"{synthese['Volume atypique (Mds FCFA)']:.0f} Mds FCFA.")

st.markdown(
    f"Sur ce périmètre, écarter les prints atypiques déplace le rendement moyen "
    f"pondéré de **{synthese['Écart des univers (pb)']:+.0f} pb** "
    f"({_pourcent(synthese['Rendement (univers complet)'])} → "
    f"{_pourcent(synthese['Rendement (univers retenu)'])}). C'est la mesure de "
    "ce que les transactions hors marché coûtent à la lecture du marché.")

onglets = st.tabs(["Activité", "Liquidité", "Qualité d'exécution",
                   "Rendements et courbe", "Détail"])

# --------------------------------------------------------------------------
# Activité
# --------------------------------------------------------------------------
with onglets[0]:
    evolution = secondaire.evolution_mensuelle(donnees)
    st.altair_chart(
        alt.Chart(evolution).mark_bar(color="#1f6f8b").encode(
            x=alt.X("Mois:T", title=None),
            y=alt.Y("Volume (Mds FCFA):Q", title="Mds FCFA"),
            tooltip=[alt.Tooltip("Mois:T", format="%m/%Y"),
                     alt.Tooltip("Volume (Mds FCFA):Q", format=".0f"),
                     alt.Tooltip("Transactions:Q", format=".0f")],
        ).properties(height=280, title="Volume mensuel échangé"),
        width="stretch")

    rendements = evolution.melt(
        id_vars="Mois", value_vars=["Rendement complet", "Rendement retenu"],
        var_name="Univers", value_name="Rendement").dropna(subset=["Rendement"])
    st.altair_chart(
        alt.Chart(rendements).mark_line().encode(
            x=alt.X("Mois:T", title=None),
            y=alt.Y("Rendement:Q", axis=alt.Axis(format="%"),
                    scale=alt.Scale(zero=False)),
            color=alt.Color("Univers:N", title=None,
                            scale=alt.Scale(
                                domain=["Rendement complet", "Rendement retenu"],
                                range=["#9aa0a6", "#1f6f8b"])),
            tooltip=[alt.Tooltip("Mois:T", format="%m/%Y"), "Univers",
                     alt.Tooltip("Rendement:Q", format=".3%")],
        ).properties(height=260,
                     title="Rendement moyen pondéré — les deux univers"),
        width="stretch")
    st.caption("Quand les deux courbes s'écartent, le mois comporte des "
               "transactions dont le prix ne reflète pas les conditions de "
               "marché.")

    gauche, droite = st.columns(2)
    for colonne, cle in ((gauche, "Pays"), (droite, "Instrument")):
        table = secondaire.par_modalite(donnees, cle)
        with colonne:
            st.altair_chart(
                alt.Chart(table).mark_bar(color="#1f6f8b").encode(
                    x=alt.X("Volume (Mds FCFA):Q"),
                    y=alt.Y(f"{cle}:N", title=None, sort="-x"),
                    tooltip=[cle, alt.Tooltip("Volume (Mds FCFA):Q", format=".0f"),
                             alt.Tooltip("Rendement retenu:Q", format=".2%"),
                             alt.Tooltip("Part du volume atypique:Q", format=".1%")],
                ).properties(height=260, title=f"Volume par {cle.lower()}"),
                width="stretch")
            st.dataframe(
                table, hide_index=True, width="stretch",
                column_config={
                    "Volume (Mds FCFA)": st.column_config.NumberColumn(format="%.0f"),
                    "Rendement retenu": st.column_config.NumberColumn(format="percent"),
                    "Part du volume atypique": st.column_config.NumberColumn(
                        format="percent"),
                })

# --------------------------------------------------------------------------
# Liquidité
# --------------------------------------------------------------------------
with onglets[1]:
    titres = _referentiel(reglages_courbe)
    taux_rotation = secondaire.rotation(donnees, titres)
    st.markdown(
        "**Rotation** = volume échangé sur la période rapporté à l'encours "
        "vivant. Une mesure que le référentiel rend possible : sans encours par "
        "titre, le volume seul ne dit pas si un compartiment est actif ou "
        "simplement gros.")
    st.altair_chart(
        alt.Chart(taux_rotation.dropna(subset=["Rotation"]))
        .mark_bar(color="#2e7d5b").encode(
            x=alt.X("Rotation:Q", title="Volume / encours"),
            y=alt.Y("Pays:N", title=None, sort="-x"),
            tooltip=["Pays", alt.Tooltip("Rotation:Q", format=".2f"),
                     alt.Tooltip("Volume (Mds FCFA):Q", format=".0f"),
                     alt.Tooltip("Encours (Mds FCFA):Q", format=".0f"),
                     "Titres à encours connu"],
        ).properties(height=280, title="Rotation par pays"),
        width="stretch")
    st.dataframe(
        taux_rotation, hide_index=True, width="stretch",
        column_config={
            "Volume (Mds FCFA)": st.column_config.NumberColumn(format="%.0f"),
            "Encours (Mds FCFA)": st.column_config.NumberColumn(format="%.0f"),
            "Rotation": st.column_config.NumberColumn(format="%.2f"),
        })
    st.caption("L'encours n'est documenté que pour une partie de l'univers : le "
               "nombre de titres couverts accompagne le ratio. Le volume porte "
               "sur la période filtrée, l'encours sur l'état actuel — la "
               "rotation se lit en ordre de grandeur, pas au centième.")

    st.subheader("Concentration")
    top = secondaire.concentration(donnees, 20)
    st.altair_chart(
        alt.Chart(top).mark_bar(color="#1f6f8b").encode(
            x=alt.X("Volume (Mds FCFA):Q"),
            y=alt.Y("ISIN:N", title=None, sort="-x"),
            tooltip=["ISIN", "Pays", "Instrument", "Séances",
                     alt.Tooltip("Volume (Mds FCFA):Q", format=".1f"),
                     alt.Tooltip("Part cumulée:Q", format=".1%")],
        ).properties(height=460, title="20 titres les plus échangés"),
        width="stretch")
    if not top.empty:
        st.markdown(
            f"Les 20 premiers titres concentrent **{top['Part cumulée'].iloc[-1]:.1%}** "
            f"du volume, sur {synthese['Titres négociés']} titres négociés.")

# --------------------------------------------------------------------------
# Qualité d'exécution
# --------------------------------------------------------------------------
with onglets[2]:
    repartition = qualite_prix.synthese(donnees)
    repartition_graphique = repartition.assign(
        Score=repartition["Score"].astype(str))
    gauche, droite = st.columns(2)
    palette = dict(qualite_prix.COULEURS_SCORES, **{"Non évaluable": "#9aa0a6"})
    for colonne, mesure, titre in (
            (gauche, "Lignes", "Répartition des lignes"),
            (droite, "Volume (Mds FCFA)", "Répartition du volume")):
        with colonne:
            st.altair_chart(
                alt.Chart(repartition_graphique).mark_arc(innerRadius=55).encode(
                    theta=alt.Theta(f"{mesure}:Q", stack=True),
                    color=alt.Color("Score:N", title=None,
                                    scale=alt.Scale(domain=list(palette),
                                                    range=list(palette.values()))),
                    tooltip=["Score", alt.Tooltip(f"{mesure}:Q", format=".1f")],
                ).properties(height=260, title=titre),
                width="stretch")
    st.dataframe(
        repartition, hide_index=True, width="stretch",
        column_config={
            "Volume (Mds FCFA)": st.column_config.NumberColumn(format="%.0f"),
            "Part des lignes": st.column_config.NumberColumn(format="percent"),
            "Part du volume": st.column_config.NumberColumn(format="percent"),
        })

    st.subheader("Motifs de déclassement")
    motifs = (donnees[donnees["Score"].isin(
        [qualite_prix.SCORE_B, qualite_prix.SCORE_C])]["Motifs"]
        .value_counts().rename_axis("Motifs").reset_index(name="Lignes"))
    if motifs.empty:
        st.info("Aucune ligne déclassée sur ce périmètre.")
    else:
        st.altair_chart(
            alt.Chart(motifs).mark_bar(color="#c98a2e").encode(
                x=alt.X("Lignes:Q"),
                y=alt.Y("Motifs:N", title=None, sort="-x"),
                tooltip=["Motifs", "Lignes"],
            ).properties(height=200), width="stretch")

    st.subheader("Prints atypiques, les plus gros volumes d'abord")
    st.caption("Un écart isolé n'est pas une preuve : c'est un signalement. "
               "Aucune ligne n'est supprimée des données, elles sont marquées.")
    atypiques = secondaire.prints_atypiques(donnees)
    st.dataframe(
        atypiques, hide_index=True, width="stretch", height=420,
        column_config={
            "Date de transaction": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Prix moyen": st.column_config.NumberColumn(format="%.4f"),
            "YTM": st.column_config.NumberColumn(format="percent"),
            "Taux courbe": st.column_config.NumberColumn(format="percent"),
            "Écart courbe (pb)": st.column_config.NumberColumn(format="%.0f"),
            "Écart adjudication (pb)": st.column_config.NumberColumn(format="%.0f"),
            "Volume global (Mds FCFA)": st.column_config.NumberColumn(format="%.2f"),
            "Maturité résiduelle (années)": st.column_config.NumberColumn(format="%.2f"),
        })
    st.download_button(
        "Exporter les prints atypiques (CSV)",
        atypiques.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"prints_atypiques_{reference:%Y%m%d}.csv", mime="text/csv")

# --------------------------------------------------------------------------
# Rendements et courbe
# --------------------------------------------------------------------------
with onglets[3]:
    st.markdown("Chaque point est une séance de négociation, positionnée à sa "
                "maturité résiduelle et à son rendement, colorée par fiabilité. "
                "Le nuage devrait épouser la courbe souveraine ; ce qui s'en "
                "écarte est signalé.")
    pays_nuage = st.selectbox("Pays", sorted(donnees["Pays"].dropna().unique()))
    nuage = donnees[donnees["Pays"] == pays_nuage].assign(
        Score=lambda cadre: cadre["Score"].astype(str))
    if nuage.empty:
        st.info("Aucune transaction pour ce pays sur le périmètre.")
    else:
        palette = dict(qualite_prix.COULEURS_SCORES, **{"Non évaluable": "#9aa0a6"})
        points = alt.Chart(nuage).mark_circle(opacity=0.55).encode(
            x=alt.X("Maturité résiduelle (années):Q", title="Maturité résiduelle"),
            y=alt.Y("YTM:Q", title="Rendement", axis=alt.Axis(format="%"),
                    scale=alt.Scale(zero=False)),
            size=alt.Size("Volume global (Mds FCFA):Q", title="Volume",
                          scale=alt.Scale(range=[20, 500])),
            color=alt.Color("Score:N", title="Fiabilité",
                            scale=alt.Scale(domain=list(palette),
                                            range=list(palette.values()))),
            tooltip=["ISIN", alt.Tooltip("Date de transaction:T", format="%d/%m/%Y"),
                     alt.Tooltip("YTM:Q", format=".2%"),
                     alt.Tooltip("Taux courbe:Q", format=".2%"),
                     alt.Tooltip("Écart courbe (pb):Q", format=".0f"),
                     alt.Tooltip("Volume global (Mds FCFA):Q", format=".2f"),
                     "Motifs"],
        )
        courbe = courbes.construire_courbe(
            pays_nuage, reference, courbes.NIVEAU_CGF,
            courbes.ParametresCourbe.depuis_etat(reglages_courbe))
        couches = points
        if not courbe.empty:
            couches = points + alt.Chart(courbe).mark_line(
                color="#333333", strokeDash=[5, 4]).encode(
                x=alt.X("Maturité:Q"), y=alt.Y("Taux:Q"))
        st.altair_chart(
            couches.properties(
                height=440,
                title=f"{pays_nuage} — rendements négociés et courbe actuelle"),
            width="stretch")
        st.caption("La courbe tracée est celle de la dernière publication ; les "
                   "points couvrent toute la période filtrée. L'écart de chaque "
                   "point est calculé contre la courbe de **sa** date, pas "
                   "contre celle-ci.")

# --------------------------------------------------------------------------
# Détail
# --------------------------------------------------------------------------
with onglets[4]:
    colonnes = ["Date de transaction", "Pays", "Instrument", "ISIN",
                "Nombre de transactions", "Quantité", "Prix moyen", "YTM",
                "Taux courbe", "Écart courbe (pb)", "Écart adjudication (pb)",
                "Volume global (Mds FCFA)", "Maturité résiduelle (années)",
                "Duration modifiée", "Convexité", "Score", "Motifs"]
    table = donnees[colonnes].sort_values("Date de transaction", ascending=False)
    st.dataframe(
        table.head(2000), hide_index=True, width="stretch", height=520,
        column_config={
            "Date de transaction": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Prix moyen": st.column_config.NumberColumn(format="%.4f"),
            "YTM": st.column_config.NumberColumn(format="percent"),
            "Taux courbe": st.column_config.NumberColumn(format="percent"),
            "Écart courbe (pb)": st.column_config.NumberColumn(format="%.0f"),
            "Écart adjudication (pb)": st.column_config.NumberColumn(format="%.0f"),
            "Volume global (Mds FCFA)": st.column_config.NumberColumn(format="%.3f"),
            "Maturité résiduelle (années)": st.column_config.NumberColumn(format="%.2f"),
            "Duration modifiée": st.column_config.NumberColumn(format="%.2f"),
            "Convexité": st.column_config.NumberColumn(format="%.1f"),
        })
    if len(table) > 2000:
        st.caption(f"Affichage limité aux 2 000 lignes les plus récentes sur "
                   f"{len(table):,} — l'export contient tout.".replace(",", " "))
    st.download_button(
        "Exporter ce périmètre (CSV)",
        table.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"secondaire_{reference:%Y%m%d}.csv", mime="text/csv")
