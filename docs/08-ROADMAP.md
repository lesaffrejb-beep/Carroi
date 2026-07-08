# Roadmap & journal de bord

> **Ce fichier est le journal du projet.** Chaque session LLM qui termine une tâche met à jour le statut, la date, et surtout ce qui a été **appris/mesuré** (les chiffres réels valent plus que le plan). La session suivante ne sait que ce qui est écrit ici.

## ⚡ PROCHAINE SESSION : COMMENCER ICI (état au 2026-07-08, fin des sessions Fable)

**Où on en est en une phrase** : tout le moteur est codé et testé (45 tests verts — détection
piscines 1b complète, tri humain, moteur solaire, détecteur terrasses P2, export avec --demo) ;
AUCUNE donnée réelle n'a encore été traitée, AUCUN document légal rédigé, AUCUN prospect appelé
— et le pre-mortem (`10`) a établi que c'est LE risque n°1. La priorité absolue n'est plus le code.

**File d'attente — chaque tâche est autonome et cadrée ; une session Opus prend LA PREMIÈRE
non cochée de son niveau, la fait EN ENTIER, consigne, et s'arrête. Ne pas improviser au-delà
du cadre ; si quelque chose bloque ou surprend, le consigner ici et s'arrêter proprement.**

1. `[HUMAIN — en cours, RDV imminents]` **D0** : appels de pré-vente avec le kit `11`,
   réponses dans `sales/prospection_d0.csv`, puis dérouler l'arbre `12`.

2. `[OPUS — sans dépendance, faisable maintenant]` **C2 : drafts légaux.**
   Livrables : `docs/legal/LIA.md`, `docs/legal/AIPD.md`, `docs/legal/registre_art30.md`,
   `docs/legal/politique_confidentialite.md`, `docs/templates/notice_art14.txt` complétée.
   Cadre : suivre `03-LEGAL-RGPD.md` + intégrer OBLIGATOIREMENT le raisonnement art. 14.5.b
   « stock invendu » (`10` §4 : mesures compensatoires publiques) et les 4 clauses contrat
   (`10` §5). Structure des templates CNIL (outil PIA). Marquer chaque document « DRAFT —
   à valider par avocat ». Fini = les 5 fichiers existent, roadmap cochée, PR mergée.
   NE PAS : inventer des positions juridiques hors de `03`/`10` ; toucher au code.

3. `[OPUS — sans dépendance]` **C5 : pack incident.** Livrables : `docs/legal/qa_presse.md`
   (1 page, spec `10` §9 : sources publiques, opt-out 1 clic, AUCUNE référence au fisc) et
   `docs/legal/procedure_reclamation.md` (ligne fausse → remplacement/avoir 90 j + entrée
   `data/validation/reclamations.csv` comme étiquette négative ; opposition sans identité
   → process art. 11). Fini = 2 fichiers + roadmap. NE PAS : dépasser 1 page chacun.

4. `[OPUS — sans dépendance]` **D1 : liste de prospects.** Livrable :
   `sales/prospects_49.csv` (hors git) via SIRENE open data (méthode `07` §1, codes NAF
   listés là-bas) : ≥ 30 lignes {raison_sociale, naf, ville, tel_si_public, site_web,
   priorite}. Écrire le script d'extraction dans `pipeline/src/50_prospects_sirene.py`
   (réutilisable, --dept paramétré, mêmes conventions que les autres scripts).
   NE PAS : collecter d'autres données que l'établissement (pas de dirigeants).

