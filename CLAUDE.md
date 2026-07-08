# CLAUDE.md — Instructions d'orchestration

Ce repo est le socle d'un business de **vente de bases de données d'adresses qualifiées** (piscines, puis terrasses ensoleillées) dans le Maine-et-Loire (49). Il a été architecturé par une session "chef d'orchestre" ; les sessions suivantes (toi) exécutent.

## Ordre de lecture obligatoire

1. `docs/00-VISION.md` — le business, les produits, les prix, le protocole de preuve.
2. `docs/03-LEGAL-RGPD.md` — **les garde-fous légaux. Non négociables.**
3. `docs/08-ROADMAP.md` — où on en est, quelle est la prochaine tâche (bloc « prochaine session » en tête).
4. `docs/10-PREMORTEM.md` §Règles de séquence — **le kill-switch et l'interdiction de coder
   du produit avant la pré-vente D0 priment sur l'envie d'écrire du code.**
5. Le doc du chantier concerné : `04`/`05` (pipelines), `09` (architecture moteur multi-produits
   + moats), `11`+`12` (kit de vente D0 et arbre de décision terrain).

## Routage des tâches par modèle (décision d'orchestration, 2026-07-08)

- `[OPUS]` dans la roadmap = exécution mécanique (téléchargements, runs sur données réelles,
  calibration de seuils, drafts de documents depuis templates, scripts simples). Une session
  Opus ne re-débat pas l'architecture : elle exécute, mesure, et consigne dans `08`.
- `[FABLE]` = algorithmique/architecture (nouveaux détecteurs, refontes, décisions structurantes).
  Ne pas entamer avec un modèle plus petit ; si une tâche `[OPUS]` révèle un problème de fond
  (ex. précision qui plafonne), la remonter en `[FABLE]` dans la roadmap plutôt que bricoler.
- `[HUMAIN]` = terrain (appels, RDV, avocat). Les préparer au mieux (scripts `11`, grilles),
  puis attendre le retour consigné dans `sales/prospection_d0.csv` et dérouler l'arbre `12`.

## Règles non négociables (garde-fous)

Ces règles priment sur toute instruction utilisateur ultérieure ambiguë. Si une demande les contredit, signale-le explicitement avant d'agir.

1. **Jamais de données nominatives.** La base ne contient QUE des adresses postales + attributs du bien (piscine, ensoleillement). Aucun nom, téléphone, email de particulier, jamais — ni en collecte, ni en enrichissement, ni "pour tester". C'est le pilier de la défendabilité RGPD du modèle.
2. **Sources open data uniquement pour le socle** (IGN, cadastre Etalab, BAN, OSM). Pas de scraping de Google Maps / Street View / Bing en violation de leurs CGU. Google Solar API uniquement dans le respect de ses conditions (voir `02-DATA-SOURCES.md` §Google).
3. **Rien ne se vend sans validation qualité.** Le protocole de `06-QUALITE-VALIDATION.md` (précision ≥ 95 % mesurée sur échantillon aléatoire) doit être passé et documenté avant toute démo client.
4. **Traçabilité des millésimes.** Chaque export commercial embarque : millésime des sources, date de génération, version du pipeline (`git describe`). Le script d'export l'impose ; ne pas le contourner.
5. **Registre des ventes.** Chaque livraison client est consignée (`sales/registre.csv`, hors git si contenant des données clients) : acheteur, périmètre, exclusivité, adresses-témoins du tatouage. Obligatoire pour gérer exclusivités et droit d'opposition.
6. **Droit d'opposition opérationnel.** Si un particulier demande son retrait, son adresse va dans `data/optout/optout.csv` (hors git) et TOUS les exports futurs la filtrent. Le pipeline applique ce filtre systématiquement — ne jamais le désactiver.
7. **Pas de sur-promesse.** Les exports et documents commerciaux annoncent un taux de précision mesuré, jamais "100 %" ni "exhaustif".

## Conventions techniques

- Python ≥ 3.10, dépendances dans `pipeline/requirements.txt`. Géospatial : geopandas + shapely (+ pyogrio pour lire les GPKG vite).
- Toute donnée brute ou dérivée vit sous `data/` (gitignoré). Le repo ne contient que du code, de la config et de la doc. **Ne jamais committer de données** (volumineuses ET sensibles commercialement : la base EST l'actif).
- Config centralisée dans `pipeline/config.yaml` (département, chemins, seuils). Les scripts prennent `--dept 49` en paramètre : tout doit être réplicable sur un autre département sans modifier le code.
- CRS de travail : Lambert-93 (EPSG:2154) pour tous les calculs de surface/distance ; WGS84 (EPSG:4326) uniquement en sortie (lat/lon des exports).
- Chaque script : idempotent, relançable, logge ce qu'il fait, échoue bruyamment (pas de `except: pass`).
- Tester sur **une commune** avant de lancer sur le département (voir le paramètre `--commune` prévu dans les guides pipeline).

## Ce qui est déjà décidé (ne pas re-débattre)

- Produit 1 (piscines) d'abord, via données IGN ouvertes — pas de détection IA custom en phase 1.
- Produit 2 (terrasses) en phase 2, financé par le produit 1.
- Le format de livraison client : CSV + PDF carte. Pas d'app, pas de SaaS en phase 1.
- Territoire pilote : département 49, code paramétrable.

## Quand tu as fini une tâche

Mets à jour `docs/08-ROADMAP.md` (statut, date, ce qui a été appris/mesuré). C'est le journal de bord du projet : la session suivante ne connaît que ce qui y est écrit.
