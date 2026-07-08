"""Équivalence ombres_rapide (propagation d'horizon, 1 passe) vs ombres (oracle).

L'oracle `ombres()` est trivialement juste (comparaison directe pixel-obstacle) ;
`ombres_rapide()` est l'algorithme de production (≈2 ordres de grandeur plus
rapide). Ces tests prouvent qu'on n'a pas troqué la justesse contre la vitesse :
égalité EXACTE sur les azimuts cardinaux, ≥98 % d'accord sur les obliques
(discrétisation sub-pixel différente, assumée et documentée).
"""
from __future__ import annotations

import numpy as np
import pytest

import solaire

RES = 0.5


def _terrain_aleatoire(seed: int, n: int = 96) -> np.ndarray:
    """Terrain synthétique réaliste : sol plat + blocs (bâtiments/murs/arbres)."""
    rng = np.random.default_rng(seed)
    mns = np.zeros((n, n))
    for _ in range(8):
        r, c = rng.integers(5, n - 20, 2)
        h_, w_ = rng.integers(3, 15, 2)
        mns[r: r + h_, c: c + w_] = rng.uniform(2.0, 18.0)
    return mns


@pytest.mark.parametrize("azimut_deg", [0.0, 90.0, 180.0, 270.0])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_equivalence_exacte_sur_azimuts_cardinaux(azimut_deg, seed):
    mns = _terrain_aleatoire(seed)
    alt, az = np.radians(25.0), np.radians(azimut_deg)
    portee = mns.shape[0] * RES * 2  # l'oracle couvre toute la grille
    ref = solaire.ombres(mns, RES, alt, az, portee_m=portee)
    rap = solaire.ombres_rapide(mns, RES, alt, az)
    assert (ref == rap).all(), (
        f"az={azimut_deg}°, seed={seed} : {int((ref != rap).sum())} pixels divergent"
    )


@pytest.mark.parametrize("azimut_deg", [37.0, 135.0, 222.5, 301.0])
@pytest.mark.parametrize("altitude_deg", [12.0, 35.0, 60.0])
def test_accord_sur_azimuts_obliques(azimut_deg, altitude_deg):
    mns = _terrain_aleatoire(seed=7)
    alt, az = np.radians(altitude_deg), np.radians(azimut_deg)
    ref = solaire.ombres(mns, RES, alt, az, portee_m=mns.shape[0] * RES * 2)
    rap = solaire.ombres_rapide(mns, RES, alt, az)
    desaccord = (ref != rap).mean()
    assert desaccord < 0.02, (
        f"az={azimut_deg}°, alt={altitude_deg}° : {desaccord:.1%} de désaccord (max 2 %)"
    )


def test_rapide_terrain_plat_et_soleil_couche():
    plat = np.zeros((40, 40))
    assert not solaire.ombres_rapide(plat, RES, np.radians(30), np.radians(180)).any()
    assert solaire.ombres_rapide(plat, RES, -0.05, 0.0).all()


def test_rapide_portee_illimitee():
    """Un obstacle LOINTAIN ombrage avec rapide (portée illimitée) mais pas avec
    l'oracle borné — c'est une amélioration de justesse, pas une régression."""
    n = 400  # 200 m
    mns = np.zeros((n, n))
    mns[390, :] = 30.0  # falaise/immeuble à ~190 m au sud du point testé
    alt, az = np.radians(8.0), np.radians(180.0)  # soleil bas : ombre de 213 m
    rap = solaire.ombres_rapide(mns, RES, alt, az)
    ref_borne = solaire.ombres(mns, RES, alt, az, portee_m=50.0)
    assert rap[10, 200], "l'obstacle lointain doit ombrager (portée illimitée)"
    assert not ref_borne[10, 200], "l'oracle borné à 50 m le rate (limite documentée)"


def test_heures_soleil_jour_deux_algorithmes_coherents():
    """Sur une journée complète, les deux algorithmes doivent raconter la même
    histoire physique (écart moyen < 15 min par pixel)."""
    mns = _terrain_aleatoire(seed=11, n=64)
    commun = dict(res_m=RES, lat_deg=47.5, jour=solaire.JOUR_EQUINOXE, pas_minutes=60)
    h_rap = solaire.heures_soleil_jour(mns, algorithme="rapide", **commun)
    h_ref = solaire.heures_soleil_jour(mns, algorithme="reference",
                                       portee_m=mns.shape[0] * RES * 2, **commun)
    assert np.abs(h_rap - h_ref).mean() < 0.25
    with pytest.raises(ValueError):
        solaire.heures_soleil_jour(mns, RES, 47.5, 80, algorithme="magique")
