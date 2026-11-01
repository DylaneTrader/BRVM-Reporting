# -*- coding: utf-8 -*-
"""Courbes de taux souveraines : trois niveaux de lecture, tous paramétrables.

Rappel de la décision d'architecture (cf. discussion de conception) : le taux de
référence n'est pas recalculé, il est *repris* d'UMOA-Titres. On empile donc
trois niveaux qui cohabitent en permanence, sans qu'aucun n'écrase l'autre :

    N0  brut       « Zéro Coupon » publié           -> audit, jamais par défaut
    N1  officielle « Taux Après Lissage » publié     -> référence de place, défaut
    N2  reconstruite reconstruction maison             -> analytique

N2 corrige trois défauts mesurés du fichier source, sans toucher au niveau :
  1. la grille est trouée (le point 10 ans n'existe que sur 48 % des courbes,
     le 15 ans sur 14 %) -> interpolation monotone sur grille régulière ;
  2. le segment court est bruité (7,7 % des courbes ont le 3 mois au-dessus du
     1 an de plus de 100 pb) -> ancrage optionnel sur les adjudications BAT ;
  3. le segment long est figé -> extrapolation Nelson-Siegel-Svensson optionnelle
     plutôt qu'un prolongement plat.

Tous les réglages passent par `ParametresCourbe`, conçu pour être piloté depuis
des widgets Streamlit (`ParametresCourbe.depuis_etat(dict)`).
"""
from __future__ import annotations

import functools
from dataclasses import asdict, dataclass, fields

import numpy as np
import pandas as pd

from . import chargement

NIVEAU_BRUT = "brut"
NIVEAU_OFFICIELLE = "officielle"
NIVEAU_RECONSTRUITE = "reconstruite"

LIBELLES_NIVEAUX = {
    NIVEAU_BRUT: "Zéro coupon brut (UMOA-Titres)",
    NIVEAU_OFFICIELLE: "Courbe officielle lissée (UMOA-Titres)",
    NIVEAU_RECONSTRUITE: "Courbe reconstruite",
}

_COLONNE_NIVEAU = {
    NIVEAU_BRUT: "Taux zéro coupon",
    NIVEAU_OFFICIELLE: "Taux après lissage",
}


@dataclass(frozen=True)
class ParametresCourbe:
    """Réglages de la reconstruction N2. Les défauts sont ceux recommandés."""

    #: "pchip" (monotone, recommandé), "lineaire" ou "nss" (ajustement global).
    interpolateur: str = "pchip"
    #: Grille de sortie, en années.
    maturite_min: float = 0.25
    maturite_max: float = 15.0
    pas: float = 0.25
    #: Ancrage du court terme sur les adjudications réellement servies.
    ancrage_bat: bool = True
    #: Fenêtre de collecte des adjudications autour de la date de courbe (jours).
    ancrage_fenetre_jours: int = 90
    #: Maturité au-delà de laquelle l'ancrage ne s'applique plus (années).
    ancrage_maturite_max: float = 1.0
    #: Poids de l'adjudication face au point publié (1.0 = remplacement total).
    ancrage_poids: float = 1.0
    #: Nombre minimum d'adjudications pour qu'un point d'ancrage soit retenu.
    ancrage_min_observations: int = 2
    #: "plat" ou "nss" au-delà de la dernière maturité publiée.
    extrapolation: str = "nss"
    #: Garde-fous appliqués en sortie (en décimal).
    taux_min: float = 0.0
    taux_max: float = 0.20
    #: Ancienneté au-delà de laquelle une courbe est signalée comme périmée.
    seuil_fraicheur_jours: int = 21

    @classmethod
    def depuis_etat(cls, etat: dict | None) -> "ParametresCourbe":
        """Construit les paramètres depuis un dict (ex. `st.session_state`)."""
        if not etat:
            return cls()
        connus = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in etat.items() if k in connus})

    def en_dict(self) -> dict:
        return asdict(self)


#: Clé de `st.session_state` portant les réglages choisis sur la page Courbes.
CLE_ETAT = "parametres_courbe"


def parametres_actifs() -> ParametresCourbe:
    """Réglages retenus pour toute l'app, ou les défauts hors contexte Streamlit.

    Permet à la page Courbes de piloter la reconstruction utilisée partout
    ailleurs (référentiel, fiche titre) sans que ces pages aient à connaître
    les widgets.
    """
    try:
        import streamlit as st

        return ParametresCourbe.depuis_etat(dict(st.session_state.get(CLE_ETAT, {})))
    except Exception:
        return ParametresCourbe()


