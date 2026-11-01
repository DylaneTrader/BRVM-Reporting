# BRVM Analytics — Spécification pour reconstruction en rapport Power BI

> **Objectif** — Reproduire le plus fidèlement possible l'application Streamlit **BRVM Analytics** sous forme de rapport **Power BI structuré par pages**. Ce document décrit, page par page, chaque visuel (tableaux, graphiques, filtres, cartes KPI, etc.), le modèle de données sous-jacent, la charte graphique dérivée du logo, et un **ordre de construction avec points d'arrêt de validation**.
>
> **Public** — Agent IA chargé de construire le rapport. **Procédure imposée : construire une page à la fois, puis s'arrêter et attendre la validation de l'utilisateur avant de passer à la page suivante.**

---

## 0. Comment utiliser ce document

1. Lire d'abord la **section 1 (Charte graphique)** et la **section 2 (Modèle de données)** — elles sont transversales à toutes les pages.
2. Construire les pages dans l'ordre de la **section 4** (build order).
3. Après **chaque page**, produire une capture / description de ce qui a été construit et **demander validation**. Ne pas enchaîner.
4. Les mesures DAX récurrentes sont centralisées en **section 3**. Les créer une fois, les réutiliser partout.

### Note de cadrage : Streamlit → Power BI
L'app d'origine utilise des **onglets internes** (`st.tabs`) sur presque toutes les pages. Power BI n'a pas d'onglets natifs dans une page. **Convention retenue :**
- Un onglet Streamlit « lourd » (avec ses propres visuels) → **une page Power BI dédiée**, OU
- **navigation par signets** (bookmarks) + boutons stylés en haut de page pour simuler les onglets quand ils partagent le même contexte.
- Les longues pages de documentation théorique (page *À propos*) → une page Power BI « Méthodologie » synthétique (les formules deviennent des zones de texte), à basse priorité.

---

## 1. Charte graphique (dérivée du logo)

Le logo **BRVM ANALYTICS** (taureau + flèche) est en tons **brun/taupe/crème**. L'app applique déjà une palette « Claude/beige » parfaitement cohérente avec le logo. **On conserve cette palette.**

### 1.1 Couleurs primaires (issues du logo + thème app)

| Rôle | Hex | Usage |
|---|---|---|
| **Brun foncé (logo – taureau / "BRVM")** | `#3D3429` | Titres, en-têtes, texte fort |
| **Brun-dark thème** | `#4A3728` | Texte de titre, libellés d'axes |
| **Brun moyen / accent principal** | `#8B7355` | Accents, labels, lignes de référence |
| **Taupe / or (logo – flèche & "ANALYTICS")** | `#C4A77D` | Bordures mises en avant, séries neutres, accent chaud secondaire |
| **Tan / surfaces secondaires** | `#E8DDD4` | Fonds de cartes, sidebar, quadrillage des graphes |
| **Beige / fond global** | `#FAF9F6` | Arrière-plan des pages et des visuels |
| **Crème logo** | `#FEFAF1` | Variante de fond clair |
| **Orange chaud** | `#D97706` | Accent d'alerte / mise en avant |

### 1.2 Couleurs sémantiques (performance & états)

| Rôle | Hex |
|---|---|
| **Positif / hausse** | `#10B981` (vert) — variante claire bandeau `#6EE7B7` |
| **Négatif / baisse** | `#EF4444` (rouge) — variante claire bandeau `#FCA5A5` |
| **Avertissement** | `#F59E0B` |
| **Info** | `#3B82F6` |
| **Texte secondaire (muted)** | `#6B7280` |
| **Échelle divergente (heatmaps/treemap)** | rouge `#EF4444` → crème `#FAF9F6` → vert `#10B981`, **point médian = 0** |

### 1.3 Typographie & style visuel
- Police proche du thème : **sans-serif** (Segoe UI par défaut Power BI convient). Titres en brun foncé, semi-gras.
- **Bandeau d'en-tête** (voir 2.5) : dégradé `#4A3728 → #8B7355` (135°), texte crème.
- Cartes KPI (« stat-card ») : fond `#FAF9F6`, bordure fine `#E8DDD4`, coin arrondi ~12px, valeur en gros brun foncé, libellé en muted.
- Coins arrondis, ombres légères, densité aérée.
- **Logo** `assets/logo.png` : placé en haut à gauche de chaque page (bandeau) + sur la page d'accueil (largeur ~220px).

