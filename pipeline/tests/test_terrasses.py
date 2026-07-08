"""Tests du cœur produit 2 (terrasses.py) + intégration 25_terrasses.py sur
dalles MNS synthétiques.

Les cas encodent la physique de vente : un jardin sud dégagé est plein_soleil,
le même jardin muré est ombrage, et la canopée d'un arbre ensoleillé ne compte
JAMAIS comme terrasse (masque MNH).
"""
from __future__ import annotations

import importlib
import sys

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

import terrasses

terr_cli = importlib.import_module("25_terrasses")

SEUILS = {
    "dist_facade_m": 15, "tampon_limite_m": 1.0, "surface_zone_min_m2": 10,
    "hauteur_sol_max_m": 0.5, "pas_minutes": 30, "portee_ombre_m": 150,
    "surface_contigue_min_m2": 20,
    "plein_soleil": {"juin_min_h": 7, "equinoxe_min_h": 4},
    "bon": {"juin_min_h": 5, "equinoxe_min_h": 3},
}


# ------------------------------------------------------------- zone jardin

def test_zone_jardin_exclut_bati_limites_et_loin_de_facade():
    parcelle = box(0, 0, 40, 40)
    maison = box(0, 25, 40, 40)  # bande nord
    zone = terrasses.zone_jardin(parcelle, [maison], **{
        "dist_facade_m": 15, "tampon_limite_m": 1.0, "surface_min_m2": 10})
    assert zone is not None
    assert not zone.intersects(box(5, 30, 10, 35)), "le bâti est exclu"
    assert zone.bounds[1] >= 25 - 15 - 1e-6, "rien au-delà de 15 m de la façade"
    assert zone.bounds[0] >= 1.0 - 1e-6, "la bande de limite de parcelle est exclue"


def test_parcelle_non_batie_ignoree():
    assert terrasses.zone_jardin(box(0, 0, 30, 30), [box(100, 100, 110, 110)],
                                 dist_facade_m=15, tampon_limite_m=1.0,
                                 surface_min_m2=10) is None


def test_orientation_zone_sud():
    maison = box(0, 20, 20, 30)
    jardin_sud = box(0, 0, 20, 18)
    az, secteur = terrasses.orientation_zone(jardin_sud, maison)
    assert secteur == "S"
    assert 150 <= az <= 210
    jardin_est = box(25, 20, 45, 30)
    _, secteur_e = terrasses.orientation_zone(jardin_est, maison)
    assert secteur_e == "E"


# ------------------------------------------------------------- classification

def _masque(n=40):
    return np.ones((n, n), dtype=bool)


def test_classe_plein_soleil_exige_du_contigu():
    """40 pixels de soleil ÉPARPILLÉS (10 m² contigus max) ne font pas une
    terrasse ; le même total en bloc contigu, si."""
    res = 0.5  # 1 px = 0,25 m²
    h_juin = np.zeros((40, 40)); h_eq = np.zeros((40, 40))
    # Damier de soleil : chaque pixel ensoleillé isolé (connectivité 4).
    damier = np.indices((40, 40)).sum(axis=0) % 2 == 0
    h_juin[damier] = 10.0; h_eq[damier] = 6.0
    r = terrasses.classifier_soleil(h_juin, h_eq, _masque(), res, SEUILS)
    assert r["classe_soleil"] == "ombrage", "du soleil en damier n'est pas une terrasse"

    h_juin[:] = 0; h_eq[:] = 0
    h_juin[5:15, 5:15] = 10.0; h_eq[5:15, 5:15] = 6.0  # bloc 25 m² contigu
    r = terrasses.classifier_soleil(h_juin, h_eq, _masque(), res, SEUILS)
    assert r["classe_soleil"] == "plein_soleil"
    assert r["surface_plein_soleil_m2"] == pytest.approx(25.0)


def test_classe_bon_si_seuils_intermediaires():
    h_juin = np.full((40, 40), 6.0)   # < 7 (pas plein soleil) mais ≥ 5
    h_eq = np.full((40, 40), 3.5)     # < 4 mais ≥ 3
    r = terrasses.classifier_soleil(h_juin, h_eq, _masque(), 0.5, SEUILS)
    assert r["classe_soleil"] == "bon"
    assert 0.0 < r["score_detection"] < 1.0


def test_masque_sol_exclut_la_canopee():
    """Le piège du produit : un grand arbre au soleil dans le jardin. Ses pixels
    (MNH haut) doivent sortir du masque AVANT classification."""
    masque = _masque(20)
    mnh = np.zeros((20, 20)); mnh[5:15, 5:15] = 9.0  # arbre de 9 m
    m2 = terrasses.masque_sol(masque, mnh, hauteur_max_m=0.5)
    assert not m2[10, 10], "la canopée est exclue"
    assert m2[0, 0], "le sol nu reste"
    with pytest.raises(ValueError):
        terrasses.masque_sol(masque, np.zeros((5, 5)), 0.5)


def test_zone_vide_est_ombrage_sans_crash():
    r = terrasses.classifier_soleil(np.zeros((5, 5)), np.zeros((5, 5)),
                                    np.zeros((5, 5), dtype=bool), 0.5, SEUILS)
    assert r["classe_soleil"] == "ombrage"
    assert r["score_detection"] == 0.0


