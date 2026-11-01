# Reporting

Interfaces et rapports : applications web, rapports Power BI, présentations, tableaux de bord. Ce dépôt ne
collecte aucune donnée : chaque reporting lit celles d'un dépôt de données. Il est rangé par sujet, qu'il
s'agisse d'un marché ou non.

| Dossier | Contenu | Données lues |
|---|---|---|
| `brvm/simulateur-bourse/` | Simulateur de portefeuille d'actions BRVM (Next.js, SQLite, Prisma) | `data/` d'un clone voisin de `DylaneTrader/Scraper-BRVM` (`MARKET_DATA_DIR`) |
| `brvm/dashboard/` | Tableau de bord HTML des actions BRVM (cours, fondamentaux, dividendes, signaux) | API GitHub de Scraper-BRVM, jeton passé une fois dans l'adresse (`#jeton=…`) |
| `brvm/powerbi/` | Rapport Power BI des actions BRVM (`reporting_brvm_actions.pbip`) et son cahier des charges | dossier `data/` local (paramètre `CheminDonnees`) |
| `umoa-titres/app/` | Application Streamlit des titres publics UMOA et obligations BRVM : référentiel, fiche titre, courbes, primaire, secondaire, benchmark, risque de taux, calendrier, simulateur | `data/` d'un clone voisin de `DylaneTrader/Scraper-UMOA-Titres` (`UMOA_DATA_DIR`) |
| `umoa-titres/powerbi/` | Rapport Power BI CGF Gestion des titres publics (`Reporting BI.pbip`), configuration et méthodologie | `data/_bi/` de Scraper-UMOA-Titres, par l'API GitHub |

Un nouveau reporting (présentation PowerPoint, autre marché, sujet interne) prend son propre dossier, au
premier niveau ou sous celui de son sujet.

## Installer

Cloner les dépôts de données à côté de celui-ci :

```bash
git clone https://github.com/DylaneTrader/Scraper-BRVM.git
git clone https://github.com/DylaneTrader/Scraper-UMOA-Titres.git
git clone https://github.com/DylaneTrader/Reporting.git
```

Application UMOA-Titres :

```bash
cd Reporting
pip install -r umoa-titres/requirements.txt
streamlit run umoa-titres/app/Accueil.py
```

Contrôles du moteur obligataire du simulateur UMOA : `python umoa-titres/test_simulateur.py`.

Simulateur BRVM : voir [brvm/simulateur-bourse/README.md](brvm/simulateur-bourse/README.md).

## Power BI

**BRVM.** Le modèle lit un dossier `data/` local : la valeur de `CheminDonnees` est écrite dans chaque table
(`brvm/powerbi/reporting_brvm_actions.SemanticModel/definition/tables/*.tmdl`). Elle désigne encore le dossier
`data/` de BRVM app sur le poste d'origine ; il reste à jour, car brvm-app recopie les données de
Scraper-BRVM. Pour lire Scraper-BRVM directement, remplacer ce chemin dans les huit tables.
`.github/workflows/refresh-powerbi.yml` déclenche l'actualisation du jeu de données publié chaque jour ouvré à
23 h 40 UTC, puis le lendemain à 6 h 40 UTC. Il demande cinq secrets : `PBI_TENANT_ID`, `PBI_CLIENT_ID`,
`PBI_CLIENT_SECRET` (principal de service Azure AD autorisé sur l'espace de travail), `PBI_GROUP_ID` et
`PBI_DATASET_ID`. Sans eux, l'étape est ignorée.

**UMOA-Titres.** Le rapport lit `data/_bi/*.csv` de Scraper-UMOA-Titres par l'API GitHub, avec un jeton en
lecture saisi dans le paramètre `GitHubToken` : voir
[umoa-titres/powerbi/CONFIGURATION_POWERBI.md](umoa-titres/powerbi/CONFIGURATION_POWERBI.md).

Le cache local (`.pbi/cache.abf`) n'est pas versionné : le premier chargement actualise les données.

## Historique

Créé le 01/11/2026 sous le nom BRVM-Reporting, puis élargi. Viennent de Scraper-BRVM le simulateur, le
tableau de bord et le cahier Power BI BRVM ; de brvm-app le projet Power BI BRVM ; de Scraper-UMOA-Titres
l'application Streamlit et le rapport Power BI des titres publics. Leur historique antérieur est dans ces
dépôts.
