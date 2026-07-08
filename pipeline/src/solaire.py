"""Moteur solaire — heures de soleil direct sur un MNS (produit 2 Terrasses, réutilisable P3 Toitures).

Fonctions PURES numpy (MNS in → rasters out), testées sur terrains synthétiques
(pipeline/tests/test_solaire.py) — même philosophie que detection.py : verrouiller
l'algorithme avant la première dalle LiDAR HD réelle.

DÉCISION D'ARCHITECTURE (2026-07-08, remplace le choix « GRASS r.sun » de
docs/05-PIPELINE-TERRASSES.md §3) : implémentation native plutôt que r.sun.
Justification :
  - le besoin est un CLASSEMENT en heures de soleil direct (docs/05 §Pièges :
    « ce qui compte est le classement relatif, pas la valeur en kWh ») — pas
    d'irradiance, donc pas besoin de turbidité Linke ni de diffus ;
  - GRASS est une dépendance système lourde, non testable unitairement, fragile
    en environnement d'exécution managé ; ce module est du numpy pur ;
  - l'algorithme est le même dans son principe (ombres portées par balayage du
    MNS dans la direction du soleil).
Si un jour l'irradiance kWh devient un argument de vente, r.sun reste l'outil ;
consigner le changement dans 08-ROADMAP.md.

Algorithme :
  1. position_soleil : astronomie standard (déclinaison de Cooper, angle horaire)
     → altitude/azimut en temps solaire local. Précision ~1°, largement suffisante
     pour un score comparatif.
  2. ombres : projection d'ombres vectorisée « shift-and-compare » — un pixel est
     à l'ombre s'il existe, à k pas en direction du soleil, un point du MNS qui
     dépasse le rayon (élévation > k·res·tan(altitude)). O(portée/res) passes
     numpy sur toute la dalle, pas de boucle par pixel.
  3. heures_soleil_jour : échantillonnage de la journée (pas_minutes) → raster
     d'heures de soleil direct. Trois dates contractuelles (docs/05 §4) :
     21 juin (n=172), équinoxe (n=80), 21 décembre (n=355).

Limites documentées (assumées pour un score comparatif) :
  - portée d'ombre bornée (défaut 150 m) : un relief lointain n'ombrage pas ;
    le soleil très bas (< ~4°) est de toute façon peu discriminant.
  - temps solaire local (pas d'équation du temps) : décale l'heure, pas la durée.
"""
from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger("solaire")

JOUR_SOLSTICE_ETE = 172   # 21 juin
JOUR_EQUINOXE = 80        # ~21 mars
JOUR_SOLSTICE_HIVER = 355  # 21 décembre


def declinaison(jour: int) -> float:
    """Déclinaison solaire (radians) — formule de Cooper, précision ~0,3°."""
    if not 1 <= jour <= 366:
        raise ValueError(f"jour {jour} hors [1, 366]")
    return np.radians(23.45) * np.sin(2 * np.pi * (284 + jour) / 365)


def position_soleil(lat_deg: float, jour: int, heure_solaire: float) -> tuple[float, float]:
    """Altitude et azimut du soleil (radians). Azimut depuis le nord, horaire
    (est = π/2, sud = π). heure_solaire : temps solaire local décimal (12 = midi)."""
    if not -90 <= lat_deg <= 90:
        raise ValueError(f"latitude {lat_deg} invalide")
    phi = np.radians(lat_deg)
    delta = declinaison(jour)
    h = np.radians(15.0 * (heure_solaire - 12.0))  # angle horaire

    sin_alt = np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.cos(h)
    alt = np.arcsin(np.clip(sin_alt, -1.0, 1.0))

    cos_az = (np.sin(delta) - np.sin(phi) * sin_alt) / max(np.cos(phi) * np.cos(alt), 1e-12)
    az = np.arccos(np.clip(cos_az, -1.0, 1.0))
    if h > 0:  # après-midi : le soleil passe à l'ouest
        az = 2 * np.pi - az
    return float(alt), float(az)


