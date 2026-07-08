"""Cœur du produit 2 — zones jardin & classification d'ensoleillement (fonctions pures).

Complète `solaire.py` (qui calcule les heures de soleil sur le MNS) avec la partie
métier : où est la terrasse potentielle, et se vend-elle ? Spec : docs/05 §Architecture.
L'orchestration par dalles vit dans 25_terrasses.py ; ici tout est testable à sec
(pipeline/tests/test_terrasses.py).

Pièges traités (et testés) :
  - « la cime d'un arbre ensoleillé n'est pas une terrasse » : les pixels de
    sursol (MNH > seuil) sont EXCLUS du masque de zone avant classification —
    sans ça, la canopée d'un jardin arboré compte comme surface plein-soleil.
  - la classe se joue sur une surface CONTIGUË (composante connexe ≥ 20 m²),
    pas sur une moyenne : 40 pixels de soleil éparpillés entre les ombres ne
    font pas une terrasse.
"""
from __future__ import annotations

import logging

import numpy as np
from rasterio import features
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union
from skimage import measure

log = logging.getLogger("terrasses")

SECTEURS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]


def zone_jardin(
    parcelle: Polygon,
    batiments: list,
    dist_facade_m: float,
    tampon_limite_m: float,
    surface_min_m2: float,
):
    """Zone « terrasse potentielle » d'une parcelle bâtie, ou None.

    Définition (docs/05 §2) : parcelle érodée du tampon de limite (on ne vend pas
    la bande le long de la clôture du voisin), moins l'emprise bâtie, restreinte
    à moins de dist_facade_m de la façade (une pergola se vend adossée ou proche).
    """
    bati = unary_union([b for b in batiments if b.intersects(parcelle)])
    if bati.is_empty:
        return None  # parcelle non bâtie : pas un prospect pergola
    zone = parcelle.buffer(-tampon_limite_m)
    zone = zone.difference(bati.buffer(0.5))  # 0,5 m de mur/gouttière
    zone = zone.intersection(bati.buffer(dist_facade_m))
    if zone.is_empty or zone.area < surface_min_m2:
        return None
    return zone


def orientation_zone(zone, bati) -> tuple[float, str]:
    """Azimut (degrés, depuis le nord, horaire) du barycentre de la zone vu du
    bâtiment + secteur 8 directions. Sud/Sud-Ouest = argument de vente."""
    dx = zone.centroid.x - bati.centroid.x
    dy = zone.centroid.y - bati.centroid.y
    az = float(np.degrees(np.arctan2(dx, dy)) % 360.0)
    secteur = SECTEURS[int(((az + 22.5) % 360) // 45)]
    return round(az, 1), secteur


def rasteriser_zone(zone, transform, shape: tuple[int, int]) -> np.ndarray:
    """Masque booléen des pixels de la zone sur la grille du MNS."""
    geoms = list(zone.geoms) if isinstance(zone, MultiPolygon) else [zone]
    return features.rasterize(
        [(g, 1) for g in geoms], out_shape=shape, transform=transform,
        fill=0, dtype="uint8",
    ).astype(bool)


def masque_sol(masque_zone: np.ndarray, mnh: np.ndarray | None, hauteur_max_m: float) -> np.ndarray:
    """Retire du masque les pixels de sursol (arbres, abris…) : MNH > hauteur_max.

    Sans MNH, retourne le masque inchangé — l'appelant doit avoir loggé la
    dégradation (la canopée ensoleillée comptera à tort comme terrasse)."""
    if mnh is None:
        return masque_zone
    if mnh.shape != masque_zone.shape:
        raise ValueError(f"MNH {mnh.shape} ≠ masque {masque_zone.shape}")
    return masque_zone & (mnh <= hauteur_max_m)


def _surface_contigue_max(ok: np.ndarray, px_m2: float) -> float:
    """Surface (m²) de la plus grande composante connexe de pixels True."""
    if not ok.any():
        return 0.0
    labels = measure.label(ok, connectivity=1)
    return float(np.bincount(labels.ravel())[1:].max() * px_m2)


def classifier_soleil(
    h_juin: np.ndarray,
    h_equinoxe: np.ndarray,
    masque: np.ndarray,
    res_m: float,
    seuils: dict,
) -> dict:
    """Classe de vente d'une zone : plein_soleil / bon / ombrage (exclu de la vente).

    La classe exige une surface CONTIGUË ≥ surface_contigue_min_m2 satisfaisant
    les seuils juin ET équinoxe (docs/05 §4). Retourne aussi les moyennes
    d'heures sur la zone (attributs du livrable) et le score ∈ [0,1].
    """
    if not masque.any():
        return {"classe_soleil": "ombrage", "surface_plein_soleil_m2": 0.0,
                "heures_soleil_juin": 0.0, "heures_soleil_equinoxe": 0.0,
                "score_detection": 0.0}
    px_m2 = res_m * res_m
    ps, bon = seuils["plein_soleil"], seuils["bon"]
    s_min = seuils["surface_contigue_min_m2"]

    ok_ps = masque & (h_juin >= ps["juin_min_h"]) & (h_equinoxe >= ps["equinoxe_min_h"])
    surf_ps = _surface_contigue_max(ok_ps, px_m2)
    ok_bon = masque & (h_juin >= bon["juin_min_h"]) & (h_equinoxe >= bon["equinoxe_min_h"])
    surf_bon = _surface_contigue_max(ok_bon, px_m2)

    if surf_ps >= s_min:
        classe = "plein_soleil"
    elif surf_bon >= s_min:
        classe = "bon"
    else:
        classe = "ombrage"

    juin_moy = float(h_juin[masque].mean())
    eq_moy = float(h_equinoxe[masque].mean())
    # Score comparatif : moyenne normalisée par les durées de jour à ~47°N.
    score = 0.5 * min(juin_moy / 16.0, 1.0) + 0.5 * min(eq_moy / 12.0, 1.0)
    return {
        "classe_soleil": classe,
        "surface_plein_soleil_m2": round(surf_ps, 1),
        "heures_soleil_juin": round(juin_moy, 2),
        "heures_soleil_equinoxe": round(eq_moy, 2),
        "score_detection": round(score, 3),
    }
