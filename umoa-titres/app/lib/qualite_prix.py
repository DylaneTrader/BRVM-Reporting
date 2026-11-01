# -*- coding: utf-8 -*-
"""Fiabilité des prix du marché secondaire.

Certaines lignes du marché secondaire ne reflètent pas le marché : deux entités
peuvent transiger à un rendement qui n'a rien à voir avec les conditions du
moment. C'est indétectable avec certitude — mais c'est mesurable en écart.

Trois signaux, tous calculables sur les données existantes :

  1. **Écart à la courbe souveraine** — YTM de la transaction contre le taux du
     pays interpolé à la maturité résiduelle. Distribution observée sur les
     6 375 lignes appariables : médiane -37 pb, P5/P95 = -284 / +137 pb.
  2. **Profondeur du print** — 54 % des lignes n'ont qu'une seule transaction
     (30 % du volume). Une ligne unique très écartée n'est pas un prix de
     marché, c'est un transfert.
  3. **Écart à l'adjudication** — via l'ISIN, comparaison au rendement moyen
     pondéré servi sur la même souche au primaire.

Principe non négociable : **aucune ligne n'est supprimée**, elles sont marquées.
Les métriques de marché se déclinent ensuite sur l'univers retenu ou sur
l'univers complet, et l'écart entre les deux versions est en soi un indicateur.

Tous les seuils sont dans `ParametresQualite`, prévu pour être piloté depuis
l'app.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields

import numpy as np
import pandas as pd

from . import chargement, courbes as mod_courbes

SCORE_A = "A — cohérent"
SCORE_B = "B — à surveiller"
SCORE_C = "C — atypique"

ORDRE_SCORES = [SCORE_A, SCORE_B, SCORE_C]
COULEURS_SCORES = {SCORE_A: "#2e7d5b", SCORE_B: "#c98a2e", SCORE_C: "#b23a3a"}


@dataclass(frozen=True)
class ParametresQualite:
    """Seuils de classement. Les défauts découlent de la distribution observée."""

    #: Au-delà de cet écart absolu à la courbe (pb), la ligne passe en B.
    seuil_courbe_b: float = 150.0
    #: Au-delà de celui-ci, elle passe en C.
    seuil_courbe_c: float = 300.0
    #: En-dessous de ce nombre de transactions, la ligne est déclassée d'un cran.
    min_transactions: int = 2
    #: Écart au rendement d'adjudication de la souche (pb) déclassant d'un cran.
    seuil_adjudication: float = 250.0
    #: Ancienneté maximale de l'adjudication comparée (jours). 0 = pas de limite.
    fenetre_adjudication_jours: int = 0
    #: Un volume élevé rend le print plus crédible : au-delà, pas de déclassement
    #: pour cause de profondeur (Mds FCFA). 0 = désactivé.
    volume_credibilisant: float = 1.0

    @classmethod
    def depuis_etat(cls, etat: dict | None) -> "ParametresQualite":
        if not etat:
            return cls()
        connus = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in etat.items() if k in connus})

    def en_dict(self) -> dict:
        return asdict(self)


def _rendements_adjudication() -> pd.DataFrame:
    """Rendement moyen pondéré servi par souche, par date d'opération."""
    primaire = chargement.emissions_primaire()
    colonnes = ["ISIN", "Date de l'opération", "Rendement moyen pondéré (déc.)"]
    extrait = primaire.loc[
        (primaire["Catégorie"] == "Passée")
        & primaire["ISIN"].notna()
        & primaire["Date de l'opération"].notna()
        & primaire["Rendement moyen pondéré (déc.)"].notna(), colonnes]
    return extrait.sort_values("Date de l'opération").reset_index(drop=True)


