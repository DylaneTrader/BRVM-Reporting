# -*- coding: utf-8 -*-
"""Référentiel des titres : la dimension qui manquait au dispositif.

Les cinq jeux de données sont aujourd'hui des îlots reliés uniquement par la
date. Ce module construit la table qui les relie, au grain d'un titre :

    primaire  --ISIN-->  secondaire  --(pays, coupon, millésime)-->  BRVM

Couvertures mesurées sur les données du dépôt :
  * 1 291 ISIN communs primaire/secondaire, soit 96,5 % du volume secondaire ;
  * 268 des 269 lignes BRVM sont rapprochables par parsing du libellé ;
  * l'encours est renseigné à 100 % pour les 1 350 ISIN ayant traité.

C'est cette table qui rend possibles la fiche titre, la répartition coté /
non coté, le taux de rotation et la détection des prix hors marché — quatre
choses impossibles tant que les sources restent disjointes.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import chargement, courbes as mod_courbes
from .chargement import SEGMENT_PRIVE, SEGMENT_SOUVERAIN, cle_pays, sans_accents

#: Préfixes de libellés BRVM qui ne contiennent pas le nom du pays en clair.
CODES_TRESOR = {
    "tpci": "Côte d'Ivoire", "tpbj": "Bénin", "tptg": "Togo",
    "tpbf": "Burkina Faso", "tpsn": "Sénégal", "tpml": "Mali",
    "tpne": "Niger", "tpgb": "Guinée-Bissau",
}

_MOTIF_LIBELLE_BRVM = re.compile(
    r"(?P<taux>\d{1,2}(?:[.,]\d{1,3})?)\s*%\s*(?P<emission>\d{4})\s*-\s*(?P<echeance>\d{4})")

#: Tolérance d'appariement BRVM sur le taux facial (en décimal).
TOLERANCE_COUPON = 0.0005


def _pays_depuis_libelle_brvm(nom: str) -> str | None:
    """Retrouve l'émetteur souverain derrière un libellé BRVM."""
    pays = cle_pays(nom)
    if pays:
        return pays
    t = sans_accents(nom)
    for code, valeur in CODES_TRESOR.items():
        if t.startswith(code) or f" {code} " in f" {t} ":
            return valeur
    return None


# --------------------------------------------------------------------------
# Agrégats par source
# --------------------------------------------------------------------------
def _agreger_primaire() -> pd.DataFrame:
    """Un titre par ISIN, toutes tranches de réabondement confondues.

    2 538 ISIN pour 3 950 lignes : une souche peut être rouverte une dizaine de
    fois. La date d'émission retenue est celle de la première tranche, le taux
    d'adjudication est pondéré par les montants retenus.
    """
    primaire = chargement.emissions_primaire()
    passees = primaire[(primaire["Catégorie"] == "Passée")
                       & primaire["ISIN"].notna()].copy()
    if passees.empty:
        return pd.DataFrame()

    montant = pd.to_numeric(passees["Montant retenu (millions FCFA)"], errors="coerce")
    # 14,2 % des montants retenus sont négatifs dans la source : on les neutralise
    # pour les agrégats mais on conserve le compte pour la page Qualité.
    passees["_montant_valide"] = montant.where(montant > 0)
    passees["_montant_anormal"] = (montant <= 0).astype(int)
    passees["_poids"] = passees["_montant_valide"].fillna(0.0)

    def _resume(groupe: pd.DataFrame) -> pd.Series:
        poids = groupe["_poids"]
        poids = poids if poids.sum() > 0 else pd.Series(1.0, index=groupe.index)
        taux = groupe["Rendement moyen pondéré (déc.)"]
        valides = taux.notna()
        return pd.Series({
            "Pays": groupe["Pays"].dropna().iloc[0] if groupe["Pays"].notna().any() else None,
            "Instrument": (groupe["Instrument"].dropna().iloc[0]
                           if groupe["Instrument"].notna().any() else None),
            "Date d'émission": groupe["Date de valeur"].min(),
            "Échéance": groupe["Échéance"].max(),
            "Coupon primaire": groupe["Taux d'intérêt (déc.)"].dropna().iloc[0]
            if groupe["Taux d'intérêt (déc.)"].notna().any() else np.nan,
            "Amortissement primaire": (groupe["Type d'amortissement"].dropna().iloc[0]
                                       if groupe["Type d'amortissement"].notna().any() else None),
            "Nb tranches": len(groupe),
            "Montant levé (Mds FCFA)": groupe["_montant_valide"].sum() / 1_000.0,
            "Taux d'adjudication moyen": (
                np.average(taux[valides], weights=poids[valides])
                if valides.any() and poids[valides].sum() > 0 else np.nan),
            "Dernière adjudication": groupe["Date de l'opération"].max(),
            "Taux dernière adjudication": (
                groupe.sort_values("Date de l'opération")["Rendement moyen pondéré (déc.)"]
                .dropna().iloc[-1] if valides.any() else np.nan),
            "Taux de couverture moyen": pd.to_numeric(
                groupe["Taux de couverture"], errors="coerce").mean(),
            "Montants anormaux": int(groupe["_montant_anormal"].sum()),
        })

    return passees.groupby("ISIN").apply(_resume, include_groups=False)


