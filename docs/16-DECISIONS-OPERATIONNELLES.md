# Décisions opérationnelles — l'audit des mystères, tout est tranché

> **2026-07-08.** Audit systématique de toutes les questions restées sans réponse
> (livrable concret, stockage, flux de données, tarifs, recoupement, société, outillage).
> Chaque décision est TRANCHÉE ici avec son pourquoi. Une décision se change en la
> réécrivant ici avec la raison du changement — pas en la contournant en silence.
> Marquage : ✅ décidé et actionnable · 🧑 l'humain doit valider/agir · 🔧 tâche [OPUS] créée.

---

## 1. Le livrable client — qu'est-ce qu'on met dans les mains du piscinier ?

**✅ Décision : un dossier ZIP par livraison, cinq fichiers, pas d'app, pas de portail.**

| Fichier | Contenu | Pourquoi |
|---|---|---|
| `piscines_<zone>.xlsx` | LE fichier de travail du client : une ligne par adresse, colonnes lisibles (adresse, CP, commune, surface piscine, confiance, lat/lon), figées + filtres actifs | Un artisan vit dans Excel. Le CSV le perd (séparateurs, accents). 🔧 tâche [OPUS] : export XLSX via openpyxl dans 40_export |
| `piscines_<zone>.csv` | Le même en CSV UTF-8 BOM | Pour son logiciel métier / son routeur postal |
| `carte_<zone>.pdf` | Carte A4 des points sur fond de plan + compteur par commune | La preuve visuelle qui reste sur son bureau (D2, déjà spécifiée) |
| `README_LIVRAISON.txt` | Millésimes, précision mesurée (borne basse Wilson), licence d'usage, politique de remplacement 90 j | Déjà généré par 40_export |
| `notice_art14.txt` | La notice RGPD à joindre à ses courriers | Obligation + argument (« je vous mets en conformité ») |

**Pourquoi pas de front/back/portail** : décision `00` maintenue (pas de SaaS phase 1).
Un portail ne vend pas mieux, il coûte du temps de dev et crée une surface d'attaque
(la base fuite si le portail fuite). L'« interface » du client, c'est Excel + le PDF.
Réévaluation : uniquement si ≥ 10 clients récurrents demandent la même chose.

**Livraison** : lien de téléchargement à durée limitée (Swiss Transfer/équivalent) OU clé
USB remise en main propre au premier RDV (l'occasion d'un second contact). Jamais de
pièce jointe email non chiffrée pour un département entier.

## 2. Stockage & infra — où vivent les giga, qu'est-ce qui est sur le repo ?

**✅ Décision : tout tourne sur TA machine ; le repo ne contient QUE code+docs+config ;
les données vivent dans `data/` (gitignoré) ; sauvegarde 3-2-1 allégée.**