def evaluer(transactions: pd.DataFrame,
            params: ParametresQualite | None = None,
            niveau_courbe: str = mod_courbes.NIVEAU_OFFICIELLE,
            params_courbe: mod_courbes.ParametresCourbe | None = None
            ) -> pd.DataFrame:
    """Ajoute les trois signaux et le score de fiabilité à des transactions.

    `transactions` doit porter les colonnes du marché secondaire préparé
    (`Pays`, `Date de transaction`, `Maturité résiduelle (années)`, `YTM`,
    `Nombre de transactions`, `Volume global (Mds FCFA)`, `ISIN`).
    """
    params = params or ParametresQualite()
    if transactions.empty:
        return transactions.assign(**{
            "Taux courbe": np.nan, "Écart courbe (pb)": np.nan,
            "Taux adjudication": np.nan, "Écart adjudication (pb)": np.nan,
            "Score": pd.Series(dtype="object"), "Motifs": pd.Series(dtype="object")})

    resultat = transactions.copy()
    interpolateur = mod_courbes.Interpolateur(niveau_courbe, params_courbe)

    # --- Signal 1 : écart à la courbe -------------------------------------
    exploitables = (resultat["Pays"].notna() & resultat["YTM"].notna()
                    & resultat["Maturité résiduelle (années)"].notna())
    resultat["Taux courbe"] = np.nan
    if exploitables.any():
        sous_ensemble = resultat[exploitables]
        resultat.loc[exploitables, "Taux courbe"] = interpolateur.taux_par_ligne(
            sous_ensemble["Pays"], sous_ensemble["Date de transaction"],
            sous_ensemble["Maturité résiduelle (années)"])
    resultat["Écart courbe (pb)"] = (
        (resultat["YTM"] - resultat["Taux courbe"]) * 10_000)

    # --- Signal 3 : écart à l'adjudication de la souche --------------------
    adjudications = _rendements_adjudication()
    resultat["Taux adjudication"] = np.nan
    appariables = resultat["ISIN"].notna() & resultat["Date de transaction"].notna()
    if appariables.any() and not adjudications.empty:
        gauche = (resultat.loc[appariables, ["ISIN", "Date de transaction"]]
                  .reset_index().sort_values("Date de transaction"))
        rapproche = pd.merge_asof(
            gauche, adjudications, by="ISIN",
            left_on="Date de transaction", right_on="Date de l'opération",
            direction="backward",
            tolerance=(pd.Timedelta(days=params.fenetre_adjudication_jours)
                       if params.fenetre_adjudication_jours else None))
        resultat.loc[rapproche["index"], "Taux adjudication"] = (
            rapproche["Rendement moyen pondéré (déc.)"].to_numpy())
    resultat["Écart adjudication (pb)"] = (
        (resultat["YTM"] - resultat["Taux adjudication"]) * 10_000)

    # --- Classement --------------------------------------------------------
    ecart = resultat["Écart courbe (pb)"].abs()
    rang = pd.Series(0, index=resultat.index, dtype=int)
    rang = rang.where(~(ecart > params.seuil_courbe_b), 1)
    rang = rang.where(~(ecart > params.seuil_courbe_c), 2)

    motifs = pd.Series([[] for _ in range(len(resultat))], index=resultat.index)
    motifs[ecart > params.seuil_courbe_b] = motifs[ecart > params.seuil_courbe_b].apply(
        lambda liste: liste + ["écart à la courbe"])

    # Signal 2 : profondeur. Un gros volume rend le print crédible malgré une
    # transaction unique — un transfert de complaisance est rarement massif.
    peu_profond = resultat["Nombre de transactions"].fillna(0) < params.min_transactions
    if params.volume_credibilisant:
        peu_profond &= (resultat["Volume global (Mds FCFA)"].fillna(0)
                        < params.volume_credibilisant)
    # Ne déclasse que ce qui s'écarte déjà : une transaction unique au prix du
    # marché reste une transaction au prix du marché.
    peu_profond &= rang > 0
    rang = rang.where(~peu_profond, (rang + 1).clip(upper=2))
    motifs[peu_profond] = motifs[peu_profond].apply(
        lambda liste: liste + ["transaction isolée"])

    ecart_adjudication = (resultat["Écart adjudication (pb)"].abs()
                          > params.seuil_adjudication)
    ecart_adjudication = ecart_adjudication.fillna(False) & (rang > 0)
    rang = rang.where(~ecart_adjudication, (rang + 1).clip(upper=2))
    motifs[ecart_adjudication] = motifs[ecart_adjudication].apply(
        lambda liste: liste + ["écart à l'adjudication"])

    # Sans courbe de comparaison, on ne prétend pas classer.
    resultat["Score"] = pd.Categorical(
        np.where(resultat["Taux courbe"].isna(), "Non évaluable",
                 np.array(ORDRE_SCORES)[rang]),
        categories=ORDRE_SCORES + ["Non évaluable"], ordered=True)
    resultat["Motifs"] = motifs.apply(lambda liste: ", ".join(liste) or "—")
    resultat.loc[resultat["Taux courbe"].isna(), "Motifs"] = "pas de courbe applicable"
    return resultat


def synthese(transactions: pd.DataFrame) -> pd.DataFrame:
    """Répartition des lignes et du volume par score."""
    if transactions.empty or "Score" not in transactions.columns:
        return pd.DataFrame(columns=["Score", "Lignes", "Volume (Mds FCFA)",
                                     "Part des lignes", "Part du volume"])
    agrege = (transactions.groupby("Score", observed=False)
              .agg(**{"Lignes": ("Score", "size"),
                      "Volume (Mds FCFA)": ("Volume global (Mds FCFA)", "sum")})
              .reset_index())
    agrege["Part des lignes"] = agrege["Lignes"] / agrege["Lignes"].sum()
    total = agrege["Volume (Mds FCFA)"].sum()
    agrege["Part du volume"] = agrege["Volume (Mds FCFA)"] / total if total else np.nan
    return agrege


def univers_retenu(transactions: pd.DataFrame) -> pd.DataFrame:
    """Transactions hors lignes classées atypiques (score C)."""
    if "Score" not in transactions.columns:
        return transactions
    return transactions[transactions["Score"] != SCORE_C]
