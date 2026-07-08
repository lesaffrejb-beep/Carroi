"""Géométrie d'exploitabilité — la plus grande poche rectangulaire libre d'une emprise.

Le problème commun aux produits « ombrières de parking » (loi APER) et « parcelles
divisibles » (docs/14 §4) : dans une emprise donnée (parking, parcelle), en évitant
des obstacles (bâtiments, arbres via MNH, ombrières existantes), quelle est la plus
grande surface rectangulaire d'un seul tenant, et dans quelle orientation ?

Le rectangle inscrit maximal dans un polygone quelconque est un problème dur en
exact ; on résout en approché — largement suffisant pour SCORER et TRIER des
milliers de sites (on vend un classement et des faits mesurés, pas un permis) :
  1. rotation de l'espace libre sur N orientations (0-90°, symétrie du rectangle) ;
  2. rastérisation du libre à `res_m` ;
  3. plus grand rectangle plein dans la matrice binaire : méthode de l'histogramme
     par pile, O(lignes × colonnes) — exacte sur la grille ;
  4. re-projection du meilleur rectangle dans le repère d'origine.

Précision : bornée par res_m et le pas angulaire (90°/N). Avec res_m=0.5 et N=12,
l'erreur de surface observée en tests est < 15 % — voir test_geometrie.py.

Fonctions PURES, sans I/O, testées à sec (même doctrine que detection.py/solaire.py).
"""
from __future__ import annotations

import logging

import numpy as np
from rasterio import features
from rasterio.transform import from_origin
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

log = logging.getLogger("geometrie")


def _plus_grand_rectangle_matrice(libre: np.ndarray) -> tuple[int, int, int, int, int]:
    """Plus grand rectangle de True dans une matrice binaire.

    Méthode de l'histogramme par pile (classique, exacte, O(h×w)) : chaque ligne
    devient la base d'un histogramme de hauteurs de colonnes libres ; le plus
    grand rectangle sous histogramme se calcule en O(w) par pile monotone.
    Retourne (aire_px, ligne_haut, col_gauche, hauteur_px, largeur_px).
    """
    h, w = libre.shape
    hauteurs = np.zeros(w, dtype=np.int32)
    meilleur = (0, 0, 0, 0, 0)
    for r in range(h):
        hauteurs = np.where(libre[r], hauteurs + 1, 0)
        pile: list[int] = []  # indices de colonnes, hauteurs croissantes
        c = 0
        while c <= w:
            courante = hauteurs[c] if c < w else 0
            if not pile or hauteurs[pile[-1]] <= courante:
                pile.append(c)
                c += 1
            else:
                sommet = pile.pop()
                haut = int(hauteurs[sommet])
                gauche = pile[-1] + 1 if pile else 0
                aire = haut * (c - gauche)
                if aire > meilleur[0]:
                    meilleur = (aire, r - haut + 1, gauche, haut, c - gauche)
    return meilleur


def plus_grand_rectangle_libre(
    zone,
    obstacles=None,
    res_m: float = 0.5,
    n_orientations: int = 12,
):
    """Plus grand rectangle inscrit dans `zone` moins `obstacles`, orientation libre.

    Retourne None si l'espace libre est vide, sinon un dict :
      rectangle (Polygon, repère d'origine), surface_m2, largeur_m, longueur_m,
      angle_deg (orientation du grand côté), surface_libre_m2 (tout le libre).
    """
    if res_m <= 0:
        raise ValueError("res_m doit être > 0")
    if n_orientations < 1:
        raise ValueError("n_orientations doit être ≥ 1")
    libre = zone
    if obstacles:
        libre = zone.difference(unary_union([o for o in obstacles]))
    if libre.is_empty or libre.area < res_m * res_m:
        return None

    origine = libre.centroid
    meilleur = None  # (surface_m2, rect_polygon_origine, angle, h_m, w_m)
    for k in range(n_orientations):
        angle = 90.0 * k / n_orientations
        tourne = affinity.rotate(libre, -angle, origin=origine)
        minx, miny, maxx, maxy = tourne.bounds
        w_px = max(1, int(np.ceil((maxx - minx) / res_m)))
        h_px = max(1, int(np.ceil((maxy - miny) / res_m)))
        if w_px * h_px > 40_000_000:
            raise ValueError(
                f"Emprise trop grande pour res_m={res_m} ({w_px}×{h_px} px) — "
                "augmenter res_m (on score des sites, pas des départements entiers)."
            )
        transform = from_origin(minx, maxy, res_m, res_m)
        geoms = list(tourne.geoms) if isinstance(tourne, MultiPolygon) else [tourne]
        grille = features.rasterize(
            [(g, 1) for g in geoms], out_shape=(h_px, w_px), transform=transform,
            fill=0, all_touched=False, dtype="uint8",
        ).astype(bool)
        aire_px, r0, c0, hh, ww = _plus_grand_rectangle_matrice(grille)
        if aire_px == 0:
            continue
        surface = aire_px * res_m * res_m
        if meilleur is None or surface > meilleur[0]:
            # Coins du rectangle en coordonnées du repère tourné…
            x0, y1 = transform * (c0, r0)
            x1, y0 = transform * (c0 + ww, r0 + hh)
            rect = box(x0, y0, x1, y1)
            # …re-projeté dans le repère d'origine.
            rect = affinity.rotate(rect, angle, origin=origine)
            cotes = sorted([ww * res_m, hh * res_m])
            grand_cote_vertical = hh >= ww
            angle_grand_cote = (angle + (90.0 if grand_cote_vertical else 0.0)) % 180.0
            meilleur = (surface, rect, angle_grand_cote, cotes[0], cotes[1])

    if meilleur is None:
        return None
    surface, rect, angle_gc, petit, grand = meilleur
    return {
        "rectangle": rect,
        "surface_m2": round(surface, 1),
        "largeur_m": round(petit, 2),
        "longueur_m": round(grand, 2),
        "angle_deg": round(angle_gc, 1),
        "surface_libre_m2": round(libre.area, 1),
    }


def poche_libre(
    emprise: Polygon,
    obstacles=None,
    res_m: float = 0.5,
    n_orientations: int = 12,
) -> dict:
    """Vue « exploitabilité » d'une emprise : surface libre totale + rectangle max.

    C'est l'attribut vendable des produits ombrières (surface équipable d'un seul
    tenant) et foncier (poche constructible d'un fond de jardin). Retourne toujours
    un dict (surface nulle si rien de libre) — l'appelant filtre sur les seuils.
    """
    r = plus_grand_rectangle_libre(emprise, obstacles, res_m, n_orientations)
    if r is None:
        return {"surface_libre_m2": 0.0, "rect_surface_m2": 0.0,
                "rect_largeur_m": 0.0, "rect_longueur_m": 0.0,
                "rect_angle_deg": None, "rectangle": None}
    return {
        "surface_libre_m2": r["surface_libre_m2"],
        "rect_surface_m2": r["surface_m2"],
        "rect_largeur_m": r["largeur_m"],
        "rect_longueur_m": r["longueur_m"],
        "rect_angle_deg": r["angle_deg"],
        "rectangle": r["rectangle"],
    }
