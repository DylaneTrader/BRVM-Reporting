# Évaluation de la stratégie du tableau de bord BRVM

Le tableau de bord (`brvm/dashboard/`) et le simulateur affichent les signaux et l'allocation calculés
par Scraper-BRVM : prévision Prophet à 30 jours de chaque titre (`quant/signals.py`), puis allocation
Black-Litterman qui prend ces prévisions pour vues (`quant/portfolio.py`, covariance Ledoit-Wolf,
poids plafonnés à 25 %). Cette évaluation rejoue cette stratégie dans le moteur de BRVM app pour
savoir si elle a une valeur réelle.

## Méthode

- `prophet_black_litterman.py` : la stratégie, au format `StrategieAllocation` de BRVM app. Elle
  appelle sans les modifier les fonctions de Scraper-BRVM et ne lit que les données connues à la
  date de décision. Le mode `achat` garde les seuls signaux (parts égales entre les titres ACHAT et
  ACHAT FORT, sans Black-Litterman).
- `evaluer.py` : lance `strategies.tester` de BRVM app du 01/01/2019 au 29/10/2026, rééquilibrage
  mensuel, univers des titres liquides (seuil de 60 % de séances avec échange), capital de
  10 millions FCFA, réglages par défaut du moteur : frais de 1 % par ordre, ordres exécutés à la
  séance suivante, participation limitée à 20 % du volume, dividendes crédités, règlement en J+2.
- `journal_2019_2026.txt` : sortie du calcul (environ 17 minutes).

Pour rejouer, depuis la racine d'un clone de BRVM app et avec un clone de Scraper-BRVM :

```bash
SCRAPER_BRVM_DIR=../Scraper-BRVM python ../Reporting/brvm/dashboard/evaluation/evaluer.py 2019-01-01 2026-10-29 resultats.json
```

## Résultats (01/01/2019 au 29/10/2026)

| Stratégie | Performance | Par an | Volatilité | Sharpe | Perte max. | Rotation par an | Frais (FCFA) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Prophet + Black-Litterman (tableau de bord) | +241,8 % | 17,0 % | 13,5 % | 0,98 | -32,0 % | 6,9 | 17,9 M |
| Signaux Prophet seuls, parts égales | +270,8 % | 18,2 % | 13,2 % | 1,07 | -30,6 % | 6,3 | 16,7 M |
| Parts égales, rééquilibrage mensuel | +634,9 % | 29,0 % | 9,4 % | 2,38 | -22,3 % | 0,5 | 1,9 M |
| Markowitz, Sharpe maximal | +358,2 % | 21,5 % | 13,6 % | 1,24 | -58,7 % | 2,5 | 6,7 M |
| Momentum 12-1 | +456,5 % | 24,5 % | 20,5 % | 1,00 | -50,8 % | 3,4 | 16,1 M |
| Indice BRVMC (cours seuls, sans dividendes) | +207,6 % | 15,4 % | | | | | |

## Verdict

**La stratégie n'a pas de valeur démontrée ; en l'état, elle est à écarter comme règle de gestion.**

1. Elle bat l'indice BRVMC, mais la comparaison la flatte : la stratégie touche les dividendes,
   l'indice non. Face à la référence juste, les parts égales sur le même univers, elle perd
   largement : 17 % par an contre 29 %, un Sharpe de 0,98 contre 2,38, une perte maximale plus
   profonde.
2. Black-Litterman n'ajoute rien aux signaux : les signaux seuls font un peu mieux (18,2 % par an),
   avec moins d'ordres. L'optimisation n'apporte que de la rotation.
3. La rotation tue la performance : environ 7 fois le portefeuille par an, soit 17,9 millions FCFA de
   frais pour 10 millions de capital de départ. Prophet extrapole une tendance lissée qui change de
   signe d'un mois à l'autre sur des titres peu liquides, et chaque changement coûte 1 % à l'achat
   et à la vente.
4. Quatre mois de 2020 sont passés en trésorerie : toutes les vues étaient sous le taux sans risque
   et l'optimiseur n'a pas trouvé de solution.

Limites du test : un seul jeu de paramètres, une seule période, l'univers des titres cotés
aujourd'hui (biais du survivant, commun à toutes les lignes du tableau). Ce qu'il faudrait tester
avant de réhabiliter l'idée : des vues relatives plutôt qu'absolues, un a priori d'équilibre plutôt
que neutre, une bande de non-rééquilibrage pour limiter la rotation, et une validation hors
échantillon. Ce travail est ouvert dans BRVM-Recherche (`black_litterman/`).
