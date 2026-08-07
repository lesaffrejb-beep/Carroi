"""Tests des candidats CoSIA (24) et de la reprise des signalements (26).

Tout ce qui est testé ici est PUR : pas de GPKG, pas de disque externe.
"""
from __future__ import annotations

import importlib
import math

import geopandas as gpd
import pytest
from shapely.geometry import Point, box

m24 = importlib.import_module("24_candidats_cosia")
m26 = importlib.import_module("26_signalements_candidats")


def test_bbox_bloc_coin_nord():
    """RÉGRESSION (2026-08-06) : le Y du nom d'un bloc CoSIA est le coin NORD.
    L'avoir lu comme un coin SUD faisait chercher les piscines 10 km trop bas —
    aucune erreur levée, juste 58 points de rappel perdus en silence."""
    assert m24.bbox_bloc("D049_2022_420_6710_vecto.gpkg") == (420000, 6700000, 430000, 6710000)
    assert m24.bbox_bloc("D049_2022_370_6680_vecto.gpkg") == (370000, 6670000, 380000, 6680000)
    assert m24.bbox_bloc("pas_un_bloc.gpkg") is None


def test_attributs_forme():
    """Un disque : compacité ≈ 1, solidité ≈ 1. Un rectangle allongé : compacité
    faible, solidité 1 (convexe)."""
    g = gpd.GeoDataFrame(
        geometry=[Point(0, 0).buffer(5, quad_segs=64), box(0, 0, 40, 1)],
        crs="EPSG:2154")
    out = m24.attributs_forme(g)
    assert out.loc[0, "surface_m2"] == pytest.approx(math.pi * 25, rel=0.01)
    assert out.loc[0, "compacite"] > 0.99
    assert out.loc[0, "solidite"] > 0.99
    assert out.loc[1, "compacite"] < 0.2
    assert out.loc[1, "solidite"] > 0.99


def test_construire_candidats_corroboration_et_orphelins():
    """CoSIA seul → 'cosia' ; CoSIA + symbole PCI proche → 'cosia+pci' ;
    symbole PCI sans CoSIA → candidat 'pci_sym65' (rattrapage des couvertes)."""
    cosia = gpd.GeoDataFrame(
        geometry=[Point(0, 0).buffer(3), Point(100, 0).buffer(3)],
        data={"dalle": ["b1", "b1"]}, crs="EPSG:2154")
    pci = gpd.GeoDataFrame(
        geometry=[Point(1, 0).buffer(2),        # à 1 m du 1er CoSIA → corrobore
                  Point(500, 500).buffer(3)],   # isolé → orphelin
        crs="EPSG:2154")
    out = m24.construire_candidats(cosia, pci, s_min=3.0, s_max=150.0)
    assert sorted(out["methode"]) == ["cosia", "cosia+pci", "pci_sym65"]
    scores = dict(zip(out["methode"], out["score_detection"]))
    assert scores["cosia+pci"] > scores["cosia"] > scores["pci_sym65"]


def test_construire_candidats_filtre_surface():
    """Les bornes de surface s'appliquent à TOUTES les sources."""
    cosia = gpd.GeoDataFrame(
        geometry=[Point(0, 0).buffer(0.5),    # ~0,8 m² : trop petit
                  Point(50, 0).buffer(3),     # ~28 m² : gardé
                  Point(200, 0).buffer(20)],  # ~1250 m² : trop grand
        data={"dalle": ["b"] * 3}, crs="EPSG:2154")
    out = m24.construire_candidats(cosia, None, s_min=3.0, s_max=150.0)
    assert len(out) == 1


def test_fusionner_clics_par_item():
    """Deux clics du même item à < 10 m = une intention (le farmer réajuste) ;
    au-delà, ou sur un autre item, ce sont des signalements distincts."""
    pts = [("a", 0, 0), ("a", 3, 0), ("a", 50, 0), ("b", 0, 0), ("b", 1, 1)]
    out = m26.fusionner_clics(pts)
    assert out == [("a", 0, 0), ("a", 50, 0), ("b", 0, 0)]
    assert m26.fusionner_clics([]) == []


def test_construire_signalements_chaine_de_decision():
    """L'ordre compte : déjà-candidat > récupération CoSIA > disque nu."""
    deja = gpd.GeoDataFrame(
        {"id_detection": ["x"]}, geometry=[Point(0, 0).buffer(2)], crs="EPSG:2154")
    cosia = gpd.GeoDataFrame(geometry=[Point(100, 0).buffer(3)], crs="EPSG:2154")
    parcelles = gpd.GeoDataFrame(
        {"commune": ["49035"]}, geometry=[box(-50, -50, 250, 250)], crs="EPSG:2154")
    points = [("i", 0, 0),        # sur un candidat existant → ignoré
              ("i", 100, 0),      # sous un polygone CoSIA → récupéré
              ("i", 200, 200)]    # rien → disque
    cand, stats = m26.construire(points, deja, cosia, parcelles, "EPSG:2154")
    assert stats == {"deja_candidat": 1, "recupere_cosia": 1, "point_nu": 1}
    assert sorted(cand["methode"]) == ["signale+cosia", "signale_humain"]
    assert set(cand["commune"]) == {"49035"}
    # le disque nu a bien le rayon par défaut
    nu = cand[cand["methode"] == "signale_humain"].iloc[0]
    assert nu["surface_m2"] == pytest.approx(math.pi * m26.RAYON_DEFAUT_M ** 2, rel=0.02)


def test_communes_alm_completes():
    """Les 29 communes d'Angers Loire Métropole (source geo.api.gouv.fr,
    EPCI 244900015, relevé 2026-08-06) — Bouchemaine incluse (commune étalon)."""
    assert len(m24.COMMUNES_ALM) == 29
    assert len(set(m24.COMMUNES_ALM)) == 29
    assert "49007" in m24.COMMUNES_ALM      # Angers
    assert "49035" in m24.COMMUNES_ALM      # Bouchemaine
    assert all(c.startswith("49") and len(c) == 5 for c in m24.COMMUNES_ALM)
