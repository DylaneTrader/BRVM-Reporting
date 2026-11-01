"""Évalue la stratégie du tableau de bord avec le moteur de BRVM app.

    cd brvm-app && SCRAPER_BRVM_DIR=... python evaluer.py DEBUT FIN [sortie.json]
"""
import json, sys, time, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
from strategies import tester
import prophet_black_litterman as PBL

debut, fin = sys.argv[1], sys.argv[2]
sortie = Path(sys.argv[3]) if len(sys.argv) > 3 else None
from strategies.marche import marche
univers = list(marche().titres)
res = {}
for nom, strat, params in [
    ("Prophet + Black-Litterman", PBL.STRATEGIE, {"mode": "bl"}),
    ("Signaux Prophet seuls (ACHAT, parts égales)", PBL.STRATEGIE, {"mode": "achat"}),
    ("Parts égales (catalogue)", "equipondere", None),
    ("Markowitz max Sharpe (catalogue)", "markowitz_max_sharpe", None),
    ("Momentum 12-1 (catalogue)", "momentum_12_1", None),
]:
    t = time.time()
    b = tester(strat, univers, debut, fin, params=params, frequence="ME", seuil=0.60)
    m = {k: b.mesures.get(k) for k in ("perf", "perf_annualisee", "volatilite", "sharpe", "perte_max",
                                       "frais", "operations", "rotation", "tresorerie_moyenne", "beta")}
    res[nom] = {"mesures": m, "alertes": b.alertes,
                "valeurs": b.resultat.valeurs.resample("ME").last().round(0).astype(float).rename(lambda d: d.date().isoformat()).to_dict()}
    if "ref" not in res and b.reference is not None:
        res["ref_1N"] = {"mesures": {k: b.mesures_reference.get(k) for k in m}}
    print(f"{nom}: {time.time()-t:.0f}s", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()}, flush=True)
from strategies.contexte import Contexte
ix = Contexte(fin).indice("BRVMC")
ix = ix[ix.index >= pd.Timestamp(debut)]
res["BRVMC"] = {"perf": float(ix.iloc[-1] / ix.iloc[0] - 1)}
print("BRVMC perf", round(res["BRVMC"]["perf"], 4))
if sortie:
    sortie.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