### 1.4 Thème Power BI (JSON)
Générer un fichier **`theme.json`** Power BI reprenant ces couleurs (dataColors dans l'ordre : `#8B7355, #C4A77D, #4A3728, #D97706, #10B981, #EF4444, #3B82F6, #E8DDD4`, `background #FAF9F6`, `foreground #4A3728`, `tableAccent #C4A77D`). Charger via **Affichage → Thèmes → Rechercher des thèmes**.

---

## 2. Modèle de données

L'app lit un dossier `data/` (identique dans l'autre repo de scraping). Les fichiers sources et leur transformation en **modèle en étoile** Power BI :

### 2.1 Sources brutes

| Source | Emplacement | Format | Contenu |
|---|---|---|---|
| Historique actions | `data/actions/{TICKER}_{pays}_historique.csv` | CSV `;`, décimale `,` | 1 fichier / action. Colonnes : `Date; Ouverture; Plus_Haut; Plus_Bas; Cloture; Volume_Titres; Volume_FCFA; Variation_Pct` |
| Fiche société | `data/societes/{TICKER}_societe.json` | JSON | 1 fichier / action : `ticker, Nom, Chiffre d'affaires, Résultat net, BNPA, PER, Dividende, ISIN, Nombre_Titres, Flottant(_Pct), Valorisation, Secteur, La société (desc), Dirigeants, Adresse, Téléphone, Conseil_*` (recommandation technique sikafinance) |
| Historique indices | `data/indices/{IDX}_historique.csv` | CSV `;` | Mêmes colonnes OHLCV que les actions |
| Info indices | `data/indices/{IDX}_info.json` | JSON | `Symbol, Name, ISIN` |
| Résumé scraping | `data/resume_scraping.csv` | CSV `;` | `Ticker; Type; Nb_Lignes; Date_Min; Date_Max; Dernier_Cours` |
| Actualités | `data/news/actualites_brvm.csv` | CSV `;` | `id; titre; date_publication; auteur; categorie; contenu; image_url; url; date_scraping` |
| Synthèse top/flop | `data/synthese.json` | JSON | `generated_at`, `top_flop.top5/flop5` (ticker, cours, variation_1j, date) |
| Dividendes *(nouveau scraper)* | `scraper_dividendes_unified.py` → `data/` | CSV/JSON | Historique des dividendes par société (à intégrer si présent) |
| Portefeuilles / Stratégies | `data/portefeuilles.json`, `data/strategies.json` | JSON | Données applicatives (voir pages 9 & 10 — largement hors périmètre BI) |

> ⚠️ **Locale FR** : séparateur `;`, décimale `,`, montants en **FCFA** avec espaces (`1 334 874`), pourcentages `22,47%`. À gérer dans Power Query (Type/Locale = Français, ou remplacement `,`→`.`).
> ⚠️ Les CSV commencent par un **BOM UTF-8** et certaines valeurs `Variation_Pct` sont **vides** en première ligne.
> ⚠️ Les indices ont des symboles à underscore (`BRVM_CB`, `BRVM_TEL`…) ; ne pas confondre avec le suffixe pays des actions.

### 2.2 Tables cibles Power BI (modèle en étoile)

**Tables de faits**
1. **`Cotations_Actions`** (long) : `Date, Symbol, Ouverture, PlusHaut, PlusBas, Cloture, VolumeTitres, VolumeFCFA, VariationPct`
   *(dépivoter : concaténer les ~47 CSV, ajouter `Symbol` depuis le nom de fichier).*
2. **`Cotations_Indices`** (long) : mêmes colonnes + `Symbol` (indice).

**Tables de dimensions**
3. **`Dim_Action`** (depuis les JSON sociétés) : `Symbol, Name, Secteur, ISIN, NombreTitres, PER, Dividende, BNPA, ChiffreAffaires, ResultatNet, Valorisation, FlottantPct, Description, Dirigeants, Adresse, Telephone, Conseil_Texte, Conseil_Image_URL`.
4. **`Dim_Indice`** : `Symbol, Name, ISIN`.
5. **`Dim_Date`** : calendrier continu (min→max des cotations). Colonnes : `Date, Année, Trimestre, Mois, Semaine, JourSemaine, AnnéeMois`, marqueurs `EstDébutSemaine/Mois/Trimestre/Année`. **Marquer comme table de dates.**
6. **`Dim_Secteur`** (optionnel, dérivé de `Dim_Action.Secteur`).

**Tables secondaires** : `Resume_Scraping`, `Actualites`, `Dividendes`.