# ------------------------------------------------------------- intégration CLI

RES = 0.5
ORIGINE = (450_000.0, 6_720_000.0)
N = 200  # dalle synthétique 100 m


def _ecrire_dalle(path, arr):
    profile = {"driver": "GTiff", "width": N, "height": N, "count": 1,
               "dtype": "float32", "crs": "EPSG:2154",
               "transform": from_origin(ORIGINE[0], ORIGINE[1], RES, RES)}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype(np.float32)[np.newaxis, ...])


def _monde(col, row):
    return ORIGINE[0] + col * RES, ORIGINE[1] - row * RES


@pytest.fixture
def environnement(tmp_path):
    mns = np.zeros((N, N)); mnh = np.zeros((N, N))

    # Parcelle A (ouest) : maison rangée nord, jardin sud DÉGAGÉ → plein_soleil.
    mns[20:40, 20:80] = 6.0  # maison A (rows 20-40 = nord)

    # Parcelle B (est) : même maison, mais le jardin est une COUR fermée de 5 m
    # de profondeur cernée de murs/arbres de 20 m (MNS et MNH) → ombrage.
    # (La parcelle s'arrête au mur sud : la zone jardin est la cour, rien d'autre.)
    mns[20:40, 120:180] = 6.0            # maison B
    for rows, cols in [((50, 54), (118, 182)),   # mur sud, à 5 m de la façade
                       ((40, 54), (118, 122)),   # mur ouest
                       ((40, 54), (178, 182))]:  # mur est
        mns[rows[0]:rows[1], cols[0]:cols[1]] = 20.0
        mnh[rows[0]:rows[1], cols[0]:cols[1]] = 20.0

    mns_dir = tmp_path / "mns"; mns_dir.mkdir()
    mnh_dir = tmp_path / "mnh"; mnh_dir.mkdir()
    _ecrire_dalle(mns_dir / "dalle.tif", mns)
    _ecrire_dalle(mnh_dir / "dalle.tif", mnh)

    interim = tmp_path / "interim"; interim.mkdir()
    # Parcelles et bâtiments en coordonnées monde (y décroît avec row).
    ax0, ay0 = _monde(15, 85); ax1, ay1 = _monde(85, 15)
    bx0, by0 = _monde(115, 54); bx1, by1 = _monde(185, 15)  # B s'arrête au mur sud
    parcelles = gpd.GeoDataFrame(
        {"id": ["A" * 14, "B" * 14], "commune": ["49999", "49999"]},
        geometry=[box(ax0, ay0, ax1, ay1), box(bx0, by0, bx1, by1)], crs="EPSG:2154")
    parcelles.to_parquet(interim / "parcelles_49.parquet")
    ma = box(*_monde(20, 40), *_monde(80, 20))
    mb = box(*_monde(120, 40), *_monde(180, 20))
    gpd.GeoDataFrame(geometry=[ma, mb], crs="EPSG:2154").to_parquet(
        interim / "bdtopo_batiment_49.parquet")

    cfg = {
        "dept": "49", "crs_metric": "EPSG:2154", "crs_output": "EPSG:4326",
        "paths": {"raw": str(tmp_path / "raw"), "interim": str(interim),
                  "final": str(tmp_path / "final"), "exports": str(tmp_path / "exports"),
                  "optout": str(tmp_path / "optout/optout.csv"),
                  "validation": str(tmp_path / "validation")},
        "terrasses": {**SEUILS, "pas_minutes": 60, "portee_ombre_m": 60},
        "piscines": {},
    }
    return tmp_path, mns_dir, mnh_dir, cfg


def test_chaine_terrasses_bout_en_bout(environnement, monkeypatch):
    tmp_path, mns_dir, mnh_dir, cfg = environnement
    monkeypatch.setattr(terr_cli, "load_config", lambda: cfg)
    monkeypatch.setattr(sys, "argv", ["25", "--mns-dir", str(mns_dir),
                                      "--mnh-dir", str(mnh_dir)])
    terr_cli.main()

    out = gpd.read_parquet(tmp_path / "interim" / "terrasses_candidates_49.parquet")
    assert len(out) == 2
    # Contrat couche 1 (docs/09 §2)
    for col in ["surface_m2", "score_detection", "methode", "classe_soleil",
                "heures_soleil_juin", "heures_soleil_equinoxe",
                "orientation_deg", "secteur", "id_detection"]:
        assert col in out.columns, f"colonne contractuelle manquante : {col}"
    assert (out["methode"] == "mns_solaire").all()
    assert out.crs.to_epsg() == 2154

    a = out[out["id_parcelle"] == "A" * 14].iloc[0]
    b = out[out["id_parcelle"] == "B" * 14].iloc[0]
    assert a["classe_soleil"] == "plein_soleil", "jardin sud dégagé"
    assert a["secteur"] in ("S", "SE", "SO")
    assert b["classe_soleil"] == "ombrage", "jardin emmuré : exclu de la vente"
    assert a["heures_soleil_juin"] > b["heures_soleil_juin"] + 3
    assert a["score_detection"] > b["score_detection"]
