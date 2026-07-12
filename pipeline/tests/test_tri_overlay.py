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


# ------------------------------------------------------- HTML de la planche
# Le front doit être auto-explicatif et transmissible à un tiers : on vérifie
# côté Python que le HTML généré contient les blocs clés (pas de test JS).

def _items():
    return [
        {"id": "pisc_a", "png": "vignettes/pisc_a.png", "surface": 30.0,
         "score": 0.8, "corrobore": 1},
        {"id": "pisc_b", "png": "vignettes/pisc_b.png", "surface": 12.0,
         "score": 0.5, "corrobore": 0},
    ]


def test_rendre_html_bandeau_question_et_touches():
    """Bandeau d'accueil : la question en gros, le compteur, la jauge de
    progression et le rappel des touches (dont Z/← pour annuler)."""
    html = tri.rendre_html(_items(), "49")
    assert "CONTOUR ROUGE" in html
    assert 'id="compteur"' in html and 'id="jauge"' in html
    assert "Reste ${reste} à trier" in html  # gabarit JS du compteur dynamique
    assert "<kbd>O</kbd>" in html and "<kbd>N</kbd>" in html and "<kbd>U</kbd>" in html
    assert "<kbd>Z</kbd>" in html and "annuler la dernière décision" in html
    assert "function annuler()" in html and "histo.pop()" in html


def test_rendre_html_regles_du_jeu():
    """Panneau repliable « règles du jeu » avec le texte de consigne exact."""
    html = tri.rendre_html(_items(), "49")
    assert 'id="regles"' in html and "<summary>" in html
    assert "EXISTENCE" in html and "pas son adresse" in html
    assert "n'est JAMAIS vendu" in html
    assert "IGNOREZ-la, jugez uniquement le contour rouge" in html
    assert "O quand même (la géométrie est recollée ailleurs)" in html
    assert "⌂ cadastré" in html and "limites de parcelles cadastrales" in html


def test_rendre_html_items_persistance_et_export():
    """Les candidats sont embarqués (avec corrobore pour le badge/data-attribute),
    la persistance localStorage est par département, et l'export garde le contrat
    CSV id_detection,decision. L'export prévient s'il reste des non-triés
    (seuil 2 %) mais exporte quand même."""
    html = tri.rendre_html(_items(), "49")
    assert '"id": "pisc_a"' in html and '"corrobore": 1' in html
    assert "dataset.corrobore" in html
    assert 'tri_piscines_49' in html  # clé localStorage : reprise par département
    assert "localStorage.setItem(CLE" in html
    assert 'id="btn-export"' in html and "Exporter decisions.csv" in html
    assert "id_detection,decision" in html
    assert "refusera au-delà de 2 %" in html
    assert "exporté quand même" in html


def test_rendre_html_navigation_et_correction():
    """Après décision, saut à la prochaine non triée ; les cartes triées restent
    marquées (classes dec-*) et re-cliquables pour corriger."""
    html = tri.rendre_html(_items(), "49")
    assert "premierNonTrie" in html and "scrollIntoView" in html
    assert ".dec-oui" in html and ".dec-non" in html and ".dec-incertain" in html
    assert 'addEventListener("click"' in html
    assert 'loading="lazy"' in html  # 977 vignettes : chargement paresseux obligatoire