def _agreger_secondaire() -> pd.DataFrame:
    """Une ligne par ISIN : caractéristiques du titre et dernière observation."""
    secondaire = chargement.marche_secondaire()
    negocies = secondaire[secondaire["ISIN"].notna()].copy()
    if negocies.empty:
        return pd.DataFrame()
    negocies = negocies.sort_values("Date de transaction")

    def _resume(groupe: pd.DataFrame) -> pd.Series:
        derniere = groupe.iloc[-1]
        return pd.Series({
            "Pays secondaire": derniere["Pays"],
            "Instrument secondaire": derniere["Instrument"],
            "Coupon": derniere["Coupon"],
            "Échéance secondaire": derniere["Date d'échéance"],
            "Mode amortissement": derniere["Mode amortissement"],
            "Encours (FCFA)": derniere["Encours"],
            "Méthode de calcul": derniere["Méthode"],
            "Nb séances négociées": len(groupe),
            "Volume échangé (Mds FCFA)": groupe["Volume global (Mds FCFA)"].sum(),
            "Dernière négociation": derniere["Date de transaction"],
            "Dernier prix secondaire": derniere["Prix moyen"],
            "Dernier YTM": derniere["YTM"],
            "Duration modifiée": derniere["Duration modifiée"],
            "Duration Macaulay": derniere["Duration Macaulay"],
            "Convexité": derniere["Convexité"],
            "DV01 (FCFA / M nominal)": derniere.get("DV01 (FCFA / M nominal)"),
            "Maturité résiduelle observée": derniere["Maturité résiduelle (années)"],
        })

    return negocies.groupby("ISIN").apply(_resume, include_groups=False)


def cotations_brvm_recentes() -> pd.DataFrame:
    """Dernière séance BRVM disponible, une ligne par code obligation."""
    brvm = chargement.brvm_obligations()
    if brvm.empty:
        return brvm
    derniere = brvm["Date de cotation"].max()
    seance = brvm[brvm["Date de cotation"] == derniere].copy()

    extrait = seance["Nom"].str.extract(_MOTIF_LIBELLE_BRVM)
    seance["Taux facial libellé"] = (
        pd.to_numeric(extrait["taux"].str.replace(",", ".", regex=False),
                      errors="coerce") / 100.0)
    seance["Année émission libellé"] = pd.to_numeric(extrait["emission"], errors="coerce")
    seance["Année échéance libellé"] = pd.to_numeric(extrait["echeance"], errors="coerce")
    seance["Pays BRVM"] = seance["Nom"].map(_pays_depuis_libelle_brvm)
    seance.loc[seance["Segment"] != SEGMENT_SOUVERAIN, "Pays BRVM"] = None
    return seance


