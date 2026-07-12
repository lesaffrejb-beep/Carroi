"""Tests des fonctions pures de surimpression cadastrale du tri visuel
(16_tri_visuel) : transformation monde→pixel, corroboration cadastre à <5 m, et
robustesse quand les fichiers parcelles/PCI sont absents.
"""
from __future__ import annotations

import importlib

import geopandas as gpd
import numpy as np
from shapely.geometry import Point, box

tri = importlib.import_module("16_tri_visuel")


# ------------------------------------------------ transformation monde → pixel

def test_monde_vers_pixel_centre_et_bords():
    """Le centre du crop tombe au milieu de la vignette ; le nord est en haut
    (axe Y inversé)."""
    cx, cy, cote, px = 1000.0, 2000.0, 60.0, 300
    # centre -> (150, 150)
    assert tri.monde_vers_pixel(cx, cy, cx, cy, cote, px) == (150.0, 150.0)
    # coin nord-ouest (x-demi, y+demi) -> (0, 0)
    assert tri.monde_vers_pixel(cx - 30, cy + 30, cx, cy, cote, px) == (0.0, 0.0)
    # un point plus au nord a un 'row' plus petit (plus haut dans l'image)
    _, row_nord = tri.monde_vers_pixel(cx, cy + 10, cx, cy, cote, px)
    _, row_sud = tri.monde_vers_pixel(cx, cy - 10, cx, cy, cote, px)
    assert row_nord < row_sud


# --------------------------------------------------- corroboration cadastre

def _pci(geoms):
    return gpd.GeoDataFrame({"SYM": ["65"] * len(geoms)}, geometry=geoms, crs="EPSG:2154")


def test_corrobore_vrai_sous_5m():
    """Un candidat à moins de 5 m d'une piscine SYM=65 est corroboré."""
    pci = _pci([box(0, 0, 4, 4)])
    cand = box(6, 0, 8, 4)  # 2 m du bord droit de la piscine
    assert tri.corrobore_cadastre(cand, pci) is True


def test_corrobore_faux_au_dela_de_5m():
    """Au-delà de 5 m, pas de corroboration."""
    pci = _pci([box(0, 0, 4, 4)])
    cand = box(20, 0, 22, 4)  # 16 m
    assert tri.corrobore_cadastre(cand, pci) is False


def test_corrobore_robuste_pci_absent():
    """PCI None ou GeoDataFrame vide → False, jamais d'exception (robustesse)."""
    assert tri.corrobore_cadastre(box(0, 0, 1, 1), None) is False
    vide = gpd.GeoDataFrame({"SYM": []}, geometry=[], crs="EPSG:2154")
    assert tri.corrobore_cadastre(box(0, 0, 1, 1), vide) is False


def test_corrobore_geometrie_vide():
    pci = _pci([box(0, 0, 4, 4)])
    assert tri.corrobore_cadastre(None, pci) is False


# ------------------------------------------- robustesse chargement de fichiers

def test_charger_parcelles_absent_renvoie_none(tmp_path):
    """Fichier parcelles absent → None + warning, pas d'échec."""
    cfg = {"paths": {"interim": str(tmp_path)}, "dept": "49"}
    assert tri.charger_parcelles(cfg) is None


def test_charger_pci_absent_renvoie_none(tmp_path):
    """Aucun piscines_pci_sym65_*.parquet → None, pas d'échec."""
    cfg = {"paths": {"interim": str(tmp_path)}, "dept": "49"}
    assert tri.charger_pci_piscines(cfg) is None


def test_charger_pci_concatene_et_filtre_sym65(tmp_path):
    """Plusieurs fichiers PCI sont concaténés ; seules les géométries SYM=65 restent."""
    g1 = gpd.GeoDataFrame({"SYM": ["65", "40"]},
                          geometry=[box(0, 0, 1, 1), box(2, 2, 3, 3)], crs="EPSG:2154")
    g2 = gpd.GeoDataFrame({"SYM": ["65"]}, geometry=[box(5, 5, 6, 6)], crs="EPSG:2154")
    g1.to_parquet(tmp_path / "piscines_pci_sym65_49035.parquet")
    g2.to_parquet(tmp_path / "piscines_pci_sym65_49308.parquet")
    cfg = {"paths": {"interim": str(tmp_path)}, "dept": "49"}
    out = tri.charger_pci_piscines(cfg)
    assert len(out) == 2  # les deux SYM=65, le SYM=40 est écarté
    assert set(out["SYM"].astype(str)) == {"65"}


