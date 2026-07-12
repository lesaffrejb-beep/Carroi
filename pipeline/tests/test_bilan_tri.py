"""Tests des fonctions pures de 18_bilan_tri.py : chargement des décisions (2 et
4 colonnes), JOIN décisions × candidats, échec bruyant sur id inconnus, calcul des
buckets/taux, corroboration recalculée, et section « implications ».

Données synthétiques en mémoire (aucun accès disque hors tmp_path pour les CSV).
"""
from __future__ import annotations

import importlib

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

bilan = importlib.import_module("18_bilan_tri")
tri = importlib.import_module("16_tri_visuel")


def _candidats(n=10):
    """n candidats carrés alignés, scores/surfaces étalés pour remplir les buckets."""
    ids = [f"pisc_{k}" for k in range(n)]
    geoms = [box(k * 100, 0, k * 100 + 5, 5) for k in range(n)]
    scores = [0.56 + 0.04 * k for k in range(n)]  # de 0.56 à ~0.92
    surfaces = [10 + 6 * k for k in range(n)]      # de 10 à 64
    return gpd.GeoDataFrame({
        "id_detection": ids,
        "surface_m2": surfaces,
        "compacite": [0.7] * n,
        "solidite": [0.9] * n,
        "score_detection": scores,
        "dalle": ["d.jp2"] * n,
        "methode": ["hsv"] * n,
    }, geometry=geoms, crs="EPSG:2154")


# ------------------------------------------------------ chargement décisions

def test_charger_decisions_2_colonnes(tmp_path):
    f = tmp_path / "decisions_49_49035_aaaaaaaaaaaa.csv"
    pd.DataFrame({"id_detection": ["pisc_0"], "decision": ["oui"]}).to_csv(f, index=False)
    df = bilan.charger_decisions(f)
    assert list(df.columns) == ["id_detection", "decision", "trieur", "horodatage"]
    assert df.iloc[0]["trieur"] == "inconnu"  # absent → 'inconnu'


def test_charger_decisions_4_colonnes(tmp_path):
    f = tmp_path / "decisions_49_49035_aaaaaaaaaaaa.csv"
    pd.DataFrame({"id_detection": ["pisc_0"], "decision": ["oui"],
                  "trieur": ["JB"], "horodatage": ["2026-07-12T10:00:00Z"]}).to_csv(f, index=False)
    df = bilan.charger_decisions(f)
    assert df.iloc[0]["trieur"] == "JB"
    assert df.iloc[0]["horodatage"] == "2026-07-12T10:00:00Z"


def test_charger_decisions_valeur_invalide(tmp_path):
    f = tmp_path / "decisions.csv"
    pd.DataFrame({"id_detection": ["p"], "decision": ["peut-etre"]}).to_csv(f, index=False)
    with pytest.raises(SystemExit, match="invalides"):
        bilan.charger_decisions(f)


# ------------------------------------------------------------ JOIN

def test_joindre_features_completes():
    cand = _candidats(5)
    dec = pd.DataFrame({"id_detection": ["pisc_0", "pisc_1"],
                        "decision": ["oui", "non"],
                        "trieur": ["JB", "JB"], "horodatage": ["", ""]})
    labels = bilan.joindre(dec, cand)
    assert len(labels) == 2
    # TOUTES les features des candidats + decision + trieur
    for col in ["surface_m2", "compacite", "solidite", "score_detection",
                "dalle", "methode", "geometry", "decision", "trieur"]:
        assert col in labels.columns


def test_joindre_echec_bruyant_ids_inconnus():
    """> 2 % de décisions sur des id inconnus → SystemExit (mauvais couple)."""
    cand = _candidats(5)
    dec = pd.DataFrame({"id_detection": ["pisc_0", "inconnu_1", "inconnu_2"],
                        "decision": ["oui", "oui", "non"],
                        "trieur": ["JB"] * 3, "horodatage": [""] * 3})
    with pytest.raises(SystemExit, match="id_detection inconnus"):
        bilan.joindre(dec, cand)


def test_joindre_tolere_peu_inconnus():
    """Sous le seuil de 2 %, les inconnus sont ignorés (pas d'échec)."""
    cand = _candidats(100)
    ids = [f"pisc_{k}" for k in range(100)] + ["inconnu"]  # 1/101 < 2 %
    dec = pd.DataFrame({"id_detection": ids, "decision": ["oui"] * 101,
                        "trieur": ["JB"] * 101, "horodatage": [""] * 101})
    labels = bilan.joindre(dec, cand)
    assert len(labels) == 100  # l'inconnu est écarté du join