### 2.3 Relations
- `Dim_Date[Date]` 1—* `Cotations_Actions[Date]`
- `Dim_Date[Date]` 1—* `Cotations_Indices[Date]`
- `Dim_Action[Symbol]` 1—* `Cotations_Actions[Symbol]`
- `Dim_Indice[Symbol]` 1—* `Cotations_Indices[Symbol]`
- `Dim_Secteur[Secteur]` 1—* `Dim_Action[Secteur]`

> Pour l'analyse **corrélation / bêta** (page 4) qui compare action vs indice sur le même axe date, prévoir soit des mesures avec `USERELATIONSHIP`, soit une table de dates partagée (déjà le cas via `Dim_Date`). Les calculs matriciels lourds (matrice de corrélation N×N, bêta glissant) sont **coûteux en DAX** : envisager de les **pré-calculer en Power Query / dans le repo de scraping** et de les charger comme tables prêtes à l'emploi (voir notes page 4).

### 2.4 Segments (slicers) globaux recommandés
Panneau de filtres réutilisable (via panneau latéral / signet) : **Secteur**, **Action (Symbol/Name)**, **Indice**, **Période** (plage de dates). La « Période » de l'app est un `selectbox` de fenêtres (1J, 1S, 1M, 3M, 6M, 1A, 3A) + calendaires (WTD, MTD, QTD, STD, YTD, OTD) — voir 3.2 pour la table de paramètres.

### 2.5 En-tête commun à toutes les pages
Bandeau haut : **logo** à gauche, **titre de page** au centre, et à droite un mini **bandeau marché** (voir page Accueil) : *BRVM Composite, Variation du jour, YTD, Nb actions suivies, Dernière séance*. Reproduire le dégradé brun.

---

## 3. Mesures DAX transversales

### 3.1 Table de paramètres « Période »
Créer une table `P_Periode` (saisie manuelle) pilotant les fenêtres glissantes :

| Cle | Libelle | Jours | Type |
|---|---|---|---|
| 1D | 1 Jour | 1 | glissante |
| 1W | 1 Semaine | 7 | glissante |
| 1M | 1 Mois | 30 | glissante |
| 3M | 3 Mois | 91 | glissante |
| 6M | 6 Mois | 182 | glissante |
| 1Y | 1 An | 365 | glissante |
| 3Y | 3 Ans | 1095 | glissante |
| WTD | Depuis lundi | — | calendaire |
| MTD | Depuis 1er du mois | — | calendaire |
| QTD | Depuis début trimestre | — | calendaire |
| STD | Depuis début semestre | — | calendaire |
| YTD | Depuis 1er janvier | — | calendaire |
| OTD | Depuis origine | — | calendaire |

### 3.2 Mesures clés (à créer)
- **Cours de clôture** : `Dernier Cours = CALCULATE(LASTNONBLANKVALUE(Dim_Date[Date], MAX(Cotations_Actions[Cloture])))`
- **Rendement période glissante** : `Rendement Periode = VAR d = SELECTEDVALUE(P_Periode[Jours]) ... (Cloture fin / Cloture début - 1)`. Reproduire les fonctions `calculate_returns_for_period` et `calculate_calendar_performance` de `utils.py`.
- **Performances calendaires** : `Perf WTD`, `Perf MTD`, `Perf QTD`, `Perf STD`, `Perf YTD`, `Perf OTD`.
- **Rendement cumulé base 100** : `Base100 = DIVIDE(Cloture; PremièreCloturePériode) * 100`.
- **Drawdown %** : `Drawdown = Cloture / MAXrunning(Cloture) - 1`.
- **Volatilité annualisée** : `écart-type(rendements quotidiens) * SQRT(252)`.
- **Capitalisation boursière** : `Capi = Dim_Action[NombreTitres] * [Dernier Cours]`.
- **Rendement dividende** : `Div Yield = DIVIDE(Dim_Action[Dividende]; [Dernier Cours])`.
- **Bêta / Corrélation** (action vs indice) : voir page 4.

> Les formules exactes (WTD/MTD/QTD/STD/YTD/OTD, rolling, cumulé) sont dans `utils.py` du repo — les répliquer à l'identique pour la cohérence des chiffres.

---

## 4. Ordre de construction & points de validation

Construire dans cet ordre, **un arrêt validation après chaque page** :

