"""Tests des fonctions PURES de la vérification d'adresse (17_verification_adresse) :
sélection des adresses dans le rayon, flag `assignee`, filtre des cas à vérifier,
structure du JSON embarqué et présence des blocs clés dans le HTML généré.

Tout est synthétique en mémoire : aucune dalle ortho requise (les vignettes ortho
sont injectées en paramètre `image_b64` et donc mockables — ici None).
"""
from __future__ import annotations

import importlib
import json

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box

verif = importlib.import_module("17_verification_adresse")


# --------------------------------------------------------------- fixtures BAN

def _ban(rows):
    """rows : liste de (id_ban, x, y, numero, nom_voie). Construit un GeoDataFrame BAN
    minimal en Lambert-93."""
    recs = [{"id_ban": r[0], "numero": r[3], "rep": "", "nom_voie": r[4],
             "code_postal": "49080", "nom_commune": "Bouchemaine",
             "geometry": Point(r[1], r[2])} for r in rows]
    return gpd.GeoDataFrame(recs, geometry="geometry", crs="EPSG:2154")


# --------------------------------------------------- sélection dans le rayon

def test_adresses_dans_rayon_seulement():
    """Seules les adresses à ≤ RAYON_M du centre sont retenues, triées par distance."""
    ban = _ban([
        ("A", 10, 0, "1", "rue Proche"),      # 10 m
        ("B", 100, 0, "2", "rue Moyenne"),    # 100 m
        ("C", 500, 0, "3", "rue Loin"),       # 500 m > 150 → exclue
    ])
    res = verif.adresses_pour_piscine(ban, 0.0, 0.0, id_ban_assignee="B")
    ids = [a["id_ban"] for a in res]
    assert ids == ["A", "B"]           # C exclue, triées par distance croissante
    assert res[0]["dist_m"] == 10.0


def test_flag_assignee():
    """Le flag `assignee` marque exactement l'id_ban retenu par le pipeline."""
    ban = _ban([("A", 10, 0, "1", "rue A"), ("B", 20, 0, "2", "rue B")])
    res = verif.adresses_pour_piscine(ban, 0.0, 0.0, id_ban_assignee="B")
    par_id = {a["id_ban"]: a["assignee"] for a in res}
    assert par_id == {"A": False, "B": True}


def test_flag_assignee_aucune():
    """id_ban_assignee None → aucune adresse marquée assignee (pas d'exception)."""
    ban = _ban([("A", 10, 0, "1", "rue A")])
    res = verif.adresses_pour_piscine(ban, 0.0, 0.0, id_ban_assignee=None)
    assert res[0]["assignee"] is False


def test_projection_pixel_centre():
    """Une adresse au centre du crop tombe au milieu du cadre SVG (OUT_PX/2)."""
    ban = _ban([("A", 1000, 2000, "1", "rue A")])
    res = verif.adresses_pour_piscine(ban, 1000.0, 2000.0, id_ban_assignee="A")
    assert res[0]["x"] == verif.OUT_PX / 2
    assert res[0]["y"] == verif.OUT_PX / 2


# ----------------------------------------------------- filtre cas à vérifier

def _gdf(confiances):
    return gpd.GeoDataFrame(
        {"confiance": confiances, "id_ban": ["x"] * len(confiances)},
        geometry=[Point(0, 0)] * len(confiances), crs="EPSG:2154")


def test_cas_a_verifier_exclut_haute():
    g = _gdf(["haute", "moyenne", "basse", "haute"])
    out = verif.cas_a_verifier(g)
    assert set(out["confiance"]) == {"moyenne", "basse"}
    assert len(out) == 2


def test_cas_a_verifier_toutes():
    g = _gdf(["haute", "moyenne"])
    assert len(verif.cas_a_verifier(g, toutes=True)) == 2


def test_cas_a_verifier_proxy_sans_confiance():
    """Sans colonne 'confiance', proxy : jointure ambiguë OU 'nearest' → à vérifier."""
    g = gpd.GeoDataFrame({
        "jointure_ambigue": [False, True, False],
        "source_jointure": ["cad_parcelles", "cad_parcelles", "nearest"],
        "id_ban": ["a", "b", "c"],
    }, geometry=[Point(0, 0)] * 3, crs="EPSG:2154")
    out = verif.cas_a_verifier(g)
    assert set(out["id_ban"]) == {"b", "c"}   # a (net, cad_parcelles) écartée


# ----------------------------------------------------- texte d'adresse

def test_texte_adresse_ban_complet():
    row = pd.Series({"numero": 12.0, "rep": "bis", "nom_voie": "rue des Lacs",
                     "code_postal": "49080", "nom_commune": "Bouchemaine"})
    txt = verif.texte_adresse_ban(row)
    assert "12 bis rue des Lacs" in txt and "Bouchemaine" in txt
    assert ".0" not in txt              # 12.0 → 12


def test_texte_adresse_ban_manquant():
    row = pd.Series({"numero": None, "rep": None, "nom_voie": "rue Seule",
                     "code_postal": None, "nom_commune": None})
    assert verif.texte_adresse_ban(row) == "rue Seule"


# ----------------------------------------------------- construction d'un item

def _piscine(id_ban="B", id_parcelle="49035000AB0001"):
    geom = box(-3, -3, 3, 3)            # 6×6 m centré sur l'origine
    return pd.Series({"geometry": geom, "id_piscine": "p1", "id_ban": id_ban,
                      "id_parcelle": id_parcelle, "confiance": "moyenne",
                      "source_jointure": "nearest", "adresse": "2 rue B"})


