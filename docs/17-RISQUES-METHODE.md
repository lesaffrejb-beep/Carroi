# 17 — Registre des risques de MÉTHODE

Ce document recense les risques liés à **la méthode de travail** (données, process,
multi-machines, multi-humains, multi-LLM) — PAS les risques business (marché, prix,
légal), qui vivent dans `docs/10-PREMORTEM.md`.

Contexte structurant : les données brutes (BD ORTHO, 61 Go) ne vivent que sur le SSD
externe du propriétaire ; les autres machines **reconstruisent** `data/` via les
scripts. Or plusieurs sources sont « latest » (cadastre Etalab, BAN) : deux clones
lancés à deux dates peuvent diverger **silencieusement**. Tout ce qui suit protège
contre le scénario « on croit travailler sur les mêmes données, mais non ».

Légende statut : ✅ patché (garde-fou en place) · 🧑 action humaine requise · 👁 surveillé.

| ID | Risque | Scénario concret | Garde-fou en place | Statut |
|----|--------|------------------|--------------------|--------|
| R1 | Divergence de données entre machines | La machine B reconstruit `data/interim/` un autre jour ; la BAN « latest » a changé → B et A n'ont pas les mêmes adresses, mais rien ne le signale. Une jointure sur B produit un actif faux. | Manifeste commité `pipeline/manifeste_donnees.json` (SHA-256 + taille + nb lignes par fichier) + `verifier_donnees.py --verifier` qui compare et refuse bruyamment. Intégré à `verifier_tout.sh`. | ✅ patché |
| R2 | Décision prise sur une planche de tri périmée | Un trieur annote une planche, mais entre-temps la détection a été régénérée : les vignettes ne correspondent plus aux mêmes piscines. Fusionner ces décisions corrompt le jeu de labels. | Empreinte `hash12` de la planche portée par chaque décision ; la fusion (`handoff/appliquer_decisions_recues.py`) refuse d'appliquer une décision dont le hash ne correspond plus. | ✅ patché |
| R3 | Écrasement silencieux d'un millésime par un re-download « latest » | On relance `10_download.py` : Etalab a publié un nouveau cadastre → `data/interim/` change sans qu'on l'ait décidé, et le manifeste ne correspond plus. | `verifier_donnees.py --verifier` détecte l'écart (hash différent). **Consigne** : à CHAQUE (ré)génération de `data/interim/`, relancer `--generer`, committer le manifeste, et consigner le changement de millésime dans `docs/08-ROADMAP.md` + `data/interim/millesimes.yaml`. | ✅ patché |
| R4 | Perte du dataset de labels (décisions de tri) | Le jeu de décisions O/N/U (l'or du produit : la vérité terrain qui calibre la détection) n'existe que sur une machine et disparaît avec elle. | Copie versionnée sous `handoff/labels/` (sans PII : imagerie ortho publique + géométrie + décisions), suivie par git. | ✅ patché — en cours, session du 2026-07-12 |
| R5 | Conflits entre trieurs sur la même planche | Deux humains trient la même planche et se contredisent (l'un O, l'autre N sur la même piscine) ; sans mesure, on ne sait pas qui croire ni quel est le taux de désaccord. | La fusion logge chaque conflit ; le bilan de tri (`18_bilan_tri.py`) mesurera le désaccord inter-trieurs pour arbitrer et estimer la fiabilité des labels. | 👁 surveillé |
| R6 | Push cassé non détecté | Un commit casse la suite de tests mais est poussé sur `main` ; la session suivante hérite d'un socle rouge sans le savoir. | CI GitHub Actions `.github/workflows/tests.yml` : `pytest` sur chaque push et PR (Python 3.12 + 3.13). | ✅ patché |
| R7 | Improvisation des futurs LLM | Une session LLM saute les vérifications, part sur des données divergentes ou pousse un arbre incohérent. | `verifier_tout.sh` (une commande : tests + données + git) + consignes dans `CLAUDE.md` (§Conventions techniques) : le lancer AVANT et APRÈS toute tâche touchant aux données. | ✅ patché |
| R8 | Backup off-site non finalisé | Le SSD du propriétaire lâche : les 61 Go de BD ORTHO et l'actif `data/final/` sont perdus ; les données « latest » d'origine ne sont plus re-téléchargeables à l'identique. | **Configuré + testé 2026-07-12** (`docs/BACKUP.md`) : age (clé publique dans `config.yaml`, privée hors repo) + rclone vers `/Volumes/NOIR 1/maps-backups` — cycle chiffrement→restauration prouvé. **Restent 🧑** : (a) copier la clé privée `~/.config/maps-backup/age-key.txt` dans un gestionnaire de mots de passe (sinon backups illisibles si le disque meurt) ; (b) ajouter un vrai remote hors-site (`rclone config`) ; (c) planifier (cron). | 👁 partiellement patché · 🧑 pour off-site + clé |
| R9 | localStorage navigateur non fiable pour le tri | L'interface de tri stocke les décisions dans le localStorage du navigateur ; un vidage de cache / navigation privée / autre machine efface tout. | L'export CSV **est** la sauvegarde : chaque planche triée est exportée en CSV, seule source de vérité persistée. Consigné dans `ONBOARDING.md`. | ✅ patché |
| R10 | Décision d'architecture prise sur une métrique biaisée ou une lecture de code non mesurée | Deux cas réels du 2026-07-12 : (a) le « rappel vs OSM » (53 %) sous-estime structurellement le détecteur — 80 % des manquées sont couvertes/vides/postérieures au millésime ortho, invisibles pour TOUT algorithme ; décider « il faut un modèle IA » sur ce chiffre brut aurait coûté des semaines pour rien. (b) Les « hotspots de perf » de 10bis venaient d'une lecture de code : au banc d'essai réel, < 2 s au total. | Règle : toute décision coûteuse (modèle, refonte, pivot) exige une MESURE sur données réelles qui isole la cause (ex. autopsie du rappel : rejouer le masque aux emplacements manqués + planche contact visuelle, `data/validation/autopsie_*`). Une métrique agrégée ne suffit pas ; il faut sa décomposition. | ✅ patché (méthode consignée) |

## Comment ajouter un risque

Ajouter une ligne au tableau : ID `R<n+1>` (jamais réutiliser un ID retiré), le risque en une phrase, un scénario **concret** (« quand X arrive alors Y »), le garde-fou en nommant le script/test précis qui le porte (sans quoi le statut ne peut pas être ✅), et le statut. Un risque sans garde-fou nommé reste 🧑 ou 👁, jamais ✅.
