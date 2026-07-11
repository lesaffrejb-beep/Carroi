"""Tests de la « généralisation cosmétique » des flags CLI (roadmap item 7, docs/09 §6).

Deux surfaces couvertes, sans données réelles (parsing + fonctions pures) :
  - 20_join : alias --source rétro-compatible de --source-piscines ;
  - 30_score : flag --produit (défaut piscines) qui paramètre config + noms de fichiers.

Garde-fou de non-régression : le comportement PAR DÉFAUT pour piscines doit être
strictement identique à l'existant (mêmes noms de fichiers d'entrée/sortie).
"""
from __future__ import annotations

import importlib
import sys

import pytest

join = importlib.import_module("20_join_piscines_adresses")
score = importlib.import_module("30_score_qualite")


class _Stop(Exception):
    """Sentinelle : on interrompt main() dès le premier read_parquet, après avoir
    capturé le chemin — inutile de lire de vraies données pour tester le parsing."""


# ------------------------------------------------------------- 20_join --source

def test_resoudre_source_source_piscines_seul():
    assert join.resoudre_source("data/x.parquet", None) == "data/x.parquet"


def test_resoudre_source_alias_source_seul():
    assert join.resoudre_source(None, "data/y.parquet") == "data/y.parquet"


def test_resoudre_source_les_deux_meme_valeur_ok():
    assert join.resoudre_source("data/z.parquet", "data/z.parquet") == "data/z.parquet"


def test_resoudre_source_aucun_argument_refuse():
    with pytest.raises(SystemExit):
        join.resoudre_source(None, None)


def test_resoudre_source_valeurs_divergentes_refuse():
    with pytest.raises(SystemExit):
        join.resoudre_source("data/a.parquet", "data/b.parquet")


def _stub_join(monkeypatch):
    captured = {}

    def fake_read_parquet(path):
        captured["source"] = str(path)
        raise _Stop

    monkeypatch.setattr(join, "load_config", lambda: {})
    monkeypatch.setattr(join, "ensure_dirs", lambda cfg: None)
    monkeypatch.setattr(join.gpd, "read_parquet", fake_read_parquet)
    return captured


def test_parsing_source_piscines_marche_toujours(monkeypatch):
    captured = _stub_join(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["prog", "--source-piscines", "data/hist.parquet"])
    with pytest.raises(_Stop):
        join.main()
    assert captured["source"] == "data/hist.parquet"


def test_parsing_alias_source_marche(monkeypatch):
    captured = _stub_join(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["prog", "--source", "data/alias.parquet"])
    with pytest.raises(_Stop):
        join.main()
    assert captured["source"] == "data/alias.parquet"


def test_parsing_sans_source_echoue(monkeypatch):
    _stub_join(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["prog", "--commune", "49007"])
    with pytest.raises(SystemExit):
        join.main()


# ---------------------------------------------------------- 30_score --produit

def _stub_score(monkeypatch):
    captured = {}
    cfg = {
        "paths": {"interim": "/tmp/interim", "final": "/tmp/final"},
        "dept": "49",
        "piscines": {"marqueur": "piscines"},
        "terrasses": {"marqueur": "terrasses"},
    }

    def fake_read_parquet(path):
        captured["src"] = str(path)
        raise _Stop

    monkeypatch.setattr(score, "load_config", lambda: cfg)
    monkeypatch.setattr(score, "ensure_dirs", lambda c: None)
    monkeypatch.setattr(score.gpd, "read_parquet", fake_read_parquet)
    return captured


def test_produit_defaut_piscines_lit_le_fichier_historique(monkeypatch):
    """Défaut = piscines : fichier d'entrée strictement identique à l'existant."""
    captured = _stub_score(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["prog"])
    with pytest.raises(_Stop):
        score.main()
    assert captured["src"].endswith("piscines_adressees_49.parquet")


def test_produit_defaut_dev_conserve_le_suffixe(monkeypatch):
    captured = _stub_score(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["prog", "--dev"])
    with pytest.raises(_Stop):
        score.main()
    assert captured["src"].endswith("piscines_adressees_49_dev.parquet")


def test_produit_parametre_change_le_prefixe_de_fichier(monkeypatch):
    captured = _stub_score(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["prog", "--produit", "terrasses"])
    with pytest.raises(_Stop):
        score.main()
    assert captured["src"].endswith("terrasses_adressees_49.parquet")


def test_produit_inconnu_echoue_sur_la_section_config(monkeypatch):
    """cfg[produit] est lu tôt : un produit absent de la config plante bruyamment
    (KeyError) plutôt que de produire une base vide silencieusement."""
    _stub_score(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["prog", "--produit", "inexistant"])
    with pytest.raises(KeyError):
        score.main()
