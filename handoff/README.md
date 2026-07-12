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
- des **décisions** (`decisions_49_49035_<hash12>.csv`) : colonnes
  `id_detection,decision,trieur,horodatage` où `decision` ∈ {`oui`, `non`,
  `incertain`}, `trieur` = prénom/pseudo du trieur (l'équipe, pas un prospect —
  cf. `CLAUDE.md`), `horodatage` = date ISO de la décision. **Aucun identifiant
  nominatif de particulier.** L'ancien format à 2 colonnes (`id_detection,decision`)
  reste accepté pour toujours : la fusion et l'application lisent les deux formats,
  et conservent `trieur`/`horodatage` dans le CSV fusionné quand ils sont présents
  (ces deux colonnes servent la traçabilité qualité, elles n'influencent jamais la
  logique d'application — seule la colonne `decision` décide).

**En cas de doute sur un fichier, ne pas le mettre ici.** C'est le pilier de la
défendabilité RGPD du projet (voir `CLAUDE.md` règle 1). Les fichiers avec adresses
(ex. `data/final/`) restent gitignorés et ne transitent jamais par `handoff/`.

## Contenu

- `tri_bouchemaine_49035.html` — planche de tri autonome (images en base64).
  S'ouvre dans n'importe quel navigateur, aucune install requise. Voir le parcours A
  de `ONBOARDING.md`.
- `soumettre_tri.sh` — renvoie un CSV de décisions trié (git add + commit + push).
- `appliquer_decisions_recues.py` — fusionne tous les CSV reçus et applique le tri
  via `pipeline/src/16_tri_visuel.py --apply`.
- `decisions_recus/` — dépôt des décisions renvoyées par les contributeurs.

## Empreinte de version dans le nom des fichiers

Chaque planche embarque une **empreinte `hash12`** (12 caractères) qui identifie
exactement le jeu de candidats affiché. Le CSV exporté par la planche la reprend
dans son nom : `decisions_{dept}_{commune}_{hash12}.csv` (ex.
`decisions_49_49035_<hash12>.csv`). **Cette empreinte garantit que les décisions
reçues correspondent bien à la planche qui a été triée** : à la fusion,
`appliquer_decisions_recues.py` **refuse** un CSV dont l'empreinte ne colle pas à
la planche courante (sauf `--force` explicite). Conséquence pratique :

- **Ne jamais renommer** un `decisions_*.csv` reçu — le nom porte l'empreinte.
- **Exporter régulièrement**, même partiellement : le CSV exporté est la vraie
  sauvegarde (le stockage navigateur n'est pas fiable). Un export partiel est
  accepté et fusionnable ; on peut trier en plusieurs fois.
