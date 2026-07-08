"""Cœur algorithmique de la détection de piscines sur BD ORTHO (étape 1b, option B).

Fonctions PURES (numpy in → geodataframe out), sans I/O : c'est ce qui les rend
testables sur imagerie synthétique (pipeline/tests/test_detection.py) avant de
toucher une seule dalle réelle. L'orchestration par dalles/fenêtres vit dans
15_detect_piscines.py.

Principe (spec docs/04-PIPELINE-PISCINES.md étape 1b) :
  1. masque_eau      — seuillage HSV (teinte cyan de l'eau traitée) + garde-fous
                       spectraux IRC : NDVI bas (pas de végétation), NDWI haut
                       (signature eau : le proche IR est absorbé par l'eau).
  2. nettoyer_masque — morphologie : retire le bruit, ferme les trous (échelle,
                       reflets), sans déformer les contours.
  3. extraire_candidats — vectorisation géoréférencée + filtres de forme
                       (surface, compacité, solidité) + score de confiance.
  4. fusionner_adjacentes — recolle les morceaux d'une même piscine coupée par
                       une limite de dalle.

Le score_detection est une heuristique v0 (spectral + forme), à calibrer sur la
commune test (roadmap B2) ; tout changement de seuil se fait dans config.yaml
et se consigne dans 08-ROADMAP.md.
"""
from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
from rasterio import features
from scipy import ndimage
from shapely.geometry import shape
from shapely.ops import unary_union
from skimage import measure, morphology
from skimage.color import rgb2hsv
from skimage.util import img_as_float

log = logging.getLogger("detection")

_EPS = 1e-9


def masque_eau(rgb: np.ndarray, nir: np.ndarray | None, seuils: dict) -> np.ndarray:
    """Masque booléen des pixels « eau de piscine » d'une fenêtre.

    rgb : HxWx3 (uint8 ou float 0-1). nir : HxW ou None (dégradé sans IRC :
    le seuillage HSV seul travaille, le tri humain rattrape les faux positifs
    végétation — mais la précision chute, l'IRC est fortement recommandé).
    """
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"rgb attendu HxWx3, reçu {rgb.shape}")
    rgb_f = img_as_float(rgb)
    hsv = rgb2hsv(rgb_f)
    h = seuils["hsv"]
    mask = (
        (hsv[..., 0] >= h["hue_min"]) & (hsv[..., 0] <= h["hue_max"])
        & (hsv[..., 1] >= h["sat_min"]) & (hsv[..., 2] >= h["val_min"])
    )
    if nir is not None:
        if nir.shape != rgb.shape[:2]:
            raise ValueError(f"nir {nir.shape} ne correspond pas à rgb {rgb.shape[:2]}")
        nir_f = img_as_float(nir)
        r, g = rgb_f[..., 0], rgb_f[..., 1]
        ndvi = (nir_f - r) / (nir_f + r + _EPS)
        ndwi = (g - nir_f) / (g + nir_f + _EPS)
        i = seuils["irc"]
        mask &= (ndvi <= i["ndvi_max"]) & (ndwi >= i["ndwi_min"])
    return mask


def nettoyer_masque(mask: np.ndarray, min_px: int) -> np.ndarray:
    """Morphologie : retire les objets < min_px, ferme les petits trous
    (échelles, margelles réfléchissantes, bouées) sans grossir les contours."""
    if min_px < 1:
        raise ValueError("min_px doit être ≥ 1")
    out = morphology.remove_small_objects(mask, max_size=min_px - 1)
    out = morphology.closing(out, morphology.disk(2))
    out = ndimage.binary_fill_holes(out)
    # Le closing peut recréer de petits objets par pontage : repasse finale.
    return morphology.remove_small_objects(out, max_size=min_px - 1)


def _compacite(area_px: float, perimetre_px: float) -> float:
    """4πA/P² — 1.0 pour un disque, →0 pour une forme filandreuse."""
    if perimetre_px <= 0:
        return 0.0
    return float(min(1.0, 4.0 * np.pi * area_px / perimetre_px**2))


def score_candidat(compacite: float, ndwi_moyen: float | None, seuils: dict) -> float:
    """Score de confiance v0 ∈ [0,1] : moitié forme, moitié signature spectrale.

    Sans IRC, la composante spectrale est remplacée par la forme seule (score
    plus conservateur, documenté dans la colonne `methode`).
    """
    s_forme = compacite
    if ndwi_moyen is None:
        return round(s_forme, 3)
    ndwi_min = seuils["irc"]["ndwi_min"]
    # Normalise le NDWI entre le seuil d'entrée et 0.4 (eau franche).
    s_spectral = float(np.clip((ndwi_moyen - ndwi_min) / (0.4 - ndwi_min), 0.0, 1.0))
    return round(0.5 * s_forme + 0.5 * s_spectral, 3)


