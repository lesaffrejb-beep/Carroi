"""Signalements humains (« je vois une piscine ailleurs ») → nouveaux candidats.

Pendant qu'il vote sur la zone rouge, un farmer voit souvent une piscine que
NOTRE source de candidats a ratée. La touche F enregistre un point Lambert-93
(table `signalements` de l'Atelier). Ce module transforme ces points en
candidats farmables — c'est du RAPPEL gratuit, produit par l'œil humain là où
CoSIA et le cadastre sont aveugles (piscines couvertes, bâchées, à l'ombre).

Chaîne de décision par point (dans cet ordre, le premier qui répond gagne) :

  1. **déjà candidat** — le point tombe dans (ou à < 3 m d') un candidat
     existant : le farmer a signalé une zone déjà en file. Rien à créer, on
     compte et on log (signal d'UX, pas de donnée).
  2. **CoSIA récupérable** — un polygone CoSIA classe Piscine existe sous le
     point mais avait été écarté (surface hors bornes, ou hors AOI communale
     parce qu'à cheval sur une frontière) : on le RÉCUPÈRE avec sa vraie
     géométrie. C'est le meilleur cas — géométrie fiable + confirmation humaine.
  3. **point nu** — personne d'autre ne voit rien : on crée un disque de
     rayon `RAYON_DEFAUT_M` centré sur le clic. La géométrie est approximative
     et le dit (`methode="signale_humain"`), mais elle suffit à générer une
     vignette et à faire voter — la vérité viendra du vote, pas du disque.

Le résultat passe le contrat de couche 1 et sort dans un parquet de candidats
ordinaire, mélangeable à la file (`--fusionner-dans`).

Usage :
    python 26_signalements_candidats.py --cosia-dir "/Volumes/…/COSIA_…"
    python 26_signalements_candidats.py --fusionner-dans \\
        data/interim/piscines_candidates_49_alm.parquet
"""
from __future__ import annotations

import argparse
import logging
import math
import sqlite3
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from common import load_config
from contrat import ids_stables, valider_couche1

log = logging.getLogger("signalements")

# Deux clics à moins de ça = le même signalement (un farmer re-clique pour
# ajuster ; mesuré chez Azan : 162 clics bruts pour 60 intentions).
FUSION_CLICS_M = 10.0
# Le point tombe sur un candidat déjà en file → rien de neuf.
PROCHE_CANDIDAT_M = 3.0
# Rayon du disque quand aucune géométrie n'est récupérable. ~20 m², l'ordre de
# grandeur d'une piscine de particulier ; ce n'est PAS une mesure, juste une
# cible à faire voter.
RAYON_DEFAUT_M = 2.5
# Distance max pour récupérer un polygone CoSIA sous le point.
RECUP_COSIA_M = 6.0

SCORE_SIGNALE = 0.7        # confiance humaine, géométrie approximative
SCORE_RECUPERE = 0.95      # CoSIA + confirmation humaine : le meilleur des deux


# --------------------------------------------------------------------------
# Fonctions pures
# --------------------------------------------------------------------------

def fusionner_clics(points: list[tuple[str, float, float]],
                    seuil_m: float = FUSION_CLICS_M) -> list[tuple[str, float, float]]:
    """Déduplique les clics : deux points du MÊME item à moins de `seuil_m`
    sont une seule intention (on garde le premier). Pure et déterministe —
    l'ordre d'entrée (chronologique) fait foi."""
    gardes: list[tuple[str, float, float]] = []
    for item, x, y in points:
        if any(i == item and math.dist((x, y), (gx, gy)) < seuil_m
               for i, gx, gy in gardes):
            continue
        gardes.append((item, x, y))
    return gardes


def attributs_forme(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """surface_m2 / compacite / solidite — mêmes définitions que 24."""
    a = gdf.geometry.area
    p = gdf.geometry.length
    gdf["surface_m2"] = a
    gdf["compacite"] = (4 * math.pi * a / (p * p)).where(p > 0, 0.0)
    gdf["solidite"] = (a / gdf.geometry.convex_hull.area).clip(upper=1.0)
    return gdf


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------

def lire_signalements(db: Path, produit: str = "piscines") -> list[tuple[str, float, float]]:
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT id_item, x_l93, y_l93 FROM signalements WHERE produit=? "
        "ORDER BY rowid", (produit,)).fetchall()
    conn.close()
    return [(str(i), float(x), float(y)) for i, x, y in rows]


def candidats_existants(interim: Path, dept: str) -> gpd.GeoDataFrame:
    """Union de TOUS les parquets de candidats connus — un signalement déjà
    couvert par n'importe quelle commune ne doit pas être recréé."""
    frames = []
    for p in sorted(interim.glob(f"piscines_candidates_{dept}_*.parquet")):
        frames.append(gpd.read_parquet(p, columns=["id_detection", "geometry"]))
    if not frames:
        return gpd.GeoDataFrame(columns=["id_detection", "geometry"], crs="EPSG:2154")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)


