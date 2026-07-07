"""Jointure spatiale : polygone piscine → parcelle cadastrale → adresse BAN.

Stratégie (justifiée dans docs/04-PIPELINE-PISCINES.md étape 2) :
  1. piscine → parcelle : point-on-surface dans la parcelle (pas d'intersection,
     évite les doublons quand une piscine chevauche deux parcelles) ;
     part de chevauchement < seuil ⇒ flag jointure_ambigue.
  2. parcelle → adresse : index inverse BAN `cad_parcelles` (identifiants 14 car.
     séparés par |) ; fallback : adresse BAN la plus proche dans la parcelle,
     sinon la plus proche à < dist_max_adresse_m dans la même commune.
  3. distance piscine ↔ bâtiment BD TOPO le plus proche (diagnostic pour 30_score).

Usage :
    python 20_join_piscines_adresses.py --source-piscines data/interim/piscines_osm_dev.parquet
    python 20_join_piscines_adresses.py --source-piscines data/interim/piscines_detectees_49.parquet
    (option --commune 49XXX pour tester sur une seule commune)

Sortie : data/interim/piscines_adressees_{dept}[_dev].parquet
Le suffixe _dev est propagé depuis la source : une source de dev ne peut pas
produire un fichier d'apparence production (garde-fou licence ODbL).
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from common import ensure_dirs, load_config

log = logging.getLogger("join")


def charger(cfg: dict, commune: str | None):
    interim = Path(cfg["paths"]["interim"])
    dept = cfg["dept"]
    parcelles = gpd.read_parquet(interim / f"parcelles_{dept}.parquet")
    ban = gpd.read_parquet(interim / f"ban_{dept}.parquet")
    batiments = gpd.read_parquet(interim / f"bdtopo_batiment_{dept}.parquet")
    if commune:
        parcelles = parcelles[parcelles["commune"] == commune]
        ban = ban[ban["code_insee"] == commune]
        batiments = batiments[batiments.intersects(parcelles.union_all())]
        log.info("Restriction commune %s : %d parcelles, %d adresses.", commune, len(parcelles), len(ban))
    return parcelles, ban, batiments


def joindre_parcelle(piscines: gpd.GeoDataFrame, parcelles: gpd.GeoDataFrame, seuil_chevauchement: float) -> gpd.GeoDataFrame:
    pts = piscines.copy()
    pts["pt"] = pts.geometry.representative_point()
    pts = pts.set_geometry("pt")
    joined = gpd.sjoin(pts, parcelles[["id", "geometry"]], how="left", predicate="within")
    joined = joined.rename(columns={"id": "id_parcelle"}).drop(columns=["index_right"], errors="ignore")
    joined = joined.set_geometry("geometry")

    # Part de la surface de la piscine réellement contenue dans la parcelle retenue.
    ok = joined["id_parcelle"].notna()
    parc_geo = parcelles.set_index("id").geometry
    inter = joined.loc[ok].apply(
        lambda r: r.geometry.intersection(parc_geo[r["id_parcelle"]]).area / max(r.geometry.area, 1e-9), axis=1
    )
    joined["part_dans_parcelle"] = np.nan
    joined.loc[ok, "part_dans_parcelle"] = inter
    joined["jointure_ambigue"] = ~ok | (joined["part_dans_parcelle"] < seuil_chevauchement)
    log.info("Piscines→parcelle : %d/%d jointes, %d ambiguës.",
             ok.sum(), len(joined), int(joined["jointure_ambigue"].sum()))
    return joined.drop(columns=["pt"])


def index_ban_par_parcelle(ban: gpd.GeoDataFrame) -> pd.DataFrame:
    b = ban[ban["cad_parcelles"].notna() & (ban["cad_parcelles"] != "")]
    idx = b.assign(id_parcelle=b["cad_parcelles"].str.split("|")).explode("id_parcelle")
    return idx[["id_parcelle", "id_ban"]]


def joindre_adresse(piscines: gpd.GeoDataFrame, ban: gpd.GeoDataFrame, parcelles: gpd.GeoDataFrame, cfg: dict) -> gpd.GeoDataFrame:
    dist_max = cfg["piscines"]["dist_max_adresse_m"]

    # Voie 1 : index inverse BAN cad_parcelles.
    idx = index_ban_par_parcelle(ban)
    out = piscines.merge(idx, on="id_parcelle", how="left")
    # Une parcelle peut porter plusieurs adresses : garder la plus proche de la piscine.
    ban_geo = ban.set_index("id_ban").geometry
    multi = out["id_ban"].notna()
    out["dist_adresse_m"] = np.nan
    if multi.any():
        out.loc[multi, "dist_adresse_m"] = out.loc[multi].apply(
            lambda r: r.geometry.distance(ban_geo[r["id_ban"]]), axis=1
        )
    out = (out.sort_values("dist_adresse_m", na_position="last")
              .drop_duplicates(subset="id_piscine", keep="first")
              .set_index("id_piscine", drop=False).sort_index())
    out = gpd.GeoDataFrame(out, geometry="geometry", crs=piscines.crs)
    out["source_jointure"] = np.where(out["id_ban"].notna(), "cad_parcelles", None)

    # Voie 2 (fallback) : plus proche adresse dans un rayon, même commune.
    manquants = out["id_ban"].isna()
    if manquants.any():
        cand = out.loc[manquants].sjoin_nearest(
            ban[["id_ban", "code_insee", "geometry"]].rename(columns={"id_ban": "id_ban_n", "code_insee": "insee_n"}),
            how="left", max_distance=dist_max, distance_col="dist_n",
        )
        cand = cand[~cand.index.duplicated(keep="first")]
        out.loc[manquants, "id_ban"] = cand["id_ban_n"]
        out.loc[manquants, "dist_adresse_m"] = cand["dist_n"]
        out.loc[manquants & out["id_ban"].notna(), "source_jointure"] = "nearest"

    trouve = out["id_ban"].notna()
    log.info("Piscines→adresse : %d/%d (dont %d via cad_parcelles).",
             trouve.sum(), len(out), (out["source_jointure"] == "cad_parcelles").sum())
    # Les piscines sans adresse sont conservées avec id_ban NaN : 30_score les
    # classera basse confiance / exclusion — on ne perd pas silencieusement de données.

    # Attributs d'adresse pour le livrable.
    attrs = ban.set_index("id_ban")[["numero", "rep", "nom_voie", "code_postal", "nom_commune", "code_insee"]]
    out = out.join(attrs, on="id_ban")
    out["adresse"] = (
        out["numero"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
        + " " + out["rep"].fillna("") + " " + out["nom_voie"].fillna("")
    ).str.replace(r"\s+", " ", regex=True).str.strip()
    return out.rename(columns={"nom_commune": "commune"})


def dist_batiment(piscines: gpd.GeoDataFrame, batiments: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    near = piscines.sjoin_nearest(batiments[["geometry"]], how="left", distance_col="dist_batiment_m")
    return near[~near.index.duplicated(keep="first")].drop(columns=["index_right"], errors="ignore")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-piscines", required=True)
    p.add_argument("--commune", help="code INSEE pour un run de test sur une commune")
    args = p.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    dev = "_dev" in Path(args.source_piscines).name

    piscines = gpd.read_parquet(args.source_piscines).to_crs(cfg["crs_metric"])
    piscines = piscines[piscines.geometry.notna() & ~piscines.geometry.is_empty].reset_index(drop=True)
    piscines["id_piscine"] = piscines.index
    piscines["surface_m2"] = piscines.geometry.area.round(1)
    log.info("Source %s : %d polygones piscine.", args.source_piscines, len(piscines))

    parcelles, ban, batiments = charger(cfg, args.commune)
    if args.commune:
        piscines = piscines[piscines.intersects(parcelles.union_all())].reset_index(drop=True)

    piscines = joindre_parcelle(piscines, parcelles, cfg["piscines"]["chevauchement_parcelle_min"])
    piscines = joindre_adresse(piscines, ban, parcelles, cfg)
    piscines = dist_batiment(piscines, batiments)

    suffix = "_dev" if dev else ""
    out = Path(cfg["paths"]["interim"]) / f"piscines_adressees_{cfg['dept']}{suffix}.parquet"
    piscines.to_parquet(out)
    log.info("Écrit : %s (%d lignes)", out, len(piscines))


if __name__ == "__main__":
    main()