| # | Page Power BI | Correspond à | Priorité |
|---|---|---|---|
| 0 | **Modèle + thème** (Power Query, relations, `theme.json`, `Dim_Date`, mesures 3.2) | infra | 🔴 socle |
| 1 | **Accueil / Tableau de bord** | `1_🏠_Accueil.py` | 🔴 |
| 2 | **Overview – Actions & KYC** | `2_📋_Overview.py` (onglet Actions) | 🔴 |
| 3 | **Overview – Indices** | `2_📋` (onglet Indices) | 🟠 |
| 4 | **Overview – Santé du marché** (Régime + Fear & Greed) | `2_📋` (onglet Santé) | 🟠 |
| 5 | **Performances** (calendaires / glissantes / comparatif) | `3_📈_Performances.py` | 🔴 |
| 6 | **Corrélations & Bêta** | `4_🔗` | 🟠 |
| 7 | **Indicateurs techniques** | `5_📐` | 🟢 (voir note) |
| 8 | **Importation / Qualité des données** | `6_📥` | 🟠 |
| 9 | **Stratégie & Simulation** | `9_📊`, `🔟_💼` | 🟢 |
| 10 | **Actualités** | `data/news` | 🟢 |
| 11 | **Méthodologie / À propos** | `7_ℹ️` | 🟢 |

> Les pages **Chatbot IA (8)**, **Blog communautaire (11)**, **Support/tickets (12)** sont **interactives/transactionnelles** et **hors périmètre Power BI** (pas de reporting). Les mentionner à l'utilisateur mais ne pas les reconstruire, sauf demande explicite (le Blog/Support pourraient devenir de simples tables en lecture seule).

---

# 5. Spécification page par page

> Pour chaque page : liste ordonnée des zones, type de visuel Power BI, champs/mesures, filtres, mise en forme. Les couleurs renvoient à la section 1.

---

## PAGE 1 — Accueil / Tableau de bord du marché
*(`pages/1_🏠_Accueil.py`)*

**Titre** : « Tableau de bord du marché » + logo (220px).

### 1.1 Bandeau marché (5 KPI en ligne) — *carte multi-lignes / cartes stylées*
Fond dégradé brun `#4A3728→#8B7355`, texte crème. Valeurs +/- colorées (vert clair `#6EE7B7` / rouge clair `#FCA5A5`).
| KPI | Mesure |
|---|---|
| BRVM Composite | dernier niveau de l'indice `BRVMC` |
| Variation du jour | variation % 1 séance de BRVMC |
| Performance YTD | perf YTD de BRVMC |
| Actions suivies | nb d'actions = `DISTINCTCOUNT(Cotations_Actions[Symbol])` |
| Dernière séance | `MAX(Dim_Date[Date])` format `jj/mm/aaaa` |

### 1.2 Filtre Période — *slicer*
Slicer sur `P_Periode` (liste déroulante), défaut **1 Mois**. Sous-titre dynamique : « *N actions éligibles sur la période …* ».

### 1.3 Top 5 / Flop 5 performers — *2 tableaux/cartes côte à côte*
Deux colonnes. Chaque ligne = carte : **rang #**, **nom société**, **ticker**, **rendement %** (vert/rouge) + **sparkline 30 jours** (line chart miniature, vert pour top / rouge pour flop).
- Données : `Rendement Periode` par action, top 5 desc / flop 5 asc.
- Sparkline Power BI : mini graphique en courbes (30 dernières séances de `Cloture`) — utiliser un visuel *Sparkline* natif dans le tableau, ou un petit line chart par carte.

### 1.4 Carte sectorielle — *Treemap*
- **Hiérarchie** : `BRVM (racine) → Secteur → Nom action`.
- **Taille** = capitalisation boursière (`NombreTitres × Dernier Cours`, en Mrd FCFA). Secteur = somme des capis.
- **Couleur** = rendement sur la période choisie. Échelle divergente rouge→crème→vert, **médian 0**, bornée au 95ᵉ percentile de |rendement| pour éviter les outliers.
- Tooltip : Rendement %, Capi (Mrd FCFA), part du parent %.
- Étiquette : nom + rendement signé.

### 1.5 Tableau complet des rendements — *table (repliable)*
Colonnes : `Nom, Symbole, Secteur, Rendement <période> (%)`, trié desc. Format `+0.00%` conditionnel vert/rouge. Bouton **Export CSV** (natif Power BI).

**✅ Point d'arrêt validation — Page 1.**

---

## PAGE 2 — Overview : Statistiques descriptives (Actions & KYC)
*(`pages/2_📋_Overview.py`, onglet « Actions »)*

**Titre** : « Overview – Statistiques Descriptives ».

### 2.1 Bandeau 5 cartes KPI globales — *cartes « stat-card »*
`Actions suivies` · `Indices suivis` · `Séances médianes / action` · `Première date` · `Dernière date`.