def _decaler(arr: np.ndarray, drow: int, dcol: int) -> np.ndarray:
    """arr décalé de (drow, dcol), rempli à -inf hors emprise (pas d'obstacle)."""
    out = np.full_like(arr, -np.inf, dtype=np.float64)
    h, w = arr.shape
    r0, r1 = max(0, -drow), min(h, h - drow)
    c0, c1 = max(0, -dcol), min(w, w - dcol)
    if r0 < r1 and c0 < c1:
        out[r0:r1, c0:c1] = arr[r0 + drow: r1 + drow, c0 + dcol: c1 + dcol]
    return out


def ombres(
    mns: np.ndarray,
    res_m: float,
    altitude: float,
    azimut: float,
    portee_m: float = 150.0,
) -> np.ndarray:
    """Masque booléen des pixels À L'OMBRE pour une position de soleil donnée.

    Un pixel est ombré s'il existe un point du MNS, à distance d ≤ portee_m en
    direction du soleil, tel que mns[obstacle] − mns[pixel] > d·tan(altitude).
    Convention raster nord en haut : ligne 0 = nord, colonne 0 = ouest.
    """
    if mns.ndim != 2:
        raise ValueError(f"MNS 2D attendu, reçu {mns.shape}")
    if res_m <= 0:
        raise ValueError("res_m doit être > 0")
    if altitude <= 0:
        return np.ones(mns.shape, dtype=bool)  # soleil couché : tout à l'ombre

    # Vecteur unitaire (ligne, colonne) POINTANT VERS le soleil.
    drow = -np.cos(azimut)  # azimut 0 = nord = lignes décroissantes
    dcol = np.sin(azimut)   # azimut π/2 = est = colonnes croissantes
    tan_alt = np.tan(altitude)
    n_pas = int(np.ceil(portee_m / res_m))

    mns_f = mns.astype(np.float64)
    ombre = np.zeros(mns.shape, dtype=bool)
    for k in range(1, n_pas + 1):
        obstacle = _decaler(mns_f, int(round(k * drow)), int(round(k * dcol)))
        ombre |= (obstacle - mns_f) > (k * res_m * tan_alt + 1e-9)
    return ombre


def _decaler_1d(arr: np.ndarray, d: int) -> np.ndarray:
    """arr décalé de d (out[c] = arr[c+d]), rempli à -inf hors emprise."""
    if d == 0:
        return arr.copy()
    out = np.full_like(arr, -np.inf)
    n = arr.shape[0]
    if d > 0:
        out[: n - d] = arr[d:]
    else:
        out[-d:] = arr[: n + d]
    return out


def _propagation_lignes(mns: np.ndarray, res_m: float, drow: float, dcol: float,
                        tan_alt: float) -> np.ndarray:
    """Propagation d'horizon ligne par ligne. Précondition : |drow| ≥ |dcol|.

    R[p] = max(mns[p], R[p vers le soleil] − pas·tanα) : la hauteur du rayon
    rasant venant du soleil se propage en UNE passe sur la grille. Un pixel est
    à l'ombre si le rayon arrivant sur lui dépasse son élévation. La dérive de
    colonne (soleil non axial) est accumulée en sub-pixel et appliquée par
    décalages entiers (erreur bornée à ±0,5 px, sans dérive cumulative).
    """
    h, w = mns.shape
    pas = res_m / abs(drow)          # distance réelle parcourue entre deux lignes
    drop = pas * tan_alt
    derive = dcol / abs(drow)        # dérive de colonne par ligne, vers le soleil
    lignes = range(h - 1, -1, -1) if drow > 0 else range(h)

    ombre = np.zeros((h, w), dtype=bool)
    rayon_prec: np.ndarray | None = None
    frac = 0.0
    for r in lignes:
        ligne = mns[r]
        if rayon_prec is None:
            rayon = ligne.astype(np.float64, copy=True)
        else:
            frac += derive
            d = int(round(frac))
            frac -= d
            venant = _decaler_1d(rayon_prec, d) - drop
            ombre[r] = venant > ligne + 1e-9
            rayon = np.maximum(ligne, venant)
        rayon_prec = rayon
    return ombre


