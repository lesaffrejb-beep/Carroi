# 18 — L'Atelier d'annotation (bench local multi-passes)

> Créé le 2026-07-16 (demande JB : « un seul HTML, un backend local, je farm »).
> Code : `pipeline/src/atelier.py`. Un serveur stdlib + une page. Zéro dépendance
> nouvelle, zéro cloud : les votes restent sur la machine.

## Lancer

```bash
cd maps-main
.venv/bin/python pipeline/src/atelier.py        # → http://localhost:8199
```

Options : `--port`, `--candidats <parquet>`, `--ortho-dir <dalles RVB>`.
Au premier lancement, la base de votes est amorcée avec les acquis (tri fusionné
+ dernière concordance) : on ne repart jamais de zéro.

## Le modèle : des votes, jamais des états

Chaque réponse est un **vote** `(produit, mode, id_item, reponse, trieur, ts)`
ajouté à `data/atelier/atelier.sqlite` (append-only, gitignoré comme tout
`data/`). Conséquences :

- **Passes illimitées** : la passe N s'ajoute à la passe N-1. La « vérité » d'un
  item = la **majorité** de ses votes ; sa solidité = **taux d'accord × nombre
  de votes**. C'est le schéma de toutes les plateformes de labellisation
  (agrément inter-annotateurs).
- **Correction ≠ nouvelle passe** : revenir en arrière (`←`/`Q`) et re-répondre
  **remplace son propre dernier vote** (erreur de clic), sans doublon.
- **File « moins vu d'abord »** : l'item servi est tiré au hasard parmi les
  moins votés → couverture uniforme, pas de biais d'ordre, pas d'ennui.

## Les niveaux

| Niveau | Question | Réponses | Débloqué par |
|---|---|---|---|
| 1 · Existence | piscine dans le contour rouge ? | `Q` oui · `D` non · `S` impossible à dire | — |
| 2 · Adresse | quelle maison ? | rangée de chiffres AZERTY · `A` aucune · `S` impossible | majorité de « oui » au niveau 1 |

