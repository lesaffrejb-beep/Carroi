"""Tests du pré-tri appris : choix des seuils (fonction pure)."""
from __future__ import annotations

import importlib

import numpy as np

pt = importlib.import_module("22_pretri")


def test_choisir_seuils_bandes_correctes():
    # 100 négatifs bien séparés, 50 positifs, 10 incertains au milieu
    rng = np.random.default_rng(0)
    p = np.concatenate([rng.uniform(0, 0.05, 100), rng.uniform(0.4, 0.6, 10),
                        rng.uniform(0.9, 1.0, 50)])
    y = np.concatenate([np.zeros(100), np.array([0, 1] * 5), np.ones(50)])
    s = pt.choisir_seuils(y, p, perte_max=0.02, precision_min=0.95)
    assert s["piscines_perdues_auto_non"] <= 0.02 * y.sum()
    assert s["precision_auto_oui"] >= 0.95
    assert s["auto_non"] >= 90 and s["auto_oui"] >= 45
    assert s["t_bas"] < s["t_haut"]


def test_choisir_seuils_precision_non_monotone():
    """Un faux positif tout en haut ne doit pas fermer la bande auto-oui
    (régression du balayage glouton du 2026-07-17)."""
    p = np.concatenate([np.linspace(0.0, 0.05, 60), np.linspace(0.9, 0.99, 40), [1.0]])
    y = np.concatenate([np.zeros(60), np.ones(40), [0]])   # le sommet est un faux positif
    s = pt.choisir_seuils(y, p, perte_max=0.02, precision_min=0.95)
    assert s["auto_oui"] >= 20


def test_choisir_seuils_degenere_reste_sur():
    # tout mélangé : aucune bande ne doit s'ouvrir dangereusement
    rng = np.random.default_rng(1)
    p = rng.uniform(0, 1, 200)
    y = (rng.uniform(0, 1, 200) > 0.5).astype(float)
    s = pt.choisir_seuils(y, p, perte_max=0.01, precision_min=0.99)
    assert s["piscines_perdues_auto_non"] <= max(1, 0.01 * y.sum())