### 2.2 Know Your Company (KYC) — *fiche société dynamique*
- **Slicer** : sélection d'une action (`Dim_Action[Name]`).
- **Bloc gauche** : 6 cartes KPI — `Valorisation (MFCFA)`, `PER (×)`, `Dividende (FCFA)`, `Flottant`, `Nb de titres`, `Cours actuel (FCFA)`. + 3 cartes : `Chiffre d'affaires`, `Résultat net`, `BNPA`.
- **Bloc droit** : **sparkline / line chart 1 an** du cours + 2 cartes `Perf. 1 an (%)` et `Plus haut 1 an`.
- (Optionnel) zone texte : description société (`La société`), dirigeants, adresse.

### 2.3 Classements — *3 graphiques en barres côte à côte*
Trois bar charts horizontaux (Top N) :
1. **Meilleurs rendements dividende** (Div Yield = Dividende / Cours).
2. **Plus grosses capitalisations** (Capi).
3. **Meilleures performances** (rendement sur période).
Couleur barres : accent `#C4A77D` / brun ; mettre en évidence la valeur.

### 2.4 Positionnement valeur / croissance — *nuage de points (scatter)*
- **X** = PER, **Y** = Rendement total, **taille** = capitalisation, **couleur** = secteur.
- Tooltip : nom, PER, rendement, capi. (« PER vs Rendement total ».)

### 2.5 Fiche détaillée des sociétés — *table (repliable)*
Toutes les colonnes de `Dim_Action` (vue tabulaire), `hide_index`.

### 2.6 Statistiques descriptives par action — *table*
Par action : moyenne, écart-type (volatilité), min, max, dernier cours, nb d'observations, rendement total, volatilité annualisée. Format conditionnel.

### 2.7 Drawdown — *graphique en aires*
- **Slicers** : multi-sélection d'actions, période, case « indice de référence » + choix de l'indice.
- **Visuel** : courbes de drawdown (%) remplies en rouge translucide (`rgba(239,68,68,0.12)`), ligne 0 en pointillé.

**✅ Point d'arrêt validation — Page 2.**

---

## PAGE 3 — Overview : Indices
*(`2_📋` onglet « Indices »)*

### 3.1 Informations sur les indices — *table* (`Symbol, Name, ISIN`).
### 3.2 Statistiques descriptives des indices — *table* (moyenne, vol, min, max, dernier, perf).
### 3.3 Évolution normalisée (base 100) — *graphique en courbes multi-séries*
- **Slicers** : multi-indices, période (`1M…MAX`).
- **Y** = valeur base 100. Palette qualitative (Set1-like), quadrillage `#E8DDD4`, ligne de repère 100.

**✅ Point d'arrêt validation — Page 3.**

---

## PAGE 4 — Overview : Santé du marché
*(`2_📋` onglet « Santé du marché »)* — **la page la plus « signature ».**

### 4.1 Régime de marché dynamique
- **Paramètres** (slicers/champs de saisie) : MM court (déf. 20 j), MM moyen (50 j), MM long (200 j), indice de référence, période.
- **4 cartes** : régime actuel (Haussier / Baissier / Neutre), % actions au-dessus de leur MM long (breadth), tendance, etc.
- **Visuel principal** : line chart de l'indice avec **3 moyennes mobiles** superposées + **bandes de fond colorées** selon le régime (vert/rouge/gris).
> DAX lourd : le calcul du régime (croisements MM + breadth) gagne à être **pré-calculé** dans le pipeline de scraping et chargé comme colonne `Regime` sur `Cotations_Indices`.

### 4.2 Fear & Greed BRVM — *jauge (gauge) + barres composantes*
- **Slicers/poids** : poids Breadth (déf 3), Volatilité (3), Momentum (2), Dispersion (2) ; fenêtres vol court/long, momentum.
- **Visuel gauche** : **jauge** 0–100 (indicateur type gauge), zones colorées : 0–25 *Extreme Fear* (rouge) … 75–100 *Extreme Greed* (vert), aiguille sur le score courant.
- **Visuel droite** : **bar chart** des 4 composantes normalisées (Breadth, Volatilité, Momentum, Dispersion) avec leur contribution.
> Là encore : **pré-calculer** l'indice Fear & Greed et ses composantes en amont ; Power BI n'affiche que le résultat.

**✅ Point d'arrêt validation — Page 4.**

---

## PAGE 5 — Performances (Calendaires · Glissantes · Comparatif)
*(`pages/3_📈_Performances.py`)*

Structure d'origine : onglets **Actions / Indices**, chacun avec sous-onglets **Calendaires / Glissantes / Graphique comparatif**. En Power BI : **1 page Actions + 1 page Indices**, ou navigation par signets. Ci-dessous la version **Actions** (répliquer pour Indices).

