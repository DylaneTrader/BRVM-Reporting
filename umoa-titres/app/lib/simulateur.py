# -*- coding: utf-8 -*-
"""Simulateur obligataire : échéancier daté, prix, sensibilité et horizon.

`scripts/finance.py` calcule les analytiques du marché secondaire à partir d'une
seule maturité résiduelle exprimée en années : c'est suffisant pour valoriser
7 000 lignes en masse, insuffisant pour instruire une décision sur un titre. Ce
module reprend les mêmes conventions mais travaille sur des **dates réelles** :

  * échéancier construit par anniversaires successifs depuis l'échéance, ce qui
    place correctement le premier coupon (fractionnaire) et les amortissements ;
  * amortissement **in fine**, **constant** (linéaire) ou par **annuités
    constantes**, avec différé — les trois régimes présents dans les sources ;
  * prix pied de coupon et prix coupon couru inclus, exprimés en pourcentage du
    **nominal résiduel** : sur un titre amortissable, le pair n'est plus 100 %
    du nominal d'origine et confondre les deux fausse tout le raisonnement ;
  * rendement actuariel résolu par bissection, base **Exact/365, composition
    annuelle** — la convention du « Rendement moyen » publié par UMOA-Titres.

L'analyse d'horizon est le cœur de la décision. Elle sépare trois effets qui
s'additionnent exactement (coupons perçus, réinvestissement de ces coupons,
effet capital), puis casse l'effet capital en portage à taux inchangé et effet
taux. Aucune de ces grandeurs n'est une prévision : ce sont des scénarios, et
le point d'indifférence (le choc de taux qui annule le gain, le taux de
réinvestissement qui égalise vendre et conserver) est ce que le module cherche à
rendre lisible, plutôt qu'une recommandation.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import chargement, courbes as mod_courbes

#: Nominal unitaire de place (BRVM et UMOA-Titres cotent par 10 000 FCFA).
NOMINAL_UNITAIRE = 10_000.0

#: Base de calcul du temps, commune à tout le module.
BASE_JOURS = 365.0

AMORTISSEMENT_IN_FINE = "IF"
AMORTISSEMENT_CONSTANT = "CA"
#: « AN » et non « AC » : le marché secondaire écrit « AC » pour un
#: amortissement constant, la collision de codes serait silencieuse et fausse.
AMORTISSEMENT_ANNUITES = "AN"

LIBELLES_AMORTISSEMENT = {
    AMORTISSEMENT_IN_FINE: "In fine (remboursement à l'échéance)",
    AMORTISSEMENT_CONSTANT: "Amortissement constant du capital (linéaire)",
    AMORTISSEMENT_ANNUITES: "Annuités constantes",
}

#: Graphies rencontrées dans les sources et codes canoniques -> régime retenu.
_ALIAS_AMORTISSEMENT = {
    "if": AMORTISSEMENT_IN_FINE, "in fine": AMORTISSEMENT_IN_FINE,
    "0": AMORTISSEMENT_IN_FINE, "": AMORTISSEMENT_IN_FINE,
    "ca": AMORTISSEMENT_CONSTANT, "acd": AMORTISSEMENT_CONSTANT,
    "ac": AMORTISSEMENT_CONSTANT,
    "lineaire": AMORTISSEMENT_CONSTANT, "linéaire": AMORTISSEMENT_CONSTANT,
    "constant": AMORTISSEMENT_CONSTANT,
    "an": AMORTISSEMENT_ANNUITES, "anc": AMORTISSEMENT_ANNUITES,
    "annuites constantes": AMORTISSEMENT_ANNUITES,
    "annuités constantes": AMORTISSEMENT_ANNUITES,
}


def normaliser_amortissement(valeur) -> str:
    """« ACD », « Linéaire », « In Fine »… ramenés aux trois régimes connus."""
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return AMORTISSEMENT_IN_FINE
    return _ALIAS_AMORTISSEMENT.get(str(valeur).strip().lower(),
                                    AMORTISSEMENT_IN_FINE)


@dataclass(frozen=True)
class Titre:
    """Caractéristiques contractuelles d'une souche.

    `differe_annees` compte les périodes pendant lesquelles seul l'intérêt est
    versé ; il n'a de sens que pour les régimes amortissables.
    """

    echeance: pd.Timestamp
    coupon: float = 0.06
    date_jouissance: pd.Timestamp | None = None
    amortissement: str = AMORTISSEMENT_IN_FINE
    differe_annees: int = 0
    frequence: int = 1
    nominal: float = NOMINAL_UNITAIRE
    pays: str | None = None
    libelle: str | None = None
    isin: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "echeance", pd.Timestamp(self.echeance).normalize())
        if self.date_jouissance is not None:
            object.__setattr__(self, "date_jouissance",
                               pd.Timestamp(self.date_jouissance).normalize())
        object.__setattr__(self, "amortissement",
                           normaliser_amortissement(self.amortissement))

    @property
    def jouissance_connue(self) -> bool:
        return self.date_jouissance is not None

    @property
    def duree_initiale(self) -> float:
        if not self.jouissance_connue:
            return np.nan
        return (self.echeance - self.date_jouissance).days / BASE_JOURS

    @property
    def zero_coupon(self) -> bool:
        """Un BAT, et rien d'autre.

        Un titre à un an de durée initiale ne verse qu'un flux, mais ce flux
        porte un intérêt : le confondre avec un zéro-coupon reviendrait à
        l'émettre au pair et à ne jamais payer son coupon.
        """
        return not self.coupon


# --------------------------------------------------------------------------
# Échéancier
# --------------------------------------------------------------------------
def _origine(titre: Titre, depuis: pd.Timestamp | None = None) -> pd.Timestamp:
    """Point de départ de l'échéancier.

    La date de jouissance quand elle est connue. Sinon — un cas isolé du
    référentiel, mais qui doit rester calculable — on part de la veille de la
    date d'analyse : tous les flux à venir sont alors correctement datés, au
    prix d'un coupon couru inconnu (traité comme nul) et, sur un amortissable,
    d'un profil de remboursement supposé plutôt que lu.
    """
    if titre.jouissance_connue:
        return titre.date_jouissance
    if depuis is not None:
        return pd.Timestamp(depuis).normalize() - pd.Timedelta(days=1)
    return titre.echeance - pd.DateOffset(years=1)


def _dates_depuis_origine(titre: Titre, origine: pd.Timestamp
                          ) -> list[pd.Timestamp]:
    """Dates de tombée postérieures à une origine déjà résolue."""
    pas = int(round(12 / max(titre.frequence, 1)))
    dates, courante = [], titre.echeance
    while courante > origine:
        dates.append(courante)
        courante = courante - pd.DateOffset(months=pas)
        if len(dates) > 600:  # garde-fou : échéance aberrante
            break
    return sorted(dates)


def dates_flux(titre: Titre, depuis: pd.Timestamp | None = None
               ) -> list[pd.Timestamp]:
    """Dates de tombée, de la première à l'échéance.

    Construites **à rebours depuis l'échéance** : c'est la seule façon d'obtenir
    un dernier flux tombant exactement à l'échéance, et cela reporte
    naturellement l'irrégularité sur la première période (coupon rompu), comme
    le fait le contrat.
    """
    return _dates_depuis_origine(titre, _origine(titre, depuis))


@functools.lru_cache(maxsize=8192)
def _plan(titre: Titre, origine: pd.Timestamp) -> tuple:
    """Échéancier sous forme de tableaux numpy, mémoïsé sur (titre, origine).

    Le cœur du module est appelé des milliers de fois par page : chaque
    bissection revalorise le même échéancier des dizaines de fois, et la
    recherche d'un point d'indifférence en enchaîne cent vingt. Reconstruire un
    DataFrame à chaque passage coûtait plusieurs secondes par interaction ;
    `Titre` étant gelé, donc hachable, la mémoïsation est immédiate.
    """
    dates = _dates_depuis_origine(titre, origine)
    if not dates:
        vide = np.empty(0, dtype=float)
        return np.empty(0, dtype="datetime64[ns]"), vide, vide, vide, vide

    n = len(dates)
    taux_periodique = titre.coupon / max(titre.frequence, 1)
    if titre.zero_coupon or titre.amortissement == AMORTISSEMENT_IN_FINE:
        amortissements = [0.0] * (n - 1) + [1.0]
    else:
        differe = int(min(max(titre.differe_annees, 0) * titre.frequence, n - 1))
        restantes = n - differe
        if titre.amortissement == AMORTISSEMENT_CONSTANT:
            amortissements = [0.0] * differe + [1.0 / restantes] * restantes
        else:  # annuités constantes sur la période non différée
            if taux_periodique <= 0:
                amortissements = [0.0] * differe + [1.0 / restantes] * restantes
            else:
                annuite = taux_periodique / (1 - (1 + taux_periodique) ** -restantes)
                amortissements, encours = [0.0] * differe, 1.0
                for _ in range(restantes):
                    part = annuite - taux_periodique * encours
                    part = min(part, encours)
                    amortissements.append(part)
                    encours -= part
                amortissements[-1] += encours  # solde l'arrondi sur le dernier flux

    encours_debut, interets, encours = [], [], 1.0
    for amortissement in amortissements:
        encours_debut.append(encours)
        # BAT : intérêt précompté, un flux unique de 1 à l'échéance.
        interets.append(0.0 if titre.zero_coupon else taux_periodique * encours)
        encours -= amortissement

    amortissements = np.asarray(amortissements, dtype=float)
    interets = np.asarray(interets, dtype=float)
    return (pd.DatetimeIndex(dates).to_numpy(),
            np.asarray(encours_debut, dtype=float), interets, amortissements,
            interets + amortissements)


def echeancier(titre: Titre, depuis: pd.Timestamp | None = None) -> pd.DataFrame:
    """Échéancier contractuel complet, pour un nominal d'origine de 1.

    Colonnes : `Date`, `Encours début`, `Intérêt`, `Amortissement`, `Flux`.
    Les montants sont exprimés en fraction du nominal **d'origine** ; la mise à
    l'échelle en pourcentage du nominal résiduel se fait au moment du prix.
    """
    dates, encours, interets, amortissements, flux = _plan(
        titre, _origine(titre, depuis))
    return pd.DataFrame({
        "Date": dates, "Encours début": encours, "Intérêt": interets,
        "Amortissement": amortissements, "Flux": flux,
    })


def _premiere_periode(titre: Titre, dates: list[pd.Timestamp],
                      date_reglement: pd.Timestamp,
                      origine: pd.Timestamp) -> tuple:
    """(début, fin) de la période de coupon courante à la date de règlement."""
    prochaine = next((d for d in dates if d > date_reglement), None)
    if prochaine is None:
        return None, None
    pas = int(round(12 / max(titre.frequence, 1)))
    precedente = prochaine - pd.DateOffset(months=pas)
    return max(precedente, origine), prochaine


@functools.lru_cache(maxsize=8192)
def _flux_apres(titre: Titre, date_reglement: pd.Timestamp,
                origine: pd.Timestamp) -> tuple:
    """(temps, flux, intérêts, amortissements, encours résiduel) après une date.

    Mémoïsé au même titre que `_plan` : une bissection interroge cent fois le
    même découpage, seul le taux d'actualisation change.
    """
    dates, _, interets, amortissements, flux = _plan(titre, origine)
    if not len(dates):
        vide = np.empty(0, dtype=float)
        return vide, vide, vide, vide, 0.0
    garde = dates > np.datetime64(date_reglement)
    temps = ((dates[garde] - np.datetime64(date_reglement))
             / np.timedelta64(1, "D")).astype(float) / BASE_JOURS
    return (temps, flux[garde], interets[garde], amortissements[garde],
            float(amortissements[garde].sum()))


def encours_residuel(titre: Titre, date_reglement: pd.Timestamp,
                     depuis: pd.Timestamp | None = None) -> float:
    """Part du nominal d'origine encore vivante à la date de règlement.

    Vaut 1 pour un in fine, moins pour un amortissable déjà entamé : c'est le
    dénominateur de toutes les cotations en pourcentage.
    """
    date_reglement = pd.Timestamp(date_reglement).normalize()
    origine = _origine(titre, depuis if depuis is not None else date_reglement)
    return _flux_apres(titre, date_reglement, origine)[4]


def coupon_couru(titre: Titre, date_reglement: pd.Timestamp,
                 depuis: pd.Timestamp | None = None) -> float:
    """Coupon couru en pourcentage du nominal résiduel, base Exact/365.

    Nul par construction quand la jouissance est inconnue : mieux vaut un couru
    absent qu'un couru inventé sur une période de référence supposée.
    """
    if titre.zero_coupon or not titre.jouissance_connue:
        return 0.0
    date_reglement = pd.Timestamp(date_reglement).normalize()
    origine = _origine(titre, depuis if depuis is not None else date_reglement)
    dates = _dates_depuis_origine(titre, origine)
    debut, fin = _premiere_periode(titre, dates, date_reglement, origine)
    if debut is None or date_reglement <= debut:
        return 0.0
    jours = (date_reglement - debut).days
    duree = max((fin - debut).days, 1)
    # Le couru est calculé sur l'encours de la période, puis ramené au nominal
    # résiduel : les deux coïncident tant qu'aucun amortissement n'est intervenu
    # à l'intérieur de la période courante.
    return titre.coupon * min(jours / BASE_JOURS, duree / BASE_JOURS)


def flux_a_venir(titre: Titre, date_reglement: pd.Timestamp,
                 depuis: pd.Timestamp | None = None) -> pd.DataFrame:
    """Flux strictement postérieurs au règlement, avec leur temps actuariel."""
    date_reglement = pd.Timestamp(date_reglement).normalize()
    plan = echeancier(titre, depuis if depuis is not None else date_reglement)
    if plan.empty:
        return plan.assign(**{"Années": pd.Series(dtype=float)})
    a_venir = plan[plan["Date"] > date_reglement].copy()
    a_venir["Années"] = ((a_venir["Date"] - date_reglement).dt.days / BASE_JOURS)
    return a_venir.reset_index(drop=True)


# --------------------------------------------------------------------------
# Prix, rendement, sensibilité
# --------------------------------------------------------------------------
def prix_depuis_taux(titre: Titre, taux: float, date_reglement: pd.Timestamp,
                     depuis: pd.Timestamp | None = None) -> dict:
    """Prix pied de coupon et prix total, en pourcentage du nominal résiduel.

    Actualisation actuarielle annuelle : P = Σ CF·(1 + y)^(−t), t en années
    Exact/365. Le prix « total » (dirty) est ce qu'on décaisse réellement ; le
    prix « pied de coupon » (clean) est ce qui se cote.

    `depuis` fige l'origine de l'échéancier quand la jouissance est inconnue :
    une même analyse doit valoriser plusieurs dates sur un échéancier unique,
    faute de quoi le titre changerait de nature d'une date à l'autre.
    """
    vide = {"Prix total": np.nan, "Prix pied de coupon": np.nan,
            "Coupon couru": np.nan, "Encours résiduel": np.nan}
    if taux is None or pd.isna(taux) or taux <= -0.99:
        return vide
    date_reglement = pd.Timestamp(date_reglement).normalize()
    origine = _origine(titre, depuis if depuis is not None else date_reglement)
    temps, flux, _, _, encours = _flux_apres(titre, date_reglement, origine)
    if not len(flux) or encours <= 0:
        return vide
    total = float((flux * (1 + taux) ** -temps).sum()) / encours
    couru = coupon_couru(titre, date_reglement, depuis)
    return {"Prix total": total, "Prix pied de coupon": total - couru,
            "Coupon couru": couru, "Encours résiduel": encours}


def taux_depuis_prix(titre: Titre, prix: float, date_reglement: pd.Timestamp,
                     pied_de_coupon: bool = True,
                     depuis: pd.Timestamp | None = None) -> float:
    """Rendement actuariel résolu par bissection.

    Le prix étant strictement décroissant en taux, la bissection converge
    toujours et sans dérivée : plus lent qu'un Newton, mais insensible aux
    échéanciers dégénérés (différé long, dernier flux unique) où la dérivée
    s'annule numériquement.
    """
    if prix is None or pd.isna(prix) or prix <= 0:
        return np.nan
    date_reglement = pd.Timestamp(date_reglement).normalize()
    cible = prix + (coupon_couru(titre, date_reglement, depuis)
                    if pied_de_coupon else 0.0)
    origine = _origine(titre, depuis if depuis is not None else date_reglement)
    if not len(_flux_apres(titre, date_reglement, origine)[1]):
        return np.nan

    def _ecart(taux: float) -> float:
        return (prix_depuis_taux(titre, taux, date_reglement, depuis)["Prix total"]
                - cible)

    bas, haut = -0.5, 3.0
    valeur_bas, valeur_haut = _ecart(bas), _ecart(haut)
    if np.isnan(valeur_bas) or np.isnan(valeur_haut) or valeur_bas * valeur_haut > 0:
        return np.nan
    for _ in range(200):
        milieu = (bas + haut) / 2
        valeur = _ecart(milieu)
        if abs(valeur) < 1e-12 or (haut - bas) < 1e-12:
            return milieu
        if valeur_bas * valeur > 0:
            bas, valeur_bas = milieu, valeur
        else:
            haut = milieu
    return (bas + haut) / 2


def metriques(titre: Titre, taux: float, date_reglement: pd.Timestamp,
              depuis: pd.Timestamp | None = None) -> dict:
    """Prix, durations, convexité et DV01 pour un couple (titre, rendement).

    Durations et convexité sont calculées sur le prix total (coupon couru
    inclus), seule base cohérente avec la valeur réellement exposée.
    """
    date_reglement = pd.Timestamp(date_reglement).normalize()
    resultat = prix_depuis_taux(titre, taux, date_reglement, depuis)
    vide = {**resultat, "Duration Macaulay": np.nan, "Duration modifiée": np.nan,
            "Convexité": np.nan, "DV01 (pour 10 000 FCFA)": np.nan,
            "Maturité résiduelle (années)": np.nan,
            "Maturité moyenne pondérée (années)": np.nan}
    origine = _origine(titre, depuis if depuis is not None else date_reglement)
    temps, montants, _, amortissements, _ = _flux_apres(
        titre, date_reglement, origine)
    if not len(montants) or pd.isna(resultat["Prix total"]):
        return vide

    actualises = montants * (1 + taux) ** (-temps)
    valeur = actualises.sum()
    macaulay = float((temps * actualises).sum() / valeur)
    modifiee = macaulay / (1 + taux)
    convexite = float((temps * (temps + 1) * montants
                       * (1 + taux) ** (-temps - 2)).sum() / valeur)
    prix_total = resultat["Prix total"]
    # Maturité moyenne pondérée par les remboursements de principal : sur un
    # amortissable, c'est elle qui doit être lue face à la courbe, pas la date
    # d'échéance finale.
    vie_moyenne = (float((temps * amortissements).sum() / amortissements.sum())
                   if amortissements.sum() > 0 else float(temps[-1]))
    return {
        **resultat,
        "Duration Macaulay": macaulay,
        "Duration modifiée": modifiee,
        "Convexité": convexite,
        "DV01 (pour 10 000 FCFA)": modifiee * prix_total * NOMINAL_UNITAIRE * 1e-4,
        "Maturité résiduelle (années)": float(temps[-1]),
        "Maturité moyenne pondérée (années)": vie_moyenne,
    }


def courbe_prix_taux(titre: Titre, date_reglement: pd.Timestamp,
                     taux_central: float, amplitude_pb: float = 300.0,
                     pas_pb: float = 25.0) -> pd.DataFrame:
    """Prix et variation relative pour une grille de rendements.

    Sert à montrer la convexité telle qu'elle est — la droite de la duration
    modifiée est tracée en regard, et l'écart entre les deux est précisément ce
    que la duration seule fait manquer.
    """
    if pd.isna(taux_central):
        return pd.DataFrame(columns=["Taux", "Choc (pb)", "Prix total",
                                     "Variation", "Variation (duration)"])
    reference = metriques(titre, taux_central, date_reglement)
    chocs = np.arange(-amplitude_pb, amplitude_pb + pas_pb, pas_pb)
    lignes = []
    for choc in chocs:
        taux = taux_central + choc / 10_000.0
        prix = prix_depuis_taux(titre, taux, date_reglement)["Prix total"]
        variation = prix / reference["Prix total"] - 1
        lignes.append({
            "Taux": taux, "Choc (pb)": float(choc), "Prix total": prix,
            "Variation": variation,
            "Variation (duration)": -reference["Duration modifiée"] * choc / 10_000.0,
        })
    return pd.DataFrame(lignes)


# --------------------------------------------------------------------------
# Analyse d'horizon
# --------------------------------------------------------------------------
def analyse_horizon(titre: Titre, date_reglement: pd.Timestamp,
                    taux_achat: float, date_horizon: pd.Timestamp,
                    taux_horizon: float, taux_reinvestissement: float,
                    montant_nominal: float = NOMINAL_UNITAIRE,
                    prix_achat_total: float | None = None) -> dict:
    """Valeur à l'horizon d'une position, décomposée en effets additifs.

    Trois briques qui somment exactement au gain :

      * **coupons perçus** — intérêts encaissés entre le règlement et l'horizon ;
      * **effet de réinvestissement** — ce que ces flux rapportent une fois
        replacés au taux retenu, et rien d'autre ;
      * **effet capital** — valeur de revente augmentée des amortissements
        perçus, moins l'investissement initial ; lui-même scindé en portage à
        taux inchangé et effet taux.

    `prix_achat_total` permet de partir d'un prix réellement payé plutôt que du
    prix théorique au taux d'achat : pour un titre déjà détenu, c'est le prix
    historique qui commande le résultat comptable.
    """
    date_reglement = pd.Timestamp(date_reglement).normalize()
    date_horizon = pd.Timestamp(date_horizon).normalize()
    duree = (date_horizon - date_reglement).days / BASE_JOURS
    vide = {"Durée (années)": duree, "Valeur finale": np.nan,
            "Investissement": np.nan, "Gain": np.nan, "Rendement total": np.nan}
    if duree <= 0:
        return vide

    # Toute l'analyse partage une même origine d'échéancier : la date de
    # règlement. Sans cela, un titre à jouissance inconnue verrait son plan de
    # flux changer entre la valorisation initiale et celle de l'horizon.
    origine = date_reglement
    encours_initial = encours_residuel(titre, date_reglement, origine)
    if encours_initial <= 0:
        return vide
    # Tout est calculé pour 1 F de nominal d'origine puis mis à l'échelle : le
    # montant saisi est un nominal *résiduel*, celui qu'on détient aujourd'hui.
    facteur = montant_nominal / encours_initial

    prix_initial = prix_depuis_taux(titre, taux_achat, date_reglement, origine)
    prix_paye = (prix_initial["Prix total"] if prix_achat_total is None
                 else prix_achat_total)
    if pd.isna(prix_paye):
        return vide
    investissement = prix_paye * montant_nominal

    temps, flux, interets, amorts, _ = _flux_apres(titre, date_reglement, origine)
    avant_horizon = temps <= duree + 1e-9
    temps_restant = duree - temps[avant_horizon]
    coupons = float(interets[avant_horizon].sum()) * facteur
    amortissements = float(amorts[avant_horizon].sum()) * facteur
    montants = flux[avant_horizon] * facteur
    valeur_capitalisee = float(
        (montants * (1 + taux_reinvestissement) ** temps_restant).sum())
    reinvestissement = valeur_capitalisee - float(montants.sum())

    encours_horizon = encours_residuel(titre, date_horizon, origine)
    nominal_horizon = encours_horizon * facteur
    if nominal_horizon > 0:
        revente = (prix_depuis_taux(titre, taux_horizon, date_horizon, origine)
                   ["Prix total"] * nominal_horizon)
        revente_inchange = (prix_depuis_taux(titre, taux_achat, date_horizon,
                                             origine)["Prix total"]
                            * nominal_horizon)
    else:  # l'horizon dépasse l'échéance : plus rien à revendre
        revente = revente_inchange = 0.0

    valeur_finale = valeur_capitalisee + revente
    gain = valeur_finale - investissement
    effet_capital = revente + amortissements - investissement
    portage = revente_inchange + amortissements - investissement
    return {
        "Durée (années)": duree,
        "Investissement": investissement,
        "Prix payé": prix_paye,
        "Coupons perçus": coupons,
        "Amortissements perçus": amortissements,
        "Effet de réinvestissement": reinvestissement,
        "Valeur de revente": revente,
        "Valeur de revente à taux inchangé": revente_inchange,
        "Effet capital": effet_capital,
        "Effet de portage": portage,
        "Effet taux": effet_capital - portage,
        "Valeur finale": valeur_finale,
        "Gain": gain,
        "Rendement total": ((valeur_finale / investissement) ** (1 / duree) - 1
                            if investissement > 0 and valeur_finale > 0 else np.nan),
        "Rendement cumulé": (valeur_finale / investissement - 1
                             if investissement > 0 else np.nan),
        "Nominal résiduel à l'horizon": nominal_horizon,
    }


def matrice_horizon(titre: Titre, date_reglement: pd.Timestamp,
                    taux_achat: float, horizons_mois, chocs_pb,
                    taux_reinvestissement: float,
                    montant_nominal: float = NOMINAL_UNITAIRE,
                    prix_achat_total: float | None = None,
                    taux_marche: float | None = None) -> pd.DataFrame:
    """Rendement total annualisé pour une grille (horizon × choc de taux).

    `taux_marche` est le rendement de départ auquel s'applique le choc ; il
    diffère du taux d'achat dès que le titre est déjà détenu — le prix payé
    appartient au passé, le choc s'applique au marché d'aujourd'hui.
    """
    depart = taux_achat if taux_marche is None else taux_marche
    lignes = []
    for mois in horizons_mois:
        horizon = pd.Timestamp(date_reglement) + pd.DateOffset(months=int(mois))
        for choc in chocs_pb:
            resultat = analyse_horizon(
                titre, date_reglement, taux_achat, horizon, depart + choc / 10_000.0,
                taux_reinvestissement, montant_nominal, prix_achat_total)
            lignes.append({
                "Horizon (mois)": int(mois),
                "Horizon": horizon,
                "Choc (pb)": float(choc),
                "Rendement total": resultat["Rendement total"],
                "Gain": resultat["Gain"],
            })
    return pd.DataFrame(lignes)


def choc_indifference(titre: Titre, date_reglement: pd.Timestamp,
                      taux_achat: float, date_horizon: pd.Timestamp,
                      taux_reinvestissement: float,
                      montant_nominal: float = NOMINAL_UNITAIRE,
                      prix_achat_total: float | None = None,
                      taux_marche: float | None = None,
                      rendement_cible: float = 0.0) -> float:
    """Choc de taux, en pb, qui ramène le rendement total au niveau visé.

    C'est le « coussin de portage » : tant que les taux montent moins que ça
    sur l'horizon, la position reste au-dessus de la cible. Résolu par
    bissection sur le choc, le rendement total étant décroissant en taux.
    """
    depart = taux_achat if taux_marche is None else taux_marche

    def _ecart(choc_pb: float) -> float:
        resultat = analyse_horizon(
            titre, date_reglement, taux_achat,
            date_horizon, depart + choc_pb / 10_000.0, taux_reinvestissement,
            montant_nominal, prix_achat_total)
        rendement = resultat["Rendement total"]
        return np.nan if pd.isna(rendement) else rendement - rendement_cible

    bas, haut = -1_000.0, 3_000.0
    valeur_bas, valeur_haut = _ecart(bas), _ecart(haut)
    if np.isnan(valeur_bas) or np.isnan(valeur_haut) or valeur_bas * valeur_haut > 0:
        return np.nan
    for _ in range(120):
        milieu = (bas + haut) / 2
        valeur = _ecart(milieu)
        if np.isnan(valeur):
            return np.nan
        if abs(valeur) < 1e-10:
            return milieu
        if valeur_bas * valeur > 0:
            bas, valeur_bas = milieu, valeur
        else:
            haut = milieu
    return (bas + haut) / 2


# --------------------------------------------------------------------------
# Position détenue : conserver ou vendre
# --------------------------------------------------------------------------
def tri(flux: list[tuple[pd.Timestamp, float]]) -> float:
    """Taux de rendement interne d'une suite de flux datés (base annuelle).

    Utilisé pour le rendement réellement réalisé depuis l'achat : décaissement
    initial, coupons encaissés, produit de cession. La bissection s'applique sur
    [−0,9 ; 3] ; hors de cet intervalle, le TRI n'a pas de sens économique ici.
    """
    if not flux:
        return np.nan
    origine = min(date for date, _ in flux)
    temps = np.array([(pd.Timestamp(date) - origine).days / BASE_JOURS
                      for date, _ in flux], dtype=float)
    montants = np.array([montant for _, montant in flux], dtype=float)
    if (montants > 0).sum() == 0 or (montants < 0).sum() == 0:
        return np.nan

    def _van(taux: float) -> float:
        return float((montants * (1 + taux) ** (-temps)).sum())

    bas, haut = -0.9, 3.0
    valeur_bas, valeur_haut = _van(bas), _van(haut)
    if valeur_bas * valeur_haut > 0:
        return np.nan
    for _ in range(200):
        milieu = (bas + haut) / 2
        valeur = _van(milieu)
        if abs(valeur) < 1e-9:
            return milieu
        if valeur_bas * valeur > 0:
            bas, valeur_bas = milieu, valeur
        else:
            haut = milieu
    return (bas + haut) / 2


def position(titre: Titre, date_achat: pd.Timestamp, prix_achat_propre: float,
             date_valorisation: pd.Timestamp, taux_marche: float,
             montant_nominal: float = NOMINAL_UNITAIRE,
             frais_achat: float = 0.0, frais_vente: float = 0.0) -> dict:
    """Situation d'une position détenue : coût, valeur, plus-value, TRI réalisé.

    Les frais sont exprimés en fraction du montant traité (0,001 = 10 pb) et
    appliqués des deux côtés : sur une décision de cession à horizon court, ils
    pèsent souvent plus que le mouvement de taux anticipé.
    """
    date_achat = pd.Timestamp(date_achat).normalize()
    date_valorisation = pd.Timestamp(date_valorisation).normalize()

    # Origine commune : la date d'achat, la plus ancienne des deux.
    origine = date_achat
    encours_achat = encours_residuel(titre, date_achat, origine)
    couru_achat = coupon_couru(titre, date_achat, origine)
    prix_achat_total = prix_achat_propre + couru_achat
    # Le nominal détenu est exprimé au jour de la valorisation ; on remonte au
    # nominal d'origine pour dater correctement les amortissements déjà perçus.
    encours_valorisation = encours_residuel(titre, date_valorisation, origine)
    facteur = (montant_nominal / encours_valorisation
               if encours_valorisation > 0 else np.nan)
    if pd.isna(facteur):
        return {}
    nominal_achat = encours_achat * facteur
    cout = prix_achat_total * nominal_achat * (1 + frais_achat)
    taux_achat = taux_depuis_prix(titre, prix_achat_propre, date_achat,
                                  depuis=origine)

    valeur = prix_depuis_taux(titre, taux_marche, date_valorisation, origine)
    valeur_totale = valeur["Prix total"] * montant_nominal
    produit_cession = valeur_totale * (1 - frais_vente)

    plan = flux_a_venir(titre, date_achat, origine)
    encaisses = plan[plan["Date"] <= date_valorisation]
    coupons_percus = float(encaisses["Intérêt"].sum()) * facteur
    amortissements_percus = float(encaisses["Amortissement"].sum()) * facteur

    mouvements = [(date_achat, -cout)]
    for _, ligne in encaisses.iterrows():
        mouvements.append((ligne["Date"], float(ligne["Flux"]) * facteur))
    mouvements.append((date_valorisation, produit_cession))

    plus_value_totale = (produit_cession + coupons_percus + amortissements_percus
                         - cout)
    return {
        "Taux d'achat": taux_achat,
        "Prix d'achat total": prix_achat_total,
        "Coupon couru à l'achat": couru_achat,
        "Coût d'acquisition": cout,
        "Nominal à l'achat": nominal_achat,
        "Prix de marché total": valeur["Prix total"],
        "Prix de marché pied de coupon": valeur["Prix pied de coupon"],
        "Coupon couru": valeur["Coupon couru"],
        "Valeur de marché": valeur_totale,
        "Produit de cession net": produit_cession,
        "Coupons perçus": coupons_percus,
        "Amortissements perçus": amortissements_percus,
        "Plus-value de cours": produit_cession - cout + amortissements_percus,
        "Résultat total": plus_value_totale,
        "Résultat total (%)": plus_value_totale / cout if cout else np.nan,
        "TRI réalisé": tri(mouvements),
        "Durée de détention (années)": (date_valorisation - date_achat).days / BASE_JOURS,
        "Variation de taux depuis l'achat (pb)": (
            (taux_marche - taux_achat) * 10_000 if not pd.isna(taux_achat) else np.nan),
    }


def conserver_ou_vendre(titre: Titre, date_valorisation: pd.Timestamp,
                        taux_marche: float, taux_reinvestissement: float,
                        montant_nominal: float = NOMINAL_UNITAIRE,
                        frais_vente: float = 0.0,
                        date_horizon: pd.Timestamp | None = None) -> dict:
    """Compare conserver jusqu'à l'horizon et vendre pour replacer les fonds.

    Le prix d'achat n'entre pas dans cette comparaison, et c'est volontaire :
    il est enterré. Seules comptent la valeur de cession disponible aujourd'hui
    et ce que chaque branche rapporte ensuite.

    Le **taux de replacement d'indifférence** est la sortie utile : c'est le
    taux auquel il faudrait réinvestir le produit de la vente pour arriver au
    même capital que la conservation. Au-dessus, vendre l'emporte ; en dessous,
    conserver l'emporte. Il vaut mécaniquement le rendement de marché du titre
    lorsque les coupons sont eux-mêmes réinvestis à ce rendement — ce qui est
    la façon la plus honnête de dire que l'arbitrage se joue sur les hypothèses
    de replacement, pas sur le prix payé jadis.
    """
    date_valorisation = pd.Timestamp(date_valorisation).normalize()
    horizon = (pd.Timestamp(titre.echeance) if date_horizon is None
               else pd.Timestamp(date_horizon).normalize())
    duree = (horizon - date_valorisation).days / BASE_JOURS
    if duree <= 0:
        return {}

    origine = date_valorisation
    encours = encours_residuel(titre, date_valorisation, origine)
    facteur = montant_nominal / encours if encours > 0 else np.nan
    if pd.isna(facteur):
        return {}

    temps, flux, _, _, _ = _flux_apres(titre, date_valorisation, origine)
    avant_horizon = temps <= duree + 1e-9
    temps_restant = duree - temps[avant_horizon]
    montants = flux[avant_horizon] * facteur
    capitalises = float(
        (montants * (1 + taux_reinvestissement) ** temps_restant).sum())

    encours_horizon = encours_residuel(titre, horizon, origine)
    valeur_terminale = 0.0
    if encours_horizon > 0:
        valeur_terminale = (
            prix_depuis_taux(titre, taux_marche, horizon, origine)["Prix total"]
            * encours_horizon * facteur)
    valeur_conservation = capitalises + valeur_terminale

    prix_marche = prix_depuis_taux(titre, taux_marche, date_valorisation, origine)
    produit = prix_marche["Prix total"] * montant_nominal * (1 - frais_vente)
    valeur_vente = produit * (1 + taux_reinvestissement) ** duree
    indifference = ((valeur_conservation / produit) ** (1 / duree) - 1
                    if produit > 0 and valeur_conservation > 0 else np.nan)
    return {
        "Horizon": horizon,
        "Durée (années)": duree,
        "Produit de cession net": produit,
        "Valeur en conservant": valeur_conservation,
        "Valeur en vendant et replaçant": valeur_vente,
        "Écart (conserver − vendre)": valeur_conservation - valeur_vente,
        "Taux de replacement d'indifférence": indifference,
        "Rendement de la conservation": (
            (valeur_conservation / (prix_marche["Prix total"] * montant_nominal))
            ** (1 / duree) - 1),
        "Flux capitalisés": capitalises,
        "Valeur terminale": valeur_terminale,
    }


# --------------------------------------------------------------------------
# Ancrages de marché
# --------------------------------------------------------------------------
def taux_courbe(pays: str | None, maturite: float,
                date: pd.Timestamp | None = None,
                niveau: str = mod_courbes.NIVEAU_OFFICIELLE,
                params: mod_courbes.ParametresCourbe | None = None) -> float:
    """Taux de la courbe souveraine du pays à la maturité demandée."""
    if not pays or pd.isna(maturite) or maturite <= 0:
        return np.nan
    date = chargement.date_reference() if date is None else pd.Timestamp(date)
    interpolateur = mod_courbes.Interpolateur(niveau, params)
    valeur = interpolateur.taux(pays, date, [maturite])
    return float(valeur[0]) if len(valeur) else np.nan


def comparables_primaire(pays: str | None, maturite: float,
                         tolerance_annees: float = 1.0,
                         fenetre_jours: int = 365,
                         date: pd.Timestamp | None = None) -> pd.DataFrame:
    """Adjudications récentes de maturité voisine, pour situer une soumission.

    La courbe dit où le marché *devrait* se traiter ; les adjudications disent
    où l'émetteur a *effectivement* servi. Sur le court terme, l'écart entre les
    deux est régulièrement de plus de cent points de base (cf. `courbes.py`,
    ancrage BAT), et c'est l'adjudication qui fait foi puisqu'elle est un prix.
    """
    colonnes = ["Date de l'opération", "Pays", "Instrument", "ISIN",
                "Maturité (années)", "Rendement moyen pondéré (déc.)",
                "Taux marginal (déc.)", "Taux de couverture",
                "Montant retenu (Mds FCFA)"]
    if not pays or pd.isna(maturite):
        return pd.DataFrame(columns=colonnes)
    date = chargement.date_reference() if date is None else pd.Timestamp(date)
    primaire = chargement.emissions_primaire()
    retenues = primaire[
        (primaire["Catégorie"] == "Passée")
        & (primaire["Pays"] == pays)
        & primaire["Date de l'opération"].between(
            date - pd.Timedelta(days=fenetre_jours), date)
        & primaire["Rendement moyen pondéré (déc.)"].notna()
        & (primaire["Maturité (années)"] - maturite).abs().le(tolerance_annees)]
    if retenues.empty:
        return pd.DataFrame(columns=colonnes)
    return (retenues[colonnes].sort_values("Date de l'opération", ascending=False)
            .reset_index(drop=True))


def resume_comparables(comparables: pd.DataFrame) -> dict:
    """Distribution des taux servis sur les adjudications comparables."""
    if comparables.empty:
        return {}
    taux = comparables["Rendement moyen pondéré (déc.)"].dropna()
    marginal = comparables["Taux marginal (déc.)"].dropna()
    return {
        "Adjudications": int(len(comparables)),
        "Dernière": comparables["Date de l'opération"].max(),
        "Taux médian": float(taux.median()) if not taux.empty else np.nan,
        "1er quartile": float(taux.quantile(0.25)) if not taux.empty else np.nan,
        "3e quartile": float(taux.quantile(0.75)) if not taux.empty else np.nan,
        "Dernier taux servi": (
            float(comparables.sort_values("Date de l'opération")
                  ["Rendement moyen pondéré (déc.)"].dropna().iloc[-1])
            if not taux.empty else np.nan),
        "Taux marginal médian": float(marginal.median()) if not marginal.empty else np.nan,
        "Couverture médiane": float(
            comparables["Taux de couverture"].dropna().median())
        if comparables["Taux de couverture"].notna().any() else np.nan,
    }


def comparables_secondaire(pays: str | None, maturite: float,
                           titres: pd.DataFrame,
                           tolerance_annees: float = 1.0) -> pd.DataFrame:
    """Souches vivantes du même émetteur, de maturité voisine, ayant un YTM.

    Le point de comparaison le plus direct pour juger d'un niveau : ce que le
    marché secondaire paie aujourd'hui pour un risque et une durée équivalents.
    """
    colonnes = ["Identifiant", "ISIN", "Pays", "Coupon", "Échéance",
                "Maturité résiduelle (années)", "Dernier YTM",
                "Dernière négociation", "Écart YTM / courbe (pb)",
                "Encours (Mds FCFA)"]
    if titres.empty or not pays or pd.isna(maturite):
        return pd.DataFrame(columns=colonnes)
    voisins = titres[
        (titres["Pays"] == pays)
        & (titres["Statut"] == "Vivant")
        & titres["Dernier YTM"].notna()
        & (titres["Maturité résiduelle (années)"] - maturite).abs()
        .le(tolerance_annees)]
    if voisins.empty:
        return pd.DataFrame(columns=colonnes)
    return (voisins[[c for c in colonnes if c in voisins.columns]]
            .sort_values("Dernière négociation", ascending=False)
            .reset_index(drop=True))