5. `[OPUS — dès résultats deepsearch ① collés ici]` **A1-A4 puis B1 + B2-terrain.**
   Ordre strict : A1 (10_download ; si le miroir BD TOPO échoue → --bdtopo-url), A2 (OSM
   2 communes), A3 (20→35 en --dev ; consigner % cad_parcelles vs nearest), A4 (contrôle
   visuel 30 lignes Géoportail, consigner le taux), B1 (dalles ortho 1 commune), B2-terrain
   (15_detect sur la commune ; consigner ratio candidats/piscines-OSM, précision, rappel ;
   calibrer les seuils `detection:` de config.yaml en consignant AVANT/APRÈS chaque seuil).
   Fini = tableau de mesures ci-dessous rempli. NE PAS : lancer le département entier ;
   modifier detection.py/solaire.py (seuils config UNIQUEMENT — si ça ne suffit pas,
   consigner et s'arrêter : c'est un déclencheur [FABLE]).

6. `[OPUS — sans dépendance]` **Leçons de l'état de l'art** (doc 15 §2, deux petites
   améliorations cadrées) : (a) 16_tri : trier les vignettes par incertitude
   (|score − 0,5| croissant) au lieu de l'ordre du fichier — les cas limites d'abord,
   les évidences en rafale à la fin ; (b) protocole `06` §2 : remplacer le point simple
   « ≥ 95 % sur 100 » par l'intervalle de Wilson à 95 % (annoncer la borne BASSE de
   l'intervalle, jamais le point). Fini = les deux changements + tests verts.
   NE PAS : toucher à autre chose dans 16_tri ; changer les seuils.

7. `[OPUS — après A1]` **Généralisation cosmétique** (doc 09 §6) : 20_join `--source`
   (alias rétro-compatible de --source-piscines), 30_score `--produit` (lit
   `config[produit]`, défaut piscines). Fini = 82+ tests verts, aucun comportement changé
   pour piscines. NE PAS : refactorer au-delà de ces deux flags.

8. `[OPUS — après le premier re-run de détection sur un nouveau millésime]`
   **45_diff_millesimes.py** : CLI mince autour de `millesimes.py` (cœur fait et testé).
   Args : --avant X.parquet --apres Y.parquet [--tolerance-m 8]. Sorties :
   `{produit}_nouvelles_{dept}.parquet` (contrat couche 1 intact — les nouvelles
   repartent dans 20→30→40 comme n'importe quelle source) + log des conservées/disparues
   + REFUS d'écrire si > 50 % de « nouvelles » (recalage suspect, voir warning du cœur).
   Mêmes conventions que les autres CLI (config, ensure_dirs, échec bruyant).
   NE PAS : toucher à millesimes.py ; vendre les « disparues ».

9. `[FABLE — seulement si déclenché]` : option A détection (déclencheur : B2-terrain
   plafonne < 95 % après calibration ; noter — doc 15 : l'option A améliore le rappel
   et le débit, PAS la précision finale, le tri humain reste) ; détecteur P3 pans de
   toiture (déclencheur : branche D de l'arbre `12`, ou 5 ventes P1).

**Interdit tant que D0/D3 n'ont pas parlé : tout nouveau code produit** (`10` §Règles ;
dérogation moteur du 2026-07-08 close — le moteur est fini).

**Deepsearchs demandées à l'humain (résultats à coller ici)** : ① URLs/format/millésime
BD ORTHO 49 RVB+IRC + date du prochain survol ; ② SITADEL : adresse précise des DP piscine ?
licence ? ; ③ cadastre solaire public couvrant le 49 (concurrence gratuite de P3) ?

## État au 2026-07-07 (session fondation)

Fait par la session d'architecture :
- Recherche approfondie et verdicts : sources de données (`02`), Google Solar API **écarté** pour cause de CGU (`05`), cadre légal RGPD complet (`03`).
- Toute la documentation structurante (docs 00→08) + garde-fous dans `CLAUDE.md`.
- Code écrit (non exécuté sur données réelles — à tester au premier run) : `common.py`, `10_download.py`, `20_join_piscines_adresses.py`, `30_score_qualite.py`, `35_stats_prospection.py`, `40_export_client.py`.

## État au 2026-07-08 (session détection — Fable 5)

Stratégie d'orchestration décidée : les tâches à haute complexité algorithmique/architecturale
sont traitées par les sessions Fable 5 ; les tâches d'exécution mécanique (téléchargements,
débogage de chaîne sur données réelles, drafts de documents, scripts simples) sont **réservées
aux sessions Opus 4.8** — elles sont marquées `[OPUS]` ci-dessous.

