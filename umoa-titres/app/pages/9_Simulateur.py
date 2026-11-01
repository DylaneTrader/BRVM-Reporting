# -*- coding: utf-8 -*-
"""Simulateur obligataire — soumissionner, conserver ou vendre.

Deux décisions, un seul moteur de valorisation :

  * **soumission** — à quel taux se porter sur une adjudication, sachant où se
    situe la courbe du pays, où l'émetteur a servi ces derniers mois et où se
    traitent les souches voisines au secondaire ;
  * **position détenue** — ce que la ligne a rapporté depuis l'achat, ce qu'elle
    rapporte encore, et à partir de quel taux de replacement la vendre devient
    la meilleure branche.

Toutes les grandeurs affichées sont des scénarios explicites, jamais des
prévisions : les points d'indifférence (choc de taux qui annule le gain, taux de
replacement qui égalise vendre et conserver) sont là pour situer une décision,
pas pour la prendre.
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.lib import (calendrier, chargement, courbes, referentiel,  # noqa: E402
                     simulateur)

st.set_page_config(page_title="Simulateur obligataire", page_icon="🧮",
                   layout="wide")

MODE_SOUMISSION = "Soumissionner à une émission"
MODE_DETENU = "Arbitrer un titre détenu"

VERT, BLEU, GRIS, ROUGE = "#2e7d5b", "#1f6f8b", "#9aa0a6", "#b23a3a"


@st.cache_data(show_spinner="Construction du référentiel…")
def _referentiel(reglages: dict) -> pd.DataFrame:
    return referentiel.construire_referentiel(
        params=courbes.ParametresCourbe.depuis_etat(reglages))


@st.cache_data(show_spinner=False)
def _agenda() -> pd.DataFrame:
    return calendrier.agenda()


def _pourcent(valeur, decimales: int = 2) -> str:
    return "—" if pd.isna(valeur) else f"{valeur * 100:.{decimales}f} %"


def _pb(valeur, decimales: int = 0) -> str:
    return "—" if pd.isna(valeur) else f"{valeur:+,.{decimales}f} pb".replace(",", " ")


def _fcfa(valeur, decimales: int = 0) -> str:
    return ("—" if pd.isna(valeur)
            else f"{valeur:,.{decimales}f} F".replace(",", " "))


def _annees(valeur, decimales: int = 2) -> str:
    return "—" if pd.isna(valeur) else f"{valeur:.{decimales}f} ans"


reglages_courbe = courbes.parametres_actifs().en_dict()
reference = chargement.date_reference()

st.title("Simulateur obligataire")
st.caption("Valorisation, sensibilité et analyse d'horizon d'une souche, "
           "adossées aux trois sources : courbe souveraine du pays, "
           "adjudications comparables et cotations du secondaire.")

# --------------------------------------------------------------------------
# Définition du titre
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Décision")
    mode = st.radio("Objet de l'analyse", [MODE_SOUMISSION, MODE_DETENU],
                    help="La soumission raisonne sur un titre à acquérir ; "
                         "l'arbitrage sur une ligne déjà en portefeuille.")

    st.header("Titre")
    sources = (["Émission à venir", "Titre du référentiel", "Saisie libre"]
               if mode == MODE_SOUMISSION
               else ["Titre du référentiel", "Saisie libre"])
    source = st.selectbox("Point de départ", sources)

    titres = _referentiel(reglages_courbe)
    pays_possibles = chargement.PAYS_UEMOA
    prefill = {"pays": "Côte d'Ivoire", "coupon": 6.0, "maturite": 5.0,
               "amortissement": simulateur.AMORTISSEMENT_IN_FINE, "differe": 0,
               "reglement": reference, "taux": None, "libelle": None,
               "isin": None, "echeance": None}

    if source == "Émission à venir":
        futurs = _agenda()
        if futurs.empty:
            st.warning("Aucune émission annoncée : bascule en saisie libre.")
        else:
            libelles = {}
            for position_ligne, ligne in futurs.iterrows():
                enveloppe = ligne["Enveloppe (Mds FCFA)"]
                montant_annonce = ("enveloppe inconnue" if pd.isna(enveloppe)
                                   else f"{enveloppe:.0f} Mds")
                libelles[f"{ligne['Date']:%d/%m/%Y} — {ligne['Pays']} "
                         f"({montant_annonce})"] = position_ligne
            choix = st.selectbox("Séance", list(libelles))
            ligne = futurs.loc[libelles[choix]]
            reglement = (ligne["Date de valeur"]
                         if not pd.isna(ligne.get("Date de valeur"))
                         else ligne["Date"] + pd.Timedelta(days=1))
            prefill.update(pays=ligne["Pays"] or prefill["pays"],
                           reglement=pd.Timestamp(reglement))
            st.caption("La séance fixe le pays et la date de règlement ; la "
                       "maturité et le taux facial restent à saisir, l'avis "
                       "d'adjudication ne les publie qu'à l'ouverture.")

    elif source == "Titre du référentiel":
        univers = titres[(titres["Statut"] == "Vivant")
                         & titres["Échéance"].notna()
                         & titres["Coupon"].notna()].copy()
        if univers.empty:
            st.warning("Aucun titre vivant exploitable : bascule en saisie libre.")
        else:
            # Souverains UMOA d'abord — seuls titres dont la courbe de
            # référence est celle de leur propre émetteur — puis les souches
            # négociées le plus récemment : celles dont le prix de marché est
            # le moins périmé, donc les plus exploitables telles quelles.
            univers["_ordre"] = np.where(
                univers["Pays"].isin(pays_possibles), 0, 1)
            univers = univers.sort_values(
                ["_ordre", "Dernière négociation", "Échéance"],
                ascending=[True, False, True], na_position="last")
            etiquettes = {
                f"{ligne['Identifiant']} — {ligne['Pays']} "
                f"{ligne['Coupon'] * 100:.2f} % {ligne['Échéance']:%m/%Y}": ligne
                for _, ligne in univers.iterrows()}
            defaut = st.query_params.get("titre")
            noms = list(etiquettes)
            index = next((i for i, nom in enumerate(noms)
                          if defaut and nom.startswith(str(defaut))), 0)
            ligne = etiquettes[st.selectbox("Souche", noms, index=index)]
            prefill.update(
                pays=ligne["Pays"] if ligne["Pays"] in pays_possibles else prefill["pays"],
                coupon=float(ligne["Coupon"]) * 100,
                echeance=pd.Timestamp(ligne["Échéance"]),
                amortissement=simulateur.normaliser_amortissement(ligne["Amortissement"]),
                taux=(None if pd.isna(ligne["Dernier YTM"])
                      else float(ligne["Dernier YTM"])),
                libelle=ligne["Identifiant"], isin=ligne["ISIN"])
            if not pd.isna(ligne["Date du prix"]):
                st.caption(f"Dernier prix connu : {ligne['Source du prix'].lower()} "
                           f"du {ligne['Date du prix']:%d/%m/%Y} "
                           f"({ligne['Âge du prix (jours)']:.0f} jours).")
            if ligne["Pays"] not in pays_possibles:
                st.warning("Émetteur hors souverains UMOA : la courbe de "
                           "référence sélectionnée ci-dessous n'est qu'un "
                           "proxy, l'écart affiché en tient la trace.")

    pays = st.selectbox("Pays émetteur", pays_possibles,
                        index=pays_possibles.index(prefill["pays"])
                        if prefill["pays"] in pays_possibles else 0)
    coupon = st.number_input("Taux facial (%)", min_value=0.0, max_value=20.0,
                             value=float(prefill["coupon"]), step=0.05,
                             format="%.3f",
                             help="0 pour un BAT : le titre est alors traité "
                                  "en zéro-coupon, flux unique à l'échéance.")
    reglement = pd.Timestamp(st.date_input(
        "Date de règlement", value=prefill["reglement"].date(),
        help="Date de valeur de l'achat. Le référentiel se cale sur la "
             "dernière donnée observée, pas sur l'horloge système."))

    if prefill["echeance"] is not None:
        echeance = pd.Timestamp(st.date_input(
            "Échéance", value=prefill["echeance"].date()))
        maturite_saisie = (echeance - reglement).days / simulateur.BASE_JOURS
    else:
        maturite_saisie = st.number_input(
            "Maturité (années)", min_value=0.08, max_value=30.0,
            value=float(prefill["maturite"]), step=0.25, format="%.2f")
        echeance = reglement + pd.Timedelta(
            days=int(round(maturite_saisie * simulateur.BASE_JOURS)))
        st.caption(f"Échéance déduite : {echeance:%d/%m/%Y}")

    amortissements = list(simulateur.LIBELLES_AMORTISSEMENT)
    amortissement = st.selectbox(
        "Amortissement", amortissements,
        index=amortissements.index(prefill["amortissement"]),
        format_func=simulateur.LIBELLES_AMORTISSEMENT.get)
    differe = 0
    if amortissement != simulateur.AMORTISSEMENT_IN_FINE:
        differe = st.number_input("Différé (années)", min_value=0, max_value=10,
                                  value=int(prefill["differe"]), step=1)

    montant = st.number_input(
        "Montant nominal (FCFA)", min_value=10_000.0, max_value=1e12,
        value=100_000_000.0, step=10_000_000.0, format="%.0f",
        help="Nominal résiduel détenu ou visé. Sert à convertir prix et "
             "sensibilités en francs.")
    niveau = st.selectbox(
        "Courbe de référence", [courbes.NIVEAU_OFFICIELLE, courbes.NIVEAU_CGF,
                                courbes.NIVEAU_BRUT],
        format_func=courbes.LIBELLES_NIVEAUX.get)

# Date de jouissance : celle du référentiel pour une souche existante, la date
# de règlement pour une émission neuve — c'est ce qui date correctement le
# premier coupon et, sur un amortissable, le plan de remboursement.
date_jouissance = None
if prefill["libelle"]:
    emissions = titres.loc[titres["Identifiant"] == prefill["libelle"],
                           "Date d'émission"].dropna()
    if not emissions.empty and pd.Timestamp(emissions.iloc[0]) < echeance:
        date_jouissance = pd.Timestamp(emissions.iloc[0])
else:
    date_jouissance = reglement

titre = simulateur.Titre(
    echeance=echeance, coupon=coupon / 100.0, date_jouissance=date_jouissance,
    amortissement=amortissement, differe_annees=int(differe), pays=pays,
    libelle=prefill["libelle"], isin=prefill["isin"])

flux_restants = simulateur.flux_a_venir(titre, reglement)
if flux_restants.empty:
    st.error("Aucun flux ne reste à courir après la date de règlement : "
             "vérifier l'échéance et la date de valeur.")
    st.stop()

maturite = float(flux_restants["Années"].iloc[-1])
# Face à la courbe et aux adjudications, c'est la maturité moyenne pondérée par
# les remboursements qui situe le titre : un amortissable de dix ans dont le
# capital revient dès la quatrième année ne se compare pas à un dix ans bullet.
# Les deux coïncident pour un in fine, où le principal tombe d'un bloc.
amortissements_restants = flux_restants["Amortissement"]
maturite_courbe = (
    float((flux_restants["Années"] * amortissements_restants).sum()
          / amortissements_restants.sum())
    if amortissements_restants.sum() > 0 else maturite)

params_courbe = courbes.ParametresCourbe.depuis_etat(reglages_courbe)
taux_courbe = simulateur.taux_courbe(pays, maturite_courbe, reglement, niveau,
                                     params_courbe)
comparables = simulateur.comparables_primaire(pays, maturite_courbe,
                                              date=reference)
stats_comparables = simulateur.resume_comparables(comparables)
voisins = simulateur.comparables_secondaire(pays, maturite_courbe, titres)

# --------------------------------------------------------------------------
# Taux ou prix de travail
# --------------------------------------------------------------------------
defaut_taux = next(
    (valeur for valeur in (prefill["taux"], stats_comparables.get("Dernier taux servi"),
                           taux_courbe, 0.06)
     if valeur is not None and not pd.isna(valeur)), 0.06)

entree = st.columns([1.1, 1, 1, 1.4])
saisie = entree[0].radio("Saisie", ["Par le taux", "Par le prix"],
                         horizontal=True, label_visibility="collapsed")
if saisie == "Par le taux":
    taux = entree[1].number_input(
        "Taux visé (%)", min_value=0.0, max_value=30.0,
        value=round(defaut_taux * 100, 3), step=0.05, format="%.3f",
        help="Rendement actuariel annuel, base Exact/365 — la convention du "
             "« Rendement moyen » publié par UMOA-Titres.") / 100.0
    valorisation = simulateur.prix_depuis_taux(titre, taux, reglement)
    entree[2].metric("Prix pied de coupon",
                     _pourcent(valorisation["Prix pied de coupon"], 3))
else:
    prix_saisi = entree[1].number_input(
        "Prix pied de coupon (%)", min_value=1.0, max_value=200.0,
        value=100.0, step=0.05, format="%.3f") / 100.0
    taux = simulateur.taux_depuis_prix(titre, prix_saisi, reglement)
    valorisation = simulateur.prix_depuis_taux(titre, taux, reglement)
    entree[2].metric("Taux actuariel", _pourcent(taux, 3))

if pd.isna(taux):
    st.error("Le rendement n'a pas pu être résolu pour ce prix : vérifier les "
             "caractéristiques du titre.")
    st.stop()

analytiques = simulateur.metriques(titre, taux, reglement)
entree[3].caption(
    f"Règlement {reglement:%d/%m/%Y} · échéance {echeance:%d/%m/%Y} · "
    f"{_annees(maturite)} · nominal résiduel "
    f"{valorisation['Encours résiduel'] * 100:.1f} % du nominal d'origine")

# --------------------------------------------------------------------------
# Synthèse chiffrée
# --------------------------------------------------------------------------
prix_unitaire = valorisation["Prix total"] * simulateur.NOMINAL_UNITAIRE
decaissement = valorisation["Prix total"] * montant
ecart_courbe = ((taux - taux_courbe) * 10_000 if not pd.isna(taux_courbe)
                else np.nan)
horizon_12m = min(reglement + pd.DateOffset(months=12), titre.echeance)
coussin = simulateur.choc_indifference(
    titre, reglement, taux, horizon_12m, taux, montant)

cartes = st.columns(6)
cartes[0].metric("Prix total", _pourcent(valorisation["Prix total"], 3),
                 help=f"Soit {_fcfa(prix_unitaire, 0)} par 10 000 de nominal, "
                      f"{_fcfa(decaissement, 0)} pour le montant saisi. "
                      f"Coupon couru : {_pourcent(valorisation['Coupon couru'], 3)}.")
cartes[1].metric("Taux actuariel", _pourcent(taux, 3))
cartes[2].metric("Écart / courbe", _pb(ecart_courbe),
                 help=f"Courbe {courbes.LIBELLES_NIVEAUX[niveau].lower()} du "
                      f"{pays} à {_annees(maturite_courbe)} : "
                      f"{_pourcent(taux_courbe, 3)}. Positif = le titre "
                      "rapporte plus que la courbe.")
cartes[3].metric("Duration modifiée",
                 _annees(analytiques["Duration modifiée"]),
                 help=f"Convexité {analytiques['Convexité']:.1f}. "
                      "Une hausse de 100 pb coûte environ "
                      f"{analytiques['Duration modifiée']:.2f} % de la valeur, "
                      "atténuée par la convexité.")
cartes[4].metric("DV01", _fcfa(analytiques["Duration modifiée"]
                               * valorisation["Prix total"] * montant * 1e-4, 0),
                 help="Perte de valeur pour 1 pb de hausse des taux, sur le "
                      "montant saisi.")
cartes[5].metric("Coussin 12 mois", _pb(coussin),
                 help="Hausse de taux que la position peut absorber sur douze "
                      "mois avant que le rendement total ne devienne négatif "
                      "(coupons réinvestis au taux courant). Sans objet — donc "
                      "affiché « — » — quand le titre arrive à échéance avant "
                      "l'horizon : il n'y a alors plus de prix de revente à "
                      "exposer au risque de taux.")

onglets_mode = ("Comparables de marché" if mode == MODE_SOUMISSION
                else "Conserver ou vendre")
onglets = st.tabs(["Lecture", "Échéancier et sensibilité", onglets_mode,
                   "Horizon et scénarios", "Conventions"])

# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------
with onglets[0]:
    reperes = [
        {"Repère": f"Courbe {courbes.LIBELLES_NIVEAUX[niveau].lower()}",
         "Taux": taux_courbe,
         "Base": (f"{pays}, {_annees(maturite_courbe)}, "
                  f"courbe du {reglement:%d/%m/%Y}")},
        {"Repère": "Adjudications comparables (médiane)",
         "Taux": stats_comparables.get("Taux médian", np.nan),
         "Base": (f"{stats_comparables.get('Adjudications', 0)} adjudications "
                  f"{pays} à ±1 an de {_annees(maturite_courbe)}, "
                  "12 derniers mois")},
        {"Repère": "Dernier taux servi",
         "Taux": stats_comparables.get("Dernier taux servi", np.nan),
         "Base": (f"adjudication du "
                  f"{stats_comparables['Dernière']:%d/%m/%Y}"
                  if stats_comparables.get("Dernière") is not None else "—")},
        {"Repère": "Secondaire, souches voisines (médiane)",
         "Taux": (float(voisins["Dernier YTM"].median()) if not voisins.empty
                  else np.nan),
         "Base": (f"{len(voisins)} souches vivantes {pays} à ±1 an de "
                  f"{_annees(maturite_courbe)}, dernier YTM négocié"
                  if not voisins.empty else "aucune souche voisine négociée")},
        {"Repère": "Taux retenu dans la simulation", "Taux": taux,
         "Base": "saisie de l'utilisateur"},
    ]
    table_reperes = pd.DataFrame(reperes)
    table_reperes["Écart au taux retenu (pb)"] = (
        (taux - table_reperes["Taux"]) * 10_000)
    table_reperes.loc[table_reperes["Repère"].str.startswith("Taux retenu"),
                      "Écart au taux retenu (pb)"] = np.nan

    st.markdown("#### Où se situe le taux retenu")
    st.dataframe(
        table_reperes, hide_index=True, width="stretch",
        column_config={
            "Taux": st.column_config.NumberColumn(format="percent"),
            "Écart au taux retenu (pb)": st.column_config.NumberColumn(format="%.0f"),
        })
    st.caption("Un écart positif signifie que la simulation retient un taux "
               "plus élevé que le repère : plus rémunérateur à l'achat, plus "
               "coûteux pour l'émetteur. La courbe est une estimation lissée, "
               "l'adjudication est un prix effectivement servi — quand les deux "
               "divergent sur le court terme, c'est l'adjudication qui a "
               "tranché.")

    # --- Positionnement sur la courbe -------------------------------------
    courbe = courbes.construire_courbe(pays, reglement, niveau, params_courbe)
    if courbe.empty:
        st.info(f"Aucune courbe publiée pour le {pays} à cette date.")
    else:
        trace = alt.Chart(courbe).mark_line(color=BLEU).encode(
            x=alt.X("Maturité:Q", title="Maturité (années)"),
            y=alt.Y("Taux:Q", title="Taux", axis=alt.Axis(format="%"),
                    scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("Maturité:Q", format=".2f"),
                     alt.Tooltip("Taux:Q", format=".3%"), "Origine"])
        couches = [trace]
        if not comparables.empty:
            adjudications = comparables.rename(columns={
                "Maturité (années)": "Maturité",
                "Rendement moyen pondéré (déc.)": "Taux"})
            couches.append(
                alt.Chart(adjudications).mark_point(
                    color=GRIS, opacity=0.65, size=45).encode(
                    x="Maturité:Q", y="Taux:Q",
                    tooltip=[alt.Tooltip("Date de l'opération:T", format="%d/%m/%Y"),
                             "Instrument", alt.Tooltip("Taux:Q", format=".3%"),
                             alt.Tooltip("Maturité:Q", format=".2f")]))
        if not voisins.empty:
            secondaire = voisins.rename(columns={
                "Maturité résiduelle (années)": "Maturité",
                "Dernier YTM": "Taux"})
            couches.append(
                alt.Chart(secondaire).mark_point(
                    color=VERT, opacity=0.8, size=60, shape="triangle").encode(
                    x="Maturité:Q", y="Taux:Q",
                    tooltip=["Identifiant", alt.Tooltip("Taux:Q", format=".3%"),
                             alt.Tooltip("Maturité:Q", format=".2f"),
                             alt.Tooltip("Dernière négociation:T", format="%d/%m/%Y")]))
        point = pd.DataFrame([{"Maturité": maturite_courbe, "Taux": taux,
                               "Titre": titre.libelle or "Simulation"}])
        couches.append(
            alt.Chart(point).mark_point(
                color=ROUGE, size=220, shape="diamond", filled=True).encode(
                x="Maturité:Q", y="Taux:Q",
                tooltip=["Titre", alt.Tooltip("Taux:Q", format=".3%"),
                         alt.Tooltip("Maturité:Q", format=".2f")]))
        st.altair_chart(
            alt.layer(*couches).properties(
                height=380,
                title=f"Courbe {pays}, adjudications (gris), souches "
                      f"secondaires (vert) et titre simulé (rouge)"),
            width="stretch")

    gauche, droite = st.columns(2)
    with gauche:
        st.markdown("#### Ce que coûte la position")
        st.dataframe(pd.DataFrame([
            {"Grandeur": "Prix pied de coupon", "Valeur":
                _pourcent(valorisation["Prix pied de coupon"], 3)},
            {"Grandeur": "Coupon couru", "Valeur":
                _pourcent(valorisation["Coupon couru"], 3)},
            {"Grandeur": "Prix total (par 10 000)", "Valeur":
                _fcfa(prix_unitaire, 0)},
            {"Grandeur": "Décaissement pour le montant saisi", "Valeur":
                _fcfa(decaissement, 0)},
            {"Grandeur": "Nominal résiduel", "Valeur":
                _pourcent(valorisation["Encours résiduel"], 1)},
        ]), hide_index=True, width="stretch")
    with droite:
        st.markdown("#### Ce que la position risque")
        st.dataframe(pd.DataFrame([
            {"Grandeur": "Duration Macaulay", "Valeur":
                _annees(analytiques["Duration Macaulay"])},
            {"Grandeur": "Duration modifiée", "Valeur":
                _annees(analytiques["Duration modifiée"])},
            {"Grandeur": "Convexité", "Valeur":
                f"{analytiques['Convexité']:.2f}"},
            {"Grandeur": "Maturité moyenne pondérée", "Valeur":
                _annees(analytiques["Maturité moyenne pondérée (années)"])},
            {"Grandeur": "DV01 (montant saisi)", "Valeur":
                _fcfa(analytiques["Duration modifiée"]
                      * valorisation["Prix total"] * montant * 1e-4, 0)},
        ]), hide_index=True, width="stretch")
        if titre.amortissement != simulateur.AMORTISSEMENT_IN_FINE:
            st.caption(
                f"Titre amortissable : les repères de marché sont pris à "
                f"{_annees(maturite_courbe)}, la maturité moyenne pondérée par "
                f"les remboursements, et non à l'échéance finale "
                f"({_annees(maturite)}) — le capital revient plus tôt, le "
                "risque porté est plus court.")

# --------------------------------------------------------------------------
# Échéancier et sensibilité
# --------------------------------------------------------------------------
with onglets[1]:
    echeancier = flux_restants.copy()
    facteur = montant / valorisation["Encours résiduel"]
    for colonne in ("Intérêt", "Amortissement", "Flux"):
        echeancier[f"{colonne} (FCFA)"] = echeancier[colonne] * facteur
    echeancier["Actualisé (FCFA)"] = (echeancier["Flux (FCFA)"]
                                      * (1 + taux) ** -echeancier["Années"])
    echeancier["Encours (FCFA)"] = echeancier["Encours début"] * facteur

    total_flux = echeancier["Flux (FCFA)"].sum()
    resume_flux = st.columns(4)
    resume_flux[0].metric("Flux à percevoir", _fcfa(total_flux, 0))
    resume_flux[1].metric("dont intérêts",
                          _fcfa(echeancier["Intérêt (FCFA)"].sum(), 0))
    resume_flux[2].metric("Valeur actuelle",
                          _fcfa(echeancier["Actualisé (FCFA)"].sum(), 0),
                          help="Somme des flux actualisés au taux retenu : "
                               "c'est le prix total, exprimé en francs.")
    resume_flux[3].metric("Multiple sur décaissement",
                          f"{total_flux / decaissement:.2f} ×"
                          if decaissement else "—")

    empilable = echeancier.melt(
        id_vars="Date", value_vars=["Intérêt (FCFA)", "Amortissement (FCFA)"],
        var_name="Nature", value_name="Montant")
    st.altair_chart(
        alt.Chart(empilable).mark_bar().encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("Montant:Q", title="FCFA", stack="zero"),
            color=alt.Color("Nature:N", title=None,
                            scale=alt.Scale(
                                domain=["Intérêt (FCFA)", "Amortissement (FCFA)"],
                                range=[BLEU, VERT])),
            tooltip=[alt.Tooltip("Date:T", format="%d/%m/%Y"), "Nature",
                     alt.Tooltip("Montant:Q", format=",.0f")],
        ).properties(height=260, title="Échéancier des flux"),
        width="stretch")

    st.dataframe(
        echeancier[["Date", "Années", "Encours (FCFA)", "Intérêt (FCFA)",
                    "Amortissement (FCFA)", "Flux (FCFA)", "Actualisé (FCFA)"]],
        hide_index=True, width="stretch", height=280,
        column_config={
            "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Années": st.column_config.NumberColumn(format="%.3f"),
            "Encours (FCFA)": st.column_config.NumberColumn(format="%.0f"),
            "Intérêt (FCFA)": st.column_config.NumberColumn(format="%.0f"),
            "Amortissement (FCFA)": st.column_config.NumberColumn(format="%.0f"),
            "Flux (FCFA)": st.column_config.NumberColumn(format="%.0f"),
            "Actualisé (FCFA)": st.column_config.NumberColumn(format="%.0f"),
        })
    st.download_button(
        "Exporter l'échéancier (CSV)",
        echeancier.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"echeancier_{(titre.isin or pays)}_{reglement:%Y%m%d}.csv",
        mime="text/csv")

    st.markdown("#### Sensibilité au taux")
    grille = simulateur.courbe_prix_taux(titre, reglement, taux)
    grille["Valeur (FCFA)"] = grille["Prix total"] * montant
    base = alt.Chart(grille).encode(x=alt.X("Choc (pb):Q", title="Choc de taux (pb)"))
    st.altair_chart(
        alt.layer(
            base.mark_line(color=BLEU).encode(
                y=alt.Y("Variation:Q", title="Variation de valeur",
                        axis=alt.Axis(format="%")),
                tooltip=[alt.Tooltip("Choc (pb):Q", format=".0f"),
                         alt.Tooltip("Variation:Q", format=".2%"),
                         alt.Tooltip("Valeur (FCFA):Q", format=",.0f")]),
            base.mark_line(color=GRIS, strokeDash=[5, 4]).encode(
                y=alt.Y("Variation (duration):Q")),
        ).properties(height=300,
                     title="Prix réel (bleu) et approximation par la duration "
                           "(gris) — l'écart est la convexité"),
        width="stretch")

    chocs_table = grille[grille["Choc (pb)"].isin([-200, -100, -50, 0, 50, 100, 200])]
    st.dataframe(
        chocs_table[["Choc (pb)", "Taux", "Prix total", "Variation",
                     "Valeur (FCFA)"]],
        hide_index=True, width="stretch",
        column_config={
            "Choc (pb)": st.column_config.NumberColumn(format="%+.0f"),
            "Taux": st.column_config.NumberColumn(format="percent"),
            "Prix total": st.column_config.NumberColumn(format="percent"),
            "Variation": st.column_config.NumberColumn(format="percent"),
            "Valeur (FCFA)": st.column_config.NumberColumn(format="%.0f"),
        })

# --------------------------------------------------------------------------
# Comparables de marché  /  Conserver ou vendre
# --------------------------------------------------------------------------
with onglets[2]:
    if mode == MODE_SOUMISSION:
        st.markdown("#### Ce que l'émetteur a servi récemment")
        if comparables.empty:
            st.info(f"Aucune adjudication {pays} de maturité voisine sur les "
                    "douze derniers mois. La courbe reste le seul repère.")
        else:
            cartes_comp = st.columns(5)
            cartes_comp[0].metric("Adjudications",
                                  stats_comparables["Adjudications"])
            cartes_comp[1].metric("Taux médian servi",
                                  _pourcent(stats_comparables["Taux médian"]))
            cartes_comp[2].metric(
                "Fourchette interquartile",
                f"{stats_comparables['1er quartile'] * 100:.2f} – "
                f"{stats_comparables['3e quartile'] * 100:.2f} %")
            cartes_comp[3].metric(
                "Couverture médiane",
                "—" if pd.isna(stats_comparables["Couverture médiane"])
                else f"{stats_comparables['Couverture médiane']:.2f}",
                help="Montant soumis rapporté au montant annoncé. En dessous "
                     "de 1, l'émetteur n'a pas reçu assez d'offres — une "
                     "soumission agressive y a plus de chances d'être servie.")
            cartes_comp[4].metric(
                "Taux marginal médian",
                _pourcent(stats_comparables["Taux marginal médian"]),
                help="Le marginal est le taux le plus élevé servi : au-delà, "
                     "la soumission n'était pas retenue.")

            st.altair_chart(
                alt.Chart(comparables).mark_circle(opacity=0.7).encode(
                    x=alt.X("Date de l'opération:T", title=None),
                    y=alt.Y("Rendement moyen pondéré (déc.):Q",
                            title="Taux servi", axis=alt.Axis(format="%"),
                            scale=alt.Scale(zero=False)),
                    size=alt.Size("Montant retenu (Mds FCFA):Q", title="Mds"),
                    color=alt.Color("Instrument:N", title=None),
                    tooltip=["Instrument", "ISIN",
                             alt.Tooltip("Date de l'opération:T", format="%d/%m/%Y"),
                             alt.Tooltip("Rendement moyen pondéré (déc.):Q", format=".3%"),
                             alt.Tooltip("Taux marginal (déc.):Q", format=".3%"),
                             alt.Tooltip("Maturité (années):Q", format=".2f"),
                             alt.Tooltip("Taux de couverture:Q", format=".2f")],
                ).properties(height=300,
                             title=f"Adjudications {pays} à ±1 an de "
                                   f"{_annees(maturite_courbe)}, "
                                   "12 derniers mois"),
                width="stretch")

            st.markdown("#### Prix à soumettre selon le taux visé")
            niveaux = {
                "1er quartile des adjudications": stats_comparables["1er quartile"],
                "Médiane des adjudications": stats_comparables["Taux médian"],
                "3e quartile des adjudications": stats_comparables["3e quartile"],
                "Dernier taux servi": stats_comparables["Dernier taux servi"],
                "Taux marginal médian": stats_comparables["Taux marginal médian"],
                "Courbe du pays": taux_courbe,
                "Taux retenu": taux,
            }
            lignes_prix = []
            for libelle, valeur in niveaux.items():
                if valeur is None or pd.isna(valeur):
                    continue
                prix = simulateur.prix_depuis_taux(titre, valeur, reglement)
                lignes_prix.append({
                    "Niveau": libelle, "Taux": valeur,
                    "Prix pied de coupon": prix["Prix pied de coupon"],
                    "Prix total (par 10 000)": (prix["Prix total"]
                                                * simulateur.NOMINAL_UNITAIRE),
                    "Décaissement (montant saisi)": prix["Prix total"] * montant,
                    "Écart au taux retenu (pb)": (taux - valeur) * 10_000,
                })
            st.dataframe(
                pd.DataFrame(lignes_prix), hide_index=True, width="stretch",
                column_config={
                    "Taux": st.column_config.NumberColumn(format="percent"),
                    "Prix pied de coupon": st.column_config.NumberColumn(format="percent"),
                    "Prix total (par 10 000)": st.column_config.NumberColumn(format="%.0f"),
                    "Décaissement (montant saisi)": st.column_config.NumberColumn(format="%.0f"),
                    "Écart au taux retenu (pb)": st.column_config.NumberColumn(format="%+.0f"),
                })
            st.caption("Soumissionner **plus haut en taux**, c'est proposer un "
                       "prix plus bas : plus de rendement si l'on est servi, "
                       "moins de chances de l'être. La distribution des taux "
                       "servis et le taux de couverture disent où se situe "
                       "cette frontière ces derniers mois.")

            with st.expander("Détail des adjudications comparables"):
                st.dataframe(
                    comparables, hide_index=True, width="stretch", height=320,
                    column_config={
                        "Date de l'opération": st.column_config.DateColumn(format="DD/MM/YYYY"),
                        "Maturité (années)": st.column_config.NumberColumn(format="%.2f"),
                        "Rendement moyen pondéré (déc.)": st.column_config.NumberColumn(
                            "Taux servi", format="percent"),
                        "Taux marginal (déc.)": st.column_config.NumberColumn(
                            "Taux marginal", format="percent"),
                        "Taux de couverture": st.column_config.NumberColumn(format="%.2f"),
                        "Montant retenu (Mds FCFA)": st.column_config.NumberColumn(format="%.2f"),
                    })

        if not voisins.empty:
            st.markdown("#### Souches voisines au secondaire")
            st.dataframe(
                voisins, hide_index=True, width="stretch",
                column_config={
                    "Échéance": st.column_config.DateColumn(format="DD/MM/YYYY"),
                    "Dernière négociation": st.column_config.DateColumn(format="DD/MM/YYYY"),
                    "Coupon": st.column_config.NumberColumn(format="percent"),
                    "Dernier YTM": st.column_config.NumberColumn(format="percent"),
                    "Maturité résiduelle (années)": st.column_config.NumberColumn(format="%.2f"),
                    "Écart YTM / courbe (pb)": st.column_config.NumberColumn(format="%+.0f"),
                    "Encours (Mds FCFA)": st.column_config.NumberColumn(format="%.1f"),
                })

    else:
        st.markdown("#### La position détenue")
        saisie_position = st.columns(4)
        # Un achat ne peut précéder la jouissance du titre : sans ce plancher,
        # la valorisation actualiserait des flux d'un titre pas encore émis.
        plancher = titre.date_jouissance if titre.jouissance_connue else None
        defaut_achat = min(reglement - pd.DateOffset(years=1), reglement)
        if plancher is not None:
            defaut_achat = min(max(defaut_achat, plancher), reglement)
        date_achat = pd.Timestamp(saisie_position[0].date_input(
            "Date d'achat", value=defaut_achat.date(),
            min_value=None if plancher is None else plancher.date(),
            max_value=reglement.date()))
        mode_achat = saisie_position[1].radio(
            "Prix d'achat", ["Par le prix", "Par le taux"], horizontal=True)
        if mode_achat == "Par le prix":
            prix_achat = saisie_position[2].number_input(
                "Prix payé, pied de coupon (%)", min_value=1.0, max_value=200.0,
                value=100.0, step=0.05, format="%.3f") / 100.0
        else:
            taux_achat_saisi = saisie_position[2].number_input(
                "Taux d'achat (%)", min_value=0.0, max_value=30.0,
                value=round(taux * 100, 3), step=0.05, format="%.3f") / 100.0
            prix_achat = simulateur.prix_depuis_taux(
                titre, taux_achat_saisi, date_achat)["Prix pied de coupon"]
            saisie_position[2].caption(
                f"Prix pied de coupon : {_pourcent(prix_achat, 3)}")
        frais = saisie_position[3].number_input(
            "Frais aller-retour (pb)", min_value=0.0, max_value=200.0,
            value=0.0, step=5.0,
            help="Appliqués pour moitié à l'achat et pour moitié à la vente.") / 10_000.0

        etat = simulateur.position(titre, date_achat, prix_achat, reglement,
                                   taux, montant, frais / 2, frais / 2)
        if not etat:
            st.info("La date d'achat doit précéder la date de règlement et le "
                    "titre doit être encore vivant.")
        else:
            cartes_pos = st.columns(5)
            taux_achat_reconstitue = _pourcent(etat["Taux d'achat"], 3)
            cartes_pos[0].metric("Coût d'acquisition",
                                 _fcfa(etat["Coût d'acquisition"], 0),
                                 help="Taux d'achat reconstitué : "
                                      f"{taux_achat_reconstitue}. Frais inclus.")
            cartes_pos[1].metric("Valeur de marché",
                                 _fcfa(etat["Valeur de marché"], 0),
                                 help="Au taux retenu en haut de page, coupon "
                                      "couru inclus.")
            cartes_pos[2].metric("Résultat total",
                                 _fcfa(etat["Résultat total"], 0),
                                 delta=_pourcent(etat["Résultat total (%)"], 2),
                                 help="Produit de cession net + coupons et "
                                      "amortissements perçus − coût d'acquisition.")
            cartes_pos[3].metric("TRI réalisé", _pourcent(etat["TRI réalisé"], 2),
                                 help="Taux de rendement interne des flux "
                                      "réellement datés depuis l'achat, "
                                      "cession au prix du jour incluse.")
            cartes_pos[4].metric(
                "Taux depuis l'achat",
                _pb(etat["Variation de taux depuis l'achat (pb)"]),
                help="Hausse du rendement = baisse du prix. C'est la source "
                     "principale de la plus ou moins-value de cours.")
            if etat["Durée de détention (années)"] <= 0:
                st.caption("Date d'achat égale à la date de valorisation : le "
                           "résultat affiché n'est que l'écart immédiat entre "
                           "le prix payé et le prix de marché, et le TRI n'est "
                           "pas défini sur une durée nulle. Reculer la date "
                           "d'achat donne la performance réellement réalisée.")

            st.markdown("#### Conserver jusqu'à l'échéance, ou vendre et replacer")
            reglages_arbitrage = st.columns(3)
            horizon_choix = reglages_arbitrage[0].selectbox(
                "Horizon de comparaison",
                ["Jusqu'à l'échéance", "12 mois", "24 mois", "36 mois"])
            mois = {"12 mois": 12, "24 mois": 24, "36 mois": 36}.get(horizon_choix)
            date_horizon = (None if mois is None
                            else min(reglement + pd.DateOffset(months=mois),
                                     titre.echeance))
            taux_replacement = reglages_arbitrage[1].number_input(
                "Taux de replacement envisagé (%)", min_value=0.0, max_value=30.0,
                value=round(taux * 100, 3), step=0.10, format="%.3f",
                help="Taux auquel les fonds — coupons perçus comme produit "
                     "d'une éventuelle cession — seraient replacés.") / 100.0
            reglages_arbitrage[2].caption(
                "Le prix d'achat n'entre pas dans cet arbitrage : il est "
                "enterré. Seules comptent la valeur de cession disponible "
                "aujourd'hui et ce que chaque branche rapporte ensuite.")

            arbitrage = simulateur.conserver_ou_vendre(
                titre, reglement, taux, taux_replacement, montant, frais / 2,
                date_horizon)
            if not arbitrage:
                st.info("Horizon incompatible avec l'échéance du titre.")
            else:
                cartes_arb = st.columns(4)
                cartes_arb[0].metric(
                    "Valeur en conservant",
                    _fcfa(arbitrage["Valeur en conservant"], 0),
                    help=f"Flux capitalisés au taux de replacement jusqu'au "
                         f"{arbitrage['Horizon']:%d/%m/%Y}, valeur résiduelle "
                         "du titre incluse.")
                cartes_arb[1].metric(
                    "Valeur en vendant et replaçant",
                    _fcfa(arbitrage["Valeur en vendant et replaçant"], 0),
                    help="Produit de cession net de frais, replacé au même taux.")
                cartes_arb[2].metric(
                    "Écart",
                    _fcfa(arbitrage["Écart (conserver − vendre)"], 0),
                    help="Positif : conserver l'emporte sous ces hypothèses.")
                cartes_arb[3].metric(
                    "Taux de replacement d'indifférence",
                    _pourcent(arbitrage["Taux de replacement d'indifférence"], 3),
                    help="Au-dessus de ce taux, replacer le produit de la "
                         "vente rapporte plus que conserver le titre ; en "
                         "dessous, conserver l'emporte.")

                bornes = np.linspace(max(0.005, taux - 0.05), taux + 0.05, 41)
                comparaison = []
                for candidat in bornes:
                    resultat = simulateur.conserver_ou_vendre(
                        titre, reglement, taux, float(candidat), montant,
                        frais / 2, date_horizon)
                    if not resultat:
                        continue
                    comparaison += [
                        {"Taux de replacement": float(candidat),
                         "Branche": "Conserver",
                         "Valeur": resultat["Valeur en conservant"]},
                        {"Taux de replacement": float(candidat),
                         "Branche": "Vendre et replacer",
                         "Valeur": resultat["Valeur en vendant et replaçant"]}]
                comparaison = pd.DataFrame(comparaison)
                croisement = arbitrage["Taux de replacement d'indifférence"]
                lignes_chart = alt.Chart(comparaison).mark_line().encode(
                    x=alt.X("Taux de replacement:Q", axis=alt.Axis(format="%"),
                            scale=alt.Scale(zero=False)),
                    y=alt.Y("Valeur:Q", title="Valeur à l'horizon (FCFA)",
                            scale=alt.Scale(zero=False)),
                    color=alt.Color("Branche:N", title=None,
                                    scale=alt.Scale(
                                        domain=["Conserver", "Vendre et replacer"],
                                        range=[VERT, BLEU])),
                    tooltip=["Branche",
                             alt.Tooltip("Taux de replacement:Q", format=".2%"),
                             alt.Tooltip("Valeur:Q", format=",.0f")])
                marque = alt.Chart(
                    pd.DataFrame({"x": [croisement]})).mark_rule(
                    color=ROUGE, strokeDash=[4, 3]).encode(x="x:Q")
                st.altair_chart(
                    (lignes_chart + marque).properties(
                        height=320,
                        title="Les deux branches selon le taux de replacement "
                              "— elles se croisent au point d'indifférence"),
                    width="stretch")
                st.caption(
                    "Le point d'indifférence coïncide avec le rendement de "
                    "marché du titre lorsque les coupons sont eux-mêmes "
                    "replacés à ce rendement : l'arbitrage se joue donc sur "
                    "les hypothèses de replacement et sur l'anticipation de "
                    "taux, jamais sur le prix payé jadis.")

# --------------------------------------------------------------------------
# Horizon et scénarios
# --------------------------------------------------------------------------
with onglets[3]:
    reglages_horizon = st.columns(3)
    horizon_mois = reglages_horizon[0].slider(
        "Horizon principal (mois)", 1,
        max(2, int(maturite * 12)), min(12, max(2, int(maturite * 12))))
    taux_reinvestissement = reglages_horizon[1].number_input(
        "Taux de réinvestissement (%)", min_value=0.0, max_value=30.0,
        value=round(taux * 100, 3), step=0.10, format="%.3f",
        help="Taux auquel les coupons perçus avant l'horizon sont replacés. "
             "Son poids grandit avec la durée de détention.") / 100.0
    choc_central = reglages_horizon[2].slider(
        "Choc de taux à l'horizon (pb)", -300, 300, 0, step=25,
        help="Déplacement du rendement du titre entre aujourd'hui et l'horizon.")

    date_horizon = min(reglement + pd.DateOffset(months=int(horizon_mois)),
                       titre.echeance)
    scenario = simulateur.analyse_horizon(
        titre, reglement, taux, date_horizon, taux + choc_central / 10_000.0,
        taux_reinvestissement, montant)

    cartes_horizon = st.columns(5)
    cartes_horizon[0].metric("Valeur à l'horizon",
                             _fcfa(scenario["Valeur finale"], 0),
                             help=f"Au {date_horizon:%d/%m/%Y}.")
    cartes_horizon[1].metric("Gain", _fcfa(scenario["Gain"], 0))
    cartes_horizon[2].metric("Rendement total annualisé",
                             _pourcent(scenario["Rendement total"], 2),
                             help="Rendement effectivement réalisé sur "
                                  "l'horizon, coupons replacés compris.")
    cartes_horizon[3].metric("Rendement cumulé",
                             _pourcent(scenario["Rendement cumulé"], 2))
    coussin_horizon = simulateur.choc_indifference(
        titre, reglement, taux, date_horizon, taux_reinvestissement, montant)
    cartes_horizon[4].metric("Choc d'indifférence", _pb(coussin_horizon),
                             help="Hausse de taux à l'horizon qui ramène le "
                                  "rendement total à zéro.")

    decomposition = pd.DataFrame([
        {"Effet": "Coupons perçus", "Montant": scenario["Coupons perçus"]},
        {"Effet": "Réinvestissement",
         "Montant": scenario["Effet de réinvestissement"]},
        {"Effet": "Portage (taux inchangé)", "Montant": scenario["Effet de portage"]},
        {"Effet": "Effet taux", "Montant": scenario["Effet taux"]},
        {"Effet": "Gain total", "Montant": scenario["Gain"]},
    ])
    st.altair_chart(
        alt.Chart(decomposition).mark_bar().encode(
            x=alt.X("Montant:Q", title="FCFA"),
            y=alt.Y("Effet:N", title=None, sort=list(decomposition["Effet"])),
            color=alt.condition(alt.datum.Montant >= 0, alt.value(VERT),
                                alt.value(ROUGE)),
            tooltip=["Effet", alt.Tooltip("Montant:Q", format=",.0f")],
        ).properties(height=220,
                     title="Décomposition du gain — les trois premiers effets "
                           "et l'effet taux somment exactement au total"),
        width="stretch")
    st.caption("Le portage est ce que rapporte le seul passage du temps à taux "
               "inchangé : rapprochement du pair et glissement le long de la "
               "courbe. L'effet taux est ce que le choc retenu ajoute ou "
               "retire par-dessus.")

    st.markdown("#### Grille de scénarios")
    horizons = sorted({1, 3, 6, 12, 24, 36, int(horizon_mois)})
    horizons = [h for h in horizons if h <= max(2, int(maturite * 12))]
    chocs = [-200, -100, -50, 0, 50, 100, 200]
    matrice = simulateur.matrice_horizon(
        titre, reglement, taux, horizons, chocs, taux_reinvestissement, montant)
    tableau = matrice.pivot(index="Horizon (mois)", columns="Choc (pb)",
                            values="Rendement total")
    tableau.columns = [f"{int(c):+d} pb" for c in tableau.columns]
    st.dataframe(
        tableau.style.format("{:.2%}", na_rep="—")
        .background_gradient(cmap="RdYlGn", axis=None),
        width="stretch")
    st.caption("Rendement total annualisé, coupons replacés au taux retenu. "
               "Lecture en ligne : plus l'horizon est long, plus le portage "
               "compense un choc de taux — c'est l'effet de la duration qui "
               "s'épuise à mesure que le titre vieillit.")

    seuils = pd.DataFrame([
        {"Horizon (mois)": mois_,
         "Choc d'indifférence (pb)": simulateur.choc_indifference(
             titre, reglement, taux,
             min(reglement + pd.DateOffset(months=int(mois_)), titre.echeance),
             taux_reinvestissement, montant)}
        for mois_ in horizons])
    st.altair_chart(
        alt.Chart(seuils.dropna()).mark_line(point=True, color=BLEU).encode(
            x=alt.X("Horizon (mois):O", title="Horizon (mois)"),
            y=alt.Y("Choc d'indifférence (pb):Q", title="pb"),
            tooltip=["Horizon (mois)",
                     alt.Tooltip("Choc d'indifférence (pb):Q", format=".0f")],
        ).properties(height=240,
                     title="Hausse de taux absorbable avant que le rendement "
                           "total ne devienne négatif"),
        width="stretch")

# --------------------------------------------------------------------------
# Conventions
# --------------------------------------------------------------------------
with onglets[4]:
    st.markdown("""