def recuperer_cosia(cosia_dir: Path, points: list[tuple[str, float, float]],
                    crs: str) -> gpd.GeoDataFrame:
    """Polygones CoSIA classe Piscine sous les points signalés (tous blocs
    confondus, sans filtre de surface ni d'AOI : on cherche justement ce que
    les filtres avaient écarté)."""
    import importlib
    m24 = importlib.import_module("24_candidats_cosia")
    import pyogrio
    from shapely.geometry import box

    if not points:
        return gpd.GeoDataFrame(columns=["geometry"], crs=crs)
    enveloppe = box(min(x for _, x, _ in points) - RECUP_COSIA_M,
                    min(y for _, _, y in points) - RECUP_COSIA_M,
                    max(x for _, x, _ in points) + RECUP_COSIA_M,
                    max(y for _, _, y in points) + RECUP_COSIA_M)
    frames = []
    for bloc in m24.blocs_pour_aoi(cosia_dir, enveloppe):
        g = pyogrio.read_dataframe(bloc, where="classe = 'Piscine'",
                                   bbox=tuple(enveloppe.bounds))
        if not g.empty:
            frames.append(g[["geometry"]])
    if not frames:
        return gpd.GeoDataFrame(columns=["geometry"], crs=crs)
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=crs)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def construire(points: list[tuple[str, float, float]],
               deja: gpd.GeoDataFrame, cosia: gpd.GeoDataFrame,
               parcelles: gpd.GeoDataFrame, crs: str) -> tuple[gpd.GeoDataFrame, dict]:
    """Applique la chaîne de décision. Retourne (candidats, compteurs)."""
    s_deja = deja.sindex if not deja.empty else None
    s_cosia = cosia.sindex if not cosia.empty else None
    geoms, methodes, scores = [], [], []
    stats = {"deja_candidat": 0, "recupere_cosia": 0, "point_nu": 0}

    for _, x, y in points:
        pt = Point(x, y)
        if s_deja is not None and len(s_deja.query(pt.buffer(PROCHE_CANDIDAT_M),
                                                   predicate="intersects")):
            stats["deja_candidat"] += 1
            continue
        geom, methode, score = None, "signale_humain", SCORE_SIGNALE
        if s_cosia is not None:
            hits = s_cosia.query(pt.buffer(RECUP_COSIA_M), predicate="intersects")
            if len(hits):
                geom = cosia.iloc[hits[0]].geometry
                methode, score = "signale+cosia", SCORE_RECUPERE
                stats["recupere_cosia"] += 1
        if geom is None:
            geom = pt.buffer(RAYON_DEFAUT_M)
            stats["point_nu"] += 1
        geoms.append(geom)
        methodes.append(methode)
        scores.append(score)

    if not geoms:
        return gpd.GeoDataFrame(columns=["geometry"], crs=crs), stats

    cand = gpd.GeoDataFrame(
        {"methode": methodes, "score_detection": scores,
         "dalle": ["signalement"] * len(geoms)},
        geometry=geoms, crs=crs)
    # commune = celle de la parcelle sous le point (sinon jointure spatiale)
    jointe = gpd.sjoin(
        gpd.GeoDataFrame(geometry=cand.geometry.representative_point(), crs=crs),
        parcelles[["commune", "geometry"]], how="left", predicate="within")
    cand["commune"] = jointe["commune"].to_numpy()
    cand = attributs_forme(cand)
    cand["id_detection"] = ids_stables(cand, "pisc")
    return cand, stats


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cosia-dir", help="blocs GPKG CoSIA (sinon cosia.gpkg_dir)")
    p.add_argument("--produit", default="piscines")
    p.add_argument("--out", help="parquet de sortie (défaut : "
                                 "data/interim/piscines_signales_{dept}.parquet)")
    p.add_argument("--fusionner-dans", help="parquet de candidats à COMPLÉTER "
                                            "(les nouveaux s'y ajoutent, sans doublon)")
    args = p.parse_args()

    cfg = load_config()
    interim = Path(cfg["paths"]["interim"])
    dept, crs = cfg["dept"], cfg["crs_metric"]

    bruts = lire_signalements(interim.parent / "atelier" / "atelier.sqlite", args.produit)
    points = fusionner_clics(bruts)
    log.info("Signalements : %d clics bruts → %d intentions distinctes.",
             len(bruts), len(points))
    if not points:
        log.warning("Aucun signalement — rien à faire.")
        return

    deja = candidats_existants(interim, dept)
    cosia_dir = Path(args.cosia_dir or cfg.get("cosia", {}).get("gpkg_dir") or "")
    cosia = (recuperer_cosia(cosia_dir, points, crs)
             if cosia_dir.name and cosia_dir.exists()
             else gpd.GeoDataFrame(columns=["geometry"], crs=crs))
    if cosia.empty:
        log.warning("CoSIA indisponible (%s) — récupération de géométrie "
                    "désactivée, tous les points deviendront des disques.", cosia_dir)
    parcelles = gpd.read_parquet(interim / f"parcelles_{dept}.parquet",
                                 columns=["commune", "geometry"])

    cand, stats = construire(points, deja, cosia, parcelles, crs)
    log.info("Chaîne de décision : %s", stats)
    if cand.empty:
        log.warning("Tous les signalements pointaient des candidats existants — "
                    "aucun nouveau candidat (à surveiller : incompréhension de F ?).")
        return

    valider_couche1(cand, crs_attendu=crs)
    out = Path(args.out) if args.out else interim / f"piscines_signales_{dept}.parquet"
    cand.to_parquet(out)
    log.info("%d candidats signalés → %s", len(cand), out)

    if args.fusionner_dans:
        cible = Path(args.fusionner_dans)
        base = gpd.read_parquet(cible)
        avant = len(base)
        fusion = pd.concat([base, cand], ignore_index=True)
        fusion = fusion.drop_duplicates(subset="id_detection", keep="first")
        gpd.GeoDataFrame(fusion, crs=crs).to_parquet(cible)
        log.info("Fusion dans %s : %d → %d candidats (+%d).",
                 cible.name, avant, len(fusion), len(fusion) - avant)


if __name__ == "__main__":
    main()
