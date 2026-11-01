# -*- coding: utf-8 -*-
"""Courbes de taux — les trois niveaux de lecture et les réglages de la N2.

Rappel de la décision d'architecture : le taux de référence n'est pas recalculé,
il est repris d'UMOA-Titres. Trois niveaux cohabitent en permanence :

    N0  brut       « Zéro Coupon » publié          -> audit
    N1  officielle « Taux Après Lissage » publié    -> référence de place, défaut
    N2  reconstruite reconstruction maison            -> analytique

Cette page est l'endroit où l'on règle N2 et où l'on voit ce que ce réglage
change, avant de l'appliquer au reste de l'app.
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.lib import chargement, courbes  # noqa: E402

st.set_page_config(page_title="Courbes de taux", page_icon="📉", layout="wide")

COULEURS_NIVEAUX = {
    courbes.NIVEAU_BRUT: "#9aa0a6",
    courbes.NIVEAU_OFFICIELLE: "#1f6f8b",
    courbes.NIVEAU_RECONSTRUITE: "#b23a3a",
}
COULEURS_ORIGINES = {
    "Publié": "#1f6f8b", "Ancré (BAT)": "#2e7d5b",
    "Interpolé": "#9aa0a6", "Extrapolé": "#c98a2e",
}


@st.cache_data(show_spinner="Reconstruction de l'historique…")
def _serie(pays_liste: tuple, maturite: float, niveau: str, reglages: dict,
           depuis: pd.Timestamp) -> pd.DataFrame:
    # Une série longue reconstruit une courbe par pays et par publication : le
    # premier tracé coûte quelques secondes, les suivants sont instantanés.
    return courbes.serie_temporelle(
        list(pays_liste), maturite, niveau,
        courbes.ParametresCourbe.depuis_etat(reglages), depuis)


def _pourcent(valeur, decimales: int = 2) -> str:
    return "—" if pd.isna(valeur) else f"{valeur * 100:.{decimales}f} %"


def _pb(valeur, decimales: int = 0) -> str:
    return "—" if pd.isna(valeur) else f"{valeur:,.{decimales}f} pb".replace(",", " ")


st.title("Courbes de taux")
reference = chargement.date_reference()

# --------------------------------------------------------------------------
# Réglages
# --------------------------------------------------------------------------
defauts = courbes.parametres_actifs()

with st.sidebar:
    st.header("Périmètre")
    pays_liste = sorted(chargement.courbes_taux()["Pays"].dropna().unique())
    pays = st.selectbox("Pays", pays_liste,
                        index=pays_liste.index("Côte d'Ivoire")
                        if "Côte d'Ivoire" in pays_liste else 0)
    dates = courbes.dates_disponibles(pays)
    date = st.selectbox("Date de courbe", dates, index=0,
                        format_func=lambda d: f"{d:%d/%m/%Y}")
    niveaux = st.multiselect(
        "Niveaux affichés", list(courbes.LIBELLES_NIVEAUX),
        default=[courbes.NIVEAU_OFFICIELLE, courbes.NIVEAU_RECONSTRUITE],
        format_func=lambda n: courbes.LIBELLES_NIVEAUX[n])

    st.header("Réglages de la courbe reconstruite (N2)")
    st.caption("Ces réglages ne touchent ni au brut ni à l'officielle : les "
               "trois niveaux restent disponibles côte à côte.")

    with st.expander("Interpolation et grille", expanded=True):
        interpolateur = st.radio(
            "Interpolateur", ["pchip", "lineaire", "nss"],
            index=["pchip", "lineaire", "nss"].index(defauts.interpolateur),
            format_func={"pchip": "PCHIP (monotone)", "lineaire": "Linéaire",
                         "nss": "Nelson-Siegel-Svensson"}.get,
            help="PCHIP préserve la monotonie : une spline cubique naturelle "
                 "overshoote entre deux points éloignés, cas fréquent ici où il "
                 "manque parfois cinq ans entre deux maturités publiées.")
        pas = st.select_slider("Pas de la grille (années)",
                               [0.25, 0.5, 1.0], value=defauts.pas)
        maturite_max = st.slider("Maturité maximale (années)", 5.0, 30.0,
                                 defauts.maturite_max, 1.0)
        extrapolation = st.radio(
            "Au-delà du dernier point publié", ["nss", "plat"],
            index=["nss", "plat"].index(defauts.extrapolation),
            format_func={"nss": "Extrapolation NSS", "plat": "Prolongement plat"}.get,
            help="Le prolongement plat sous-estime le risque de duration "
                 "longue — c'est la limite déjà documentée sur le benchmark.")

    with st.expander("Ancrage sur les adjudications", expanded=True):
        ancrage_bat = st.toggle(
            "Ancrer le court terme sur les adjudications",
            value=defauts.ancrage_bat,
            help="Sur 272 comparaisons à 3 mois, l'écart entre le taux servi en "
                 "adjudication et la courbe lissée a un écart-type de 162 pb. "
                 "Une adjudication est un prix, pas une estimation.")
        ancrage_fenetre = st.slider("Fenêtre de collecte (jours)", 30, 365,
                                    defauts.ancrage_fenetre_jours, 15,
                                    disabled=not ancrage_bat)
        ancrage_maturite = st.select_slider(
            "Maturité maximale ancrée (années)", [0.25, 0.5, 0.75, 1.0],
            value=defauts.ancrage_maturite_max, disabled=not ancrage_bat)
        ancrage_min = st.slider("Adjudications minimum par point", 1, 5,
                                defauts.ancrage_min_observations,
                                disabled=not ancrage_bat)
        ancrage_poids = st.slider(
            "Poids de l'adjudication", 0.0, 1.0, defauts.ancrage_poids, 0.1,
            disabled=not ancrage_bat,
            help="1,0 remplace le point publié ; en dessous, les deux sont "
                 "mélangés.")

    with st.expander("Garde-fous"):
        taux_max = st.slider("Taux maximum (%)", 10.0, 30.0,
                             defauts.taux_max * 100, 1.0) / 100
        seuil_fraicheur = st.slider("Courbe périmée au-delà de (jours)", 7, 90,
                                    defauts.seuil_fraicheur_jours, 7)

params = courbes.ParametresCourbe(
    interpolateur=interpolateur, pas=pas, maturite_max=maturite_max,
    extrapolation=extrapolation, ancrage_bat=ancrage_bat,
    ancrage_fenetre_jours=ancrage_fenetre, ancrage_maturite_max=ancrage_maturite,
    ancrage_min_observations=ancrage_min, ancrage_poids=ancrage_poids,
    taux_max=taux_max, seuil_fraicheur_jours=seuil_fraicheur)

with st.sidebar:
    actifs = courbes.parametres_actifs()
    if st.button("Appliquer à toute l'app", type="primary",
                 disabled=params == actifs):
        st.session_state[courbes.CLE_ETAT] = params.en_dict()
        st.success("Réglages appliqués. Le référentiel et les fiches titre "
                   "utilisent désormais cette courbe.")
    if params != actifs:
        st.caption("Réglages en cours d'essai — non encore appliqués au reste "
                   "de l'app.")

# --------------------------------------------------------------------------
# Fraîcheur
# --------------------------------------------------------------------------
fraicheur = courbes.fraicheur_courbes(params)
ligne_pays = fraicheur[fraicheur["Pays"] == pays]
if not ligne_pays.empty:
    etat = ligne_pays.iloc[0]
    message = (f"Dernière courbe {pays} : **{etat['Dernière courbe']:%d/%m/%Y}** "
               f"({etat['Ancienneté (jours)']} jours), "
               f"{etat['Points publiés']} points publiés. "
               f"Inchangée sur **{etat['Part de semaines inchangées']:.0%}** des "
               "publications historiques")
    if etat["Publications figées"]:
        message += (f", dont les **{etat['Publications figées']} dernières**")
    st.markdown(message + ".")
    if etat["Publications figées"] >= 3:
        st.warning(
            "Cette courbe n'a pas bougé depuis plusieurs publications "
            "consécutives. Un mouvement absent n'est pas un mouvement nul : "
            "c'est probablement une absence de réestimation, à ne pas lire "
            "comme un signal de marché.")

onglets = st.tabs(["Courbe", "Ancrage sur les adjudications",
                   "Comparaison pays", "Historique"])

# --------------------------------------------------------------------------
# Courbe
# --------------------------------------------------------------------------
with onglets[0]:
    date_courbe = courbes.date_courbe_applicable(pays, date)
    couches, tables = [], []
    for niveau in niveaux:
        donnees = courbes.construire_courbe(pays, date, niveau, params)
        if donnees.empty:
            continue
        donnees = donnees.assign(Niveau=courbes.LIBELLES_NIVEAUX[niveau],
                                 _cle=niveau)
        tables.append(donnees)
        marque = alt.Chart(donnees).mark_line(
            point=(niveau != courbes.NIVEAU_RECONSTRUITE),
            strokeDash=[4, 3] if niveau == courbes.NIVEAU_BRUT else [0]).encode(
            x=alt.X("Maturité:Q", title="Maturité (années)"),
            y=alt.Y("Taux:Q", title="Taux", axis=alt.Axis(format="%"),
                    scale=alt.Scale(zero=False)),
            color=alt.Color("Niveau:N", title=None,
                            scale=alt.Scale(
                                domain=[courbes.LIBELLES_NIVEAUX[n] for n in niveaux],
                                range=[COULEURS_NIVEAUX[n] for n in niveaux])),
            tooltip=["Niveau", alt.Tooltip("Maturité:Q", format=".2f"),
                     alt.Tooltip("Taux:Q", format=".3%"), "Origine"],
        )
        couches.append(marque)

    if not couches:
        st.info("Aucune courbe publiée pour ce pays à cette date.")
    else:
        st.altair_chart(
            alt.layer(*couches).properties(
                height=380,
                title=f"{pays} — courbe du {date_courbe:%d/%m/%Y}"),
            width="stretch")

        reconstruite = next((t for t in tables if t["_cle"].iloc[0] == courbes.NIVEAU_RECONSTRUITE), None)
        if reconstruite is not None:
            origines = alt.Chart(reconstruite).mark_tick(thickness=3, size=26).encode(
                x=alt.X("Maturité:Q", title="Maturité (années)"),
                color=alt.Color("Origine:N", title="Origine du point",
                                scale=alt.Scale(
                                    domain=list(COULEURS_ORIGINES),
                                    range=list(COULEURS_ORIGINES.values()))),
                tooltip=[alt.Tooltip("Maturité:Q", format=".2f"),
                         alt.Tooltip("Taux:Q", format=".3%"), "Origine"],
            ).properties(height=90, title="Ce qui est observé et ce qui est reconstruit")
            st.altair_chart(origines, width="stretch")

    st.subheader("Diagnostic")
    diagnostic = courbes.diagnostic_courbe(pays, date, params)
    if diagnostic:
        cartes = st.columns(5)
        cartes[0].metric("Points publiés", diagnostic["Points publiés"],
                         help="La grille source est trouée : le point 10 ans "
                              "n'existe que sur 48 % des courbes, le 15 ans sur 14 %.")
        cartes[1].metric("Rugosité brut", _pb(diagnostic["Rugosité brut (pb)"]),
                         help="Moyenne des différences secondes. Plus c'est bas, "
                              "plus la courbe est lisse.")
        cartes[2].metric("Rugosité officielle",
                         _pb(diagnostic["Rugosité officielle (pb)"]))
        cartes[3].metric("Rugosité (reconstruite)", _pb(diagnostic["Rugosité reconstruite (pb)"]))
        cartes[4].metric("Inversion 3 mois / 1 an",
                         _pb(diagnostic["Inversion 3 mois / 1 an (pb)"]),
                         help="Positif = le 3 mois cote au-dessus du 1 an. "
                              "7,7 % des courbes dépassent +100 pb, ce qui n'est "
                              "pas économiquement plausible.")

        saut = diagnostic["Saut max reconstruit (pb)"]
        if not pd.isna(saut) and saut > 200:
            st.warning(
                f"Saut de **{saut:.0f} pb** entre deux maturités voisines de la "
                "courbe reconstruite. L'ancrage ne corrige que les maturités "
                "effectivement adjugées sur la période : là où l'État n'a pas "
                "émis, le point publié subsiste tel quel.")

    comparaison = courbes.comparer_niveaux(pays, date, params)
    if not comparaison.empty:
        st.subheader("Officielle contre reconstruite")
        ecarts = comparaison["Écart reconstruit - officiel (pb)"].dropna()
        if not ecarts.empty:
            resume = st.columns(3)
            resume[0].metric("Écart médian", _pb(ecarts.median()))
            resume[1].metric("Écart maximum", _pb(ecarts.abs().max()))
            resume[2].metric("Points comparables", len(ecarts),
                             help="Au-delà de la dernière maturité publiée, il "
                                  "n'y a rien à comparer : la reconstruite extrapole.")
        st.dataframe(
            comparaison, hide_index=True, width="stretch", height=340,
            column_config={
                "Maturité": st.column_config.NumberColumn(format="%.2f"),
                "Taux reconstruit": st.column_config.NumberColumn(format="percent"),
                "Taux officiel": st.column_config.NumberColumn(format="percent"),
                "Taux brut": st.column_config.NumberColumn(format="percent"),
                "Écart reconstruit - officiel (pb)": st.column_config.NumberColumn(format="%.0f"),
            })

# --------------------------------------------------------------------------
# Ancrage
# --------------------------------------------------------------------------
with onglets[1]:
    if not params.ancrage_bat:
        st.info("L'ancrage est désactivé. La courbe reconstruite reprend les points "
                "publiés tels quels sur tout le spectre.")
    else:
        date_courbe = courbes.date_courbe_applicable(pays, date)
        ancrages = courbes.points_ancrage_bat(pays, date_courbe, params)
        publies = courbes.points_publies(pays, date_courbe,
                                         courbes.NIVEAU_OFFICIELLE)
        st.markdown(
            f"Adjudications retenues dans les **{params.ancrage_fenetre_jours} "
            f"jours** précédant le {date_courbe:%d/%m/%Y}, jusqu'à "
            f"**{params.ancrage_maturite_max:g} an(s)** de maturité, avec au "
            f"moins **{params.ancrage_min_observations}** observation(s) par point.")

        if ancrages.empty:
            st.warning(
                "Aucun point d'ancrage retenu pour ce pays à cette date. "
                "L'ancrage ne peut corriger que les maturités effectivement "
                "adjugées : élargir la fenêtre ou abaisser le nombre minimum "
                "d'observations ne crée pas d'adjudication là où l'État n'a pas "
                "émis.")
        else:
            fusion = ancrages.merge(
                publies.rename(columns={"Taux": "Taux publié"}),
                on="Maturité", how="left")
            fusion["Écart (pb)"] = (fusion["Taux"] - fusion["Taux publié"]) * 10_000
            fusion = fusion.rename(columns={"Taux": "Taux adjugé"})
            st.dataframe(
                fusion[["Maturité", "Observations", "Taux adjugé", "Taux publié",
                        "Écart (pb)"]],
                hide_index=True, width="stretch",
                column_config={
                    "Maturité": st.column_config.NumberColumn(format="%.2f"),
                    "Observations": st.column_config.NumberColumn(format="%d"),
                    "Taux adjugé": st.column_config.NumberColumn(format="percent"),
                    "Taux publié": st.column_config.NumberColumn(format="percent"),
                    "Écart (pb)": st.column_config.NumberColumn(format="%.0f"),
                })
            st.caption("`Écart` mesure de combien le lissage source s'éloigne du "
                       "taux réellement servi. Un écart vide signifie que la "
                       "maturité n'est pas publiée dans la courbe.")

# --------------------------------------------------------------------------
# Comparaison pays
# --------------------------------------------------------------------------
with onglets[2]:
    niveau_comparaison = st.radio(
        "Niveau", [courbes.NIVEAU_OFFICIELLE, courbes.NIVEAU_RECONSTRUITE],
        format_func=lambda n: courbes.LIBELLES_NIVEAUX[n], horizontal=True)
    selection = st.multiselect("Pays comparés", pays_liste, default=pays_liste)
    empilees = []
    for nom in selection:
        donnees = courbes.construire_courbe(nom, date, niveau_comparaison, params)
        if not donnees.empty:
            empilees.append(donnees.assign(Pays=nom))
    if not empilees:
        st.info("Aucune courbe disponible à cette date.")
    else:
        toutes = pd.concat(empilees, ignore_index=True)
        st.altair_chart(
            alt.Chart(toutes).mark_line().encode(
                x=alt.X("Maturité:Q", title="Maturité (années)"),
                y=alt.Y("Taux:Q", title="Taux", axis=alt.Axis(format="%"),
                        scale=alt.Scale(zero=False)),
                color=alt.Color("Pays:N", title=None),
                tooltip=["Pays", alt.Tooltip("Maturité:Q", format=".2f"),
                         alt.Tooltip("Taux:Q", format=".3%"), "Origine"],
            ).properties(height=420,
                         title=f"Courbes souveraines au {date:%d/%m/%Y}"),
            width="stretch")
        st.caption("Chaque pays est affiché à sa dernière courbe publiée à cette "
                   "date ou avant — les publications ne sont pas synchronisées.")

# --------------------------------------------------------------------------
# Historique
# --------------------------------------------------------------------------
with onglets[3]:
    reglages = st.columns(3)
    maturite = reglages[0].select_slider(
        "Maturité suivie (années)", [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0],
        value=5.0)
    profondeur = reglages[1].selectbox("Profondeur", [1, 2, 3, 5, 10], index=2,
                                       format_func=lambda a: f"{a} an(s)")
    niveau_serie = reglages[2].radio(
        "Niveau", [courbes.NIVEAU_OFFICIELLE, courbes.NIVEAU_RECONSTRUITE],
        format_func=lambda n: courbes.LIBELLES_NIVEAUX[n], horizontal=True,
        key="niveau_serie")

    depuis = reference - pd.DateOffset(years=profondeur)
    serie = _serie(tuple(pays_liste), maturite, niveau_serie, params.en_dict(),
                   depuis)
    if serie.empty:
        st.info("Aucune donnée sur cette période.")
    else:
        st.altair_chart(
            alt.Chart(serie).mark_line().encode(
                x=alt.X("Date:T", title=None),
                y=alt.Y("Taux:Q", title="Taux", axis=alt.Axis(format="%"),
                        scale=alt.Scale(zero=False)),
                color=alt.Color("Pays:N", title=None),
                tooltip=["Pays", alt.Tooltip("Date:T", format="%d/%m/%Y"),
                         alt.Tooltip("Taux:Q", format=".3%")],
            ).properties(height=380,
                         title=f"Taux à {maturite:g} an(s), interpolé sur chaque "
                               "courbe publiée"),
            width="stretch")
        st.caption("La série est interpolée à chaque date : il n'existe pas de "
                   "série toute faite, la grille publiée étant irrégulière.")

    st.subheader("Fraîcheur, tous pays")
    st.dataframe(
        fraicheur, hide_index=True, width="stretch",
        column_config={
            "Dernière courbe": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Part de semaines inchangées": st.column_config.NumberColumn(
                format="percent",
                help="Part des publications où aucun point n'a bougé."),
            "Publications figées": st.column_config.NumberColumn(
                format="%d", help="Nombre de publications consécutives sans "
                                  "le moindre mouvement, à ce jour."),
        })
