# Pipeline

Scripts numérotés = ordre d'exécution. Guides détaillés : `docs/04-PIPELINE-PISCINES.md` (et `05` pour le produit 2).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r pipeline/requirements.txt

cd pipeline/src
python 10_download.py                       # cadastre + BAN + BD TOPO 49
# piscines OSM (dev) : voir docs/04 étape 1a
python 20_join_piscines_adresses.py --source-piscines ../../data/interim/piscines_osm_dev.parquet --commune 49XXX
python 30_score_qualite.py --dev
python 35_stats_prospection.py --dev --centre "47.4712,-0.5518" --rayon-km 30
# production : 15_detect_piscines.py (à implémenter, spec docs/04 étape 1b) puis mêmes étapes sans --dev
python 40_export_client.py --produit piscines --acheteur "EXEMPLE SARL" --centre "47.4712,-0.5518"
```

Garde-fous codés (ne pas contourner — voir CLAUDE.md) :
- filtre opt-out systématique sur stats et exports (`common.apply_optout`) ;
- sources `_dev` (OSM/ODbL) ne peuvent pas produire la base vendable ;
- exports : liste blanche de colonnes, mention de source/millésimes, tatouage acheteur, registre des ventes.
