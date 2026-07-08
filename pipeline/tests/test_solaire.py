"""Tests du moteur solaire sur terrains SYNTHÉTIQUES.

Chaque test encode une vérité physique vérifiable de tête : hauteur du soleil
à midi selon la saison, longueur d'une ombre = hauteur/tan(altitude), direction
de l'ombre opposée au soleil, durée du jour été vs hiver à la latitude du 49.
Si l'un casse, le moteur ment — et un score d'ensoleillement faux est invendable.
"""
from __future__ import annotations

import numpy as np
import pytest

import solaire

LAT_49 = 47.5  # latitude du Maine-et-Loire
RES = 0.5      # résolution MNS LiDAR HD


# ------------------------------------------------------------- astronomie

def test_declinaison_aux_dates_cles():
    assert np.degrees(solaire.declinaison(solaire.JOUR_SOLSTICE_ETE)) == pytest.approx(23.45, abs=0.2)
    assert np.degrees(solaire.declinaison(solaire.JOUR_SOLSTICE_HIVER)) == pytest.approx(-23.45, abs=0.4)
    assert np.degrees(solaire.declinaison(solaire.JOUR_EQUINOXE)) == pytest.approx(0.0, abs=1.5)
    with pytest.raises(ValueError):
        solaire.declinaison(0)


def test_hauteur_du_soleil_a_midi():
    """À midi solaire : altitude = 90° − latitude + déclinaison (formule exacte à midi)."""
    alt_eq, az_eq = solaire.position_soleil(LAT_49, solaire.JOUR_EQUINOXE, 12.0)
    assert np.degrees(alt_eq) == pytest.approx(90 - LAT_49, abs=1.5)
    assert np.degrees(az_eq) == pytest.approx(180.0, abs=2.0), "à midi le soleil est plein sud"

    alt_juin, _ = solaire.position_soleil(LAT_49, solaire.JOUR_SOLSTICE_ETE, 12.0)
    assert np.degrees(alt_juin) == pytest.approx(90 - LAT_49 + 23.45, abs=1.5)

    alt_dec, _ = solaire.position_soleil(LAT_49, solaire.JOUR_SOLSTICE_HIVER, 12.0)
    assert np.degrees(alt_dec) == pytest.approx(90 - LAT_49 - 23.45, abs=1.5)


def test_azimut_matin_est_apres_midi_ouest():
    _, az_matin = solaire.position_soleil(LAT_49, solaire.JOUR_EQUINOXE, 8.0)
    _, az_soir = solaire.position_soleil(LAT_49, solaire.JOUR_EQUINOXE, 16.0)
    assert np.degrees(az_matin) < 180, "le matin, le soleil est à l'est"
    assert np.degrees(az_soir) > 180, "l'après-midi, le soleil est à l'ouest"
    # Symétrie du temps solaire : altitudes égales de part et d'autre de midi.
    alt_m, _ = solaire.position_soleil(LAT_49, solaire.JOUR_EQUINOXE, 9.0)
    alt_s, _ = solaire.position_soleil(LAT_49, solaire.JOUR_EQUINOXE, 15.0)
    assert alt_m == pytest.approx(alt_s, abs=1e-6)


# ------------------------------------------------------------- ombres portées

def _terrain_plat(n=80):
    return np.zeros((n, n), dtype=np.float64)


def test_terrain_plat_aucune_ombre():
    ombre = solaire.ombres(_terrain_plat(), RES, np.radians(45), np.radians(180))
    assert not ombre.any()


def test_soleil_couche_tout_a_lombre():
    ombre = solaire.ombres(_terrain_plat(), RES, altitude=-0.1, azimut=0.0)
    assert ombre.all()