# --------------------------------------------------------------------------
# Interpolation monotone (Fritsch-Carlson) — sans dépendance à scipy
# --------------------------------------------------------------------------
def _pentes_pchip(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Pentes préservant la monotonie, méthode de Fritsch-Carlson.

    Une spline cubique naturelle overshoote entre deux points éloignés — cas
    fréquent ici, où il manque parfois 5 ans entre deux maturités publiées.
    """
    n = len(x)
    if n == 1:
        return np.zeros(1)
    h = np.diff(x)
    delta = np.diff(y) / h
    if n == 2:
        return np.repeat(delta[0], 2)

    pentes = np.zeros(n)
    signe = np.sign(delta[:-1]) * np.sign(delta[1:])
    interieur = signe > 0
    w1 = 2 * h[1:] + h[:-1]
    w2 = h[1:] + 2 * h[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        moyenne = (w1 + w2) / (w1 / delta[:-1] + w2 / delta[1:])
    pentes[1:-1] = np.where(interieur, moyenne, 0.0)

    pentes[0] = _pente_bord(h[0], h[1] if n > 2 else h[0], delta[0],
                            delta[1] if n > 2 else delta[0])
    pentes[-1] = _pente_bord(h[-1], h[-2] if n > 2 else h[-1], delta[-1],
                             delta[-2] if n > 2 else delta[-1])
    return pentes


def _pente_bord(h0: float, h1: float, d0: float, d1: float) -> float:
    """Pente au bord, formule à trois points bornée pour rester monotone."""
    pente = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
    if np.sign(pente) != np.sign(d0):
        return 0.0
    if np.sign(d0) != np.sign(d1) and abs(pente) > abs(3 * d0):
        return 3 * d0
    return pente


def _evaluer_hermite(x: np.ndarray, y: np.ndarray, pentes: np.ndarray,
                     cible: np.ndarray) -> np.ndarray:
    """Évalue la cubique d'Hermite par morceaux ; extrapolation plate aux bords."""
    cible = np.asarray(cible, dtype=float)
    idx = np.clip(np.searchsorted(x, cible) - 1, 0, len(x) - 2)
    h = x[idx + 1] - x[idx]
    t = (cible - x[idx]) / h
    t2, t3 = t * t, t * t * t
    valeurs = (
        (2 * t3 - 3 * t2 + 1) * y[idx]
        + (t3 - 2 * t2 + t) * h * pentes[idx]
        + (-2 * t3 + 3 * t2) * y[idx + 1]
        + (t3 - t2) * h * pentes[idx + 1]
    )
    return np.where(cible < x[0], y[0], np.where(cible > x[-1], y[-1], valeurs))


# --------------------------------------------------------------------------
# Nelson-Siegel-Svensson — ajustement numpy pur (grille sur tau, moindres carrés)
# --------------------------------------------------------------------------
def _base_nss(t: np.ndarray, tau1: float, tau2: float) -> np.ndarray:
    t = np.maximum(np.asarray(t, dtype=float), 1e-6)
    e1, e2 = np.exp(-t / tau1), np.exp(-t / tau2)
    f1 = (1 - e1) / (t / tau1)
    f2 = f1 - e1
    f3 = (1 - e2) / (t / tau2) - e2
    return np.column_stack([np.ones_like(t), f1, f2, f3])


@functools.lru_cache(maxsize=8192)
def _ajuster_nss_memo(maturites: tuple, taux: tuple) -> tuple | None:
    """Cœur de l'ajustement, mémoïsé sur les points d'entrée.

    Les courbes publiées sont souvent identiques d'une semaine à l'autre (de
    36 % à 76 % des publications selon le pays) : la mémoïsation évite de
    refaire les mêmes 24 moindres carrés des centaines de fois sur un
    historique long.
    """
    x = np.asarray(maturites, dtype=float)
    y = np.asarray(taux, dtype=float)
    meilleur, erreur_min = None, np.inf
    for tau1 in (0.5, 1.0, 1.5, 2.0, 3.0, 5.0):
        for tau2 in (3.0, 5.0, 8.0, 12.0):
            base = _base_nss(x, tau1, tau2)
            betas, *_ = np.linalg.lstsq(base, y, rcond=None)
            erreur = float(np.sum((base @ betas - y) ** 2))
            if erreur < erreur_min:
                meilleur, erreur_min = (betas, tau1, tau2), erreur
    return meilleur


def ajuster_nss(maturites: np.ndarray, taux: np.ndarray) -> tuple | None:
    """Ajuste un NSS. Renvoie (betas, tau1, tau2) ou None si trop peu de points."""
    maturites = np.asarray(maturites, dtype=float)
    taux = np.asarray(taux, dtype=float)
    if len(maturites) < 5:
        return None
    return _ajuster_nss_memo(tuple(maturites.tolist()), tuple(taux.tolist()))


def _evaluer_nss(modele: tuple, cible: np.ndarray) -> np.ndarray:
    betas, tau1, tau2 = modele
    return _base_nss(cible, tau1, tau2) @ betas


# --------------------------------------------------------------------------
# Points sources
# --------------------------------------------------------------------------
def grille(params: ParametresCourbe) -> np.ndarray:
    """Grille de maturités régulière de la courbe reconstruite."""
    nombre = int(round((params.maturite_max - params.maturite_min) / params.pas)) + 1
    return np.round(params.maturite_min + params.pas * np.arange(nombre), 6)


@functools.lru_cache(maxsize=1)
def _courbes_indexees() -> dict:
    """Courbes découpées une fois par (pays, date), et dates triées par pays.

    Sans cet index, chaque lecture de courbe refiltre les 33 000 lignes du
    fichier : une série temporelle sur huit pays et trois ans en demande plus
    d'un millier, ce qui coûtait une dizaine de secondes à chaque interaction.
    """
    donnees = chargement.courbes_taux()
    groupes = {cle: bloc for cle, bloc in donnees.groupby(["Pays", "Date"])}
    dates: dict = {}
    for pays, date in groupes:
        dates.setdefault(pays, []).append(date)
    return {"groupes": groupes,
            "dates": {pays: np.array(sorted(valeurs), dtype="datetime64[ns]")
                      for pays, valeurs in dates.items()}}


def dates_disponibles(pays: str) -> list[pd.Timestamp]:
    """Dates de courbe publiées pour un pays, de la plus récente à la plus ancienne."""
    dates = _courbes_indexees()["dates"].get(pays)
    return [pd.Timestamp(d) for d in dates[::-1]] if dates is not None else []


def date_courbe_applicable(pays: str, date: pd.Timestamp) -> pd.Timestamp | None:
    """Dernière courbe publiée à la date donnée ou avant (celle qu'un opérateur
    aurait effectivement eue sous les yeux ce jour-là)."""
    dates = _courbes_indexees()["dates"].get(pays)
    if dates is None or not len(dates):
        return None
    position = np.searchsorted(dates, np.datetime64(pd.Timestamp(date)), "right") - 1
    return pd.Timestamp(dates[position]) if position >= 0 else None


@functools.lru_cache(maxsize=4096)
def points_publies(pays: str, date_courbe: pd.Timestamp,
                   niveau: str = NIVEAU_OFFICIELLE) -> pd.DataFrame:
    """Points bruts publiés pour (pays, date), colonnes `Maturité` / `Taux`."""
    colonne = _COLONNE_NIVEAU.get(niveau, _COLONNE_NIVEAU[NIVEAU_OFFICIELLE])
    extrait = _courbes_indexees()["groupes"].get((pays, pd.Timestamp(date_courbe)))
    if extrait is None:
        return pd.DataFrame(columns=["Maturité", "Taux"])
    extrait = extrait[["Maturité (années)", colonne]].dropna()
    extrait = extrait.rename(columns={"Maturité (années)": "Maturité", colonne: "Taux"})
    return (extrait.groupby("Maturité", as_index=False)["Taux"].mean()
            .sort_values("Maturité").reset_index(drop=True))


@functools.lru_cache(maxsize=1)
def _adjudications_indexees() -> dict:
    """Adjudications passées exploitables, en tableaux numpy triés par pays.

    Même motif que `_courbes_indexees` : chaque point d'ancrage refiltrait tout
    le fichier primaire, ce qui devenait le poste dominant dès qu'on
    reconstruisait plusieurs centaines de courbes.
    """
    primaire = chargement.emissions_primaire()
    retenues = primaire[
        (primaire["Catégorie"] == "Passée")
        & primaire["Date de l'opération"].notna()
        & (primaire["Maturité (années)"] > 0)
        & primaire["Rendement moyen pondéré (déc.)"].notna()]
    index = {}
    for pays, bloc in retenues.groupby("Pays"):
        bloc = bloc.sort_values("Date de l'opération")
        poids = pd.to_numeric(bloc["Montant retenu (millions FCFA)"],
                              errors="coerce").abs().fillna(0.0).to_numpy(float)
        index[pays] = {
            "dates": bloc["Date de l'opération"].to_numpy("datetime64[ns]"),
            "maturites": bloc["Maturité (années)"].to_numpy(float),
            "taux": bloc["Rendement moyen pondéré (déc.)"].to_numpy(float),
            # Les montants retenus négatifs de la source sont ramenés en valeur
            # absolue pour la seule pondération ; à défaut de montant, poids 1.
            "poids": np.where(poids > 0, poids, 1.0),
        }
    return index


def points_ancrage_bat(pays: str, date_courbe: pd.Timestamp,
                       params: ParametresCourbe) -> pd.DataFrame:
    """Points de court terme déduits des adjudications réellement servies.

    Le lissage source rate le clearing du court terme : sur 272 comparaisons à
    3 mois, l'écart adjudication - courbe a un écart-type de 162 pb. Les
    adjudications sont un prix, pas une estimation ; on les préfère sur ce
    segment quand elles sont assez nombreuses.
    """
    vide = pd.DataFrame(columns=["Maturité", "Taux", "Observations"])
    donnees = _adjudications_indexees().get(pays)
    if donnees is None:
        return vide

    # Grille standard du court terme (3, 6, 9, 12 mois).
    tranches = np.array([0.25, 0.5, 0.75, 1.0])
    tranches = tranches[tranches <= params.ancrage_maturite_max]
    if not len(tranches):
        return vide

    fin = np.datetime64(pd.Timestamp(date_courbe))
    debut = fin - np.timedelta64(params.ancrage_fenetre_jours, "D")
    debut_i = np.searchsorted(donnees["dates"], debut, "left")
    fin_i = np.searchsorted(donnees["dates"], fin, "right")
    if fin_i <= debut_i:
        return vide

    maturites = donnees["maturites"][debut_i:fin_i]
    garde = maturites <= params.ancrage_maturite_max
    if not garde.any():
        return vide
    maturites = maturites[garde]
    taux = donnees["taux"][debut_i:fin_i][garde]
    poids = donnees["poids"][debut_i:fin_i][garde]

    indices = np.abs(maturites[:, None] - tranches).argmin(axis=1)
    observations = np.bincount(indices, minlength=len(tranches))
    somme_poids = np.bincount(indices, weights=poids, minlength=len(tranches))
    somme_taux = np.bincount(indices, weights=taux * poids, minlength=len(tranches))
    with np.errstate(invalid="ignore", divide="ignore"):
        moyennes = somme_taux / somme_poids

    retenus = observations >= params.ancrage_min_observations
    if not retenus.any():
        return vide
    return pd.DataFrame({
        "Maturité": tranches[retenus],
        "Taux": moyennes[retenus],
        "Observations": observations[retenus].astype(float),
    })


# --------------------------------------------------------------------------
# Construction de la courbe
# --------------------------------------------------------------------------
@functools.lru_cache(maxsize=8192)
def _construire_courbe_memo(pays: str, date_courbe: pd.Timestamp, niveau: str,
                            params: ParametresCourbe) -> pd.DataFrame:
    """Construction effective, mémoïsée sur (pays, date de courbe, niveau, réglages).

    `ParametresCourbe` est un dataclass gelé, donc hachable : changer un réglage
    invalide naturellement l'entrée de cache. Sans cette mémoïsation, tracer un
    historique long revenait à reconstruire plusieurs milliers de courbes à
    chaque interaction.
    """
    if niveau in _COLONNE_NIVEAU:
        return points_publies(pays, date_courbe, niveau).assign(Origine="Publié")

    publies = points_publies(pays, date_courbe, NIVEAU_OFFICIELLE)
    if publies.empty:
        return pd.DataFrame(columns=["Maturité", "Taux", "Origine"])

    noeuds = publies.assign(Origine="Publié")
    if params.ancrage_bat:
        ancrages = points_ancrage_bat(pays, date_courbe, params)
        for _, point in ancrages.iterrows():
            masque = np.isclose(noeuds["Maturité"], point["Maturité"])
            if masque.any() and params.ancrage_poids < 1.0:
                melange = ((1 - params.ancrage_poids) * noeuds.loc[masque, "Taux"].iloc[0]
                           + params.ancrage_poids * point["Taux"])
                noeuds.loc[masque, ["Taux", "Origine"]] = [melange, "Ancré (BAT)"]
            elif masque.any():
                noeuds.loc[masque, ["Taux", "Origine"]] = [point["Taux"], "Ancré (BAT)"]
            else:
                noeuds = pd.concat([noeuds, pd.DataFrame([{
                    "Maturité": point["Maturité"], "Taux": point["Taux"],
                    "Origine": "Ancré (BAT)"}])], ignore_index=True)
        noeuds = noeuds.sort_values("Maturité").reset_index(drop=True)

    x = noeuds["Maturité"].to_numpy(dtype=float)
    y = noeuds["Taux"].to_numpy(dtype=float)
    cible = grille(params)

    if params.interpolateur == "lineaire":
        taux = np.interp(cible, x, y)
    elif params.interpolateur == "nss":
        modele = ajuster_nss(x, y)
        taux = _evaluer_nss(modele, cible) if modele else np.interp(cible, x, y)
    else:
        taux = _evaluer_hermite(x, y, _pentes_pchip(x, y), cible)

    # Au-delà du dernier point publié, Hermite et l'interpolation linéaire
    # prolongent à plat, ce qui sous-estime le risque de duration longue.
    if params.extrapolation == "nss" and params.interpolateur != "nss":
        au_dela = cible > x[-1]
        if au_dela.any():
            modele = ajuster_nss(x, y)
            if modele is not None:
                taux = np.where(au_dela, _evaluer_nss(modele, cible), taux)

    taux = np.clip(taux, params.taux_min, params.taux_max)
    origines = np.full(len(cible), "Interpolé", dtype=object)
    for _, point in noeuds.iterrows():
        proche = np.isclose(cible, point["Maturité"], atol=params.pas / 2)
        origines[proche] = point["Origine"]
    origines[cible > x[-1]] = "Extrapolé"
    return pd.DataFrame({"Maturité": cible, "Taux": taux, "Origine": origines})


def construire_courbe(pays: str, date: pd.Timestamp,
                      niveau: str = NIVEAU_OFFICIELLE,
                      params: ParametresCourbe | None = None) -> pd.DataFrame:
    """Courbe exploitable pour (pays, date), au niveau de lecture demandé.

    Renvoie un DataFrame `Maturité` / `Taux` / `Origine`, vide si aucune courbe
    n'a été publiée à cette date ou avant. `Origine` distingue les points
    publiés, les points d'ancrage et les points interpolés — c'est ce qui permet
    d'afficher honnêtement ce qui est observé et ce qui est reconstruit.
    """
    params = params or ParametresCourbe()
    date_courbe = date_courbe_applicable(pays, date)
    if date_courbe is None:
        return pd.DataFrame(columns=["Maturité", "Taux", "Origine"])

    # Mémoïsé sur la date de courbe applicable, pas sur la date demandée :
    # deux jours d'une même semaine partagent la même courbe publiée.
    return _construire_courbe_memo(pays, date_courbe, niveau, params)


class Interpolateur:
    """Évalue un taux de courbe pour des couples (pays, date, maturité) en masse.

    Les courbes construites sont mises en cache par (pays, date de courbe), ce
    qui rend l'appariement des 7 000 lignes du marché secondaire instantané.
    """

    def __init__(self, niveau: str = NIVEAU_OFFICIELLE,
                 params: ParametresCourbe | None = None):
        self.niveau = niveau
        self.params = params or ParametresCourbe()
        self._cache: dict = {}

    def _courbe(self, pays: str, date_courbe: pd.Timestamp) -> pd.DataFrame:
        cle = (pays, date_courbe)
        if cle not in self._cache:
            self._cache[cle] = construire_courbe(
                pays, date_courbe, self.niveau, self.params)
        return self._cache[cle]

    def taux_a_date_courbe(self, pays: str, date_courbe: pd.Timestamp,
                           maturites) -> np.ndarray:
        """Taux interpolés sur une courbe dont la date de publication est connue."""
        maturites = np.atleast_1d(np.asarray(maturites, dtype=float))
        courbe = self._courbe(pays, date_courbe)
        if courbe.empty:
            return np.full(len(maturites), np.nan)
        return np.interp(maturites, courbe["Maturité"], courbe["Taux"],
                         left=courbe["Taux"].iloc[0], right=courbe["Taux"].iloc[-1])

    def taux(self, pays: str, date: pd.Timestamp, maturites) -> np.ndarray:
        """Taux interpolés pour un pays, à une date, sur un vecteur de maturités."""
        date_courbe = date_courbe_applicable(pays, date)
        if date_courbe is None:
            return np.full(len(np.atleast_1d(maturites)), np.nan)
        return self.taux_a_date_courbe(pays, date_courbe, maturites)

    def taux_par_ligne(self, pays: pd.Series, dates: pd.Series,
                       maturites: pd.Series) -> np.ndarray:
        """Version vectorisée sur un DataFrame : un taux par ligne."""
        resultat = np.full(len(pays), np.nan)
        cadre = pd.DataFrame({"pays": pays.values, "date": pd.to_datetime(dates).values,
                              "mat": maturites.values})
        for (p, d), groupe in cadre.groupby(["pays", "date"], dropna=True):
            if not isinstance(p, str):
                continue
            resultat[groupe.index] = self.taux(p, d, groupe["mat"].values)
        return resultat


# --------------------------------------------------------------------------
# Diagnostic
# --------------------------------------------------------------------------
def fraicheur_courbes(params: ParametresCourbe | None = None) -> pd.DataFrame:
    """Ancienneté et immobilisme de la courbe, pays par pays.

    Chaque pays est strictement inchangé d'une semaine à l'autre dans 36 % à
    76 % des cas selon le pays : sans ce diagnostic affiché, on lit comme un
    signal de marché ce qui n'est qu'une absence de mise à jour.
    """
    params = params or ParametresCourbe()
    courbes = chargement.courbes_taux()
    reference = chargement.date_reference()
    lignes = []
    for pays, groupe in courbes.groupby("Pays"):
        if not isinstance(pays, str):
            continue
        pivot = groupe.pivot_table(index="Date", columns="Maturité (années)",
                                   values="Taux après lissage").sort_index()
        variations = pivot.diff().abs().max(axis=1).dropna()
        inchangees = (variations == 0)
        # Nombre de publications consécutives sans le moindre mouvement.
        gel = 0
        for valeur in inchangees.values[::-1]:
            if valeur:
                gel += 1
            else:
                break
        derniere = pivot.index.max()
        lignes.append({
            "Pays": pays,
            "Dernière courbe": derniere,
            "Ancienneté (jours)": (reference - derniere).days,
            "Publications figées": gel,
            "Part de semaines inchangées": float(inchangees.mean()),
            "Points publiés": int(pivot.loc[derniere].notna().sum()),
            "Périmée": (reference - derniere).days > params.seuil_fraicheur_jours,
        })
    return pd.DataFrame(lignes).sort_values("Pays").reset_index(drop=True)


def _rugosite(taux: np.ndarray) -> float:
    """Moyenne des différences secondes, en pb. Mesure le bruit d'une courbe."""
    valeurs = np.asarray(taux, dtype=float)
    valeurs = valeurs[~np.isnan(valeurs)]
    if len(valeurs) < 3:
        return float("nan")
    return float(np.abs(np.diff(valeurs, 2)).mean() * 10_000)


def _saut_max(taux: np.ndarray) -> float:
    """Plus grand écart entre deux maturités voisines, en pb."""
    valeurs = np.asarray(taux, dtype=float)
    valeurs = valeurs[~np.isnan(valeurs)]
    if len(valeurs) < 2:
        return float("nan")
    return float(np.abs(np.diff(valeurs)).max() * 10_000)


def diagnostic_courbe(pays: str, date: pd.Timestamp,
                      params: ParametresCourbe | None = None) -> dict:
    """Mesures de qualité d'une courbe, niveau par niveau.

    Sert à objectiver le débat « faut-il reconstruire ? » plutôt qu'à en juger
    à l'œil : la rugosité dit combien de bruit reste, le saut maximum et
    l'inversion 3 mois / 1 an disent si le segment court est plausible.
    """
    params = params or ParametresCourbe()
    date_courbe = date_courbe_applicable(pays, date)
    if date_courbe is None:
        return {}

    brut = points_publies(pays, date_courbe, NIVEAU_BRUT)
    officielle = points_publies(pays, date_courbe, NIVEAU_OFFICIELLE)
    reconstruite = construire_courbe(pays, date_courbe, NIVEAU_RECONSTRUITE, params)
    ancrages = (points_ancrage_bat(pays, date_courbe, params)
                if params.ancrage_bat else pd.DataFrame())

    def _point(source: pd.DataFrame, maturite: float) -> float:
        if source.empty:
            return float("nan")
        proche = source[np.isclose(source["Maturité"], maturite, atol=1e-6)]
        return float(proche["Taux"].iloc[0]) if not proche.empty else float("nan")

    trois_mois, un_an = _point(officielle, 0.25), _point(officielle, 1.0)
    return {
        "Date de courbe": date_courbe,
        "Points publiés": len(officielle),
        "Rugosité brut (pb)": _rugosite(brut["Taux"].to_numpy()),
        "Rugosité officielle (pb)": _rugosite(officielle["Taux"].to_numpy()),
        "Rugosité reconstruite (pb)": _rugosite(reconstruite["Taux"].to_numpy()),
        "Saut max officielle (pb)": _saut_max(officielle["Taux"].to_numpy()),
        "Saut max reconstruit (pb)": _saut_max(reconstruite["Taux"].to_numpy()),
        "Inversion 3 mois / 1 an (pb)": (
            (trois_mois - un_an) * 10_000
            if not (np.isnan(trois_mois) or np.isnan(un_an)) else float("nan")),
        "Maturité max publiée": (float(officielle["Maturité"].max())
                                 if not officielle.empty else float("nan")),
        "Points d'ancrage retenus": len(ancrages),
        "Ancrages": ancrages,
    }


def serie_temporelle(pays: list[str] | str, maturite: float,
                     niveau: str = NIVEAU_OFFICIELLE,
                     params: ParametresCourbe | None = None,
                     depuis: pd.Timestamp | None = None) -> pd.DataFrame:
    """Historique du taux à une maturité donnée, pour un ou plusieurs pays.

    Le taux est interpolé à la maturité demandée sur chaque courbe publiée : la
    grille source est trouée, il n'existe pas de série toute faite (le point
    10 ans n'est publié que sur 48 % des courbes).
    """
    params = params or ParametresCourbe()
    liste = [pays] if isinstance(pays, str) else list(pays)
    interpolateur = Interpolateur(niveau, params)
    lignes = []
    for nom in liste:
        for date in dates_disponibles(nom):
            if depuis is not None and date < pd.Timestamp(depuis):
                continue
            # Ces dates sont par construction des dates de publication : inutile
            # de repasser par la recherche de la courbe applicable.
            valeur = interpolateur.taux_a_date_courbe(nom, date, [maturite])[0]
            if not np.isnan(valeur):
                lignes.append({"Date": date, "Pays": nom, "Taux": valeur})
    if not lignes:
        return pd.DataFrame(columns=["Date", "Pays", "Taux"])
    return pd.DataFrame(lignes).sort_values(["Pays", "Date"]).reset_index(drop=True)


def comparer_niveaux(pays: str, date: pd.Timestamp,
                     params: ParametresCourbe | None = None) -> pd.DataFrame:
    """Courbe officielle et courbe reconstruite côte à côte, avec l'écart en pb."""
    params = params or ParametresCourbe()
    reconstruite = construire_courbe(pays, date, NIVEAU_RECONSTRUITE, params)
    if reconstruite.empty:
        return reconstruite
    date_courbe = date_courbe_applicable(pays, date)
    officielle = points_publies(pays, date_courbe, NIVEAU_OFFICIELLE)
    brut = points_publies(pays, date_courbe, NIVEAU_BRUT)
    resultat = reconstruite.rename(columns={"Taux": "Taux reconstruit"})
    resultat["Taux officiel"] = np.interp(
        resultat["Maturité"], officielle["Maturité"], officielle["Taux"],
        left=np.nan, right=np.nan)
    if not brut.empty:
        resultat["Taux brut"] = np.interp(
            resultat["Maturité"], brut["Maturité"], brut["Taux"],
            left=np.nan, right=np.nan)
    resultat["Écart reconstruit - officiel (pb)"] = (
        (resultat["Taux reconstruit"] - resultat["Taux officiel"]) * 10_000)
    return resultat
