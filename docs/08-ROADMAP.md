# Roadmap & journal de bord

> **Ce fichier est le journal du projet.** Chaque session LLM qui termine une tâche met à jour le statut, la date, et surtout ce qui a été **appris/mesuré** (les chiffres réels valent plus que le plan). La session suivante ne sait que ce qui est écrit ici.

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
- [ ] **C4.** Canal d'opposition opérationnel (email dédié + page web statique) + test du filtre opt-out avec une adresse factice.

## Phase D — Vente

- [ ] **D1.** Liste de prospects B2B (SIRENE + annuaire — méthode dans `07` §1). Cible : 30 pisciniers/vendeurs 49.
- [ ] **D2.** `41_export_carte.py` (PDF carte pour RDV) — à écrire, simple (matplotlib + contextily).
- [ ] **D3.** 4-5 RDV de preuve (protocole `07` §3). Consigner objections réelles et prix acceptés.
- [ ] **D4.** Premières ventes ; registre des ventes tenu ; ajuster la grille tarifaire de `00` avec les prix réels.

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
