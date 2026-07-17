"""Adresses des zones terrasses — chaînon 25 → Atelier niveau 2 / 30_score.

Les zones terrasses sortent de 25_terrasses avec leur `id_parcelle` : la
jointure adresse est donc la même que pour les piscines (parcelle → BAN via
l'index cad_parcelles, fallback proximité). On RÉUTILISE joindre_adresse de
20_join (fonction éprouvée, corroboration A4 incluse) au lieu de la réécrire.

Usage :
    python 26_terrasses_adresses.py   # lit terrasses_a_farmer_49_49035.parquet

Sortie : data/interim/terrasses_adressees_49.parquet (contrat identique aux
piscines adressées : id_detection, id_piscine*, id_ban, adresse, id_parcelle,
source_jointure, adresse_dans_parcelle…) — consommé par l'Atelier (niveau 2)
et, à terme, 30_score --produit terrasses.

*id_piscine : nom de colonne générique hérité du contrat (identifiant d'item).
"""
from __future__ import annotations

import importlib
import logging
from pathlib import Path

import geopandas as gpd

from common import ensure_dirs, load_config

j20 = importlib.import_module("20_join_piscines_adresses")
log = logging.getLogger("terr_adr")


def main() -> None:
    cfg = load_config()
    ensure_dirs(cfg)
    interim = Path(cfg["paths"]["interim"])
    dept = cfg["dept"]

    zones = gpd.read_parquet(interim / f"terrasses_a_farmer_{dept}_49035.parquet")
    zones = zones.reset_index(drop=True)
    zones["id_piscine"] = zones.index.astype(str)     # contrat générique d'item
    ban = gpd.read_parquet(interim / f"ban_{dept}.parquet").to_crs(cfg["crs_metric"])
    parcelles = gpd.read_parquet(interim / f"parcelles_{dept}.parquet").to_crs(cfg["crs_metric"])
    log.info("%d zones, %d adresses BAN, %d parcelles.", len(zones), len(ban), len(parcelles))

    out = j20.joindre_adresse(zones, ban, parcelles, cfg)
    dest = interim / f"terrasses_adressees_{dept}.parquet"
    out.to_parquet(dest)
    n_adr = out["id_ban"].notna().sum()
    log.info("Écrit : %s (%d/%d adressées, %d via cad_parcelles).", dest, n_adr,
             len(out), (out["source_jointure"] == "cad_parcelles").sum())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
