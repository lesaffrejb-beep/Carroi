"""Corroboration adresse↔parcelle (mesure A4, docs/08) — ferme la faille du fallback
'nearest' : la jointure par proximité ne tombe dans la bonne parcelle que 23 % du temps
(vs 94 % via cad_parcelles). On vérifie ici :
  1. la primitive géométrique `corroborer_adresse_parcelle` (20_join) ;
  2. la règle de confiance durcie `calculer_confiance` (30_score), qui déclasse en
     « basse » toute adresse 'nearest' hors parcelle.
"""
from __future__ import annotations

import importlib

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box

join = importlib.import_module("20_join_piscines_adresses")
score = importlib.import_module("30_score_qualite")

CRS = "EPSG:2154"


def _parcelles():
    # Une seule parcelle P1 = carré 10×10 à l'origine.
    return gpd.GeoDataFrame({"id": ["P1"]}, geometry=[box(0, 0, 10, 10)], crs=CRS)


def _ban():
    # b_in : point dans la parcelle ; b_out : loin hors parcelle ; b_bord : à 1 m du bord.
    return gpd.GeoDataFrame(
        {"id_ban": ["b_in", "b_out", "b_bord"]},
        geometry=[Point(5, 5), Point(50, 50), Point(11, 5)],
        crs=CRS,
    )


def _out(rows):
    """`rows` : liste de (id_ban, id_parcelle). Géométrie piscine = petit carré interne."""
    return gpd.GeoDataFrame(
        {"id_ban": [r[0] for r in rows], "id_parcelle": [r[1] for r in rows]},
        geometry=[box(2, 2, 4, 4) for _ in rows],
        crs=CRS,
    )


# ------------------------------------------------------ primitive géométrique (20_join)

def test_adresse_dans_parcelle_true():
    out = _out([("b_in", "P1")])
    res = join.corroborer_adresse_parcelle(out, _ban(), _parcelles())
    assert res.iloc[0] is True or res.iloc[0] == True  # noqa: E712


def test_adresse_hors_parcelle_false():
    out = _out([("b_out", "P1")])
    res = join.corroborer_adresse_parcelle(out, _ban(), _parcelles())
    assert res.iloc[0] == False  # noqa: E712


def test_adresse_sans_id_ban_na():
    out = _out([(None, "P1")])
    res = join.corroborer_adresse_parcelle(out, _ban(), _parcelles())
    assert pd.isna(res.iloc[0])


def test_adresse_sans_id_parcelle_na():
    out = _out([("b_in", None)])
    res = join.corroborer_adresse_parcelle(out, _ban(), _parcelles())
    assert pd.isna(res.iloc[0])


def test_tolerance_2m_bord_de_parcelle():
    # b_bord est à 1 m du bord droit (< 2 m) → considéré dans la parcelle.
    out = _out([("b_bord", "P1")])
    res = join.corroborer_adresse_parcelle(out, _ban(), _parcelles())
    assert res.iloc[0] == True  # noqa: E712


# ---------------------------------------------------- règle de confiance durcie (30_score)

def test_confiance_nearest_hors_parcelle_declasse_en_basse():
    """Adresse trouvée par proximité ET hors de la parcelle → basse, même si proche
    et jointure non ambiguë (règle A4 : jamais haute/moyenne)."""
    gdf = pd.DataFrame({
        "jointure_ambigue": [False],
        "source_jointure": ["nearest"],
        "dist_adresse_m": [10.0],
        "adresse_dans_parcelle": pd.array([False], dtype="boolean"),
    })
    conf = score.calculer_confiance(gdf, dist_max_adresse_m=100)
    assert conf[0] == "basse"


def test_confiance_cad_parcelles_dans_parcelle_haute():
    gdf = pd.DataFrame({
        "jointure_ambigue": [False],
        "source_jointure": ["cad_parcelles"],
        "dist_adresse_m": [10.0],
        "adresse_dans_parcelle": pd.array([True], dtype="boolean"),
    })
    conf = score.calculer_confiance(gdf, dist_max_adresse_m=100)
    assert conf[0] == "haute"


def test_confiance_cad_parcelles_hors_parcelle_pas_haute():
    """cad_parcelles mais point hors parcelle : perd la haute confiance (→ moyenne)."""
    gdf = pd.DataFrame({
        "jointure_ambigue": [False],
        "source_jointure": ["cad_parcelles"],
        "dist_adresse_m": [10.0],
        "adresse_dans_parcelle": pd.array([False], dtype="boolean"),
    })
    conf = score.calculer_confiance(gdf, dist_max_adresse_m=100)
    assert conf[0] == "moyenne"


def test_confiance_retrocompat_sans_colonne():
    """Parquet ancienne génération (pas de colonne) → comportement historique conservé :
    cad_parcelles + non-ambiguë + proche = haute."""
    gdf = pd.DataFrame({
        "jointure_ambigue": [False],
        "source_jointure": ["cad_parcelles"],
        "dist_adresse_m": [10.0],
    })
    conf = score.calculer_confiance(gdf, dist_max_adresse_m=100)
    assert conf[0] == "haute"
