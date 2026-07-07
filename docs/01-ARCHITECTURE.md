# Architecture technique

## Principes

1. **Open data uniquement pour le socle** — licences compatibles revente (Licence Ouverte 2.0), zéro coût de données, zéro dépendance à un fournisseur qui peut couper l'accès ou interdire l'usage (cf. verdict Google Solar API dans `05-PIPELINE-TERRASSES.md`).
2. **Un pipeline batch simple, pas une plateforme.** Des scripts Python numérotés, relançables, un répertoire `data/` local. Pas de base de données serveur, pas de SaaS, pas d'orchestrateur : le volume (un département) tient sur un laptop.
3. **Paramétré par département** : `--dept 49` aujourd'hui, 44/85/37 demain sans toucher au code.
4. **La donnée ne rentre jamais dans git.** Le repo = code + config + docs. L'actif commercial (`data/final/`) et le registre des ventes (`sales/`) restent locaux et sauvegardés à part (voir §Sauvegarde).

## Vue d'ensemble

```
                     SOURCES OPEN DATA (Licence Ouverte 2.0)
   ┌──────────────┬──────────────┬─────────────────┬──────────┬──────────────────┐
   │ IGN BD ORTHO │ IGN BD TOPO  │ Cadastre Etalab │   BAN    │ IGN LiDAR HD MNS │
   │ (orthophoto  │ (bâtiments,  │ (parcelles)     │(adresses)│ (produit 2 uniq.)│
   │  20 cm)      │  exclusions) │                 │          │                  │
   └──────┬───────┴──────┬───────┴────────┬────────┴────┬─────┴────────┬─────────┘
          ▼              ▼                ▼             ▼              ▼
   10_download.py   (téléchargement + décompression + millesimes.yaml)
          │
          ▼
   15_detect_piscines.py  ← segmentation sur orthophoto (voir 04-PIPELINE-PISCINES.md)
          │  polygones piscines + score de détection
          ▼
   20_join_piscines_adresses.py        [produit 2 : 2x_score_soleil.py]
   piscine → parcelle → bâtiment → adresse BAN
          │
          ▼
   30_score_qualite.py
   filtres surface / distance / collectif / dédoublonnage / score confiance
          │
          ▼
   data/final/piscines_qualifiees_49.parquet     ← L'ACTIF
          │
          ├── 35_stats_prospection.py  → chiffres par zone pour les appels de vente
          ├── 40_export_client.py      → CSV livrable (opt-out, tatouage, sources)
          └── 41_export_carte.py       → PDF carte pour le RDV (à écrire)
```

## Formats & conventions

- **Interne** : GeoParquet (`data/interim/`, `data/final/`) — rapide, typé, geopandas natif.
- **Livrable client** : CSV UTF-8-BOM (Excel-proof) + PDF carte. Jamais le parquet interne.
- **CRS** : calculs en EPSG:2154 (Lambert-93), sorties lat/lon EPSG:4326.
- **Clé d'adresse** : `id_ban` (identifiant BAN) — clé du dédoublonnage, de l'opt-out et des diffs de millésimes.
- **Millésimes** : `10_download.py` écrit `data/interim/millesimes.yaml` ; l'export le lit et l'embarque. Chaîne de traçabilité complète : source → millésime → version pipeline (`git describe`) → fichier livré.

## Schéma de la base finale (`piscines_qualifiees_{dept}.parquet`)

| colonne | type | note |
|---|---|---|
| `id_ban` | str | clé BAN |
| `adresse` | str | numéro + voie normalisés |
| `code_postal`, `commune`, `code_insee` | str | |
| `geometry` | Point (2154) | point d'adresse BAN |
| `surface_m2` | float | surface du polygone piscine |
| `dist_batiment_m`, `dist_adresse_m` | float | diagnostics de jointure |
| `confiance` | str | `haute` / `moyenne` / `basse` (voir 06) |
| `id_parcelle` | str | traçabilité interne, ne sort jamais dans les exports |

Colonnes livrées au client : liste blanche `COLONNES_LIVREES` dans `40_export_client.py` — tout ajout se décide là, jamais par accident.

## Environnement d'exécution

- Python ≥ 3.10, `pip install -r pipeline/requirements.txt`. Sous Debian/Ubuntu, GDAL est fourni par les wheels pyogrio/geopandas — pas d'installation système nécessaire dans le cas nominal.
- Volumétrie produit 1 : BD TOPO 49 ~1–2 Go, cadastre 49 ~1 Go, BAN 49 ~30 Mo. Un laptop suffit.
- Volumétrie produit 2 : dalles MNS 0,5 m ciblées par communes — dizaines de Go. Prévoir un disque externe ou un traitement par lots avec purge.

## Sauvegarde de l'actif

`data/final/`, `data/optout/`, `sales/` sont hors git mais sont **le business**. Règle : après chaque run réussi et après chaque vente, copie chiffrée vers un stockage personnel (disque externe + cloud privé). Ne jamais les mettre dans un repo, même privé (le repo peut être partagé/cloné pour du dev).
