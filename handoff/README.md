# handoff/ — échange de planches de tri

Ce dossier sert **uniquement** à s'échanger des planches de tri de piscines et
les décisions qui en reviennent. Il est suivi par git (exception documentée dans
`.gitignore`).

## RÈGLE ABSOLUE — aucune donnée personnelle, jamais

Ce dossier ne doit **JAMAIS** contenir :

- une **adresse** postale,
- un **nom**, prénom, téléphone, email de particulier,
- toute autre **donnée personnelle**.

Il ne contient QUE :

- des **planches de tri** (`tri_*.html`) : vignettes d'imagerie ortho publique
  (IGN, BD ORTHO), polygones candidats et limites de parcelles — pas de PII ;
- des **décisions** (`decisions_recus/*.csv`) : deux colonnes `id_detection,decision`
  où `decision` ∈ {`oui`, `non`, `incertain`}. Aucun identifiant nominatif.

**En cas de doute sur un fichier, ne pas le mettre ici.** C'est le pilier de la
défendabilité RGPD du projet (voir `CLAUDE.md` règle 1). Les fichiers avec adresses
(ex. `data/final/`) restent gitignorés et ne transitent jamais par `handoff/`.

## Contenu

- `tri_bouchemaine_49035.html` — planche de tri autonome (images en base64).
  S'ouvre dans n'importe quel navigateur, aucune install requise. Voir le parcours A
  de `ONBOARDING.md`.
- `soumettre_tri.sh` — renvoie un `decisions.csv` trié (git add + commit + push).
- `appliquer_decisions_recues.py` — fusionne tous les CSV reçus et applique le tri
  via `pipeline/src/16_tri_visuel.py --apply`.
- `decisions_recus/` — dépôt des décisions renvoyées par les contributeurs.