# ---------------------------------------------------- dessin de surimpression

def test_dessiner_surimpression_modifie_les_pixels():
    """Le contour du candidat est bien peint sur la vignette (des pixels changent)."""
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    cand = box(995, 1995, 1005, 2005)  # centré sur (1000, 2000)
    out = tri.dessiner_surimpression(img, 1000.0, 2000.0, 60.0, 300, cand, None)
    assert out.shape == img.shape
    assert out.sum() > 0, "le contour vif du candidat doit peindre des pixels"


def test_dessiner_surimpression_sans_parcelles_ne_plante_pas():
    """parcelles=None : pas de limites tracées, mais aucune erreur."""
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    out = tri.dessiner_surimpression(img, 0.0, 0.0, 60.0, 300, Point(0, 0).buffer(5), None)
    assert out.shape == img.shape


# ------------------------------------------------------- HTML de la planche
# Le front doit être auto-explicatif et transmissible à un tiers : on vérifie
# côté Python que le HTML généré contient les blocs clés (pas de test JS).

def _items():
    return [
        {"id": "pisc_a", "png": "vignettes/pisc_a.png", "surface": 30.0,
         "score": 0.8, "corrobore": 1},
        {"id": "pisc_b", "png": "vignettes/pisc_b.png", "surface": 12.0,
         "score": 0.5, "corrobore": 0},
    ]


def test_rendre_html_bandeau_question_et_touches():
    """Bandeau d'accueil : la question en gros, le compteur, la jauge de
    progression et le rappel des touches (dont Z/← pour annuler)."""
    html = tri.rendre_html(_items(), "49")
    assert "CONTOUR ROUGE" in html
    assert 'id="compteur"' in html and 'id="jauge"' in html
    assert "Reste ${reste} à trier" in html  # gabarit JS du compteur dynamique
    assert "<kbd>O</kbd>" in html and "<kbd>N</kbd>" in html and "<kbd>U</kbd>" in html
    assert "<kbd>Z</kbd>" in html and "annuler la dernière décision" in html
    assert "function annuler()" in html and "histo.pop()" in html


def test_rendre_html_regles_du_jeu():
    """Panneau repliable « règles du jeu » avec le texte de consigne exact."""
    html = tri.rendre_html(_items(), "49")
    assert 'id="regles"' in html and "<summary>" in html
    assert "EXISTENCE" in html and "pas son adresse" in html
    assert "n'est JAMAIS vendu" in html
    assert "IGNOREZ-la, jugez uniquement le contour rouge" in html
    assert "O quand même (la géométrie est recollée ailleurs)" in html
    assert "⌂ cadastré" in html and "limites de parcelles cadastrales" in html


def test_rendre_html_items_persistance_et_export():
    """Les candidats sont embarqués (avec corrobore pour le badge/data-attribute),
    la persistance localStorage est par département, et l'export garde le contrat
    CSV id_detection,decision. L'export prévient s'il reste des non-triés
    (seuil 2 %) mais exporte quand même."""
    html = tri.rendre_html(_items(), "49", "49_49035_abc123def456")
    assert '"id": "pisc_a"' in html and '"corrobore": 1' in html
    assert "dataset.corrobore" in html
    # Clé localStorage DÉRIVÉE de l'empreinte de planche (data-planche), pas
    # d'ancienne clé globale partagée entre communes/versions.
    assert 'data-planche="49_49035_abc123def456"' in html
    assert 'const PLANCHE = document.body.dataset.planche;' in html
    assert 'const CLE = "tri_" + PLANCHE;' in html
    assert "localStorage.setItem(CLE" in html
    assert 'id="btn-export"' in html and "Exporter decisions.csv" in html
    assert "id_detection,decision" in html
    assert "refusera au-delà de 2 %" in html
    assert "exporté quand même" in html


