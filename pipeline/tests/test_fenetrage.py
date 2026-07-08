"""Tests du fenêtrage de 15_detect_piscines.py : la propriété critique est que
les zones intérieures des fenêtres PARTITIONNENT le raster (couverture totale,
recouvrement nul) — c'est ce qui garantit zéro doublon et zéro oubli aux
frontières de fenêtres.
"""
from __future__ import annotations

import importlib

import numpy as np
from rasterio.transform import from_origin
from shapely.geometry import Point
from shapely.ops import unary_union

detect_cli = importlib.import_module("15_detect_piscines")

RES = 0.2


def _inner_boxes(width, height, taille, chev):
    transform = from_origin(0.0, height * RES, RES, RES)
    wins = list(detect_cli.fenetres(width, height, taille, chev))
    return [
        detect_cli.zone_interieure(w, transform, chev, width, height) for w in wins
    ], transform


def test_zones_interieures_partitionnent_le_raster():
    width, height, taille, chev = 500, 300, 200, 40
    boxes, _ = _inner_boxes(width, height, taille, chev)
    union = unary_union(boxes)
    aire_raster = width * RES * height * RES
    assert union.area == abs(aire_raster) or np.isclose(union.area, aire_raster), \
        "les zones intérieures doivent couvrir tout le raster"
    somme = sum(b.area for b in boxes)
    assert np.isclose(somme, aire_raster), \
        f"recouvrement des zones intérieures détecté (somme {somme} ≠ raster {aire_raster})"


def test_chaque_point_appartient_a_une_seule_zone():
    width, height, taille, chev = 500, 300, 200, 40
    boxes, _ = _inner_boxes(width, height, taille, chev)
    rng = np.random.default_rng(42)
    # Décalage irrationnel pour éviter de tomber pile sur une frontière.
    xs = rng.uniform(0.001, width * RES - 0.001, 200)
    ys = rng.uniform(0.001, height * RES - 0.001, 200)
    for x, y in zip(xs, ys):
        n = sum(Point(x, y).within(b) for b in boxes)
        assert n == 1, f"point ({x:.3f},{y:.3f}) dans {n} zones intérieures"


def test_fenetres_couvrent_tout_le_raster_avec_chevauchement():
    width, height, taille, chev = 450, 210, 128, 32
    couverture = np.zeros((height, width), dtype=int)
    for w in detect_cli.fenetres(width, height, taille, chev):
        couverture[
            int(w.row_off): int(w.row_off + w.height),
            int(w.col_off): int(w.col_off + w.width),
        ] += 1
    assert (couverture >= 1).all(), "chaque pixel doit être lu au moins une fois"


def test_fenetre_refuse_config_incoherente():
    import pytest

    with pytest.raises(ValueError):
        list(detect_cli.fenetres(100, 100, 64, 64))