Fait par cette session :
- **B2 (code) + B3 : étape 1b implémentée et testée.** `detection.py` (cœur pur : masque HSV+IRC,
  morphologie, vectorisation géoréférencée, filtres de forme, score, fusion inter-dalles),
  `15_detect_piscines.py` (orchestration par dalles/fenêtres avec chevauchement, partition des
  zones intérieures = zéro doublon par construction, masque bâti BD TOPO, appariement RVB/IRC
  par emprise, échecs bruyants), `16_tri_visuel.py` (vignettes + page de tri HTML autonome
  O/N/U + application des décisions avec refus des tris incomplets >2 %).
- **25 tests** (`pipeline/tests/`, `python -m pytest pipeline/tests/`) : détection sur scènes
  synthétiques (piscine trouvée à ±20 % de surface, végétation bleutée rejetée par l'IRC,
  bâche marine rejetée par la teinte, fossé rejeté par la compacité), propriétés du fenêtrage,
  intégration bout-en-bout sur dalles GeoTIFF fabriquées (15 → 16 → --apply), garde-fous
  (opt-out, traçabilité, incertains jamais vendus). Tous verts au 2026-07-08.
- Config `detection:` + `tri_visuel:` ajoutées à `config.yaml` (seuils **non calibrés** sur
  données réelles — valeurs physiquement raisonnables à ajuster en B2-terrain).
- requirements.txt : + rasterio, scikit-image ≥ 0.26, scipy, pillow, pytest.

## Phase A — Chaîne technique en mode dev (OSM, 2-3 communes)

Objectif : chaîne 10→40 qui tourne de bout en bout. Aucune vente possible à ce stade.

