"""Tests des garde-fous transverses : opt-out (obligation légale), traçabilité
des sources, et rigueur du tri humain (16_tri_visuel.appliquer_decisions).
"""
from __future__ import annotations

import importlib
import logging

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

import common

tri = importlib.import_module("16_tri_visuel")
log = logging.getLogger("tests")


# ------------------------------------------------------------------ opt-out

def test_apply_optout_retire_les_adresses_opposees(tmp_path):
    optout = tmp_path / "optout.csv"
    optout.write_text("id_ban,adresse,date_demande\nban_2,2 rue X,2026-07-01\n")
    cfg = {"paths": {"optout": str(optout)}}
    df = pd.DataFrame({"id_ban": ["ban_1", "ban_2", "ban_3"], "adresse": ["a", "b", "c"]})
    out = common.apply_optout(df, cfg, log)
    assert list(out["id_ban"]) == ["ban_1", "ban_3"]


def test_apply_optout_refuse_un_fichier_mal_forme(tmp_path):
    """Un optout.csv sans colonne id_ban ne doit PAS être ignoré silencieusement :
    on préfère bloquer l'export que risquer de livrer une adresse opposée."""
    optout = tmp_path / "optout.csv"
    optout.write_text("email,date\nx@y.fr,2026-07-01\n")
    cfg = {"paths": {"optout": str(optout)}}
    df = pd.DataFrame({"id_ban": ["ban_1"]})
    with pytest.raises(ValueError):
        common.apply_optout(df, cfg, log)


def test_attribution_source_contient_millesimes_et_licence():
    s = common.source_attribution({"BAN": "2026-06", "Cadastre (Etalab)": "2026-04"})
    assert "BAN millésime 2026-06" in s
    assert "Licence Ouverte 2.0" in s
    assert "pipeline" in s


# ------------------------------------------------------- tri humain (--apply)

def _candidats(n=10):
    return gpd.GeoDataFrame(
        {
            "id_detection": list(range(n)),
            "surface_m2": [30.0] * n,
            "score_detection": [0.8] * n,
            "methode": ["hsv"] * n,
        },
        geometry=[Point(i, i) for i in range(n)], crs="EPSG:2154",
    )


def test_appliquer_decisions_ne_garde_que_les_oui():
    cand = _candidats(4)
    dec = pd.DataFrame(
        {"id_detection": [0, 1, 2, 3], "decision": ["oui", "non", "incertain", "oui"]}
    )
    out = tri.appliquer_decisions(cand, dec)
    assert sorted(out["id_detection"]) == [0, 3]
    assert (out["methode"] == "valide_humain").all(), \
        "la méthode doit tracer la validation humaine (traçabilité qualité)"


def test_appliquer_decisions_refuse_un_tri_bacle():
    """>2 % de candidats sans décision = tri incomplet = refus. Une base à
    moitié triée casserait la promesse de précision mesurée (docs/06)."""
    cand = _candidats(100)
    dec = pd.DataFrame({"id_detection": list(range(90)), "decision": ["oui"] * 90})
    with pytest.raises(ValueError, match="incomplet"):
        tri.appliquer_decisions(cand, dec)


def test_appliquer_decisions_refuse_des_ids_inconnus():
    cand = _candidats(3)
    dec = pd.DataFrame({"id_detection": [0, 1, 2, 99], "decision": ["oui"] * 4})
    with pytest.raises(ValueError, match="inconnus"):
        tri.appliquer_decisions(cand, dec)


def test_appliquer_decisions_refuse_des_valeurs_inconnues():
    cand = _candidats(2)
    dec = pd.DataFrame({"id_detection": [0, 1], "decision": ["oui", "peut-être"]})
    with pytest.raises(ValueError, match="invalides"):
        tri.appliquer_decisions(cand, dec)


def test_les_incertains_ne_passent_jamais():
    """« On ne vend pas le doute » : incertain = exclu, pas de zone grise."""
    cand = _candidats(2)
    dec = pd.DataFrame({"id_detection": [0, 1], "decision": ["incertain", "incertain"]})
    out = tri.appliquer_decisions(cand, dec)
    assert out.empty
