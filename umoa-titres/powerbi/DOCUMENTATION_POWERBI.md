# Rapport Power BI des titres publics UMOA : documentation

Extrait de la documentation de `DylaneTrader/Scraper-UMOA-Titres` (sections 8 à 12), qui décrit la
collecte et la préparation des fichiers `data/_bi/` lus par ce rapport. Les chemins `Reporting BI.*`
sont relatifs à ce dossier ; le script `generer_pages_rapport.py` est à côté.

## 8. Étape 6 — Le modèle de données Power BI (PBIP / TMDL)

Le projet Power BI est au format **PBIP** (dossiers texte versionnables), et non
un `.pbix` binaire. Deux dossiers :

- `Reporting BI.SemanticModel/` : le **modèle de données** (format **TMDL**).
- `Reporting BI.Report/` : le **rapport** (pages, visuels, thème — format **PBIR** JSON).

> Pour éditer ce format : Power BI Desktop → *Fichier → Options → Préversions* →
> activer **« Power BI Project (.pbip) »** et **« Store reports using enhanced
> metadata format (PBIR) »**. On peut ensuite ouvrir `Reporting BI.pbip`.

### 8.1 Connexion aux données : le paramètre + la fonction

Fichier : [`Reporting BI.SemanticModel/definition/expressions.tmdl`](Reporting%20BI.SemanticModel/definition/expressions.tmdl)

- **`GitHubToken`** : un paramètre texte (vide dans le dépôt) où l'on colle un
  jeton GitHub. **Aucun secret n'est stocké dans le dépôt.**
- **`GitHubFichier`** : une fonction M qui télécharge un fichier de `data/_bi`
  **via l'API Git de GitHub** (dépôt privé). Elle procède en deux temps :
  1. appelle l'endpoint **`trees`** pour obtenir le **SHA** du fichier,
  2. appelle l'endpoint **`blobs`** qui renvoie le contenu en **base64 dans le
     JSON**, puis le décode.

  Pourquoi ce détour ? L'API « Contents » plus simple est **limitée à 1 Mo** et
  bascule sur une redirection au-delà (ce qui faisait **expirer** Power BI sur
  `courbes_taux.csv` de 2,4 Mo). L'API Blobs gère **jusqu'à 100 Mo** sans
  redirection. La base d'URL est **statique** (`api.github.com`), ce qui reste
  compatible avec l'actualisation planifiée du service Power BI.

### 8.2 Les tables

Dossier : `Reporting BI.SemanticModel/definition/tables/`

| Table | Source | Rôle |
|---|---|---|
| `Marché secondaire` | `marche_secondaire.csv` | Transactions (volumes, rendements, encours…) |
| `Calendrier` | `calendrier_emissions.csv` | Émissions passées / à venir |
| `Courbes de taux` | `courbes_taux.csv` | Taux zéro coupon et après lissage par maturité |
| `BRVM Obligations` | `brvm_obligations.csv` | Cotations obligataires |
| `Dates` | *calculée en M* | Table de dates (Année, Mois, Trimestre, Année-Mois) reliant tout |
| `Mesures` | *table technique* | Ne contient **que des mesures** (aucune donnée) |

Chaque table de données a une **partition M** qui fait :
`Csv.Document(GitHubFichier("…​.csv"), …)` → `PromoteHeaders` → `TransformColumnTypes`
(avec la culture `en-US` pour lire les décimales à point). Les types sont
déclarés explicitement (dates, nombres, texte, booléen).

