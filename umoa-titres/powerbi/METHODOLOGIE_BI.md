# Méthodologie de calcul des éléments du reporting BI

Ce document décrit **précisément comment chaque indicateur du rapport Power BI
des titres publics UMOA** est calculé : d'où viennent les données brutes, quelles
transformations leur sont appliquées, quelles formules financières sont
utilisées, et quelles conventions ont été retenues. Il complète
[`DOCUMENTATION.md`](DOCUMENTATION.md) (qui explique l'architecture technique du
projet) en se concentrant uniquement sur la **méthodologie de calcul**.

---

## 1. Vue d'ensemble du pipeline de calcul

```
Données brutes scrapées (data/umoa_titres/…, data/brvm/…)
        │
        ▼
scripts/preparer_donnees_bi.py   ← nettoyage + calculs Python (dont scripts/finance.py)
        │
        ▼
data/_bi/*.csv                   ← 5 fichiers, colonnes déjà calculées, prêtes à l'emploi
        │
        ▼
Reporting BI.SemanticModel       ← mesures DAX (agrégations, pondérations, pentes)
        │
        ▼
Reporting BI.Report              ← visuels des 7 pages
```

**Principe directeur** : tout calcul qui dépend d'une **convention de marché
obligataire** (actualisation, duration, convexité) est fait **en Python**, une
seule fois, ligne par ligne, dans `preparer_donnees_bi.py`. Tout calcul qui
dépend du **contexte de filtre de l'utilisateur** (ce qu'il a sélectionné dans
le rapport : une période, un pays, un émetteur) est fait **en DAX**, dans les
mesures de la table `Mesures`. Cette séparation évite de dupliquer la logique
financière dans le langage DAX, plus difficile à auditer.

---

## 2. Fichiers sources et leur rôle

| Fichier `data/_bi/` | Alimenté par | Contenu |
|---|---|---|
| `marche_secondaire.csv` | `preparer_marche_secondaire()` | Transactions du marché secondaire des titres publics + indicateurs obligataires calculés (YTM, duration, convexité…) |
| `courbes_taux.csv` | `preparer_courbes()` | Courbes de taux zéro-coupon par pays/maturité/date + spreads inter-pays |
| `courbes_pente.csv` | `preparer_courbes_pente()` | Pentes de courbe (2-5 ans, 2-10 ans) par pays et par date |
| `brvm_obligations.csv` | `preparer_brvm()` | Cotations d'obligations BRVM + taux facial et catégorie extraits du nom |
| `calendrier_emissions.csv` | `preparer_calendrier()` | Calendrier des émissions passées / à venir |

Toutes les fonctions vivent dans
[`scripts/preparer_donnees_bi.py`](scripts/preparer_donnees_bi.py) et sont
orchestrées par sa fonction `main()`.

---

## 3. Nettoyage préalable des nombres

