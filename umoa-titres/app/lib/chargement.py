# -*- coding: utf-8 -*-
"""Chargement et normalisation des jeux de données `data/_bi/`.

Point d'entrée unique de l'app : aucune page ne lit un CSV directement. Les
fonctions renvoient toujours des DataFrames aux types déjà convertis (dates en
datetime, taux en décimal) et aux libellés pays normalisés, de sorte que les
jointures entre sources se font sans retraitement.

Le cache Streamlit est appliqué quand streamlit est disponible ; les modules
restent importables depuis un script ou un notebook sans lui.
"""
from __future__ import annotations

import functools
import os
import unicodedata
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parents[2]
#: Dossier `data/` du dépôt de données Scraper-UMOA-Titres : par défaut, un clone placé à côté de
#: Reporting (même dossier parent) ; `UMOA_DATA_DIR` peut en désigner un autre.
DONNEES = Path(os.environ.get("UMOA_DATA_DIR")
               or RACINE.parents[1] / "Scraper-UMOA-Titres" / "data")
DOSSIER_BI = DONNEES / "_bi"
DOSSIER_BENCHMARK = DONNEES / "benchmark"

PAYS_UEMOA = [
    "Bénin", "Burkina Faso", "Côte d'Ivoire", "Guinée-Bissau",
    "Mali", "Niger", "Sénégal", "Togo",
]

#: Segments d'univers utilisés dans tout le référentiel.
SEGMENT_SOUVERAIN = "Souverain UMOA"
SEGMENT_PRIVE = "Privé / Institutionnel"


def _cache_memoire(fonction):
    """Repli hors app : mémoïsation simple.

    Indispensable et pas seulement confortable — le référentiel interroge les
    courbes plus d'un millier de fois, et sans mémoïsation chaque appel relit et
    reparse les 33 000 lignes de `courbes_taux.csv`.
    """
    return functools.lru_cache(maxsize=None)(fonction)


try:  # pragma: no cover - dépend du contexte d'exécution
    import streamlit as st
    from streamlit.runtime import exists as _runtime_actif

    # Hors runtime (script, test, notebook), `st.cache_data` émet un
    # avertissement par appel : on ne l'installe que dans l'app.
    _cache = (st.cache_data(show_spinner=False) if _runtime_actif()
              else _cache_memoire)
except Exception:  # streamlit absent
    _cache = _cache_memoire


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------
def sans_accents(texte) -> str:
    """'Sénégal' -> 'senegal'. Neutralise aussi l'apostrophe typographique."""
    nfkd = unicodedata.normalize("NFKD", str(texte)).replace("’", "'")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def cle_pays(valeur) -> str | None:
    """Ramène toutes les graphies d'un pays UEMOA à un libellé unique.

    Les trois sources écrivent le même pays différemment : le marché secondaire
    dit « Burkina », le primaire « Côte d’Ivoire » (apostrophe typographique) et
    « Guinée Bissau » sans trait d'union, les courbes « Burkina Faso ».
    """
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return None
    t = sans_accents(valeur).replace("-", " ")
    if not t:
        return None
    for motif, pays in (
        ("benin", "Bénin"),
        ("burkina", "Burkina Faso"),
        ("ivoire", "Côte d'Ivoire"),
        ("bissau", "Guinée-Bissau"),
        ("guinee", "Guinée-Bissau"),
        ("mali", "Mali"),
        ("niger", "Niger"),
        ("senegal", "Sénégal"),
        ("togo", "Togo"),
    ):
        if motif in t:
            return pays
    return None


def _dates(df: pd.DataFrame, colonnes, dayfirst: bool = False) -> pd.DataFrame:
    """Convertit en datetime. `dayfirst` pour les sources au format JJ/MM/AAAA."""
    for colonne in colonnes:
        if colonne in df.columns:
            df[colonne] = pd.to_datetime(df[colonne], errors="coerce",
                                         dayfirst=dayfirst, format="mixed")
    return df


def _lire(nom: str) -> pd.DataFrame:
    chemin = DOSSIER_BI / nom
    if not chemin.exists():
        raise FileNotFoundError(
            f"{chemin} est absent. Lancer `python scripts/preparer_donnees_bi.py` "
            "pour régénérer les fichiers BI."
        )
    return pd.read_csv(chemin, encoding="utf-8")


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------
@_cache
def marche_secondaire() -> pd.DataFrame:
    """Transactions du marché secondaire, une ligne par (titre, séance)."""
    df = _lire("marche_secondaire.csv")
    df = _dates(df, ["Date de transaction", "Date d'échéance"])
    df["Pays"] = df["Émetteur"].map(cle_pays)
    return df


@_cache
def emissions_primaire() -> pd.DataFrame:
    """Adjudications du marché primaire (une ligne par titre et par opération).

    Un même ISIN revient autant de fois qu'il a été réabondé : 2 538 ISIN pour
    3 950 lignes, jusqu'à une dizaine de tranches pour les souches profondes.
    L'agrégation par titre est faite dans `referentiel.py`.
    """
    return _normaliser_primaire(_lire("emissions_primaire.csv"))


