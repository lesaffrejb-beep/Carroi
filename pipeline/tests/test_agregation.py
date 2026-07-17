"""Tests Dawid-Skene : doit battre la majorité quand un trieur est mauvais."""
from __future__ import annotations

import importlib

ag = importlib.import_module("agregation")


def _votes(scenario):
    return {it: [(t, r) for t, r in vs] for it, vs in scenario.items()}


def test_unanime_et_majorite_simple():
    v = _votes({"a": [("x", "oui"), ("y", "oui")], "b": [("x", "non"), ("y", "non"), ("z", "oui")]})
    c = ag.consensus_dawid_skene(v)
    assert c["a"][0] == "oui" and c["b"][0] == "non"
    assert 0.5 < c["b"][1] <= 1.0


def test_trieur_systematiquement_faux_est_corrige():
    # x et y fiables sur 8 items ; z répond TOUJOURS l'inverse. Sur l'item
    # litigieux где z contredit un seul fiable, DS doit suivre le fiable.
    sc = {}
    for k in range(8):
        sc[f"i{k}"] = [("x", "oui"), ("y", "oui"), ("z", "non")] if k % 2 == 0 \
            else [("x", "non"), ("y", "non"), ("z", "oui")]
    sc["litige"] = [("x", "oui"), ("z", "non")]
    c = ag.consensus_dawid_skene(_votes(sc))
    assert c["litige"][0] == "oui"          # la majorité simple aurait dit 50/50
    fia = ag.fiabilite_trieurs(_votes(sc), c)
    assert fia["x"] > 0.9 and fia["z"] < 0.2


def test_vide_et_solo():
    assert ag.consensus_dawid_skene({}) == {}
    c = ag.consensus_dawid_skene({"a": [("x", "oui")]})
    assert c["a"][0] == "oui"
