"""CoSIA (IA de couverture du sol IGN) via flux WMS — pré-annotateur national.

Découverte de la veille 2026-07-17 : CoSIA est servi en WMS sur la
Géoplateforme (couches IGNF_COSIA_2017-2020 / 2021-2023 / 2024-2026), donc
utilisable crop par crop SANS télécharger le département. La classe « Piscine »
sort en RGB(98, 208, 255) dans le rendu (auto-calibré sur nos piscines validées
humain, 2026-07-17).

Ce module enrichit un parquet de candidats d'une colonne `cosia_frac` : la
fraction de pixels classés Piscine par CoSIA dans un crop de 40 m autour du
candidat. Usages :
  - FEATURE du pré-tri (22_pretri la prend automatiquement si présente) ;
  - MESURE : rappel/précision de CoSIA vs le consensus humain (rapport stdout) ;
  - PRIORISATION : divergence CoSIA ↔ humain = tuile à re-farmer.

Usage :
    python 14_cosia.py --candidats data/interim/piscines_candidates_49_49035.parquet
    (idempotent : cache disque data/interim/cosia_cache/, requêtes espacées)

Licence Ouverte 2.0 (IGN). CoSIA est du brut de modèle (~78 % d'exactitude
globale annoncée) : un pré-annotateur, JAMAIS une vérité — la vérité reste le
consensus humain de l'Atelier.
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import requests

from common import ensure_dirs, load_config

log = logging.getLogger("cosia")

WMS = "https://data.geopf.fr/wms-r/wms"
COUCHE = "IGNF_COSIA_2021-2023"      # millésime aligné sur notre BD ORTHO 2022
RGB_PISCINE = np.array([98, 208, 255], dtype=float)
TOLERANCE = 12.0                      # anti-aliasing / compression du rendu
CROP_M = 40.0
CROP_PX = 64


def frac_piscine(img_rgb: np.ndarray) -> float:
    """Fraction de pixels « Piscine » dans un rendu CoSIA. Pure."""
    d = np.linalg.norm(img_rgb.reshape(-1, 3).astype(float) - RGB_PISCINE, axis=1)
    return float((d < TOLERANCE).mean())


def crop_cosia(cx: float, cy: float, session: requests.Session,
               couche: str = COUCHE, m: float = CROP_M, px: int = CROP_PX
               ) -> np.ndarray:
    from PIL import Image
    r = session.get(WMS, params={
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
        "LAYERS": couche, "STYLES": "", "CRS": "EPSG:2154",
        "BBOX": f"{cx - m/2},{cy - m/2},{cx + m/2},{cy + m/2}",
        "WIDTH": px, "HEIGHT": px, "FORMAT": "image/png"}, timeout=60)
    r.raise_for_status()
    return np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"))


def enrichir(candidats: gpd.GeoDataFrame, cache_dir: Path) -> gpd.GeoDataFrame:
    """Ajoute cosia_frac à chaque candidat (cache disque, reprise possible)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_f = cache_dir / "cosia_frac.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    session = requests.Session()
    fait = 0
    for _, r in candidats.iterrows():
        i = str(r["id_detection"])
        if i in cache:
            continue
        pt = r.geometry.representative_point()
        for essai in range(3):
            try:
                cache[i] = frac_piscine(crop_cosia(pt.x, pt.y, session))
                break
            except Exception as e:                      # réseau : on insiste
                if essai == 2:
                    log.warning("échec %s : %s", i, e)
                    cache[i] = None
                time.sleep(2 * (essai + 1))
        fait += 1
        if fait % 100 == 0:
            cache_f.write_text(json.dumps(cache))
            log.info("%d/%d crops interrogés…", len(cache), len(candidats))
        time.sleep(0.05)                                # politesse Géoplateforme
    cache_f.write_text(json.dumps(cache))
    out = candidats.copy()
    out["cosia_frac"] = [cache.get(str(i)) for i in out["id_detection"].astype(str)]
    return out


def mesurer_vs_humain(candidats: gpd.GeoDataFrame, db: Path, produit: str) -> None:
    """Rappel / précision de « CoSIA voit de la piscine » vs consensus humain."""
    import importlib
    pt22 = importlib.import_module("22_pretri")
    y = pt22.labels_consensus(db, produit)
    df = candidats[candidats["id_detection"].astype(str).isin(y.index)].copy()
    df["y"] = y.loc[df["id_detection"].astype(str)].to_numpy()
    df = df[df["cosia_frac"].notna()]
    for seuil in (0.0, 0.005, 0.02):
        voit = df["cosia_frac"] > seuil
        rappel = df.loc[voit, "y"].sum() / max(1, df["y"].sum())
        prec = df.loc[voit, "y"].mean() if voit.any() else float("nan")
        log.info("CoSIA frac>%s : rappel %.1f%%, précision %.1f%% (%d candidats vus)",
                 seuil, 100 * rappel, 100 * prec, int(voit.sum()))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidats", required=True)
    p.add_argument("--produit", default="piscines")
    args = p.parse_args()
    cfg = load_config()
    ensure_dirs(cfg)
    interim = Path(cfg["paths"]["interim"])
    cand = gpd.read_parquet(args.candidats)
    out = enrichir(cand, interim / "cosia_cache")
    out.to_parquet(args.candidats)
    log.info("Écrit : %s (+ colonne cosia_frac).", args.candidats)
    db = interim.parent / "atelier" / "atelier.sqlite"
    if db.exists():
        mesurer_vs_humain(out, db, args.produit)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