Clavier main gauche (mapping JB, 2026-07-16) : `A`/`←` revenir, `E`/`→` avancer,
`ESPACE` passer **sans** voter (l'item reste dû), `O`/`N` restent en alias au
niveau 1. « Impossible à dire » est un **vote** : l'item ne revient plus cette
passe et n'est jamais vendu.

**Signalements (`F` puis clic)** : « je vois une piscine ailleurs dans l'image ».
Le clic est converti en point **Lambert-93** (via le centre et le côté du crop)
et stocké dans la table `signalements` — donnée de RAPPEL (détections manquées),
export `/api/export/signalements.csv`, à recouper avec cadastre SYM=65 / CoSIA.

**Rythme et pauses** : chrono de session (temps actif, coupé après 60 s
d'inactivité), rythme réel en votes/h calculé depuis les horodatages (mesure du
2026-07-16 : **~1 360 votes/h**, 2,6 s par vignette). Toutes les 100 réponses :
pause forcée de 3 s + dump automatique du consensus dans `data/atelier/exports/`
(le SQLite, lui, est écrit à chaque vote). Les items en désaccord (votes à
égalité) passent en tête de la passe suivante.

## Exports (compatibles chaîne existante)

- `/api/export/existence.csv` → `id_detection,decision,n_votes,accord,methode,statut,raison`
  (consommable par `16 --apply` après filtrage, et par `18_bilan_tri`).
- `/api/export/adresse.csv` → contrat de `concordance.csv` + `n_votes,accord,statut,raison`
  (consommable par `21_appliquer_concordance`).
- `/api/export/incertitudes.csv` → toutes les zones gelées, avec raison,
  changements d'avis max et votes bruts (le « à résoudre plus tard »).

Règle de gestion : **une décision multi-votes ne redescend dans le pipeline que
par ces exports consensus** — jamais en éditant les parquets à la main.

## Incertitudes : la règle des 3 signaux (décision JB 2026-08-06, `16` §8)

Doctrine commerciale : on ne vend que le quasi-100 % ; le reste est **classé**,
pas forcé. `classer_incertitude(votes, corrections_max)` gèle une zone dès
qu'UN signal se déclenche :

1. **desaccord** — votes à égalité, OU des réponses incompatibles coexistent
   avec un accord < 2/3 (`INCERTITUDE_ACCORD_MIN`) ;
2. **instable** — un même trieur a changé d'avis plus de 2 fois sur la même
   image (`INCERTITUDE_CHANGEMENTS_MAX` ; journal SQLite `corrections`,
   alimenté quand la navigation arrière REMPLACE un vote par une réponse
   différente) ;
3. **vote_incertain** — la majorité elle-même est incertain/indecis.

Effet dans TOUS les exports (y compris les dumps auto tous les 100 votes) :
`decision` forcée à `incertain`/`indecis` — même un vieux script aval ne peut
pas vendre une zone gelée. Les items contestés restent prioritaires dans la
file (une passe de plus peut les trancher) ; ce qui résiste attend le
multi-millésimes (tâche 23, roadmap) ou le terrain.

## Clic-piscine ↔ cadastre (mode 🧭 SITUER, décision JB 2026-08-06)

Le numéro BAN peut être affiché à un endroit bizarre du rectangle propriétaire,
mais le polygone cadastral, lui, est bon : la vraie question est « la piscine
est-elle dans la parcelle X ou Z », pas « où est la piscine dans le rectangle ».
En SITUER, cliquer sur la **piscine elle-même** (le fond de l'image, pas une
pastille) appelle `/api/parcelle_clic` : le serveur convertit le clic en
Lambert-93, trouve la parcelle cadastrale du point (`parcelle_au_point`), et
surligne (anneau lime + liseré dans la liste) les maisons candidates dont le
point BAN tombe dans CETTE parcelle. Le farmer reste juge : rien n'est voté à
sa place. Les signalements `F` (mode CLASSER) stockent aussi `id_parcelle` au
moment du clic.

## Extension aux produits suivants

Le schéma (existence → attribut) est générique : terrasses (existence de la
terrasse ensoleillée → adresse), parkings (idée produit 3, non chiffrée), etc.
Brancher un produit = fournir un parquet de candidats + des vignettes + la
constante `PRODUIT`.

## À quoi servent ces labels demain (IA maison)

Question JB du 2026-07-16 : « à terme on entraînera notre IA ? il faudrait
combien de samples ? » Ordres de grandeur état de l'art (fine-tuning d'un
backbone pré-entraîné, PAS d'entraînement from scratch) :

| Objectif | Architecture type | Labels nécessaires | Où on en est |
|---|---|---|---|
| **Classifieur de vignettes** « piscine O/N » (pré-tri des candidats d'un détecteur) | ResNet/EfficientNet fine-tuné, ou tête linéaire sur DINOv2 | **1 000–5 000 vignettes équilibrées** ; utilisable dès ~500/classe | **977 déjà faites** (246 oui / 731 non), chaque passe augmente la qualité des labels |
| **Détecteur/segmenteur** d'objets sur ortho (trouver les piscines soi-même) | YOLO fine-tuné ou SAM/U-Net | 1 000–3 000 **instances** délimitées (polygones) | Les polygones candidats validés « oui » = déjà des pseudo-masques ; CoSIA rend ce modèle NON prioritaire (décision `15` §4) |
| **Modèle multi-classes** piscine/terrasse/parking/panneau solaire | même base, une tête par classe | 1 000–5 000 par classe | à farmer produit par produit |

Doctrine :
1. **Des petits modèles par tâche**, pas un gros : un classifieur de vignettes
   par produit est entraînable sur un laptop (transfer learning), diagnostiquable,
   et remplaçable. Un « gros modèle » maison n'a aucun sens face à CoSIA (IGN)
   qui publie déjà la détection nationale en Licence Ouverte.
2. **La cible rentable** : le classifieur d'existence multi-classes qui pré-trie
   les candidats des futures communes (moins d'items à farmer par commune), pas
   le détecteur (CoSIA + cadastre SYM=65 couvrent déjà la détection piscines).
3. Le dataset se constitue AUTOMATIQUEMENT en farmant : `18_bilan_tri` joint
   déjà décisions × features géométriques (`tri_labels_*.parquet`) ; l'atelier
   y ajoute la dimension multi-votes (pondérer chaque label par son accord).
4. **Qualité avant volume** : 1 000 labels à 3 votes concordants battent 5 000
   labels à 1 vote. Les passes de l'atelier fabriquent exactement ça.

## Limites connues (v1)

- Mono-commune (Bouchemaine) : passer une autre commune = `--candidats` +
  vignettes générées par `16_tri_visuel` + ortho extraite (`12`).
- Zones denses au niveau 2 : jusqu'à ~80 pastilles dans le rayon de 150 m —
  la liste triée par distance reste le chemin rapide.
- Pas de multi-poste (SQLite local, un seul serveur) : suffisant pour JB + un
  invité sur la même machine ; passer à un vrai backend le jour où ça se partage.
