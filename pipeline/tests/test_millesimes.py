"""Tests du diff de millésimes — les cas qui décident si le produit premium
« nouvelles piscines » est vendable ou dangereux.

Le cas qui tue : une piscine EXISTANTE mal appariée devient une fausse
« nouvelle » → client démarché pour rien. Chaque test encode un cas limite réel
du recalage inter-millésimes.
"""
from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import Point

import millesimes


def _gdf(points, prefix="d"):
    return gpd.GeoDataFrame(
        {
            "id_detection": [f"{prefix}_{i}" for i in range(len(points))],
            "surface_m2": [30.0] * len(points),
            "score_detection": [0.8] * len(points),
            "methode": ["hsv"] * len(points),
        },
        geometry=[Point(x, y).buffer(3.0) for x, y in points],
        crs="EPSG:2154",
    )


def test_piscine_decalee_de_2m_est_conservee_pas_nouvelle():
    """LE cas qui tue le produit : recalage inter-millésimes de ~2 m — la
    piscine doit être appariée, jamais vendue comme nouvelle."""
    avant = _gdf([(100, 100)], "av")
    apres = _gdf([(102, 100.5)], "ap")
    r = millesimes.diff_millesimes(avant, apres)
    assert len(r["conservees"]) == 1
    assert len(r["nouvelles"]) == 0
    c = r["conservees"].iloc[0]
    assert c["id_detection_avant"] == "av_0"
    assert c["derive_m"] == pytest.approx(2.06, abs=0.1)


def test_vraie_nouvelle_et_vraie_disparue():
    avant = _gdf([(100, 100), (300, 300)], "av")           # 300,300 sera comblée
    apres = _gdf([(100, 100), (500, 500)], "ap")           # 500,500 est neuve
    r = millesimes.diff_millesimes(avant, apres)
    assert list(r["nouvelles"]["id_detection"]) == ["ap_1"]
    assert list(r["disparues"]["id_detection"]) == ["av_1"]
    assert len(r["conservees"]) == 1


def test_piscine_du_voisin_a_12m_n_est_pas_appariee():
    """Deux piscines à 12 m (tolérance 8 m) : l'ancienne est disparue, la
    nouvelle est nouvelle — pas d'appariement abusif entre voisins."""
    avant = _gdf([(100, 100)], "av")
    apres = _gdf([(112, 100)], "ap")
    r = millesimes.diff_millesimes(avant, apres, tolerance_m=8.0)
    assert len(r["nouvelles"]) == 1 and len(r["disparues"]) == 1


def test_appariement_un_pour_un_prend_la_plus_proche():
    """Deux piscines proches côté après, une seule avant : la PLUS PROCHE est
    appariée, l'autre est nouvelle — jamais deux appariements sur le même avant."""
    avant = _gdf([(100, 100)], "av")
    apres = _gdf([(101, 100), (106, 100)], "ap")  # à 1 m et 6 m
    r = millesimes.diff_millesimes(avant, apres)
    assert len(r["conservees"]) == 1
    assert r["conservees"].iloc[0]["derive_m"] == pytest.approx(1.0, abs=0.1)
    assert list(r["nouvelles"]["id_detection"]) == ["ap_1"]


def test_paires_croisees_resolues_par_distance():
    """Deux avant / deux après entrelacées : le glouton par distance croissante
    doit produire deux paires cohérentes (pas un chassé-croisé)."""
    avant = _gdf([(100, 100), (105, 100)], "av")
    apres = _gdf([(101, 100), (104, 100)], "ap")
    r = millesimes.diff_millesimes(avant, apres)
    assert len(r["conservees"]) == 2
    assert len(r["nouvelles"]) == 0 and len(r["disparues"]) == 0
    assert max(r["conservees"]["derive_m"]) <= 1.5


def test_ensembles_vides_et_erreurs():
    avant, apres = _gdf([(0, 0)]), _gdf([])
    r = millesimes.diff_millesimes(avant, apres)
    assert len(r["disparues"]) == 1 and len(r["nouvelles"]) == 0
    with pytest.raises(ValueError, match="tolerance"):
        millesimes.apparier(avant, avant, tolerance_m=0)
    with pytest.raises(ValueError, match="CRS"):
        millesimes.apparier(avant, _gdf([(0, 0)]).to_crs("EPSG:4326"))


def test_colonnes_preservees_pour_la_chaine_aval():
    """Les « nouvelles » repartent dans 20_join → 30 → 40 : le contrat couche 1
    doit être intact en sortie de diff."""
    import contrat

    avant = _gdf([(100, 100)], "av")
    apres = _gdf([(100, 100), (500, 500)], "ap")
    nouvelles = millesimes.diff_millesimes(avant, apres)["nouvelles"].reset_index(drop=True)
    contrat.valider_couche1(nouvelles)  # ne doit pas lever
