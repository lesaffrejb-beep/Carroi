"""Tests de la jointure piscine → parcelle → adresse (20_join).

Cible en priorité `normaliser_ref_cadastrale` : la conversion des références de
parcelle du champ BAN `cad_parcelles` vers le format d'identifiant Etalab. Un bug
de format y faisait tomber la jointure « cad_parcelles » à 0 % (tout basculait sur
le fallback 'nearest', moins précis) — voir 08-ROADMAP.md, tâche 5 / A3.
"""
from __future__ import annotations

import importlib

import pandas as pd

join = importlib.import_module("20_join_piscines_adresses")


def test_normalise_format_espace():
    """Format « espacé » 15 car. (0 inséré après le dept, préfixe en espaces) →
    identifiant Etalab 14 car."""
    assert join.normaliser_ref_cadastrale("490035   BA0071") == "49035000BA0071"
    assert join.normaliser_ref_cadastrale("490007   BS0038") == "49007000BS0038"


def test_normalise_format_compact_inchange():
    """Format compact 14 car. déjà conforme (préfixe de commune absorbée en chiffres,
    communes nouvelles fusionnées) → gardé tel quel."""
    assert join.normaliser_ref_cadastrale("49003181ZM0083") == "49003181ZM0083"
    assert join.normaliser_ref_cadastrale("49092351AA0571") == "49092351AA0571"


def test_normalise_robustesse():
    assert join.normaliser_ref_cadastrale("") is None
    assert join.normaliser_ref_cadastrale("   ") is None
    assert join.normaliser_ref_cadastrale(None) is None


def test_index_ban_gere_les_deux_separateurs():
    """Le champ source mélange les séparateurs '|' ET ',' : les deux doivent
    produire plusieurs lignes normalisées."""
    ban = pd.DataFrame({
        "id_ban": ["a", "b"],
        "cad_parcelles": ["490035   BA0071|490035   BA0084", "49092351AA0571,49092351AA0572"],
    })
    idx = join.index_ban_par_parcelle(ban)
    refs = set(idx["id_parcelle"])
    assert refs == {"49035000BA0071", "49035000BA0084", "49092351AA0571", "49092351AA0572"}
    assert len(idx) == 4