La table **`Dates`** est générée en M (`List.Dates` de 2014 à l'année en cours +2)
et marquée « table de dates ». Elle est reliée à chaque table de faits par sa
colonne date → un seul axe temporel commun.

### 8.3 Les mesures

Fichier : `…/tables/Mesures.tmdl`. Exemples clés :

- `Volume global échangé`, `Volume global (Mds FCFA)`, `Volume nominal échangé`
- `Nb transactions`, `Nb lignes cotées`
- `Rendement moyen` (moyenne simple) et **`Rendement moyen pondéré`**
  (pondéré par le volume — plus juste pour un gestionnaire)
- `Encours total`
- `Nb émissions à venir`, `Nb émissions total`
- `Nb obligations cotées`, `Taux facial moyen (BRVM)`
- `Taux dernière courbe` / `Taux après lissage moyen` (courbes)
- `Texte mise à jour` (mesure texte affichée sur la page d'accueil)

Les **relations** sont dans `definition/relationships.tmdl` (chaque table de
faits → `Dates[Date]`).

> Détail technique TMDL : l'indentation se fait **avec des tabulations** (pas des
> espaces), et le corps M d'une expression est indenté plus profondément que ses
> propriétés (`lineageTag`, `annotation`).

---

## 9. Étape 7 : le thème Simple Header - Blue

Fichiers : [`outils/theme_simple_header_blue/`](../../outils/theme_simple_header_blue/), copiés dans
`Reporting BI.Report/StaticResources/RegisteredResources/` par
[`outils/appliquer_theme_powerbi.py`](../../outils/appliquer_theme_powerbi.py) : le thème
`Simple-Header---Blue.json` et les fonds de page SVG du modèle Power BI « Simple Header - Blue ».

| Rôle | Couleur |
|---|---|
| Bandeau haut, titres | `#1F2F4C` |
| Bandeau bas, couleur principale | `#2C4770` |
| Pavé gauche, couleur secondaire | `#3B5E94` |
| Fond de page | `#D2D2D2` |

Chaque page porte le fond `Overview.svg` (bandeau de 75 px en haut, pavé de 192 px à gauche) ; le
titre est dans la bande haute, le sous-titre dans la bande basse, en blanc ; la date de mise à jour
est dans le pavé gauche. Le thème masque par défaut légendes et titres d'axes ; un visuel qui en a
besoin les réactive dans son volet Format.

**Enregistrement du thème** (dans `Reporting BI.Report/definition/report.json`) :
il faut à la fois une entrée dans `resourcePackages` (type `RegisteredResources`)
**et** un bloc `themeCollection.customTheme` — ce dernier **doit contenir**
`reportVersionAtImport` (sinon Power BI refuse d'ouvrir le rapport : c'est
l'erreur « propriété requise reportVersionAtImport »).

---

## 10. Étape 8 — Les pages du rapport (PBIR)

Le format PBIR décrit **un fichier JSON par visuel**, sous
`Reporting BI.Report/definition/pages/<id_page>/visuals/<id_visuel>/visual.json`,
plus un `page.json` par page et un `pages.json` (ordre des pages).

Comme ce JSON est verbeux et répétitif, il est **généré par un script Python** :
[`scripts/generer_pages_rapport.py`](scripts/generer_pages_rapport.py). Ce script
contient des « briques » (`card`, `chart`, `slicer`, `table`, `textbox`,
`header`) et décrit chaque page de façon lisible.

Anatomie d'un visuel (exemple simplifié d'un graphique) :

```json
{
  "$schema": ".../visualContainer/1.4.0/schema.json",
  "name": "…_line",
  "position": { "x": 16, "y": 244, "z": 0, "width": 616, "height": 220, "tabOrder": 0 },
  "visual": {
    "visualType": "lineChart",
    "query": { "queryState": {
      "Category": { "projections": [ { "field": { "Column": {
        "Expression": { "SourceRef": { "Entity": "Dates" } }, "Property": "Année" } },
        "queryRef": "Dates.Année", "nativeQueryRef": "Année" } ] },
      "Y": { "projections": [ { "field": { "Measure": {
        "Expression": { "SourceRef": { "Entity": "Mesures" } }, "Property": "Volume global (Mds FCFA)" } },
        "queryRef": "Mesures.Volume global (Mds FCFA)", "nativeQueryRef": "Volume global (Mds FCFA)" } ] }
    } },
    "objects": { "title": [ … ], "dataPoint": [ … ] }
  }
}
```

Les 5 pages (destinées aux gestionnaires) :

1. **Accueil** — bandeau + date de mise à jour + 5 KPI (volume, transactions,
   rendement pondéré, émissions à venir, obligations cotées) + volume par
   année / par émetteur + répartition par instrument.
2. **Marché secondaire** — évolution du volume, rendement pondéré par émetteur,
   table détaillée, slicers (année, émetteur, instrument).
3. **Courbes de taux** — courbe par pays (dernière publication), évolution des
   taux moyens, table ; slicers pays / date.
4. **Calendrier des émissions** — émissions par pays / par instrument, table
   passé + à venir ; slicers statut / pays / année.
5. **Cotations BRVM** — indicateurs + répartition par catégorie + table des
   obligations cotées.

**Régénérer les pages** :

```bash
# Fermer d'abord le rapport dans Power BI Desktop (verrou de fichiers).
python umoa-titres/powerbi/generer_pages_rapport.py
```

Le script **écrase les fichiers en place** (les identifiants de visuels sont
fixes). Pour supprimer un visuel du design, effacer son dossier à la main puis
relancer.

---

## 11. Problèmes rencontrés et solutions (mémo)

Ces obstacles reviendront si vous refaites un projet similaire :

| Symptôme | Cause | Solution appliquée |
|---|---|---|
| `git push` ouvre une fenêtre d'identifiants / échoue | Jeton entouré de chevrons `<…>` dans l'URL du remote | Retirer les chevrons de l'URL du remote |
| Ouverture rapport : « propriété requise reportVersionAtImport » | `customTheme` incomplet | Ajouter `reportVersionAtImport` au `customTheme` |
| Web.Contents 404 sur les CSV | Dépôt **privé** : `raw.githubusercontent` renvoie 404 sans auth | Passer par l'**API GitHub authentifiée** (token) |
| Web.Contents **expire** (timeout) | Fichiers > 1 Mo → l'API Contents redirige | Utiliser l'**API Git Blobs** (base64, jusqu'à 100 Mo) |
| « niveaux de confidentialité ne peuvent pas être utilisés ensemble » | Pare-feu de Power BI (2 appels chaînés trees→blobs) | **Ignorer les niveaux de confidentialité** (voir §12) |
| Générateur de pages : `PermissionError` | Rapport ouvert (verrou OneDrive/PBI) | **Fermer le rapport** avant de régénérer |

---

## 12. Publier et partager en toute sécurité

Objectif : que **plusieurs gestionnaires** consultent le rapport, toujours à jour
(grâce à GitHub Actions), **sans jamais manipuler de jeton ni de fichier local**,
et **sans exposer le dépôt privé**.

### 12.1 Préparer le jeton d'accès (une fois)

1. GitHub → **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token**.
2. **Repository access** : *Only select repositories* → ce dépôt uniquement.
3. **Permissions → Repository → Contents : Read-only** (rien d'autre).
4. Choisir une **expiration** (ex. 90 jours) et générer. Copier le jeton.

> Sécurité : un *fine-grained token* limité à **lecture du contenu d'un seul
> dépôt** ne peut rien faire d'autre. En cas de fuite, il ne donne accès qu'à ces
> CSV, et vous pouvez le **révoquer** à tout moment (le régénérer côté Power BI).

### 12.2 Renseigner le jeton dans Power BI Desktop

1. Ouvrir `Reporting BI.pbip`.
2. **Accueil → Transformer les données → Gérer les paramètres** → coller le jeton
   dans `GitHubToken`.
3. **Actualiser**. Si Power BI demande des identifiants pour `api.github.com`,
   choisir **Anonyme** (l'authentification passe par l'en-tête, pas par Power BI).
4. Régler le **pare-feu de confidentialité** : *Fichier → Options et paramètres →
   Options → FICHIER ACTUEL → Confidentialité →* cocher **« Ignorer les niveaux
   de confidentialité… »**. (Sans risque : une seule source, `api.github.com`.)

### 12.3 Publier dans le service Power BI et partager

C'est **la bonne façon de partager** (les gestionnaires ne voient jamais le jeton
ni les fichiers) :

1. Dans Power BI Desktop : **Publier** → choisir un **espace de travail**
   (idéalement un workspace d'équipe).
2. Dans le service (app.powerbi.com), ouvrir le **jeu de données** →
   **Paramètres** :
   - **Informations d'identification de la source** (`api.github.com`) :
     méthode **Anonyme**, niveau de confidentialité **Public** (ou *Organisation*).
   - **Paramètres** : renseigner `GitHubToken` (le jeton y est stocké de façon
     sécurisée, côté service).
   - **Actualisation planifiée** : activer et choisir la fréquence (ex. tous les
     jours ouvrés en fin d'après-midi, après le passage de GitHub Actions).
3. **Partager** : publier une **App Power BI** depuis le workspace, ou donner
   accès en **lecture** au rapport / workspace aux gestionnaires. Ils consultent
   le rapport publié — aucune installation, aucun jeton, données toujours fraîches.

### 12.4 Règles de sécurité à respecter

- **Ne jamais** écrire le jeton en clair dans un fichier versionné. Il reste
  **vide** dans le dépôt (`GitHubToken = ""`) et se saisit dans Power BI / le
  service. *(À chaque `git pull` de `expressions.tmdl`, le paramètre revient à
  vide : c'est voulu. En pratique, une fois publié dans le service, on n'y touche
  plus.)*
- Utiliser un **fine-grained token** en **lecture seule** sur **ce seul dépôt**,
  avec **expiration**. Le renouveler avant échéance (le mettre à jour dans le
  service).
- Garder le **dépôt privé** : les scripts, données et jeton potentiel ne sont pas
  exposés. Le partage passe par le **service Power BI**, pas par le dépôt.
- En cas de doute (jeton compromis) : **révoquer** le token sur GitHub → en créer
  un nouveau → le mettre à jour dans le service. Rien d'autre à changer.

---