def test_rendre_html_navigation_et_correction():
    """Après décision, saut à la prochaine non triée ; les cartes triées restent
    marquées (classes dec-*) et re-cliquables pour corriger."""
    html = tri.rendre_html(_items(), "49")
    html = tri.rendre_html(_items(), "49", "49_49035_abc123def456")
    assert "premierNonTrie" in html and "scrollIntoView" in html
    assert ".dec-oui" in html and ".dec-non" in html and ".dec-incertain" in html
    assert 'addEventListener("click"' in html
    assert 'loading="lazy"' in html  # 977 vignettes : chargement paresseux obligatoire


# ------------------------------------------------ FIX 1/2 : empreinte de planche

def test_hash12_parquet_stable_et_12_hex(tmp_path):
    """Le hash12 est déterministe (mêmes octets → même valeur), 12 hex, et change
    si le fichier change."""
    f1 = tmp_path / "a.parquet"
    f1.write_bytes(b"des octets de candidats")
    h = tri.hash12_parquet(f1)
    assert len(h) == 12 and all(c in "0123456789abcdef" for c in h)
    assert h == tri.hash12_parquet(f1)  # stable
    f2 = tmp_path / "b.parquet"
    f2.write_bytes(b"des octets differents")
    assert tri.hash12_parquet(f2) != h


def test_commune_depuis_nom():
    """Commune extraite du motif piscines_candidates_{dept}_{commune}.parquet ;
    sinon 'dept'."""
    assert tri.commune_depuis_nom("x/piscines_candidates_49_49035.parquet", "49") == "49035"
    assert tri.commune_depuis_nom("x/piscines_candidates_49.parquet", "49") == "dept"
    assert tri.commune_depuis_nom("x/autre.parquet", "49") == "dept"


def test_id_planche_format(tmp_path):
    """id_planche = {dept}_{commune}_{hash12}, présent tel quel dans le HTML."""
    f = tmp_path / "piscines_candidates_49_49035.parquet"
    f.write_bytes(b"candidats bouchemaine")
    pid = tri.id_planche(f, "49")
    h = tri.hash12_parquet(f)
    assert pid == f"49_49035_{h}"
    html = tri.rendre_html(_items(), "49", pid)
    assert f'data-planche="{pid}"' in html


def test_export_csv_nomme_par_planche():
    """Le nom du fichier téléchargé embarque l'empreinte de planche ; le CONTENU
    reste le contrat immuable id_detection,decision."""
    html = tri.rendre_html(_items(), "49", "49_49035_abc123def456")
    assert 'a.download = "decisions_" + PLANCHE + ".csv"' in html
    assert 'csv = "id_detection,decision' in html


# ------------------------------------------------ FIX 4 : planche embarquée

def _candidats_mini(tmp_path):
    """GeoDataFrame minimal : un candidat carré, avec les colonnes attendues."""
    from shapely.geometry import box as sbox
    g = gpd.GeoDataFrame(
        {"id_detection": ["pisc_x"], "surface_m2": [30.0], "score_detection": [0.7]},
        geometry=[sbox(999, 1999, 1001, 2001)], crs="EPSG:2154",
    )
    return g


def test_embarquer_produit_html_autonome(tmp_path, monkeypatch):
    """--embarquer : le HTML ne référence AUCUN vignettes/*.png et contient des
    data:image/jpeg inline. Sans le flag : références externes conservées."""
    import numpy as np

    cfg = {"dept": "49", "paths": {"interim": str(tmp_path)},
           "tri_visuel": {"vignette_m": 60, "vignette_px": 64}}
    cand = _candidats_mini(tmp_path)
    cand_path = tmp_path / "piscines_candidates_49_49035.parquet"
    cand.to_parquet(cand_path)

    # On court-circuite l'ortho : dalle bidon + extraction qui renvoie une image noire.
    monkeypatch.setattr(tri, "indexer_dalles", lambda d: {"paths": ["dalle.tif"]})
    monkeypatch.setattr(tri, "dalle_pour", lambda x, y, idx: "dalle.tif")
    monkeypatch.setattr(tri, "extraire_vignette",
                        lambda *a, **k: np.zeros((64, 64, 3), dtype=np.uint8))
    monkeypatch.setattr(tri, "charger_parcelles", lambda cfg: None)
    monkeypatch.setattr(tri, "charger_pci_piscines", lambda cfg: None)

    out_dir = tmp_path / "tri"
    tri.generer_planche(cand, tmp_path / "ortho", cfg, out_dir,
                        candidats_path=cand_path, embarquer=True)
    html = (out_dir / "tri.html").read_text()
    assert "data:image/jpeg;base64," in html
    assert "vignettes/" not in html  # aucune référence externe
    assert "data-planche=" in html


