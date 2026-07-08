"""Test d'intégration bout-en-bout de l'étape 1b sur dalles synthétiques :

    dalles GeoTIFF (RVB + IRC) fabriquées de toutes pièces
        → 15_detect_piscines.py (CLI complet : fenêtrage, appariement IRC,
          masque bâti, fusion, parquet)
        → 16_tri_visuel.py mode planche (vignettes + tri.html)
        → 16_tri_visuel.py mode --apply (decisions.csv → piscines_detectees)

C'est le filet de sécurité avant le premier run sur BD ORTHO réelle : si
l'orchestration casse (bounds, transforms, appariement, CRS), ça casse ici.
"""
from __future__ import annotations

import importlib
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

detect_cli = importlib.import_module("15_detect_piscines")
tri_cli = importlib.import_module("16_tri_visuel")

RES = 0.2
ORIGINE = (400_000.0, 6_700_000.0)  # Lambert-93 plausible
TAILLE = 1024                        # dalle 204,8 m de côté

PELOUSE = ((80, 140, 60), 200)
PISCINE = ((60, 180, 200), 30)


def _ecrire_dalle(path, data, count):
    profile = {
        "driver": "GTiff", "width": TAILLE, "height": TAILLE, "count": count,
        "dtype": "uint8", "crs": "EPSG:2154",
        "transform": from_origin(ORIGINE[0], ORIGINE[1], RES, RES),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)


@pytest.fixture
def environnement(tmp_path):
    """Dalles RVB/IRC + bâtiments + config, tout dans tmp_path."""
    rgb = np.zeros((TAILLE, TAILLE, 3), dtype=np.uint8)
    rgb[..., :] = PELOUSE[0]
    nir = np.full((TAILLE, TAILLE), PELOUSE[1], dtype=np.uint8)
    yy, xx = np.ogrid[:TAILLE, :TAILLE]
    m = ((yy - 512) / 25.0) ** 2 + ((xx - 512) / 15.0) ** 2 <= 1  # piscine ~47 m²
    rgb[m] = PISCINE[0]
    nir[m] = PISCINE[1]

    rvb_dir = tmp_path / "rvb"; rvb_dir.mkdir()
    irc_dir = tmp_path / "irc"; irc_dir.mkdir()
    _ecrire_dalle(rvb_dir / "dalle-0400-6700.tif", np.transpose(rgb, (2, 0, 1)), 3)
    _ecrire_dalle(irc_dir / "dalle-0400-6700-irc.tif", nir[np.newaxis, ...], 1)

    interim = tmp_path / "interim"; interim.mkdir()
    # Un bâtiment à ~30 m de la piscine : la fenêtre passe le masque bâti.
    cx = ORIGINE[0] + 512 * RES
    cy = ORIGINE[1] - 512 * RES
    bat = gpd.GeoDataFrame(geometry=[box(cx + 20, cy + 20, cx + 35, cy + 30)], crs="EPSG:2154")
    bat.to_parquet(interim / "bdtopo_batiment_49.parquet")

    cfg = {
        "dept": "49",
        "crs_metric": "EPSG:2154",
        "crs_output": "EPSG:4326",
        "paths": {
            "raw": str(tmp_path / "raw"), "interim": str(interim),
            "final": str(tmp_path / "final"), "exports": str(tmp_path / "exports"),
            "optout": str(tmp_path / "optout/optout.csv"),
            "validation": str(tmp_path / "validation"),
        },
        "detection": {
            "hsv": {"hue_min": 0.42, "hue_max": 0.62, "sat_min": 0.15, "val_min": 0.25},
            "irc": {"band_nir": 1, "ndvi_max": 0.10, "ndwi_min": -0.05},
            "forme": {"surface_min_m2": 4, "surface_max_m2": 400,
                      "compacite_min": 0.30, "solidite_min": 0.65},
            "fenetre": {"taille_px": 512, "chevauchement_px": 128},
            "buffer_batiments_m": 80,
            "score_min": 0.35,
        },
        "tri_visuel": {"vignette_m": 60, "vignette_px": 128},
        "piscines": {},
    }
    return tmp_path, rvb_dir, irc_dir, cfg