def apparier_brvm(titres: pd.DataFrame, seance: pd.DataFrame) -> pd.DataFrame:
    """Table de correspondance BRVM <-> ISIN.

    La BRVM ne publie pas d'ISIN : le rapprochement passe par le libellé, qui
    porte l'émetteur, le taux facial et le millésime (« ETAT DU MALI 6,55 %
    2025-2032 »). On exige les trois pour éviter les faux positifs entre souches
    voisines, et on laisse délibérément non apparié ce qui est ambigu — un titre
    faussement rattaché est pire qu'un titre non rattaché.

    Le taux d'appariement est structurellement faible (11 exacts sur 198 lignes
    souveraines) et ce n'est pas un défaut de la méthode : les souverains cotés
    à la BRVM sont massivement issus d'appels publics à l'épargne et de
    syndications, un canal distinct des adjudications couvertes par
    UMOA-Titres. « ETAT DU MALI 6,50 % 2024-2034 » n'a aucune contrepartie
    possible : aucun titre malien d'adjudication n'arrive à échéance en 2034.
    Les deux univers se recoupent à la marge — d'où la pertinence de la
    distinction coté / non coté plutôt que d'un univers unique.
    """
    colonnes = ["Code obligation", "ISIN", "Score appariement"]
    souverains = seance[seance["Segment"] == SEGMENT_SOUVERAIN] if not seance.empty \
        else pd.DataFrame()
    if souverains.empty or titres.empty:
        return pd.DataFrame(columns=colonnes)

    candidats = titres[titres["Coupon"].notna()
                       & titres["Date d'émission"].notna()
                       & titres["Échéance"].notna()].copy()
    candidats["_an_emission"] = candidats["Date d'émission"].dt.year
    candidats["_an_echeance"] = candidats["Échéance"].dt.year

    liens = []
    for _, ligne in souverains.iterrows():
        pays, taux = ligne["Pays BRVM"], ligne["Taux facial libellé"]
        an_e, an_m = ligne["Année émission libellé"], ligne["Année échéance libellé"]
        if not pays or pd.isna(taux) or pd.isna(an_e) or pd.isna(an_m):
            continue
        masque = (
            (candidats["Pays"] == pays)
            & (candidats["Coupon"] - taux).abs().le(TOLERANCE_COUPON)
            & candidats["_an_emission"].between(an_e - 1, an_e + 1)
            & (candidats["_an_echeance"] == an_m)
        )
        retenus = candidats[masque]
        if len(retenus) != 1:
            # 0 = pas de souche connue ; >1 = ambiguïté, on préfère s'abstenir.
            liens.append({"Code obligation": ligne["Code obligation"], "ISIN": None,
                          "Score appariement": "Ambigu" if len(retenus) else "Sans correspondance"})
            continue
        liens.append({"Code obligation": ligne["Code obligation"],
                      "ISIN": retenus.index[0], "Score appariement": "Exact"})
    return pd.DataFrame(liens, columns=colonnes)


