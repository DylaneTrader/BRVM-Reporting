# -*- coding: utf-8 -*-
"""Risque de taux : sensibilité de l'univers obligataire aux mouvements de courbe.

Deux partis pris, l'un et l'autre rendus possibles par le référentiel :

  * **pondération par l'encours, jamais par le volume échangé.** Le volume est
    biaisé par les prints atypiques et par la concentration du secondaire sur
    quelques souches ; l'encours mesure l'exposition réellement portée.
  * **choc appliqué à la courbe, pas au rendement de chaque ligne.** On déforme
    la courbe souveraine puis on revalorise, plutôt que d'appliquer un delta
    uniforme à des YTM d'âges hétérogènes.

L'approximation reste celle de l'ordre 2 (duration modifiée et convexité), qui
est exactement ce que `scripts/finance.py` calcule ligne à ligne.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

#: Scénarios standards, en points de base.
SCENARIOS_PARALLELES = (-200, -100, -50, 0, 50, 100, 200)

CLASSES_MATURITE = (
    [0, 1, 2, 3, 5, 7, 10, 15, np.inf],
    ["≤ 1 an", "1-2 ans", "2-3 ans", "3-5 ans", "5-7 ans", "7-10 ans",
     "10-15 ans", "> 15 ans"],
)


@dataclass(frozen=True)
class Deformation:
    """Choc de courbe : translation, pentification et pivot.

    `pivot` est la maturité autour de laquelle la pentification s'applique :
    au-delà, le choc est amplifié ; en deçà, atténué.
    """

    parallele_pb: float = 0.0
    pentification_pb: float = 0.0
    pivot_annees: float = 5.0

    def choc(self, maturites) -> np.ndarray:
        """Variation de taux, en décimal, pour un vecteur de maturités."""
        maturites = np.asarray(maturites, dtype=float)
        pente = 0.0
        if self.pentification_pb:
            pente = (self.pentification_pb
                     * (maturites - self.pivot_annees) / self.pivot_annees)
        return (self.parallele_pb + pente) / 10_000.0


def perimetre(titres: pd.DataFrame) -> pd.DataFrame:
    """Titres exploitables pour le risque : vivants, avec encours et duration."""
    if titres.empty:
        return titres
    retenus = titres[(titres["Statut"] == "Vivant")
                     & titres["Encours connu"]
                     & titres["Duration modifiée"].notna()
                     & titres["Maturité résiduelle (années)"].notna()].copy()
    bornes, libelles = CLASSES_MATURITE
    retenus["Classe de maturité"] = pd.cut(
        retenus["Maturité résiduelle (années)"], bins=bornes, labels=libelles,
        right=False)
    return retenus


def couverture(titres: pd.DataFrame) -> dict:
    """Part de l'univers effectivement couverte par la mesure de risque.

    La duration n'existe que pour les titres ayant négocié au moins une fois :
    la page doit dire sur quoi elle calcule avant de dire ce qu'elle calcule.
    """
    vivants = titres[titres["Statut"] == "Vivant"] if not titres.empty else titres
    retenus = perimetre(titres)
    encours_vivant = vivants["Encours (Mds FCFA)"].sum(skipna=True) if len(vivants) else 0.0
    encours_retenu = retenus["Encours (Mds FCFA)"].sum(skipna=True) if len(retenus) else 0.0
    return {
        "Titres vivants": int(len(vivants)),
        "Titres couverts": int(len(retenus)),
        "Encours vivant (Mds FCFA)": float(encours_vivant),
        "Encours couvert (Mds FCFA)": float(encours_retenu),
        "Couverture en nombre": (len(retenus) / len(vivants)) if len(vivants) else np.nan,
        "Couverture en encours": (encours_retenu / encours_vivant
                                  if encours_vivant else np.nan),
    }


def _pondere(donnees: pd.DataFrame, colonne: str) -> float:
    poids = donnees["Encours (Mds FCFA)"]
    valeurs = donnees[colonne]
    valides = valeurs.notna() & poids.notna() & (poids > 0)
    if not valides.any():
        return float("nan")
    return float(np.average(valeurs[valides], weights=poids[valides]))


def indicateurs(donnees: pd.DataFrame) -> dict:
    """Sensibilités agrégées, pondérées par l'encours."""
    if donnees.empty:
        return {}
    encours = donnees["Encours (Mds FCFA)"].sum(skipna=True)
    duration = _pondere(donnees, "Duration modifiée")
    return {
        "Encours (Mds FCFA)": float(encours),
        "Titres": int(len(donnees)),
        "Duration modifiée": duration,
        "Duration Macaulay": _pondere(donnees, "Duration Macaulay"),
        "Convexité": _pondere(donnees, "Convexité"),
        "Maturité résiduelle": _pondere(donnees, "Maturité résiduelle (années)"),
        "Coupon moyen": _pondere(donnees, "Coupon"),
        # DV01 du portefeuille : perte de valeur pour 1 pb de hausse, en Mds.
        "DV01 (Mds FCFA / pb)": (encours * duration / 10_000
                                 if not pd.isna(duration) else float("nan")),
    }


