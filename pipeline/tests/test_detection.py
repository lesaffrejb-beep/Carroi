"""Tests du cœur de détection sur imagerie SYNTHÉTIQUE.

But : verrouiller le comportement de l'algorithme (ce qu'il doit trouver, ce
qu'il doit rejeter, la justesse du géoréférencement) avant tout run sur dalles
réelles. Chaque scène encode un cas métier documenté dans
docs/04-PIPELINE-PISCINES.md étape 1b.
"""
from __future__ import annotations

import numpy as np
import pytest
from rasterio.transform import from_origin
from shapely.geometry import box

import detection

RES = 0.2  # m/px, résolution BD ORTHO

SEUILS = {
    "hsv": {"hue_min": 0.42, "hue_max": 0.62, "sat_min": 0.15, "val_min": 0.25},
    "irc": {"band_nir": 1, "ndvi_max": 0.10, "ndwi_min": -0.05},
    "forme": {"surface_min_m2": 4, "surface_max_m2": 400,
              "compacite_min": 0.30, "solidite_min": 0.65},
    "score_min": 0.35,
}

# Signatures spectrales synthétiques (RGB uint8, NIR uint8)
PELOUSE = ((80, 140, 60), 200)     # végétation : NIR fort
PISCINE = ((60, 180, 200), 30)     # eau traitée : cyan, NIR absorbé
CONIFERE_BLEUTE = ((70, 130, 140), 220)  # végétation bleutée : HSV piège, NIR trahit
TOLE_MARINE = ((30, 50, 120), 90)  # trampoline/bâche marine : teinte hors fenêtre


def scene(taille=512):
    """Pelouse uniforme + NIR végétation."""
    rgb = np.zeros((taille, taille, 3), dtype=np.uint8)
    rgb[..., :] = PELOUSE[0]
    nir = np.full((taille, taille), PELOUSE[1], dtype=np.uint8)
    return rgb, nir


def poser_ellipse(rgb, nir, centre, rayons, couleur):
    yy, xx = np.ogrid[: rgb.shape[0], : rgb.shape[1]]
    m = ((yy - centre[0]) / rayons[0]) ** 2 + ((xx - centre[1]) / rayons[1]) ** 2 <= 1
    rgb[m] = couleur[0]
    nir[m] = couleur[1]
    return m


def poser_rect(rgb, nir, r0, c0, r1, c1, couleur):
    rgb[r0:r1, c0:c1] = couleur[0]
    nir[r0:r1, c0:c1] = couleur[1]


TRANSFORM = from_origin(1000.0, 2000.0, RES, RES)


def detecter(rgb, nir):
    mask = detection.masque_eau(rgb, nir, SEUILS)
    min_px = max(1, int(SEUILS["forme"]["surface_min_m2"] / (RES * RES) * 0.5))
    mask = detection.nettoyer_masque(mask, min_px)
    return detection.extraire_candidats(mask, rgb, nir, TRANSFORM, RES, SEUILS)


def test_masque_eau_separe_piscine_et_pelouse():
    rgb, nir = scene()
    m_pisc = poser_ellipse(rgb, nir, (256, 256), (25, 15), PISCINE)
    mask = detection.masque_eau(rgb, nir, SEUILS)
    assert mask[m_pisc].mean() > 0.99, "la piscine doit être entièrement masquée eau"
    assert mask[~m_pisc].mean() < 0.01, "la pelouse ne doit pas être masquée eau"


def test_detection_piscine_surface_et_georeferencement():
    rgb, nir = scene()
    poser_ellipse(rgb, nir, (256, 256), (25, 15), PISCINE)  # ~47 m²
    cand = detecter(rgb, nir)
    assert len(cand) == 1
    row = cand.iloc[0]
    surface_attendue = np.pi * 25 * 15 * RES * RES
    assert row["surface_m2"] == pytest.approx(surface_attendue, rel=0.20)
    assert row["score_detection"] >= SEUILS["score_min"]
    # Géoréférencement : centre pixel (256,256) → monde (1000+256·0.2, 2000−256·0.2)
    c = row.geometry.centroid
    assert c.x == pytest.approx(1000 + 256 * RES, abs=0.5)
    assert c.y == pytest.approx(2000 - 256 * RES, abs=0.5)