# ------------------------------------------------------ buckets / taux

def test_taux_oui_par_bucket_surface():
    cand = _candidats(4)  # surfaces 10, 16, 22, 28
    # décisions : oui pour les deux premiers, non ensuite
    labels = cand.assign(decision=["oui", "oui", "non", "non"])
    surf = bilan.taux_oui_par_bucket(labels, labels["surface_m2"],
                                     bilan.BUCKETS_SURFACE, bilan.LABELS_SURFACE)
    r_8_15 = surf[surf["tranche"] == "8-15"].iloc[0]
    assert r_8_15["n"] == 1 and r_8_15["oui"] == 1 and r_8_15["taux_oui"] == 1.0
    r_15_30 = surf[surf["tranche"] == "15-30"].iloc[0]
    assert r_15_30["n"] == 3 and r_15_30["oui"] == 1  # 16 oui, 22/28 non
    assert abs(r_15_30["taux_oui"] - 1 / 3) < 1e-9


def test_bornes_score_abaisse_si_sous_055():
    labels = pd.DataFrame({"score_detection": [0.4, 0.7, 0.9]})
    bornes = bilan.bornes_score(labels)
    assert bornes[0] <= 0.4  # première borne abaissée au min observé


# ------------------------------------------------ corroboration recalculée

def test_taux_par_corroboration(monkeypatch):
    cand = _candidats(3)  # candidats en x=0,100,200
    labels = gpd.GeoDataFrame(cand.assign(decision=["oui", "non", "oui"]),
                              geometry="geometry", crs="EPSG:2154")
    # PCI : une piscine cadastrée collée au candidat 0 uniquement.
    pci = gpd.GeoDataFrame({"SYM": ["65"]}, geometry=[box(3, 0, 8, 5)], crs="EPSG:2154")
    monkeypatch.setattr(tri, "charger_pci_piscines", lambda cfg: pci)
    corr = bilan.taux_par_corroboration(labels, {})
    ok = corr[corr["groupe"] == "corroborés cadastre"].iloc[0]
    assert ok["n"] == 1 and ok["oui"] == 1  # seul pisc_0, décidé oui


def test_taux_par_corroboration_pci_absent(monkeypatch):
    labels = gpd.GeoDataFrame(_candidats(2).assign(decision=["oui", "non"]),
                              geometry="geometry", crs="EPSG:2154")
    monkeypatch.setattr(tri, "charger_pci_piscines", lambda cfg: None)
    assert bilan.taux_par_corroboration(labels, {}) is None


# ------------------------------------------------------------ rapport

def test_construire_rapport_implication_score_faible():
    """Un bucket de score à taux de oui < 20 % (n >= 10) déclenche la suggestion
    prudente de remonter score_min, SANS toucher config."""
    calib = pd.DataFrame({"tranche": ["0.55-0.60"], "n": [20], "oui": [2],
                          "taux_oui": [0.10]})
    surf = pd.DataFrame({"tranche": ["8-15"], "n": [20], "oui": [2], "taux_oui": [0.10]})
    labels = gpd.GeoDataFrame(_candidats(2).assign(decision=["oui", "non"],
                                                   trieur=["JB", "Azan"], horodatage=["", ""]),
                              geometry="geometry", crs="EPSG:2154")
    rapport = bilan.construire_rapport(labels, 2, "49", "49035", calib, surf, None)
    assert "suggestion à valider" in rapport
    assert "score_min" in rapport
    assert "aucune modification automatique" in rapport.lower()


def test_construire_rapport_badge_cadastre_tient():
    calib = pd.DataFrame({"tranche": ["0.70-0.80"], "n": [20], "oui": [18], "taux_oui": [0.9]})
    surf = pd.DataFrame({"tranche": ["30-60"], "n": [20], "oui": [18], "taux_oui": [0.9]})
    corr = pd.DataFrame({"groupe": ["corroborés cadastre", "non corroborés"],
                         "n": [20, 10], "oui": [20, 3], "taux_oui": [1.0, 0.3]})
    labels = gpd.GeoDataFrame(_candidats(2).assign(decision=["oui", "oui"],
                                                   trieur=["JB", "JB"], horodatage=["", ""]),
                              geometry="geometry", crs="EPSG:2154")
    rapport = bilan.construire_rapport(labels, 2, "49", "49035", calib, surf, corr)
    assert "badge" in rapport.lower() and "tient sa" in rapport