#### Conventions de calcul

- **Rendement** : taux actuariel annuel, composition annuelle, base
  **Exact/365** — la convention du « Rendement moyen » publié par UMOA-Titres
  et celle retenue par `scripts/finance.py` pour les analytiques du secondaire.
  Une maturité de cinq ans calendaires vaut donc 5,003 années actuarielles, ce
  qui suffit à décaler un prix au pair de quelques points de base.
- **Échéancier** : construit à rebours depuis l'échéance, par anniversaires.
  L'irrégularité éventuelle tombe sur la première période, comme au contrat.
- **Coupon couru** : prorata Exact/365 depuis le dernier détachement, exprimé
  en pourcentage du nominal résiduel.
- **Amortissables** : in fine, amortissement constant du capital ou annuités
  constantes, avec différé. Les prix et sensibilités sont rapportés au
  **nominal résiduel** — sur un titre déjà amorti, le pair n'est plus 100 % du
  nominal d'origine.
- **BAT** : taux facial nul, flux unique à l'échéance, prix = valeur
  actualisée. Le rendement affiché est actuariel, pas précompté.
- **Durations et convexité** : calculées sur le prix total (coupon couru
  inclus), qui est la valeur réellement exposée au risque de taux.

#### Ce que la simulation ne dit pas

- Elle ne prévoit pas les taux. Les scénarios sont des hypothèses affichées
  comme telles, et les points d'indifférence servent à situer une décision, non
  à la prendre.
