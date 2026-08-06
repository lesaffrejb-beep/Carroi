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
    v.ajouter("piscines", "existence", "p1", "oui", "JB")
    v.ajouter("piscines", "existence", "p1", "non", "Azan")
    v.ajouter("piscines", "adresse", "p1", "ban_x", "JB")
    v.ajouter("terrasses", "existence", "p1", "non", "JB")   # produits étanches
    assert v.votes_item("piscines", "existence", "p1") == ["oui", "non"]
    assert v.votes_item("terrasses", "existence", "p1") == ["non"]
    assert v.compte_par_item("piscines", "existence")["p1"] == 2
    assert v.total() == 4 and not v.vide()


def test_remplacer_dernier_corrige_sans_doublon(tmp_path):
    """Navigation arrière : re-répondre corrige SON dernier vote (erreur de clic),
    sans doublon et sans toucher aux votes des autres trieurs."""
    v = atelier.Votes(tmp_path / "v.sqlite")
    v.ajouter("piscines", "existence", "p1", "non", "JB")
    v.ajouter("piscines", "existence", "p1", "oui", "Azan")
    v.remplacer_dernier("piscines", "existence", "p1", "oui", "JB")
    assert sorted(v.votes_item("piscines", "existence", "p1")) == ["oui", "oui"]
    assert v.dernier_de("piscines", "existence", "p1", "JB") == "oui"
    assert v.dernier_de("piscines", "existence", "p1", "Azan") == "oui"
    # remplacer sans vote antérieur = simple ajout
    v.remplacer_dernier("piscines", "existence", "p2", "non", "JB")
    assert v.votes_item("piscines", "existence", "p2") == ["non"]


def test_choisir_moins_vu_priorite_aux_desaccords():
    """Passe N : parmi les moins vus, les items CONTESTÉS (votes à égalité)
    passent d'abord — une passe de plus tranche ce qui est disputé."""
    from collections import Counter
    rng = random.Random(7)
    compte = Counter({"a": 2, "b": 2, "c": 2})
    for _ in range(10):
        assert atelier.choisir_moins_vu(["a", "b", "c"], compte, rng,
                                        prioritaires={"b"}) == "b"
    # sans prioritaire dans le groupe min, comportement inchangé
    assert atelier.choisir_moins_vu(["a", "c"], compte, rng, prioritaires={"zz"}) in ("a", "c")


def test_signalements_et_stats(tmp_path):
    v = atelier.Votes(tmp_path / "v.sqlite")
    v.signaler("piscines", "p1", 427421.5, 6707886.1, "JB")
    csv = v.signalements_csv()
    assert "produit,id_item,x_l93,y_l93,trieur,ts" in csv and "427421.5" in csv
    v.ajouter("piscines", "existence", "p1", "oui", "JB")
    v.ajouter("piscines", "existence", "p2", "non", "JB")
    s = v.stats_trieur("JB")
    assert s["votes"] == 2 and s["temps_actif_s"] >= 0


def test_trieurs_invites_et_gel(tmp_path):
    """Mode en ligne : invitation par token, identité côté serveur, gel."""
    v = atelier.Votes(tmp_path / "v.sqlite")
    token = v.inviter("Azan", 1.5)
    tr = v.trieur_par_token(token)
    assert tr["nom"] == "Azan" and tr["taux_ct"] == 1.5 and not tr["gele"]
    assert v.trieur_par_token("zzz") is None
    v.geler(token)
    assert v.trieur_par_token(token)["gele"]
    assert v.lister_trieurs()[0]["nom"] == "Azan"


def test_cadence_suspecte(tmp_path):
    v = atelier.Votes(tmp_path / "v.sqlite")
    for k in range(25):                        # rafale instantanée = robot
        v.ajouter("piscines", "existence", f"p{k}", "non", "bot")
    assert v.cadence_suspecte("bot")
    assert not v.cadence_suspecte("personne_inconnue")


def test_vocab_fast_coherent_avec_les_produits():
    """Mode FAST : les touches sont uniques, et chaque canonisation pointe vers
    un code natif du produit (sinon un vote « piscine » casserait consensus/or)."""
    touches = [t for _, t, _, _ in atelier.VOCAB_FAST]
    assert len(touches) == len(set(touches))
    for nom, pcfg in atelier.PRODUITS.items():
        codes = {c for c, *_ in pcfg["reponses"]}
        for source, cible in pcfg.get("canonique", {}).items():
            assert cible in codes, f"{nom}: canonique {source}->{cible} hors vocabulaire"
    # piscines : le code fast « piscine » DOIT se réécrire en « oui »
    assert atelier.PRODUITS["piscines"]["canonique"]["piscine"] == "oui"
    # terrasses : les codes fast positifs sont déjà natifs
    assert {"terrasse", "jardin"} <= {c for c, *_ in atelier.PRODUITS["terrasses"]["reponses"]}


