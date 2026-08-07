# 20 — Runbook d'une salve (nouveau territoire, produit piscines)

> **À quoi ça sert** : dérouler un territoire entier sans re-réfléchir. Chaque
> étape est UNE commande, dans l'ordre, avec ce qu'on attend en sortie et le
> piège connu. Établi en déroulant Angers Loire Métropole (2026-08-06/07).
> Les décisions de fond ne sont PAS ici : elles sont dans `16` §8 et `15` §4.

Prérequis : disque NOIR branché (archives BD ORTHO + CoSIA), `.venv` installé,
`data/interim/parcelles_{dept}.parquet` et `ban_{dept}.parquet` présents
(produits par `10_download.py`).

Dans tout ce qui suit : `PY="PYTHONPATH=pipeline/src .venv/bin/python"`,
`COSIA="/Volumes/NOIR 1/maps-bdortho/COSIA_D049/2022/COSIA_1-0__GPKG_LAMB93_D049_2022-01-01"`,
`ARCH="/Volumes/NOIR 1/maps-bdortho/D049_2022"`.

## 1. Candidats — CoSIA ∪ cadastre PCI

```bash
PYTHONPATH=pipeline/src .venv/bin/python pipeline/src/24_candidats_cosia.py \
  --communes-alm --cosia-dir "$COSIA"
```

Sortie : un `data/interim/piscines_candidates_{dept}_{INSEE}.parquet` par commune.
Ordre de grandeur mesuré : **~340 candidats / 10 000 habitants** (ALM : 9 647 sur
28 communes). Rappel attendu **~98 %** (mesuré vs vérité humaine Bouchemaine).

- Le PCI SYM=65 n'entre que si `piscines_pci_sym65_{INSEE}.parquet` existe
  (étape 1bis) — sinon les candidats sont CoSIA seul, ce qui marche déjà.
- ⚠ Le script REFUSE d'écraser un parquet existant (il peut porter des votes) :
  `--force` seulement en connaissance de cause.

### 1bis. (optionnel, améliore la qualité) Piscines cadastrées

```bash
PYTHONPATH=pipeline/src .venv/bin/python pipeline/src/11_pci_piscines.py --communes-alm
```

Puis relancer l'étape 1 avec `--force`. Gain : badge « cadastré » sur les
vignettes (**98 % de oui** quand il est là) + rattrapage des piscines couvertes
que CoSIA ne voit pas.

## 2. Dalles ortho (pour fabriquer les vignettes)

Une commune à la fois, idempotent (saute ce qui est déjà extrait) :

```bash
PYTHONPATH=pipeline/src .venv/bin/python pipeline/src/12_extraire_dalles_ortho.py \
  --commune 49015 --archives-dir "$ARCH" \
  --out-dir "/Volumes/NOIR 1/maps-bdortho/dalles_alm/49015"
```

Compter **~500 Mo/commune** (ALM : ~12 Go). Les dalles vont sur le disque
externe, jamais dans le repo.

## 3. Vignettes

```bash
PYTHONPATH=pipeline/src .venv/bin/python pipeline/src/16_tri_visuel.py \
  --candidats data/interim/piscines_candidates_49_49015.parquet \
  --ortho-dir "/Volumes/NOIR 1/maps-bdortho/dalles_alm/49015/rvb" \
  --out-dir data/interim/tri
```

**Toujours le même `--out-dir`** : les `id_detection` sont positionnels donc
uniques à l'échelle du département, un seul dossier de vignettes sert toutes
les communes (et c'est ce que `22_pretri` lit par défaut). ~3 min / 500 vignettes.

## 4. File unifiée + mise en service

```bash
# union des parquets communaux (dédoublonne les frontières par id_detection)
.venv/bin/python - <<'EOF'
import geopandas as gpd, pandas as pd, glob
f = [gpd.read_parquet(p) for p in sorted(glob.glob("data/interim/piscines_candidates_49_*.parquet"))
     if "_alm" not in p and "_49035" not in p]
alm = pd.concat(f, ignore_index=True).drop_duplicates(subset="id_detection")
gpd.GeoDataFrame(alm, crs=f[0].crs).to_parquet("data/interim/piscines_candidates_49_alm.parquet")
print(len(alm), "candidats")
EOF
```

Puis pointer `PRODUITS["piscines"]["candidats"]` (dans `pipeline/src/atelier.py`)
sur ce parquet et relancer l'Atelier. Vérifier au log : `N candidats, N farmables`.

## 5. Farm

Serveur local (`Atelier.command`) seul, ou — dès qu'un farmer est distant — le
gardien qui tient serveur + tunnel + veille du Mac :

```bash
./handoff/gardien_atelier.sh
```

L'URL publique courante est dans `data/atelier/lien_actuel.txt` ; elle change
à chaque redémarrage du tunnel (trycloudflare = URL éphémère), **la relire
avant d'envoyer un lien**. Un tunnel nommé sur un domaine à soi supprimerait
cette contrainte (non fait : pas de domaine à ce jour).

Un lien par personne (identité résolue côté serveur, révocable) :

```bash
.venv/bin/python pipeline/src/atelier.py --inviter Azan --taux-ct 1.5
```

Garder le Mac éveillé pendant la session d'un invité : `caffeinate -dimsu &`.
Rythme mesuré : **~830 votes/h** (Azan, 2026-08-06).

## 6. Après ~1 000 votes — pré-tri v2

```bash
PYTHONPATH=pipeline/src .venv/bin/python pipeline/src/22_pretri.py train \
  --candidats data/interim/piscines_candidates_49_alm.parquet
PYTHONPATH=pipeline/src .venv/bin/python pipeline/src/22_pretri.py apply \
  --candidats data/interim/piscines_candidates_49_alm.parquet
```

`apply` écrit `pretri_verdict` ∈ {auto_non, farm, auto_oui} **dans le parquet** ;
l'Atelier ne sert alors plus que les `farm` (branché, redémarrage suffit).
⚠ Ne pas entraîner sur des labels d'une AUTRE génération de candidats : les ids
sont positionnels, un candidat CoSIA n'a pas les votes du candidat v1 voisin
(vécu le 2026-08-06 : 10 négatifs exploitables seulement → entraînement refusé).

## 7. Reprendre les signalements humains (rappel gratuit)

```bash
PYTHONPATH=pipeline/src .venv/bin/python pipeline/src/26_signalements_candidats.py \
  --cosia-dir "$COSIA" --fusionner-dans data/interim/piscines_candidates_49_alm.parquet
```

Puis regénérer les vignettes des nouveaux (étape 3 sur
`data/interim/piscines_signales_{dept}.parquet`) et redémarrer l'Atelier.
Mesuré sur la passe d'Azan : 162 clics → 60 intentions → **19 candidats neufs**
(18 polygones CoSIA récupérés, 1 disque) ; les 41 autres pointaient des zones
déjà en file (normal en tissu dense, ce n'est pas une erreur du farmer).

## 8. Chaîne aval (inchangée)

`16 --apply` (consensus existence) → `20_join` (adresse) → Atelier niveau
SITUER → `21_appliquer_concordance` → `30_score` → `40_export_client`.
Les incertitudes (`/api/export/incertitudes.csv`) ne descendent JAMAIS dans
cette chaîne : elles attendent le multi-millésimes ou le terrain (`16` §8).
