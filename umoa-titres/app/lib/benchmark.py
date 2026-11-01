# -*- coding: utf-8 -*-
"""Benchmark obligataire CGF : indice composite 30 % coté / 70 % non coté.

Construit par `scripts/construire_benchmark.py`, base 100 au 31/12/2019. Le
classeur porte plus que la série mensuelle : performances annuelles avec
volatilité, taux de référence par classe de maturité, et détail quotidien de
l'indice non coté.

Les limites méthodologiques connues sont reprises dans `LIMITES` — elles sont
affichées dans l'app plutôt que reléguées dans un document annexe, parce
qu'elles conditionnent la lecture de toute mesure de risque dérivée de l'indice.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .chargement import DOSSIER_BENCHMARK, _cache

CHEMIN_CLASSEUR = DOSSIER_BENCHMARK / "benchmark_obligataire.xlsx"

INDICES = {
    "Indice obligataire (30/70)": "#1f6f8b",
    "Indice coté": "#c98a2e",
    "Indice non coté": "#2e7d5b",
}

#: Limites documentées dans `Limites_Methodologie_Benchmark_Obligataire.md`.
LIMITES = [
    ("Équipondération de l'indice coté",
     "Chaque ligne pèse 1/N quel que soit son encours. Un portefeuille réel ne "
     "peut pas répliquer cette structure à coût nul, et c'est incohérent avec "
     "le BRVM Composite, pondéré par capitalisation.",
     "Pondérer par l'encours en circulation — désormais calculable, l'encours "
     "étant documenté pour 1 350 titres dans le référentiel."),
    ("Absence d'effet prix dans l'indice non coté",
     "Le rendement n'est calculé qu'au premier jour ouvré du mois, à partir du "
     "seul incrément de coupon couru. Entre deux rééquilibrages, l'indice se "
     "comporte comme du carry pur, sans risque de duration.",
     "Toute mesure de risque dérivée (tracking error, duration implicite, DV01 "
     "de référence) est structurellement biaisée : risque sous-estimé la "
     "majeure partie du mois, surestimé le jour du reset."),
    ("Granularité du dernier bucket de maturité",
     "Le découpage est fin par tranches de 3 mois jusqu'à 7 ans, puis un seul "
     "bucket regroupe 7 à 15 ans.",
     "Une obligation à 8 ans et une à 15 ans reçoivent le même taux de "
     "référence, alors que leur sensibilité diffère fortement."),
    ("Pondération 30/70 fixe pour tous les fonds",
     "La même clé est appliquée quelle que soit l'exposition réelle du fonds "
     "entre coté et gré à gré.",
     "Génère une tracking error indépendante de la performance du gérant. "
     "Définir les poids par fonds, comme c'est déjà fait pour la clé "
     "action/obligation."),
    ("Absence de méthode de chaînage explicite",
     "Rien ne précise comment l'indice coté est ajusté quand le nombre de "
     "lignes change.",
     "Une entrée ou une sortie de ligne modifie mécaniquement le poids 1/N de "
     "toutes les autres, ce qui peut introduire un saut de rendement non "
     "économique."),
]


@_cache
def serie() -> pd.DataFrame:
    """Série mensuelle des trois indices et de leurs rendements."""
    chemin = DOSSIER_BENCHMARK / "benchmark_obligataire.csv"
    if not chemin.exists():
        return pd.DataFrame()
    donnees = pd.read_csv(chemin, encoding="utf-8", parse_dates=["Date"])
    donnees["Coté disponible"] = donnees["Rendement coté"].notna()
    return donnees.sort_values("Date").reset_index(drop=True)


@_cache
def _feuille(nom: str) -> pd.DataFrame:
    """Lit une feuille du classeur, ou renvoie un cadre vide s'il est absent."""
    if not CHEMIN_CLASSEUR.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(CHEMIN_CLASSEUR, sheet_name=nom)
    except (ValueError, KeyError):
        return pd.DataFrame()


def performances() -> pd.DataFrame:
    """Performance et volatilité annualisée, par indice et par année."""
    return _feuille("Performances")


def taux_par_classe() -> pd.DataFrame:
    """Taux de référence mensuel par classe de maturité (29 classes)."""
    return _feuille("Taux par classe")


def detail_quotidien() -> pd.DataFrame:
    """Série quotidienne de l'indice non coté."""
    return _feuille("Détail quotidien")


def methodologie() -> pd.DataFrame:
    """Fiche de méthodologie embarquée dans le classeur.

    La colonne `Détail` mélange dates, nombres et texte : elle est ramenée en
    chaînes, faute de quoi la sérialisation Arrow de l'affichage échoue.
    """
    fiche = _feuille("Méthodologie")
    if fiche.empty:
        return fiche
    return fiche.astype(str)


def resume(donnees: pd.DataFrame) -> dict:
    """Niveaux, performances et couverture sur la période affichée."""
    if donnees.empty:
        return {}
    debut, fin = donnees.iloc[0], donnees.iloc[-1]
    mois = len(donnees) - 1
    resultat = {
        "Date de début": debut["Date"],
        "Date de fin": fin["Date"],
        "Mois observés": mois,
        "Mois sans cotation BRVM": int((~donnees["Coté disponible"]).sum()),
        "Lignes cotées (dernier mois)": (
            float(fin["Lignes cotées"]) if pd.notna(fin["Lignes cotées"])
            else float("nan")),
    }
    for indice in INDICES:
        depart, arrivee = debut[indice], fin[indice]
        performance = (arrivee / depart - 1) if depart else np.nan
        resultat[f"{indice} — niveau"] = arrivee
        resultat[f"{indice} — performance"] = performance
        resultat[f"{indice} — annualisée"] = (
            (1 + performance) ** (12 / mois) - 1 if mois > 0 and pd.notna(performance)
            else np.nan)
    return resultat


def rendements_mensuels(donnees: pd.DataFrame) -> pd.DataFrame:
    """Rendements mensuels des trois indices, format long."""
    colonnes = {"Rendement obligataire": "Indice obligataire (30/70)",
                "Rendement coté": "Indice coté",
                "Rendement non coté": "Indice non coté"}
    presentes = [c for c in colonnes if c in donnees.columns]
    if donnees.empty or not presentes:
        return pd.DataFrame(columns=["Date", "Indice", "Rendement"])
    longue = donnees.melt(id_vars="Date", value_vars=presentes,
                          var_name="Colonne", value_name="Rendement")
    longue["Indice"] = longue["Colonne"].map(colonnes)
    return longue.dropna(subset=["Rendement"])[["Date", "Indice", "Rendement"]]


def contributions(donnees: pd.DataFrame, poids_cote: float = 0.30) -> pd.DataFrame:
    """Décomposition du rendement composite entre ses deux jambes.

    Quand le bulletin BRVM manque, le composite se replie sur le seul non coté :
    la contribution du coté est alors nulle par construction, ce que la colonne
    `Repli` signale explicitement.
    """
    if donnees.empty:
        return pd.DataFrame(columns=["Date", "Contribution cotée",
                                     "Contribution non cotée", "Repli"])
    resultat = pd.DataFrame({"Date": donnees["Date"]})
    disponible = donnees["Coté disponible"]
    resultat["Contribution cotée"] = np.where(
        disponible, donnees["Rendement coté"].fillna(0) * poids_cote, 0.0)
    resultat["Contribution non cotée"] = np.where(
        disponible, donnees["Rendement non coté"] * (1 - poids_cote),
        donnees["Rendement non coté"])
    resultat["Repli"] = ~disponible
    return resultat
