# Roadmap & journal de bord

> **Ce fichier est le journal du projet.** Chaque session LLM qui termine une tâche met à jour le statut, la date, et surtout ce qui a été **appris/mesuré** (les chiffres réels valent plus que le plan). La session suivante ne sait que ce qui est écrit ici.

## État au 2026-07-07 (session fondation)

Fait par la session d'architecture :
- Recherche approfondie et verdicts : sources de données (`02`), Google Solar API **écarté** pour cause de CGU (`05`), cadre légal RGPD complet (`03`).
- Toute la documentation structurante (docs 00→08) + garde-fous dans `CLAUDE.md`.
- Code écrit (non exécuté sur données réelles — à tester au premier run) : `common.py`, `10_download.py`, `20_join_piscines_adresses.py`, `30_score_qualite.py`, `35_stats_prospection.py`, `40_export_client.py`.

## Phase A — Chaîne technique en mode dev (OSM, 2-3 communes)

Objectif : chaîne 10→40 qui tourne de bout en bout. Aucune vente possible à ce stade.

- [ ] **A1.** `pip install -r pipeline/requirements.txt` ; lancer `10_download.py` (cadastre, BAN, BD TOPO 49). Corriger les surprises d'URL/format et **consigner ici les URLs réelles utilisées + millésimes**.
- [ ] **A2.** Extraire les piscines OSM (commandes dans `04` étape 1a). Choisir 2 communes bien couvertes (compter les piscines OSM par commune ; viser une péri-urbaine d'Angers + une rurale).
- [ ] **A3.** Lancer `20` puis `30 --dev` puis `35 --dev` sur ces communes. Déboguer. Consigner : % de jointures via `cad_parcelles` vs `nearest` (si `cad_parcelles` < 50 %, activer le dataset "Adresses extraites du cadastre" en complément — voir `02`).
- [ ] **A4.** Contrôle visuel de 30 lignes sur le Géoportail : l'adresse tombe-t-elle sur la bonne parcelle ? Consigner le taux et les erreurs types.

## Phase B — Détection BD ORTHO (l'actif)

- [ ] **B1.** Télécharger les dalles BD ORTHO (RVB + IRC) d'UNE commune test. Consigner l'URL/format réel.
- [ ] **B2.** Implémenter `15_detect_piscines.py`, option B d'abord (seuillage HSV + IRC + filtres de forme — spec dans `04` étape 1b). Mesurer précision/rappel vs OSM sur la commune test.
- [ ] **B3.** Construire l'outil de tri visuel (page HTML de vignettes, raccourcis O/N — spec dans `04` étape 1b point 4).
- [ ] **B4.** Décision A/B (modèle entraîné vs seuillage+tri) sur les chiffres de B2. Consigner la décision et les chiffres.
- [ ] **B5.** Industrialiser sur le département par lots de dalles + tri humain. Sortie : `piscines_detectees_49.parquet`.
- [ ] **B6.** Chaîne complète 20→30 en mode production ; `35 --dept` pour le chiffre total.

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
