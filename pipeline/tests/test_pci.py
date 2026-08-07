"""Tests des fonctions pures de `11_pci_piscines` (piscines cadastrées PCI SYM=65).

Aucun réseau, aucun téléchargement : on couvre le parsing de l'index HTML de
cadastre.data.gouv.fr, la construction des URLs et le filtrage du symbole 65 —
c'est-à-dire tout ce qui peut casser SILENCIEUSEMENT si la source change de
forme (un index mal parsé rend « commune sans piscine », pas une erreur).

Le fixture HTML reproduit l'index nginx réel relevé le 2026-08-07 : le nom de
l'archive y apparaît DEUX fois par ligne (href + texte), d'où le besoin de
déduplication.
"""
from __future__ import annotations

import importlib

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

pci = importlib.import_module("11_pci_piscines")


INDEX_HTML = """<!DOCTYPE html><html>
<head><title>dgfip-pci-vecteur/2026-06-01/edigeo/feuilles/49/49035/</title></head>
<body><h1>Index of /dgfip-pci-vecteur/2026-06-01/edigeo/feuilles/49/49035/</h1>
<table id="list"><tbody>
<tr><td><a href="../">..</a></td></tr>
<tr>
<td><a href="/data/dgfip-pci-vecteur/2026-06-01/edigeo/feuilles/49/49035/edigeo-490350000B01.tar.bz2">edigeo-490350000B01.tar.bz2</a></td>
<td>105620</td><td>2026-07-03T10:31:33.000Z</td>
</tr>
<tr>
<td><a href="/data/dgfip-pci-vecteur/2026-06-01/edigeo/feuilles/49/49035/edigeo-490350000A03.tar.bz2">edigeo-490350000A03.tar.bz2</a></td>
<td>54101</td><td>2026-07-03T10:31:33.000Z</td>
</tr>
<tr>
<td><a href="/data/dgfip-pci-vecteur/2026-06-01/edigeo/feuilles/49/49035/edigeo-49035000AA01.tar.bz2">edigeo-49035000AA01.tar.bz2</a></td>
<td>129826</td><td>2026-07-03T10:31:33.000Z</td>
</tr>
</tbody></table></body></html>"""

INDEX_VIDE = """<!DOCTYPE html><html><head><title>Index</title></head>
<body><h1>Index of /…/49/49999/</h1><table id="list"><tbody>
<tr><td><a href="../">..</a></td></tr></tbody></table></body></html>"""


# ------------------------------------------------------------ parsing de l'index

def test_parser_index_trouve_les_archives_dedupliquees():
    assert pci.parser_index_feuilles(INDEX_HTML) == [
        "edigeo-490350000A03.tar.bz2",
        "edigeo-490350000B01.tar.bz2",
        "edigeo-49035000AA01.tar.bz2",
    ]


def test_parser_index_est_trie_donc_deterministe():
    feuilles = pci.parser_index_feuilles(INDEX_HTML)
    assert feuilles == sorted(feuilles)


def test_parser_index_commune_absente_rend_liste_vide():
    """Une commune absente rend un index HTTP 200 mais sans lien : liste vide,
    l'appelant en fait un warning (pas un crash)."""
    assert pci.parser_index_feuilles(INDEX_VIDE) == []


def test_parser_index_ignore_les_autres_extensions():
    html = ('<a href="/x/edigeo-490350000B01.tar.bz2">edigeo-490350000B01.tar.bz2</a>'
            '<a href="/x/cadastre-49-parcelles.json.gz">autre.json.gz</a>'
            '<a href="/x/edigeo-490350000B01.tar.bz2.md5">md5</a>')
    assert pci.parser_index_feuilles(html) == ["edigeo-490350000B01.tar.bz2"]


def test_code_feuille():
    assert pci.code_feuille("edigeo-490350000A03.tar.bz2") == "490350000A03"


# ------------------------------------------------------------------------ URLs

def test_url_index_commune():
    assert pci.url_index_commune("49", "49035") == (
        "https://cadastre.data.gouv.fr/data/dgfip-pci-vecteur/latest/edigeo/"
        "feuilles/49/49035/")