### 5.1 Filtre secteur — *slicer* (`Tous` + liste des secteurs).

### 5.2 Performances calendaires
- **Rotation sectorielle** — *heatmap (matrice avec mise en forme conditionnelle)* : lignes = secteurs, colonnes = `WTD, MTD, QTD, STD, YTD, OTD`, valeur = perf moyenne, échelle divergente rouge→crème→vert (médian 0), triée par YTD desc.
- **Détail par action** — *table/matrice* : `Nom, Secteur, WTD, MTD, QTD, STD, YTD, OTD`, format `+0.00%` conditionnel vert/rouge. Export CSV.

### 5.3 Performances glissantes — *table* : `Nom, Secteur, 1 Sem, 1 Mois, 3 Mois, 6 Mois, 1 An, 3 Ans`, conditionnel. Export CSV.

### 5.4 Graphique comparatif d'évolution — *line chart*
- **Slicers** : multi-actions (max 10), période (`1M…MAX`), case « ajouter un indice de référence » + choix indice.
- **Mode d'affichage** (slicer/boutons) : **Indexée base 100** / **Drawdown (%)** / **Rendement quotidien (%)**.
  - Base 100 : ligne repère 100.
  - Drawdown : aires rouges translucides, repère 0.
  - Rendement quotidien : courbes, repère 0.
- Palette Set2, hover unifié, quadrillage `#E8DDD4`.

**✅ Point d'arrêt validation — Page 5** (puis répliquer pour Indices).

---

## PAGE 6 — Corrélations & Bêta
*(`pages/4_🔗_Corrélations_&_Bêta.py`)* — onglets **Corrélations Actions / Corrélations Indices / Analyse Bêta**.

### 6.1 Matrice de corrélation des actions — *heatmap (matrice conditionnelle)*
- **Slicers** : secteur, méthode (`Pearson/Spearman/Kendall`), nb max d'actifs (slider), période, case « clustering » (regroupement hiérarchique).
- **Visuel** : matrice N×N couleur divergente (−1 rouge → 0 crème → +1 vert).
- **4 cartes** : corrélation moyenne, médiane, max, min.
- **2 tables repliables** : Top 10 paires les plus / les moins corrélées.
> **Pré-calcul recommandé** : générer la matrice de corrélation (par période & méthode) en amont et la charger comme table longue `Corr(SymbolA, SymbolB, Periode, Methode, Valeur)`. Un vrai calcul N×N glissant en DAX est impraticable.

### 6.2 Matrice de corrélation des indices — *heatmap* (idem, + table des corrélations + encart d'interprétation).

### 6.3 Analyse Bêta — *cartes + régression*
- **Slicers** : action, indice, période.
- **4 cartes** : **Bêta**, **Volatilité action (%)**, **Volatilité indice (%)**, **Corrélation**.
- **Bêta glissant** — *line chart* : bêta sur fenêtre glissante + 4 cartes (bêta actuel, moyen, max, min).
- **Régression des rendements** — *scatter* : rendements action (Y) vs indice (X) + **droite de régression** (bêta = pente).
> Bêta = `COVAR(rdt_action, rdt_indice) / VAR(rdt_indice)`. Le **bêta glissant** est coûteux → pré-calculer côté pipeline (table `Beta(Symbol, Indice, Date, Beta)`).

**✅ Point d'arrêt validation — Page 6.**

---

## PAGE 7 — Indicateurs techniques
*(`pages/5_📐_Indicateurs_Techniques.py`)* — **la page la plus riche** (≈ 15 indicateurs).

> **Note de faisabilité** : cette page est un terminal d'analyse technique très interactif (sliders de paramètres pour chaque indicateur, recalcul en direct). Power BI n'est pas idéal pour recalculer RSI/MACD/Bollinger dynamiquement selon des sliders. **Recommandation : pré-calculer tous les indicateurs (avec paramètres par défaut) dans le pipeline de scraping** et les charger dans une table `Indicateurs(Symbol, Date, RSI, SMA20, SMA50, EMA12, EMA26, MACD, Signal, Hist, BB_up, BB_low, %K, %D, ADX, +DI, −DI, ATR, CCI, WilliamsR, OBV, MFI, AD, SAR, …)`. Les sliders deviennent alors des **paramètres What-If Power BI** (jeu limité) ou sont figés aux valeurs par défaut.

Structure : sélection d'une action + choix de période, puis **cartes de synthèse des signaux**, puis onglets par famille d'indicateurs. Version Power BI = **une page par famille** ou navigation par signets.

