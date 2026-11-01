# -*- coding: utf-8 -*-
"""Marché secondaire : activité, concentration et rotation.

Le classement de fiabilité des prix vit dans `qualite_prix` ; ce module s'occupe
des agrégats, en déclinant systématiquement chaque mesure de rendement sur deux
univers :

  * **complet** — toutes les lignes, y compris les prints atypiques ;
  * **retenu** — hors lignes classées C.

L'écart entre les deux n'est pas un détail de présentation : sur l'historique
complet, le rendement moyen pondéré passe de 5,87 % à 6,13 %. Ces 26 pb sont la
mesure de ce que les transactions hors marché coûtent à la lecture du marché.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from dataclasses import asdict, dataclass, fields

from . import chargement, qualite_prix


@dataclass(frozen=True)
class FiltreSecondaire:
    """Traitement du marché secondaire, réglable dans l'application et dans Power BI.

    Les lignes ne sont jamais supprimées des fichiers : chaque réglage retire des lignes du calcul
    affiché. Défauts : doublons exacts et rendements nuls ou négatifs écartés, aucune exigence de
    profondeur (sur l'historique, 53 % des lignes n'ont qu'une transaction ; exiger au moins 3
    transactions retire 82 % des lignes et 60 % du volume).
    """

    #: Nombre minimal de transactions d'une ligne (1 = toutes les lignes).
    min_transactions: int = 1
    #: Écarter les transactions publiées deux fois à l'identique.
    exclure_doublons: bool = True
    #: Écarter les rendements nuls ou négatifs.
    exclure_rendements_non_positifs: bool = True
    #: Écarter les lignes classées C (atypiques) par `qualite_prix`.
    exclure_atypiques: bool = False
    #: Volume global minimal d'une ligne (Mds FCFA), 0 = pas de seuil.
    volume_min_mds: float = 0.0

    @classmethod
    def depuis_etat(cls, etat: dict | None) -> "FiltreSecondaire":
        if not etat:
            return cls()
        connus = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in etat.items() if k in connus})

    def en_dict(self) -> dict:
        return asdict(self)


def filtrer(donnees: pd.DataFrame, filtre: FiltreSecondaire | None = None) -> pd.DataFrame:
    """Lignes retenues par ``filtre`` ; ``donnees.attrs["retirees"]`` compte les lignes retirées
    par motif (une ligne compte pour le premier motif qui l'écarte)."""
    filtre = filtre or FiltreSecondaire()
    garde = pd.Series(True, index=donnees.index)
    retirees = {}

    def _retirer(motif: str, masque: pd.Series) -> None:
        nonlocal garde
        masque = masque.fillna(False).astype(bool) & garde
        retirees[motif] = int(masque.sum())
        garde &= ~masque

    if filtre.exclure_doublons and "Doublon" in donnees:
        _retirer("doublon", donnees["Doublon"].astype(bool))
    if filtre.exclure_rendements_non_positifs:
        _retirer("rendement nul ou négatif", pd.to_numeric(donnees["Rendement moyen"], errors="coerce").le(0))
    if filtre.min_transactions > 1:
        _retirer(f"moins de {filtre.min_transactions} transactions",
                 pd.to_numeric(donnees["Nombre de transactions"], errors="coerce") < filtre.min_transactions)
    if filtre.volume_min_mds > 0:
        _retirer(f"volume sous {filtre.volume_min_mds:g} Mds FCFA",
                 pd.to_numeric(donnees["Volume global (Mds FCFA)"], errors="coerce") < filtre.volume_min_mds)
    if filtre.exclure_atypiques and "Score" in donnees:
        _retirer("prix atypique (C)", donnees["Score"] == qualite_prix.SCORE_C)
    resultat = donnees[garde].copy()
    resultat.attrs["retirees"] = retirees
    return resultat


def transactions(params_qualite: qualite_prix.ParametresQualite | None = None,
                 niveau_courbe: str = "officielle",
                 params_courbe=None,
                 filtre: FiltreSecondaire | None = None) -> pd.DataFrame:
    """Transactions du marché secondaire, enrichies du score de fiabilité, puis filtrées par
    ``filtre`` (``FiltreSecondaire()`` par défaut ; ``attrs["retirees"]`` : lignes retirées)."""
    brutes = chargement.marche_secondaire()
    evaluees = qualite_prix.evaluer(brutes, params_qualite, niveau_courbe,
                                    params_courbe)
    evaluees = evaluees.copy()
    evaluees["Mois"] = (evaluees["Date de transaction"].dt.to_period("M")
                        .dt.to_timestamp())
    evaluees["Année"] = evaluees["Date de transaction"].dt.year
    return filtrer(evaluees, filtre)


def _rendement_pondere(donnees: pd.DataFrame) -> float:
    """Rendement moyen pondéré par le volume global échangé."""
    poids = donnees["Volume global échangé"]
    taux = donnees["YTM"]
    valides = poids.notna() & taux.notna() & (poids > 0)
    if not valides.any():
        return float("nan")
    return float(np.average(taux[valides], weights=poids[valides]))


def resume(donnees: pd.DataFrame) -> dict:
    """Indicateurs de tête, déclinés sur les deux univers."""
    retenu = qualite_prix.univers_retenu(donnees)
    atypiques = donnees[donnees["Score"] == qualite_prix.SCORE_C]
    volume_total = donnees["Volume global (Mds FCFA)"].sum(skipna=True)
    rendement_complet = _rendement_pondere(donnees)
    rendement_retenu = _rendement_pondere(retenu)
    return {
        "Séances-titres": int(len(donnees)),
        "Transactions": int(donnees["Nombre de transactions"].sum(skipna=True)),
        "Volume (Mds FCFA)": float(volume_total),
        "Titres négociés": int(donnees["ISIN"].nunique()),
        "Rendement (univers complet)": rendement_complet,
        "Rendement (univers retenu)": rendement_retenu,
        "Écart des univers (pb)": (
            (rendement_retenu - rendement_complet) * 10_000
            if not (pd.isna(rendement_complet) or pd.isna(rendement_retenu))
            else float("nan")),
        "Lignes atypiques": int(len(atypiques)),
        "Volume atypique (Mds FCFA)": float(
            atypiques["Volume global (Mds FCFA)"].sum(skipna=True)),
        "Part du volume atypique": (
            float(atypiques["Volume global (Mds FCFA)"].sum(skipna=True) / volume_total)
            if volume_total else float("nan")),
        "Duration modifiée moyenne": _moyenne_volume(retenu, "Duration modifiée"),
        "Maturité résiduelle moyenne": _moyenne_volume(
            retenu, "Maturité résiduelle (années)"),
    }


def _moyenne_volume(donnees: pd.DataFrame, colonne: str) -> float:
    poids = donnees["Volume global échangé"]
    valeurs = donnees[colonne]
    valides = poids.notna() & valeurs.notna() & (poids > 0)
    if not valides.any():
        return float("nan")
    return float(np.average(valeurs[valides], weights=poids[valides]))


def evolution_mensuelle(donnees: pd.DataFrame) -> pd.DataFrame:
    """Volume, transactions et rendement mensuels, sur les deux univers."""
    colonnes = ["Mois", "Volume (Mds FCFA)", "Séances-titres", "Transactions",
                "Rendement complet", "Rendement retenu", "Volume atypique"]
    if donnees.empty:
        return pd.DataFrame(columns=colonnes)
    agrege = donnees.groupby("Mois").apply(lambda groupe: pd.Series({
        "Volume (Mds FCFA)": groupe["Volume global (Mds FCFA)"].sum(skipna=True),
        "Séances-titres": len(groupe),
        "Transactions": groupe["Nombre de transactions"].sum(skipna=True),
        "Rendement complet": _rendement_pondere(groupe),
        "Rendement retenu": _rendement_pondere(qualite_prix.univers_retenu(groupe)),
        "Volume atypique": groupe.loc[
            groupe["Score"] == qualite_prix.SCORE_C,
            "Volume global (Mds FCFA)"].sum(skipna=True),
    }), include_groups=False).reset_index()
    return agrege[colonnes]


def par_modalite(donnees: pd.DataFrame, cle: str) -> pd.DataFrame:
    """Volume, rendement et part atypique par pays, instrument ou autre clé."""
    colonnes = [cle, "Séances-titres", "Volume (Mds FCFA)", "Rendement retenu",
                "Part du volume atypique"]
    if donnees.empty or cle not in donnees.columns:
        return pd.DataFrame(columns=colonnes)
    agrege = donnees.groupby(cle, observed=True).apply(
        lambda groupe: pd.Series({
            "Séances-titres": len(groupe),
            "Volume (Mds FCFA)": groupe["Volume global (Mds FCFA)"].sum(skipna=True),
            "Rendement retenu": _rendement_pondere(
                qualite_prix.univers_retenu(groupe)),
            "Part du volume atypique": (
                groupe.loc[groupe["Score"] == qualite_prix.SCORE_C,
                           "Volume global (Mds FCFA)"].sum(skipna=True)
                / groupe["Volume global (Mds FCFA)"].sum(skipna=True)
                if groupe["Volume global (Mds FCFA)"].sum(skipna=True) else np.nan),
        }), include_groups=False).reset_index()
    return (agrege[colonnes].sort_values("Volume (Mds FCFA)", ascending=False)
            .reset_index(drop=True))


def concentration(donnees: pd.DataFrame, sommet: int = 20) -> pd.DataFrame:
    """Titres les plus échangés et part cumulée du volume."""
    colonnes = ["ISIN", "Pays", "Instrument", "Séances", "Volume (Mds FCFA)",
                "Part du volume", "Part cumulée"]
    if donnees.empty:
        return pd.DataFrame(columns=colonnes)
    agrege = donnees.groupby("ISIN", observed=True).agg(**{
        "Pays": ("Pays", "first"),
        "Instrument": ("Instrument", "first"),
        "Séances": ("ISIN", "size"),
        "Volume (Mds FCFA)": ("Volume global (Mds FCFA)", "sum"),
    }).reset_index().sort_values("Volume (Mds FCFA)", ascending=False)
    total = agrege["Volume (Mds FCFA)"].sum()
    agrege["Part du volume"] = agrege["Volume (Mds FCFA)"] / total if total else np.nan
    agrege["Part cumulée"] = agrege["Part du volume"].cumsum()
    return agrege[colonnes].head(sommet).reset_index(drop=True)


def rotation(donnees: pd.DataFrame, titres: pd.DataFrame) -> pd.DataFrame:
    """Volume échangé rapporté à l'encours, par pays.

    Mesure de liquidité rendue possible par le référentiel : sans encours par
    titre, le volume seul ne dit pas si un compartiment est actif ou simplement
    gros. L'encours n'étant documenté que pour une partie de l'univers, la
    couverture accompagne le ratio.
    """
    colonnes = ["Pays", "Volume (Mds FCFA)", "Encours (Mds FCFA)",
                "Rotation", "Titres à encours connu"]
    if donnees.empty or titres.empty:
        return pd.DataFrame(columns=colonnes)
    vivants = titres[(titres["Statut"] == "Vivant") & titres["Encours connu"]]
    encours = vivants.groupby("Pays", observed=True).agg(**{
        "Encours (Mds FCFA)": ("Encours (Mds FCFA)", "sum"),
        "Titres à encours connu": ("Identifiant", "count"),
    }).reset_index()
    volumes = donnees.groupby("Pays", observed=True).agg(**{
        "Volume (Mds FCFA)": ("Volume global (Mds FCFA)", "sum"),
    }).reset_index()
    fusion = volumes.merge(encours, on="Pays", how="left")
    fusion["Rotation"] = (fusion["Volume (Mds FCFA)"]
                          / fusion["Encours (Mds FCFA)"])
    return (fusion[colonnes].sort_values("Rotation", ascending=False)
            .reset_index(drop=True))


def prints_atypiques(donnees: pd.DataFrame, sommet: int = 200) -> pd.DataFrame:
    """Lignes classées atypiques, les plus gros volumes d'abord."""
    colonnes = ["Date de transaction", "Pays", "Instrument", "ISIN",
                "Maturité résiduelle (années)", "Nombre de transactions",
                "Prix moyen", "YTM", "Taux courbe", "Écart courbe (pb)",
                "Écart adjudication (pb)", "Volume global (Mds FCFA)", "Motifs"]
    if donnees.empty:
        return pd.DataFrame(columns=colonnes)
    atypiques = donnees[donnees["Score"] == qualite_prix.SCORE_C]
    if atypiques.empty:
        return pd.DataFrame(columns=colonnes)
    return (atypiques[colonnes]
            .sort_values("Volume global (Mds FCFA)", ascending=False)
            .head(sommet).reset_index(drop=True))
