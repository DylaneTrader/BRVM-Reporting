# Configuration Power BI — accès aux données

Le rapport lit les fichiers `data/_bi/*.csv` **depuis GitHub** (fonction `GitHubFichier`
dans le modèle sémantique). Le paramètre `GitHubToken` a été **vidé du dépôt** : il ne doit
jamais y être commité. Ce document explique comment le renseigner pour que le rapport
continue de fonctionner, et comment, à terme, s'en passer complètement.

---

## 0. À faire — hygiène des jetons

**Bonne nouvelle vérifiée :** aucun token n'a **jamais été commité** dans le dépôt
(recherche `git log --all -S "github_pat_"` : vide). La valeur qui figurait dans
`expressions.tmdl` était une saisie **locale non commitée** ; la version versionnée a
toujours été `GitHubToken = ""`. Il n'y a donc **pas d'exposition via l'historique GitHub**
et rien à purger côté historique.

Deux jetons restent néanmoins connus en clair côté poste (ils ont été affichés). Par
simple hygiène — surtout si le poste ou un `.pbix` a pu être partagé — il est recommandé
de les **faire tourner** :

1. GitHub → *Settings → Developer settings → Fine-grained tokens* → révoquer / régénérer :
   - le token utilisé localement pour `GitHubToken` ;
   - le token embarqué dans l'URL du remote `origin` (voir `git remote -v`).
2. Nouveau PAT recommandé : portée minimale **Contents = Read-only**, limité au seul dépôt
   `Scraper-UMOA-Titres`, avec **date d'expiration** (ex. 90 jours).
3. Nettoyer l'URL du remote pour ne plus y stocker de token :
   ```bash
   git remote set-url origin https://github.com/DylaneTrader/Scraper-UMOA-Titres.git
   ```
   (l'authentification passera par le gestionnaire d'identifiants Windows / GitHub CLI).

> Ce n'est pas une urgence (rien n'a fuité dans le dépôt), mais la rotation reste la
> bonne pratique dès qu'une valeur de secret a été visible en clair.

---

## 1. Qui a besoin du token ?

| Acteur | A besoin du token ? |
|---|---|
| **Lecteurs** du rapport publié (Service / app) | ❌ Non — ils voient les données du dernier rafraîchissement |
| **Propriétaire** du dataset (rafraîchissement) | ✅ Oui — le token sert uniquement à recharger les CSV |

Le token n'est donc **jamais visible par les utilisateurs finaux** : il reste côté dataset,
utilisé seulement lors des actualisations.

---

## 2. Power BI Desktop (édition locale)

1. Ruban **Accueil → Transformer les données → Modifier les paramètres**
   (ou *Gérer les paramètres*).
2. Renseigner `GitHubToken` avec le **nouveau** PAT.
3. Première actualisation : si Power BI demande des identifiants pour `api.github.com`,
   choisir **Anonyme** (le token voyage dans l'en-tête `Authorization`, pas dans les
   identifiants de la source).
4. **Ne jamais** committer le `.tmdl` avec le token renseigné — le laisser vide avant
   tout `git commit` (le fichier versionné doit rester `GitHubToken = ""`).

---

## 3. Power BI Service (rapport déjà publié)

Pour que l'actualisation planifiée continue de fonctionner après publication :

1. **app.powerbi.com** → votre espace de travail → le **dataset** (jeu de données) →
   menu **⋯ → Paramètres**.
2. Section **Paramètres** : coller le nouveau PAT dans `GitHubToken` → **Appliquer**.
3. Section **Informations d'identification de la source de données** :
   pour la source `https://api.github.com`, cliquer **Modifier**, méthode
   d'authentification **Anonyme**, niveau de confidentialité **Organisation** (ou *Public*),
   puis **Se connecter**.
4. Section **Actualisation planifiée** : activer, définir la fréquence (ex. tous les jours
   ouvrés après 18h30 UTC, une fois le scraping GitHub Actions terminé).

> `api.github.com` est une source cloud publique → **aucune passerelle (gateway) n'est
> nécessaire**. Le token étant stocké dans le paramètre du dataset (côté serveur, chiffré),
> il faudra le remettre à jour ici à chaque rotation / expiration du PAT.

---

## 4. Option « grand public » — se passer totalement du token

La donnée servie (`data/_bi/*.csv`) provient de sources **publiques** (UMOA-Titres, BRVM).
Rien n'oblige à la lire depuis un dépôt privé. Pour supprimer le secret **et** garder le
dépôt de code privé, on **découple la donnée** vers un point public :

**Recommandé — un dépôt GitHub public dédié à la donnée :**

1. Créer un dépôt public, ex. `umoa-titres-data`, ne contenant que `data/_bi/`.
2. Dans le workflow GitHub Actions, après le scraping, pousser les CSV vers ce dépôt public
   (ou publier via **GitHub Pages**).
3. Dans le modèle Power BI, remplacer `GitHubFichier(...)` par une simple lecture d'URL
   publique, **sans token** :
   ```m
   Source = Csv.Document(
       Web.Contents("https://raw.githubusercontent.com/<user>/umoa-titres-data/main/data/_bi/" & nomFichier),
       [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv])
   ```
4. Supprimer le paramètre `GitHubToken` et la fonction `GitHubFichier`.

Résultat : **plus aucun secret** dans le rapport, actualisation sans identifiants, et le
dépôt `Scraper-UMOA-Titres` (scripts) **reste privé**. Seuls les CSV — déjà publics à la
source — deviennent accessibles.

**Alternatives équivalentes :** un *Gist* public, ou un bucket de stockage statique
(Azure Blob « public read », S3, etc.). Le principe est le même : point de lecture public,
zéro credential.

---

## Récapitulatif de sécurité

| Niveau | Mécanisme | Effort | Secret exposé aux lecteurs |
|---|---|---|---|
| Actuel (dépôt privé + PAT) | Token dans le paramètre du dataset | Rotation du PAT à gérer | Non |
| **Cible « grand public »** | Données sur endpoint public, code privé | Nul après mise en place | Aucun (plus de secret) |
