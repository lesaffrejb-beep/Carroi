# Pipeline Produit 1 — Piscines

> Guide d'exécution pour les sessions LLM suivantes. Les décisions d'architecture sont prises et justifiées ici ; l'exécution suit l'ordre des étapes. Le code des étapes 2–4 est déjà écrit (`pipeline/src/`) ; l'étape 1b (détection) est spécifiée en détail mais à implémenter.

## Vue d'ensemble

```
Étape 0  — 10_download.py        télécharger cadastre + BAN + BD TOPO (+ ortho par lots)   [code écrit]
Étape 1a — OSM dev only          extraire piscines OSM pour développer/déboguer la suite    [instructions]
Étape 1b — 15_detect_piscines.py détection sur BD ORTHO 20 cm                               [à implémenter]
Étape 2  — 20_join_piscines_adresses.py   piscine → parcelle → adresse                      [code écrit]
Étape 3  — 30_score_qualite.py   filtres + score de confiance                               [code écrit]
Étape 4  — 35_stats + 40_export  chiffres de vente + livrables                              [code écrit]
```

**Stratégie en deux temps, décidée :**
1. **D'abord** développer et valider toute la chaîne jointure→export avec les piscines **OSM** (données immédiates, gratuites) sur 2–3 communes bien couvertes. But : chaîne complète qui marche, protocole de preuve rodé. **Rien de tout ça ne se vend** (licence ODbL).
2. **Ensuite** remplacer la source par la détection maison sur BD ORTHO (étape 1b) → base commercialisable, couverture complète du département.

## Étape 0 — Téléchargements (`10_download.py`, écrit)

Sources et URLs : voir `02-DATA-SOURCES.md`. Le script télécharge cadastre parcelles/bâtiments + BAN + BD TOPO 49, décompresse, convertit en GeoParquet dans `data/interim/`, et écrit `data/interim/millesimes.yaml`. La BD ORTHO se télécharge par lots au moment de la détection (étape 1b), pas ici.

## Étape 1a — Piscines OSM (développement uniquement)

```bash
# Télécharger l'extrait régional puis filtrer :
curl -LO https://download.geofabrik.de/europe/france/pays-de-la-loire-latest.osm.pbf
osmium tags-filter pays-de-la-loire-latest.osm.pbf w/leisure=swimming_pool -o piscines_osm.pbf
ogr2ogr -f Parquet data/interim/piscines_osm_dev.parquet piscines_osm.pbf multipolygons
```
Garder `access` (private/…) et `location` (écarter indoor). **Fichier marqué `_dev` : ne doit jamais alimenter `data/final/`** — le pipeline de jointure prend la source en paramètre `--source-piscines`, et `30_score_qualite.py` refuse d'écrire dans `final/` si la source contient `_dev` (garde-fou codé).

Usage secondaire : estimer le rappel de la détection (étape 1b) sur les communes où OSM est dense.

## Étape 1b — Détection sur BD ORTHO (le cœur de l'actif, à implémenter)

C'est l'étape qui fait la valeur (aucune base ouverte ne contient les piscines privées — cf. `02-DATA-SOURCES.md`). Problème classique et bien documenté ("swimming pool detection aerial imagery") : objet turquoise/bleu, géométrique, 8–150 m², dans les jardins.

**Spécification décidée :**

