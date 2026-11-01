# -*- coding: utf-8 -*-
"""Calendrier des émissions — agenda à venir, cadence et tenue des annonces.

La seule source prospective du dispositif : elle dit quand les Trésors viennent
au marché, avant que le primaire ne dise combien ils y ont levé.
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.lib import calendrier  # noqa: E402

st.set_page_config(page_title="Calendrier des émissions", page_icon="🗓️",
                   layout="wide")

COULEURS_ETAT = {
    calendrier.ETAT_ANNONCEE: "#2e7d5b",
    calendrier.ETAT_PLANIFIEE: "#1f6f8b",
    calendrier.ETAT_CALENDRIER: "#9aa0a6",
}


@st.cache_data(show_spinner=False)
def _evenements() -> pd.DataFrame:
    return calendrier.evenements()


@st.cache_data(show_spinner=False)
def _agenda() -> pd.DataFrame:
    return calendrier.agenda()


@st.cache_data(show_spinner=False)
def _rapproches() -> pd.DataFrame:
    passees = calendrier.evenements()
    return calendrier.rapprocher(passees[passees["Statut"] == "Passée"])


def _milliards(valeur, decimales: int = 0) -> str:
    return ("—" if pd.isna(valeur)
            else f"{valeur:,.{decimales}f} Mds".replace(",", " "))


st.title("Calendrier des émissions")
st.caption("Séances d'adjudication de titres publics UMOA annoncées par "
           "UMOA-Titres, du 05/01/2017 à l'horizon publié. Contrairement au "
           "reste de l'app, cette page se cale sur la date du jour : c'est un "
           "agenda, pas une valorisation.")

tous = _evenements()
futurs_complets = _agenda()
aujourdhui = pd.Timestamp.today().normalize()

# --------------------------------------------------------------------------
# Filtres
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Périmètre")
    pays_connus = sorted(tous["Pays"].dropna().unique())
    pays = st.multiselect("Pays", pays_connus, default=pays_connus)
    instruments_connus = sorted(tous["Instrument"].dropna().unique())
    instruments = st.multiselect("Instrument", instruments_connus,
                                 default=instruments_connus)
    horizon = st.slider("Horizon de l'agenda (jours)", 7, 180, 60, step=7)
    annees = sorted(tous["Année"].unique())
    debut, fin = st.select_slider(
        "Historique", annees, value=(max(annees[0], annees[-1] - 4), annees[-1]))


def _filtrer(donnees: pd.DataFrame) -> pd.DataFrame:
    masque = pd.Series(True, index=donnees.index)
    if pays:
        masque &= donnees["Pays"].isin(pays)
    if instruments:
        masque &= donnees["Instrument"].isin(instruments)
    return donnees[masque]


historique = _filtrer(tous)
historique = historique[historique["Année"].between(debut, fin)
                        & (historique["Statut"] == "Passée")]
futurs = _filtrer(futurs_complets)
agenda = futurs[futurs["Jours restants"] <= horizon]

# --------------------------------------------------------------------------
# Synthèse
# --------------------------------------------------------------------------
prochaine = futurs.head(1)
douze_mois = _filtrer(tous)
douze_mois = douze_mois[(douze_mois["Date"] < aujourdhui)
                        & (douze_mois["Date"] >= aujourdhui - pd.Timedelta(days=365))]
preavis = futurs["Préavis (jours)"].median()

cartes = st.columns(5)
if prochaine.empty:
    cartes[0].metric("Prochaine séance", "—")
else:
    ligne = prochaine.iloc[0]
    jours = int(ligne["Jours restants"])
    cartes[0].metric(
        "Prochaine séance", f"{ligne['Date']:%d/%m}",
        delta=("aujourd'hui" if jours == 0
               else f"dans {jours} jour{'s' if jours > 1 else ''}"),
        delta_color="off",
        help=str(ligne["Titre"]))
cartes[1].metric(f"Séances sous {horizon} jours", len(agenda),
                 help=f"{len(futurs)} séance(s) publiées au total, jusqu'au "
                      f"{futurs['Date'].max():%d/%m/%Y}" if not futurs.empty
                      else None)
cartes[2].metric("Enveloppe annoncée",
                 _milliards(agenda["Enveloppe (Mds FCFA)"].sum(skipna=True)),
                 help="Somme des montants mis en adjudication, annoncés ou "
                      "prévisionnels, sur l'horizon retenu. Les séances encore "
                      "sans fiche primaire n'y contribuent pas.")
cartes[3].metric("Cadence sur 12 mois", f"{len(douze_mois) / 12:.1f} / mois",
                 help=f"{len(douze_mois)} séances tenues depuis le "
                      f"{aujourdhui - pd.Timedelta(days=365):%d/%m/%Y}.")
cartes[4].metric("Préavis médian",
                 "—" if pd.isna(preavis) else f"{preavis:.0f} j",
                 help="Écart entre la publication de la fiche et la date de "
                      "séance, sur les séances à venir. Borne inférieure : la "
                      "source ne date que la dernière modification de la fiche.")

onglets = st.tabs(["Agenda", "Cadence", "Réalisations", "Détail"])

# --------------------------------------------------------------------------
# Agenda
# --------------------------------------------------------------------------
with onglets[0]:
    if agenda.empty:
        st.info("Aucune séance annoncée sur cet horizon et ce périmètre.")
    else:
        st.markdown(
            f"**{len(agenda)} séances** d'ici le {agenda['Date'].max():%d/%m/%Y}. "
            f"« {calendrier.ETAT_ANNONCEE} » : l'avis d'adjudication est publié "
            "avec son enveloppe. "
            f"« {calendrier.ETAT_PLANIFIEE} » : inscrite au calendrier "
            "prévisionnel du Trésor, montant indicatif. "
            f"« {calendrier.ETAT_CALENDRIER} » : la séance figure au calendrier "
            "mais aucune fiche primaire ne lui correspond encore.")

        ordre_pays = list(agenda.groupby("Pays")["Date"].min()
                          .sort_values().index)
        frise = alt.Chart(agenda).mark_circle(opacity=0.85).encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("Pays:N", title=None, sort=ordre_pays),
            size=alt.Size("Enveloppe (Mds FCFA):Q", title="Mds FCFA",
                          scale=alt.Scale(range=[80, 700])),
            color=alt.Color("État attendu:N", title=None,
                            scale=alt.Scale(domain=list(COULEURS_ETAT),
                                            range=list(COULEURS_ETAT.values()))),
            tooltip=["Pays", "Instrument", "État attendu",
                     alt.Tooltip("Date:T", format="%d/%m/%Y"),
                     alt.Tooltip("Jours restants:Q", format=".0f"),
                     alt.Tooltip("Enveloppe (Mds FCFA):Q", format=".1f")],
        ).properties(height=max(220, 40 * agenda["Pays"].nunique()),
                     title="Séances à venir")
        maintenant = alt.Chart(pd.DataFrame({"x": [aujourdhui]})).mark_rule(
            color="#b23a3a", strokeDash=[4, 3]).encode(x="x:T")
        st.altair_chart(frise + maintenant, width="stretch")

        semaines = agenda.assign(
            Semaine=agenda["Date"].dt.to_period("W").dt.start_time)
        par_semaine = semaines.groupby("Semaine").agg(**{
            "Séances": ("Date", "size"),
            "Enveloppe (Mds FCFA)": ("Enveloppe (Mds FCFA)", "sum"),
            "Pays": ("Pays", lambda s: ", ".join(sorted(set(s.dropna())))),
        }).reset_index()
        st.altair_chart(
            alt.Chart(par_semaine).mark_bar(color="#1f6f8b", size=18).encode(
                x=alt.X("Semaine:T", title=None),
                y=alt.Y("Enveloppe (Mds FCFA):Q", title="Mds FCFA"),
                tooltip=[alt.Tooltip("Semaine:T", format="Semaine du %d/%m"),
                         "Séances", "Pays",
                         alt.Tooltip("Enveloppe (Mds FCFA):Q", format=".0f")],
            ).properties(height=200, title="Enveloppe annoncée par semaine"),
            width="stretch")

        colonnes_agenda = ["Date", "Jours restants", "Pays", "Instrument",
                           "État attendu", "Enveloppe (Mds FCFA)",
                           "Date de valeur", "Lien"]
        st.dataframe(
            agenda[[c for c in colonnes_agenda if c in agenda.columns]],
            hide_index=True, width="stretch",
            column_config={
                "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Date de valeur": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Jours restants": st.column_config.NumberColumn(format="%d j"),
                "Enveloppe (Mds FCFA)": st.column_config.NumberColumn(format="%.1f"),
                "Lien": st.column_config.LinkColumn("Avis", display_text="Ouvrir"),
            })

        exports = st.columns(2)
        exports[0].download_button(
            "Ajouter à mon agenda (.ics)",
            calendrier.ics(agenda).encode("utf-8"),
            file_name=f"emissions_umoa_{aujourdhui:%Y%m%d}.ics",
            mime="text/calendar",
            help="Import direct dans Outlook ou Google Agenda. Événements "
                 "journée entière : la source ne publie pas d'heure de séance.")
        exports[1].download_button(
            "Exporter (CSV)",
            agenda[[c for c in colonnes_agenda if c in agenda.columns]]
            .to_csv(index=False).encode("utf-8-sig"),
            file_name=f"agenda_emissions_{aujourdhui:%Y%m%d}.csv",
            mime="text/csv")

# --------------------------------------------------------------------------
# Cadence
# --------------------------------------------------------------------------
with onglets[1]:
    if historique.empty:
        st.info("Aucune séance passée sur ce périmètre.")
    else:
        reglages = st.columns(2)
        frequence = reglages[0].radio(
            "Fréquence", ["M", "Q", "Y"], index=0, horizontal=True,
            format_func={"M": "Mensuelle", "Q": "Trimestrielle",
                         "Y": "Annuelle"}.get)
        axe = reglages[1].radio("Ventilation", ["Pays", "Instrument"],
                                horizontal=True)

        rythme = calendrier.cadence(historique, par=axe, frequence=frequence)
        st.altair_chart(
            alt.Chart(rythme).mark_bar().encode(
                x=alt.X("Période:T", title=None),
                y=alt.Y("Émissions:Q", title="Séances"),
                color=alt.Color(f"{axe}:N", title=None),
                tooltip=[axe, alt.Tooltip("Période:T", format="%m/%Y"),
                         "Émissions"],
            ).properties(height=320, title="Nombre de séances par période"),
            width="stretch")

        gauche, droite = st.columns(2)
        with gauche:
            grille = (historique.groupby(["Année", "Pays"], observed=True)
                      .size().rename("Séances").reset_index())
            st.altair_chart(
                alt.Chart(grille).mark_rect().encode(
                    x=alt.X("Année:O", title=None),
                    y=alt.Y("Pays:N", title=None),
                    color=alt.Color("Séances:Q", title="Séances",
                                    scale=alt.Scale(scheme="teals")),
                    tooltip=["Pays", "Année", "Séances"],
                ).properties(height=300, title="Venues au marché, par année"),
                width="stretch")
        with droite:
            jours = (historique.groupby("Jour de semaine", observed=True)
                     .size().rename("Séances").reset_index())
            st.altair_chart(
                alt.Chart(jours).mark_bar(color="#1f6f8b").encode(
                    x=alt.X("Séances:Q"),
                    y=alt.Y("Jour de semaine:N", title=None,
                            sort=calendrier.JOURS_SEMAINE),
                    tooltip=["Jour de semaine", "Séances"],
                ).properties(height=300, title="Répartition par jour de séance"),
                width="stretch")

        st.subheader("Régularité par émetteur")
        st.caption("L'intervalle médian entre deux séances consécutives dit "
                   "mieux que le décompte annuel à quel rythme un Trésor se "
                   "présente : deux campagnes serrées et vingt-quatre séances "
                   "régulières donnent le même total.")
        st.dataframe(
            calendrier.regularite(historique), hide_index=True, width="stretch",
            column_config={
                "Première": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Dernière": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Intervalle médian (jours)": st.column_config.NumberColumn(
                    format="%.0f"),
                "Émissions par an": st.column_config.NumberColumn(format="%.1f"),
            })

# --------------------------------------------------------------------------
# Réalisations
# --------------------------------------------------------------------------
with onglets[2]:
    rapproches = _rapproches()
    rapproches = _filtrer(rapproches)
    rapproches = rapproches[rapproches["Année"].between(debut, fin)]
    if rapproches.empty:
        st.info("Aucune séance passée sur ce périmètre.")
    else:
        publies = rapproches[rapproches["Rapprochement"] != "Aucun"]
        st.markdown(
            "Chaque séance du calendrier est rapprochée de son opération "
            "primaire, par l'URL de la fiche d'émission puis, à défaut, par le "
            "couple pays / date. Ce qui reste sans résultat publié n'est pas "
            "masqué : une séance peut avoir été reportée ou annulée sans que "
            "sa fiche disparaisse du calendrier.")

        cartes_reel = st.columns(5)
        cartes_reel[0].metric("Séances au calendrier", len(rapproches))
        cartes_reel[1].metric("Résultats publiés",
                              f"{len(publies) / len(rapproches):.1%}",
                              help=f"{len(publies)} séances appariées, dont "
                                   f"{(rapproches['Rapprochement'] == 'Pays et date').sum()} "
                                   "par le seul couple pays / date.")
        cartes_reel[2].metric(
            "Enveloppe annoncée",
            _milliards(publies["Montant annoncé (Mds FCFA)"].sum(skipna=True)))
        cartes_reel[3].metric(
            "Montant retenu",
            _milliards(publies["Montant retenu (Mds FCFA)"].sum(skipna=True)))
        realisation_globale = (
            publies["Montant retenu (Mds FCFA)"].sum(skipna=True)
            / publies["Montant annoncé (Mds FCFA)"].sum(skipna=True))
        cartes_reel[4].metric("Taux de réalisation",
                              f"{realisation_globale:.0%}",
                              help="Montant retenu rapporté à l'enveloppe "
                                   "annoncée, sur les séances appariées.")

        par_pays = publies.groupby("Pays", observed=True).agg(**{
            "Séances": ("Date", "size"),
            "Annoncé (Mds FCFA)": ("Montant annoncé (Mds FCFA)", "sum"),
            "Retenu (Mds FCFA)": ("Montant retenu (Mds FCFA)", "sum"),
        }).reset_index()
        par_pays["Taux de réalisation"] = (par_pays["Retenu (Mds FCFA)"]
                                           / par_pays["Annoncé (Mds FCFA)"])
        barres = alt.Chart(par_pays.dropna(subset=["Taux de réalisation"])
                           ).mark_bar(color="#2e7d5b").encode(
            x=alt.X("Taux de réalisation:Q", axis=alt.Axis(format="%")),
            y=alt.Y("Pays:N", title=None, sort="-x"),
            tooltip=["Pays", "Séances",
                     alt.Tooltip("Annoncé (Mds FCFA):Q", format=".0f"),
                     alt.Tooltip("Retenu (Mds FCFA):Q", format=".0f"),
                     alt.Tooltip("Taux de réalisation:Q", format=".1%")],
        ).properties(height=280,
                     title="Montant retenu rapporté à l'enveloppe annoncée")
        cible = alt.Chart(pd.DataFrame({"x": [1.0]})).mark_rule(
            color="#b23a3a", strokeDash=[4, 3]).encode(x="x:Q")
        st.altair_chart(barres + cible, width="stretch")
        st.caption("Au-dessus de 100 %, le Trésor a servi plus que son "
                   "enveloppe initiale — la faculté de sur-allocation est "
                   "prévue par les avis d'adjudication.")

        st.subheader("Couverture de la source")
        suivi = calendrier.appariement(rapproches)
        st.altair_chart(
            alt.Chart(suivi).mark_line(point=True, color="#1f6f8b").encode(
                x=alt.X("Année:O", title=None),
                y=alt.Y("Taux d'appariement:Q", axis=alt.Axis(format="%"),
                        scale=alt.Scale(zero=False)),
                tooltip=["Année", alt.Tooltip("Événements:Q", format=".0f"),
                         alt.Tooltip("Résultats publiés:Q", format=".0f"),
                         alt.Tooltip("Taux d'appariement:Q", format=".1%")],
            ).properties(height=220,
                         title="Part des séances dont le résultat est publié"),
            width="stretch")

        orphelines = rapproches[rapproches["Rapprochement"] == "Aucun"]
        if not orphelines.empty:
            st.markdown(f"**{len(orphelines)} séances annoncées sans résultat "
                        "publié** sur le périmètre retenu.")
            st.dataframe(
                orphelines[["Date", "Pays", "Instrument", "Titre", "Lien"]],
                hide_index=True, width="stretch", height=260,
                column_config={
                    "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                    "Lien": st.column_config.LinkColumn("Fiche",
                                                        display_text="Ouvrir"),
                })

# --------------------------------------------------------------------------
# Détail
# --------------------------------------------------------------------------
with onglets[3]:
    portee = st.radio("Portée", ["Séances passées", "Séances à venir"],
                      horizontal=True)
    if portee == "Séances à venir":
        table = futurs[["Date", "Jours restants", "Pays", "Instrument",
                        "État attendu", "Enveloppe (Mds FCFA)", "Titre",
                        "Lien"]]
    else:
        colonnes = ["Date", "Pays", "Instrument", "Titre", "Rapprochement",
                    "Montant annoncé (Mds FCFA)", "Montant retenu (Mds FCFA)",
                    "Taux de couverture", "Rendement moyen pondéré",
                    "Maturité moyenne (années)", "Dernière modification",
                    "Lien"]
        detaille = _filtrer(_rapproches())
        detaille = detaille[detaille["Année"].between(debut, fin)]
        table = detaille[[c for c in colonnes if c in detaille.columns]]

    table = table.sort_values("Date", ascending=(portee == "Séances à venir"))
    st.dataframe(
        table, hide_index=True, width="stretch", height=520,
        column_config={
            "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Dernière modification": st.column_config.DatetimeColumn(
                "Dernière modification de la fiche", format="DD/MM/YYYY HH:mm"),
            "Jours restants": st.column_config.NumberColumn(format="%d j"),
            "Enveloppe (Mds FCFA)": st.column_config.NumberColumn(format="%.1f"),
            "Montant annoncé (Mds FCFA)": st.column_config.NumberColumn(format="%.1f"),
            "Montant retenu (Mds FCFA)": st.column_config.NumberColumn(format="%.1f"),
            "Taux de couverture": st.column_config.NumberColumn(format="%.2f"),
            "Rendement moyen pondéré": st.column_config.NumberColumn(format="percent"),
            "Maturité moyenne (années)": st.column_config.NumberColumn(format="%.2f"),
            "Lien": st.column_config.LinkColumn("Fiche", display_text="Ouvrir"),
        })
    st.download_button(
        "Exporter (CSV)", table.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"calendrier_{portee.split()[-1]}_{aujourdhui:%Y%m%d}.csv",
        mime="text/csv")
