"""Tests des fonctions pures de handoff/appliquer_decisions_recues.py (FIX 1 & 3) :

  - filtrage par empreinte de planche (hash12 dans le NOM du CSV) ;
  - départage des conflits par TIMESTAMP DU NOM (pas mtime, qu'un git clone
    réécrit), avec fallback mtime pour les noms non horodatés.

On charge le module handoff par son chemin (nom de fichier non importable tel quel
comme paquet), sans exécuter main().
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "appliquer_decisions_recues", REPO / "handoff" / "appliquer_decisions_recues.py"
)
adr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(adr)


# --------------------------------------------------------- extraction du nom

def test_hash12_du_nom():
    assert adr.hash12_du_nom("decisions_20260712_143000_alice_abc123def456.csv") == "abc123def456"
    assert adr.hash12_du_nom("decisions_49_49035_abc123def456.csv") == "abc123def456"
    assert adr.hash12_du_nom("decisions_20260712_143000_alice.csv") is None
    assert adr.hash12_du_nom("decisions.csv") is None


def test_timestamp_du_nom():
    from datetime import datetime
    ts = adr.timestamp_du_nom("decisions_20260712_143000_alice_abc123def456.csv")
    assert ts == datetime(2026, 7, 12, 14, 30, 0).timestamp()
    # nom du fichier brut de l'ami (dept/commune, pas de timestamp) → None
    assert adr.timestamp_du_nom("decisions_49_49035_abc123def456.csv") is None
    assert adr.timestamp_du_nom("nimporte.csv") is None


# ------------------------------------------------------ filtrage par empreinte

def test_filtrer_par_hash_exclut_les_mauvaises_planches(tmp_path):
    bon = tmp_path / "decisions_20260712_100000_a_aaaaaaaaaaaa.csv"
    mauvais = tmp_path / "decisions_20260712_110000_b_bbbbbbbbbbbb.csv"
    sans = tmp_path / "decisions_20260712_120000_c.csv"
    for p in (bon, mauvais, sans):
        p.write_text("id_detection,decision\n")
    retenus, exclus = adr.filtrer_par_hash([bon, mauvais, sans], "aaaaaaaaaaaa")
    assert bon in retenus and sans in retenus  # bon hash + toléré sans hash
    assert exclus == [mauvais]


def test_filtrer_par_hash_force_inclut_tout(tmp_path):
    bon = tmp_path / "decisions_20260712_100000_a_aaaaaaaaaaaa.csv"
    mauvais = tmp_path / "decisions_20260712_110000_b_bbbbbbbbbbbb.csv"
    for p in (bon, mauvais):
        p.write_text("id_detection,decision\n")
    retenus, exclus = adr.filtrer_par_hash([bon, mauvais], "aaaaaaaaaaaa", force=True)
    assert set(retenus) == {bon, mauvais} and exclus == []


# ------------------------------------------------ départage par timestamp du nom

def test_cle_recence_utilise_le_timestamp_du_nom(tmp_path):
    """Deux fichiers dont l'ORDRE mtime est inversé par rapport à l'ordre du nom :
    le tri par cle_recence suit le NOM, pas le mtime."""
    import os
    tard = tmp_path / "decisions_20260712_150000_a_aaaaaaaaaaaa.csv"   # nom récent
    tot = tmp_path / "decisions_20260712_090000_b_aaaaaaaaaaaa.csv"    # nom ancien
    tard.write_text("id_detection,decision\n")
    tot.write_text("id_detection,decision\n")
    # mtime inversé : le fichier au nom ANCIEN a le mtime le PLUS récent (git clone).
    os.utime(tot, (2_000_000_000, 2_000_000_000))
    os.utime(tard, (1_000_000_000, 1_000_000_000))
    ordonne = sorted([tot, tard], key=adr.cle_recence)
    assert ordonne == [tot, tard]  # ordre du NOM (09h avant 15h), pas du mtime


def test_fusion_conflit_recent_du_nom_gagne(tmp_path):
    """En cas de conflit sur un id, la décision du fichier au nom le plus récent
    l'emporte, indépendamment du mtime."""
    import os
    ancien = tmp_path / "decisions_20260712_090000_x_aaaaaaaaaaaa.csv"
    recent = tmp_path / "decisions_20260712_150000_y_aaaaaaaaaaaa.csv"
    pd.DataFrame({"id_detection": ["p1"], "decision": ["non"]}).to_csv(ancien, index=False)
    pd.DataFrame({"id_detection": ["p1"], "decision": ["oui"]}).to_csv(recent, index=False)
    # mtime trompeur : l'ancien (par le nom) a le mtime le plus récent.
    os.utime(ancien, (2_000_000_000, 2_000_000_000))
    os.utime(recent, (1_000_000_000, 1_000_000_000))
    ordonne = sorted([ancien, recent], key=adr.cle_recence)
    fusion = adr.fusionner(ordonne)
    assert fusion.set_index("id_detection").loc["p1", "decision"] == "oui"


