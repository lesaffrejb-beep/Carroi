"""Tests du cœur géométrique (geometrie.py) — rectangle libre maximal.

Les cas encodent les situations métier des produits ombrières/foncier :
parking rectangulaire, forme en L, obstacle central (bâtiment/arbres),
emprise orientée en biais (le monde réel n'est pas aligné au nord).
"""
from __future__ import annotations

import numpy as np
import pytest
from shapely import affinity
from shapely.geometry import Polygon, box

import geometrie


def test_matrice_histogramme_exacte():
    m = np.zeros((6, 8), dtype=bool)
    m[1:5, 2:7] = True   # bloc 4×5 = 20 px
    m[0, 0] = True
    aire, r0, c0, h, w = geometrie._plus_grand_rectangle_matrice(m)
    assert (aire, r0, c0, h, w) == (20, 1, 2, 4, 5)


def test_carre_simple():
    r = geometrie.plus_grand_rectangle_libre(box(0, 0, 20, 20), res_m=0.5)
    assert r["surface_m2"] == pytest.approx(400, rel=0.10)
    assert r["surface_libre_m2"] == pytest.approx(400, rel=0.01)


def test_forme_en_L_prend_la_grande_branche():
    # L : branche horizontale 40×10, branche verticale 10×30 (au-dessus).
    L = box(0, 0, 40, 10).union(box(0, 10, 10, 40))
    r = geometrie.plus_grand_rectangle_libre(L, res_m=0.5)
    # La meilleure poche rectangulaire est la branche 40×10 = 400 m²
    # (la verticale fait 10×40=400 aussi — les deux réponses sont valides).
    assert r["surface_m2"] == pytest.approx(400, rel=0.12)
    assert r["longueur_m"] == pytest.approx(40, rel=0.15)
    assert r["largeur_m"] == pytest.approx(10, rel=0.15)


def test_obstacle_central_coupe_la_poche():
    """Parking 60×30 avec un bâtiment 10×10 au centre : la poche max est le
    flanc ouest/est du bâtiment (25×30 = 750 m²), pas la pleine emprise —
    et pas la bande nord (60×10 = 600 m²), plus longue mais plus petite."""
    parking = box(0, 0, 60, 30)
    batiment = box(25, 10, 35, 20)
    r = geometrie.plus_grand_rectangle_libre(parking, [batiment], res_m=0.5)
    assert r["surface_m2"] == pytest.approx(750, rel=0.10)
    assert not r["rectangle"].intersects(batiment.buffer(-0.6)), \
        "le rectangle ne doit pas mordre l'obstacle"


def test_emprise_en_biais_retrouvee_par_rotation():
    """Un parking rectangulaire tourné de 30° : sans balayage d'orientations on
    perdrait ~la moitié de la surface ; avec, on retrouve presque tout."""
    droit = box(0, 0, 50, 20)  # 1000 m²
    biais = affinity.rotate(droit, 30, origin="centroid")
    r = geometrie.plus_grand_rectangle_libre(biais, res_m=0.5, n_orientations=12)
    assert r["surface_m2"] > 0.85 * 1000, f"seulement {r['surface_m2']} m² retrouvés"
    # L'angle du grand côté doit être proche de 30° (modulo la grille de 7,5°).
    assert min(abs(r["angle_deg"] - 30), abs(r["angle_deg"] - 30 - 180)) <= 8.0


def test_vide_et_entrees_invalides():
    assert geometrie.plus_grand_rectangle_libre(
        box(0, 0, 10, 10), [box(-1, -1, 11, 11)]) is None
    with pytest.raises(ValueError):
        geometrie.plus_grand_rectangle_libre(box(0, 0, 1, 1), res_m=0)
    with pytest.raises(ValueError):
        geometrie.plus_grand_rectangle_libre(box(0, 0, 1, 1), n_orientations=0)


def test_poche_libre_contrat_de_sortie():
    """poche_libre retourne TOUJOURS un dict aux mêmes clés (l'appelant filtre) —
    c'est ce que consommeront les extracteurs ombrières/foncier."""
    plein = geometrie.poche_libre(box(0, 0, 30, 30), [box(5, 5, 25, 25)])
    vide = geometrie.poche_libre(box(0, 0, 2, 2), [box(-1, -1, 3, 3)])
    assert set(plein) == set(vide)
    assert vide["rect_surface_m2"] == 0.0 and vide["rectangle"] is None
    # Carré 30×30 moins carré central 20×20 : bande de 5 m → rect max 30×5 = 150 m².
    assert plein["rect_surface_m2"] == pytest.approx(150, rel=0.12)


def test_cas_metier_fond_de_jardin():
    """Parcelle 15×50 m, maison 12×10 côté rue : la poche du fond doit faire
    ~15×38 m — c'est l'attribut « divisible » du produit foncier."""
    parcelle = box(0, 0, 15, 50)
    maison = box(1.5, 40, 13.5, 50)
    p = geometrie.poche_libre(parcelle, [maison])
    assert p["rect_surface_m2"] >= 0.85 * (15 * 38)
    assert p["rect_longueur_m"] == pytest.approx(39.5, rel=0.10)