1. **Données** : dalles BD ORTHO 49 en RVB **+ IRC** (l'infrarouge élimine végétation et bâches vertes). Traiter par lots de dalles (dizaines de Go au total) ; ne traiter que les dalles intersectant des zones bâties (tuiles contenant des bâtiments BD TOPO — élimine ~60 % du territoire agricole).
2. **Approche modèle, dans l'ordre de préférence :**
   - **Option A (défaut)** : fine-tuner un modèle de segmentation léger (U-Net/DeepLabv3+ backbone ResNet, ou YOLOv8-seg) sur des tuiles 512×512. Il existe des poids/datasets publics de détection de piscines sur imagerie aérienne (chercher sur Hugging Face / Kaggle "swimming pool segmentation") — vérifier la licence des poids avant usage commercial.
   - **Option B (zéro entraînement, à essayer en premier tant que c'est bon marché)** : seuillage colorimétrique HSV (teinte cyan) + indice NDWI-like avec l'IRC + filtres morphologiques + filtres de forme (surface, compacité). Donne beaucoup de candidats avec faux positifs (bâches, trampolines bleus, bassins d'ornement) → suffisant si suivi d'une **passe de tri visuel humain assisté** (voir point 4). Pour un département, c'est viable : quelques milliers de candidats à trier à ~1 s/vignette.
   - Le choix A vs B se tranche empiriquement sur 2 communes tests : si B + tri humain donne précision ≥ 95 % pour < 1 jour de tri, B suffit pour le lancement ; A devient l'investissement d'industrialisation multi-départements.
3. **Étiquettes d'entraînement (option A)** : annoter manuellement 300–500 piscines sur des tuiles du 49 (2–4 h avec QGIS ou Label Studio). **Décision licence : ne PAS utiliser les polygones OSM comme masques d'entraînement** — le statut ODbL d'un modèle entraîné est juridiquement flou, et 3 h d'annotation manuelle éliminent le risque. (Si un jour on assume ce risque, le documenter ici.)
4. **Tri humain assisté** (quelle que soit l'option) : générer une planche de vignettes (crop ortho 60×60 m centré sur chaque détection) + interface de tri oui/non (une page HTML statique avec raccourcis clavier suffit — à générer). C'est ce qui garantit la précision ≥ 95 % vendable. Coût : ~2–4 h par tranche de 10 000 candidats.
5. **Sortie** : `data/interim/piscines_detectees_49.parquet` — polygones EPSG:2154, colonnes `surface_m2`, `score_detection`, `methode` (hsv/model/valide_humain).
6. **Test avant industrialisation** : tout au point sur UNE commune (`--commune 49XXX`), mesurer précision/rappel vs OSM + contrôle visuel, consigner dans ROADMAP, PUIS lancer le département.

## Étape 2 — Jointure piscine → adresse (`20_join_piscines_adresses.py`, écrit)

Stratégie décidée (et codée) :
1. **Piscine → parcelle** : `representative_point()` du polygone piscine dans la parcelle cadastre (point-on-surface, pas d'intersection → pas de doublons quand une piscine chevauche deux parcelles). Part de chevauchement < 60 % ⇒ flag `jointure_ambigue`.
2. **Parcelle → adresse** : d'abord l'index inverse BAN `cad_parcelles` (exploser le champ séparé par `|`, joindre sur l'identifiant 14 caractères). Fallback si vide : adresse BAN la plus proche **dans** la parcelle, sinon la plus proche à < 120 m dans la même commune (au-delà : confiance basse).
3. **Distance piscine ↔ bâtiment** le plus proche (BD TOPO `batiment`) : diagnostic pour les filtres de l'étape 3.

## Étape 3 — Qualité (`30_score_qualite.py`, écrit)

Applique les filtres de `06-QUALITE-VALIDATION.md` (surface 8–150 m², bâtiment < 60 m, exclusion bassins publics/campings via BD TOPO, dédoublonnage par `id_ban`, score de confiance). Écrit `data/final/piscines_qualifiees_49.parquet`. Refuse les sources `_dev`.

## Étape 4 — Vente (`35_stats_prospection.py` + `40_export_client.py`, écrits)

- `35_stats_prospection.py --centre "lat,lon" --rayon-km 30` : le chiffre à donner au téléphone ("j'en ai N autour de chez vous") sans générer de livrable.
- `40_export_client.py` : livrable complet (opt-out, tatouage, mentions légales, registre). Voir l'en-tête du script.
- `41_export_carte.py` (à écrire, simple) : PDF A4 carte des points sur fond de plan + compteur par commune, pour poser sur la table en RDV. matplotlib + contextily.

## Definition of done du produit 1

- [ ] Chaîne complète validée sur OSM/2 communes (étape 1a → 4 en `_dev`)
- [ ] Détection BD ORTHO au point sur 1 commune (précision/rappel mesurés, consignés)
- [ ] Détection département complet + tri humain
- [ ] Validation qualité `06` passée (≥ 95 % sur 100 adresses aléatoires)
- [ ] Checklist légale `03` §6 complète
- [ ] Premier extrait de démo généré pour le premier RDV