def ombres_rapide(mns: np.ndarray, res_m: float, altitude: float, azimut: float) -> np.ndarray:
    """Même sémantique qu'`ombres()` mais en UNE passe sur la grille (propagation
    d'horizon) au lieu de portée/res passes complètes : ~2 ordres de grandeur plus
    rapide, portée d'ombre illimitée. C'est ce qui rend le calcul départemental
    (produits 2 et 3) réaliste en Python pur.

    Différences assumées vs `ombres()` (l'oracle de référence, conservé) :
    discrétisation sub-pixel différente sur les azimuts obliques (équivalence
    exacte sur les azimuts cardinaux, ≥98 % de pixels identiques ailleurs —
    prouvé par pipeline/tests/test_solaire.py) ; pas de limite de portée.
    """
    if mns.ndim != 2:
        raise ValueError(f"MNS 2D attendu, reçu {mns.shape}")
    if res_m <= 0:
        raise ValueError("res_m doit être > 0")
    if altitude <= 0:
        return np.ones(mns.shape, dtype=bool)
    drow = -np.cos(azimut)
    dcol = np.sin(azimut)
    tan_alt = np.tan(altitude)
    mns_f = mns.astype(np.float64)
    if abs(drow) >= abs(dcol):
        return _propagation_lignes(mns_f, res_m, drow, dcol, tan_alt)
    # Axe dominant horizontal : on transpose le problème (lignes ↔ colonnes).
    return _propagation_lignes(mns_f.T, res_m, dcol, drow, tan_alt).T


def heures_soleil_jour(
    mns: np.ndarray,
    res_m: float,
    lat_deg: float,
    jour: int,
    pas_minutes: int = 30,
    portee_m: float = 150.0,
    altitude_min_deg: float = 2.0,
    algorithme: str = "rapide",
) -> np.ndarray:
    """Raster d'heures de soleil DIRECT reçues dans la journée (float, en heures).

    Échantillonne la journée par pas de pas_minutes ; chaque échantillon où le
    soleil est levé (altitude > altitude_min_deg, en dessous : rasant, non
    significatif pour une terrasse) ajoute pas_minutes/60 aux pixels éclairés.

    algorithme : "rapide" (propagation d'horizon, défaut — portee_m ignorée,
    portée illimitée) ou "reference" (shift-and-compare borné à portee_m,
    conservé comme oracle de validation).
    """
    if pas_minutes <= 0 or pas_minutes > 120:
        raise ValueError("pas_minutes doit être dans ]0, 120]")
    if algorithme not in ("rapide", "reference"):
        raise ValueError(f"algorithme inconnu : {algorithme}")
    heures = np.zeros(mns.shape, dtype=np.float64)
    poids = pas_minutes / 60.0
    n_ech = 0
    for minutes in range(0, 24 * 60, pas_minutes):
        alt, az = position_soleil(lat_deg, jour, minutes / 60.0)
        if np.degrees(alt) <= altitude_min_deg:
            continue
        if algorithme == "rapide":
            masque_ombre = ombres_rapide(mns, res_m, alt, az)
        else:
            masque_ombre = ombres(mns, res_m, alt, az, portee_m)
        heures += np.where(masque_ombre, 0.0, poids)
        n_ech += 1
    log.info("Jour %d (lat %.1f) : %d échantillons de soleil levé, max %.1f h.",
             jour, lat_deg, n_ech, float(heures.max()) if heures.size else 0.0)
    return heures


def score_trois_dates(
    mns: np.ndarray, res_m: float, lat_deg: float, **kwargs
) -> dict[str, np.ndarray]:
    """Les trois rasters contractuels de docs/05 §4 : juin, équinoxe, décembre."""
    return {
        "heures_soleil_juin": heures_soleil_jour(mns, res_m, lat_deg, JOUR_SOLSTICE_ETE, **kwargs),
        "heures_soleil_equinoxe": heures_soleil_jour(mns, res_m, lat_deg, JOUR_EQUINOXE, **kwargs),
        "heures_soleil_decembre": heures_soleil_jour(mns, res_m, lat_deg, JOUR_SOLSTICE_HIVER, **kwargs),
    }