def _patch_config(monkeypatch, module, cfg):
    monkeypatch.setattr(module, "load_config", lambda: cfg)


def test_chaine_detection_puis_tri(environnement, monkeypatch):
    tmp_path, rvb_dir, irc_dir, cfg = environnement

    # --- 15 : détection ---
    _patch_config(monkeypatch, detect_cli, cfg)
    monkeypatch.setattr(
        sys, "argv",
        ["15", "--ortho-dir", str(rvb_dir), "--irc-dir", str(irc_dir)],
    )
    detect_cli.main()

    out = tmp_path / "interim" / "piscines_candidates_49.parquet"
    cand = gpd.read_parquet(out)
    assert len(cand) == 1, "exactement une piscine dans la scène"
    row = cand.iloc[0]
    assert row["methode"] == "hsv"
    assert row["surface_m2"] == pytest.approx(np.pi * 25 * 15 * RES * RES, rel=0.25)
    # Géoréférencement absolu dans la dalle (fenêtrage + transform fenêtre).
    c = cand.geometry.iloc[0].centroid
    assert c.x == pytest.approx(ORIGINE[0] + 512 * RES, abs=1.0)
    assert c.y == pytest.approx(ORIGINE[1] - 512 * RES, abs=1.0)
    assert cand.crs.to_epsg() == 2154

    # --- 16 : planche de tri ---
    _patch_config(monkeypatch, tri_cli, cfg)
    monkeypatch.setattr(
        sys, "argv",
        ["16", "--candidats", str(out), "--ortho-dir", str(rvb_dir)],
    )
    tri_cli.main()
    html = (tmp_path / "interim" / "tri" / "tri.html").read_text(encoding="utf-8")
    assert "data:image/png;base64," in html
    assert '"id": 0' in html

    # --- 16 --apply : décisions → base validée ---
    decisions = tmp_path / "decisions.csv"
    decisions.write_text("id_detection,decision\n0,oui\n")
    monkeypatch.setattr(
        sys, "argv",
        ["16", "--candidats", str(out), "--apply", str(decisions)],
    )
    tri_cli.main()
    detectees = gpd.read_parquet(tmp_path / "interim" / "piscines_detectees_49.parquet")
    assert len(detectees) == 1
    assert detectees.iloc[0]["methode"] == "valide_humain"


def test_detection_echoue_bruyamment_sans_batiments(environnement, monkeypatch):
    """Pas de bdtopo_batiment → SystemExit explicite, pas de run silencieux."""
    tmp_path, rvb_dir, irc_dir, cfg = environnement
    (tmp_path / "interim" / "bdtopo_batiment_49.parquet").unlink()
    _patch_config(monkeypatch, detect_cli, cfg)
    monkeypatch.setattr(sys, "argv", ["15", "--ortho-dir", str(rvb_dir)])
    with pytest.raises(SystemExit, match="10_download"):
        detect_cli.main()


def test_detection_refuse_une_dalle_irc_manquante(environnement, monkeypatch, tmp_path):
    """IRC fourni mais dalle non appariée → refus (pas de détection à moitié)."""
    _, rvb_dir, irc_dir, cfg = environnement
    irc_vide = tmp_path / "irc_autre"; irc_vide.mkdir()
    nir = np.full((1, 64, 64), 200, dtype=np.uint8)
    profile = {
        "driver": "GTiff", "width": 64, "height": 64, "count": 1, "dtype": "uint8",
        "crs": "EPSG:2154", "transform": from_origin(0, 100, RES, RES),
    }
    with rasterio.open(irc_vide / "ailleurs.tif", "w", **profile) as dst:
        dst.write(nir)
    _patch_config(monkeypatch, detect_cli, cfg)
    monkeypatch.setattr(
        sys, "argv",
        ["15", "--ortho-dir", str(rvb_dir), "--irc-dir", str(irc_vide)],
    )
    with pytest.raises(SystemExit, match="IRC manquante"):
        detect_cli.main()
