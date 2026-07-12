"""Tests des fonctions pures de surimpression cadastrale du tri visuel
(16_tri_visuel) : transformation monde→pixel, corroboration cadastre à <5 m, et
robustesse quand les fichiers parcelles/PCI sont absents.
"""
from __future__ import annotations

import importlib

import geopandas as gpd
import numpy as np
from shapely.geometry import Point, box

tri = importlib.import_module("16_tri_visuel")


# ------------------------------------------------ transformation monde → pixel

def test_monde_vers_pixel_centre_et_bords():
    """Le centre du crop tombe au milieu de la vignette ; le nord est en haut
    (axe Y inversé)."""
    cx, cy, cote, px = 1000.0, 2000.0, 60.0, 300
    # centre -> (150, 150)
    assert tri.monde_vers_pixel(cx, cy, cx, cy, cote, px) == (150.0, 150.0)
    # coin nord-ouest (x-demi, y+demi) -> (0, 0)
    assert tri.monde_vers_pixel(cx - 30, cy + 30, cx, cy, cote, px) == (0.0, 0.0)
    # un point plus au nord a un 'row' plus petit (plus haut dans l'image)
    _, row_nord = tri.monde_vers_pixel(cx, cy + 10, cx, cy, cote, px)
    _, row_sud = tri.monde_vers_pixel(cx, cy - 10, cx, cy, cote, px)
    assert row_nord < row_sud


# --------------------------------------------------- corroboration cadastre

def _pci(geoms):
    return gpd.GeoDataFrame({"SYM": ["65"] * len(geoms)}, geometry=geoms, crs="EPSG:2154")


def test_corrobore_vrai_sous_5m():
    """Un candidat à moins de 5 m d'une piscine SYM=65 est corroboré."""
    pci = _pci([box(0, 0, 4, 4)])
    cand = box(6, 0, 8, 4)  # 2 m du bord droit de la piscine
    assert tri.corrobore_cadastre(cand, pci) is True


def test_corrobore_faux_au_dela_de_5m():
    """Au-delà de 5 m, pas de corroboration."""
    pci = _pci([box(0, 0, 4, 4)])
    cand = box(20, 0, 22, 4)  # 16 m
    assert tri.corrobore_cadastre(cand, pci) is False


def test_corrobore_robuste_pci_absent():
    """PCI None ou GeoDataFrame vide → False, jamais d'exception (robustesse)."""
    assert tri.corrobore_cadastre(box(0, 0, 1, 1), None) is False
    vide = gpd.GeoDataFrame({"SYM": []}, geometry=[], crs="EPSG:2154")
    assert tri.corrobore_cadastre(box(0, 0, 1, 1), vide) is False


def test_corrobore_geometrie_vide():
    pci = _pci([box(0, 0, 4, 4)])
    assert tri.corrobore_cadastre(None, pci) is False


# ------------------------------------------- robustesse chargement de fichiers

def test_charger_parcelles_absent_renvoie_none(tmp_path):
    """Fichier parcelles absent → None + warning, pas d'échec."""
    cfg = {"paths": {"interim": str(tmp_path)}, "dept": "49"}
    assert tri.charger_parcelles(cfg) is None


def test_charger_pci_absent_renvoie_none(tmp_path):
    """Aucun piscines_pci_sym65_*.parquet → None, pas d'échec."""
    cfg = {"paths": {"interim": str(tmp_path)}, "dept": "49"}
    assert tri.charger_pci_piscines(cfg) is None


def test_charger_pci_concatene_et_filtre_sym65(tmp_path):
    """Plusieurs fichiers PCI sont concaténés ; seules les géométries SYM=65 restent."""
    g1 = gpd.GeoDataFrame({"SYM": ["65", "40"]},
                          geometry=[box(0, 0, 1, 1), box(2, 2, 3, 3)], crs="EPSG:2154")
    g2 = gpd.GeoDataFrame({"SYM": ["65"]}, geometry=[box(5, 5, 6, 6)], crs="EPSG:2154")
    g1.to_parquet(tmp_path / "piscines_pci_sym65_49035.parquet")
    g2.to_parquet(tmp_path / "piscines_pci_sym65_49308.parquet")
    cfg = {"paths": {"interim": str(tmp_path)}, "dept": "49"}
    out = tri.charger_pci_piscines(cfg)
    assert len(out) == 2  # les deux SYM=65, le SYM=40 est écarté
    assert set(out["SYM"].astype(str)) == {"65"}


# ---------------------------------------------------- dessin de surimpression

def test_dessiner_surimpression_modifie_les_pixels():
    """Le contour du candidat est bien peint sur la vignette (des pixels changent)."""
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    cand = box(995, 1995, 1005, 2005)  # centré sur (1000, 2000)
    out = tri.dessiner_surimpression(img, 1000.0, 2000.0, 60.0, 300, cand, None)
    assert out.shape == img.shape
    assert out.sum() > 0, "le contour vif du candidat doit peindre des pixels"


def test_dessiner_surimpression_sans_parcelles_ne_plante_pas():
    """parcelles=None : pas de limites tracées, mais aucune erreur."""
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    out = tri.dessiner_surimpression(img, 0.0, 0.0, 60.0, 300, Point(0, 0).buffer(5), None)
    assert out.shape == img.shape
