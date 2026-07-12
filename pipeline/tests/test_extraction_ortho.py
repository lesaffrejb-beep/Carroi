"""Tests de la logique PURE de 12_extraire_dalles_ortho.py.

On ne touche JAMAIS aux vraies archives (61 Go, absentes d'un clone) : index de
dalles et AOI sont des GeoDataFrame/géométries bidon en mémoire. On vérifie le
nettoyage du nom, la construction d'AOI (commune / bbox) et la sélection spatiale,
dont le piège du suffixe -IRC- (le nom réel de l'index prime, jamais reconstruit).
"""
import importlib.util
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

SRC = Path(__file__).resolve().parents[1] / "src"
spec = importlib.util.spec_from_file_location(
    "extraire_dalles_ortho", SRC / "12_extraire_dalles_ortho.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# --- nom_dalle -----------------------------------------------------------

def test_nom_dalle_retire_prefixe_point_slash():
    assert mod.nom_dalle("./49-2022-0405-6700-LA93-0M20-E080.jp2") == \
        "49-2022-0405-6700-LA93-0M20-E080.jp2"


def test_nom_dalle_conserve_suffixe_irc_sans_reconstruire():
    # Le nom IRC porte -IRC- : on le garde tel quel (pas de reconstruction).
    brut = "./49-2022-0440-6700-LA93-0M20-IRC-E080.jp2"
    assert mod.nom_dalle(brut) == "49-2022-0440-6700-LA93-0M20-IRC-E080.jp2"


def test_nom_dalle_sans_prefixe():
    assert mod.nom_dalle("49-2022-0405-6700-LA93-0M20-E080.jp2") == \
        "49-2022-0405-6700-LA93-0M20-E080.jp2"


def test_nom_dalle_none_leve():
    with pytest.raises(ValueError):
        mod.nom_dalle(None)


# --- aoi_depuis_bbox -----------------------------------------------------

def test_aoi_depuis_bbox_ok():
    aoi = mod.aoi_depuis_bbox(0, 0, 10, 10)
    assert aoi.area == 100


@pytest.mark.parametrize("bbox", [(10, 0, 0, 10), (0, 10, 10, 0), (0, 0, 0, 10)])
def test_aoi_depuis_bbox_invalide_leve(bbox):
    with pytest.raises(ValueError):
        mod.aoi_depuis_bbox(*bbox)


# --- aoi_depuis_commune --------------------------------------------------

def _parcelles_bidon():
    return gpd.GeoDataFrame(
        {"commune": ["49035", "49035", "49099"]},
        geometry=[box(0, 0, 5, 5), box(5, 0, 10, 5), box(100, 100, 110, 110)],
        crs="EPSG:2154",
    )


def test_aoi_depuis_commune_union():
    aoi = mod.aoi_depuis_commune(_parcelles_bidon(), "49035")
    # Deux parcelles jointives de 25 → union de 50, sans la parcelle 49099.
    assert aoi.area == pytest.approx(50)
    assert not aoi.intersects(box(100, 100, 110, 110))


def test_aoi_depuis_commune_absente_leve():
    with pytest.raises(ValueError):
        mod.aoi_depuis_commune(_parcelles_bidon(), "49999")


def test_aoi_depuis_commune_sans_colonne_leve():
    g = gpd.GeoDataFrame({"x": [1]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:2154")
    with pytest.raises(ValueError):
        mod.aoi_depuis_commune(g, "49035")


# --- selectionner_dalles -------------------------------------------------

def _index_bidon():
    # 3 dalles de 5×5, préfixe ./, dont une IRC pour tester les deux nommages.
    return gpd.GeoDataFrame(
        {"NOM": [
            "./49-2022-0000-0000-LA93-0M20-E080.jp2",       # couvre (0,0)-(5,5)
            "./49-2022-0005-0000-LA93-0M20-E080.jp2",       # couvre (5,0)-(10,5)
            "./49-2022-0100-0100-LA93-0M20-IRC-E080.jp2",   # loin (100,100)
        ]},
        geometry=[box(0, 0, 5, 5), box(5, 0, 10, 5), box(100, 100, 105, 105)],
        crs="EPSG:2154",
    )


def test_selectionner_dalles_intersection():
    aoi = box(1, 1, 6, 4)  # chevauche les deux premières dalles seulement
    noms = mod.selectionner_dalles(_index_bidon(), aoi)
    assert noms == [
        "49-2022-0000-0000-LA93-0M20-E080.jp2",
        "49-2022-0005-0000-LA93-0M20-E080.jp2",
    ]


def test_selectionner_dalles_garde_nom_irc_reel():
    aoi = box(100, 100, 105, 105)
    noms = mod.selectionner_dalles(_index_bidon(), aoi)
    assert noms == ["49-2022-0100-0100-LA93-0M20-IRC-E080.jp2"]


def test_selectionner_dalles_aucune():
    aoi = box(1000, 1000, 1010, 1010)
    assert mod.selectionner_dalles(_index_bidon(), aoi) == []


def test_selectionner_dalles_sans_colonne_nom_leve():
    g = gpd.GeoDataFrame({"x": [1]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:2154")
    with pytest.raises(ValueError):
        mod.selectionner_dalles(g, box(0, 0, 1, 1))