def test_reutiliser_vignettes_embarquer_relit_les_png(tmp_path, monkeypatch):
    """--embarquer + --reutiliser-vignettes : les PNG existants sont relus et
    ré-encodés en JPEG inline (pas de re-rendu)."""
    import numpy as np
    from PIL import Image

    cfg = {"dept": "49", "paths": {"interim": str(tmp_path)},
           "tri_visuel": {"vignette_m": 60, "vignette_px": 64}}
    cand = _candidats_mini(tmp_path)
    cand_path = tmp_path / "piscines_candidates_49_49035.parquet"
    cand.to_parquet(cand_path)

    out_dir = tmp_path / "tri"
    vign = out_dir / "vignettes"
    vign.mkdir(parents=True)
    Image.fromarray(np.full((64, 64, 3), 128, dtype=np.uint8)).save(vign / "pisc_x.png")

    monkeypatch.setattr(tri, "indexer_dalles", lambda d: {"paths": ["dalle.tif"]})
    monkeypatch.setattr(tri, "dalle_pour", lambda x, y, idx: "dalle.tif")

    def _boom(*a, **k):
        raise AssertionError("extraire_vignette ne doit pas être appelée en réutilisation")

    monkeypatch.setattr(tri, "extraire_vignette", _boom)
    monkeypatch.setattr(tri, "charger_parcelles", lambda cfg: None)
    monkeypatch.setattr(tri, "charger_pci_piscines", lambda cfg: None)

    tri.generer_planche(cand, tmp_path / "ortho", cfg, out_dir,
                        candidats_path=cand_path, reutiliser_vignettes=True, embarquer=True)
    html = (out_dir / "tri.html").read_text()
    assert "data:image/jpeg;base64," in html
    assert "vignettes/" not in html


# ------------------------------------ FIX 1 : contrôle d'empreinte au --apply

def _prep_apply(tmp_path, monkeypatch):
    import pandas as pd
    cfg = {"dept": "49", "paths": {"interim": str(tmp_path)}}
    cand = _candidats_mini(tmp_path)
    cand_path = tmp_path / "piscines_candidates_49_49035.parquet"
    cand.to_parquet(cand_path)
    dec = tmp_path / "decisions.csv"
    pd.DataFrame({"id_detection": ["pisc_x"], "decision": ["oui"]}).to_csv(dec, index=False)
    monkeypatch.setattr(tri, "load_config", lambda: cfg)
    monkeypatch.setattr(tri, "ensure_dirs", lambda c: None)
    return cand_path, dec


def test_apply_refuse_planche_hash_different(tmp_path, monkeypatch):
    """--planche-hash faux → SystemExit clair, aucune écriture."""
    import sys
    import pytest
    cand_path, dec = _prep_apply(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [
        "prog", "--candidats", str(cand_path), "--apply", str(dec),
        "--planche-hash", "000000000000",
    ])
    with pytest.raises(SystemExit, match="autre version des candidats"):
        tri.main()


def test_apply_force_outrepasse_le_hash(tmp_path, monkeypatch):
    """--force applique malgré un --planche-hash faux : la base de sortie est écrite."""
    import sys
    cand_path, dec = _prep_apply(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [
        "prog", "--candidats", str(cand_path), "--apply", str(dec),
        "--planche-hash", "000000000000", "--force",
    ])
    tri.main()
    assert (tmp_path / "piscines_detectees_49.parquet").exists()


def test_apply_hash_correct_passe(tmp_path, monkeypatch):
    """Le bon hash12 laisse passer l'application."""
    import sys
    cand_path, dec = _prep_apply(tmp_path, monkeypatch)
    bon = tri.hash12_parquet(cand_path)
    monkeypatch.setattr(sys, "argv", [
        "prog", "--candidats", str(cand_path), "--apply", str(dec),
        "--planche-hash", bon,
    ])
    tri.main()
    assert (tmp_path / "piscines_detectees_49.parquet").exists()