def extraire_candidats(
    mask: np.ndarray,
    rgb: np.ndarray,
    nir: np.ndarray | None,
    transform,
    res_m: float,
    seuils: dict,
) -> gpd.GeoDataFrame:
    """Vectorise le masque nettoyé et applique les filtres de forme.

    Retourne un GeoDataFrame (EPSG à fixer par l'appelant) avec :
    geometry, surface_m2, compacite, solidite, score_detection.
    Chaque rejet est compté et loggé — pas de perte silencieuse.
    """
    forme = seuils["forme"]
    px_m2 = res_m * res_m

    labels = measure.label(mask, connectivity=2)
    if labels.max() == 0:
        return _gdf_vide()

    # Polygones géoréférencés par label (une piscine = un label connexe).
    geoms_par_label: dict[int, list] = {}
    for geom, val in features.shapes(
        labels.astype(np.int32), mask=labels > 0, transform=transform
    ):
        geoms_par_label.setdefault(int(val), []).append(shape(geom))

    rgb_f = img_as_float(rgb)
    nir_f = img_as_float(nir) if nir is not None else None

    lignes, rejets = [], {"surface": 0, "compacite": 0, "solidite": 0, "score": 0}
    for region in measure.regionprops(labels):
        surface_m2 = region.area * px_m2
        if not (forme["surface_min_m2"] <= surface_m2 <= forme["surface_max_m2"]):
            rejets["surface"] += 1
            continue
        compacite = _compacite(region.area, region.perimeter)
        if compacite < forme["compacite_min"]:
            rejets["compacite"] += 1
            continue
        if region.solidity < forme["solidite_min"]:
            rejets["solidite"] += 1
            continue

        ndwi_moyen = None
        if nir_f is not None:
            rr, cc = region.coords[:, 0], region.coords[:, 1]
            g, n = rgb_f[rr, cc, 1], nir_f[rr, cc]
            ndwi_moyen = float(np.mean((g - n) / (g + n + _EPS)))
        score = score_candidat(compacite, ndwi_moyen, seuils)
        if score < seuils["score_min"]:
            rejets["score"] += 1
            continue

        poly = unary_union(geoms_par_label[region.label])
        lignes.append(
            {
                "geometry": poly,
                "surface_m2": round(surface_m2, 1),
                "compacite": round(compacite, 3),
                "solidite": round(float(region.solidity), 3),
                "score_detection": score,
            }
        )

    log.info(
        "Candidats : %d retenus, rejets %s (sur %d composantes).",
        len(lignes), rejets, labels.max(),
    )
    if not lignes:
        return _gdf_vide()
    return gpd.GeoDataFrame(lignes, geometry="geometry")


def fusionner_adjacentes(gdf: gpd.GeoDataFrame, tolerance_m: float = 0.5) -> gpd.GeoDataFrame:
    """Recolle les morceaux d'une même piscine coupée par une limite de dalle.

    Deux candidats à moins de `tolerance_m` l'un de l'autre sont fusionnés :
    géométries unies, surface recalculée, score = max (le morceau le mieux vu
    l'emporte). Ne fusionne PAS deux vraies piscines voisines : à 20 cm de
    résolution, deux bassins distincts sont séparés par bien plus de 0,5 m.
    """
    if len(gdf) <= 1:
        return gdf.reset_index(drop=True)
    buffered = gdf.geometry.buffer(tolerance_m / 2.0)
    # Graphe de connexité via l'index spatial, puis composantes connexes.
    parent = list(range(len(gdf)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    sidx = buffered.sindex
    for i, geom in enumerate(buffered.values):
        for j in sidx.query(geom, predicate="intersects"):
            j = int(j)
            if j != i:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri

    groupes: dict[int, list[int]] = {}
    for i in range(len(gdf)):
        groupes.setdefault(find(i), []).append(i)

    lignes = []
    for membres in groupes.values():
        sous = gdf.iloc[membres]
        if len(membres) == 1:
            lignes.append(sous.iloc[0].to_dict())
            continue
        geom = unary_union(sous.geometry.values)
        lignes.append(
            {
                **sous.loc[sous["score_detection"].idxmax()].to_dict(),
                "geometry": geom,
                "surface_m2": round(geom.area, 1),
            }
        )
    n_fusions = len(gdf) - len(lignes)
    if n_fusions:
        log.info("Fusion inter-dalles : %d morceau(x) recollé(s).", n_fusions)
    return gpd.GeoDataFrame(lignes, geometry="geometry", crs=gdf.crs).reset_index(drop=True)


def _gdf_vide() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "surface_m2": [], "compacite": [], "solidite": [], "score_detection": [],
        },
        geometry=gpd.GeoSeries([]),
    )
