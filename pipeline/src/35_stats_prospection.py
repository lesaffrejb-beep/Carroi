"""Chiffres pour les appels de vente — sans générer de livrable.

Donne le nombre d'adresses vendables autour d'un point (ex. l'entreprise du
prospect qu'on s'apprête à appeler) et le top des communes.

Usage :
    python 35_stats_prospection.py --centre "47.4712,-0.5518" --rayon-km 30
    python 35_stats_prospection.py --dept
    (--dev pour utiliser la base de développement OSM)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd

from common import apply_optout, load_config
import logging

log = logging.getLogger("stats")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--centre", help='"lat,lon"')
    p.add_argument("--rayon-km", type=float, default=None)
    p.add_argument("--dept", action="store_true")
    p.add_argument("--dev", action="store_true")
    args = p.parse_args()
    if not args.centre and not args.dept:
        p.error("--centre ou --dept requis")

    cfg = load_config()
    if args.dev:
        base = Path(cfg["paths"]["interim"]) / f"piscines_qualifiees_{cfg['dept']}_dev.parquet"
    else:
        base = Path(cfg["paths"]["final"]) / f"piscines_qualifiees_{cfg['dept']}.parquet"
    gdf = gpd.read_parquet(base)
    gdf = gdf[gdf["confiance"].isin(cfg["export"]["confiances_vendues"])]
    gdf = apply_optout(gdf, cfg, log)

    if args.centre:
        rayon = args.rayon_km or cfg["export"]["rayon_defaut_km"]
        lat, lon = (float(x) for x in args.centre.split(","))
        centre = gpd.GeoSeries.from_xy([lon], [lat], crs=cfg["crs_output"]).to_crs(cfg["crs_metric"])[0]
        gdf = gdf[gdf.to_crs(cfg["crs_metric"]).geometry.distance(centre) <= rayon * 1000]
        print(f"\n=== {len(gdf)} adresses vendables dans un rayon de {rayon:g} km ===\n")
    else:
        print(f"\n=== {len(gdf)} adresses vendables dans le département {cfg['dept']} ===\n")

    print("Top 15 communes :")
    print(gdf.groupby("commune").size().sort_values(ascending=False).head(15).to_string())
    print("\nRépartition confiance :", gdf["confiance"].value_counts().to_dict())


if __name__ == "__main__":
    main()
