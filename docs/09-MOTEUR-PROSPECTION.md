# Le moteur de prospection — architecture multi-produits & portefeuille

> **Décision d'architecture (2026-07-08, session Fable).** Ce document étend `01-ARCHITECTURE.md`
> sans le contredire : le produit 1 (piscines) reste la priorité d'exécution. Mais le repo est
> désormais pensé comme un **moteur générique de prospection sur open data**, dont chaque produit
> n'est qu'un plugin de détection. C'est ce qui rend le business versatile (pivots bon marché)
> et scalable (nouveau produit = nouveau détecteur, pas un nouveau pipeline).

## 1. La thèse business (à garder en tête dans chaque décision)

On vend des **listes d'adresses qualifiées par un attribut physique du bien**, détecté par
traitement automatique d'open data géographique (BD ORTHO, LiDAR HD, cadastre, BAN, BD TOPO).
La barrière à l'entrée n'est pas technologique au sens noble : c'est un **travail de fourmi
que personne ne fait** — trop niche pour une startup, trop technique pour un commercial,
trop long à la main. L'IA de développement (ce repo) rend ce travail quasi gratuit à produire
et reproductible à volonté. Le fichier complet reste l'actif ; on vend des extraits
territorialisés, de l'exclusivité sectorielle, et de la fraîcheur (diffs de millésimes).

**Corollaire architectural : tout ce qui n'est pas le détecteur doit être écrit UNE fois.**
Un pivot produit ne doit coûter que : (a) un détecteur, (b) une page de doc, (c) des RDV.

## 2. L'architecture en couches (le contrat)

```
┌───────────────────────────────────────────────────────────────────────┐
│ COUCHE 1 — DÉTECTEURS (un par produit, la seule partie spécifique)    │
│   piscines   : detection.py + 15_detect (HSV+IRC sur BD ORTHO)  [fait]│
│   terrasses  : solaire.py + 25_terrasses (MNS LiDAR HD)    [cœur fait]│
│   parkings, toitures, … : futurs plugins                              │
│   CONTRAT DE SORTIE (invariant) : GeoDataFrame EPSG:2154              │
│     geometry (polygone), surface_m2, score_detection ∈ [0,1],         │
│     methode (str, traçabilité), + attributs propres au produit        │
│     → fichier data/interim/{produit}_candidates_{dept}.parquet        │
├───────────────────────────────────────────────────────────────────────┤
│ COUCHE 2 — VALIDATION HUMAINE (mutualisée)                            │
│   16_tri_visuel.py : planche HTML O/N/U + --apply.                    │
│   Déjà générique : il consomme le contrat de la couche 1 (geometry +  │
│   id_detection) et n'a AUCUNE connaissance du produit.                │
├───────────────────────────────────────────────────────────────────────┤
│ COUCHE 3 — ADRESSAGE (mutualisée)                                     │
│   20_join : polygone → parcelle → adresse BAN. Générique par nature   │
│   (un polygone est un polygone). Paramètre --source-piscines à        │
│   renommer --source à la prochaine retouche [OPUS].                   │
├───────────────────────────────────────────────────────────────────────┤
│ COUCHE 4 — QUALITÉ & SCORE (semi-mutualisée)                          │
│   30_score : les filtres (surface, dist bâtiment, exclusions BD TOPO, │
│   dédoublonnage id_ban, confiance) sont paramétrés par config.yaml ;  │
│   chaque produit = une section de seuils, même code.                  │
├───────────────────────────────────────────────────────────────────────┤
│ COUCHE 5 — COMMERCIALISATION (mutualisée, NE JAMAIS dupliquer)        │
│   35_stats (chiffre au téléphone), 40_export (opt-out + tatouage +    │
│   millésimes + registre), 41_carte (PDF de RDV). Les garde-fous       │
│   légaux (CLAUDE.md) vivent ici et dans common.py : un nouveau        │
│   produit en hérite automatiquement — c'est voulu et non négociable.  │
└───────────────────────────────────────────────────────────────────────┘
```

Règles d'or :
- **Un nouveau produit n'a le droit de toucher qu'à la couche 1** (+ sa section config + sa doc).
  S'il faut modifier les couches 2-5, c'est une évolution du moteur : la faire générique.
- Le tri humain (couche 2) est obligatoire pour tout produit dont la précision brute < 95 %.
- Les colonnes du contrat de sortie sont un invariant testé (`pipeline/tests/`) — les
  détecteurs futurs doivent passer les mêmes tests de contrat.

## 3. Portefeuille de produits (scoré, à réévaluer après chaque série de RDV)

Notation ✚✚ (fort) → ✖ (rédhibitoire). "Données" = disponibilité open data ; "Détection" =
difficulté technique restante ; "Marché" = densité d'acheteurs locaux solvables ; "Défendable" =
difficulté pour un concurrent de refaire.