### 7.1 En-tête action — *slicer action + encart « Conseil sikafinance »* (image `Conseil_Image_URL` + texte `Conseil_Texte`).
### 7.2 Synthèse des signaux — *4 cartes* (Momentum / Tendance / Volatilité / Volume : score achat-vente).
### 7.3 Onglets/pages par indicateur (chacun = un line chart + cartes de valeurs courantes) :
- **RSI** : courbe 0–100 + bornes 30/70. Cartes : RSI actuel + statut.
- **Moyennes mobiles** (SMA/EMA) : prix + MM superposées, MM additionnelles multi-select. Signaux d'achat/vente.
- **MACD / PPO** : MACD, ligne signal, histogramme. Cartes MACD/Signal/Histogramme.
- **Bandes de Bollinger** : prix + bandes ± k·σ. Cartes %B, Bandwidth, percentile.
- **Stochastique / Stoch RSI** : %K, %D. Cartes %K, %D, statut.
- **ADX / DMI** : ADX, +DI, −DI. Cartes ADX, +DI, −DI.
- **ATR** : ATR absolu + relatif. Cartes ATR (FCFA), ATR relatif %, stop suggéré (−2·ATR).
- **CCI & Williams %R** : deux oscillateurs. Cartes valeurs + statut.
- **Momentum / ROC / TRIX** : 3 oscillateurs.
- **Volume : OBV / MFI / A/D** : cartes OBV, MFI, A/D.
- **Parabolic SAR & Ichimoku** : prix + SAR + nuage Ichimoku. Cartes SAR, position vs nuage, croisement Tenkan/Kijun.
- **Recommandations ML** : sous-onglets par modèle (probabilités hausse/baisse) — *voir aussi bloc ML ci-dessous*.

### 7.4 Bloc Machine Learning (haut de page dans l'app) — *cartes + graphiques*
- **4 cartes** : Horizon (séances), Observations, Accuracy (test), F1 macro (test).
- **Graphique probabilités** (barres/jauge) de direction prédite.
- **Table** détails du modèle + **importance des variables** (bar chart) — repliable.
> Charger les sorties du modèle (`models/`, `XGBoost.py`) comme table `ML_Predictions(Symbol, Date, Proba_Hausse, Signal, …)` + table `ML_Metrics`.

**✅ Point d'arrêt validation — Page 7** (valider l'approche pré-calcul AVANT de tout construire).

---

## PAGE 8 — Importation / Qualité des données
*(`pages/6_📥_Importation.py`)* — en BI, devient **« Qualité & Couverture des données »** (le scraping lui-même reste dans le repo Python).

### 8.1 État actuel — *4 cartes KPI* : `Actions téléchargées (n/total)`, `Indices téléchargés (n/total)`, `Sociétés`, autre compteur.
### 8.2 Suivi de l'automatisation — *3 cartes* : dernière exécution, statut, **Fraîcheur (jours ouvrés)** avec code couleur (vert si récent, ambre/rouge si périmé).
### 8.3 Couverture par ticker — *bar chart (repliable)* : nb de séances par ticker (depuis `resume_scraping.csv`) + cartes : séances médianes, profondeur médiane (ans), fraîcheur médiane.
### 8.4 (Hors BI) — les contrôles de lancement de scraping (`radio`, `multiselect`, bouton « Lancer ») ne sont **pas** reproduits en Power BI.

**✅ Point d'arrêt validation — Page 8.**

---

## PAGE 9 — Stratégie & Simulation de portefeuille
*(`pages/9_📊_Stratégie.py` + `pages/🔟_💼_Simulation_Portefeuille.py`)*

> Fortement **transactionnel** (création/optimisation/achat/vente de portefeuilles, écriture dans `portefeuilles.json`/`strategies.json`). En Power BI, **version lecture seule / analytique** uniquement. Prévenir l'utilisateur que la partie « saisie » (optimiseur Markowitz/Risk Parity, achats/ventes) ne se reproduit pas dans Power BI et resterait dans l'app.

Ce qui **peut** être reporté (si les JSON de portefeuilles sont chargés) :
### 9.1 Vue portefeuille — *5 cartes KPI* : valeur, P&L, rendement, volatilité, nb de lignes.
### 9.2 Allocation — *3 donuts* : par ligne, par secteur, par pays.
### 9.3 Garde-fou de concentration — *bar chart* + seuil (slider What-If) mettant en rouge les lignes > seuil.
### 9.4 Positions — *table* (PRU, quantité, valeur, P&L, poids).
### 9.5 Performance vs BRVM Composite (base 100) — *line chart* + drawdown + cartes (perf, vol, Sharpe).
### 9.6 Frontière efficiente (Markowitz) — *scatter* : nuage de portefeuilles simulés (risque X / rendement Y, couleur = Sharpe) + points « rendement max » / « variance min » — **si** les résultats d'optimisation sont exportés comme table.

