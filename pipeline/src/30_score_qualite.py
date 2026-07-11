"""Filtres qualité + score de confiance → base commercialisable.

Règles définies dans docs/06-QUALITE-VALIDATION.md §3-4 ; seuils dans config.yaml.

Usage :
    python 30_score_qualite.py                    # lit piscines_adressees_{dept}.parquet
    python 30_score_qualite.py --dev              # variante _dev (OSM) — sortie en interim/, jamais en final/

Sortie : data/final/piscines_qualifiees_{dept}.parquet
         (ou data/interim/piscines_qualifiees_{dept}_dev.parquet en mode dev)
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np

from common import archiver_copie_datee, ensure_dirs, load_config

log = logging.getLogger("score")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dev", action="store_true", help="source OSM de développement (ODbL) — ne peut pas produire la base vendable")
    p.add_argument("--produit", default="piscines", help="section de config + préfixe de fichiers (défaut : piscines)")
    args = p.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    dept = cfg["dept"]
    produit = args.produit
    pc = cfg[produit]
    suffix = "_dev" if args.dev else ""

    src = Path(cfg["paths"]["interim"]) / f"{produit}_adressees_{dept}{suffix}.parquet"
    gdf = gpd.read_parquet(src)
    n0 = len(gdf)

    # --- Filtres d'exclusion (chaque compte est loggé : pas de perte silencieuse) ---
    def garder(mask, raison):
        nonlocal gdf
        avant = len(gdf)
        gdf = gdf[mask(gdf)]
        log.info("Filtre %-28s : -%d (reste %d)", raison, avant - len(gdf), len(gdf))

    garder(lambda g: g["surface_m2"].between(pc["surface_min_m2"], pc["surface_max_m2"]), "surface 8-150 m2")
    garder(lambda g: g["id_ban"].notna(), "adresse trouvée")
    garder(lambda g: g["dist_batiment_m"] <= pc["dist_max_batiment_m"], "bâtiment proche")

    # Exclusion des piscines collectives/publiques (campings, hôtels, équipements).
    excl_path = Path(cfg["paths"]["interim"]) / f"bdtopo_exclusions_{dept}.parquet"
    exclusions = gpd.read_parquet(excl_path)
    dans_zone = gdf.geometry.representative_point().within(exclusions.union_all())
    garder(lambda g: ~dans_zone.reindex(g.index, fill_value=False), "hors zones collectives")

    # --- Score de confiance (docs/06 §4) ---
    conf = np.select(
        [
            # haute : jointure cadastrale nette, adresse proche
            (~gdf["jointure_ambigue"]) & (gdf["source_jointure"] == "cad_parcelles") & (gdf["dist_adresse_m"] <= 60),
            # basse : jointure ambiguë OU adresse lointaine
            gdf["jointure_ambigue"] | (gdf["dist_adresse_m"] > pc["dist_max_adresse_m"] * 0.8),
        ],
        ["haute", "basse"],
        default="moyenne",
    )
    gdf["confiance"] = conf

    # --- Dédoublonnage : une adresse = une ligne (la plus grande piscine) ---
    gdf = gdf.sort_values("surface_m2", ascending=False).drop_duplicates(subset="id_ban", keep="first")
    log.info("Après dédoublonnage id_ban : %d lignes (%d au départ).", len(gdf), n0)
    log.info("Confiance : %s", gdf["confiance"].value_counts().to_dict())

    # Géométrie de sortie : le POINT ADRESSE (pas le polygone piscine — minimisation :
    # le client reçoit une adresse, pas le contour de la piscine du voisin).
    interim = Path(cfg["paths"]["interim"])
    # La BAN comporte quelques id_ban en doublon (0,02 % sur le 49 : même id, coords
    # voisines) → index non unique = plantage du .map() de géométrie. On garde la 1re.
    ban = gpd.read_parquet(interim / f"ban_{dept}.parquet").drop_duplicates("id_ban").set_index("id_ban")
    gdf = gdf.set_geometry(gdf["id_ban"].map(ban.geometry)).set_crs(cfg["crs_metric"])

    cols = ["id_ban", "adresse", "code_postal", "commune", "code_insee",
            "surface_m2", "dist_batiment_m", "dist_adresse_m", "confiance",
            "id_parcelle", "source_jointure", "geometry"]
    gdf = gdf[[c for c in cols if c in gdf.columns]]

    if args.dev:
        out = interim / f"{produit}_qualifiees_{dept}_dev.parquet"
    else:
        if "_dev" in src.name:  # ceinture + bretelles : garde-fou licence ODbL
            raise SystemExit("Source _dev détectée sans --dev : refus d'écrire dans final/.")
        out = Path(cfg["paths"]["final"]) / f"{produit}_qualifiees_{dept}.parquet"
    gdf.to_parquet(out)
    log.info("Écrit : %s (%d lignes)", out, len(gdf))
    if not args.dev:
        # Point-zéro des millésimes (moat n°2) : copie datée avant tout écrasement futur.
        archiver_copie_datee(out, produit, dept, cfg, log)
        log.warning("Rappel : validation qualité (docs/06) + checklist légale (docs/03 §6) "
                    "obligatoires avant toute démo ou vente.")


if __name__ == "__main__":
    main()