| # | Produit | Acheteurs | Données | Détection | Marché | Défendable | Verdict |
|---|---|---|---|---|---|---|---|
| P1 | **Piscines** | pisciniers, abris, PAC, entretien | ✚✚ BD ORTHO | ✚✚ fait, à calibrer | ✚✚ dense 49 | ✚ | **EN COURS** |
| P2 | **Terrasses/pergolas** (ensoleillement) | pergolistes, storistes, vérandalistes | ✚✚ LiDAR HD MNS/MNT | ✚ cœur solaire fait | ✚✚ panier moyen élevé | ✚✚ personne ne le fait | **SUIVANT** (financé par P1) |
| P3 | **Potentiel solaire toiture** (pans sud, surface, sans ombrage) | installateurs PV | ✚✚ LiDAR HD + BD TOPO | ✚ réutilise `solaire.py` + pentes MNS | ✚✚ marché énorme | ✚ (cadastre solaire public existe par endroits — vérifier le 49) | pivot crédible n°1 |
| P4 | **Places de parking / imperméabilisation** | promoteurs, collectivités, BE | ✚ BD ORTHO | ± marquage au sol fin, détection dure | ± acheteur public = cycle lent | ✚ | veille — B2G, pas B2B rapide |
| P5 | **État/matériau de couverture** (toits à rénover) | couvreurs | ± ortho 20 cm limite | ✖ subjectif, risque sur-promesse | ✚✚ | ✚ | NON en l'état (précision invendable) |
| P6 | **Nouvelles piscines** (diff millésimes) | mêmes que P1 | ✚✚ | ✚✚ trivial une fois P1 fait | ✚✚ prospects chauds | ✚✚ | upsell P1, pas un produit séparé |
| P7 | Haies/clôtures, portails, abris de jardin… | paysagistes, clôturistes | ✚ | ± | ± | ± | backlog, ne pas y penser avant P2 |

**Le multiplicateur caché : P2 et P3 partagent le même cœur (`solaire.py`).** Heures de soleil
sur un plan quelconque (terrasse au sol OU pan de toiture), masque d'ombrage par le MNS —
un seul investissement algorithmique, deux produits.

## 4. Critères de pivot (décidés à froid, pour ne pas décider à chaud)

- **Go/No-Go P1** : après **10 RDV pisciniers** menés selon `07-VENTE-PLAYBOOK.md` —
  < 2 ventes OU prix accepté < 300 € l'extrait ⇒ on pivote (P2 si un pergoliste a mordu en
  RDV exploratoire, sinon P3). On ne "retravaille" pas la base P1 plus de 5 jours après ce constat.
- **Un pivot n'est jamais un abandon d'actif** : la base P1 reste vendable en fond de
  catalogue ; le moteur (couches 2-5) sert le produit suivant tel quel.
- **Jamais deux détecteurs en développement en même temps.** Un produit se valide (RDV,
  chiffres consignés dans `08-ROADMAP.md`) avant qu'on code le suivant.
- Les garde-fous de `CLAUDE.md` (pas de données nominatives, open data seulement, précision
  mesurée, opt-out) s'appliquent à TOUT produit du portefeuille, sans exception — c'est le
  moteur qui les impose, pas la bonne volonté.

## 5. Différenciation défendable (arbitrage 2026-07-08)

Lucidité d'abord : **le code n'est PAS le moat.** Un dev assisté par LLM reproduit ce repo
en quelques semaines ; l'open data est public ; l'idée de détecter les piscines est publique
depuis le « foncier innovant » du fisc. Si on gagne, ce n'est pas par secret technique.
Les vrais moats, par ordre de priorité d'exécution :

1. **Verrouillage contractuel du marché local — le moat n°1, à exécuter AVANT tout le reste.**
   Le marché est étroit : ~30 pisciniers autour d'Angers. Une fois 5-10 exclusivités signées
   (par secteur d'activité × zone × 12 mois, tacite reconduction), un copieur arrive sur un
   marché déjà fermé : il a le fichier mais plus d'acheteurs. Conséquence tarifaire assumée :
   accepter un rabais sur les premières exclusivités vaut mieux que vendre cher du non-exclusif.
2. **L'actif temporel irrécupérable.** Deux choses qu'un retardataire ne peut PAS reconstruire :
   (a) la **vérité terrain accumulée** — décisions de tri humain, retours clients « cette adresse
   n'a pas de piscine », seuils calibrés par territoire. C'est un dataset étiqueté qui s'améliore
   à chaque vente et qui financera l'option A (modèle entraîné) le moment venu ; le formaliser :
   chaque réclamation client entre dans `data/validation/` comme étiquette négative.
   (b) le **point zéro des millésimes** — le produit « nouvelles piscines » (le plus cher au
   prospect le plus chaud) exige une base t₀ ; un entrant tardif attend un cycle BD ORTHO
   complet (~3 ans) pour son premier diff.
3. **La vitesse de réplication.** Le moteur (couches 2-5) + le playbook rendent un nouveau
   département ≈ mécanique. Pendant qu'un copieur valide son 49, on ouvre 44, 85, 72.
4. **Le produit composite.** Chaque nouveau détecteur enrichit les MÊMES adresses (piscine +
   ensoleillement + toiture) : la valeur du fichier croît en produit cartésien, un copieur
   mono-produit ne suit pas. C'est l'argument économique profond de l'architecture en couches.

Anti-moat assumé : si un acteur installé (opérateur d'annuaires, courtier en données) décidait
de le faire, il gagnerait — mais le marché est trop niche pour justifier son coût d'opportunité.
Le concurrent réaliste est un autre solo outillé d'IA : contre lui, les moats 1 et 2 suffisent
**à condition d'être rapide**. La lenteur est le seul vrai concurrent.

## 6. Ce que ça change au code (état & reste à faire)

- [x] Couche 2 déjà générique (16_tri_visuel ne connaît pas le produit).
- [x] Cœur solaire `solaire.py` écrit + testé (position du soleil, ombres portées MNS,
      heures annuelles) — voir `05-PIPELINE-TERRASSES.md`.
- [ ] `[OPUS]` Renommer `--source-piscines` → `--source` dans 20_join (rétro-compatible).
- [ ] `[OPUS]` 30_score : lire les seuils depuis `config[produit]` au lieu de `config["piscines"]`
      (une ligne de paramétrage `--produit piscines` par défaut).
- [ ] `[FABLE, quand P2 démarre]` `25_terrasses.py` : orchestration MNS par dalles autour de
      `solaire.py` (zones jardin sud des parcelles bâties, score d'ensoleillement, contrat couche 1).
