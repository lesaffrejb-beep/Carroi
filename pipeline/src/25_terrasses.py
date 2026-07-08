"""Détecteur produit 2 — terrasses/jardins ensoleillés sur MNS LiDAR HD (couche 1 du moteur).

Orchestration par dalles autour des cœurs purs `solaire.py` (heures de soleil,
ombres portées) et `terrasses.py` (zones jardin, classification). Spec docs/05.

Pour chaque dalle MNS 0,5 m :
  1. mosaïque la dalle + ses voisines sur une marge = portée d'ombre (150 m) :
     sans ça, l'immeuble ou le bois situé dans la dalle d'à côté n'ombrage pas ;
  2. calcule les rasters d'heures de soleil direct aux 3 dates (solaire.py) —
     UNE fois par dalle, partagé par toutes les parcelles ;
  3. pour chaque parcelle bâtie dont le point représentatif est dans la dalle :
     zone jardin (parcelle − bâti, ≤ 15 m de la façade), masque au sol via le
     MNH (la cime d'un arbre ensoleillé n'est PAS une terrasse), classification
     plein_soleil / bon / ombrage sur surface contiguë.

Usage :
    python 25_terrasses.py --mns-dir data/raw/lidar/mns [--mnh-dir data/raw/lidar/mnh]
        [--commune 49XXX] [--limit-dalles N]

Sortie : data/interim/terrasses_candidates_{dept}[_{commune}].parquet
Contrat couche 1 (docs/09 §2) : geometry, surface_m2, score_detection, methode
+ attributs produit : classe_soleil, surface_plein_soleil_m2, heures_soleil_juin,
heures_soleil_equinoxe, orientation_deg, secteur, id_parcelle.
Les zones `ombrage` sont CONSERVÉES ici (utile au diagnostic) mais exclues de la
vente en aval (docs/05 §4) — le filtre est dans la couche qualité, pas ici.

Coût : ~5-10 min/dalle en Python pur (36 échantillons solaires × portée 300 px).
Optimisation identifiée si besoin [OPUS] : calculer les ombres sur MNS
sous-échantillonné à 1 m (4× moins de pixels, 2× moins de pas) et réappliquer
le masque à 0,5 m — à valider contre la version exacte sur une commune.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.merge import merge as rio_merge
from shapely.geometry import box

import solaire
import terrasses
from common import ensure_dirs, load_config
from contrat import ids_stables, valider_couche1

log = logging.getLogger("terrasses25")

EXTENSIONS = (".tif", ".tiff", ".asc", ".jp2")


def lister_dalles(dossier: Path) -> list[Path]:
    dalles = sorted(p for p in dossier.iterdir() if p.suffix.lower() in EXTENSIONS)
    if not dalles:
        raise SystemExit(f"Aucune dalle MNS dans {dossier}.")
    return dalles


def indexer_bounds(paths: list[Path]) -> list[tuple[tuple, Path]]:
    index = []
    for p in paths:
        with rasterio.open(p) as src:
            index.append((tuple(src.bounds), p))
    return index


def mosaique(index: list[tuple[tuple, Path]], bounds: tuple, marge_m: float):
    """Mosaïque des dalles intersectant bounds élargi de marge_m (ombres des voisins).

    Retourne (array 2D float, transform, res_m)."""
    cible = box(bounds[0] - marge_m, bounds[1] - marge_m, bounds[2] + marge_m, bounds[3] + marge_m)
    chemins = [p for b, p in index if box(*b).intersects(cible)]
    sources = [rasterio.open(p) for p in chemins]
    try:
        arr, transform = rio_merge(sources, bounds=cible.bounds)
    finally:
        for s in sources:
            s.close()
    res = abs(transform.a)
    return arr[0].astype(np.float64), transform, res


def latitude_de(bounds: tuple, crs) -> float:
    t = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    _, lat = t.transform((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
    return float(lat)


def charger_vecteurs(cfg: dict, commune: str | None):
    interim = Path(cfg["paths"]["interim"])
    dept = cfg["dept"]
    parcelles = gpd.read_parquet(interim / f"parcelles_{dept}.parquet")
    if commune:
        parcelles = parcelles[parcelles["commune"] == commune]
        if parcelles.empty:
            raise SystemExit(f"Commune {commune} introuvable.")
    bat_path = interim / f"bdtopo_batiment_{dept}.parquet"
    if not bat_path.exists():
        raise SystemExit(f"{bat_path} manquant — lancer 10_download.py d'abord.")
    batiments = gpd.read_parquet(bat_path)
    return parcelles, batiments


def traiter_dalle(
    dalle_bounds: tuple,
    index_mns,
    index_mnh,
    parcelles: gpd.GeoDataFrame,
    pts_parcelles_sidx,
    batiments: gpd.GeoDataFrame,
    cfg_t: dict,
    crs,
) -> list[dict]:
    emprise = box(*dalle_bounds)
    # Index spatial des points représentatifs (construit UNE fois dans main) :
    # le scan linéaire coûterait dalles × parcelles (7 100 × 400 000 au département).
    dans_dalle = parcelles.iloc[pts_parcelles_sidx.query(emprise, predicate="contains")]
    if dans_dalle.empty:
        return []

    t0 = time.monotonic()
    mns, transform, res = mosaique(index_mns, dalle_bounds, cfg_t["portee_ombre_m"])
    if not (0.2 <= res <= 2.0):
        raise SystemExit(f"Résolution MNS {res} m/px inattendue (LiDAR HD dérivé = 0,5 m).")
    mnh = None
    if index_mnh:
        mnh, t_mnh, res_mnh = mosaique(index_mnh, dalle_bounds, cfg_t["portee_ombre_m"])
        if mnh.shape != mns.shape or abs(res_mnh - res) > 1e-6:
            raise SystemExit("Grilles MNS/MNH incohérentes — vérifier les dalles téléchargées.")

    lat = latitude_de(dalle_bounds, crs)
    h_juin = solaire.heures_soleil_jour(
        mns, res, lat, solaire.JOUR_SOLSTICE_ETE,
        pas_minutes=cfg_t["pas_minutes"], portee_m=cfg_t["portee_ombre_m"])
    h_eq = solaire.heures_soleil_jour(
        mns, res, lat, solaire.JOUR_EQUINOXE,
        pas_minutes=cfg_t["pas_minutes"], portee_m=cfg_t["portee_ombre_m"])
    log.info("Rasters solaires calculés en %.0f s (%s px).", time.monotonic() - t0, mns.shape)

    bat_sidx = batiments.sindex
    lignes = []
    n_sans_bati = n_sans_zone = 0
    for _, parc in dans_dalle.iterrows():
        voisins = batiments.iloc[bat_sidx.query(parc.geometry, predicate="intersects")]
        if voisins.empty:
            n_sans_bati += 1
            continue
        zone = terrasses.zone_jardin(
            parc.geometry, list(voisins.geometry),
            cfg_t["dist_facade_m"], cfg_t["tampon_limite_m"], cfg_t["surface_zone_min_m2"])
        if zone is None:
            n_sans_zone += 1
            continue
        masque = terrasses.rasteriser_zone(zone, transform, mns.shape)
        masque = terrasses.masque_sol(masque, mnh, cfg_t["hauteur_sol_max_m"])
        res_classif = terrasses.classifier_soleil(h_juin, h_eq, masque, res, cfg_t)
        az, secteur = terrasses.orientation_zone(
            zone, voisins.geometry.union_all() if len(voisins) > 1 else voisins.geometry.iloc[0])
        lignes.append({
            "geometry": zone,
            "surface_m2": round(zone.area, 1),
            "methode": "mns_solaire" if mnh is not None else "mns_solaire_sans_mnh",
            "orientation_deg": az,
            "secteur": secteur,
            "id_parcelle": parc.get("id"),
            **res_classif,
        })
    log.info("Dalle : %d parcelles (%d sans bâti, %d sans zone jardin) → %d zones.",
             len(dans_dalle), n_sans_bati, n_sans_zone, len(lignes))
    return lignes


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mns-dir", required=True, help="dalles MNS LiDAR HD (GeoTIFF 0,5 m)")
    p.add_argument("--mnh-dir", help="dalles MNH (hauteur de sursol) — fortement recommandé")
    p.add_argument("--commune", help="code INSEE pour un run de test")
    p.add_argument("--limit-dalles", type=int)
    args = p.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    cfg_t = cfg["terrasses"]
    if not args.mnh_dir:
        log.warning("Pas de MNH : la canopée ensoleillée des jardins arborés comptera "
                    "à tort comme terrasse — précision dégradée, tri humain plus long.")

    dalles = lister_dalles(Path(args.mns_dir))
    if args.limit_dalles:
        dalles = dalles[: args.limit_dalles]
    index_mns = indexer_bounds(dalles)
    index_mnh = indexer_bounds(lister_dalles(Path(args.mnh_dir))) if args.mnh_dir else []
    parcelles, batiments = charger_vecteurs(cfg, args.commune)
    pts_parcelles = parcelles.geometry.representative_point()
    pts_parcelles_sidx = pts_parcelles.sindex

    with rasterio.open(dalles[0]) as src:
        crs = src.crs

    lignes: list[dict] = []
    for i, (bounds, path) in enumerate(index_mns, 1):
        log.info("[%d/%d] %s", i, len(index_mns), path.name)
        lignes.extend(traiter_dalle(bounds, index_mns, index_mnh, parcelles,
                                    pts_parcelles_sidx, batiments, cfg_t, crs))

    if not lignes:
        raise SystemExit("0 zone jardin produite — mauvaises dalles, mauvaise commune, "
                         "ou parcelles/bâtiments manquants ?")
    gdf = gpd.GeoDataFrame(lignes, geometry="geometry", crs=cfg["crs_metric"])
    gdf["id_detection"] = ids_stables(gdf, "terr")
    suffix = f"_{args.commune}" if args.commune else ""
    out = Path(cfg["paths"]["interim"]) / f"terrasses_candidates_{cfg['dept']}{suffix}.parquet"
    valider_couche1(gdf, cfg["crs_metric"])
    gdf.to_parquet(out)
    log.info("Écrit : %s (%d zones ; classes : %s).", out, len(gdf),
             gdf["classe_soleil"].value_counts().to_dict())


if __name__ == "__main__":
    main()
