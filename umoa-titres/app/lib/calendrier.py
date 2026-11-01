# -*- coding: utf-8 -*-
"""Calendrier des émissions : agenda, cadence et tenue des annonces.

Le calendrier UMOA-Titres est la seule source **prospective** du dispositif :
il annonce les séances d'adjudication avant qu'elles n'aient lieu, là où le
marché primaire ne publie ses chiffres qu'une fois l'opération dénouée. Les
deux se recouvrent largement — 1 683 événements depuis 2017 contre 1 763
opérations primaires — mais ne racontent pas la même chose : le calendrier dit
*quand*, le primaire dit *combien*.

Le rapprochement se fait sur l'URL de la fiche d'émission, partagée par les deux
sources, avec repli sur le couple (pays, date) quand l'URL a été réécrite : la
clé lien apparie 92 % des événements passés, le couple pays-date en récupère
4 points de plus. Les 4 % restants sont des annonces sans résultat publié —
séances déplacées, annulées, ou simplement absentes du fichier primaire — et
sont exposées telles quelles plutôt que masquées.

Prudence sur `Dernière modification` : c'est le `dtstamp` du flux, donc la
**dernière** retouche de la fiche, souvent postérieure à la séance (les
résultats y sont ajoutés après coup). Il ne majore un préavis que pour les
fiches jamais rééditées depuis leur publication ; toutes les mesures qui s'en
servent ici se restreignent aux événements où il précède la date d'opération, et
n'en donnent qu'une borne inférieure.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import chargement
# Helper de pondération partagé avec le primaire : le dupliquer ferait diverger
# les deux traitements du cas « poids absents ».
from .primaire import _moyenne_ponderee

#: Libellés d'état affichés dans l'agenda, du plus au moins renseigné.
ETAT_ANNONCEE = "Annoncée"
ETAT_PLANIFIEE = "Planifiée"
ETAT_CALENDRIER = "Au calendrier"

JOURS_SEMAINE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi",
                 "samedi", "dimanche"]

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


def _cle_lien(serie: pd.Series) -> pd.Series:
    """URL normalisée : casse, espaces et barre oblique finale neutralisées."""
    nettoyee = (serie.astype(str).str.strip().str.rstrip("/").str.lower()
                .replace({"nan": None, "": None}))
    return nettoyee


def _cle_pays_date(pays: pd.Series, dates: pd.Series) -> pd.Series:
    """Clé de repli : un pays n'adjuge qu'exceptionnellement deux fois le même jour."""
    return pays.astype(str) + "|" + dates.dt.strftime("%Y-%m-%d")


def evenements() -> pd.DataFrame:
    """Événements du calendrier, statut recalculé à la date du jour.

    Le statut porté par le fichier date du dernier passage du scraper : une
    émission « à venir » scrapée il y a un mois est déjà passée. Il est donc
    systématiquement recalculé ici, contre l'horloge système — c'est le seul
    endroit de l'app où c'est la bonne référence, puisqu'on parle d'un agenda
    et non d'une valorisation.
    """
    donnees = chargement.calendrier().copy()
    donnees = donnees[donnees["Date"].notna()].copy()
    aujourdhui = pd.Timestamp.today().normalize()

    donnees["Statut"] = np.where(donnees["Date"] >= aujourdhui,
                                 "À venir", "Passée")
    donnees["Jours restants"] = (donnees["Date"] - aujourdhui).dt.days
    donnees["Clé lien"] = _cle_lien(donnees["Lien"])
    donnees["Clé pays-date"] = _cle_pays_date(donnees["Pays"], donnees["Date"])
    donnees["Mois"] = donnees["Date"].dt.to_period("M").dt.to_timestamp()
    donnees["Année"] = donnees["Date"].dt.year
    donnees["Jour de semaine"] = donnees["Date"].dt.dayofweek.map(
        dict(enumerate(JOURS_SEMAINE)))
    donnees["Préavis (jours)"] = (
        donnees["Date"] - donnees["Dernière modification"]).dt.days
    # Un préavis négatif signale une fiche rééditée après la séance : la mesure
    # n'a alors plus de sens et vaut mieux manquante que trompeuse.
    donnees.loc[donnees["Préavis (jours)"] < 0, "Préavis (jours)"] = np.nan
    return donnees.sort_values("Date", ascending=False).reset_index(drop=True)


def _agreger_resultats(lignes: pd.DataFrame, cle: str) -> pd.DataFrame:
    """Résultats d'adjudication agrégés par clé de rapprochement.

    Les volumes viennent du niveau opération (dédoublonné par
    `Premier titre de l'opération`), les taux du niveau titre : c'est la règle
    posée dans `primaire.py`, et elle vaut aussi ici.
    """
    entetes = lignes[lignes["Premier titre de l'opération"].fillna(False)]
    if entetes.empty:
        entetes = lignes.drop_duplicates(subset=[cle])

    volumes = entetes.groupby(cle).agg(**{
        "Opérations publiées": ("Opération", "size"),
        "Montant annoncé (Mds FCFA)": (
            "Montant annoncé opération (Mds FCFA)",
            lambda s: s.where(s > 0).sum(min_count=1)),
        "Montant retenu (Mds FCFA)": (
            "Montant retenu opération (Mds FCFA)",
            lambda s: s.where(s > 0).sum(min_count=1)),
        "État": ("État", "first"),
        "Catégorie": ("Catégorie", "first"),
    })
    taux = lignes.groupby(cle).apply(lambda groupe: pd.Series({
        "Taux de couverture": _moyenne_ponderee(
            groupe["Taux de couverture"],
            groupe["Montant annoncé opération (Mds FCFA)"]),
        "Rendement moyen pondéré": _moyenne_ponderee(
            groupe["Rendement moyen pondéré (déc.)"],
            groupe["Montant retenu (Mds FCFA)"]),
        "Maturité moyenne (années)": _moyenne_ponderee(
            groupe["Maturité (années)"], groupe["Montant retenu (Mds FCFA)"]),
        "Titres servis": float(len(groupe)),
    }), include_groups=False)
    return volumes.join(taux).reset_index()


def _primaire_indexe() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Le primaire agrégé, une fois par clé lien et une fois par (pays, date)."""
    lignes = chargement.emissions_primaire().copy()
    lignes["Clé lien"] = _cle_lien(lignes["Lien"])
    lignes["Clé pays-date"] = _cle_pays_date(lignes["Pays"],
                                             lignes["Date de l'opération"])
    par_lien = _agreger_resultats(lignes[lignes["Clé lien"].notna()], "Clé lien")
    par_pays_date = _agreger_resultats(lignes, "Clé pays-date")
    return par_lien, par_pays_date


