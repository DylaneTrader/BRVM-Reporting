# -*- coding: utf-8 -*-
"""Marché primaire : adjudications, coût de financement et tension.

Le fichier source mélange deux grains. Chaque ligne est un **titre** servi, mais
plusieurs titres appartiennent souvent à une même **opération** d'adjudication
(les émissions simultanées, majoritaires depuis 2023). Les colonnes se déclinent
donc en deux familles, et elles n'ont pas la même fiabilité :

  * niveau titre  (`Montant retenu (Mds FCFA)`) — ventilation reconstituée par
    différence dans la source, **négative sur 14 % des lignes** ;
  * niveau opération (`Montant retenu opération (Mds FCFA)`) — publiée telle
    quelle, négative sur seulement **1,2 % des opérations**.

Tous les agrégats de volume passent donc par le niveau opération, dédoublonné
via `Premier titre de l'opération`. Les taux, eux, restent au grain du titre :
c'est là qu'ils ont un sens.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import chargement

COLONNES_OPERATION = [
    "Montant annoncé opération (Mds FCFA)", "Montant soumis opération (Mds FCFA)",
    "Montant retenu opération (Mds FCFA)",
]


def lignes(categorie: str = "Passée") -> pd.DataFrame:
    """Titres servis, au grain du titre. `categorie=None` pour tout prendre."""
    primaire = chargement.emissions_primaire()
    retenues = primaire if categorie is None else primaire[
        primaire["Catégorie"] == categorie]
    return retenues.copy()


def operations(categorie: str = "Passée") -> pd.DataFrame:
    """Une ligne par opération d'adjudication, volumes fiables.

    `Montant incohérent` marque les opérations dont les montants publiés sont
    négatifs : elles sont conservées (pour le décompte des opérations et les
    taux) mais exclues des sommes de volume.
    """
    detail = lignes(categorie)
    if detail.empty:
        return detail
    entetes = detail[detail["Premier titre de l'opération"].fillna(False)].copy()
    if entetes.empty:  # repli si le drapeau manque
        entetes = detail.drop_duplicates(subset=["Opération"]).copy()

    entetes["Montant incohérent"] = (
        entetes["Montant retenu opération (Mds FCFA)"] < 0)
    for colonne in COLONNES_OPERATION:
        entetes[colonne] = entetes[colonne].where(~entetes["Montant incohérent"])

    entetes["Mois"] = entetes["Date de l'opération"].dt.to_period("M").dt.to_timestamp()
    entetes["Année"] = entetes["Date de l'opération"].dt.year
    return entetes


def _moyenne_ponderee(valeurs: pd.Series, poids: pd.Series) -> float:
    """Moyenne pondérée robuste : poids nuls ou absents -> équipondération."""
    valides = valeurs.notna()
    if not valides.any():
        return float("nan")
    p = poids.where(poids > 0).reindex(valeurs.index)
    if p[valides].notna().any() and p[valides].sum() > 0:
        masque = valides & p.notna()
        return float(np.average(valeurs[masque], weights=p[masque]))
    return float(valeurs[valides].mean())


def resume(entetes: pd.DataFrame, detail: pd.DataFrame) -> dict:
    """Indicateurs de tête du périmètre : volumes, couverture, coût."""
    volumes = entetes[~entetes["Montant incohérent"]] if not entetes.empty else entetes
    poids_titre = detail["Montant retenu (Mds FCFA)"] if not detail.empty else pd.Series(dtype=float)
    return {
        "Opérations": int(len(entetes)),
        "Titres servis": int(len(detail)),
        "Montant annoncé (Mds FCFA)": float(
            volumes["Montant annoncé opération (Mds FCFA)"].sum(skipna=True)),
        "Montant soumis (Mds FCFA)": float(
            volumes["Montant soumis opération (Mds FCFA)"].sum(skipna=True)),
        "Montant retenu (Mds FCFA)": float(
            volumes["Montant retenu opération (Mds FCFA)"].sum(skipna=True)),
        "Taux de couverture moyen": _moyenne_ponderee(
            entetes["Taux de couverture"],
            entetes["Montant annoncé opération (Mds FCFA)"]) if not entetes.empty
        else float("nan"),
        "Taux de service moyen": _moyenne_ponderee(
            entetes["Taux de service"],
            entetes["Montant annoncé opération (Mds FCFA)"]) if not entetes.empty
        else float("nan"),
        "Rendement moyen pondéré": _moyenne_ponderee(
            detail["Rendement moyen pondéré (déc.)"], poids_titre)
        if not detail.empty else float("nan"),
        "Maturité moyenne (années)": _moyenne_ponderee(
            detail["Maturité (années)"], poids_titre)
        if not detail.empty else float("nan"),
        "Opérations à montant incohérent": int(entetes["Montant incohérent"].sum())
        if not entetes.empty else 0,
    }


def evolution_mensuelle(entetes: pd.DataFrame) -> pd.DataFrame:
    """Volumes annoncés / soumis / retenus et couverture, mois par mois."""
    colonnes = ["Mois", "Opérations", "Annoncé", "Soumis", "Retenu",
                "Taux de couverture"]
    if entetes.empty:
        return pd.DataFrame(columns=colonnes)
    agrege = entetes.groupby("Mois").apply(lambda groupe: pd.Series({
        "Opérations": len(groupe),
        "Annoncé": groupe["Montant annoncé opération (Mds FCFA)"].sum(skipna=True),
        "Soumis": groupe["Montant soumis opération (Mds FCFA)"].sum(skipna=True),
        "Retenu": groupe["Montant retenu opération (Mds FCFA)"].sum(skipna=True),
        "Taux de couverture": _moyenne_ponderee(
            groupe["Taux de couverture"],
            groupe["Montant annoncé opération (Mds FCFA)"]),
    }), include_groups=False).reset_index()
    return agrege[colonnes]


def cout_financement(detail: pd.DataFrame, par: str = "Pays",
                     frequence: str = "Q") -> pd.DataFrame:
    """Rendement moyen pondéré servi, par période et par modalité.

    Pondéré par les montants retenus positifs ; à défaut, équipondéré. C'est le
    coût de financement effectivement supporté par l'émetteur, pas une moyenne
    de taux affichés.
    """
    colonnes = ["Période", par, "Rendement", "Opérations"]
    if detail.empty or par not in detail.columns:
        return pd.DataFrame(columns=colonnes)
    travail = detail[detail["Rendement moyen pondéré (déc.)"].notna()
                     & detail["Date de l'opération"].notna()].copy()
    if travail.empty:
        return pd.DataFrame(columns=colonnes)
    travail["Période"] = (travail["Date de l'opération"].dt.to_period(frequence)
                          .dt.to_timestamp())
    agrege = travail.groupby(["Période", par], observed=True).apply(
        lambda groupe: pd.Series({
            "Rendement": _moyenne_ponderee(groupe["Rendement moyen pondéré (déc.)"],
                                           groupe["Montant retenu (Mds FCFA)"]),
            "Opérations": len(groupe),
        }), include_groups=False).reset_index()
    return agrege[colonnes]


def classes_de_maturite(detail: pd.DataFrame) -> pd.DataFrame:
    """Répartition des montants servis et du coût, par bucket de maturité."""
    colonnes = ["Classe de maturité", "Titres", "Montant retenu (Mds FCFA)",
                "Rendement moyen pondéré"]
    if detail.empty:
        return pd.DataFrame(columns=colonnes)
    travail = detail[detail["Maturité (années)"] > 0].copy()
    if travail.empty:
        return pd.DataFrame(columns=colonnes)
    bornes = [0, 0.5, 1, 2, 3, 5, 7, 10, np.inf]
    libelles = ["≤ 6 mois", "6-12 mois", "1-2 ans", "2-3 ans", "3-5 ans",
                "5-7 ans", "7-10 ans", "> 10 ans"]
    travail["Classe de maturité"] = pd.cut(
        travail["Maturité (années)"], bins=bornes, labels=libelles, right=False)
    agrege = travail.groupby("Classe de maturité", observed=False).apply(
        lambda groupe: pd.Series({
            "Titres": len(groupe),
            "Montant retenu (Mds FCFA)": groupe["Montant retenu (Mds FCFA)"]
            .where(groupe["Montant retenu (Mds FCFA)"] > 0).sum(skipna=True),
            "Rendement moyen pondéré": _moyenne_ponderee(
                groupe["Rendement moyen pondéré (déc.)"],
                groupe["Montant retenu (Mds FCFA)"]),
        }), include_groups=False).reset_index()
    return agrege[colonnes]


def tension(detail: pd.DataFrame) -> pd.DataFrame:
    """Écart entre taux marginal et taux moyen pondéré, en points de base.

    Cet écart mesure la dispersion des offres reçues : plus il est large, plus
    l'émetteur a dû concéder pour remplir son enveloppe. Il n'est renseigné que
    sur 44 % des lignes, la source ne publiant pas systématiquement le taux
    marginal — le décompte accompagne donc toujours la moyenne.
    """
    colonnes = ["Date de l'opération", "Pays", "Instrument", "ISIN",
                "Maturité (années)", "Taux marginal (déc.)",
                "Taux moyen pondéré (déc.)", "Écart marginal / moyen (pb)"]
    if detail.empty:
        return pd.DataFrame(columns=colonnes)
    travail = detail[detail["Taux marginal (déc.)"].notna()
                     & detail["Taux moyen pondéré (déc.)"].notna()].copy()
    if travail.empty:
        return pd.DataFrame(columns=colonnes)
    travail["Écart marginal / moyen (pb)"] = (
        (travail["Taux marginal (déc.)"] - travail["Taux moyen pondéré (déc.)"])
        * 10_000)
    return travail[colonnes].sort_values("Date de l'opération", ascending=False)


def a_venir() -> pd.DataFrame:
    """Opérations annoncées ou planifiées, non encore réalisées."""
    primaire = chargement.emissions_primaire()
    futures = primaire[primaire["Catégorie"].isin(["À venir", "Planifiée"])]
    colonnes = ["Date de l'opération", "Date de valeur", "Pays", "Instrument",
                "Titre n°", "Maturité (années)", "Échéance",
                "Montant mis en adjudication (Mds FCFA)", "Catégorie", "État",
                "Opération", "Lien"]
    presentes = [c for c in colonnes if c in futures.columns]
    return (futures[presentes].sort_values("Date de l'opération")
            .reset_index(drop=True))