def test_trou_dans_la_piscine_rebouche():
    """Échelle/reflet au milieu du bassin : fill_holes doit reboucher."""
    rgb, nir = scene()
    poser_ellipse(rgb, nir, (256, 256), (25, 15), PISCINE)
    poser_rect(rgb, nir, 252, 252, 258, 258, PELOUSE)  # reflet central
    cand = detecter(rgb, nir)
    assert len(cand) == 1
    assert cand.iloc[0]["surface_m2"] == pytest.approx(np.pi * 25 * 15 * RES * RES, rel=0.20)


def test_vegetation_bleutee_rejetee_grace_a_lirc():
    """Un conifère bleuté passe le seuillage HSV mais pas le NDVI : c'est
    exactement la valeur ajoutée de l'IRC (docs/02 §BD ORTHO)."""
    rgb, nir = scene()
    poser_ellipse(rgb, nir, (128, 128), (20, 20), CONIFERE_BLEUTE)
    poser_ellipse(rgb, nir, (350, 350), (25, 15), PISCINE)
    avec_irc = detecter(rgb, nir)
    assert len(avec_irc) == 1, "avec IRC : seule la piscine"

    sans_irc_mask = detection.masque_eau(rgb, None, SEUILS)
    min_px = max(1, int(SEUILS["forme"]["surface_min_m2"] / (RES * RES) * 0.5))
    sans_irc = detection.extraire_candidats(
        detection.nettoyer_masque(sans_irc_mask, min_px), rgb, None, TRANSFORM, RES, SEUILS
    )
    assert len(sans_irc) == 2, "sans IRC : le conifère devient un faux positif (dégradation documentée)"


def test_bache_marine_rejetee_par_teinte():
    rgb, nir = scene()
    poser_ellipse(rgb, nir, (128, 128), (15, 15), TOLE_MARINE)
    assert detecter(rgb, nir).empty


def test_fosse_cyan_rejete_par_compacite():
    """Fossé/reflet linéaire couleur eau : surface plausible mais forme filandreuse."""
    rgb, nir = scene()
    poser_rect(rgb, nir, 250, 100, 254, 420, PISCINE)  # 0.8 m × 64 m ≈ 51 m²
    assert detecter(rgb, nir).empty


def test_trop_petit_et_trop_grand_rejetes():
    rgb, nir = scene()
    poser_ellipse(rgb, nir, (60, 60), (3, 3), PISCINE)        # ~1.1 m² : bruit
    poser_ellipse(rgb, nir, (300, 256), (180, 90), PISCINE)   # ~2000 m² : plan d'eau
    assert detecter(rgb, nir).empty


def test_deux_piscines_distinctes_restent_distinctes():
    rgb, nir = scene()
    poser_ellipse(rgb, nir, (150, 150), (20, 12), PISCINE)
    poser_ellipse(rgb, nir, (350, 350), (25, 15), PISCINE)
    cand = detecter(rgb, nir)
    assert len(cand) == 2
    fus = detection.fusionner_adjacentes(cand.set_crs("EPSG:2154"))
    assert len(fus) == 2, "deux bassins distincts ne doivent JAMAIS être fusionnés"


def test_fusion_recolle_une_piscine_coupee_par_une_dalle():
    """Simule une piscine coupée en deux par une limite de dalle : les deux
    moitiés se touchent → une seule ligne, surface recombinée."""
    import geopandas as gpd

    gauche = box(100.0, 100.0, 104.0, 106.0)
    droite = box(104.0, 100.0, 108.0, 106.0)   # bord commun x=104
    loin = box(500.0, 500.0, 506.0, 506.0)
    gdf = gpd.GeoDataFrame(
        {
            "surface_m2": [24.0, 24.0, 36.0],
            "compacite": [0.6, 0.6, 0.8],
            "solidite": [1.0, 1.0, 1.0],
            "score_detection": [0.5, 0.7, 0.9],
        },
        geometry=[gauche, droite, loin], crs="EPSG:2154",
    )
    fus = detection.fusionner_adjacentes(gdf)
    assert len(fus) == 2
    recollee = fus.loc[fus["surface_m2"].idxmax()]
    assert recollee["surface_m2"] == pytest.approx(48.0)
    assert recollee["score_detection"] == 0.7, "le score du morceau le mieux vu l'emporte"


def test_masque_eau_valide_les_dimensions():
    with pytest.raises(ValueError):
        detection.masque_eau(np.zeros((10, 10), dtype=np.uint8), None, SEUILS)
    with pytest.raises(ValueError):
        detection.masque_eau(
            np.zeros((10, 10, 3), dtype=np.uint8), np.zeros((5, 5), dtype=np.uint8), SEUILS
        )
