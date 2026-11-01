# -*- coding: utf-8 -*-
"""
Contrôles du moteur obligataire du simulateur (`app/lib/simulateur.py`).

Vérifie les identités qu'un calcul obligataire doit satisfaire par construction
— un titre acheté au pair vaut le pair, le rendement se retrouve depuis le prix,
la décomposition d'un gain somme au gain — plutôt que des valeurs figées :
ce sont ces identités qui cassent en premier quand une convention dérape.

    python umoa-titres/test_simulateur.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lib import simulateur as sim  # noqa: E402

ECHECS = []


def log(message: str) -> None:
    print(message, flush=True)

EMISSION = pd.Timestamp("2026-01-01")
ECHEANCE_5A = pd.Timestamp("2031-01-01")


def verifier(condition: bool, libelle: str, detail: str = "") -> None:
    if condition:
        log(f"  OK   {libelle}")
    else:
        ECHECS.append(libelle)
        log(f"  ÉCHEC {libelle}" + (f" — {detail}" if detail else ""))


def _bullet(coupon: float = 0.06) -> sim.Titre:
    return sim.Titre(echeance=ECHEANCE_5A, coupon=coupon,
                     date_jouissance=EMISSION)


# --------------------------------------------------------------------------
# Échéancier
# --------------------------------------------------------------------------
def test_echeancier() -> None:
    log("Échéanciers contractuels")
    plan = sim.echeancier(_bullet())
    verifier(len(plan) == 5, "in fine 5 ans -> 5 flux annuels", f"{len(plan)}")
    verifier(abs(plan["Amortissement"].sum() - 1.0) < 1e-12,
             "in fine : le principal est remboursé une fois et une seule")
    verifier(abs(plan["Intérêt"].sum() - 0.30) < 1e-12,
             "in fine : 5 coupons de 6 %")

    constant = sim.Titre(echeance=ECHEANCE_5A, coupon=0.06,
                         date_jouissance=EMISSION, amortissement="ACD",
                         differe_annees=2)
    plan_ca = sim.echeancier(constant)
    verifier(abs(plan_ca["Amortissement"].sum() - 1.0) < 1e-12,
             "amortissement constant : principal intégralement remboursé")
    verifier((plan_ca["Amortissement"].head(2) == 0).all(),
             "différé de 2 ans : aucun capital remboursé les deux premières années")
    verifier(abs(plan_ca["Intérêt"].sum() - 0.24) < 1e-12,
             "intérêts servis sur l'encours décroissant (0,24 attendu)",
             f"{plan_ca['Intérêt'].sum():.4f}")

    annuites = sim.Titre(echeance=ECHEANCE_5A, coupon=0.06,
                         date_jouissance=EMISSION, amortissement="AnC")
    plan_an = sim.echeancier(annuites)
    verifier(plan_an["Flux"].round(9).nunique() == 1,
             "annuités constantes : tous les flux sont égaux")
    verifier(abs(plan_an["Amortissement"].sum() - 1.0) < 1e-12,
             "annuités constantes : principal intégralement remboursé")

    # Collision de codes : le secondaire écrit « AC » pour l'amortissement
    # constant et « AnC » pour les annuités.
    verifier(sim.normaliser_amortissement("AC") == sim.AMORTISSEMENT_CONSTANT,
             "« AC » (secondaire) -> amortissement constant")
    verifier(sim.normaliser_amortissement("AnC") == sim.AMORTISSEMENT_ANNUITES,
             "« AnC » (secondaire) -> annuités constantes")
    verifier(sim.normaliser_amortissement("Linéaire") == sim.AMORTISSEMENT_CONSTANT,
             "« Linéaire » (primaire) -> amortissement constant")


# --------------------------------------------------------------------------
# Prix et rendement
# --------------------------------------------------------------------------
def test_prix_et_rendement() -> None:
    log("Prix, rendement et coupon couru")
    titre = _bullet()
    # Exact/365 : 5 ans calendaires font 5,003 années actuarielles, d'où l'écart
    # de quelques points de base au pair. C'est la convention, pas une erreur.
    prix = sim.prix_depuis_taux(titre, 0.06, EMISSION)["Prix total"]
    verifier(abs(prix - 1.0) < 5e-4, "coupon = rendement -> prix au pair",
             f"{prix:.6f}")

    taux = sim.taux_depuis_prix(titre, prix, EMISSION)
    verifier(abs(taux - 0.06) < 1e-8, "aller-retour prix -> taux",
             f"{taux:.8f}")

    un_an = sim.Titre(echeance=pd.Timestamp("2027-01-01"), coupon=0.06,
                      date_jouissance=EMISSION)
    prix_un_an = sim.prix_depuis_taux(un_an, 0.06, EMISSION)["Prix total"]
    verifier(abs(prix_un_an - 1.0) < 1e-9,
             "titre à un an : un seul flux, mais coupon payé (pas un BAT)",
             f"{prix_un_an:.6f}")

    bat = sim.Titre(echeance=pd.Timestamp("2026-07-02"), coupon=0.0,
                    date_jouissance=EMISSION)
    attendu = 1.06 ** (-(pd.Timestamp("2026-07-02") - EMISSION).days / 365)
    verifier(abs(sim.prix_depuis_taux(bat, 0.06, EMISSION)["Prix total"] - attendu)
             < 1e-12, "BAT : actualisation d'un flux unique")

    mi_periode = pd.Timestamp("2026-07-02")
    couru = sim.coupon_couru(titre, mi_periode)
    verifier(abs(couru - 0.06 * 182 / 365) < 1e-12,
             "coupon couru Exact/365 sur 182 jours")
    valorisation = sim.prix_depuis_taux(titre, 0.06, mi_periode)
    verifier(abs(valorisation["Prix total"] - valorisation["Prix pied de coupon"]
                 - couru) < 1e-12,
             "prix total = prix pied de coupon + couru")


def test_sensibilite() -> None:
    log("Durations et convexité")
    titre = _bullet()
    mesures = sim.metriques(titre, 0.06, EMISSION)
    verifier(abs(mesures["Duration Macaulay"] - 4.4675) < 1e-3,
             "duration de Macaulay d'un 5 ans 6 % au pair ≈ 4,47",
             f"{mesures['Duration Macaulay']:.4f}")
    verifier(abs(mesures["Duration modifiée"]
                 - mesures["Duration Macaulay"] / 1.06) < 1e-12,
             "duration modifiée = Macaulay / (1 + y)")

    # La duration prédit la variation de prix au premier ordre : l'écart doit
    # rester du deuxième ordre pour un petit choc.
    prix = mesures["Prix total"]
    choc = sim.prix_depuis_taux(titre, 0.0601, EMISSION)["Prix total"]
    estime = prix * (1 - mesures["Duration modifiée"] * 0.0001)
    verifier(abs(choc - estime) < 1e-6, "+1 pb : duration modifiée prédit le prix",
             f"{choc:.8f} vs {estime:.8f}")

    amortissable = sim.Titre(echeance=ECHEANCE_5A, coupon=0.06,
                             date_jouissance=EMISSION, amortissement="ACD")
    mesures_ca = sim.metriques(amortissable, 0.06, EMISSION)
    verifier(mesures_ca["Duration modifiée"] < mesures["Duration modifiée"],
             "un amortissable est moins sensible qu'un in fine de même échéance")
    verifier(mesures_ca["Maturité moyenne pondérée (années)"]
             < mesures_ca["Maturité résiduelle (années)"],
             "vie moyenne d'un amortissable < échéance finale")


# --------------------------------------------------------------------------
# Horizon et arbitrage
# --------------------------------------------------------------------------
def test_horizon() -> None:
    log("Analyse d'horizon")
    titre = _bullet()
    conserve = sim.analyse_horizon(titre, EMISSION, 0.06, ECHEANCE_5A, 0.06,
                                   0.06, 10_000_000)
    verifier(abs(conserve["Rendement total"] - 0.06) < 1e-9,
             "acheté à 6 %, coupons replacés à 6 % -> rendement total 6 %",
             f"{conserve['Rendement total']:.8f}")
    somme = (conserve["Coupons perçus"] + conserve["Effet de réinvestissement"]
             + conserve["Effet capital"])
    verifier(abs(conserve["Gain"] - somme) < 1e-6,
             "décomposition additive : coupons + réinvestissement + capital = gain")
    verifier(abs(conserve["Effet capital"] - conserve["Effet de portage"]
                 - conserve["Effet taux"]) < 1e-9,
             "effet capital = portage + effet taux")

    hausse = sim.analyse_horizon(titre, EMISSION, 0.06,
                                 pd.Timestamp("2027-01-01"), 0.07, 0.06,
                                 10_000_000)
    verifier(hausse["Effet taux"] < 0,
             "hausse des taux à l'horizon -> effet taux négatif")
    verifier(hausse["Rendement total"] < 0.06,
             "et rendement total inférieur au rendement d'achat")

    seuil = sim.choc_indifference(titre, EMISSION, 0.06,
                                  pd.Timestamp("2027-01-01"), 0.06, 10_000_000)
    au_seuil = sim.analyse_horizon(titre, EMISSION, 0.06,
                                   pd.Timestamp("2027-01-01"),
                                   0.06 + seuil / 10_000, 0.06, 10_000_000)
    verifier(abs(au_seuil["Rendement total"]) < 1e-6,
             "au choc d'indifférence, le rendement total est nul",
             f"{au_seuil['Rendement total']:.8f}")
    verifier(seuil > 0, "le coussin de portage est positif à taux inchangé")


def test_conserver_ou_vendre() -> None:
    log("Arbitrage conserver / vendre")
    titre = _bullet()
    valorisation = pd.Timestamp("2026-07-02")
    arbitrage = sim.conserver_ou_vendre(titre, valorisation, 0.065, 0.065,
                                        10_000_000)
    indifference = arbitrage["Taux de replacement d'indifférence"]
    verifier(abs(indifference - 0.065) < 1e-9,
             "replacement au rendement de marché -> indifférence à ce rendement",
             f"{indifference:.6f}")
    verifier(abs(arbitrage["Écart (conserver − vendre)"]) < 1e-6,
             "et les deux branches valent alors exactement la même chose")

    dessous = sim.conserver_ou_vendre(titre, valorisation, 0.065, 0.045,
                                      10_000_000)
    verifier(dessous["Écart (conserver − vendre)"] > 0,
             "replacement sous le rendement de marché -> conserver l'emporte")
    dessus = sim.conserver_ou_vendre(titre, valorisation, 0.065, 0.085,
                                     10_000_000)
    verifier(dessus["Écart (conserver − vendre)"] < 0,
             "replacement au-dessus -> vendre et replacer l'emporte")


def test_position() -> None:
    log("Position détenue")
    titre = _bullet()
    etat = sim.position(titre, EMISSION, 1.0, pd.Timestamp("2026-07-02"),
                        0.06, 10_000_000)
    taux_achat = etat["Taux d'achat"]
    verifier(abs(taux_achat - 0.06) < 1e-3,
             "prix d'achat au pair -> taux d'achat ≈ coupon",
             f"{taux_achat:.5f}")
    verifier(etat["Résultat total"] > 0,
             "à taux inchangé, la détention rapporte le couru")
    frais = sim.position(titre, EMISSION, 1.0, pd.Timestamp("2026-07-02"),
                         0.06, 10_000_000, frais_achat=0.001, frais_vente=0.001)
    verifier(frais["Résultat total"] < etat["Résultat total"],
             "les frais réduisent le résultat")

    amortissable = sim.Titre(echeance=ECHEANCE_5A, coupon=0.06,
                             date_jouissance=EMISSION, amortissement="ACD",
                             differe_annees=2)
    detenu = sim.position(amortissable, pd.Timestamp("2027-03-01"), 0.99,
                          pd.Timestamp("2029-06-01"), 0.065, 50_000_000)
    nominal_achat = detenu["Nominal à l'achat"]
    verifier(abs(nominal_achat - 75_000_000) < 1,
             "50 M résiduels après 1/3 d'amortissement = 75 M à l'achat",
             f"{nominal_achat:,.0f}")
    verifier(detenu["Amortissements perçus"] > 0,
             "les amortissements déjà tombés sont comptés dans le résultat")


def test_jouissance_inconnue() -> None:
    log("Jouissance inconnue")
    connu = _bullet()
    inconnu = sim.Titre(echeance=ECHEANCE_5A, coupon=0.06)
    verifier(len(sim.flux_a_venir(inconnu, EMISSION))
             == len(sim.flux_a_venir(connu, EMISSION)),
             "l'échéancier reste complet à partir de la date d'analyse")
    verifier(abs(sim.prix_depuis_taux(inconnu, 0.06, EMISSION)["Prix total"]
                 - sim.prix_depuis_taux(connu, 0.06, EMISSION)["Prix total"])
             < 1e-12, "et le prix est identique à celui du titre daté")
    verifier(sim.coupon_couru(inconnu, pd.Timestamp("2026-07-02")) == 0.0,
             "coupon couru laissé à zéro plutôt qu'inventé")


def main() -> int:
    for test in [test_echeancier, test_prix_et_rendement, test_sensibilite,
                 test_horizon, test_conserver_ou_vendre, test_position,
                 test_jouissance_inconnue]:
        test()
    log("")
    if ECHECS:
        log(f"{len(ECHECS)} contrôle(s) en échec : {', '.join(ECHECS)}")
        return 1
    log("Tous les contrôles passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
