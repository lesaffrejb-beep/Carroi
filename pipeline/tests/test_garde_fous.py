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
export = importlib.import_module("40_export_client")
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


# ---- opt-out par adresse seule (art. 11) : les 3 correctifs d'audit (tâche 5bis) ----

def test_apply_optout_retire_par_adresse_seule(tmp_path):
    """Opposition « par adresse seule » (art. 11) : pas d'id_ban dans l'optout, mais
    l'adresse (normalisée : accents/casse/ponctuation) tombe → l'adresse est retirée,
    même si son id BAN a changé de millésime."""
    optout = tmp_path / "optout.csv"
    optout.write_text("id_ban,adresse,date_demande\n,12 Rue de l'Église,2026-07-01\n")
    cfg = {"paths": {"optout": str(optout)}}
    df = pd.DataFrame({
        "id_ban": ["ban_neuf"],  # l'id BAN a changé → seul l'adresse peut matcher
        "adresse": ["12 rue de l eglise"],
    })
    out = common.apply_optout(df, cfg, log)
    assert out.empty, "l'adresse opposée doit être retirée via la clé adresse normalisée"


def test_apply_optout_refuse_une_ligne_sans_aucune_cle(tmp_path):
    """Une ligne d'opposition sans id_ban NI adresse ne peut pas être honorée :
    on refuse l'export au lieu de l'ignorer silencieusement."""
    optout = tmp_path / "optout.csv"
    optout.write_text("id_ban,adresse,date_demande\n,,2026-07-01\n")
    cfg = {"paths": {"optout": str(optout)}}
    df = pd.DataFrame({"id_ban": ["ban_1"], "adresse": ["1 rue X"]})
    with pytest.raises(ValueError, match="sans id_ban"):
        common.apply_optout(df, cfg, log)


def test_apply_optout_refuse_si_base_sans_colonne_adresse(tmp_path):
    """Une opposition « par adresse » alors que la base n'a pas de colonne adresse :
    on ne saurait pas l'honorer → refus bruyant plutôt que retrait silencieusement raté."""
    optout = tmp_path / "optout.csv"
    optout.write_text("id_ban,adresse,date_demande\n,3 rue Y,2026-07-01\n")
    cfg = {"paths": {"optout": str(optout)}}
    df = pd.DataFrame({"id_ban": ["ban_1", "ban_2"]})  # pas de colonne 'adresse'
    with pytest.raises(ValueError, match="colonne 'adresse'"):
        common.apply_optout(df, cfg, log)


def test_export_refuse_sans_version_tracable(monkeypatch):
    """Garde-fou n°4 : sans version de pipeline (git describe → 'unknown'), un export
    non-démo est REFUSÉ ; le mode --demo reste autorisé."""
    monkeypatch.setattr(export, "pipeline_version", lambda: "unknown")
    with pytest.raises(SystemExit):
        export.exiger_version_tracable(demo=False)
    assert export.exiger_version_tracable(demo=True) == "unknown"
    monkeypatch.setattr(export, "pipeline_version", lambda: "v1.2.3-4-gabcdef")
    assert export.exiger_version_tracable(demo=False) == "v1.2.3-4-gabcdef"


def test_tatouer_retourne_des_temoins():
    """Le tatouage renvoie ≤ 5 id_ban témoins (coord. à précision réduite), stables
    pour un même acheteur — de quoi réattribuer un fichier fuité (garde-fou n°5)."""
    n = 200
    df = pd.DataFrame({
        "id_ban": [f"ban_{i}" for i in range(n)],
        "adresse": [f"{i} rue Test" for i in range(n)],
        "commune": ["Angers"] * n,
        "code_postal": ["49000"] * n,
        "lat": [47.47 + i * 1e-4 for i in range(n)],
        "lon": [-0.55 + i * 1e-4 for i in range(n)],
    })
    out, temoins = export.tatouer(df, "PISCINES DUPONT SARL")
    assert 0 < len(temoins) <= 5
    assert set(temoins) <= set(out["id_ban"].astype(str))
    _, temoins2 = export.tatouer(df, "PISCINES DUPONT SARL")
    assert temoins == temoins2, "témoins déterministes pour un même acheteur"


