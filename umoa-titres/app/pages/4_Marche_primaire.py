# -*- coding: utf-8 -*-
"""Marché primaire — adjudications, coût de financement et tension.

Le compartiment le plus riche des sources disponibles, et celui qui n'était
exploité nulle part : 4 078 titres servis en 1 763 opérations depuis 2014.
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.lib import chargement, primaire  # noqa: E402

st.set_page_config(page_title="Marché primaire", page_icon="🏛️", layout="wide")


@st.cache_data(show_spinner=False)
def _donnees() -> tuple:
    return primaire.lignes(), primaire.operations()


def _pourcent(valeur, decimales: int = 2) -> str:
    return "—" if pd.isna(valeur) else f"{valeur * 100:.{decimales}f} %"


def _milliards(valeur, decimales: int = 0) -> str:
    return ("—" if pd.isna(valeur)
            else f"{valeur:,.{decimales}f} Mds".replace(",", " "))


st.title("Marché primaire")
reference = chargement.date_reference()
st.caption(f"Adjudications de titres publics UMOA au {reference:%d/%m/%Y}. "
           "Les volumes sont agrégés au niveau de l'opération, les taux au "
           "niveau du titre.")

detail_complet, operations_completes = _donnees()

# --------------------------------------------------------------------------
# Filtres
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Périmètre")
    annees = sorted(operations_completes["Année"].dropna().unique().astype(int))
    debut, fin = st.select_slider(
        "Période", annees, value=(max(annees[0], annees[-1] - 4), annees[-1]))
    pays = st.multiselect(
        "Pays", sorted(detail_complet["Pays"].dropna().unique()),
        default=sorted(detail_complet["Pays"].dropna().unique()))
    instruments = st.multiselect(
        "Instrument", sorted(detail_complet["Instrument"].dropna().unique()),
        default=sorted(detail_complet["Instrument"].dropna().unique()),
        help="BAT : bons du Trésor (court terme). OAT : obligations. "
             "ES : émission simultanée regroupant plusieurs souches.")
    etats = st.multiselect(
        "État", sorted(detail_complet["État"].dropna().unique()),
        default=["réalisée"] if "réalisée" in set(detail_complet["État"]) else None)
    rachats = st.checkbox("Inclure les opérations de rachat", value=True)


def _filtrer(donnees: pd.DataFrame) -> pd.DataFrame:
    masque = (donnees["Pays"].isin(pays)
              & donnees["Date de l'opération"].dt.year.between(debut, fin))
    if instruments:
        masque &= donnees["Instrument"].isin(instruments)
    if etats:
        masque &= donnees["État"].isin(etats)
    if not rachats and "Opération de rachat" in donnees.columns:
        masque &= ~donnees["Opération de rachat"].fillna(False)
    return donnees[masque]


detail = _filtrer(detail_complet)
entetes = _filtrer(operations_completes)
if detail.empty:
    st.info("Aucune adjudication sur ce périmètre.")
    st.stop()

# --------------------------------------------------------------------------
# Synthèse
# --------------------------------------------------------------------------
synthese = primaire.resume(entetes, detail)

cartes = st.columns(6)
cartes[0].metric("Opérations", f"{synthese['Opérations']:,}".replace(",", " "),
                 help=f"{synthese['Titres servis']} titres servis — une "
                      "opération peut porter plusieurs souches.")
cartes[1].metric("Montant retenu", _milliards(synthese["Montant retenu (Mds FCFA)"]),
                 help="Somme au niveau de l'opération, hors opérations à "
                      "montants incohérents.")
cartes[2].metric("Taux de couverture", f"{synthese['Taux de couverture moyen']:.2f}",
                 help="Montant soumis rapporté au montant annoncé, pondéré par "
                      "l'enveloppe. Au-dessus de 1, la demande excède l'offre.")
cartes[3].metric("Taux de service", _pourcent(synthese["Taux de service moyen"], 1),
                 help="Part des soumissions effectivement servies.")
cartes[4].metric("Coût de financement",
                 _pourcent(synthese["Rendement moyen pondéré"]),
                 help="Rendement moyen pondéré servi, pondéré par les montants "
                      "retenus.")
cartes[5].metric("Maturité moyenne",
                 f"{synthese['Maturité moyenne (années)']:.2f} ans")

if synthese["Opérations à montant incohérent"]:
    st.warning(
        f"{synthese['Opérations à montant incohérent']} opération(s) du "
        "périmètre portent des montants négatifs dans la source. Elles sont "
        "comptées dans le nombre d'opérations et dans les taux, mais **exclues "
        "des sommes de volume**. Le niveau opération reste de loin le plus "
        "fiable : 1,2 % d'anomalies, contre 14 % sur la ventilation par titre.")

onglets = st.tabs(["Activité", "Coût de financement", "Tension des adjudications",
                   "Émissions à venir", "Détail"])

# --------------------------------------------------------------------------
# Activité
# --------------------------------------------------------------------------
with onglets[0]:
    evolution = primaire.evolution_mensuelle(entetes)
    if evolution.empty:
        st.info("Aucune opération sur ce périmètre.")
    else:
        empilable = evolution.melt(
            id_vars="Mois", value_vars=["Annoncé", "Soumis", "Retenu"],
            var_name="Montant", value_name="Mds FCFA")
        volumes = alt.Chart(empilable).mark_line(point=False).encode(
            x=alt.X("Mois:T", title=None),
            y=alt.Y("Mds FCFA:Q", title="Mds FCFA"),
            color=alt.Color("Montant:N", title=None,
                            scale=alt.Scale(
                                domain=["Annoncé", "Soumis", "Retenu"],
                                range=["#9aa0a6", "#1f6f8b", "#2e7d5b"])),
            tooltip=[alt.Tooltip("Mois:T", format="%m/%Y"), "Montant",
                     alt.Tooltip("Mds FCFA:Q", format=".0f")],
        ).properties(height=300, title="Volumes mensuels")
        st.altair_chart(volumes, width="stretch")

        couverture = alt.Chart(evolution).mark_area(
            color="#1f6f8b", opacity=0.35, line={"color": "#1f6f8b"}).encode(
            x=alt.X("Mois:T", title=None),
            y=alt.Y("Taux de couverture:Q", title="Couverture"),
            tooltip=[alt.Tooltip("Mois:T", format="%m/%Y"),
                     alt.Tooltip("Taux de couverture:Q", format=".2f"),
                     alt.Tooltip("Opérations:Q", format=".0f")],
        ).properties(height=180, title="Taux de couverture mensuel")
        reference_un = alt.Chart(pd.DataFrame({"y": [1.0]})).mark_rule(
            color="#b23a3a", strokeDash=[4, 3]).encode(y="y:Q")
        st.altair_chart(couverture + reference_un, width="stretch")
        st.caption("La ligne rouge marque la couverture à 1,0 : en dessous, "
                   "l'émetteur n'a pas reçu assez d'offres pour remplir son "
                   "enveloppe annoncée.")

        gauche, droite = st.columns(2)
        with gauche:
            par_pays = entetes.groupby("Pays", observed=True).agg(**{
                "Opérations": ("Opération", "size"),
                "Retenu (Mds FCFA)": ("Montant retenu opération (Mds FCFA)", "sum"),
            }).reset_index().sort_values("Retenu (Mds FCFA)", ascending=False)
            st.altair_chart(
                alt.Chart(par_pays).mark_bar(color="#1f6f8b").encode(
                    x=alt.X("Retenu (Mds FCFA):Q"),
                    y=alt.Y("Pays:N", title=None, sort="-x"),
                    tooltip=["Pays", "Opérations",
                             alt.Tooltip("Retenu (Mds FCFA):Q", format=".0f")],
                ).properties(height=280, title="Montant retenu par pays"),
                width="stretch")
        with droite:
            maturites = primaire.classes_de_maturite(detail)
            maturites["Classe de maturité"] = maturites["Classe de maturité"].astype(str)
            st.altair_chart(
                alt.Chart(maturites).mark_bar(color="#2e7d5b").encode(
                    x=alt.X("Montant retenu (Mds FCFA):Q"),
                    y=alt.Y("Classe de maturité:N", title=None,
                            sort=list(maturites["Classe de maturité"])),
                    tooltip=["Classe de maturité", "Titres",
                             alt.Tooltip("Montant retenu (Mds FCFA):Q", format=".0f"),
                             alt.Tooltip("Rendement moyen pondéré:Q", format=".2%")],
                ).properties(height=280, title="Montant retenu par maturité"),
                width="stretch")

# --------------------------------------------------------------------------
# Coût de financement
# --------------------------------------------------------------------------
with onglets[1]:
    reglages = st.columns(2)
    frequence = reglages[0].radio(
        "Fréquence", ["M", "Q", "Y"], index=1, horizontal=True,
        format_func={"M": "Mensuelle", "Q": "Trimestrielle", "Y": "Annuelle"}.get)
    axe = reglages[1].radio("Ventilation", ["Pays", "Instrument"], horizontal=True)

    cout = primaire.cout_financement(detail, par=axe, frequence=frequence)
    if cout.empty:
        st.info("Aucun rendement exploitable sur ce périmètre.")
    else:
        st.altair_chart(
            alt.Chart(cout).mark_line(point=True).encode(
                x=alt.X("Période:T", title=None),
                y=alt.Y("Rendement:Q", title="Rendement moyen pondéré",
                        axis=alt.Axis(format="%"), scale=alt.Scale(zero=False)),
                color=alt.Color(f"{axe}:N", title=None),
                tooltip=[axe, alt.Tooltip("Période:T", format="%m/%Y"),
                         alt.Tooltip("Rendement:Q", format=".3%"),
                         alt.Tooltip("Opérations:Q", format=".0f")],
            ).properties(height=380,
                         title="Coût de financement effectivement servi"),
            width="stretch")
        st.caption("Pondéré par les montants retenus : c'est le coût réellement "
                   "supporté par l'émetteur, pas une moyenne de taux affichés.")

        st.subheader("Par classe de maturité")
        maturites = primaire.classes_de_maturite(detail)
        maturites["Classe de maturité"] = maturites["Classe de maturité"].astype(str)
        st.altair_chart(
            alt.Chart(maturites.dropna(subset=["Rendement moyen pondéré"]))
            .mark_bar(color="#1f6f8b").encode(
                x=alt.X("Classe de maturité:N", title=None,
                        sort=list(maturites["Classe de maturité"])),
                y=alt.Y("Rendement moyen pondéré:Q", axis=alt.Axis(format="%"),
                        scale=alt.Scale(zero=False)),
                tooltip=["Classe de maturité",
                         alt.Tooltip("Rendement moyen pondéré:Q", format=".2%"),
                         "Titres"],
            ).properties(height=280,
                         title="Courbe de financement primaire, sur le périmètre filtré"),
            width="stretch")
        st.dataframe(
            maturites, hide_index=True, width="stretch",
            column_config={
                "Montant retenu (Mds FCFA)": st.column_config.NumberColumn(format="%.0f"),
                "Rendement moyen pondéré": st.column_config.NumberColumn(format="percent"),
            })

# --------------------------------------------------------------------------
# Tension
# --------------------------------------------------------------------------
with onglets[2]:
    ecarts = primaire.tension(detail)
    if ecarts.empty:
        st.info("Le taux marginal n'est renseigné sur aucune ligne de ce "
                "périmètre.")
    else:
        st.markdown(
            f"**{len(ecarts)} adjudications** publient à la fois le taux "
            "marginal et le taux moyen pondéré. L'écart entre les deux mesure "
            "la dispersion des offres reçues : plus il est large, plus "
            "l'émetteur a dû concéder pour remplir son enveloppe.")
        cartes_tension = st.columns(3)
        cartes_tension[0].metric(
            "Écart médian",
            f"{ecarts['Écart marginal / moyen (pb)'].median():.0f} pb")
        cartes_tension[1].metric(
            "Écart au 90ᵉ centile",
            f"{ecarts['Écart marginal / moyen (pb)'].quantile(0.9):.0f} pb")
        cartes_tension[2].metric(
            "Couverture de la mesure",
            f"{len(ecarts) / len(detail):.0%}",
            help="Part des lignes du périmètre publiant un taux marginal. La "
                 "source ne le publie pas systématiquement.")

        st.altair_chart(
            alt.Chart(ecarts).mark_circle(size=45, opacity=0.5).encode(
                x=alt.X("Date de l'opération:T", title=None),
                y=alt.Y("Écart marginal / moyen (pb):Q", title="Écart (pb)"),
                color=alt.Color("Pays:N", title=None),
                tooltip=["Pays", "Instrument", "ISIN",
                         alt.Tooltip("Date de l'opération:T", format="%d/%m/%Y"),
                         alt.Tooltip("Écart marginal / moyen (pb):Q", format=".0f"),
                         alt.Tooltip("Maturité (années):Q", format=".2f")],
            ).properties(height=340,
                         title="Écart taux marginal − taux moyen pondéré"),
            width="stretch")

        st.dataframe(
            ecarts.head(300), hide_index=True, width="stretch", height=360,
            column_config={
                "Date de l'opération": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Taux marginal (déc.)": st.column_config.NumberColumn(
                    "Taux marginal", format="percent"),
                "Taux moyen pondéré (déc.)": st.column_config.NumberColumn(
                    "Taux moyen pondéré", format="percent"),
                "Écart marginal / moyen (pb)": st.column_config.NumberColumn(format="%.0f"),
                "Maturité (années)": st.column_config.NumberColumn(format="%.2f"),
            })

# --------------------------------------------------------------------------
# À venir
# --------------------------------------------------------------------------
with onglets[3]:
    futures = primaire.a_venir()
    if futures.empty:
        st.info("Aucune opération annoncée ou planifiée.")
    else:
        annoncees = futures[futures["Catégorie"] == "À venir"]
        planifiees = futures[futures["Catégorie"] == "Planifiée"]
        cartes_futures = st.columns(3)
        cartes_futures[0].metric("Opérations annoncées", len(annoncees))
        cartes_futures[1].metric("Opérations planifiées", len(planifiees))
        cartes_futures[2].metric(
            "Enveloppe annoncée",
            _milliards(futures["Montant mis en adjudication (Mds FCFA)"].sum(skipna=True)))
        st.caption("« Annoncée » : opération publiée avec son enveloppe. "
                   "« Planifiée » : inscrite au calendrier prévisionnel, "
                   "détail non encore publié. La page Calendrier des émissions "
                   "reprend ces opérations dans un agenda daté, avec les "
                   "séances que le calendrier annonce sans fiche primaire.")
        st.dataframe(
            futures, hide_index=True, width="stretch",
            column_config={
                "Date de l'opération": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Date de valeur": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Échéance": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Montant mis en adjudication (Mds FCFA)": st.column_config.NumberColumn(
                    format="%.1f"),
                "Lien": st.column_config.LinkColumn("Avis", display_text="Ouvrir"),
            })

# --------------------------------------------------------------------------
# Détail
# --------------------------------------------------------------------------
with onglets[4]:
    grain = st.radio("Grain", ["Opérations", "Titres servis"], horizontal=True)
    if grain == "Opérations":
        colonnes = ["Date de l'opération", "Pays", "Instrument", "Opération",
                    "Nombre de titres", "Montant annoncé opération (Mds FCFA)",
                    "Montant soumis opération (Mds FCFA)",
                    "Montant retenu opération (Mds FCFA)", "Taux de couverture",
                    "Taux de service", "État", "Montant incohérent"]
        table = entetes[[c for c in colonnes if c in entetes.columns]]
    else:
        colonnes = ["Date de l'opération", "Pays", "Instrument", "ISIN",
                    "Maturité (années)", "Échéance", "Taux d'intérêt (déc.)",
                    "Rendement moyen pondéré (déc.)", "Taux marginal (déc.)",
                    "Montant retenu (Mds FCFA)", "Type d'amortissement", "État"]
        table = detail[[c for c in colonnes if c in detail.columns]]

    table = table.sort_values("Date de l'opération", ascending=False)
    st.dataframe(
        table, hide_index=True, width="stretch", height=520,
        column_config={
            "Date de l'opération": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Échéance": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Taux de couverture": st.column_config.NumberColumn(format="%.2f"),
            "Taux de service": st.column_config.NumberColumn(format="%.2f"),
            "Maturité (années)": st.column_config.NumberColumn(format="%.2f"),
            "Taux d'intérêt (déc.)": st.column_config.NumberColumn(
                "Taux facial", format="percent"),
            "Rendement moyen pondéré (déc.)": st.column_config.NumberColumn(
                "Rendement moyen pondéré", format="percent"),
            "Taux marginal (déc.)": st.column_config.NumberColumn(
                "Taux marginal", format="percent"),
            "Montant annoncé opération (Mds FCFA)": st.column_config.NumberColumn(format="%.1f"),
            "Montant soumis opération (Mds FCFA)": st.column_config.NumberColumn(format="%.1f"),
            "Montant retenu opération (Mds FCFA)": st.column_config.NumberColumn(format="%.1f"),
            "Montant retenu (Mds FCFA)": st.column_config.NumberColumn(format="%.1f"),
        })
    st.download_button(
        "Exporter (CSV)", table.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"primaire_{grain.lower().replace(' ', '_')}_{reference:%Y%m%d}.csv",
        mime="text/csv")
