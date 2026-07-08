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

## 5. Ce que ça change au code (état & reste à faire)

- [x] Couche 2 déjà générique (16_tri_visuel ne connaît pas le produit).
- [x] Cœur solaire `solaire.py` écrit + testé (position du soleil, ombres portées MNS,
      heures annuelles) — voir `05-PIPELINE-TERRASSES.md`.
- [ ] `[OPUS]` Renommer `--source-piscines` → `--source` dans 20_join (rétro-compatible).
- [ ] `[OPUS]` 30_score : lire les seuils depuis `config[produit]` au lieu de `config["piscines"]`
      (une ligne de paramétrage `--produit piscines` par défaut).
- [ ] `[FABLE, quand P2 démarre]` `25_terrasses.py` : orchestration MNS par dalles autour de
      `solaire.py` (zones jardin sud des parcelles bâties, score d'ensoleillement, contrat couche 1).
