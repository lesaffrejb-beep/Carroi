"""Tests du contrat de couche 1 (contrat.py) — le garde-fou que tout futur
détecteur (parkings, toitures, n'importe quoi) devra passer, y compris le scan
anti-données-nominatives (garde-fou légal n°1, automatisé)."""
from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import Point, Polygon, box

import contrat


def _gdf_valide(n=3):
    return gpd.GeoDataFrame(
        {
            "surface_m2": [30.0] * n,
            "score_detection": [0.8] * n,
            "methode": ["hsv"] * n,
            "id_detection": list(range(n)),
        },
        geometry=[box(i, i, i + 5, i + 5) for i in range(n)],
        crs="EPSG:2154",
    )


def test_sortie_valide_passe():
    contrat.valider_couche1(_gdf_valide())


def test_sortie_vide_refusee():
    with pytest.raises(ValueError, match="vide"):
        contrat.valider_couche1(_gdf_valide(0).iloc[0:0])


def test_colonne_requise_manquante():
    g = _gdf_valide().drop(columns=["score_detection"])
    with pytest.raises(ValueError, match="score_detection"):
        contrat.valider_couche1(g)


def test_colonnes_nominatives_refusees():
    """Le garde-fou légal automatisé : aucune session future ne peut glisser une
    colonne nominative dans la chaîne sans casser le pipeline immédiatement."""
    for col in ["nom_proprietaire", "telephone", "Email_contact", "prenom", "siret"]:
        g = _gdf_valide()
        g[col] = "x"
        with pytest.raises(ValueError, match="NOMINATIVE"):
            contrat.valider_couche1(g)


def test_exceptions_adresse_postale_acceptees():
    g = _gdf_valide()
    g["nom_voie"] = "rue des Lilas"
    g["nom_commune"] = "Angers"
    contrat.valider_couche1(g)  # ne doit pas lever


def test_mauvais_crs_refuse():
    g = _gdf_valide().to_crs("EPSG:4326")
    with pytest.raises(ValueError, match="CRS"):
        contrat.valider_couche1(g)


def test_score_hors_bornes_refuse():
    g = _gdf_valide()
    g.loc[0, "score_detection"] = 1.7
    with pytest.raises(ValueError, match="score_detection"):
        contrat.valider_couche1(g)


def test_geometrie_invalide_refusee():
    g = _gdf_valide()
    papillon = Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])  # auto-intersection
    g.loc[0, "geometry"] = papillon
    with pytest.raises(ValueError, match="invalide"):
        contrat.valider_couche1(g)


def test_ids_dupliques_refuses():
    g = _gdf_valide()
    g["id_detection"] = [0, 0, 1]
    with pytest.raises(ValueError, match="uniques"):
        contrat.valider_couche1(g)


def test_toutes_les_violations_listees_dune_fois():
    """Une seule levée avec TOUTES les violations : on corrige tout d'un coup."""
    g = _gdf_valide().drop(columns=["methode"])
    g["telephone"] = "x"
    g.loc[0, "surface_m2"] = -1
    with pytest.raises(ValueError) as exc:
        contrat.valider_couche1(g)
    msg = str(exc.value)
    assert "methode" in msg and "NOMINATIVE" in msg and "surface_m2" in msg
