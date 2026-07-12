"""Tests des fonctions PURES de verifier_donnees — le garde-fou R1 (divergence
silencieuse de données entre machines). Aucune I/O : on éprouve le calcul de
manifeste et la comparaison sur données synthétiques.
"""
from __future__ import annotations

import hashlib

import pytest

import verifier_donnees as vd


# --------------------------------------------------------------------------- #
# construire_fichiers : hash, taille, nb_lignes, tri.
# --------------------------------------------------------------------------- #
def test_entree_depuis_bytes_hash_taille_lignes():
    contenu = b"piscine"
    e = vd.entree_depuis_bytes(contenu, 42)
    assert e["sha256"] == hashlib.sha256(contenu).hexdigest()
    assert e["taille_octets"] == len(contenu)
    assert e["nb_lignes"] == 42


def test_entree_non_parquet_nb_lignes_none():
    e = vd.entree_depuis_bytes(b"BAN: latest@2026-07-11\n", None)
    assert e["nb_lignes"] is None


def test_construire_fichiers_est_trie_par_nom():
    items = [
        ("z_dernier.parquet", b"z", 1),
        ("a_premier.parquet", b"a", 2),
        ("m_milieu.parquet", b"m", 3),
    ]
    fichiers = vd.construire_fichiers(items)
    assert list(fichiers) == ["a_premier.parquet", "m_milieu.parquet", "z_dernier.parquet"]


def test_construire_fichiers_stable_quel_que_soit_l_ordre_d_entree():
    a = vd.construire_fichiers([("b.parquet", b"1", 1), ("a.parquet", b"2", 2)])
    b = vd.construire_fichiers([("a.parquet", b"2", 2), ("b.parquet", b"1", 1)])
    assert a == b
    assert list(a) == list(b) == ["a.parquet", "b.parquet"]


def test_construire_fichiers_refuse_les_doublons():
    with pytest.raises(ValueError, match="dupliqué"):
        vd.construire_fichiers([("x.parquet", b"1", 1), ("x.parquet", b"2", 2)])


def test_meme_contenu_meme_hash_contenu_different_hash_different():
    f = vd.construire_fichiers([("a.parquet", b"meme", 1), ("b.parquet", b"meme", 1)])
    assert f["a.parquet"]["sha256"] == f["b.parquet"]["sha256"]
    g = vd.construire_fichiers([("a.parquet", b"AAA", 1), ("b.parquet", b"BBB", 1)])
    assert g["a.parquet"]["sha256"] != g["b.parquet"]["sha256"]


# --------------------------------------------------------------------------- #
# comparer : les 4 statuts + conformité.
# --------------------------------------------------------------------------- #
def _ref():
    return vd.construire_fichiers([
        ("ban_49.parquet", b"ban-v1", 100),
        ("parcelles_49.parquet", b"parc-v1", 200),
    ])


def test_comparer_tout_identique():
    ref = _ref()
    resultats = vd.comparer(ref, dict(ref))
    assert {r["statut"] for r in resultats} == {vd.STATUT_IDENTIQUE}
    assert vd.local_est_conforme(resultats) is True


def test_comparer_hash_different_detecte_et_bloque():
    ref = _ref()
    local = vd.construire_fichiers([
        ("ban_49.parquet", b"ban-v2-DIFFERENT", 100),   # re-download « latest » a bougé
        ("parcelles_49.parquet", b"parc-v1", 200),
    ])
    resultats = vd.comparer(ref, local)
    ban = next(r for r in resultats if r["nom"] == "ban_49.parquet")
    assert ban["statut"] == vd.STATUT_HASH_DIFFERENT
    assert vd.local_est_conforme(resultats) is False


def test_comparer_absent_local_bloque():
    ref = _ref()
    local = vd.construire_fichiers([("ban_49.parquet", b"ban-v1", 100)])
    resultats = vd.comparer(ref, local)
    manquant = next(r for r in resultats if r["nom"] == "parcelles_49.parquet")
    assert manquant["statut"] == vd.STATUT_ABSENT_LOCAL
    assert manquant["local"] is None
    assert vd.local_est_conforme(resultats) is False


def test_comparer_absent_manifeste_signale_mais_ne_bloque_pas():
    ref = _ref()
    local = dict(ref)
    local.update(vd.construire_fichiers([("piscines_extra_dev.parquet", b"extra", 5)]))
    resultats = vd.comparer(ref, local)
    extra = next(r for r in resultats if r["nom"] == "piscines_extra_dev.parquet")
    assert extra["statut"] == vd.STATUT_ABSENT_MANIFESTE
    assert extra["reference"] is None
    # Un fichier local EN PLUS ne rend pas les données incohérentes avec la référence.
    assert vd.local_est_conforme(resultats) is True


def test_comparer_resultats_tries_par_nom():
    ref = vd.construire_fichiers([("z.parquet", b"z", 1), ("a.parquet", b"a", 1)])
    local = vd.construire_fichiers([("m.parquet", b"m", 1), ("a.parquet", b"a", 1)])
    resultats = vd.comparer(ref, local)
    noms = [r["nom"] for r in resultats]
    assert noms == sorted(noms)
    assert noms == ["a.parquet", "m.parquet", "z.parquet"]


def test_comparer_cas_mixte_complet():
    ref = vd.construire_fichiers([
        ("identique.parquet", b"same", 1),
        ("modifie.parquet", b"avant", 2),
        ("manquant.parquet", b"perdu", 3),
    ])
    local = vd.construire_fichiers([
        ("identique.parquet", b"same", 1),
        ("modifie.parquet", b"apres", 2),
        ("en_plus.parquet", b"nouveau", 4),
    ])
    statuts = {r["nom"]: r["statut"] for r in vd.comparer(ref, local)}
    assert statuts["identique.parquet"] == vd.STATUT_IDENTIQUE
    assert statuts["modifie.parquet"] == vd.STATUT_HASH_DIFFERENT
    assert statuts["manquant.parquet"] == vd.STATUT_ABSENT_LOCAL
    assert statuts["en_plus.parquet"] == vd.STATUT_ABSENT_MANIFESTE
    # Un hash différent ET un manquant → non conforme.
    assert vd.local_est_conforme(vd.comparer(ref, local)) is False


def test_local_conforme_vide_est_conforme():
    # Deux ensembles vides : rien à comparer, trivialement conforme.
    assert vd.local_est_conforme(vd.comparer({}, {})) is True
