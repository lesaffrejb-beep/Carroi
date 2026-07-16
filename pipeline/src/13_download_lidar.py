"""Téléchargement ciblé des dalles LiDAR HD dérivées (MNS / MNH) pour une commune.

Le département fait ~7 100 dalles d'1 km² : on ne télécharge JAMAIS tout
(docs/05 §étape 1). Ciblage : bbox des parcelles de la commune + marge égale à
la portée d'ombre (150 m, docs/05), interrogée sur les tableaux d'assemblage WFS
de la Géoplateforme (couches IGNF_MNS-LIDAR-HD:dalle / IGNF_MNH-LIDAR-HD:dalle),
qui renvoient pour chaque dalle l'URL GeoTIFF 0,5 m prête à télécharger.

Usage :
    python 13_download_lidar.py --commune 49035 [--produits mns,mnh] [--marge 150]

Sortie : data/raw/lidar/{mns,mnh}/LHD_FXX_xxxx_yyyy_*.tif
Idempotent : une dalle déjà présente (taille > 0) n'est pas retéléchargée.
Consigner le millésime dans data/interim/millesimes.yaml après un run complet
(clé lidar_{produit}) — le LiDAR 49 date de ~2021-2024, voir docs/05 §risques.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import requests

from common import ensure_dirs, load_config

log = logging.getLogger("lidar")

WFS = "https://data.geopf.fr/wfs/ows"
COUCHES = {"mns": "IGNF_MNS-LIDAR-HD:dalle", "mnh": "IGNF_MNH-LIDAR-HD:dalle"}


def bbox_commune(parcelles: gpd.GeoDataFrame, commune: str, marge_m: float) -> tuple:
    """Bbox Lambert-93 des parcelles de la commune, gonflée de marge_m (portée
    d'ombre : un immeuble hors commune ombrage un jardin dedans). Pure."""
    sel = parcelles[parcelles["commune"].astype(str) == str(commune)]
    if sel.empty:
        raise SystemExit(f"Aucune parcelle pour la commune {commune}.")
    minx, miny, maxx, maxy = sel.total_bounds
    return (minx - marge_m, miny - marge_m, maxx + marge_m, maxy + marge_m)


def dalles_wfs(couche: str, bbox: tuple) -> list[dict]:
    """Interroge le tableau d'assemblage : liste de {name_download, url}."""
    params = {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "TYPENAMES": couche, "outputFormat": "json", "COUNT": "1000",
        "BBOX": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},urn:ogc:def:crs:EPSG::2154",
    }
    r = requests.get(WFS, params=params, timeout=120)
    r.raise_for_status()
    feats = r.json().get("features", [])
    log.info("%s : %d dalle(s) sur l'emprise.", couche, len(feats))
    return [f["properties"] for f in feats]


def telecharger(props: dict, dest_dir: Path) -> bool:
    """Télécharge une dalle si absente. True = téléchargée, False = déjà là."""
    dest = dest_dir / props["name_download"]
    if dest.exists() and dest.stat().st_size > 0:
        return False
    tmp = dest.with_suffix(".part")
    with requests.get(props["url"], stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for bloc in r.iter_content(1 << 20):
                f.write(bloc)
    tmp.rename(dest)   # atomique : jamais de .tif tronqué sous le nom final
    log.info("  %s (%.1f Mo)", dest.name, dest.stat().st_size / 1e6)
    return True


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--commune", required=True, help="code INSEE (ex. 49035)")
    p.add_argument("--produits", default="mns,mnh",
                   help="produits à télécharger, parmi mns,mnh (défaut : les deux)")
    p.add_argument("--marge", type=float, default=150.0,
                   help="marge autour de la commune en mètres (portée d'ombre)")
    args = p.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    interim = Path(cfg["paths"]["interim"])
    parcelles = gpd.read_parquet(interim / f"parcelles_{cfg['dept']}.parquet",
                                 columns=["commune", "geometry"])
    bbox = bbox_commune(parcelles, args.commune, args.marge)
    log.info("Emprise %s + %g m : %s", args.commune, args.marge,
             tuple(round(v) for v in bbox))

    for produit in [s.strip() for s in args.produits.split(",")]:
        if produit not in COUCHES:
            raise SystemExit(f"Produit inconnu : {produit} (attendu {sorted(COUCHES)}).")
        dest_dir = Path(cfg["paths"]["raw"]) / "lidar" / produit
        dest_dir.mkdir(parents=True, exist_ok=True)
        dalles = dalles_wfs(COUCHES[produit], bbox)
        nouvelles = sum(telecharger(pr, dest_dir) for pr in dalles)
        log.info("%s : %d dalle(s), %d téléchargée(s), %d déjà présentes → %s",
                 produit.upper(), len(dalles), nouvelles, len(dalles) - nouvelles, dest_dir)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