- Elle ignore la fiscalité, le risque de crédit de l'émetteur et le risque de
  liquidité : sur les souches peu négociées du secondaire UMOA, la sortie au
  prix affiché n'est pas garantie.
- Les repères de marché valent ce que valent leurs sources : la courbe
  souveraine est parfois figée plusieurs semaines (page Courbes), et le
  dernier prix secondaire peut dater de plusieurs mois — l'onglet Lecture
  affiche systématiquement la base de chaque repère.
""")
    st.markdown("#### Paramètres de la simulation en cours")
    st.dataframe(pd.DataFrame([
        {"Paramètre": "Mode", "Valeur": mode},
        {"Paramètre": "Émetteur", "Valeur": pays},
        {"Paramètre": "Titre", "Valeur": titre.libelle or "Saisie libre"},
        {"Paramètre": "Taux facial", "Valeur": _pourcent(titre.coupon, 3)},
        {"Paramètre": "Jouissance",
         "Valeur": f"{titre.date_jouissance:%d/%m/%Y}"},
        {"Paramètre": "Échéance", "Valeur": f"{titre.echeance:%d/%m/%Y}"},
        {"Paramètre": "Amortissement",
         "Valeur": simulateur.LIBELLES_AMORTISSEMENT[titre.amortissement]
         + (f" — différé {differe} an(s)" if differe else "")},
        {"Paramètre": "Règlement", "Valeur": f"{reglement:%d/%m/%Y}"},
        {"Paramètre": "Montant nominal", "Valeur": _fcfa(montant, 0)},
        {"Paramètre": "Taux retenu", "Valeur": _pourcent(taux, 3)},
        {"Paramètre": "Courbe de référence",
         "Valeur": courbes.LIBELLES_NIVEAUX[niveau]},
        {"Paramètre": "Date de référence du référentiel",
         "Valeur": f"{reference:%d/%m/%Y}"},
    ]), hide_index=True, width="stretch")