# --------------------------------------------------------------------------
# Référentiel
# --------------------------------------------------------------------------
def construire_referentiel(params: mod_courbes.ParametresCourbe | None = None,
                           niveau_courbe: str = mod_courbes.NIVEAU_OFFICIELLE
                           ) -> pd.DataFrame:
    """Table des titres, un enregistrement par titre.

    Clé `Identifiant` : l'ISIN quand il existe, sinon `BRVM:<code>` pour les
    lignes cotées non rapprochées (notamment les émetteurs privés, qui n'ont
    jamais d'ISIN dans nos sources mais font partie de l'univers obligataire).
    """
    params = params or mod_courbes.ParametresCourbe()
    reference = chargement.date_reference()

    primaire = _agreger_primaire()
    secondaire = _agreger_secondaire()
    titres = primaire.join(secondaire, how="outer") if not primaire.empty \
        else secondaire.copy()
    titres.index.name = "ISIN"

    # Réconciliation des attributs présents dans les deux sources : le primaire
    # fait foi sur l'identité du titre, le secondaire complète les trous.
    titres["Pays"] = titres.get("Pays").fillna(titres.get("Pays secondaire")) \
        if "Pays" in titres else titres.get("Pays secondaire")
    titres["Instrument"] = titres.get("Instrument").fillna(
        titres.get("Instrument secondaire"))
    titres["Échéance"] = titres.get("Échéance").fillna(titres.get("Échéance secondaire"))
    titres["Coupon"] = titres.get("Coupon").fillna(titres.get("Coupon primaire"))
    titres["Amortissement"] = titres.get("Amortissement primaire").fillna(
        titres.get("Mode amortissement"))

    titres["Origine"] = np.select(
        [titres["Nb tranches"].notna() & titres["Nb séances négociées"].notna(),
         titres["Nb tranches"].notna()],
        ["Primaire + secondaire", "Primaire seul"], default="Secondaire seul")

    titres["Segment"] = SEGMENT_SOUVERAIN
    titres = titres.reset_index()
    titres["Identifiant"] = titres["ISIN"]

    # --- Rattachement BRVM -------------------------------------------------
    seance = cotations_brvm_recentes()
    liens = apparier_brvm(titres.set_index("ISIN"), seance)
    apparies = liens[liens["ISIN"].notna()]
    if not seance.empty:
        cotations = seance.merge(liens, on="Code obligation", how="left")
        colonnes_brvm = {
            "Code obligation": "Code BRVM", "Nom": "Libellé BRVM",
            "Cours du jour": "Cours BRVM", "Coupon couru": "Coupon couru BRVM",
            "Date de cotation": "Date cotation BRVM", "Taux facial": "Taux facial BRVM",
        }
        rattachees = (cotations[cotations["ISIN"].notna()]
                      [list(colonnes_brvm) + ["ISIN"]].rename(columns=colonnes_brvm))
        titres = titres.merge(rattachees, on="ISIN", how="left")

        # Lignes cotées sans ISIN retrouvé : elles entrent au référentiel telles
        # quelles, sinon la répartition coté / non coté serait fausse.
        orphelines = cotations[cotations["ISIN"].isna()].copy()
        if not orphelines.empty:
            # Le bulletin ne renseigne pas la date de maturité : le millésime du
            # libellé (« … 2024-2034 ») est la seule échéance disponible. Fin
            # d'année par convention, marquée comme estimée.
            echeance = pd.to_datetime(
                orphelines["Année échéance libellé"].dropna().astype(int).astype(str)
                + "-12-31", errors="coerce").reindex(orphelines.index)
            orphelines["_echeance"] = orphelines["Date de maturité"].fillna(echeance)
            orphelines["_echeance_estimee"] = orphelines["Date de maturité"].isna()
            emission = pd.to_datetime(
                orphelines["Année émission libellé"].dropna().astype(int).astype(str)
                + "-01-01", errors="coerce").reindex(orphelines.index)
            ajout = pd.DataFrame({
                "Identifiant": "BRVM:" + orphelines["Code obligation"].astype(str),
                "ISIN": None,
                "Pays": orphelines["Pays BRVM"],
                "Instrument": "Obligation cotée",
                "Coupon": orphelines["Taux facial"],
                "Date d'émission": orphelines["Date d'émission"].fillna(emission),
                "Échéance": orphelines["_echeance"],
                "Échéance estimée": orphelines["_echeance_estimee"],
                "Segment": orphelines["Segment"],
                "Origine": "BRVM seul",
                "Code BRVM": orphelines["Code obligation"],
                "Libellé BRVM": orphelines["Nom"],
                "Cours BRVM": orphelines["Cours du jour"],
                "Coupon couru BRVM": orphelines["Coupon couru"],
                "Date cotation BRVM": orphelines["Date de cotation"],
                "Taux facial BRVM": orphelines["Taux facial"],
            })
            titres = pd.concat([titres, ajout], ignore_index=True)
    else:
        for colonne in ("Code BRVM", "Libellé BRVM", "Cours BRVM",
                        "Coupon couru BRVM", "Date cotation BRVM", "Taux facial BRVM"):
            titres[colonne] = np.nan

    titres["Coté"] = titres["Code BRVM"].notna()
    if "Échéance estimée" not in titres.columns:
        titres["Échéance estimée"] = False
    titres["Échéance estimée"] = titres["Échéance estimée"].fillna(False).astype(bool)

    # --- Attributs calculés ------------------------------------------------
    titres["Maturité résiduelle (années)"] = (
        (titres["Échéance"] - reference).dt.days / 365.25)
    titres["Statut"] = np.where(
        titres["Échéance"].isna(), "Échéance inconnue",
        np.where(titres["Maturité résiduelle (années)"] > 0, "Vivant", "Échu"))
    titres["Encours (Mds FCFA)"] = titres["Encours (FCFA)"] / 1e9
    # À défaut d'encours observé au secondaire, le cumul des montants levés en
    # adjudication en est la meilleure approximation. Les lignes cotées non
    # rapprochées n'ont ni l'un ni l'autre : leur encours reste inconnu, et il
    # doit le rester — le mettre à zéro fausserait toutes les pondérations.
    titres["Encours (Mds FCFA)"] = titres["Encours (Mds FCFA)"].fillna(
        titres["Montant levé (Mds FCFA)"])
    titres["Encours estimé"] = (titres["Encours (FCFA)"].isna()
                                & titres["Encours (Mds FCFA)"].notna())
    titres["Encours connu"] = titres["Encours (Mds FCFA)"].notna()

    # Émetteurs supranationaux et privés cotés (BOAD, CRRH-UEMOA, BIDC...) :
    # ils n'ont pas de pays UEMOA, ce qui n'est pas une donnée manquante.
    titres["Pays"] = titres["Pays"].fillna(
        pd.Series(np.where(titres["Segment"] == SEGMENT_PRIVE,
                           "Supranational / Privé", None), index=titres.index))

    titres = _ajouter_prix_de_reference(titres, reference)
    titres = _ajouter_ecart_courbe(titres, reference, niveau_courbe, params)

    colonnes = [
        "Identifiant", "ISIN", "Code BRVM", "Libellé BRVM", "Segment", "Pays",
        "Instrument", "Statut", "Coté", "Coupon", "Date d'émission", "Échéance",
        "Échéance estimée", "Maturité résiduelle (années)", "Amortissement",
        "Encours (Mds FCFA)", "Encours estimé", "Encours connu",
        "Nb tranches", "Montant levé (Mds FCFA)",
        "Taux d'adjudication moyen", "Taux dernière adjudication",
        "Dernière adjudication", "Taux de couverture moyen", "Nb séances négociées",
        "Volume échangé (Mds FCFA)", "Dernière négociation", "Dernier prix secondaire",
        "Dernier YTM", "Duration modifiée", "Duration Macaulay", "Convexité",
        "DV01 (FCFA / M nominal)", "Méthode de calcul", "Cours BRVM",
        "Coupon couru BRVM", "Date cotation BRVM", "Prix de référence",
        "Source du prix", "Date du prix", "Âge du prix (jours)",
        "Taux courbe (maturité)", "Écart YTM / courbe (pb)", "Origine",
        "Montants anormaux",
    ]
    for colonne in colonnes:
        if colonne not in titres.columns:
            titres[colonne] = np.nan
    return (titres[colonnes]
            .sort_values(["Segment", "Pays", "Échéance"], na_position="last")
            .reset_index(drop=True))