@_cache
def emissions_primaire_retenues() -> pd.DataFrame:
    """Adjudications retenues pour l'analyse (``scripts/preparer_donnees_bi.py``,
    ``filtrer_emissions_retenues``) : rendement moyen pondéré et montant retenu renseignés
    et positifs, sans précision (ni échange, ni obligation de relance, ni adjudication
    ciblée, ni rachat). Seulement des adjudications passées ; agrégats par opération
    recalculés sur ces lignes."""
    return _normaliser_primaire(_lire("emissions_primaire_retenues.csv"))


def _normaliser_primaire(df: pd.DataFrame) -> pd.DataFrame:
    df = _dates(df, ["Date de l'opération", "Date de valeur", "Échéance"])
    df["Pays"] = df["Pays"].map(cle_pays).fillna(df["Émetteur"].map(cle_pays))
    # Les taux du primaire sont publiés en pourcentage, pas en décimal.
    for colonne in ("Taux d'intérêt (%)", "Rendement moyen pondéré (%)",
                    "Taux moyen pondéré (%)", "Taux marginal (%)",
                    "Taux de sortie (%)"):
        if colonne in df.columns:
            df[colonne.replace(" (%)", " (déc.)")] = (
                pd.to_numeric(df[colonne], errors="coerce") / 100.0)
    return df


@_cache
def courbes_taux() -> pd.DataFrame:
    """Courbes zéro-coupon hebdomadaires UMOA-Titres, 8 pays, depuis 2019."""
    df = _lire("courbes_taux.csv")
    df = _dates(df, ["Date"])
    df["Pays"] = df["Pays"].map(cle_pays)
    return df.sort_values(["Pays", "Date", "Maturité (années)"])


@_cache
def brvm_obligations() -> pd.DataFrame:
    """Cotations quotidiennes des obligations inscrites à la BRVM."""
    df = _lire("brvm_obligations.csv")
    df = _dates(df, ["Date de cotation"])
    # Le bulletin BRVM date les titres en JJ/MM/AAAA, contrairement aux autres sources.
    df = _dates(df, ["Date d'émission", "Date de maturité"], dayfirst=True)
    df["Segment"] = df["Catégorie"].where(
        df["Catégorie"] != "État / Souverain", SEGMENT_SOUVERAIN)
    return df


@_cache
def calendrier() -> pd.DataFrame:
    """Calendrier des émissions passées et annoncées."""
    df = _lire("calendrier_emissions.csv")
    df = _dates(df, ["Date", "Dernière modification"])
    df["Pays"] = df["Pays"].map(cle_pays)
    return df


@_cache
def benchmark() -> pd.DataFrame:
    """Indice obligataire (base 100), mensuel."""
    chemin = DOSSIER_BENCHMARK / "benchmark_obligataire.csv"
    if not chemin.exists():
        return pd.DataFrame()
    return _dates(pd.read_csv(chemin, encoding="utf-8"), ["Date"])


# --------------------------------------------------------------------------
# Fraîcheur
# --------------------------------------------------------------------------
#: Sources d'observation (par opposition au calendrier, qui est prospectif).
SOURCES_OBSERVEES = ("Marché secondaire", "Marché primaire", "Courbes de taux",
                     "Cotations BRVM")


@_cache
def fraicheur() -> pd.DataFrame:
    """Dernière date disponible et ancienneté, source par source.

    Sert d'en-tête d'avertissement sur toutes les pages : une métrique lue sans
    savoir de quand datent ses données est une métrique dangereuse.
    """
    aujourdhui = pd.Timestamp.today().normalize()
    lignes = []
    for libelle, df, colonne in (
        ("Marché secondaire", marche_secondaire(), "Date de transaction"),
        ("Marché primaire", emissions_primaire(), "Date de l'opération"),
        ("Courbes de taux", courbes_taux(), "Date"),
        ("Cotations BRVM", brvm_obligations(), "Date de cotation"),
        ("Calendrier", calendrier(), "Date"),
    ):
        derniere = df[colonne].max() if not df.empty else pd.NaT
        lignes.append({
            "Source": libelle,
            "Dernière donnée": derniere,
            "Ancienneté (jours)": (
                (aujourdhui - derniere).days if pd.notna(derniere) else None),
            "Lignes": len(df),
        })
    return pd.DataFrame(lignes)


def date_reference() -> pd.Timestamp:
    """Date « aujourd'hui » du référentiel : la plus récente donnée observée.

    On ne se cale pas sur l'horloge système : si les scrapers n'ont pas tourné
    depuis une semaine, les maturités résiduelles doivent rester cohérentes avec
    les prix affichés.
    """
    etat = fraicheur()
    dates = etat.loc[etat["Source"].isin(SOURCES_OBSERVEES), "Dernière donnée"].dropna()
    aujourdhui = pd.Timestamp.today().normalize()
    if dates.empty:
        return aujourdhui
    # Le calendrier est prospectif et le primaire annonce des opérations à venir :
    # la date de référence ne doit jamais dépasser aujourd'hui.
    return min(dates.max(), aujourdhui)
