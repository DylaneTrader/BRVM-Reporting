# -*- coding: utf-8 -*-
"""Référentiel des titres — univers complet, répartition coté / non coté, liste.

Page centrale de l'app : c'est ici qu'on voit l'univers obligataire dans son
ensemble, et c'est d'ici que partira le drill vers la fiche titre.
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.lib import chargement, courbes, referentiel  # noqa: E402

st.set_page_config(page_title="Référentiel des titres", page_icon="📒",
                   layout="wide")

COULEURS_COTATION = {"Coté BRVM": "#1f6f8b", "Non coté": "#c98a2e"}


@st.cache_data(show_spinner="Construction du référentiel…")
def _referentiel(niveau: str, reglages: dict) -> pd.DataFrame:
    # `reglages` entre dans la clé de cache : changer la courbe sur la page
    # Courbes doit reconstruire le référentiel, pas resservir l'ancien.
    return referentiel.construire_referentiel(
        params=courbes.ParametresCourbe.depuis_etat(reglages), niveau_courbe=niveau)


def _carte(colonne, libelle: str, valeur: str, aide: str | None = None) -> None:
    colonne.metric(libelle, valeur, help=aide)


def _pourcent(valeur: float, decimales: int = 1) -> str:
    return "—" if pd.isna(valeur) else f"{valeur * 100:.{decimales}f} %"


def _milliards(valeur: float) -> str:
    return "—" if pd.isna(valeur) else f"{valeur:,.0f} Mds".replace(",", " ")


def _libelle_titre(donnees: pd.DataFrame, identifiant: str) -> str:
    """Libellé lisible pour le sélecteur de drill vers la fiche."""
    ligne = donnees[donnees["Identifiant"] == identifiant].iloc[0]
    if pd.notna(ligne["Libellé BRVM"]):
        return f"{identifiant} — {ligne['Libellé BRVM']}"
    coupon = "—" if pd.isna(ligne["Coupon"]) else f"{ligne['Coupon'] * 100:.2f} %"
    echeance = "—" if pd.isna(ligne["Échéance"]) else f"{ligne['Échéance']:%d/%m/%Y}"
    return f"{identifiant} — {ligne['Pays']} {coupon} éch. {echeance}"


st.title("Référentiel des titres")
reference = chargement.date_reference()
st.caption(f"Univers obligataire consolidé au {reference:%d/%m/%Y} — "
           "adjudications UMOA-Titres, marché secondaire et cotations BRVM "
           "réunis au grain du titre.")

# --------------------------------------------------------------------------
# Filtres
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Périmètre")
    niveau = st.selectbox(
        "Courbe de référence", list(courbes.LIBELLES_NIVEAUX),
        index=list(courbes.LIBELLES_NIVEAUX).index(courbes.NIVEAU_OFFICIELLE),
        format_func=lambda n: courbes.LIBELLES_NIVEAUX[n],
        help="Sert au calcul de l'écart entre le dernier rendement observé et "
             "la courbe du pays. La courbe officielle UMOA-Titres est la "
             "référence de place ; la courbe reconstruite est une reconstruction "
             "interne (réglages à venir sur la page Courbes).")

titres = _referentiel(niveau, courbes.parametres_actifs().en_dict())

with st.sidebar:
    statut = st.radio("Statut", ["Vivants", "Tous", "Échus"], horizontal=True)
    segments = st.multiselect("Segment", sorted(titres["Segment"].dropna().unique()),
                              default=sorted(titres["Segment"].dropna().unique()))
    pays = st.multiselect("Pays / émetteur", sorted(titres["Pays"].dropna().unique()),
                          default=sorted(titres["Pays"].dropna().unique()))
    instruments = st.multiselect(
        "Instrument", sorted(titres["Instrument"].dropna().unique()),
        default=sorted(titres["Instrument"].dropna().unique()))
    cotation = st.radio("Cotation", ["Tous", "Coté BRVM", "Non coté"], horizontal=True)
    recherche = st.text_input("Recherche (ISIN, code ou libellé)").strip()

filtre = titres["Segment"].isin(segments) & titres["Pays"].isin(pays) \
    & titres["Instrument"].isin(instruments)
if statut == "Vivants":
    filtre &= titres["Statut"] == "Vivant"
elif statut == "Échus":
    filtre &= titres["Statut"] == "Échu"
if cotation == "Coté BRVM":
    filtre &= titres["Coté"]
elif cotation == "Non coté":
    filtre &= ~titres["Coté"]
if recherche:
    cible = (titres["Identifiant"].fillna("") + " " + titres["ISIN"].fillna("")
             + " " + titres["Code BRVM"].fillna("") + " "
             + titres["Libellé BRVM"].fillna(""))
    filtre &= cible.str.contains(recherche, case=False, regex=False)

perimetre = titres[filtre]
if perimetre.empty:
    st.info("Aucun titre ne correspond à ce périmètre.")
    st.stop()

# --------------------------------------------------------------------------
# Cartes de synthèse
# --------------------------------------------------------------------------
# `resume` raisonne toujours sur les titres vivants : sur un périmètre « Échus »
# les cartes seraient vides, on les calcule alors sur le périmètre affiché.
base_resume = perimetre if statut != "Échus" else perimetre.assign(Statut="Vivant")
synthese = referentiel.resume(base_resume)

cartes = st.columns(6)
_carte(cartes[0], "Titres", f"{synthese['Titres vivants']:,}".replace(",", " "),
       "Titres du périmètre sélectionné.")
_carte(cartes[1], "Encours", _milliards(synthese["Encours total (Mds FCFA)"]),
       f"Somme sur les {synthese['Titres à encours connu']} titres à encours "
       f"documenté ({_pourcent(synthese['Couverture encours'])} du périmètre).")
_carte(cartes[2], "Part cotée (nombre)", _pourcent(synthese["Part cotée en nombre"]),
       "Lignes inscrites à la cote BRVM, en nombre de titres.")
_carte(cartes[3], "Coupon moyen", _pourcent(synthese["Coupon moyen"], 2),
       "Pondéré par l'encours.")
_carte(cartes[4], "Maturité résiduelle",
       "—" if pd.isna(synthese["Maturité résiduelle moyenne"])
       else f"{synthese['Maturité résiduelle moyenne']:.1f} ans",
       "Pondérée par l'encours.")
_carte(cartes[5], "Duration modifiée",
       "—" if pd.isna(synthese["Duration modifiée moyenne"])
       else f"{synthese['Duration modifiée moyenne']:.2f}",
       "Pondérée par l'encours, sur les titres ayant négocié.")

# --------------------------------------------------------------------------
# Coté / non coté
# --------------------------------------------------------------------------
st.subheader("Répartition coté / non coté")

vue = base_resume[base_resume["Statut"] == "Vivant"].copy()
vue["Cotation"] = np.where(vue["Coté"], "Coté BRVM", "Non coté")
par_cotation = referentiel.repartition(vue, "Cotation")

gauche, droite = st.columns([1, 1])
with gauche:
    donut = alt.Chart(par_cotation).mark_arc(innerRadius=60).encode(
        theta=alt.Theta("Titres:Q", stack=True),
        color=alt.Color("Cotation:N", title=None,
                        scale=alt.Scale(domain=list(COULEURS_COTATION),
                                        range=list(COULEURS_COTATION.values()))),
        tooltip=["Cotation", "Titres", "Titres sans encours"],
    ).properties(height=260, title="En nombre de titres")
    st.altair_chart(donut, width="stretch")

with droite:
    barres = alt.Chart(par_cotation.dropna(subset=["Encours (Mds FCFA)"])).mark_bar().encode(
        x=alt.X("Encours (Mds FCFA):Q", title="Encours (Mds FCFA)"),
        y=alt.Y("Cotation:N", title=None, sort="-x"),
        color=alt.Color("Cotation:N", legend=None,
                        scale=alt.Scale(domain=list(COULEURS_COTATION),
                                        range=list(COULEURS_COTATION.values()))),
        tooltip=["Cotation", "Encours (Mds FCFA)", "Titres sans encours"],
    ).properties(height=260, title="En encours documenté")
    st.altair_chart(barres, width="stretch")

st.dataframe(par_cotation, hide_index=True, width="stretch",
             column_config={
                 "Encours (Mds FCFA)": st.column_config.NumberColumn(format="%.0f"),
                 "Part encours": st.column_config.NumberColumn(format="percent"),
             })

cotes_sans_encours = int(vue[vue["Coté"]]["Encours connu"].eq(False).sum())
if cotes_sans_encours:
    st.warning(
        f"**La part cotée en encours n'est pas exploitable telle quelle.** "
        f"{cotes_sans_encours} des {int(vue['Coté'].sum())} lignes cotées n'ont "
        "pas d'encours documenté : le bulletin BRVM ne publie pas le montant en "
        "circulation, et ces titres — massivement issus d'appels publics à "
        "l'épargne et de syndications — n'apparaissent pas dans les "
        "adjudications UMOA-Titres. La répartition en **nombre** est fiable, "
        "celle en **encours** ne l'est que sur le périmètre documenté.")

# --------------------------------------------------------------------------
# Ventilations
# --------------------------------------------------------------------------
st.subheader("Ventilations")
onglet_pays, onglet_maturite, onglet_instrument = st.tabs(
    ["Par pays", "Par classe de maturité", "Par instrument"])


def _graphique_repartition(donnees: pd.DataFrame, cle: str, trier: bool) -> None:
    utilisables = donnees.dropna(subset=["Encours (Mds FCFA)"])
    if utilisables.empty:
        st.info("Aucun encours documenté sur ce périmètre.")
    else:
        graphique = alt.Chart(utilisables).mark_bar(color="#1f6f8b").encode(
            x=alt.X("Encours (Mds FCFA):Q"),
            y=alt.Y(f"{cle}:N", title=None,
                    sort="-x" if trier else list(utilisables[cle])),
            tooltip=[cle, "Titres", "Encours (Mds FCFA)", "Titres sans encours"],
        ).properties(height=max(200, 32 * len(utilisables)))
        st.altair_chart(graphique, width="stretch")
    st.dataframe(donnees, hide_index=True, width="stretch",
                 column_config={
                     "Encours (Mds FCFA)": st.column_config.NumberColumn(format="%.0f"),
                     "Part encours": st.column_config.NumberColumn(format="percent"),
                 })


with onglet_pays:
    _graphique_repartition(referentiel.repartition(vue, "Pays"), "Pays", True)
with onglet_maturite:
    classes = referentiel.classes_de_maturite(vue)
    classes["Classe de maturité"] = classes["Classe de maturité"].astype(str)
    ordre = ["≤ 1 an", "1-2 ans", "2-3 ans", "3-5 ans", "5-7 ans", "7-10 ans",
             "10-15 ans", "> 15 ans"]
    classes["_ordre"] = classes["Classe de maturité"].map(
        {libelle: rang for rang, libelle in enumerate(ordre)})
    _graphique_repartition(classes.sort_values("_ordre").drop(columns="_ordre"),
                           "Classe de maturité", False)
with onglet_instrument:
    _graphique_repartition(referentiel.repartition(vue, "Instrument"),
                           "Instrument", True)

# --------------------------------------------------------------------------
# Liste exhaustive
# --------------------------------------------------------------------------
st.subheader(f"Liste des titres ({len(perimetre):,} lignes)".replace(",", " "))
st.caption("`Source du prix` et `Âge du prix` disent d'où vient la valorisation "
           "et de quand elle date. `Écart YTM / courbe` compare le dernier "
           "rendement négocié à la courbe du pays à même maturité : un écart "
           "important signale une transaction à examiner, pas une erreur.")

COLONNES_LISTE = [
    "Identifiant", "ISIN", "Code BRVM", "Libellé BRVM", "Segment", "Pays",
    "Instrument", "Coté", "Statut", "Coupon", "Date d'émission", "Échéance",
    "Maturité résiduelle (années)", "Amortissement", "Encours (Mds FCFA)",
    "Encours estimé", "Nb tranches", "Taux d'adjudication moyen",
    "Nb séances négociées", "Volume échangé (Mds FCFA)", "Prix de référence",
    "Source du prix", "Date du prix", "Âge du prix (jours)", "Dernier YTM",
    "Taux courbe (maturité)", "Écart YTM / courbe (pb)", "Duration modifiée",
    "Convexité", "Origine",
]

liste = perimetre[COLONNES_LISTE].sort_values(
    ["Pays", "Échéance"], na_position="last")

st.dataframe(
    liste, hide_index=True, width="stretch", height=520,
    column_config={
        "Coupon": st.column_config.NumberColumn(format="percent"),
        "Taux d'adjudication moyen": st.column_config.NumberColumn(format="percent"),
        "Dernier YTM": st.column_config.NumberColumn(format="percent"),
        "Taux courbe (maturité)": st.column_config.NumberColumn(format="percent"),
        "Date d'émission": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Échéance": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Date du prix": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Maturité résiduelle (années)": st.column_config.NumberColumn(format="%.2f"),
        "Encours (Mds FCFA)": st.column_config.NumberColumn(format="%.1f"),
        "Volume échangé (Mds FCFA)": st.column_config.NumberColumn(format="%.1f"),
        "Prix de référence": st.column_config.NumberColumn(format="%.4f"),
        "Écart YTM / courbe (pb)": st.column_config.NumberColumn(format="%.0f"),
        "Duration modifiée": st.column_config.NumberColumn(format="%.2f"),
        "Convexité": st.column_config.NumberColumn(format="%.1f"),
    })

ouvrir, exporter = st.columns([2, 1])
with ouvrir:
    cible = st.selectbox(
        "Ouvrir la fiche d'un titre", perimetre["Identifiant"].tolist(),
        format_func=lambda i: _libelle_titre(perimetre, i),
        label_visibility="collapsed", placeholder="Ouvrir la fiche d'un titre")
    if st.button("Ouvrir la fiche", type="primary"):
        st.query_params["titre"] = cible
        st.switch_page("pages/2_Fiche_titre.py")
with exporter:
    st.download_button(
        "Exporter ce périmètre (CSV)",
        liste.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"referentiel_titres_{reference:%Y%m%d}.csv", mime="text/csv")

with st.expander("Comment cette table est construite"):
    st.markdown("""