def _ajouter_prix_de_reference(titres: pd.DataFrame,
                               reference: pd.Timestamp) -> pd.DataFrame:
    """Prix le plus récent disponible et sa provenance.

    Ordre de préférence : cotation BRVM du jour, puis dernier prix secondaire,
    puis dernier prix d'adjudication. L'âge du prix est affiché systématiquement :
    un prix de six mois n'a pas le même statut qu'un prix de la veille.
    """
    cours = pd.to_numeric(titres["Cours BRVM"], errors="coerce")
    # La BRVM cote en FCFA sur un nominal de 10 000 : ramené en pourcentage du pair.
    prix_brvm = np.where(cours > 200, cours / 10_000.0, cours / 100.0)
    prix_brvm = pd.Series(prix_brvm, index=titres.index).where(cours.notna())

    conditions = [prix_brvm.notna(),
                  titres["Dernier prix secondaire"].notna(),
                  titres["Taux dernière adjudication"].notna()]
    titres["Prix de référence"] = np.select(
        conditions, [prix_brvm, titres["Dernier prix secondaire"], np.nan],
        default=np.nan)
    titres["Source du prix"] = np.select(
        conditions, ["Cotation BRVM", "Marché secondaire", "Adjudication"],
        default="Aucun prix")
    titres["Date du prix"] = pd.to_datetime(np.select(
        conditions,
        [titres["Date cotation BRVM"], titres["Dernière négociation"],
         titres["Dernière adjudication"]], default=np.datetime64("NaT")))
    titres["Âge du prix (jours)"] = (reference - titres["Date du prix"]).dt.days
    return titres


def _ajouter_ecart_courbe(titres: pd.DataFrame, reference: pd.Timestamp,
                          niveau: str,
                          params: mod_courbes.ParametresCourbe) -> pd.DataFrame:
    """Écart entre le dernier YTM observé et la courbe du pays à même maturité.

    Premier des trois signaux de fiabilité de prix : le titre se traite-t-il là
    où la courbe souveraine dit qu'il devrait se traiter ? Un écart isolé n'est
    pas une preuve, mais il oriente l'examen.
    """
    interpolateur = mod_courbes.Interpolateur(niveau, params)
    exploitables = titres[titres["Pays"].notna()
                          & titres["Dernier YTM"].notna()
                          & titres["Maturité résiduelle observée"].notna()
                          & titres["Dernière négociation"].notna()] \
        if "Maturité résiduelle observée" in titres.columns else titres.iloc[0:0]

    titres["Taux courbe (maturité)"] = np.nan
    titres["Écart YTM / courbe (pb)"] = np.nan
    if exploitables.empty:
        return titres

    taux = interpolateur.taux_par_ligne(
        exploitables["Pays"], exploitables["Dernière négociation"],
        exploitables["Maturité résiduelle observée"])
    titres.loc[exploitables.index, "Taux courbe (maturité)"] = taux
    titres.loc[exploitables.index, "Écart YTM / courbe (pb)"] = (
        (exploitables["Dernier YTM"].to_numpy() - taux) * 10_000)
    return titres


