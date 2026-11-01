# BRVM Reporting

Reportings sur la BRVM (Bourse Régionale des Valeurs Mobilières). Ce dépôt ne collecte rien : toutes les
données viennent du dépôt de données `DylaneTrader/Scraper-BRVM`, qui les scrape et les traite chaque jour
ouvré.

| Dossier | Contenu | Accès aux données |
|---|---|---|
| `simulateur-bourse/` | Simulateur de portefeuille (Next.js, SQLite, Prisma) | dossier `data/` d'un clone de Scraper-BRVM placé à côté de ce dépôt (`MARKET_DATA_DIR`, par défaut `../../Scraper-BRVM/data`) |
| `dashboard/` | Tableau de bord HTML statique (cours, fondamentaux, dividendes, signaux) | API GitHub de Scraper-BRVM, avec un jeton en lecture (dépôt privé) passé une fois dans l'adresse : `brvm_dashboard_enriched.html#jeton=…`, puis gardé par le navigateur ; aucun jeton n'est écrit dans le fichier |
| `powerbi/` | Rapport Power BI `reporting_brvm_actions.pbip` (modèle sémantique, rapport, thème CGF) et son cahier des charges (`POWERBI_SPEC.md`) | dossier `data/` local désigné par le paramètre `CheminDonnees` du modèle |

## Installer le simulateur

```bash
git clone https://github.com/DylaneTrader/Scraper-BRVM.git
git clone https://github.com/DylaneTrader/BRVM-Reporting.git
cd BRVM-Reporting/simulateur-bourse
npm install
```

Le reste est décrit dans [simulateur-bourse/README.md](simulateur-bourse/README.md).

## Power BI

Le modèle lit un dossier `data/` local : la valeur de `CheminDonnees` est écrite dans chaque table
(`powerbi/reporting_brvm_actions.SemanticModel/definition/tables/*.tmdl`). Elle désigne encore le dossier
`data/` de BRVM app sur le poste d'origine ; il reste à jour, car brvm-app recopie les données de
Scraper-BRVM. Pour lire Scraper-BRVM directement, remplacer ce chemin par celui du dossier `data/` d'un clone
de Scraper-BRVM, dans les huit tables. Le cache local (`.pbi/cache.abf`) n'est pas versionné : le premier
chargement actualise les données.

`.github/workflows/refresh-powerbi.yml` déclenche l'actualisation du jeu de données Power BI chaque jour
ouvré à 23 h 40 UTC, puis le lendemain à 6 h 40 UTC, après le scraping et les signaux de Scraper-BRVM. Il
demande cinq secrets : `PBI_TENANT_ID`, `PBI_CLIENT_ID`, `PBI_CLIENT_SECRET` (principal de service Azure AD
autorisé sur l'espace de travail), `PBI_GROUP_ID` (espace de travail) et `PBI_DATASET_ID` (jeu de données).
Sans eux, l'étape est ignorée.

## Historique

Le simulateur, le tableau de bord et le cahier Power BI viennent de Scraper-BRVM, le projet Power BI
(`reporting_brvm_actions.pbip`) de brvm-app ; ils y ont été retirés le 01/11/2026 pour que chaque dépôt garde
un seul rôle. Leur historique antérieur est dans ces deux dépôts.