def test_url_feuille():
    assert pci.url_feuille("49", "49035", "edigeo-490350000A03.tar.bz2") == (
        "https://cadastre.data.gouv.fr/data/dgfip-pci-vecteur/latest/edigeo/"
        "feuilles/49/49035/edigeo-490350000A03.tar.bz2")


def test_url_feuille_marche_hors_49():
    """Le code ne doit rien coder en dur du département pilote (CLAUDE.md)."""
    assert pci.url_feuille("33", "33063", "edigeo-330630000AB01.tar.bz2").endswith(
        "/feuilles/33/33063/edigeo-330630000AB01.tar.bz2")


# ------------------------------------------------------------- filtrage SYM=65

def _carre(x: float) -> Polygon:
    return Polygon([(x, 0), (x + 4, 0), (x + 4, 4), (x, 4)])


def _tsurf(syms: list[str | None]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"OBJECT_RID": [f"o{i}" for i in range(len(syms))],
         "SYM": syms,
         "TEX": [None] * len(syms)},
        geometry=[_carre(10 * i) for i in range(len(syms))],
        crs="EPSG:2154")


def test_filtrer_sym65_ne_garde_que_le_symbole_piscine():
    out = pci.filtrer_sym65(_tsurf(["34", "65", "66", "65"]), "edigeo-x.tar.bz2")
    assert len(out) == 2
    assert set(out["SYM"]) == {"65"}


def test_filtrer_sym65_schema_de_sortie_exact():
    """Schéma imposé par les parquets A3bis et lu par 24_candidats_cosia."""
    out = pci.filtrer_sym65(_tsurf(["65"]), "edigeo-490350000A03.tar.bz2")
    assert list(out.columns) == ["SYM", "feuille", "geometry"]
    assert out["feuille"].tolist() == ["edigeo-490350000A03.tar.bz2"]
    assert out.crs.to_epsg() == 2154


def test_filtrer_sym65_feuille_sans_piscine_rend_vide_sans_planter():
    out = pci.filtrer_sym65(_tsurf(["34", "66"]), "edigeo-x.tar.bz2")
    assert out.empty
    assert list(out.columns) == ["SYM", "feuille", "geometry"]


def test_filtrer_sym65_tolere_un_sym_numerique():
    """Selon la feuille, GDAL peut typer SYM en entier : la comparaison doit
    rester vraie (sinon on rendrait 0 piscine en silence)."""
    out = pci.filtrer_sym65(_tsurf([65, 34]), "edigeo-x.tar.bz2")
    assert len(out) == 1
    assert out["SYM"].tolist() == ["65"]


def test_filtrer_sym65_sans_colonne_sym_echoue_bruyamment():
    gdf = gpd.GeoDataFrame({"AUTRE": ["x"]}, geometry=[_carre(0)], crs="EPSG:2154")
    with pytest.raises(ValueError, match="SYM"):
        pci.filtrer_sym65(gdf, "edigeo-x.tar.bz2")


# ------------------------------------------------------- parquet vide (commune
# sans aucune piscine cadastrée, ex. Béhuard 49028)

def test_parquet_vide_a_le_bon_schema():
    vide = pci.parquet_vide("EPSG:2154")
    assert vide.empty
    assert list(vide.columns) == ["SYM", "feuille", "geometry"]
    assert vide.crs.to_epsg() == 2154


def test_parquet_vide_relit_identique(tmp_path):
    chemin = tmp_path / "piscines_pci_sym65_49028.parquet"
    pci.parquet_vide("EPSG:2154").to_parquet(chemin)
    relu = gpd.read_parquet(chemin)
    assert relu.empty
    assert list(relu.columns) == ["SYM", "feuille", "geometry"]
    assert relu.crs.to_epsg() == 2154


# ------------------------------------------------------------------ liste ALM

def test_communes_alm_importee_pas_dupliquee():
    """Une seule source de vérité pour la liste ALM (24_candidats_cosia)."""
    cosia = importlib.import_module("24_candidats_cosia")
    assert pci.COMMUNES_ALM is cosia.COMMUNES_ALM
    assert "49035" in pci.COMMUNES_ALM