**✅ Point d'arrêt validation — Page 9.**

---

## PAGE 10 — Actualités BRVM
*(`data/news/actualites_brvm.csv`)*

- **Slicers** : catégorie, plage de dates, recherche.
- **Table / cartes** : titre, date, auteur, catégorie, extrait de contenu, lien (`url`), vignette (`image_url`).
- KPI : nombre d'articles, dernière date de scraping.

**✅ Point d'arrêt validation — Page 10.**

---

## PAGE 11 — Méthodologie / À propos
*(`pages/7_ℹ️_À_propos.py`)*

Page de documentation. En Power BI : **zones de texte + images de formules** organisées par sections (Performances, Indicateurs techniques, Corrélations, Bêta, Statistiques, Santé du marché, Stratégies Markowitz/Risk Parity, Portefeuille, LLM/Chatbot). Basse priorité — reproduire en synthèse. Inclure un **sommaire cliquable** (boutons signets vers les autres pages).

**✅ Point d'arrêt validation — Page 11.**

---

## 6. Pages NON reproduites en Power BI (à confirmer)
- **Chatbot IA** (`8_🤖`) : assistant LLM interactif — hors périmètre reporting.
- **Blog communautaire** (`11_📝`) : posts/commentaires/likes — transactionnel.
- **Support / Tickets** (`12_🎫`) : tickets + admin utilisateurs — transactionnel.
- **Écran de connexion / auth** (`app.py`, `auth_ui.py`) : géré par Power BI Service (RLS/accès), pas un visuel.

> Si l'utilisateur souhaite néanmoins un suivi : Blog et Support peuvent devenir de simples **tables de reporting** (volume de posts/tickets, statut, catégorie) alimentées par les JSON correspondants.

---

## 7. Récapitulatif des types de visuels Power BI à utiliser

| Besoin app | Visuel Power BI |
|---|---|
| Cartes KPI stylées | Carte / Carte à plusieurs lignes (thème custom) |
| Bandeau marché | Cartes sur fond dégradé (image de fond + cartes transparentes) |
| Top/Flop + sparkline | Table avec colonne *Sparkline* native |
| Treemap sectoriel | Treemap (couleur = mesure divergente) |
| Heatmaps (corrélation, rotation) | Matrice + mise en forme conditionnelle (échelle de couleurs) |
| Courbes multi-séries (base 100, prix, MM) | Graphique en courbes |
| Drawdown | Graphique en aires |
| Bar charts (classements, composantes) | Histogramme / barres |
| Scatter (PER/rendement, régression, frontière) | Nuage de points (+ ligne de tendance) |
| Jauge Fear & Greed | Jauge (Gauge) |
| Donuts allocation | Anneau (Donut) |
| Tables détaillées + export | Table / Matrice (export natif) |
| Paramètres (poids, périodes MM, k Bollinger) | Paramètres What-If + slicers |

---

## 8. Points d'attention pour l'agent constructeur
1. **Locale FR** dans Power Query (séparateur `;`, décimale `,`, montants avec espaces, `%`).
2. **Dépivoter** les ~47 CSV actions et ~13 CSV indices en tables longues via *Dossier* (Folder connector) + `Symbol` = nom de fichier.
3. **Pré-calculer** dans le repo de scraping tout ce qui est trop lourd en DAX : indicateurs techniques, matrices de corrélation, bêtas glissants, régime de marché, Fear & Greed, sorties ML. Fournir ces résultats en CSV/JSON dans `data/` — c'est le **chemin le plus fidèle et le plus performant**.
4. **Cohérence des chiffres** : répliquer les formules de `utils.py` (fenêtres WTD/MTD/QTD/STD/YTD/OTD, cumulés base 100, drawdown, volatilité annualisée ×√252).
5. **Respecter la charte** (section 1) sur tous les visuels : fonds beige, accents brun/taupe, vert/rouge sémantiques, échelles divergentes centrées sur 0.
6. **Un arrêt validation après chaque page.**

---

*Document généré pour piloter la reconstruction Power BI de BRVM Analytics. Source : application Streamlit `BRVM app` (12 pages) + repo de scraping partageant le même dossier `data/`.*
