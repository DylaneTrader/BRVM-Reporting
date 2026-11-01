# -*- coding: utf-8 -*-
"""Fiche titre — tout ce que les trois sources savent d'une souche.

Cible de drill depuis le référentiel (et, plus tard, depuis les pages marché).
Le titre sélectionné est porté par le paramètre d'URL `titre`, de sorte qu'une
fiche puisse être partagée par simple copie du lien.
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.lib import chargement, courbes, qualite_prix, referentiel  # noqa: E402

st.set_page_config(page_title="Fiche titre", page_icon="🔎", layout="wide")


@st.cache_data(show_spinner="Construction du référentiel…")
def _referentiel(reglages: dict) -> pd.DataFrame:
    return referentiel.construire_referentiel(
        params=courbes.ParametresCourbe.depuis_etat(reglages))


@st.cache_data(show_spinner=False)
def _secondaire_evalue(isin: str | None, seuils: dict, reglages: dict) -> pd.DataFrame:
    historique = referentiel.historique_secondaire(isin)
    return qualite_prix.evaluer(
        historique, qualite_prix.ParametresQualite.depuis_etat(seuils),
        params_courbe=courbes.ParametresCourbe.depuis_etat(reglages))


def _pourcent(valeur, decimales: int = 2) -> str:
    return "—" if pd.isna(valeur) else f"{valeur * 100:.{decimales}f} %"


def _nombre(valeur, decimales: int = 2, suffixe: str = "") -> str:
    return "—" if pd.isna(valeur) else f"{valeur:,.{decimales}f}{suffixe}".replace(",", " ")


def _date(valeur) -> str:
    return "—" if pd.isna(valeur) else f"{valeur:%d/%m/%Y}"


reglages_courbe = courbes.parametres_actifs().en_dict()
titres = _referentiel(reglages_courbe)
reference = chargement.date_reference()

# --------------------------------------------------------------------------
# Sélection du titre
# --------------------------------------------------------------------------
identifiants = titres["Identifiant"].dropna().tolist()
depuis_url = st.query_params.get("titre")
if depuis_url not in identifiants:
    depuis_url = None


def _libelle(identifiant: str) -> str:
    ligne = titres[titres["Identifiant"] == identifiant].iloc[0]
    nom = ligne["Libellé BRVM"] if pd.notna(ligne["Libellé BRVM"]) else (
        f"{ligne['Pays']} {_pourcent(ligne['Coupon'], 2)} "
        f"éch. {_date(ligne['Échéance'])}")
    return f"{identifiant} — {nom}"


with st.sidebar:
    st.header("Titre")
    choix = st.selectbox(
        "Rechercher", identifiants,
        index=identifiants.index(depuis_url) if depuis_url else 0,
        format_func=_libelle,
        help="ISIN pour les titres d'adjudication, `BRVM:<code>` pour les "
             "lignes cotées sans ISIN retrouvé.")
    st.header("Seuils de fiabilité")
    st.caption("Réglages du score des prix du marché secondaire.")
    defauts = qualite_prix.ParametresQualite()
    seuils = {
        "seuil_courbe_b": st.slider(
            "Écart à la courbe → B (pb)", 50, 500, int(defauts.seuil_courbe_b), 25),
        "seuil_courbe_c": st.slider(
            "Écart à la courbe → C (pb)", 100, 900, int(defauts.seuil_courbe_c), 25),
        "min_transactions": st.slider(
            "Transactions minimum", 1, 5, defauts.min_transactions),
        "seuil_adjudication": st.slider(
            "Écart à l'adjudication (pb)", 50, 900, int(defauts.seuil_adjudication), 25),
    }

if choix != depuis_url:
    st.query_params["titre"] = choix

fiche = referentiel.titre(titres, choix)
if fiche is None:
    st.error("Titre introuvable.")
    st.stop()

# --------------------------------------------------------------------------
# En-tête
# --------------------------------------------------------------------------
if pd.notna(fiche["Libellé BRVM"]):
    nom = fiche["Libellé BRVM"]
else:
    # Les BAT sont des zéro-coupon : afficher « — » à la place du taux facial
    # ferait croire à une donnée manquante.
    coupon = (f" {fiche['Coupon'] * 100:.2f} %" if pd.notna(fiche["Coupon"])
              and fiche["Coupon"] > 0 else "")
    nom = (f"{fiche['Pays']} — {fiche['Instrument']}{coupon} "
           f"échéance {_date(fiche['Échéance'])}")
st.title(nom)

etiquettes = [fiche["Segment"], fiche["Statut"],
              "Coté BRVM" if fiche["Coté"] else "Non coté", fiche["Origine"]]
st.caption(" · ".join(str(e) for e in etiquettes if pd.notna(e))
           + f" · au {reference:%d/%m/%Y}")

if fiche["Statut"] == "Échu":
    st.info("Ce titre est arrivé à échéance. Les indicateurs ci-dessous sont "
            "ceux de sa dernière observation.")

cartes = st.columns(6)
cartes[0].metric("Encours", _nombre(fiche["Encours (Mds FCFA)"], 1, " Mds"),
                 help=("Approché par le cumul des montants levés en adjudication."
                       if fiche["Encours estimé"] else
                       "Observé au marché secondaire." if fiche["Encours connu"]
                       else "Non documenté."))
cartes[1].metric("Coupon", _pourcent(fiche["Coupon"]))
cartes[2].metric("Maturité résiduelle",
                 _nombre(fiche["Maturité résiduelle (années)"], 2, " ans"),
                 help="Échéance estimée d'après le millésime du libellé BRVM."
                 if fiche["Échéance estimée"] else None)
cartes[3].metric("Dernier YTM", _pourcent(fiche["Dernier YTM"]),
                 help="Rendement de la dernière séance de négociation.")
cartes[4].metric("Duration modifiée", _nombre(fiche["Duration modifiée"]),
                 help=f"Méthode : {fiche['Méthode de calcul']}"
                 if pd.notna(fiche["Méthode de calcul"]) else None)
cartes[5].metric("Convexité", _nombre(fiche["Convexité"], 1))

prix = st.columns(4)
prix[0].metric("Prix de référence", _nombre(fiche["Prix de référence"], 4))
prix[1].metric("Source du prix", str(fiche["Source du prix"]))
prix[2].metric("Date du prix", _date(fiche["Date du prix"]))
prix[3].metric("Âge du prix",
               _nombre(fiche["Âge du prix (jours)"], 0, " j"),
               help="Un prix ancien reste un prix : c'est son âge qui dit "
                    "combien de crédit lui accorder.")

if pd.notna(fiche["Écart YTM / courbe (pb)"]):
    ecart = fiche["Écart YTM / courbe (pb)"]
    st.markdown(
        f"Dernier rendement négocié **{ecart:+.0f} pb** par rapport à la courbe "
        f"{fiche['Pays']} à même maturité "
        f"({_pourcent(fiche['Taux courbe (maturité)'])}).")

if fiche["Statut"] == "Vivant" and pd.notna(fiche["Échéance"]):
    # Le simulateur relit le même paramètre d'URL : la souche affichée y est
    # préchargée sans nouvelle recherche.
    st.page_link("pages/9_Simulateur.py", icon="🧮",
                 label="Simuler cette souche — prix, sensibilité, horizon, "
                       "arbitrage conserver / vendre")

# --------------------------------------------------------------------------
# Blocs
# --------------------------------------------------------------------------
onglets = st.tabs(["Identité", "Son émission", "Sa vie secondaire",
                   "Sa cotation BRVM"])

# --- Identité --------------------------------------------------------------
with onglets[0]:
    champs = [
        ("Identifiant", fiche["Identifiant"]),
        ("ISIN", fiche["ISIN"]),
        ("Code BRVM", fiche["Code BRVM"]),
        ("Libellé BRVM", fiche["Libellé BRVM"]),
        ("Segment", fiche["Segment"]),
        ("Pays / émetteur", fiche["Pays"]),
        ("Instrument", fiche["Instrument"]),
        ("Coupon", _pourcent(fiche["Coupon"])),
        ("Date d'émission", _date(fiche["Date d'émission"])),
        ("Échéance", _date(fiche["Échéance"])
         + (" (estimée)" if fiche["Échéance estimée"] else "")),
        ("Maturité résiduelle", _nombre(fiche["Maturité résiduelle (années)"], 2, " ans")),
        ("Mode d'amortissement", fiche["Amortissement"]),
        ("Encours", _nombre(fiche["Encours (Mds FCFA)"], 2, " Mds FCFA")
         + (" (estimé)" if fiche["Encours estimé"] else "")),
        ("Nombre de tranches d'adjudication", fiche["Nb tranches"]),
        ("Montant total levé", _nombre(fiche["Montant levé (Mds FCFA)"], 2, " Mds FCFA")),
        ("Taux d'adjudication moyen", _pourcent(fiche["Taux d'adjudication moyen"])),
        ("Séances négociées", fiche["Nb séances négociées"]),
        ("Volume échangé cumulé", _nombre(fiche["Volume échangé (Mds FCFA)"], 2, " Mds FCFA")),
        ("Sources", fiche["Origine"]),
    ]
    st.dataframe(
        pd.DataFrame([{"Champ": c, "Valeur": "—" if pd.isna(v) else str(v)}
                      for c, v in champs]),
        hide_index=True, width="stretch", height=560)

# --- Son émission ----------------------------------------------------------
with onglets[1]:
    tranches = referentiel.historique_primaire(fiche["ISIN"])
    if tranches.empty:
        if fiche["Coté"]:
            st.info("Aucune adjudication connue pour ce titre. C'est le cas "
                    "normal des lignes cotées issues d'appels publics à "
                    "l'épargne ou de syndications, un canal que le marché des "
                    "adjudications ne couvre pas.")
        else:
            st.info("Aucune adjudication connue pour ce titre : il n'apparaît "
                    "que dans les transactions du marché secondaire, sans "
                    "opération primaire rattachable à son ISIN.")
    else:
        st.markdown(f"**{len(tranches)} tranche(s)** sur la même souche — "
                    "une souche profonde est rouverte au fil des besoins de "
                    "financement de l'État.")
        incoherents = int(tranches["Montant incohérent"].sum())
        if incoherents:
            st.warning(
                f"{incoherents} tranche(s) portent un montant retenu négatif. "
                "Sur les émissions simultanées, la ventilation par titre est "
                "reconstituée par différence dans la source et sort négative "
                "sur 14,2 % des lignes du marché primaire. Les montants au "
                "niveau de l'opération et les taux servis restent exploitables.")

        graphique = alt.Chart(tranches.dropna(
            subset=["Rendement moyen pondéré (déc.)"])).mark_circle(size=140).encode(
            x=alt.X("Date de l'opération:T", title=None),
            y=alt.Y("Rendement moyen pondéré (déc.):Q", title="Taux servi",
                    axis=alt.Axis(format="%"), scale=alt.Scale(zero=False)),
            size=alt.Size("Taux de couverture:Q", title="Couverture"),
            color=alt.value("#1f6f8b"),
            tooltip=[alt.Tooltip("Date de l'opération:T", format="%d/%m/%Y"),
                     alt.Tooltip("Rendement moyen pondéré (déc.):Q", format=".2%"),
                     alt.Tooltip("Taux de couverture:Q", format=".2f"),
                     alt.Tooltip("Montant retenu (Mds FCFA):Q", format=".2f")],
        ).properties(height=280, title="Taux servi à chaque réouverture")
        st.altair_chart(graphique, width="stretch")

        st.dataframe(
            tranches.drop(columns=["Lien"]), hide_index=True, width="stretch",
            column_config={
                "Date de l'opération": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Date de valeur": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Échéance": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Rendement moyen pondéré (déc.)": st.column_config.NumberColumn(
                    "Rendement moyen pondéré", format="percent"),
                "Taux marginal (déc.)": st.column_config.NumberColumn(
                    "Taux marginal", format="percent"),
                "Taux moyen pondéré (déc.)": st.column_config.NumberColumn(
                    "Taux moyen pondéré", format="percent"),
                "Taux de couverture": st.column_config.NumberColumn(format="%.2f"),
                "Taux de service": st.column_config.NumberColumn(format="%.2f"),
            })

# --- Sa vie secondaire -----------------------------------------------------
with onglets[2]:
    seances = _secondaire_evalue(fiche["ISIN"], seuils, reglages_courbe)
    if seances.empty:
        st.info("Ce titre n'a jamais été négocié sur le marché secondaire des "
                "titres publics.")
    else:
        repartition = qualite_prix.synthese(seances)
        atypiques = repartition.loc[
            repartition["Score"] == qualite_prix.SCORE_C, "Lignes"].sum()
        st.markdown(
            f"**{len(seances)} séance(s)** de négociation, dont **{int(atypiques)}** "
            "classée(s) atypique(s). Le classement compare chaque rendement à la "
            "courbe du pays, à la profondeur du print et au taux servi en "
            "adjudication — c'est un signalement, pas un verdict.")

        # Altair ne sérialise pas les colonnes catégorielles : le score est
        # ramené en texte pour les graphiques, l'ordre étant porté par l'échelle.
        pour_graphique = seances.assign(Score=seances["Score"].astype(str))

        graphique_taux = alt.Chart(pour_graphique).mark_circle(size=90).encode(
            x=alt.X("Date de transaction:T", title=None),
            y=alt.Y("YTM:Q", title="Rendement", axis=alt.Axis(format="%"),
                    scale=alt.Scale(zero=False)),
            color=alt.Color("Score:N", title="Fiabilité",
                            scale=alt.Scale(
                                domain=list(qualite_prix.COULEURS_SCORES) + ["Non évaluable"],
                                range=list(qualite_prix.COULEURS_SCORES.values()) + ["#9aa0a6"])),
            tooltip=[alt.Tooltip("Date de transaction:T", format="%d/%m/%Y"),
                     alt.Tooltip("YTM:Q", format=".2%"),
                     alt.Tooltip("Taux courbe:Q", format=".2%"),
                     alt.Tooltip("Écart courbe (pb):Q", format=".0f"),
                     alt.Tooltip("Nombre de transactions:Q"),
                     alt.Tooltip("Volume global (Mds FCFA):Q", format=".2f"),
                     "Motifs"],
        )
        ligne_courbe = alt.Chart(pour_graphique.dropna(subset=["Taux courbe"])).mark_line(
            color="#5a5a5a", strokeDash=[5, 4]).encode(
            x="Date de transaction:T", y=alt.Y("Taux courbe:Q"))
        st.altair_chart(
            (ligne_courbe + graphique_taux).resolve_scale(y="shared")
            .properties(height=320,
                        title="Rendement négocié et courbe du pays à même maturité"),
            width="stretch")

        volumes = alt.Chart(pour_graphique).mark_bar(color="#1f6f8b").encode(
            x=alt.X("Date de transaction:T", title=None),
            y=alt.Y("Volume global (Mds FCFA):Q", title="Volume (Mds FCFA)"),
            tooltip=[alt.Tooltip("Date de transaction:T", format="%d/%m/%Y"),
                     alt.Tooltip("Volume global (Mds FCFA):Q", format=".2f"),
                     alt.Tooltip("Nombre de transactions:Q")],
        ).properties(height=160, title="Volume échangé par séance")
        st.altair_chart(volumes, width="stretch")

        st.dataframe(repartition, hide_index=True, width="stretch",
                     column_config={
                         "Volume (Mds FCFA)": st.column_config.NumberColumn(format="%.2f"),
                         "Part des lignes": st.column_config.NumberColumn(format="percent"),
                         "Part du volume": st.column_config.NumberColumn(format="percent"),
                     })

        colonnes = ["Date de transaction", "Nombre de transactions", "Quantité",
                    "Prix moyen", "YTM", "Taux courbe", "Écart courbe (pb)",
                    "Taux adjudication", "Écart adjudication (pb)",
                    "Volume global (Mds FCFA)", "Duration modifiée", "Convexité",
                    "Score", "Motifs"]
        st.dataframe(
            seances[colonnes].sort_values("Date de transaction", ascending=False),
            hide_index=True, width="stretch", height=420,
            column_config={
                "Date de transaction": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Prix moyen": st.column_config.NumberColumn(format="%.4f"),
                "YTM": st.column_config.NumberColumn(format="percent"),
                "Taux courbe": st.column_config.NumberColumn(format="percent"),
                "Taux adjudication": st.column_config.NumberColumn(format="percent"),
                "Écart courbe (pb)": st.column_config.NumberColumn(format="%.0f"),
                "Écart adjudication (pb)": st.column_config.NumberColumn(format="%.0f"),
                "Volume global (Mds FCFA)": st.column_config.NumberColumn(format="%.3f"),
                "Duration modifiée": st.column_config.NumberColumn(format="%.2f"),
                "Convexité": st.column_config.NumberColumn(format="%.1f"),
            })

# --- Sa cotation BRVM ------------------------------------------------------
with onglets[3]:
    cotations = referentiel.historique_brvm(fiche["Code BRVM"])
    if cotations.empty:
        st.info("Ce titre n'est pas inscrit à la cote de la BRVM — ou sa ligne "
                "cotée n'a pas pu être rapprochée de cette souche.")
    else:
        entete = st.columns(4)
        derniere = cotations.iloc[-1]
        entete[0].metric("Cours du jour", _nombre(derniere["Cours du jour"], 2))
        entete[1].metric("Coupon couru", _nombre(derniere["Coupon couru"], 2))
        entete[2].metric("Taux facial", _pourcent(derniere["Taux facial"]))
        entete[3].metric("Dernière cotation", _date(derniere["Date de cotation"]))

        cours = alt.Chart(cotations).mark_line(color="#1f6f8b", point=True).encode(
            x=alt.X("Date de cotation:T", title=None),
            y=alt.Y("Cours du jour:Q", title="Cours", scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("Date de cotation:T", format="%d/%m/%Y"),
                     alt.Tooltip("Cours du jour:Q", format=".2f"),
                     alt.Tooltip("Coupon couru:Q", format=".2f")],
        ).properties(height=280, title="Cours coté")
        st.altair_chart(cours, width="stretch")

        if pd.notna(fiche["Dernier prix secondaire"]) and pd.notna(derniere["Cours du jour"]):
            cours_pair = (derniere["Cours du jour"] / 10_000
                          if derniere["Cours du jour"] > 200
                          else derniere["Cours du jour"] / 100)
            ecart_prix = (cours_pair - fiche["Dernier prix secondaire"]) * 100
            st.markdown(
                f"Écart entre le cours BRVM ({cours_pair:.4f} du pair) et le "
                f"dernier prix du marché secondaire "
                f"({fiche['Dernier prix secondaire']:.4f}) : **{ecart_prix:+.2f} "
                "points de pair**. Un écart durable entre les deux compartiments "
                "est une information en soi, pas nécessairement une erreur.")

        st.dataframe(
            cotations.sort_values("Date de cotation", ascending=False),
            hide_index=True, width="stretch", height=380,
            column_config={
                "Date de cotation": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Cours du jour": st.column_config.NumberColumn(format="%.2f"),
                "Coupon couru": st.column_config.NumberColumn(format="%.2f"),
                "Taux facial": st.column_config.NumberColumn(format="percent"),
            })