def impact(donnees: pd.DataFrame, deformation: Deformation) -> pd.DataFrame:
    """Variation de valeur par titre pour une déformation de courbe donnée.

    Approximation d'ordre 2 :  ΔP/P = −D* · Δy + ½ · C · Δy².
    La convexité manquante est traitée comme nulle, ce qui rend l'estimation
    légèrement pessimiste à la hausse des taux plutôt qu'optimiste.
    """
    if donnees.empty:
        return donnees.assign(**{"Choc (pb)": [], "Variation (%)": [],
                                 "Impact (Mds FCFA)": []})
    resultat = donnees.copy()
    delta = deformation.choc(resultat["Maturité résiduelle (années)"])
    duration = resultat["Duration modifiée"].to_numpy(dtype=float)
    convexite = resultat["Convexité"].fillna(0.0).to_numpy(dtype=float)
    variation = -duration * delta + 0.5 * convexite * delta ** 2
    resultat["Choc (pb)"] = delta * 10_000
    resultat["Variation (%)"] = variation
    resultat["Impact (Mds FCFA)"] = variation * resultat["Encours (Mds FCFA)"]
    return resultat


def table_scenarios(donnees: pd.DataFrame,
                    chocs=SCENARIOS_PARALLELES,
                    pentification_pb: float = 0.0,
                    pivot_annees: float = 5.0) -> pd.DataFrame:
    """Impact agrégé pour une série de chocs parallèles."""
    lignes = []
    encours = donnees["Encours (Mds FCFA)"].sum(skipna=True) if not donnees.empty else 0.0
    for choc in chocs:
        detail = impact(donnees, Deformation(choc, pentification_pb, pivot_annees))
        total = detail["Impact (Mds FCFA)"].sum(skipna=True)
        lignes.append({
            "Choc parallèle (pb)": choc,
            "Impact (Mds FCFA)": total,
            "Impact (%)": total / encours if encours else np.nan,
        })
    return pd.DataFrame(lignes)


def contributions(donnees: pd.DataFrame, cle: str,
                  deformation: Deformation) -> pd.DataFrame:
    """Décomposition du risque par pays, classe de maturité ou instrument."""
    colonnes = [cle, "Titres", "Encours (Mds FCFA)", "Duration modifiée",
                "Impact (Mds FCFA)", "Part du risque"]
    if donnees.empty or cle not in donnees.columns:
        return pd.DataFrame(columns=colonnes)
    detail = impact(donnees, deformation)
    agrege = detail.groupby(cle, observed=False).apply(
        lambda groupe: pd.Series({
            "Titres": len(groupe),
            "Encours (Mds FCFA)": groupe["Encours (Mds FCFA)"].sum(skipna=True),
            "Duration modifiée": _pondere(groupe, "Duration modifiée"),
            "Impact (Mds FCFA)": groupe["Impact (Mds FCFA)"].sum(skipna=True),
        }), include_groups=False).reset_index()
    total = agrege["Impact (Mds FCFA)"].abs().sum()
    agrege["Part du risque"] = (agrege["Impact (Mds FCFA)"].abs() / total
                                if total else np.nan)
    return agrege[colonnes].sort_values("Impact (Mds FCFA)").reset_index(drop=True)