| Quoi | Où | Taille attendue | Sur le repo ? |
|---|---|---|---|
| Code, docs, config, tests | GitHub (ce repo) | < 5 Mo | ✅ oui |
| Dalles brutes BD ORTHO/LiDAR | `data/raw/` sur ton disque | 30-80 Go/dept | ❌ jamais (retéléchargeable, ne se sauvegarde même pas) |
| Couches dérivées (parquet) | `data/interim/` | 1-3 Go | ❌ jamais |
| **La base qualifiée (L'ACTIF)** | `data/final/` | < 100 Mo | ❌ JAMAIS (c'est ce qu'on vend) |
| Exports clients | `data/exports/` | < 10 Mo/client | ❌ jamais |
| Registre des ventes, prospects, opt-out | `sales/`, `data/optout/` | négligeable | ❌ jamais (données clients/personnelles) |

- **Machine** : ton ordinateur suffit pour 1-3 départements (tout le pipeline est
  fenêtré/indexé pour ça). Si le disque est court : un SSD externe 1 To (~60 € une fois)
  pour `data/raw/`. Pas de VPS/cloud tant qu'on n'a pas 5+ départements actifs — le
  cloud n'apporte que du coût et un risque de fuite de l'actif.
- **Sauvegarde (l'actif + les registres, PAS le raw)** : copie chiffrée hebdomadaire de
  `data/final/`, `data/exports/`, `sales/`, `data/optout/`, `data/validation/` sur
  (1) le SSD externe et (2) un stockage distant chiffré (Hetzner Storage Box ~4 €/mois
  ou équivalent). 🔧 tâche [OPUS] : script `90_backup.py` (tar + age/gpg + rclone), 30 lignes.
- **Pourquoi pas de base de données (PostGIS…)** : parquet + geopandas couvre nos volumes
  (< 100 k lignes finales/dept) sans serveur à administrer. PostGIS le jour où un produit
  exige des requêtes concurrentes — pas avant.

## 3. Flux des dossiers — qui entre où, qui sort d'où

**✅ Décision : le flux est linéaire et chaque script n'écrit QUE dans son étage.**

```
ENTRÉES (téléchargées)              data/raw/          ← 10_download, dalles ortho/LiDAR (manuel ou script)
    │  10_download (cadastre, BAN, BD TOPO → parquet + millesimes.yaml)
    ▼
DÉRIVÉS INTERNES                    data/interim/      ← 15_detect (candidats), 16_tri (tri/ + detectees),
    │                                                    20_join (adressées), 25_terrasses, 45_diff
    ▼  30_score (filtres qualité + confiance)
L'ACTIF                             data/final/        ← {produit}_qualifiees_{dept}.parquet
    │                                                    + archive/ : copie datée à chaque re-génération
    ▼  40_export (opt-out + tatouage + registre) — SEUL autorisé à produire du client
LIVRAISONS                          data/exports/{acheteur}_{date}/
HORS FLUX : data/optout/ (entrée permanente du filtre), data/validation/ (échantillons C1,
réclamations = étiquettes négatives), sales/ (registre, prospection, prospects).
```

🔧 tâche [OPUS] : 30_score archive une copie datée `data/final/archive/{produit}_{dept}_{date}.parquet`
à chaque écriture (c'est le point-zéro des millésimes, moat n°2 — aujourd'hui on écraserait).

## 4. Tarifs — grille v1, packs, et comment devenir indispensable

**✅ Décision : grille d'ancrage v1 ci-dessous, à réviser UNIQUEMENT avec les chiffres
D0/RDV consignés (`11` §6). Logique : les brokers louent l'adresse nominative ~0,15-0,30 €
l'unité en usage unique ; nous on vend la PROPRIÉTÉ d'un fichier local vérifiable + de la
récurrence de fraîcheur. On ne se bat pas sur le prix unitaire, on vend le stock + le flux.**

| Offre | Prix v1 | Justification |
|---|---|---|
| **Pack Lancement** (3 premiers clients, contre témoignage + droit d'instrumenter la campagne) | 490 € l'extrait 30 km | crée les références et le case study chiffré (`10` §2.3) |
| Extrait 30 km, non exclusif, achat définitif | 690–990 € selon volume | ~2 000-4 000 adresses ; sous le mailing qu'il paiera de toute façon ; ancrage sous 1 000 € = signature gérant sans réflexion longue |
| Département complet non exclusif | 2 490 € | ×3 l'extrait, pour les acteurs multi-agences |
| **Exclusivité** zone × métier, 12 mois | ×3 le non-exclusif (jamais < ×2,5) | le moat n°1 ; inclut la veille fraîcheur ci-dessous |
| **Veille « nouvelles piscines »** (le produit indispensable) | 39-59 €/mois par zone | livraison mensuelle des nouveautés (SITADEL) + diff au millésime (45_diff) ; c'est l'abonnement qui rend UNIQUE : le broker national ne sait pas faire local-frais ; churn faible car petit prix récurrent |
| Campagne clé en main (option, branche B1 de `12`) | fichier + coût routeur +30 % | transforme la donnée en résultat ; à tester en D0 |
| Cibles pro (`14` : ombrières, foncier, toitures) | 2 500–15 000 € le fichier départemental | acheteurs = pros de la donnée, obligation APER ; prix à valider par 5 appels dédiés |

**Le chemin « indispensable »** (dans l'ordre) : 1 vente sèche → veille mensuelle (il pense
à nous chaque mois) → campagne clé en main (on tient son acquisition) → exclusivité
renouvelée (il ne peut plus nous quitter sans nous laisser au concurrent). Le pain réel du
client n'est pas « avoir des adresses », c'est **remplir le carnet du printemps sans y
passer ses soirées** : chaque offre doit se formuler contre CE pain.

**✅ Ton budget de fonctionnement (plafond déclaré : 130 €/mois) — tenu :**

| Poste | €/mois |
|---|---|
| Abonnement LLM (les sessions Opus/Fable qui font tourner l'usine) | ~90-100 |
| Stockage distant chiffré (backup) | ~4 |
| Domaine + email pro (dont opposition@ — C4) | ~3 |
| Marge (Swiss Transfer pro éventuel, impression PDF démo) | ~10 |
| **Total** | **~110-120 €** |

Le routeur postal (clé en main) se facture au client, jamais sur ton budget. RC pro
(~200-300 €/an, 🧑 recommandée avant la première livraison) à ajouter au lancement.

## 5. Recoupement d'informations — décision de doctrine

**✅ Décision : le recoupement AUGMENTE la confiance, jamais il ne crée une ligne.**
La détection ortho reste LA source de vérité (vérifiable en RDV). Les recoupements :

| Source de recoupement | Usage décidé | Interdit |
|---|---|---|
| SITADEL (permis piscine) | corrobore une détection (`confiance` ↑) + alimente la veille « nouvelles » entre millésimes | créer une adresse vendue sur le SEUL permis (pas vérifiable sur photo → casse le protocole de preuve) |
| Diff de millésimes (45) | statut nouveau/conservé = attribut premium | vendre les « disparues » |
| PCI/cadastre bâti | corroboration faible (piscines parfois en « détails topo ») | source principale (incohérent par commune, cf. `02`) |
| **OSM** | UNIQUEMENT mesure de rappel interne (jamais publié) | tout attribut livré influencé par OSM — l'ODbL contaminerait le produit ; on tranche : même pas pour le score de confiance |
| Réclamations clients | étiquettes négatives (`data/validation/`) → recalibration | ignorer une réclamation |

🔧 tâche [OPUS] (après deepsearch ③) : colonne `corroboration` (sitadel/millesime/aucune)
dans 30_score, bonus de confiance si corroboré. Spec ci-dessus, ne pas improviser au-delà.

**Amendement du 2026-07-12 (arbitrage Fable, décision B4 — voir `08` journal) : PCI
SYM=65 est promu de « corroboration » à « source de candidats », SANS toucher au
principe.** Ce que l'autopsie du rappel a montré (Bouchemaine) : 80 % des piscines
manquées par la détection sont **couvertes/vides sur l'ortho 2022** — aucun réglage ni
modèle ne les verra comme de l'eau, mais 46/103 sont déjà des polygones SYM=65. Le
principe « une ligne vendue = validée par un humain sur photo » est INTACT : un candidat
`origine='cadastre'` entre dans le MÊME tri visuel, et n'est vendable que si le trieur
voit une piscine OU une couverture/abri de piscine manifeste sur la vignette (une bâche
d'hivernage SE VOIT — c'est vérifiable en RDV, contrairement à un permis SITADEL).
Ce qui reste interdit : vendre une ligne cadastre non validée sur photo ; la ligne du
tableau ci-dessus « source principale » reste vraie (couverture SYM=65 incohérente par
commune → le cadastre COMPLÈTE la détection, il ne la remplace pas). Spec d'exécution :
tâche 12 de `08`, post-D0. Effet mesuré : rappel 54,9 % → 76,6 % potentiel.

## 6. Les décisions connexes restantes — tranchées une par une

1. **Forme juridique** 🧑 : micro-entreprise (BNC) au lancement — zéro coût fixe, suffisant
   jusqu'à 77 700 € de CA services ; bascule en société si les exclusivités + cibles pro
   dépassent ~40 k€/an (TVA, crédibilité grands comptes). À valider avec l'avocat de C3
   (même rendez-vous, une question de plus, zéro coût marginal).
2. **Nom commercial** 🧑 : il faut un nom neutre multi-produits (pas « piscines-quelque-
   chose » : on vendra du foncier et des toitures). Proposition à trancher par l'humain,
   critère : un nom de DONNÉES locales sérieux en RDV pisciniers ET crédible face à un
   développeur PV. Le domaine + email opposition@<domaine> (C4) en découlent — décider
   AVANT les drafts légaux C2 (le nom figure dans la politique de confidentialité).
3. **Facturation** ✅ : paiement virement à livraison (pas d'acompte au lancement — friction
   inutile pour 690 €), facture micro-entreprise standard, mention licence d'usage au dos.
   L'exclusivité, elle, se paie 50 % à la signature (elle gèle une zone).
4. **CRM** ✅ : PAS de CRM SaaS. `sales/prospection_d0.csv` + `sales/prospects_49.csv` +
   `sales/registre.csv` suffisent en dessous de 50 clients. Un CRM = du temps de config
   pour ranger 30 lignes.
5. **Conservation des données (RGPD)** ✅ : base commercialisée = conservée tant qu'elle
   est au catalogue (millésime le plus récent + archives de millésimes = l'actif diff) ;
   exports clients + registre = 5 ans (preuve contractuelle) ; opt-out = permanent par
   nature ; à écrire tel quel dans la LIA (C2).
6. **Qui exécute le pipeline** ✅ : les sessions LLM (Opus) via ce repo, sur ta machine ou
   en session distante — jamais de service qui tourne en continu (rien à maintenir, rien
   qui fuit). Le « backend », c'est le repo + tes disques. Le « front », c'est le PDF.
7. **Suivi des versions de l'actif** ✅ : chaque `data/final/` re-généré = copie datée en
   archive (cf. §3) + ligne dans le journal `08` avec le `git describe` du pipeline.
8. **Téléphone/identité de prospection** 🧑 : un numéro dédié (eSIM/second numéro, ~5 €/mois
   éventuels dans la marge budget) — le jour où le Q&A presse sert, ton numéro perso n'est
   pas dans la nature.

## 7. Ce que cet audit ajoute au backlog [OPUS]

Repris dans `08-ROADMAP.md` (file d'attente) : export XLSX dans 40 ; archive datée dans
30 ; script backup 90 ; colonne corroboration (après deepsearch ③). Chacune cadrée là-bas.