def test_registre_consigne_version_et_temoins(tmp_path, monkeypatch):
    """Le registre des ventes embarque version_pipeline et temoins_tatouage
    (garde-fou n°5 : gestion des exclusivités + réattribution)."""
    monkeypatch.setattr(export, "REPO_ROOT", tmp_path)
    export.registre_vente(
        {}, "PISCINES DUPONT SARL", "piscines", "communes-49007", 12,
        tmp_path / "f.csv", version="v1.2.3-4-gabcdef", temoins=["ban_1", "ban_2"],
    )
    reg = pd.read_csv(tmp_path / "sales" / "registre.csv", dtype=str)
    assert reg.loc[0, "version_pipeline"] == "v1.2.3-4-gabcdef"
    assert reg.loc[0, "temoins_tatouage"] == "ban_1|ban_2"


def test_attribution_source_contient_millesimes_et_licence():
    s = common.source_attribution({"BAN": "2026-06", "Cadastre (Etalab)": "2026-04"})
    assert "BAN millésime 2026-06" in s
    assert "Licence Ouverte 2.0" in s
    assert "pipeline" in s


# ------------------------------------------ précision annoncée (borne Wilson)
# Garde-fou n°7 « pas de sur-promesse » : on annonce la borne basse, jamais le point.

def test_wilson_valeurs_de_reference():
    """Valeurs de référence de l'intervalle de Wilson à 95 % (docs/06 §2 bis)."""
    assert common.borne_basse_wilson(96, 100) == pytest.approx(0.9016, abs=1e-3)
    assert common.borne_basse_wilson(196, 200) == pytest.approx(0.9497, abs=1e-3)


def test_wilson_annonce_toujours_moins_que_le_point():
    """La borne basse est STRICTEMENT sous l'estimation ponctuelle (tant que p<1) :
    c'est tout l'intérêt anti-sur-promesse."""
    for succes, n in [(96, 100), (90, 100), (47, 50)]:
        assert common.borne_basse_wilson(succes, n) < succes / n


def test_wilson_reste_dans_0_1_meme_aux_extremes():
    """Contrairement à Wald, Wilson ne sort jamais de [0, 1], même à p=1 ou p=0."""
    assert 0.0 <= common.borne_basse_wilson(0, 100) < 1.0
    haut = common.borne_basse_wilson(100, 100)
    assert 0.0 < haut < 1.0, "à 100/100, la borne basse reste < 1 (incertitude d'échantillon)"


def test_wilson_se_resserre_quand_n_grandit():
    """Même proportion, plus d'échantillon → borne basse plus haute (intervalle resserré).
    C'est POURQUOI il faut agrandir n pour annoncer ≥ 95 %, pas changer le discours."""
    assert common.borne_basse_wilson(98, 100) < common.borne_basse_wilson(196, 200)


def test_wilson_refuse_les_entrees_absurdes():
    with pytest.raises(ValueError):
        common.borne_basse_wilson(1, 0)
    with pytest.raises(ValueError):
        common.borne_basse_wilson(101, 100)
    with pytest.raises(ValueError):
        common.borne_basse_wilson(-1, 100)


# ------------------------------------------- tri des vignettes par incertitude
# Leçon état de l'art (docs/15 §2) : cas limites d'abord, évidences à la fin.

def test_cle_incertitude_mesure_la_distance_au_seuil():
    assert tri.cle_incertitude(0.5) == pytest.approx(0.0)
    assert tri.cle_incertitude(0.9) == pytest.approx(0.4)
    assert tri.cle_incertitude(0.1) == pytest.approx(0.4)


def test_tri_par_incertitude_place_les_cas_limites_dabord():
    """L'ordre de tri (celui appliqué dans generer_planche) fait remonter les
    scores proches de 0,5 et repousse les évidences (proches de 0 ou 1) à la fin."""
    items = [{"id": s, "score": s} for s in [0.95, 0.5, 0.8, 0.05, 0.55]]
    items.sort(key=lambda it: tri.cle_incertitude(it["score"]))
    cles = [tri.cle_incertitude(it["score"]) for it in items]
    assert cles == sorted(cles), "les vignettes sont bien triées par incertitude croissante"
    assert items[0]["score"] == 0.5, "le cas le plus incertain est vu en premier"
    assert {items[-1]["score"], items[-2]["score"]} == {0.95, 0.05}, \
        "les cas les plus évidents (0,05 et 0,95) sont vus en dernier"


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