def test_combos_multi_classes():
    """Une zone rouge peut contenir plusieurs choses : le combo « x+y » compte
    positif dès qu'un composant l'est, et reste compatible avec un vote simple."""
    assert atelier.votes_compatibles("piscine+jardin", "piscine")
    assert atelier.votes_compatibles("oui", "jardin+oui")
    assert not atelier.votes_compatibles("non", "jardin+terrasse")
    # majorité combo → débloque le niveau adresse si un composant est positif
    assert atelier.existence_acquise(["jardin+oui", "jardin+oui"], positifs=("oui",))
    assert atelier.existence_acquise(["jardin+terrasse"], positifs=("terrasse", "jardin"))
    assert not atelier.existence_acquise(["non", "non"], positifs=("oui",))
    assert not atelier.existence_acquise([], positifs=("oui",))


def test_classer_incertitude_regle_des_3_signaux():
    ci = atelier.classer_incertitude
    # vendable : unanime, ou majorité nette (accord ≥ 2/3)
    assert ci(["oui", "oui", "oui"]) is None
    assert ci(["oui", "oui", "non"]) is None            # 2/3 pile = vendable
    assert ci([]) is None
    # desaccord : égalité, ou incompatibles avec accord < 2/3
    assert ci(["oui", "non"]) == "desaccord"
    assert ci(["oui", "oui", "non", "non", "oui"]) == "desaccord"   # 3/5 < 2/3
    # combos compatibles ≠ désaccord (partagent un composant)
    assert ci(["jardin+oui", "oui", "oui"]) is None
    # vote_incertain : la majorité elle-même est incertain/indecis
    assert ci(["incertain", "incertain", "oui"]) == "vote_incertain"
    assert ci(["indecis"]) == "vote_incertain"
    # instable : > 2 changements d'avis d'un même trieur, quel que soit le vote
    assert ci(["oui", "oui", "oui"], corrections_max=3) == "instable"
    assert ci(["oui"], corrections_max=2) is None       # 2 changements = toléré


def test_corrections_journalisees_et_max(tmp_path):
    """remplacer_dernier avec une réponse DIFFÉRENTE journalise un changement
    d'avis ; corrections_max donne le pire trieur par item (signal instable)."""
    v = atelier.Votes(tmp_path / "v.sqlite")
    v.ajouter("piscines", "existence", "p1", "oui", "JB")
    v.remplacer_dernier("piscines", "existence", "p1", "non", "JB")   # 1
    v.remplacer_dernier("piscines", "existence", "p1", "oui", "JB")   # 2
    v.remplacer_dernier("piscines", "existence", "p1", "oui", "JB")   # même réponse : pas un changement
    v.remplacer_dernier("piscines", "existence", "p1", "non", "JB")   # 3
    v.ajouter("piscines", "existence", "p2", "oui", "Azan")
    v.remplacer_dernier("piscines", "existence", "p2", "non", "Azan") # 1 seul
    cmax = v.corrections_max("piscines", "existence")
    assert cmax["p1"] == 3 and cmax["p2"] == 1
    assert atelier.classer_incertitude(v.votes_item("piscines", "existence", "p1"),
                                       cmax["p1"]) == "instable"
    # le vote courant reste unique (pas de doublon malgré les corrections)
    assert v.votes_item("piscines", "existence", "p1") == ["non"]


def test_signalement_porte_la_parcelle(tmp_path):
    v = atelier.Votes(tmp_path / "v.sqlite")
    v.signaler("piscines", "p1", 427421.5, 6707886.1, "JB", id_parcelle="49035000AB0001")
    v.signaler("piscines", "p2", 1.0, 2.0, "JB")            # hors parcelle → vide
    csv = v.signalements_csv()
    assert "id_parcelle" in csv.splitlines()[0]
    assert "49035000AB0001" in csv


def test_parcelle_au_point():
    import geopandas as gpd
    from shapely.geometry import box
    parcelles = gpd.GeoDataFrame(
        {"id": ["A", "B"]},
        geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10)], crs="EPSG:2154")
    assert atelier.parcelle_au_point(parcelles, 5, 5) == "A"
    assert atelier.parcelle_au_point(parcelles, 15, 5) == "B"
    assert atelier.parcelle_au_point(parcelles, 50, 50) is None
    assert atelier.parcelle_au_point(None, 5, 5) is None


def test_terrasses_en_pause():
    """Décision JB 2026-08-06 : hard focus piscines. La file terrasses n'est
    plus servie, mais le vocabulaire multi-classes reste intact."""
    assert atelier.PRODUITS["terrasses"].get("actif", True) is False
    assert atelier.PRODUITS["piscines"].get("actif", True) is True
    assert {v[0] for v in atelier.VOCAB_FAST} >= {"piscine", "terrasse", "jardin"}