COLONNES_RESULTAT = ["Opérations publiées", "Montant annoncé (Mds FCFA)",
                     "Montant retenu (Mds FCFA)", "État", "Catégorie",
                     "Taux de couverture", "Rendement moyen pondéré",
                     "Maturité moyenne (années)", "Titres servis"]


def rapprocher(donnees: pd.DataFrame) -> pd.DataFrame:
    """Joint chaque événement à son opération primaire, lien puis pays-date.

    La colonne `Rapprochement` conserve la clé qui a permis l'appariement (ou
    « aucun ») : un rapprochement par pays-date est plus fragile qu'un
    rapprochement par URL et le lecteur doit pouvoir en tenir compte.
    """
    if donnees.empty:
        return donnees.assign(Rapprochement=pd.Series(dtype=str),
                              **{c: pd.Series(dtype="object")
                                 for c in COLONNES_RESULTAT})
    par_lien, par_pays_date = _primaire_indexe()

    joint = donnees.merge(par_lien, on="Clé lien", how="left")
    joint["Rapprochement"] = np.where(joint["Opérations publiées"].notna(),
                                      "Lien", None)

    manquants = joint["Opérations publiées"].isna()
    if manquants.any():
        repli = (joint.loc[manquants, ["Clé pays-date"]]
                 .merge(par_pays_date, on="Clé pays-date", how="left"))
        repli.index = joint.index[manquants]
        for colonne in COLONNES_RESULTAT:
            joint.loc[manquants, colonne] = repli[colonne]
        joint.loc[manquants & joint["Opérations publiées"].notna(),
                  "Rapprochement"] = "Pays et date"

    joint["Rapprochement"] = joint["Rapprochement"].fillna("Aucun")
    joint["Taux de réalisation"] = (joint["Montant retenu (Mds FCFA)"]
                                    / joint["Montant annoncé (Mds FCFA)"])
    return joint


