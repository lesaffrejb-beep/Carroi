"""Tests de 21_appliquer_concordance : les verdicts humains de la page de
vérification d'adresse s'appliquent à la base adressée sans rien fabriquer."""
from __future__ import annotations

import importlib

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

conc_mod = importlib.import_module("21_appliquer_concordance")


def _base():
    adressees = gpd.GeoDataFrame(
        {
            "id_piscine": ["p1", "p2", "p3"],
            "id_ban": ["A", "B", "C"],
            "adresse": ["1 rue a", "2 rue b", "3 rue c"],
            "commune": ["X", "X", "X"],
            "dist_adresse_m": [10.0, 20.0, 30.0],
            "adresse_dans_parcelle": [True, False, True],
            "source_jointure": ["cad_parcelles", "nearest", "nearest"],
        },
        geometry=[Polygon([(0, 0), (1, 0), (1, 1)]),
                  Polygon([(10, 10), (11, 10), (11, 11)]),
                  Polygon([(20, 20), (21, 20), (21, 21)])],
        crs="EPSG:2154",
    )
    ban = gpd.GeoDataFrame(
        {"id_ban": ["A", "B", "C", "D"],
         "numero": [1, 2, 3, 4.0], "rep": [None, None, None, "bis"],
         "nom_voie": ["rue a", "rue b", "rue c", "rue d"],
         "code_postal": ["49080"] * 4, "nom_commune": ["X"] * 4,
         "code_insee": ["49035"] * 4},
        geometry=[Point(0, 5), Point(10, 15), Point(20, 25), Point(24, 20)],
        crs="EPSG:2154",
    )
    return adressees, ban


def test_confirme_corrige_et_aucune():
    adressees, ban = _base()
    conc = pd.DataFrame({
        "id_piscine": ["p1", "p2", "p3"],
        "id_ban_choisi_humain": ["A", "aucune", "D"],   # confirme / retire / corrige
    })
    out = conc_mod.appliquer_concordance(adressees, ban, conc)

    assert out["verif_humaine"].all()
    # p1 confirmée : rien ne bouge sauf le flag
    assert out.loc[out.id_piscine == "p1", "id_ban"].iloc[0] == "A"
    # p2 'aucune' : adresse retirée
    p2 = out.loc[out.id_piscine == "p2"].iloc[0]
    assert pd.isna(p2["id_ban"]) and p2["source_jointure"] == "humain_aucune"
    # p3 corrigée vers D : attributs BAN rapatriés, distance recalculée, pas de
    # corroboration parcellaire inventée
    p3 = out.loc[out.id_piscine == "p3"].iloc[0]
    assert p3["id_ban"] == "D" and p3["adresse"] == "4 bis rue d"
    assert p3["source_jointure"] == "humain" and pd.isna(p3["adresse_dans_parcelle"])
    assert p3["dist_adresse_m"] == pytest.approx(3.0)
    # l'original n'est pas modifié (copie)
    assert adressees.loc[adressees.id_piscine == "p3", "id_ban"].iloc[0] == "C"


def test_id_piscine_inconnu_refuse():
    adressees, ban = _base()
    conc = pd.DataFrame({"id_piscine": ["zz"], "id_ban_choisi_humain": ["A"]})
    with pytest.raises(ValueError, match="inconnus"):
        conc_mod.appliquer_concordance(adressees, ban, conc)


def test_id_ban_inconnu_refuse():
    adressees, ban = _base()
    conc = pd.DataFrame({"id_piscine": ["p1"], "id_ban_choisi_humain": ["ZZZ"]})
    with pytest.raises(ValueError, match="absents de la BAN"):
        conc_mod.appliquer_concordance(adressees, ban, conc)


def test_confiance_verif_humaine_prime():
    score = importlib.import_module("30_score_qualite")
    gdf = pd.DataFrame({
        "jointure_ambigue": [False, False, False],
        "source_jointure": ["nearest", "nearest", "humain"],
        "dist_adresse_m": [140.0, 30.0, 90.0],
        "adresse_dans_parcelle": [False, False, None],
        "id_ban": ["A", None, "D"],
        "verif_humaine": [True, True, True],
    })
    conf = list(score.calculer_confiance(gdf, dist_max_adresse_m=150))
    assert conf[0] == "haute"      # vérifiée humain, adresse présente → haute
    assert conf[1] != "haute"      # 'aucune' (id_ban NaN) : pas de promotion
    assert conf[2] == "haute"      # corrigée humain → haute