# --------------------------------------------------------------------------
# Synthèse
# --------------------------------------------------------------------------
def resume(titres: pd.DataFrame) -> dict:
    """Indicateurs de tête du référentiel, sur le périmètre déjà filtré.

    La répartition coté / non coté est donnée en nombre **et** en encours parce
    que les deux racontent des choses différentes. Attention à la lecture de la
    seconde : l'encours des lignes cotées non rapprochées est inconnu (le
    bulletin BRVM ne le publie pas), donc la part en encours est calculée sur le
    seul périmètre à encours connu et la couverture est renvoyée avec.
    """
    vivants = titres[titres["Statut"] == "Vivant"]
    encours = vivants["Encours (Mds FCFA)"]
    cotes = vivants[vivants["Coté"]]
    non_cotes = vivants[~vivants["Coté"]]
    connus = vivants[vivants["Encours connu"]]
    encours_cote = cotes["Encours (Mds FCFA)"].sum(skipna=True)
    encours_connu = connus["Encours (Mds FCFA)"].sum(skipna=True)
    poids = encours.where(encours > 0)

    def _moyenne_ponderee(colonne: str) -> float:
        valeurs = vivants[colonne]
        masque = valeurs.notna() & poids.notna()
        if not masque.any():
            return float("nan")
        return float(np.average(valeurs[masque], weights=poids[masque]))

    return {
        "Titres vivants": int(len(vivants)),
        "Titres échus": int((titres["Statut"] == "Échu").sum()),
        "Encours total (Mds FCFA)": float(encours_connu),
        "Titres cotés": int(len(cotes)),
        "Titres non cotés": int(len(non_cotes)),
        "Encours coté (Mds FCFA)": float(encours_cote),
        "Encours non coté (Mds FCFA)": float(
            non_cotes["Encours (Mds FCFA)"].sum(skipna=True)),
        "Part cotée en nombre": (len(cotes) / len(vivants)) if len(vivants) else float("nan"),
        "Part cotée en encours": (float(encours_cote / encours_connu)
                                  if encours_connu else float("nan")),
        "Titres à encours connu": int(len(connus)),
        "Couverture encours": (len(connus) / len(vivants)) if len(vivants) else float("nan"),
        "Titres cotés à encours connu": int(cotes["Encours connu"].sum()),
        "Coupon moyen": _moyenne_ponderee("Coupon"),
        "Maturité résiduelle moyenne": _moyenne_ponderee("Maturité résiduelle (années)"),
        "Duration modifiée moyenne": _moyenne_ponderee("Duration modifiée"),
        "Titres sans prix": int((vivants["Source du prix"] == "Aucun prix").sum()),
        "Encours estimé (titres)": int(vivants["Encours estimé"].sum()),
    }


def repartition(titres: pd.DataFrame, cle: str) -> pd.DataFrame:
    """Nombre de titres et encours par modalité, pour les ventilations.

    `Titres sans encours` accompagne systématiquement le total : une modalité à
    0 Md peut être une modalité vide ou une modalité non documentée, et la
    confusion entre les deux est exactement ce qu'on cherche à éviter.
    """
    vivants = titres[titres["Statut"] == "Vivant"]
    colonnes = [cle, "Titres", "Encours (Mds FCFA)", "Titres sans encours", "Part encours"]
    if vivants.empty or cle not in vivants.columns:
        return pd.DataFrame(columns=colonnes)
    agrege = (vivants.groupby(cle, dropna=False, observed=False)
              .agg(**{"Titres": ("Identifiant", "count"),
                      "Encours (Mds FCFA)": ("Encours (Mds FCFA)", "sum"),
                      "Titres avec encours": ("Encours connu", "sum")})
              .reset_index())
    agrege["Titres sans encours"] = agrege["Titres"] - agrege["Titres avec encours"]
    agrege["Encours (Mds FCFA)"] = agrege["Encours (Mds FCFA)"].where(
        agrege["Titres avec encours"] > 0)
    total = agrege["Encours (Mds FCFA)"].sum()
    agrege["Part encours"] = agrege["Encours (Mds FCFA)"] / total if total else np.nan
    return (agrege[colonnes].sort_values("Encours (Mds FCFA)", ascending=False,
                                         na_position="last")
            .reset_index(drop=True))