def test_cle_recence_fallback_mtime_si_nom_non_horodate(tmp_path):
    """Nom non horodaté → départage par mtime (clé = mtime)."""
    import os
    f = tmp_path / "decisions_brut_aaaaaaaaaaaa.csv"
    f.write_text("id_detection,decision\n")
    os.utime(f, (1234567890, 1234567890))
    assert adr.cle_recence(f) == (1234567890.0, f.name)


# ------------------------------------------ fusion : rétro-compat 2 col / 4 col

def test_fusion_2_colonnes_reste_2_colonnes(tmp_path):
    """Format historique (2 colonnes) : la fusion reste à 2 colonnes — contrat
    immuable, toujours accepté."""
    f = tmp_path / "decisions_20260712_100000_a_aaaaaaaaaaaa.csv"
    pd.DataFrame({"id_detection": ["p1", "p2"], "decision": ["oui", "non"]}).to_csv(f, index=False)
    fusion = adr.fusionner([f])
    assert list(fusion.columns) == ["id_detection", "decision"]
    assert set(fusion["id_detection"]) == {"p1", "p2"}


def test_fusion_4_colonnes_conserve_trieur_horodatage(tmp_path):
    """Format enrichi (4 colonnes) : trieur/horodatage sont CONSERVÉS dans la
    fusion (traçabilité), sans casser la logique 2 colonnes en aval."""
    f = tmp_path / "decisions_20260712_100000_a_aaaaaaaaaaaa.csv"
    pd.DataFrame({
        "id_detection": ["p1", "p2"],
        "decision": ["oui", "non"],
        "trieur": ["JB", "Azan"],
        "horodatage": ["2026-07-12T10:00:00Z", "2026-07-12T10:01:00Z"],
    }).to_csv(f, index=False)
    fusion = adr.fusionner([f])
    assert list(fusion.columns) == ["id_detection", "decision", "trieur", "horodatage"]
    row = fusion.set_index("id_detection").loc["p1"]
    assert row["decision"] == "oui" and row["trieur"] == "JB"


def test_fusion_mixte_2_et_4_colonnes(tmp_path):
    """Un fichier 2 col + un fichier 4 col : la fusion porte trieur/horodatage
    (colonnes présentes dès qu'un fichier les a ; '' pour l'autre)."""
    f2 = tmp_path / "decisions_20260712_090000_a_aaaaaaaaaaaa.csv"
    f4 = tmp_path / "decisions_20260712_100000_b_aaaaaaaaaaaa.csv"
    pd.DataFrame({"id_detection": ["p1"], "decision": ["non"]}).to_csv(f2, index=False)
    pd.DataFrame({"id_detection": ["p2"], "decision": ["oui"],
                  "trieur": ["JB"], "horodatage": ["2026-07-12T10:00:00Z"]}).to_csv(f4, index=False)
    fusion = adr.fusionner([f2, f4]).set_index("id_detection")
    assert "trieur" in fusion.columns and "horodatage" in fusion.columns
    assert fusion.loc["p1", "trieur"] == ""      # fichier 2 col → vide
    assert fusion.loc["p2", "trieur"] == "JB"