Le référentiel réunit trois sources au grain du titre :

| Jointure | Clé | Couverture |
|---|---|---|
| Primaire ↔ secondaire | `ISIN` | 1 291 ISIN communs, 96,5 % du volume secondaire |
| BRVM ↔ primaire/secondaire | libellé (émetteur + taux facial + millésime) | 11 rapprochements exacts sur 198 lignes souveraines |
| Titre ↔ courbe | pays + maturité résiduelle + date | 91 % des lignes secondaires |

**Le faible taux de rapprochement BRVM n'est pas un défaut de méthode.** Les
souverains cotés à la BRVM viennent majoritairement d'appels publics à l'épargne
et de syndications — un canal distinct des adjudications couvertes par
UMOA-Titres. « ETAT DU MALI 6,50 % 2024-2034 » n'a aucune contrepartie possible :
aucun titre malien d'adjudication n'arrive à échéance en 2034. Les deux univers
se recoupent à la marge, ce qui justifie précisément de les traiter comme deux
compartiments plutôt que comme un univers unique.

**Encours.** Observé au marché secondaire quand le titre a négocié, sinon
approché par le cumul des montants levés en adjudication (colonne
`Encours estimé`), sinon laissé vide. Les montants retenus négatifs de la source
primaire (14,2 % des lignes) sont neutralisés dans les agrégats.

**Prix de référence.** Par ordre de préférence : cotation BRVM du jour, dernier
prix du marché secondaire, dernière adjudication. `Âge du prix` accompagne
toujours la valeur.
""")
