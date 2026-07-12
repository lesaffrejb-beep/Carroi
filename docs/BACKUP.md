# Sauvegarde chiffrée — mode d'emploi (config + restauration)

> Configuré et testé de bout en bout le 2026-07-12 (chiffrement `age` + `rclone` vers
> le disque externe NOIR). Ce document explique comment **sauvegarder** et surtout
> comment **restaurer** — un backup qu'on ne sait pas restaurer ne vaut rien.

## Ce qui est sauvegardé

`90_backup.py` archive **uniquement** les données précieuses et non-reconstructibles :
`data/final/`, `data/exports/`, `sales/`, `data/optout/`, `data/validation/`.
**Jamais** `data/raw/` ni `data/interim/` (retéléchargeables via `10_download.py`).

## Comment ça marche

1. `tar.gz` des dossiers ci-dessus ;
2. chiffrement **par clé publique** `age` (aucune passphrase → exécutable sans interaction) ;
3. copie via `rclone` vers la destination configurée.

Config dans `pipeline/config.yaml` §`backup` :
- `destinataire` : la **clé publique** age (non secrète). Actuelle :
  `age16q3mllugvr9n4hczrm0szddfq6j7xxlq30f0k8gw47qe4980w5zssvdnqt`.
- `rclone_remote` : destination. Actuelle = dossier local `/Volumes/NOIR 1/maps-backups`
  (disque externe, aucun compte requis). C'est un backup **hors-disque-principal**, pas
  encore **hors-site**.

Lancer une sauvegarde :
```bash
.venv/bin/python pipeline/src/90_backup.py            # vers NOIR
.venv/bin/python pipeline/src/90_backup.py --garder-local  # + copie dans data/backups/
```

## 🔑 LA CLÉ PRIVÉE — le point vital

La clé qui **déchiffre** les backups est ici, **hors du repo** :
```
~/.config/maps-backup/age-key.txt   (permissions 600)
```
**Sans cette clé, aucun backup n'est récupérable.** Elle n'est ni sur GitHub ni dans les
backups eux-mêmes (ce serait absurde). Donc :

> 🧑 **ACTION HUMAINE OBLIGATOIRE** : copier le contenu de `~/.config/maps-backup/age-key.txt`
> dans un **gestionnaire de mots de passe** (ou l'imprimer / la mettre sur une 2ᵉ clé USB).
> Si le disque principal meurt ET que cette clé n'existe qu'à cet endroit, tous les
> backups deviennent illisibles.

## Comment RESTAURER (testé le 2026-07-12)

```bash
# 1. Récupérer une archive chiffrée (depuis NOIR ou le remote)
BK="/Volumes/NOIR 1/maps-backups/maps_backup_49_AAAA-MM-JJ.tar.gz.age"

# 2. Déchiffrer avec la clé privée
age -d -i ~/.config/maps-backup/age-key.txt -o restore.tar.gz "$BK"

# 3. Extraire (recrée l'arborescence data/final, sales, etc.)
tar xzf restore.tar.gz -C /chemin/de/restauration
```

## 🧑 Passer à l'off-site cloud (recommandé plus tard)

Un backup sur NOIR ne protège pas d'un vol/incendie/panne du disque externe. Pour un vrai
hors-site, créer un stockage distant (ex. Hetzner Storage Box, Backblaze B2, `docs/16` §2) :
```bash
rclone config          # créer un remote interactivement (compte + identifiants = toi)
```
puis remplacer dans `config.yaml` §backup : `rclone_remote: "monremote:maps-backups"`.
Le reste (chiffrement, script) ne change pas. La clé publique reste la même.

## Rotation / régénérer la clé

`age-keygen -o ~/.config/maps-backup/age-key.txt` crée une nouvelle paire. Mettre alors la
nouvelle clé publique dans `config.yaml`. ⚠ Les anciens backups restent déchiffrables
**uniquement** avec l'ancienne clé privée — ne pas la jeter tant que d'anciens backups comptent.