- [ ] **A1.** `[OPUS]` `pip install -r pipeline/requirements.txt` ; lancer `10_download.py` (cadastre, BAN, BD TOPO 49). Corriger les surprises d'URL/format et **consigner ici les URLs réelles utilisées + millésimes**.
- [ ] **A2.** `[OPUS]` Extraire les piscines OSM (commandes dans `04` étape 1a). Choisir 2 communes bien couvertes (compter les piscines OSM par commune ; viser une péri-urbaine d'Angers + une rurale).
- [ ] **A3.** `[OPUS]` Lancer `20` puis `30 --dev` puis `35 --dev` sur ces communes. Déboguer. Consigner : % de jointures via `cad_parcelles` vs `nearest` (si `cad_parcelles` < 50 %, activer le dataset "Adresses extraites du cadastre" en complément — voir `02`).
- [ ] **A4.** `[OPUS]` Contrôle visuel de 30 lignes sur le Géoportail : l'adresse tombe-t-elle sur la bonne parcelle ? Consigner le taux et les erreurs types.

## Phase B — Détection BD ORTHO (l'actif)

- [ ] **B1.** `[OPUS]` Télécharger les dalles BD ORTHO (RVB + IRC) d'UNE commune test. Consigner l'URL/format réel. (Une deepsearch Gemini a été demandée pour les URLs/formats exacts — voir journal.)
- [x] **B2-code.** ~~Implémenter `15_detect_piscines.py`~~ **Fait 2026-07-08** (+ `detection.py` + 25 tests sur imagerie synthétique). Reste **B2-terrain** `[OPUS, avec les seuils — remonter à Fable si la précision plafonne]` : lancer sur la commune test, mesurer précision/rappel vs OSM, calibrer les seuils `detection:` de config.yaml, consigner ici les chiffres.
- [x] **B3.** ~~Outil de tri visuel~~ **Fait 2026-07-08** (`16_tri_visuel.py` : planche `tri.html` autonome, O/N/U, export `decisions.csv`, `--apply` avec garde-fous).
- [ ] **B4.** Décision A/B (modèle entraîné vs seuillage+tri) sur les chiffres de B2-terrain. Consigner la décision et les chiffres. `[FABLE si option A retenue : architecture d'entraînement]`
- [ ] **B5.** `[OPUS]` Industrialiser sur le département par lots de dalles + tri humain. Sortie : `piscines_detectees_49.parquet`.
- [ ] **B6.** `[OPUS]` Chaîne complète 20→30 en mode production ; `35 --dept` pour le chiffre total.

## Phase C — Qualité & légal (bloquants avant vente)

- [ ] **C1.** Protocole de validation `06` §2 (100 adresses aléatoires, ≥ 95 %). Consigner le rapport.
- [ ] **C2.** Checklist légale `03` §6 : rédiger LIA + AIPD + registre + politique de confidentialité + compléter `docs/templates/notice_art14.txt` (un LLM peut drafter tout ça ; templates CNIL en ligne).
- [ ] **C3.** Contrat de licence draft + **relecture avocat** (action humaine, à planifier tôt : compter 2 semaines de délai).
- [ ] **C4.** Canal d'opposition opérationnel (email DÉDIÉ — pas le gmail perso, non sérieux en contrôle — + page web statique avec formulaire) + test du filtre opt-out avec une adresse factice + process art. 11 écrit (opposition sans identité : matching par adresse seule).
- [ ] **C5.** `[OPUS]` « Pack incident » (pre-mortem `10` §9) : Q&A presse 1 page écrit à froid (sources publiques, opt-out en un clic, aucun lien avec le fisc) + procédure écrite de réclamation qualité (ligne fausse → remplacement/avoir sous 90 j, et l'adresse entre dans `data/validation/` comme étiquette négative).

## Phase D — Vente

> **Règles de séquence issues du pre-mortem (`docs/10-PREMORTEM.md`) — priment sur tout :**
> D0 se fait AVANT la suite de la phase A/B. Kill-switch : si au 15/10/2026 il n'y a ni LIA
> validée ni 5 RDV bookés, gel total du code. Saisonnalité : les pisciniers achètent
> d'oct. à fév. — l'été sert à préparer, pas à vendre.

- [ ] **D0. [HUMAIN, cette semaine]** Pré-vente avant la base : appeler 5 pisciniers du 49
  avec le pitch (`00` + `07`). Objectif : tester le prix réel (« à 800 € vous prenez ? ») et
  l'appétence pour une offre « fichier + mailing clé en main ». Consigner chaque réponse ici.
  C'est le test des deux hypothèses les plus dangereuses du plan (`10` §hypothèses).
- [ ] **D1.** `[OPUS]` Liste de prospects B2B (SIRENE + annuaire — méthode dans `07` §1). Cible : 30 pisciniers/vendeurs 49.
- [ ] **D2.** `41_export_carte.py` (PDF carte pour RDV) — à écrire, simple (matplotlib + contextily).
- [ ] **D3.** 4-5 RDV de preuve (protocole `07` §3). Consigner objections réelles et prix acceptés.
- [ ] **D4.** Premières ventes ; registre des ventes tenu ; ajuster la grille tarifaire de `00` avec les prix réels.

## État au 2026-07-08 (2e passe session Fable — architecture moteur + cœur solaire)

- **`docs/09-MOTEUR-PROSPECTION.md` créé** : le repo est officiellement un moteur de
  prospection multi-produits (5 couches, seule la couche « détecteur » est spécifique à un
  produit ; couches tri/adressage/qualité/export mutualisées et porteuses des garde-fous).
  Portefeuille de produits scoré (P1 piscines → P7) + **critères de pivot chiffrés décidés à
  froid** (Go/No-Go P1 : 10 RDV, < 2 ventes ou < 300 €/extrait ⇒ pivot P2 ou P3).
- **Cœur du produit 2 écrit et testé : `pipeline/src/solaire.py`** (position solaire,
  ombres portées vectorisées sur MNS, heures de soleil direct aux 3 dates contractuelles).
  12 tests physiques verts (37 au total). Décision consignée : moteur natif remplace GRASS
  r.sun (voir docs/05 §3 et l'en-tête du module). Réutilisable tel quel pour P3 (toitures PV).
- ~~Reste `[FABLE]` : 25_terrasses.py~~ → **fait (3e passe, 2026-07-08)** : détecteur produit 2
  complet (`terrasses.py` + `25_terrasses.py`, mosaïque inter-dalles pour les ombres, masque
  MNH « la canopée d'un arbre ensoleillé n'est pas une terrasse », classes sur surface
  contiguë). 8 tests dont bout-en-bout (jardin sud dégagé → plein_soleil, cour emmurée →
  ombrage). **45 tests verts au total.** Le produit 2 n'attend plus que les dalles MNS/MNH
  réelles `[OPUS]` — mais reste bloqué par la règle « P1 vendu d'abord » (docs/05).
- Reste `[OPUS]` : généralisation cosmétique de 20/30 (voir 09 §6).

## Phase E — Extension (après premières ventes)

- [ ] **E1.** Produit 2 Terrasses (architecture prête : `05`) — prototype 1 commune.
- [ ] **E2.** Diff de millésimes → produit "nouvelles piscines" (prospects chauds).
- [ ] **E3.** Réplication département voisin (44 ou 85) : re-dérouler A→D avec `dept` changé dans config.

## Journal des mesures

| Date | Étape | Mesure / décision | Détail |
|---|---|---|---|
| 2026-07-07 | fondation | Google Solar API écarté | CGU : cache 30 j, revente interdite, usage hors énergie solaire interdit |
| 2026-07-07 | fondation | OSM = dev only | ODbL share-alike incompatible avec vente/exclusivité |
| 2026-07-07 | fondation | Piscines privées absentes de BD TOPO/cadastre Etalab | détection maison sur BD ORTHO requise |
| 2026-07-08 | B2-code/B3 | Étape 1b codée + testée (25 tests verts) | seuils config.yaml = a priori physiques, PAS calibrés terrain |
| 2026-07-08 | B2-code | Sans IRC, la végétation bleutée devient faux positif (test le prouve) | IRC obligatoire en production ; `methode='hsv_sans_irc'` trace la dégradation |
| 2026-07-08 | orchestration | Répartition modèles : tâches `[OPUS]` = exécution ; Fable = algorithmique/architecture | deepsearch Gemini demandée à l'humain : URLs/format BD ORTHO 49 (RVB+IRC) |
| 2026-07-08 | architecture | Repo = moteur multi-produits (doc 09) ; critères de pivot chiffrés | un pivot = un détecteur + une doc, l'aval est mutualisé |
| 2026-07-08 | P2 (cœur) | solaire.py natif remplace GRASS r.sun ; 12 tests physiques verts | même cœur réutilisable P3 toitures PV ; kWh non nécessaires (classement) |
| 2026-07-08 | pre-mortem | 2 analyses indépendantes (investisseur/concurrent + juriste/ops) → `docs/10-PREMORTEM.md` | risque n°1 : inversion de séquence (code avant vente/légal) ; kill-switch 15/10/2026 adopté |
| 2026-07-08 | pre-mortem | Abonnement « annuel » impossible (BD ORTHO ~3 ans) — sur-promesse corrigée dans `00` | parade : SITADEL (permis piscine, mensuel) ajouté à `02` ; millésime 49 à vérifier (deepsearch) |
| 2026-07-08 | pre-mortem | `40_export_client.py --demo` : les extraits de RDV = confiance haute uniquement | le maillon fragile en démo est la jointure d'adresse, pas la détection |
| 2026-07-08 | vente | Kit D0 complet (`11`) : cold call, cold email, RDV sans base, objections, grille prix, grille de consignation | positionnement honnête « je finalise la carte » (la base n'existe pas encore) |
| 2026-07-08 | stratégie | Arbre de décision terrain (`12`) : branches D0 et post-RDV décidées à froid + 7 options gros ticket scorées | franchises siège 5-30 k€, PAC, clé en main ×3-5, marque blanche ; assureurs GELÉ (RGPD aggravé) |
| 2026-07-08 | orchestration | CLAUDE.md : ordre de lecture + routage [OPUS]/[FABLE]/[HUMAIN] ; bloc « prochaine session » en tête de roadmap | la tour de contrôle est transmise — les sessions suivantes ont tout |
| 2026-07-08 | R&D moteur | contrat.py (validation couche 1 + scan anti-nominatif automatisé) ; ombres_rapide ×59 mesuré ; ids stables ; tri en fichiers | 82 tests verts ; le moteur est clos — dérogation « code avant vente » terminée |
| 2026-07-08 | audit pièges | 5 pièges corrigés : BAN sans x/y, --bdtopo-url manquant, millésimes non datés, 2 scans linéaires (tri dalles, parcelles/dalle) → index spatiaux | l'agent d'audit externe a été interrompu ; audit refait à la main sur 10/16/20/25/30/35 |
| 2026-07-08 | cibles moteur | Doc `14` : recensement attribut→acheteur, top 3 arbitré (① ombrières APER, ② foncier divisible, ③ grandes toitures) | acheteurs pros de la donnée, tickets 10-100× ; s'active via l'arbre `12`, ne double PAS D0-pisciniers |
| 2026-07-08 | R&D géométrie | `geometrie.py` : rectangle libre maximal à orientation libre (histogramme + rotations), cœur commun ombrières/foncier — 8 tests | 90 tests verts au total ; deepsearch ⑧ (APER/parkings/PLU) ajoutée à `13` |
| 2026-07-08 | état de l'art | Doc `15` : Foncier innovant = 94 % annoncé + polémique faux positifs ; DL brut ≈ 80/85 % précision/rappel | nos choix validés (tri humain = LA différence) ; 2 améliorations [OPUS] (tri par incertitude, Wilson) ; prompts ⑨⑩ dans `13` |
| 2026-07-08 | état de l'art 2 | APER : assouplie (Huwart) mais échéances 2026/2028 MAINTENUES, bon de commande avant le 31/12/2026 → cible ① brûlante | namR (coté, open data retraité) valide la thèse ; artisans locaux = angle mort des gros |
| 2026-07-08 | concurrence P1 | ⚠ Cartégie/Easyfichiers louent déjà des fichiers piscines NOMINATIFS (1 M+, téléphones) — risque n°8 du pre-mortem confirmé | repositionnement P1 (achat + vérifiable + zéro risque RGPD + exclusivité) dans kit `11` ; le segment imprenable = « nouvelles » locales |
| 2026-07-08 | R&D millésimes | `millesimes.py` : diff par appariement spatial un-pour-un (les ids stables ne survivent pas au recalage inter-millésimes) — 7 tests, 97 verts au total | garde-fou : > 50 % de « nouvelles » = recalage suspect, refus de vendre ; CLI 45 spécifiée [OPUS] |

## Tableau de mesures B2-terrain (à remplir par la session Opus de la tâche 5)

| Mesure | Valeur | Commentaire |
|---|---|---|
| Commune test (INSEE) | | |
| % jointures cad_parcelles (A3) | | seuil d'alerte : < 50 % → activer « Adresses cadastre » (doc 02) |
| Taux contrôle visuel 30 lignes (A4) | | |
| Candidats bruts 15_detect (B2) | | |
| Ratio candidats / piscines OSM | | seuil d'alerte : > 4:1 → tri humain intenable au dept (doc 10 §8) |
| Précision après tri (échantillon) | | objectif ≥ 95 % |
| Rappel vs OSM | | |
| Seuils modifiés (avant → après) | | |
