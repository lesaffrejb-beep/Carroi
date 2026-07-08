# Cibles du moteur — qui a besoin de nous, arbitrage, et terrain préparé

> **Méthode (2026-07-08)** : on part de ce que le moteur sait VOIR (ortho 20 cm RVB+IRC,
> LiDAR MNS/MNT/MNH, cadastre, BAN, BD TOPO, + SITADEL/DVF/PLU en vecteur), on en déduit
> les attributs détectables, et pour chaque attribut : qui paie pour cette liste.
> Complète `09` (portefeuille produits) et `12` §3 (options gros ticket) — ce doc est
> le recensement large ; l'arbitrage est en §3.

## 1. Le recensement : attribut détectable → qui paie

### Sur orthophoto (le détecteur spectral `detection.py` re-paramétré)

| Attribut détecté | Acheteurs | Remarque |
|---|---|---|
| Piscine (fait — P1) | pisciniers, abris, PAC, alarmes, entretien | en cours |
| Piscine **hors-sol** vs enterrée (forme/teinte) | vendeurs d'enterrées (« upgrade »), abris | attribut bonus de P1, gratuit |
| Piscine bâchée/verte (à l'abandon) | rénovateurs de piscines | diff de teinte, même chaîne |
| Court de tennis privé | rénovation de courts, clôturistes | fenêtre HSV orange/vert, ~30 min de config |
| Panneaux PV **déjà posés** | mainteneurs/nettoyeurs PV ; et en creux : les toits SANS PV pour les installateurs | teinte sombre + forme rectangulaire sur toit |
| Terrasse minérale existante | pergolistes (bonus P2) | prévu docs/05 phase 2b |
| Gazon synthétique / jardin minéralisé | paysagistes | niche |

### Sur LiDAR (le moteur `solaire.py` + MNH)

| Attribut | Acheteurs | Remarque |
|---|---|---|
| Terrasse/jardin ensoleillé (fait — P2) | pergolistes, storistes, vérandalistes | prêt |
| Toiture : pans, orientation, surface, ombrage (P3) | installateurs PV résidentiels | réutilise solaire.py |
| **Grandes toitures plates non équipées** (agricoles, industrielles, commerciales) | développeurs PV tiers-investisseurs | tickets 10-100× le résidentiel |
| **Parkings extérieurs > 1 500 m² sans ombrières** | développeurs d'ombrières PV, énergéticiens | ⭐ voir §2 — obligation légale |
| Arbres hauts surplombant bâti | élagueurs, (assureurs : gelé, cf. `12`) | MNH > seuil à < x m du bâti |
| Haies/linéaires de clôture longs | clôturistes, élagueurs | MNH linéaire en limite de parcelle |

### En vecteur pur (cadastre + PLU + bâti — AUCUN raster, détecteur le moins cher)

| Attribut | Acheteurs | Remarque |
|---|---|---|
| **Parcelle divisible / fond de jardin constructible** (grande parcelle, petite emprise bâtie, poche libre d'un seul tenant, accès voirie, zone U du PLU) | promoteurs, aménageurs, agences immo, géomètres, particuliers via agents | ⭐ voir §2 — « KelFoncier du pauvre », données 100 % ouvertes (Géoportail de l'urbanisme) |
| Jardin grand + sud + SANS piscine | pisciniers (prospection « piscine potentielle ») | l'inverse de P1 — même client, second fichier |
| Maison individuelle grande parcelle sans terrasse détectée | pergolistes/paysagistes | croisement P2 inversé |

### Qui pourrait vouloir le MOTEUR lui-même (pas des fichiers)
Réseaux/franchises nationaux (déjà `12` §3), plateformes de leads travaux, éditeurs SaaS
pour artisans, agences de marketing local en marque blanche. **Phase 1 : on vend la donnée,
pas le moteur** (décision `00` : pas de SaaS) — mais chaque fichier vendu est une démo du moteur.

## 2. L'arbitrage : le top 3, et pourquoi

**⭐ n°1 — Parkings sans ombrières (loi APER).** La loi du 10 mars 2023 (art. 40) impose
des ombrières photovoltaïques sur ~la moitié des parkings extérieurs existants de plus de
1 500 m², avec échéances 2026-2028 et sanctions. C'est le seul produit du portefeuille où
l'acheteur (développeurs PV, énergéticiens, foncières) a une **obligation légale d'agir avec
un calendrier** — le budget n'est pas à créer, il est forcé. Le fichier : parkings > 1 500 m²
non équipés, avec surface exploitable d'un seul tenant, département par département, France
entière possible. Tickets attendus 5-50 k€ (un seul site gagné vaut des centaines de k€ au
développeur). Faisabilité : parkings dans BD TOPO (couche à confirmer — deepsearch ⑧),
absence d'ombrière/arbres via MNH, **surface exploitable = le cœur dur, préparé en §4**.

**n°2 — Gisements fonciers divisibles.** Détecteur 100 % vectoriel (le moins cher à
construire), données ouvertes (cadastre + zonage PLU du Géoportail de l'urbanisme),
acheteurs solvables et habitués à payer la donnée (KelFoncier facture des milliers d'euros/an ;
un « extrait local à 500-2 000 € » est un positionnement vide). Réutilise le MÊME cœur
géométrique que le n°1 (poche libre maximale, §4).

**n°3 — Grandes toitures non équipées** (agricole/industriel/commercial). Même acheteur que
le n°1, même moteur que P3. Se vend en bundle avec le n°1 (« le fichier des sites PV du 49 »).

Pourquoi pas les autres en premier : les cibles B2C-artisans (élagueurs, clôturistes) ont le
même problème de panier que les pisciniers (cf. pre-mortem `10` §2) ; les attributs bonus de
P1/P2 s'activent gratuitement quand P1/P2 vendent. Le trio 1-2-3 vise des acheteurs
**professionnels de la donnée**, à ticket 10-100×, sans changer une ligne des couches 2-5.

**Séquence** : rien ne double D0-pisciniers (en cours, spend nul). Si l'arbre `12` branche
B2/C1 (prix bloqué ou « sans téléphone sans valeur »), le trio ci-dessus devient la cible
des 5 appels suivants — développeurs PV régionaux et promoteurs, pas artisans.

## 3. Garde-fous spécifiques à ces cibles

- Parkings/toitures pro : données de BIENS commerciaux — pas de données personnelles en jeu
  pour les parkings de zones commerciales, MAIS les parcelles divisibles restent des adresses
  de particuliers → tout le cadre `03` s'applique au n°2, à l'identique de P1.
- Ne JAMAIS vendre « conforme/non conforme à la loi APER » (qualification juridique = risque) :
  vendre des FAITS mesurés — surface, absence de couverture, géométrie. L'acheteur qualifie.

## 4. Terrain préparé : le cœur géométrique commun (fait, testé)

Les n°1 et n°2 partagent le même problème algorithmique dur : **« quelle est la plus grande
poche rectangulaire libre d'un seul tenant dans cette emprise, en évitant les obstacles ? »**
(rangées d'ombrières sur un parking ; maison constructible dans un fond de jardin).
C'est `pipeline/src/geometrie.py` : `plus_grand_rectangle_libre()` — rectangle inscrit
maximal à orientation libre (rastérisation + histogramme O(n²) + balayage d'orientations),
et `poche_libre()` (emprise − obstacles → surface libre + rectangle max + son orientation).
Testé sur formes en L, obstacles centraux, rotations (`pipeline/tests/test_geometrie.py`).
Un détecteur n°1 ou n°2 = ce module + les couches existantes + une config.

## 5. Ce qui manque pour activer (tout est cadré, rien n'est commencé)

- Deepsearch ⑧ (ajoutée à `13`) : loi APER — seuils/échéances exacts 2026, et la couche
  BD TOPO des parkings ; Géoportail de l'urbanisme — téléchargement du zonage PLU 49.
- `[OPUS, sur déclencheur de l'arbre 12]` : extracteur parkings BD TOPO + croisement MNH
  (assemblage de briques existantes, spec §2) ; extracteur parcelles divisibles (vecteur pur).
- `[HUMAIN]` : 5 appels D0 « développeurs PV » si la branche s'active — le kit `11` s'adapte
  (même structure, pitch « sites », prix ×10).
