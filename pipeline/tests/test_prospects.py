"""Tests du cœur pur de la liste de prospects (prospects.py).

But : verrouiller les garde-fous de la couche vente sans dépendre du réseau —
sélection de l'établissement DANS le département (le siège peut être ailleurs),
règle non-nominative (entrepreneur individuel sans enseigne écarté), exclusion
des non-diffusibles, priorisation par mot-clé. Les fixtures reproduisent la forme
réelle des résultats de l'API « Recherche d'entreprises » (DINUM).
"""
from __future__ import annotations

import prospects


def _resultat(nom_raison_sociale=None, statut="O", etabs=None, activite="43.99C"):
    return {
        "nom_raison_sociale": nom_raison_sociale,
        "statut_diffusion": statut,
        "activite_principale": activite,
        "dirigeants": [{"nom": "NE DOIT", "prenoms": "PAS ETRE LU"}],  # jamais lu
        "matching_etablissements": etabs or [],
    }


def _etab(commune="49007", cp="49000", ville="ANGERS", actif="A", diffusion="O",
          activite="43.99C", enseignes=None, nom_com=None, siret="12345678900011"):
    return {
        "commune": commune, "code_postal": cp, "libelle_commune": ville,
        "etat_administratif": actif, "statut_diffusion_etablissement": diffusion,
        "activite_principale": activite, "liste_enseignes": enseignes,
        "nom_commercial": nom_com, "siret": siret,
    }


# --- etablissement_du_dept -------------------------------------------------

def test_prend_etablissement_du_dept_pas_le_siege():
    # Siège hors dept (44) + établissement dans le 49 : on doit prendre le 49.
    r = _resultat(etabs=[
        _etab(commune="44172", cp="44980", ville="SAINTE-LUCE", siret="0"),
        _etab(commune="49129", cp="49000", ville="ECOUFLANT", siret="49etab"),
    ])
    etab = prospects.etablissement_du_dept(r, "49")
    assert etab is not None and etab["siret"] == "49etab"


def test_ignore_etablissement_ferme_ou_non_diffusible():
    r = _resultat(etabs=[
        _etab(actif="F", siret="ferme"),
        _etab(diffusion="P", siret="cache"),
        _etab(siret="bon"),
    ])
    assert prospects.etablissement_du_dept(r, "49")["siret"] == "bon"


def test_aucun_etablissement_dans_le_dept():
    r = _resultat(etabs=[_etab(commune="44172", cp="44000")])
    assert prospects.etablissement_du_dept(r, "49") is None


# --- nom_diffusable (règle non-nominative) ---------------------------------

def test_personne_morale_utilise_la_raison_sociale():
    r = _resultat(nom_raison_sociale="EAU BLEUE PISCINES")
    assert prospects.nom_diffusable(r, _etab()) == "EAU BLEUE PISCINES"


def test_entrepreneur_individuel_avec_enseigne_ok():
    # EI : pas de raison sociale, mais une enseigne = identité d'entreprise.
    r = _resultat(nom_raison_sociale=None)
    assert prospects.nom_diffusable(r, _etab(nom_com="MARY CILS")) == "MARY CILS"
    assert prospects.nom_diffusable(r, _etab(enseignes=["AQUA 49"])) == "AQUA 49"


def test_entrepreneur_individuel_sans_enseigne_ecarte():
    # Seule identité = un nom de personne → None (garde-fou non-nominatif).
    r = _resultat(nom_raison_sociale=None)
    assert prospects.nom_diffusable(r, _etab(enseignes=None, nom_com=None)) is None


# --- calc_priorite ---------------------------------------------------------

def test_priorite_mots_cles_et_naf():
    assert prospects.calc_priorite("EAU BLEUE PISCINES", "43.99D") == "haute"
    assert prospects.calc_priorite("BLEU BASSIN", "96.09Z") == "haute"
    # « spa » est un signal FAIBLE : un institut de beauté ne doit pas être en tête.
    assert prospects.calc_priorite("AURA HAIR SPA", "96.02A") == "moyenne"
    assert prospects.calc_priorite("VERANDA DE L'ANJOU", "43.32B") == "moyenne"
    assert prospects.calc_priorite("SARL MACON GENERIQUE", "43.99C") == "moyenne"
    assert prospects.calc_priorite("COIFFURE CHEZ NANA", "96.09Z") == "basse"


# --- resultat_vers_ligne (orchestration + motifs de rejet) -----------------

def test_ligne_complete():
    r = _resultat(nom_raison_sociale="EAU BLEUE PISCINES",
                  etabs=[_etab(ville="BAUGE-EN-ANJOU", activite="43.99D", siret="S1")])
    ligne, motif = prospects.resultat_vers_ligne(r, "49")
    assert motif is None
    assert ligne == {
        "raison_sociale": "EAU BLEUE PISCINES", "naf": "43.99D",
        "ville": "BAUGE-EN-ANJOU", "tel_si_public": "", "site_web": "",
        "priorite": "haute", "code_postal": "49000", "siret": "S1",
    }


def test_motifs_de_rejet():
    non_diff = _resultat(statut="P", etabs=[_etab()])
    assert prospects.resultat_vers_ligne(non_diff, "49") == (None, "non_diffusible")

    hors = _resultat(nom_raison_sociale="X", etabs=[_etab(commune="44172", cp="44000")])
    assert prospects.resultat_vers_ligne(hors, "49") == (None, "hors_dept")

    nominatif = _resultat(nom_raison_sociale=None,
                          etabs=[_etab(enseignes=None, nom_com=None)])
    assert prospects.resultat_vers_ligne(nominatif, "49") == (None, "nominatif_seul")