def agenda(evenements_connus: pd.DataFrame | None = None,
           horizon_jours: int | None = None) -> pd.DataFrame:
    """Émissions à venir, enrichies de l'enveloppe annoncée quand elle existe.

    Trois niveaux de renseignement cohabitent, du plus au moins avancé :
    « Annoncée » (l'avis est publié avec son enveloppe), « Planifiée »
    (inscrite au calendrier prévisionnel du Trésor, montant indicatif) et
    « Au calendrier » (l'événement existe côté calendrier, mais aucune fiche
    primaire ne lui correspond encore).
    """
    tous = evenements() if evenements_connus is None else evenements_connus
    futurs = tous[tous["Statut"] == "À venir"].copy()
    if horizon_jours is not None:
        futurs = futurs[futurs["Jours restants"] <= horizon_jours]
    if futurs.empty:
        return futurs.assign(**{"Enveloppe (Mds FCFA)": pd.Series(dtype=float),
                                "État attendu": pd.Series(dtype=str)})

    lignes = chargement.emissions_primaire().copy()
    lignes["Clé lien"] = _cle_lien(lignes["Lien"])
    a_venir = lignes[lignes["Catégorie"].isin(["À venir", "Planifiée"])]
    enveloppes = a_venir.groupby("Clé lien").agg(**{
        "Enveloppe (Mds FCFA)": ("Montant mis en adjudication (Mds FCFA)", "sum"),
        "Catégorie": ("Catégorie", "first"),
        "Date de valeur": ("Date de valeur", "first"),
    }).reset_index()

    futurs = futurs.merge(enveloppes, on="Clé lien", how="left")
    futurs["État attendu"] = futurs["Catégorie"].map(
        {"À venir": ETAT_ANNONCEE, "Planifiée": ETAT_PLANIFIEE}
    ).fillna(ETAT_CALENDRIER)
    return futurs.sort_values("Date").reset_index(drop=True)


def cadence(evenements_connus: pd.DataFrame, par: str = "Pays",
            frequence: str = "M") -> pd.DataFrame:
    """Nombre d'émissions par période et par modalité."""
    colonnes = ["Période", par, "Émissions"]
    if evenements_connus.empty or par not in evenements_connus.columns:
        return pd.DataFrame(columns=colonnes)
    travail = evenements_connus.copy()
    travail["Période"] = (travail["Date"].dt.to_period(frequence)
                          .dt.to_timestamp())
    agrege = (travail.groupby(["Période", par], observed=True)
              .size().rename("Émissions").reset_index())
    return agrege[colonnes]


def regularite(evenements_connus: pd.DataFrame) -> pd.DataFrame:
    """Régularité de la venue au marché, pays par pays.

    L'intervalle médian entre deux séances consécutives dit mieux que le
    décompte annuel à quel rythme un émetteur se présente : un pays qui adjuge
    24 fois dans l'année en deux campagnes serrées n'a pas le même profil de
    refinancement qu'un pays qui vient tous les quinze jours.
    """
    colonnes = ["Pays", "Émissions", "Première", "Dernière",
                "Intervalle médian (jours)", "Émissions par an"]
    if evenements_connus.empty:
        return pd.DataFrame(columns=colonnes)

    lignes = []
    for pays, groupe in evenements_connus[
            evenements_connus["Pays"].notna()].groupby("Pays", observed=True):
        dates = groupe["Date"].sort_values()
        ecarts = dates.diff().dt.days.dropna()
        etendue = (dates.max() - dates.min()).days
        lignes.append({
            "Pays": pays,
            "Émissions": len(dates),
            "Première": dates.min(),
            "Dernière": dates.max(),
            "Intervalle médian (jours)": (float(ecarts.median())
                                          if not ecarts.empty else np.nan),
            "Émissions par an": (len(dates) / (etendue / 365.25)
                                 if etendue > 0 else np.nan),
        })
    return (pd.DataFrame(lignes)
            .sort_values("Émissions", ascending=False)
            .reset_index(drop=True))


