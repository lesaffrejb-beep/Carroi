"""Détection de piscines sur BD ORTHO 20 cm — étape 1b, option B (HSV + IRC).

Orchestration par dalles et fenêtres autour du cœur algorithmique `detection.py` :
  - parcourt les dalles RVB d'un dossier, apparie chaque dalle IRC par emprise ;
  - lit par fenêtres (mémoire bornée) avec chevauchement ≥ diamètre max d'une
    piscine : un candidat n'est retenu que si son point représentatif tombe
    dans la zone « intérieure » de la fenêtre → aucun doublon inter-fenêtres ;
  - saute les fenêtres sans bâtiment BD TOPO à moins de buffer_batiments_m
    (~60 % du territoire agricole éliminé sans lecture pixel) ;
  - recolle les piscines coupées par une limite de dalle.

Usage :
    python 15_detect_piscines.py --ortho-dir data/raw/bdortho/rvb \
        [--irc-dir data/raw/bdortho/irc] [--commune 49XXX] [--limit-dalles N]

Sortie : data/interim/piscines_candidates_{dept}[_{commune}].parquet
         (EPSG:2154 ; colonnes surface_m2, score_detection, methode, dalle)

⚠ Ce fichier contient des CANDIDATS, pas la base : le tri visuel humain
(16_tri_visuel.py) est obligatoire pour produire piscines_detectees_{dept}.parquet
— c'est lui qui garantit la précision ≥ 95 % vendable (docs/06).
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window
from shapely.geometry import box

import detection
from common import ensure_dirs, load_config

log = logging.getLogger("detect")

EXTENSIONS = (".jp2", ".tif", ".tiff")


def lister_dalles(dossier: Path) -> list[Path]:
    dalles = sorted(p for p in dossier.iterdir() if p.suffix.lower() in EXTENSIONS)
    if not dalles:
        raise SystemExit(f"Aucune dalle ({'/'.join(EXTENSIONS)}) dans {dossier} — rien à détecter.")
    return dalles


def indexer_irc(irc_dir: Path | None) -> list[tuple[tuple, Path]]:
    """Index (bounds arrondis au mètre → chemin) des dalles IRC pour appariement."""
    if irc_dir is None:
        return []
    index = []
    for p in lister_dalles(irc_dir):
        with rasterio.open(p) as src:
            index.append((tuple(round(b) for b in src.bounds), p))
    return index


def apparier_irc(bounds, index_irc) -> Path | None:
    cle = tuple(round(b) for b in bounds)
    for b, p in index_irc:
        if b == cle:
            return p
    return None


def charger_aoi_batiments(cfg: dict, commune: str | None):
    """AOI commune (union des parcelles) + index spatial des bâtiments BD TOPO."""
    interim = Path(cfg["paths"]["interim"])
    dept = cfg["dept"]
    aoi = None
    if commune:
        parcelles = gpd.read_parquet(interim / f"parcelles_{dept}.parquet")
        sel = parcelles[parcelles["commune"] == commune]
        if sel.empty:
            raise SystemExit(f"Commune {commune} introuvable dans parcelles_{dept}.parquet.")
        aoi = sel.union_all()
        log.info("AOI commune %s : %d parcelles.", commune, len(sel))
    bat_path = interim / f"bdtopo_batiment_{dept}.parquet"
    if not bat_path.exists():
        raise SystemExit(
            f"{bat_path} manquant — lancer 10_download.py d'abord (le masque bâti "
            "est obligatoire : sans lui on traite 100 % du territoire pour rien)."
        )
    batiments = gpd.read_parquet(bat_path)
    return aoi, batiments.geometry.values, batiments.sindex


def fenetres(width: int, height: int, taille: int, chevauchement: int):
    """Fenêtres (Window, marge_gauche, marge_haut) couvrant le raster avec recouvrement."""
    pas = taille - chevauchement
    if pas <= 0:
        raise ValueError("taille_px doit être > chevauchement_px")
    for row0 in range(0, height, pas):
        for col0 in range(0, width, pas):
            w = min(taille, width - col0)
            h = min(taille, height - row0)
            if w <= chevauchement and col0 > 0:
                continue  # bande résiduelle déjà couverte par la fenêtre précédente
            if h <= chevauchement and row0 > 0:
                continue
            yield Window(col0, row0, w, h)


def zone_interieure(win: Window, transform, chevauchement: int, width: int, height: int):
    """Boîte géographique où le point représentatif d'un candidat doit tomber.

    Demi-chevauchement de marge de chaque côté, sauf en bord de raster : ainsi
    chaque point du raster appartient à la zone intérieure d'exactement une
    fenêtre → dédoublonnage par construction.
    """
    demi = chevauchement // 2
    c0 = win.col_off + (demi if win.col_off > 0 else 0)
    r0 = win.row_off + (demi if win.row_off > 0 else 0)
    c1 = win.col_off + win.width - (demi if win.col_off + win.width < width else 0)
    r1 = win.row_off + win.height - (demi if win.row_off + win.height < height else 0)
    x0, y0 = transform * (c0, r1)  # bas-gauche (y inversé en image)
    x1, y1 = transform * (c1, r0)
    return box(x0, y0, x1, y1)


def traiter_dalle(
    path_rvb: Path,
    path_irc: Path | None,
    cfg_det: dict,
    bat_geoms,
    bat_sidx,
    aoi,
) -> list[gpd.GeoDataFrame]:
    resultats = []
    taille = cfg_det["fenetre"]["taille_px"]
    chev = cfg_det["fenetre"]["chevauchement_px"]
    buffer_bat = cfg_det["buffer_batiments_m"]
    band_nir = cfg_det["irc"]["band_nir"]

    with rasterio.open(path_rvb) as rvb:
        res_m = abs(rvb.transform.a)
        if not (0.05 <= res_m <= 1.0):
            raise SystemExit(f"{path_rvb}: résolution {res_m} m/px hors BD ORTHO (attendu ~0.2).")
        irc = rasterio.open(path_irc) if path_irc else None
        try:
            if irc and tuple(round(b) for b in irc.bounds) != tuple(round(b) for b in rvb.bounds):
                raise SystemExit(f"Emprises RVB/IRC incohérentes : {path_rvb} vs {path_irc}")
            min_px = max(1, int(cfg_det["forme"]["surface_min_m2"] / (res_m * res_m) * 0.5))
            n_win = n_saut_bat = n_saut_aoi = 0
            for win in fenetres(rvb.width, rvb.height, taille, chev):
                n_win += 1
                wt = rasterio.windows.transform(win, rvb.transform)
                wx0, wy0 = wt * (0, win.height)
                wx1, wy1 = wt * (win.width, 0)
                wbox = box(wx0, wy0, wx1, wy1)
                if aoi is not None and not wbox.intersects(aoi):
                    n_saut_aoi += 1
                    continue
                # Masque bâti : fenêtre sans bâtiment à < buffer → aucune piscine privée.
                if len(bat_sidx.query(wbox.buffer(buffer_bat), predicate="intersects")) == 0:
                    n_saut_bat += 1
                    continue

                rgb = np.transpose(rvb.read([1, 2, 3], window=win), (1, 2, 0))
                nir = irc.read(band_nir, window=win) if irc else None
                mask = detection.masque_eau(rgb, nir, cfg_det)
                mask = detection.nettoyer_masque(mask, min_px)
                cand = detection.extraire_candidats(mask, rgb, nir, wt, res_m, cfg_det)
                if cand.empty:
                    continue
                interieur = zone_interieure(win, rvb.transform, chev, rvb.width, rvb.height)
                cand = cand[cand.geometry.representative_point().within(interieur)]
                if aoi is not None:
                    cand = cand[cand.geometry.representative_point().within(aoi)]
                if not cand.empty:
                    resultats.append(cand.set_crs(rvb.crs))
            log.info(
                "%s : %d fenêtres (%d sautées hors AOI, %d sans bâti), %d candidats.",
                path_rvb.name, n_win, n_saut_aoi, n_saut_bat,
                sum(len(c) for c in resultats),
            )
        finally:
            if irc:
                irc.close()
    return resultats


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ortho-dir", required=True, help="dossier des dalles RVB")
    p.add_argument("--irc-dir", help="dossier des dalles IRC (fortement recommandé)")
    p.add_argument("--commune", help="code INSEE pour un run de test sur une commune")
    p.add_argument("--limit-dalles", type=int, help="ne traiter que N dalles (débogage)")
    args = p.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    cfg_det = cfg["detection"]
    if not args.irc_dir:
        log.warning(
            "Pas d'IRC : le filtre végétation/NDWI est désactivé, attendre BEAUCOUP "
            "plus de faux positifs (bâches vertes, végétation bleutée). Le tri humain "
            "reste obligatoire mais sera plus long."
        )

    dalles = lister_dalles(Path(args.ortho_dir))
    if args.limit_dalles:
        dalles = dalles[: args.limit_dalles]
    index_irc = indexer_irc(Path(args.irc_dir) if args.irc_dir else None)
    aoi, bat_geoms, bat_sidx = charger_aoi_batiments(cfg, args.commune)

    morceaux: list[gpd.GeoDataFrame] = []
    for i, dalle in enumerate(dalles, 1):
        with rasterio.open(dalle) as src:
            bounds = src.bounds
        irc_path = apparier_irc(bounds, index_irc)
        if index_irc and irc_path is None:
            raise SystemExit(f"Dalle IRC manquante pour l'emprise de {dalle.name} — "
                             "compléter le téléchargement plutôt que détecter à moitié.")
        log.info("[%d/%d] %s (IRC: %s)", i, len(dalles), dalle.name,
                 irc_path.name if irc_path else "absent")
        for cand in traiter_dalle(dalle, irc_path, cfg_det, bat_geoms, bat_sidx, aoi):
            cand["dalle"] = dalle.name
            morceaux.append(cand)

    if not morceaux:
        raise SystemExit("0 candidat détecté — seuils trop stricts ou mauvaises dalles ? "
                         "Vérifier une dalle au hasard dans QGIS avant de conclure.")
    tous = gpd.GeoDataFrame(pd.concat(morceaux, ignore_index=True), crs=morceaux[0].crs)
    tous = tous.to_crs(cfg["crs_metric"])
    tous = detection.fusionner_adjacentes(tous)
    tous["methode"] = "hsv" if args.irc_dir else "hsv_sans_irc"
    tous["id_detection"] = range(len(tous))

    suffix = f"_{args.commune}" if args.commune else ""
    out = Path(cfg["paths"]["interim"]) / f"piscines_candidates_{cfg['dept']}{suffix}.parquet"
    tous.to_parquet(out)
    log.info("Écrit : %s (%d candidats). Prochaine étape : 16_tri_visuel.py "
             "(le tri humain est OBLIGATOIRE avant la jointure).", out, len(tous))


if __name__ == "__main__":
    main()