def test_mur_au_sud_ombre_vers_le_nord_et_longueur_exacte():
    """Mur de 10 m en ligne 50, soleil plein sud à 30° : ombre portée vers le
    nord (lignes < 50) sur hauteur/tan(30°) = 17,3 m = ~34 px à 0,5 m."""
    mns = _terrain_plat()
    mns[50, :] = 10.0
    ombre = solaire.ombres(mns, RES, np.radians(30), np.radians(180))
    portee_px = int(10.0 / np.tan(np.radians(30)) / RES)  # ≈ 34 px
    assert ombre[50 - 5, 40], "à 2,5 m au nord du mur : à l'ombre"
    assert ombre[50 - portee_px + 2, 40], "juste avant le bout de l'ombre : à l'ombre"
    assert not ombre[50 - portee_px - 3, 40], "au-delà de la portée de l'ombre : au soleil"
    assert not ombre[55, 40], "au SUD du mur (côté soleil) : au soleil"
    assert not ombre[50, 40], "le sommet du mur lui-même est au soleil"


def test_soleil_a_lest_ombre_vers_louest():
    mns = _terrain_plat()
    mns[:, 50] = 8.0
    ombre = solaire.ombres(mns, RES, np.radians(35), np.radians(90))
    assert ombre[40, 50 - 5], "à l'ouest du mur : à l'ombre"
    assert not ombre[40, 50 + 5], "à l'est du mur (côté soleil) : au soleil"


def test_ombre_diagonale_sud_ouest():
    """Soleil au sud-ouest (azimut 225°) : l'ombre part vers le nord-est."""
    mns = _terrain_plat()
    mns[40:43, 40:43] = 6.0  # bloc bâtiment
    ombre = solaire.ombres(mns, RES, np.radians(30), np.radians(225))
    assert ombre[36, 46] or ombre[35, 47], "ombre attendue au nord-est du bloc"
    assert not ombre[47, 33], "pas d'ombre au sud-ouest (côté soleil)"


def test_validation_des_entrees():
    with pytest.raises(ValueError):
        solaire.ombres(np.zeros(5), RES, 0.5, 0.5)
    with pytest.raises(ValueError):
        solaire.ombres(_terrain_plat(), -1.0, 0.5, 0.5)
    with pytest.raises(ValueError):
        solaire.position_soleil(120.0, 80, 12.0)


# ------------------------------------------------------------- heures de soleil

def test_duree_du_jour_ete_vs_hiver():
    """Terrain dégagé à 47,5°N : ~16 h de jour au solstice d'été, ~8 h en hiver.
    (Tolérances larges : altitude_min 2° et pas de 30 min rognent les extrémités.)"""
    plat = _terrain_plat(20)
    juin = solaire.heures_soleil_jour(plat, RES, LAT_49, solaire.JOUR_SOLSTICE_ETE)
    dec = solaire.heures_soleil_jour(plat, RES, LAT_49, solaire.JOUR_SOLSTICE_HIVER)
    assert 14.0 <= juin.max() <= 17.0
    assert 6.5 <= dec.max() <= 9.5
    assert (juin == juin.max()).all(), "terrain plat : tous les pixels reçoivent pareil"


def test_terrasse_au_nord_dun_mur_perd_des_heures():
    """La physique du produit pergola : au nord d'un mur = ombragé une bonne
    partie de la journée ; au sud du même mur = quasi plein soleil."""
    mns = _terrain_plat(60)
    mns[30, :] = 8.0  # mur est-ouest
    h = solaire.heures_soleil_jour(mns, RES, LAT_49, solaire.JOUR_EQUINOXE)
    nord_du_mur = h[30 - 6, 30]   # terrasse collée au nord du mur
    sud_du_mur = h[30 + 6, 30]    # terrasse au sud
    degage = h[55, 30]
    assert sud_du_mur == pytest.approx(degage, abs=0.51), "au sud : plein soleil"
    assert nord_du_mur < 0.5 * degage, "au nord : au moins moitié moins d'heures"


def test_score_trois_dates_coherent():
    plat = _terrain_plat(10)
    scores = solaire.score_trois_dates(plat, RES, LAT_49, pas_minutes=60)
    assert set(scores) == {"heures_soleil_juin", "heures_soleil_equinoxe", "heures_soleil_decembre"}
    assert scores["heures_soleil_juin"].max() > scores["heures_soleil_equinoxe"].max() \
        > scores["heures_soleil_decembre"].max()