Fonction `nombre()` ([`preparer_donnees_bi.py:30-40`](scripts/preparer_donnees_bi.py#L30-L40)).

Les données sources mélangent les conventions française et anglaise
(`"241 767 670 014"`, `"122,59"`). La fonction :

1. supprime les espaces (classiques et insécables) utilisés comme séparateurs de milliers ;
2. si la valeur contient une virgule **et pas de point**, traite la virgule comme séparateur décimal ;
3. supprime toute virgule résiduelle (séparateur de milliers) ;
4. convertit en nombre (`pd.to_numeric`, `errors="coerce"` → valeur manquante si non convertible).

Cette étape est appliquée à toutes les colonnes numériques avant tout calcul,
pour ne jamais faire d'arithmétique sur une chaîne de caractères mal typée.

---

## 4. Marché secondaire — indicateurs obligataires

Bloc : [`preparer_marche_secondaire()`](scripts/preparer_donnees_bi.py#L43-L94),
lignes 76-90. Module de calcul dédié : [`scripts/finance.py`](scripts/finance.py).

### 4.1 Conventions retenues

| Convention | Choix | Justification |
|---|---|---|
| Rendement | Le `Rendement moyen` scrapé (taux actuariel annuel) est utilisé tel quel comme `YTM` | C'est déjà le rendement actuariel calculé par UMOA-Titres à partir du prix de marché |
| Composition | Annuelle (m = 1) | Convention UMOA-Titres du taux de rendement actuariel |
| Base de temps | Exact/365 (`t = jours / 365`) | Standard des marchés de taux UEMOA |
| BAT (coupon = 0) | Zéro-coupon : un flux unique à l'échéance | Pas de coupon à modéliser |
| OAT « In Fine » (IF) | Remboursement du principal en un seul flux à l'échéance (bullet) | Calcul **exact** |
| OAT amortissables (ACD, AnC, AC…) | **Approximation** par amortissement constant du principal sur les échéances restantes | Le calendrier réel d'amortissement/différé n'est pas public ; ~9 % des lignes sont concernées et sont explicitement étiquetées `Approx. (amortissable)` dans la colonne `Méthode` |

### 4.2 Construction des flux (`finance.flux`)

Pour une maturité résiduelle `T` (en années) :

- **Zéro-coupon** (`coupon = 0`) : un flux unique `1.0` à `t = T`.
- **In Fine** : un coupon annuel `coupon` à chaque date entière jusqu'à l'échéance, le dernier flux recevant en plus le remboursement du nominal (`+1.0`).
- **Amortissable** (approximation) : le nominal (`encours`, initialisé à `1.0`) est amorti par tranches égales `amort = 1.0 / n` à chaque échéance ; le flux de chaque période est `coupon * encours + amort`, et `encours` est décrémenté d'autant.

Les dates de flux (`_temps_flux`) sont générées annuellement à partir de la
fraction d'année restante jusqu'à l'échéance `T`.

### 4.3 Étape 1 — Maturité résiduelle

```python
T = (Date d'échéance - Date de transaction).dt.days / 365.0
```

→ colonne `Maturité résiduelle (années)` (arrondie à 4 décimales).

### 4.4 Étape 2 — Métriques obligataires (`finance.metriques`)

Pour chaque transaction, avec `y` = YTM (rendement moyen, en décimal) et les
flux `(t, CFt)` obtenus ci-dessus :

| Indicateur | Formule | Colonne de sortie |
|---|---|---|
| Prix théorique | `P = Σ CFt · (1+y)^(-t)` | *(intermédiaire, non exporté)* |
| **Duration de Macaulay** `D` | `D = (1/P) · Σ t · CFt · (1+y)^(-t)` | `Duration Macaulay` |
| **Duration modifiée** `D*` | `D* = D / (1 + y)` | `Duration modifiée` |
| **Convexité** `C` | `C = (1/P) · Σ t·(t+1) · CFt · (1+y)^(-t-2)` | `Convexité` |
| **DV01 (PVBP)** | `DV01 = D* · P · 1e-4` (nominal = 1), puis `× 1 000 000` pour un nominal d'1 M FCFA | `DV01 (FCFA / M nominal)` |
| **Sensibilité +100 pb** | `≈ -D* · 0,01` (variation relative de prix pour +100 pb de taux) | `Sensibilité +100pb` |

Valeurs arrondies : duration/convexité à 4 décimales, DV01 à 2 décimales,
sensibilité à 6 décimales.

**Cas dégénérés gérés** (retournent `NaN`) : pas de flux (`T ≤ 0`), rendement
manquant ou `y ≤ -0,999` (actualisation impossible), prix théorique `≤ 0`.

**Contrôles de cohérence validés** : duration < maturité pour les obligations à
coupon, duration = maturité pour les zéro-coupons, convexité toujours positive.

### 4.5 Colonne `Méthode`

Étiquette lisible associée à chaque ligne (`finance.methode`) :
- `"Zéro-coupon"` si `coupon == 0` ;
- `"Exacte (in fine)"` si le mode d'amortissement est `IF`, `0` ou vide ;
- `"Approx. (amortissable)"` sinon — **signale à l'utilisateur du rapport que
  la métrique est une approximation**, pas un calcul exact.

---

## 5. Courbes de taux — spreads et pentes

### 5.1 Spread vs moyenne UEMOA

Bloc : [`preparer_courbes()`](scripts/preparer_donnees_bi.py#L109-L133), lignes 122-130.

Pour chaque `(Date, Maturité)`, on calcule la moyenne inter-pays du taux après
lissage :

```
Taux moyen UEMOA(Date, Maturité) = moyenne, sur tous les pays, de Taux après lissage
Spread vs moyenne (pb) = (Taux après lissage − Taux moyen UEMOA) × 10 000
```

### 5.2 Spread vs Côte d'Ivoire

Le taux après lissage de la Côte d'Ivoire (émetteur de référence, le plus
liquide de l'UEMOA) est extrait pour chaque `(Date, Maturité)` puis rapproché
(`merge`) de chaque ligne :

```
Spread vs Côte d'Ivoire (pb) = (Taux après lissage − Taux CI même Date/Maturité) × 10 000
```

### 5.3 Flag « Dernière courbe »

```
Dernière courbe = (Date == max(Date))
```

Booléen utilisé dans le rapport pour n'afficher que la courbe la plus
récemment publiée sans filtrer manuellement par date.

### 5.4 Pente de courbe

Bloc : [`preparer_courbes_pente()`](scripts/preparer_donnees_bi.py#L136-L150).

Les taux après lissage sont pivotés par `(Date, Pays)` en colonnes de maturité,
pour isoler les points 2, 5 et 10 ans :

```
Pente 2-10 ans (pb) = (Taux 10 ans − Taux 2 ans) × 10 000
Pente 2-5 ans (pb)  = (Taux 5 ans  − Taux 2 ans) × 10 000
```

Une pente positive traduit une courbe des taux normale (croissante) ; une pente
négative, une inversion.

---

## 6. Cotations BRVM — extraction heuristique

Bloc : [`preparer_brvm()`](scripts/preparer_donnees_bi.py#L153-L174).

- **Taux facial** : extrait par expression régulière du nom de l'obligation
  (motif `\d+[.,]\d+\s*%`, ex. « 6,80 % » → `0.068`). Si le nom ne contient pas
  de pourcentage reconnaissable, la valeur est manquante.
- **Catégorie d'émetteur** : heuristique par mots-clés sur le nom en majuscules
  — `TPCI`, `ETAT`, `TRESOR`, `SUKUK`, `OAT`, ou motif `TPxx` (deux lettres)
  → `"État / Souverain"` ; sinon `"Privé / Institutionnel"` par défaut.

> Ces deux colonnes sont des **approximations textuelles** (pas des données
> structurées à la source) : à vérifier ponctuellement si un nom d'obligation
> sort du format attendu.

---

## 7. Agrégats du reporting (mesures DAX)

Fichier : [`Reporting BI.SemanticModel/definition/tables/Mesures.tmdl`](Reporting%20BI.SemanticModel/definition/tables/Mesures.tmdl).

Toutes les mesures réagissent au **contexte de filtre** du rapport (période,
pays, émetteur, instrument sélectionnés par l'utilisateur).

### 7.1 Agrégats simples

| Mesure | Calcul |
|---|---|
| `Volume global échangé` | `SUM(Volume global échangé)` |
| `Volume global (Mds FCFA)` | `Volume global échangé / 1e9` |
| `Volume nominal échangé` | `SUM(Volume nominal échangé)` |
| `Nb transactions` | `SUM(Nombre de transactions)` |
| `Nb lignes cotées` | `COUNTROWS('Marché secondaire')` |
| `Encours total` | `SUM(Encours)` |
| `Nb émissions à venir` / `Nb émissions total` | `COUNTROWS(Calendrier)` (filtré ou non sur `Statut = "À venir"`) |
| `Nb obligations cotées` | `COUNTROWS('BRVM Obligations')` |
| `Taux facial moyen (BRVM)` | `AVERAGE(Taux facial)` |

### 7.2 Pourquoi des moyennes pondérées par le volume ?

Une simple `AVERAGE()` donnerait le même poids à une transaction de 10 M FCFA
et à une transaction de 10 Md FCFA — non représentatif pour un gestionnaire de
portefeuille. Toutes les métriques obligataires agrégées sont donc **pondérées
par le volume nominal échangé** de chaque ligne :

```
Mesure pondérée = SUMX(Marché secondaire, Volume nominal échangé × X) / SUM(Volume nominal échangé)
```

avec `X` ∈ {`Rendement moyen`, `YTM`, `Duration modifiée`, `Duration Macaulay`,
`Convexité`, `Maturité résiduelle (années)`}, ce qui donne respectivement :
`Rendement moyen pondéré`, `YTM moyen pondéré`, `Duration modifiée moyenne`,
`Duration Macaulay moyenne`, `Convexité moyenne`, `Maturité résiduelle moyenne`.

Pour les 5 dernières (issues des calculs `finance.py`, potentiellement
manquantes en cas de rendement invalide), le calcul est enveloppé dans un
`FILTER(NOT ISBLANK(X))` pour exclure les lignes sans valeur du numérateur
**et** du dénominateur — sinon la pondération serait faussée par des volumes
associés à un `X` manquant.

### 7.3 Mesures de courbe et de spread

- **`Taux courbe de réf.`** : au **dernier point de date disponible**
  (`REMOVEFILTERS` sur la maturité pour ignorer le filtre de maturité et
  prendre la date la plus récente toutes maturités confondues), bascule entre
  le taux du pays sélectionné (`HASONEVALUE`) et la moyenne UEMOA sinon.
- **`Écart taux a/a (pb)`** : différence, en points de base, entre le
  `Taux courbe de réf.` de l'année sélectionnée (`Dates[Année]`) et celle de
  l'année précédente (`REMOVEFILTERS(Dates)` puis `Année = anc − 1`).
- **`Pente 1-3 ans réf.`**, **`Pente 5-7 ans réf.`**, **`Pente 7-10 ans réf.`**,
  **`Pente 2-10 ans réf.`** : différences de `Taux moyen UEMOA` entre deux
  maturités repères, prises au dernier point de courbe disponible, en points
  de base (`(t_long − t_court) × 10 000`).
- **`Pente 2-10 ans moyenne (pb)`** : `AVERAGE('Courbes pente'[Pente 2-10 ans (pb)])` — moyenne dans le temps de la pente pré-calculée en Python (§5.4), à distinguer des mesures « réf. » ci-dessus qui recalculent la pente en DAX au dernier point.
- **`Spread moyen vs UEMOA (pb)`** : `AVERAGE('Courbes de taux'[Spread vs moyenne (pb)])`.

---

## 8. Où trouver quoi (référence rapide)

| Je cherche… | Fichier | Fonction / section |
|---|---|---|
| Formules de duration/convexité/DV01 | `scripts/finance.py` | `metriques()` |
| Construction des flux obligataires | `scripts/finance.py` | `flux()`, `_temps_flux()` |
| Application aux transactions | `scripts/preparer_donnees_bi.py` | `preparer_marche_secondaire()` |
| Spreads et pentes de courbe (Python) | `scripts/preparer_donnees_bi.py` | `preparer_courbes()`, `preparer_courbes_pente()` |
| Extraction taux facial / catégorie BRVM | `scripts/preparer_donnees_bi.py` | `preparer_brvm()` |
| Moyennes pondérées, pentes « réf. », écarts a/a | `Reporting BI.SemanticModel/definition/tables/Mesures.tmdl` | toutes les mesures |
| Architecture générale du pipeline (scraping → BI) | `DOCUMENTATION.md` | §1, §5, §8, §10 bis |

---

## 9. Limites connues et points de vigilance

- Les OAT amortissables sont **approximées** (amortissement constant) faute de
  calendrier public exact — toujours vérifier la colonne `Méthode` avant
  d'interpréter une duration/convexité comme exacte.
- `Taux facial` et `Catégorie` (BRVM) sont extraits par **regex sur le nom** de
  l'obligation : un format de nom inhabituel peut laisser ces colonnes vides
  ou mal classées.
- Les métriques obligataires (`YTM`, duration, convexité, DV01, sensibilité)
  sont `NaN` si le rendement moyen est manquant ou incohérent
  (`y ≤ -0,999`) — ces lignes sont exclues des moyennes pondérées via
  `FILTER(NOT ISBLANK(...))`, pas remplacées par zéro.
- Les pentes et spreads supposent qu'un point de taux existe pour **chaque**
  maturité repère (2, 5, 10 ans, etc.) à la date considérée ; en son absence,
  la mesure renvoie un blanc plutôt qu'une valeur erronée.