def test_construire_item_structure():
    ban = _ban([("A", 10, 0, "1", "rue A"), ("B", 20, 0, "2", "rue B")])
    parcelles = gpd.GeoDataFrame(
        {"id": ["49035000AB0001", "49035000AB0002"]},
        geometry=[box(-10, -10, 10, 10), box(10, -10, 30, 10)], crs="EPSG:2154")
    it = verif.construire_item(_piscine(), ban, parcelles, image_b64=None)

    assert it["id_piscine"] == "p1"
    assert it["img"] is None
    assert it["id_ban_assignee"] == "B"
    assert it["confiance"] == "moyenne" and it["source_jointure"] == "nearest"
    # adresses embarquées avec le flag assignee correct
    assert {a["id_ban"] for a in it["adresses"]} == {"A", "B"}
    assert [a["assignee"] for a in it["adresses"] if a["id_ban"] == "B"] == [True]
    assert it["adresse_assignee"] and "rue B" in it["adresse_assignee"]
    # contour piscine + parcelles projetés en pixels
    assert it["piscine"] and isinstance(it["piscine"][0][0], list)
    ids_parc = {p["id"] for p in it["parcelles"]}
    assert "49035000AB0001" in ids_parc
    assert any(p["propre"] for p in it["parcelles"] if p["id"] == "49035000AB0001")
    # JSON-sérialisable (contrat d'embarquement dans le HTML)
    json.dumps(it)


def test_construire_item_sans_adresse_assignee():
    """id_ban NaN → id_ban_assignee None, aucune adresse marquée assignee."""
    ban = _ban([("A", 10, 0, "1", "rue A")])
    pisc = _piscine(id_ban=float("nan"))
    it = verif.construire_item(pisc, ban, None, image_b64=None)
    assert it["id_ban_assignee"] is None
    assert all(not a["assignee"] for a in it["adresses"])
    assert it["parcelles"] == []       # parcelles None → liste vide, pas d'erreur


# ----------------------------------------------------------- HTML généré

def _items():
    return [{
        "id_piscine": "p1", "img": None, "piscine": [[[0, 0], [1, 1]]],
        "adresses": [{"id_ban": "A", "texte": "1 rue A", "x": 100, "y": 100,
                      "dist_m": 10.0, "assignee": False},
                     {"id_ban": "B", "texte": "2 rue B", "x": 200, "y": 120,
                      "dist_m": 20.0, "assignee": True}],
        "parcelles": [], "id_ban_assignee": "B", "adresse_assignee": "2 rue B",
        "confiance": "moyenne", "source_jointure": "nearest"}]


def test_rendre_html_items_et_vue_embarques():
    html = verif.rendre_html(_items(), "49")
    assert '"id_piscine": "p1"' in html
    assert '"id_ban_assignee": "B"' in html
    assert '"assignee": true' in html
    # géométrie de vue injectée (out_px/img_px/img_off) — l'ortho couvre
    # toute la vue depuis le retour terrain du 2026-07-16
    assert '"out_px": 700' in html and '"img_px": 700' in html and '"img_off": 0' in html
    # clé localStorage par département (reprise)
    assert "verif_adresse_49" in html


def test_rendre_html_logique_concordance_et_export():
    """Le JS compare le clic à l'assignée et logge concordance ; l'export porte le
    contrat CSV attendu (id_piscine, id_ban_choisi_humain, id_ban_assigne_auto,
    concordance)."""
    html = verif.rendre_html(_items(), "49")
    assert "concorde avec l'assignation automatique" in html
    assert "divergence" in html
    assert "id_piscine,id_ban_choisi_humain,id_ban_assigne_auto,concordance" in html
    assert 'id="btn-export"' in html and "concordance.csv" in html
    assert "function choisir" in html and "function verdict" in html


def test_rendre_html_elements_ui_cles():
    """Cadre SVG, compteur/jauge, navigation, panneau règles, cercle assignée."""
    html = verif.rendre_html(_items(), "49")
    assert 'id="cadre"' in html and "<svg" in html
    assert 'id="compteur"' in html and 'id="jauge"' in html
    assert "Précédent" in html and "Suivant" in html
    assert 'id="regles"' in html and "<summary>" in html
    assert "pin assignee" in html or "assignee" in html   # style du cercle assigné
    assert "Reste ${reste} à vérifier" in html


def test_rendre_html_json_serialisation_items():
    """Les items sont bien injectés en JSON valide (pas de troncature)."""
    html = verif.rendre_html(_items(), "49")
    debut = html.index("const ITEMS = ") + len("const ITEMS = ")
    fin = html.index(";\nconst VUE")
    parsed = json.loads(html[debut:fin])
    assert parsed[0]["id_piscine"] == "p1"


def test_rendre_html_raccourcis_azerty_et_auto_avance():
    """Retour terrain 2026-07-16 : pilotage main gauche AZERTY (rangée des
    chiffres = choisir la maison, Q/D naviguer, S passer, Z effacer) et
    auto-avance vers la prochaine piscine non vérifiée après un choix."""
    html = verif.rendre_html(_items(), "49")
    assert 'const AZERTY = {"&":0, "é":1' in html
    assert "function passer" in html and "function effacerChoix" in html
    assert "function prochainNonVerifie" in html
    assert "timerAvance" in html