def classes_de_maturite(titres: pd.DataFrame) -> pd.DataFrame:
    """Ventilation par bucket de maturité résiduelle."""
    vivants = titres[titres["Statut"] == "Vivant"].copy()
    bornes = [0, 1, 2, 3, 5, 7, 10, 15, np.inf]
    libelles = ["≤ 1 an", "1-2 ans", "2-3 ans", "3-5 ans", "5-7 ans",
                "7-10 ans", "10-15 ans", "> 15 ans"]
    vivants["Classe de maturité"] = pd.cut(
        vivants["Maturité résiduelle (années)"], bins=bornes, labels=libelles,
        right=False)
    return repartition(vivants, "Classe de maturité")


def titre(titres: pd.DataFrame, identifiant: str) -> pd.Series | None:
    """Enregistrement d'un titre par son identifiant (utilisé par la fiche)."""
    trouve = titres[titres["Identifiant"] == identifiant]
    return trouve.iloc[0] if not trouve.empty else None


# --------------------------------------------------------------------------
# Historiques d'un titre — alimentent la fiche
# --------------------------------------------------------------------------
def historique_primaire(isin: str | None) -> pd.DataFrame:
    """Toutes les tranches d'adjudication d'une souche, de la plus récente.

    Attention à la lecture des montants par titre : sur les émissions
    simultanées (plusieurs souches dans une même opération), la ventilation par
    titre est reconstituée par différence et ressort négative sur 14,2 % des
    lignes. Les montants au niveau de l'opération, eux, sont fiables.
    """
    colonnes = [
        "Date de l'opération", "Date de valeur", "Échéance", "Instrument",
        "Montant mis en adjudication (Mds FCFA)", "Montant soumis (Mds FCFA)",
        "Montant retenu (Mds FCFA)", "Taux de couverture", "Taux de service",
        "Rendement moyen pondéré (déc.)", "Taux marginal (déc.)",
        "Taux moyen pondéré (déc.)", "Prix marginal", "Prix moyen pondéré",
        "Type d'amortissement", "État", "Opération",
        "Montant annoncé opération (Mds FCFA)", "Montant soumis opération (Mds FCFA)",
        "Montant retenu opération (Mds FCFA)", "Lien",
    ]
    if not isin:
        return pd.DataFrame(columns=colonnes)
    primaire = chargement.emissions_primaire()
    extrait = primaire[primaire["ISIN"] == isin].copy()
    if extrait.empty:
        return pd.DataFrame(columns=colonnes)
    for colonne in colonnes:
        if colonne not in extrait.columns:
            extrait[colonne] = np.nan
    extrait["Montant incohérent"] = (
        pd.to_numeric(extrait["Montant retenu (Mds FCFA)"], errors="coerce") < 0)
    return (extrait[colonnes + ["Montant incohérent"]]
            .sort_values("Date de l'opération", ascending=False)
            .reset_index(drop=True))


def historique_secondaire(isin: str | None) -> pd.DataFrame:
    """Séances de négociation d'une souche, dans l'ordre chronologique."""
    if not isin:
        return chargement.marche_secondaire().iloc[0:0]
    secondaire = chargement.marche_secondaire()
    return (secondaire[secondaire["ISIN"] == isin]
            .sort_values("Date de transaction").reset_index(drop=True))


def historique_brvm(code: str | None) -> pd.DataFrame:
    """Cotations successives d'une ligne inscrite à la cote BRVM."""
    colonnes = ["Date de cotation", "Cours du jour", "Coupon couru",
                "Taux facial", "Dernier paiement"]
    if not code:
        return pd.DataFrame(columns=colonnes)
    brvm = chargement.brvm_obligations()
    extrait = brvm[brvm["Code obligation"] == code]
    if extrait.empty:
        return pd.DataFrame(columns=colonnes)
    return (extrait[colonnes].sort_values("Date de cotation")
            .reset_index(drop=True))
