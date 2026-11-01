"""Stratégie du tableau de bord BRVM (Reporting/brvm/dashboard), au format du moteur de BRVM app.

Reprend sans les modifier les calculs de DylaneTrader/Scraper-BRVM (``quant/signals.py``,
``quant/portfolio.py``) : prévision Prophet à 30 jours de chaque titre, puis allocation
Black-Litterman qui prend ces prévisions pour vues. Seules les données connues à la date de
décision sont lues (``ctx``), et le moteur exécute les ordres à la séance suivante.

Variante ``mode="achat"`` : parts égales entre les titres classés ACHAT ou ACHAT FORT par Prophet,
sans Black-Litterman, pour mesurer la valeur des seuls signaux.
"""
from __future__ import annotations

import logging
import os
import sys

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

# quant/ de BRVM app (lancé depuis sa racine) ou, à défaut, celui de Scraper-BRVM : même code.
if os.environ.get("SCRAPER_BRVM_DIR"):
    sys.path.append(os.environ["SCRAPER_BRVM_DIR"])
from quant.covariance import CovarianceResult  # noqa: E402
from quant.portfolio import optimize_portfolio  # noqa: E402
from quant.signals import TickerSignal, _classify  # noqa: E402

from strategies.base import Parametre, StrategieAllocation  # noqa: E402
from strategies.allocation._outils import tableau  # noqa: E402

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)

ANNEES_PROPHET = 3       # fenêtre d'apprentissage de quant/signals.py
ANNEES_COVARIANCE = 2    # fenêtre de quant/covariance.py
HORIZON = 30             # jours calendaires


def _prevision(ticker: str, serie: pd.Series) -> TickerSignal | None:
    """Prophet sur les clôtures des seuls jours d'échange des 3 dernières années (comme
    quant/signals.forecast_ticker)."""
    from prophet import Prophet

    s = serie.dropna()
    s = s[s.index >= s.index.max() - pd.DateOffset(years=ANNEES_PROPHET)]
    if len(s) < 60:
        return None
    m = Prophet(daily_seasonality=False, weekly_seasonality=False, yearly_seasonality=True,
                interval_width=0.80)
    m.fit(pd.DataFrame({"ds": s.index, "y": s.values}))
    f = m.predict(m.make_future_dataframe(periods=HORIZON, freq="D", include_history=False)).iloc[-1]
    dernier = float(s.iloc[-1])
    return TickerSignal(ticker=ticker, last_price=dernier, last_date=s.index[-1].date().isoformat(),
                        signal=_classify(float(f["yhat"]), dernier), confidence="",
                        target_30d=float(f["yhat"]), trend="", yhat=float(f["yhat"]),
                        yhat_lower=float(f["yhat_lower"]), yhat_upper=float(f["yhat_upper"]),
                        train_start="", train_end="", train_rows=len(s), train_annualized_return=0.0)


def _covariance(ctx, titres: list[str]) -> CovarianceResult:
    """Ledoit-Wolf sur 2 ans de rendements aux dates communes, à l'horizon de 30 séances
    (comme quant/covariance.estimate_covariance)."""
    cours = ctx.cours(titres).where(ctx.echange(titres))
    cours = cours[cours.index >= ctx.date - pd.DateOffset(years=ANNEES_COVARIANCE)]
    r = cours.dropna(how="any").pct_change().dropna(how="any")
    if len(r) < 30:  # dates communes trop rares : variances seules
        r = cours.pct_change()
        cov = np.diag(r.var().fillna(r.var().mean()).values)
    else:
        cov = LedoitWolf().fit(r.values).covariance_
    return CovarianceResult(cov=pd.DataFrame(cov * 30, index=titres, columns=titres), tickers=titres,
                            cond_number_raw=float("nan"), cond_number_shrunk=float("nan"),
                            used_fallback=False)


class ProphetBlackLitterman(StrategieAllocation):
    """
    Description :
        Prévision Prophet à 30 jours de chaque titre liquide, puis allocation Black-Litterman qui
        prend ces prévisions pour vues (covariance Ledoit-Wolf, poids plafonnés à 25 %). C'est la
        stratégie du tableau de bord BRVM et du simulateur de Reporting.

    Auteur(s) :
        Dylane (Scraper-BRVM, quant/signals.py et quant/portfolio.py)

    Avantage(s) :
        Combine une prévision par titre et le risque du portefeuille dans un cadre établi.

    Hypothèse(s) :
        La tendance et la saisonnalité annuelle estimées par Prophet sur trois ans annoncent le
        cours du mois suivant.

    Limite(s) :
        Prophet extrapole une tendance lissée : sur des titres peu liquides, ses prévisions
        suivent surtout le mouvement récent. Les vues sont absolues, avec un a priori neutre.

    Référence(s) :
        Taylor S. J. & Letham B. (2018), « Forecasting at Scale », The American Statistician,
        72(1) ; Black F. & Litterman R. (1992), « Global Portfolio Optimization », Financial
        Analysts Journal, 48(5).
    """

    code = "prophet_black_litterman"
    nom = "Prophet + Black-Litterman (tableau de bord)"
    parametres = [
        Parametre("mode", "Allocation", "choix", "bl", choix=["bl", "achat"],
                  aide="bl : Black-Litterman sur les vues Prophet ; achat : parts égales entre les titres ACHAT."),
        Parametre("poids_max", "Poids maximal par titre", "pourcentage", 0.25, 0.05, 1.0, 0.05),
    ]

    def poids(self, ctx, univers: list[str], mode: str = "bl", poids_max: float = 0.25) -> pd.DataFrame:
        cours = ctx.cours(univers).where(ctx.echange(univers))
        signaux = [s for t in univers if (s := _prevision(t, cours[t])) is not None]
        if mode == "achat":
            achats = [s.ticker for s in signaux if s.signal in ("ACHAT", "ACHAT FORT")]
            return tableau(achats, np.ones(len(achats)))       # aucun achat : tout en trésorerie
        titres = [s.ticker for s in signaux]
        if len(titres) < 2:
            return tableau(titres, np.ones(len(titres)))
        try:
            alloc = optimize_portfolio(_covariance(ctx, titres), signaux, max_weight=poids_max)["allocation"]
        except Exception as exc:  # noqa: BLE001  (optimiseur sans solution : trésorerie, signalée)
            logging.getLogger(__name__).warning("Black-Litterman sans solution au %s : %s", ctx.date.date(), exc)
            return tableau([], [])
        return tableau(list(alloc), list(alloc.values()))


STRATEGIE = ProphetBlackLitterman()
