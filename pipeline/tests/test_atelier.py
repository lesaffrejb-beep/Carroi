"""Tests de l'atelier d'annotation : logique pure (consensus, déblocage,
tirage moins-vu) et stockage des votes."""
from __future__ import annotations

import importlib
import random

atelier = importlib.import_module("atelier")


def test_consensus():
    assert atelier.consensus([]) == (None, 0.0)
    assert atelier.consensus(["oui"]) == ("oui", 1.0)
    assert atelier.consensus(["oui", "oui", "non"]) == ("oui", 2 / 3)
    maj, acc = atelier.consensus(["oui", "non"])          # égalité
    assert maj is None and acc == 0.5


def test_existence_acquise():
    assert atelier.existence_acquise(["oui", "oui", "non"])
    assert not atelier.existence_acquise(["oui", "non"])      # égalité ≠ acquis
    assert not atelier.existence_acquise(["non"])
    assert not atelier.existence_acquise([])


def test_choisir_moins_vu_prend_dans_le_minimum():
    from collections import Counter
    rng = random.Random(42)
    compte = Counter({"a": 2, "b": 0, "c": 1, "d": 0})
    for _ in range(20):
        assert atelier.choisir_moins_vu(["a", "b", "c", "d"], compte, rng) in ("b", "d")
    assert atelier.choisir_moins_vu([], compte, rng) is None


def test_votes_append_only(tmp_path):
    v = atelier.Votes(tmp_path / "v.sqlite")
    assert v.vide()
    v.ajouter("existence", "p1", "oui", "JB")
    v.ajouter("existence", "p1", "non", "Azan")
    v.ajouter("adresse", "p1", "ban_x", "JB")
    assert v.votes_item("existence", "p1") == ["oui", "non"]   # rien d'écrasé
    assert v.compte_par_item("existence")["p1"] == 2
    assert v.total() == 3 and not v.vide()