def appariement(rapproches: pd.DataFrame) -> pd.DataFrame:
    """Part des événements passés dont le résultat d'adjudication est publié.

    Le taux n'atteint jamais 100 % et c'est attendu : une séance inscrite au
    calendrier peut être reportée ou annulée sans que la fiche disparaisse.
    Suivre ce taux année par année sert surtout à repérer une dégradation de la
    collecte, qui elle n'est pas normale.
    """
    colonnes = ["Année", "Événements", "Résultats publiés", "Taux d'appariement"]
    if rapproches.empty:
        return pd.DataFrame(columns=colonnes)
    agrege = rapproches.groupby("Année").apply(lambda groupe: pd.Series({
        "Événements": float(len(groupe)),
        "Résultats publiés": float((groupe["Rapprochement"] != "Aucun").sum()),
    }), include_groups=False).reset_index()
    agrege["Taux d'appariement"] = (agrege["Résultats publiés"]
                                    / agrege["Événements"])
    return agrege[colonnes]


# --------------------------------------------------------------------------
# Export iCalendar
# --------------------------------------------------------------------------
def _echapper(texte: str) -> str:
    """Échappement RFC 5545 des séparateurs de propriété."""
    return (str(texte).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def _plier(ligne: str) -> str:
    """Repli des lignes à 75 octets, continuation par une espace."""
    octets = ligne.encode("utf-8")
    if len(octets) <= 75:
        return ligne
    morceaux, courant = [], ""
    limite = 74
    for caractere in ligne:
        if len((courant + caractere).encode("utf-8")) > limite:
            morceaux.append(courant)
            courant, limite = " " + caractere, 73
        else:
            courant += caractere
    morceaux.append(courant)
    return "\r\n".join(morceaux)


def ics(evenements_a_exporter: pd.DataFrame) -> str:
    """Agenda au format iCalendar, importable dans Outlook ou Google Agenda.

    Les événements sont journée entière : le flux source ne porte pas d'heure
    de séance, et en inventer une donnerait une fausse précision.
    """
    lignes = ["BEGIN:VCALENDAR", "VERSION:2.0",
              "PRODID:-//Scraper-UMOA-Titres//Calendrier UMOA-Titres//FR",
              "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
              "X-WR-CALNAME:Émissions UMOA-Titres"]
    for _, evenement in evenements_a_exporter.iterrows():
        date = evenement["Date"]
        if pd.isna(date):
            continue
        horodatage = evenement.get("Dernière modification")
        horodatage = (date if pd.isna(horodatage) else horodatage)
        montant = evenement.get("Enveloppe (Mds FCFA)")
        resume = " — ".join(
            part for part in (evenement.get("Pays"), evenement.get("Instrument"))
            if isinstance(part, str) and part)
        if pd.notna(montant):
            resume += f" ({montant:,.0f} Mds FCFA)".replace(",", " ")
        description = str(evenement.get("Titre") or "")
        if evenement.get("État attendu"):
            description += f" [{evenement['État attendu']}]"
        identifiant = evenement.get("Identifiant") or f"{date:%Y%m%d}"
        lignes += [
            "BEGIN:VEVENT",
            f"UID:{identifiant}@umoatitres.org",
            f"DTSTAMP:{horodatage:%Y%m%dT%H%M%SZ}",
            f"DTSTART;VALUE=DATE:{date:%Y%m%d}",
            f"DTEND;VALUE=DATE:{date + pd.Timedelta(days=1):%Y%m%d}",
            _plier(f"SUMMARY:{_echapper(resume or description)}"),
            _plier(f"DESCRIPTION:{_echapper(description)}"),
        ]
        lien = evenement.get("Lien")
        if isinstance(lien, str) and lien.startswith("http"):
            lignes.append(_plier(f"URL:{lien}"))
        lignes.append("END:VEVENT")
    lignes.append("END:VCALENDAR")
    return "\r\n".join(lignes) + "\r\n"
