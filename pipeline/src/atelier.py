"""Atelier d'annotation — le bench local multi-passes, multi-niveaux, multi-produits.

Un seul serveur sur la machine de JB, une seule page dans le navigateur, et du
temps de cerveau disponible transformé en données d'or. Ce que font toutes les
plateformes de labellisation (reCAPTCHA, Mechanical Turk, Label Studio), version
artisanale et locale :

  - NIVEAU 1 « existence »  : y a-t-il une piscine dans le contour rouge ? (O/N/U)
  - NIVEAU 2 « adresse »    : à quelle maison appartient-elle ? (débloqué quand
    l'existence est acquise : majorité de « oui » sur les votes)
  - passes ILLIMITÉES : chaque réponse est un VOTE horodaté (trieur, timestamp).
    On ne remplace jamais, on accumule — la vérité sort de la majorité, la
    confiance du taux d'accord et du nombre de passes.
  - file d'attente « moins vu d'abord » : l'item servi est tiré au hasard PARMI
    les moins votés du mode (couverture uniforme, pas de biais d'ordre).
  - progression visible : passe courante, jauge de couverture, XP, série.

Usage :
    .venv/bin/python pipeline/src/atelier.py [--port 8199] \
        [--candidats data/interim/piscines_candidates_49_49035.parquet] \
        [--ortho-dir data/raw/bdortho/49035/rvb]
    → http://localhost:8199

Les votes vivent dans data/atelier/atelier.sqlite. Au premier lancement, les
acquis existants sont importés comme passe n°1 : décisions de tri fusionnées
(handoff/decisions_recus/_fusion.csv) et dernière concordance d'adresses
(handoff/concordance_recus/). Rien n'est perdu, on repart d'où on en est.

Exports (contrats compatibles avec la chaîne existante) :
    /api/export/existence.csv  → id_detection,decision,n_votes,accord
    /api/export/adresse.csv    → id_piscine,id_ban_choisi_humain,id_ban_assigne_auto,concordance,n_votes,accord
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import random
import sqlite3
import threading
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import geopandas as gpd
import pandas as pd

from common import ensure_dirs, load_config

tri = importlib.import_module("16_tri_visuel")
v17 = importlib.import_module("17_verification_adresse")

log = logging.getLogger("atelier")

MODES = ("existence", "adresse")

# Registre des produits farmables. En ajouter un = une entrée ici + un parquet de
# candidats + des vignettes (16_tri_visuel --out-dir dédié). Le niveau adresse
# n'existe que si le produit a une base adressée (20_join).
PRODUITS = {
    "piscines": {
        "question": "Y a-t-il une piscine dans le contour rouge ?",
        "bouton_oui": "Piscine", "bouton_non": "Pas une piscine",
        "candidats": "piscines_candidates_49_49035.parquet",
        "vignettes": "tri/vignettes",
        "vignette_m": 60,
        "adressees": "piscines_adressees_49.parquet",
    },
    "terrasses": {
        "question": "La zone rouge est-elle un jardin / une terrasse dégagé(e) au soleil ?",
        "bouton_oui": "Oui, dégagé", "bouton_non": "Non (toit, route, artefact…)",
        "candidats": "terrasses_a_farmer_49_49035.parquet",
        "vignettes": "tri_terrasses/vignettes",
        "vignette_m": 100,
        "adressees": None,          # pas de niveau adresse (pas encore de 20_join terrasses)
    },
}


# ------------------------------------------------------------------ votes (DB)

class Votes:
    """Stockage append-only des votes, thread-safe. Un vote = (produit, mode,
    id_item, reponse, trieur, ts). Jamais d'UPDATE : la passe N s'ajoute à la
    passe N-1, c'est le principe du multi-passes."""

    def __init__(self, chemin: Path):
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(chemin, check_same_thread=False)
        self.lock = threading.Lock()
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS votes ("
            " produit TEXT, mode TEXT, id_item TEXT, reponse TEXT,"
            " trieur TEXT, ts TEXT)")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_votes ON votes (produit, mode, id_item)")
        # Signalements : « je vois une piscine ICI » — points cliqués hors contour,
        # en Lambert-93. Donnée de RAPPEL (détections manquées), recoupée plus tard
        # avec cadastre/CoSIA. Append-only comme les votes.
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS signalements ("
            " produit TEXT, id_item TEXT, x_l93 REAL, y_l93 REAL,"
            " trieur TEXT, ts TEXT)")
        self.conn.commit()

    def ajouter(self, produit: str, mode: str, id_item: str, reponse: str, trieur: str):
        with self.lock:
            self.conn.execute(
                "INSERT INTO votes VALUES (?,?,?,?,?,?)",
                (produit, mode, str(id_item), reponse, trieur,
                 datetime.now(timezone.utc).isoformat()))
            self.conn.commit()

    def compte_par_item(self, produit: str, mode: str) -> Counter:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id_item, COUNT(*) FROM votes WHERE produit=? AND mode=? "
                "GROUP BY id_item", (produit, mode)).fetchall()
        return Counter(dict(rows))

    def votes_item(self, produit: str, mode: str, id_item: str) -> list[str]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT reponse FROM votes WHERE produit=? AND mode=? AND id_item=?",
                (produit, mode, str(id_item))).fetchall()
        return [r[0] for r in rows]

    def tout(self, produit: str, mode: str) -> dict[str, list[str]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id_item, reponse FROM votes WHERE produit=? AND mode=?",
                (produit, mode)).fetchall()
        d: dict[str, list[str]] = {}
        for id_item, rep in rows:
            d.setdefault(id_item, []).append(rep)
        return d

    def total(self) -> int:
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0]

    def vide(self) -> bool:
        return self.total() == 0

    def signaler(self, produit: str, id_item: str, x: float, y: float, trieur: str):
        with self.lock:
            self.conn.execute(
                "INSERT INTO signalements VALUES (?,?,?,?,?,?)",
                (produit, str(id_item), float(x), float(y), trieur,
                 datetime.now(timezone.utc).isoformat()))
            self.conn.commit()

    def signalements_csv(self) -> str:
        with self.lock:
            rows = self.conn.execute(
                "SELECT produit,id_item,x_l93,y_l93,trieur,ts FROM signalements").fetchall()
        lignes = ["produit,id_item,x_l93,y_l93,trieur,ts"]
        lignes += [",".join(str(c) for c in r) for r in rows]
        return "\n".join(lignes) + "\n"

    def stats_trieur(self, trieur: str, seuil_pause_s: float = 60.0) -> dict:
        """Rythme réel depuis les horodatages : temps actif = somme des écarts
        entre votes consécutifs < seuil (une pause café ne compte pas)."""
        with self.lock:
            rows = self.conn.execute(
                "SELECT ts FROM votes WHERE trieur=? ORDER BY ts", (trieur,)).fetchall()
        n = len(rows)
        actif = 0.0
        for a, b in zip(rows, rows[1:]):
            try:
                d = (datetime.fromisoformat(b[0]) - datetime.fromisoformat(a[0])).total_seconds()
            except ValueError:
                continue
            if 0 <= d < seuil_pause_s:
                actif += d
        return {"votes": n, "temps_actif_s": round(actif),
                "votes_par_h": round(n / (actif / 3600)) if actif > 30 else None}

    def dernier_de(self, produit: str, mode: str, id_item: str, trieur: str) -> str | None:
        """Dernière réponse de CE trieur sur cet item (pour l'afficher au retour
        arrière et proposer la correction plutôt que le doublon)."""
        with self.lock:
            row = self.conn.execute(
                "SELECT reponse FROM votes WHERE produit=? AND mode=? AND id_item=? "
                "AND trieur=? ORDER BY rowid DESC LIMIT 1",
                (produit, mode, str(id_item), trieur)).fetchone()
        return row[0] if row else None

    def remplacer_dernier(self, produit: str, mode: str, id_item: str, reponse: str, trieur: str):
        """Corrige le DERNIER vote de ce trieur sur cet item (navigation arrière) :
        on supprime sa dernière réponse puis on insère la nouvelle. Le multi-passes
        reste append-only pour tout le reste — corriger sa propre erreur de clic
        n'est pas une nouvelle passe."""
        with self.lock:
            row = self.conn.execute(
                "SELECT rowid FROM votes WHERE produit=? AND mode=? AND id_item=? "
                "AND trieur=? ORDER BY rowid DESC LIMIT 1",
                (produit, mode, str(id_item), trieur)).fetchone()
            if row:
                self.conn.execute("DELETE FROM votes WHERE rowid=?", (row[0],))
                self.conn.commit()
        self.ajouter(produit, mode, id_item, reponse, trieur)


# --------------------------------------------------------------- logique pure

def consensus(votes: list[str]) -> tuple[str | None, float]:
    """(réponse majoritaire, taux d'accord). Égalité → (None, taux). Pure."""
    if not votes:
        return None, 0.0
    c = Counter(votes).most_common()
    if len(c) > 1 and c[0][1] == c[1][1]:
        return None, c[0][1] / len(votes)
    return c[0][0], c[0][1] / len(votes)


def existence_acquise(votes: list[str]) -> bool:
    """Le niveau adresse se débloque quand la majorité des votes dit « oui ». Pure."""
    maj, _ = consensus(votes)
    return maj == "oui"


def choisir_moins_vu(ids: list[str], compte: Counter, rng: random.Random,
                     prioritaires: set | None = None) -> str | None:
    """Un id au hasard PARMI les moins votés (couverture uniforme, ordre
    imprévisible — l'ennui vient de la prévisibilité). Les `prioritaires`
    (désaccords : votes à égalité) passent en tête DANS le groupe des moins vus :
    une passe de plus tranche d'abord ce qui est contesté. Pure (rng injecté)."""
    if not ids:
        return None
    mini = min(compte.get(i, 0) for i in ids)
    groupe = [i for i in ids if compte.get(i, 0) == mini]
    if prioritaires:
        contestes = [i for i in groupe if i in prioritaires]
        if contestes:
            groupe = contestes
    return rng.choice(groupe)


# ------------------------------------------------------------------- données

class Ressources:
    """Actifs géo partagés entre produits : BAN, parcelles, dalles ortho, cache."""

    def __init__(self, cfg: dict, ortho_dir: Path | None):
        interim = Path(cfg["paths"]["interim"])
        dept = cfg["dept"]
        self.cache_dir = interim.parent / "atelier" / "cache_ortho"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ban = gpd.read_parquet(interim / f"ban_{dept}.parquet").to_crs(cfg["crs_metric"])
        self.ban = self.ban.drop_duplicates("id_ban")
        self.ban.sindex
        pparc = interim / f"parcelles_{dept}.parquet"
        self.parcelles = (gpd.read_parquet(pparc, columns=["id", "geometry"])
                          .to_crs(cfg["crs_metric"]) if pparc.exists() else None)
        if self.parcelles is not None:
            self.parcelles.sindex
        self.index_dalles = tri.indexer_dalles(ortho_dir) if ortho_dir else None


class Donnees:
    """Données d'UN produit : candidats + vignettes (existence), base adressée
    (niveau adresse, optionnel). Les actifs lourds partagés vivent dans Ressources."""

    def __init__(self, cfg: dict, nom: str, pcfg: dict, res: Ressources):
        interim = Path(cfg["paths"]["interim"])
        self.nom, self.meta, self.res = nom, pcfg, res
        self.vignettes_dir = interim / pcfg["vignettes"]
        self.cache_dir = res.cache_dir
        self.ban, self.parcelles = res.ban, res.parcelles
        self.index_dalles = res.index_dalles

        cand = gpd.read_parquet(interim / pcfg["candidats"])
        self.candidats = cand.assign(id_detection=cand["id_detection"].astype(str))
        log.info("[%s] %d candidats (existence).", nom, len(self.candidats))

        self.adressees = None
        if pcfg["adressees"]:
            adressees = gpd.read_parquet(interim / pcfg["adressees"])
            self.adressees = adressees.assign(
                id_detection=adressees["id_detection"].astype(str),
                id_piscine=adressees["id_piscine"].astype(str))
        self._cache_items_adresse: dict[str, dict] = {}
        self._dispo: tuple[float, set] = (0.0, set())

    def ids_disponibles(self) -> set[str]:
        """Ids dont la vignette PNG existe SUR DISQUE — pendant qu'une génération
        tourne (16_tri_visuel), on ne sert que le déjà-prêt. Cache 15 s."""
        import time
        ts, dispo = self._dispo
        if time.monotonic() - ts > 15:
            dispo = {p.stem for p in self.vignettes_dir.glob("*.png")}
            self._dispo = (time.monotonic(), dispo)
        return dispo

    # --- existence -----------------------------------------------------------
    def item_existence(self, id_detection: str) -> dict | None:
        row = self.candidats[self.candidats["id_detection"] == id_detection]
        if row.empty:
            return None
        r = row.iloc[0]
        pt = r.geometry.representative_point()
        return {"id": id_detection,
                "png": f"/api/vignette/{self.nom}/{id_detection}.png",
                "surface": float(r["surface_m2"]),
                "score": float(r["score_detection"]),
                "cx": round(float(pt.x), 2), "cy": round(float(pt.y), 2),
                "cote_m": self.meta.get("vignette_m", 60)}

    # --- adresse -------------------------------------------------------------
    def item_adresse(self, id_piscine: str) -> dict | None:
        if self.adressees is None:
            return None
        if id_piscine in self._cache_items_adresse:
            return self._cache_items_adresse[id_piscine]
        row = self.adressees[self.adressees["id_piscine"] == id_piscine]
        if row.empty or not row.iloc[0].geometry or row.iloc[0].geometry.geom_type == "Point":
            return None
        item = v17.construire_item(row.iloc[0], self.ban, self.parcelles, image_b64=None)
        if not item["adresses"]:
            return None                       # rien à cliquer : invérifiable
        item["img"] = f"/api/ortho/{self.nom}/{id_piscine}.jpg"
        self._cache_items_adresse[id_piscine] = item
        return item

    def ortho_jpeg(self, id_piscine: str) -> bytes | None:
        cache = self.cache_dir / f"{self.nom}_{id_piscine}.jpg"
        if cache.exists():
            return cache.read_bytes()
        if self.index_dalles is None or self.adressees is None:
            return None
        row = self.adressees[self.adressees["id_piscine"] == id_piscine]
        if row.empty:
            return None
        pt = row.iloc[0].geometry.representative_point()
        dalle = tri.dalle_pour(pt.x, pt.y, self.index_dalles)
        if dalle is None:
            return None
        img = tri.extraire_vignette(dalle, pt.x, pt.y, v17.CROP_ORTHO_M, v17.IMG_PX)
        data = tri.jpeg_bytes(img)
        cache.write_bytes(data)
        return data

    def vignette_png(self, id_detection: str) -> bytes | None:
        p = self.vignettes_dir / f"{id_detection}.png"
        return p.read_bytes() if p.exists() else None


# ----------------------------------------------------------------- amorçage

def amorcer_depuis_acquis(votes: Votes, repo: Path):
    """Premier lancement : importe les décisions déjà rendues (tri fusionné +
    dernière concordance) comme passe n°1. On ne repart JAMAIS de zéro."""
    fusion = repo / "handoff" / "decisions_recus" / "_fusion.csv"
    if fusion.exists():
        df = pd.read_csv(fusion)
        for _, r in df.iterrows():
            votes.ajouter("piscines", "existence", str(r["id_detection"]),
                          str(r["decision"]), str(r.get("trieur", "import")))
        log.info("Amorçage existence : %d votes importés de %s.", len(df), fusion.name)
    conc_dir = repo / "handoff" / "concordance_recus"
    fichiers = sorted(conc_dir.glob("concordance_*.csv")) if conc_dir.exists() else []
    if fichiers:
        df = pd.read_csv(fichiers[-1])
        for _, r in df.iterrows():
            votes.ajouter("piscines", "adresse", str(r["id_piscine"]),
                          str(r["id_ban_choisi_humain"]), "JB")
        log.info("Amorçage adresse : %d votes importés de %s.", len(df), fichiers[-1].name)


# ------------------------------------------------------------------- serveur

def etat_global(donnees: Donnees, votes: Votes) -> dict:
    """Statistiques de progression par mode : items, couverture de la passe
    courante, passe minimale/maximale, accord moyen sur les items votés."""
    out = {}
    produit = donnees.nom
    ids_exist = list(donnees.candidats["id_detection"])
    tout_exist = votes.tout(produit, "existence")
    ids_adresse = ids_adresse_debloques(donnees, tout_exist)
    for mode, ids in (("existence", ids_exist), ("adresse", ids_adresse)):
        t = votes.tout(produit, mode)
        compte = {i: len(t.get(i, [])) for i in ids}
        n = len(ids)
        passe_min = min(compte.values()) if compte else 0
        accords = [consensus(t[i])[1] for i in ids if t.get(i)]
        out[mode] = {
            "items": n,
            "passe_courante": passe_min + 1,
            "restants_cette_passe": sum(1 for v in compte.values() if v == passe_min) if n else 0,
            "votes": sum(compte.values()),
            "accord_moyen": round(sum(accords) / len(accords), 3) if accords else None,
        }
    out["xp"] = votes.total()
    return out


def ids_adresse_debloques(donnees: Donnees, votes_existence: dict[str, list[str]]) -> list[str]:
    """Le niveau adresse ne propose que les piscines dont l'existence est acquise
    (majorité de oui) ET qui ont au moins une adresse candidate."""
    if donnees.adressees is None:
        return []
    ids = []
    for _, r in donnees.adressees.iterrows():
        if existence_acquise(votes_existence.get(r["id_detection"], [])):
            ids.append(r["id_piscine"])
    return ids


class Handler(BaseHTTPRequestHandler):
    produits: dict[str, Donnees] = None    # injectés au démarrage
    votes: Votes = None
    rng = random.Random()
    # HTTP/1.1 = keep-alive : le navigateur réutilise ses connexions au lieu
    # d'en rouvrir une par image (on envoie toujours Content-Length).
    protocol_version = "HTTP/1.1"

    def _produit(self, q) -> Donnees | None:
        return self.produits.get(q.get("produit", ["piscines"])[0])

    def log_message(self, fmt, *args):   # silence le log par requête
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _binaire(self, data: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def _csv(self, texte: str, nom: str):
        data = texte.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{nom}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        d, v = self._produit(q), self.votes
        if d is None:
            self.send_error(404, "produit inconnu")
            return
        produit = d.nom

        if u.path == "/":
            data = PAGE_HTML.encode()
            self._binaire(data, "text/html; charset=utf-8")
        elif u.path == "/api/produits":
            self._json([{"nom": n, "question": p.meta["question"],
                         "bouton_oui": p.meta["bouton_oui"],
                         "bouton_non": p.meta["bouton_non"],
                         "adresse": p.adressees is not None}
                        for n, p in self.produits.items()])
        elif u.path == "/api/etat":
            e = etat_global(d, v)
            trieur = q.get("trieur", [""])[0]
            if trieur:
                e["rythme"] = v.stats_trieur(trieur)
            self._json(e)
        elif u.path == "/api/export/signalements.csv":
            self._csv(v.signalements_csv(), "signalements.csv")
        elif u.path == "/api/tache":
            mode = q.get("mode", ["existence"])[0]
            sauf = q.get("sauf", [None])[0]
            if mode == "existence":
                dispo = d.ids_disponibles()
                ids = [i for i in d.candidats["id_detection"] if i in dispo and i != sauf]
                tout = v.tout(produit, "existence")
                contestes = {i for i, vs in tout.items() if consensus(vs)[0] is None and vs}
                id_item = choisir_moins_vu(ids, v.compte_par_item(produit, "existence"),
                                           self.rng, prioritaires=contestes)
                item = d.item_existence(id_item) if id_item else None
            else:
                ids = ids_adresse_debloques(d, v.tout(produit, "existence"))
                # ne proposer que les items qui ont des candidates cliquables
                ids = [i for i in ids if i != sauf and d.item_adresse(i)]
                id_item = choisir_moins_vu(ids, v.compte_par_item(produit, "adresse"), self.rng)
                item = d.item_adresse(id_item) if id_item else None
            if item is None:
                self._json({"vide": True})
                return
            id_item = item.get("id") or item.get("id_piscine")
            trieur = q.get("trieur", [""])[0]
            self._json({"item": item, "deja_vu": len(v.votes_item(produit, mode, id_item)),
                        "mon_dernier": v.dernier_de(produit, mode, id_item, trieur) if trieur else None})
        elif u.path == "/api/item":
            # Item PRÉCIS (navigation avant/arrière dans l'historique de session).
            mode = q.get("mode", ["existence"])[0]
            id_item = q.get("id", [""])[0]
            trieur = q.get("trieur", [""])[0]
            item = d.item_existence(id_item) if mode == "existence" else d.item_adresse(id_item)
            if item is None:
                self._json({"vide": True})
                return
            self._json({"item": item, "deja_vu": len(v.votes_item(produit, mode, id_item)),
                        "mon_dernier": v.dernier_de(produit, mode, id_item, trieur) if trieur else None})
        elif u.path.startswith("/api/vignette/"):
            # /api/vignette/{produit}/{id}.png — le produit est DANS le chemin
            # (les <img> ne portent pas de query string produit).
            parts = u.path.split("/")
            dp = self.produits.get(parts[3]) if len(parts) == 5 else None
            data = dp.vignette_png(parts[4].removesuffix(".png")) if dp else None
            if data is None:
                self.send_error(404)
            else:
                self._binaire(data, "image/png")
        elif u.path.startswith("/api/ortho/"):
            parts = u.path.split("/")
            dp = self.produits.get(parts[3]) if len(parts) == 5 else None
            data = dp.ortho_jpeg(parts[4].removesuffix(".jpg")) if dp else None
            if data is None:
                self.send_error(404)
            else:
                self._binaire(data, "image/jpeg")
        elif u.path == "/api/export/existence.csv":
            lignes = ["id_detection,decision,n_votes,accord"]
            for i, vs in sorted(v.tout(produit, "existence").items()):
                maj, acc = consensus(vs)
                lignes.append(f"{i},{maj or 'incertain'},{len(vs)},{acc:.2f}")
            self._csv("\n".join(lignes) + "\n", f"existence_consensus_{produit}.csv")
        elif u.path == "/api/export/adresse.csv":
            if d.adressees is None:
                self.send_error(404, "pas de niveau adresse pour ce produit")
                return
            assigne = dict(zip(d.adressees["id_piscine"],
                               d.adressees["id_ban"].astype(str)))
            lignes = ["id_piscine,id_ban_choisi_humain,id_ban_assigne_auto,concordance,n_votes,accord"]
            for i, vs in sorted(v.tout(produit, "adresse").items()):
                maj, acc = consensus(vs)
                auto = assigne.get(i, "")
                conc = str(maj == auto).lower() if maj and auto and auto != "nan" else ""
                lignes.append(f"{i},{maj or ''},{auto if auto != 'nan' else ''},{conc},{len(vs)},{acc:.2f}")
            self._csv("\n".join(lignes) + "\n", "adresse_consensus.csv")
        else:
            self.send_error(404)

    # ----------------------------------------------------------------- POST
    def do_POST(self):
        chemin = urlparse(self.path).path
        if chemin == "/api/signalement":
            corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            d = self.produits.get(corps.get("produit", ""))
            item = d.item_existence(str(corps["id_item"])) if d else None
            if item is None:
                self._json({"erreur": "item inconnu"}, 400)
                return
            # (fx, fy) = position du clic en fraction de l'image (0-1, origine
            # en haut à gauche) → Lambert-93 via le centre et le côté du crop.
            try:
                fx, fy = float(corps["fx"]), float(corps["fy"])
            except (TypeError, ValueError, KeyError):
                self._json({"erreur": "fx/fy invalides"}, 400)
                return
            if not (0 <= fx <= 1 and 0 <= fy <= 1):
                self._json({"erreur": "fx/fy hors de l'image"}, 400)
                return
            x = item["cx"] + (fx - 0.5) * item["cote_m"]
            y = item["cy"] + (0.5 - fy) * item["cote_m"]
            self.votes.signaler(corps["produit"], corps["id_item"], x, y,
                                str(corps.get("trieur") or "anonyme"))
            self._json({"ok": True, "x_l93": round(x, 2), "y_l93": round(y, 2)})
            return
        if chemin != "/api/reponse":
            self.send_error(404)
            return
        corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        produit = corps.get("produit", "piscines")
        if produit not in self.produits:
            self._json({"erreur": "produit inconnu"}, 400)
            return
        mode, id_item = corps["mode"], str(corps["id_item"])
        reponse, trieur = str(corps["reponse"]), str(corps.get("trieur") or "anonyme")
        # 'indecis' = « je ne peux pas répondre » : un vrai vote (l'item ne
        # reviendra pas cette passe), jamais vendu, exclu du consensus utile.
        valides = {"existence": {"oui", "non", "incertain"}}
        if mode not in MODES or (mode in valides and reponse not in valides[mode]):
            self._json({"erreur": "mode ou réponse invalide"}, 400)
            return
        if corps.get("remplacer"):
            self.votes.remplacer_dernier(produit, mode, id_item, reponse, trieur)
        else:
            self.votes.ajouter(produit, mode, id_item, reponse, trieur)
        vs = self.votes.votes_item(produit, mode, id_item)
        maj, acc = consensus(vs)
        total = self.votes.total()
        if total % 100 == 0:
            # Point de sauvegarde : consensus du produit dumpé sur disque (en plus
            # du SQLite qui, lui, est écrit à CHAQUE vote).
            dossier = Path(self.produits[produit].cache_dir).parent / "exports"
            dossier.mkdir(parents=True, exist_ok=True)
            lignes = ["id_item,decision,n_votes,accord"]
            for i, vv in sorted(self.votes.tout(produit, mode).items()):
                m2, a2 = consensus(vv)
                lignes.append(f"{i},{m2 or 'indecis'},{len(vv)},{a2:.2f}")
            (dossier / f"{produit}_{mode}_consensus.csv").write_text(
                "\n".join(lignes) + "\n", encoding="utf-8")
        self._json({"ok": True, "n_votes": len(vs), "majorite": maj, "accord": acc,
                    "total": total, "checkpoint": total % 100 == 0})


# ------------------------------------------------------------------ page HTML

PAGE_HTML = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>L'Atelier — farm d'annotation</title>
<style>
/* Thème unique sombre ASSUMÉ : outil d'imagerie aérienne pour sessions du soir,
   comme tous les benchs de labellisation. Un seul accent (lime = récolte/XP),
   la sémantique des réponses (oui/non/indécis/aucune) est un axe séparé. */
:root{
  --bg:#0f1115; --panel:#151920; --raise:#1c2129; --line:#272e39;
  --ink:#e7ebf2; --mut:#8b94a3; --acc:#a3e635; --acc-ink:#1a2405;
  --oui:#2fbf71; --non:#e5484d; --unsure:#f0a020; --aucune:#b083f0;
  --r:10px; --mono:ui-monospace,'SF Mono',Menlo,monospace;
}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
kbd{font-family:var(--mono);font-size:.82em;background:#0a0c10;border:1px solid var(--line);
    border-bottom-width:2px;border-radius:5px;padding:1px 7px;color:var(--mut)}
button{font:inherit;cursor:pointer}

/* ---------- HUD ---------- */
header{position:sticky;top:0;z-index:10;background:var(--panel);border-bottom:1px solid var(--line)}
#hud{display:flex;align-items:center;gap:14px;padding:10px 18px;flex-wrap:wrap}
#marque{font-family:var(--mono);font-weight:bold;letter-spacing:.14em;font-size:.8rem;color:var(--acc)}
#marque small{display:block;letter-spacing:.02em;color:var(--mut);font-weight:normal;text-transform:none}
#niveaux{display:flex;gap:6px}
.niveau{padding:7px 14px;border-radius:999px;background:var(--raise);border:1px solid var(--line);
        color:var(--mut);font-weight:600;font-size:.88rem;border-bottom-width:2px}
.niveau.actif{background:var(--acc);border-color:var(--acc);color:var(--acc-ink)}
.niveau .sous{font-weight:normal;font-size:.78rem;opacity:.8}
#chips{display:flex;gap:8px;margin-left:auto;flex-wrap:wrap}
.chip{background:var(--raise);border:1px solid var(--line);border-radius:8px;padding:4px 10px;
      font-size:.78rem;color:var(--mut);text-align:center;min-width:58px}
.chip b{display:block;font-family:var(--mono);font-size:1rem;color:var(--ink)}
.chip.acc b{color:var(--acc)}
#btn-export{background:none;border:1px solid var(--line);border-radius:8px;color:var(--mut);padding:6px 12px}
#btn-export:hover{color:var(--ink);border-color:var(--mut)}
#jauge-fond{height:4px;background:var(--raise)}
#jauge{height:100%;width:0;background:var(--acc);transition:width .25s}

/* ---------- scène ---------- */
#zone{display:flex;gap:22px;padding:18px;align-items:flex-start;justify-content:center;flex-wrap:wrap}
#cadre{position:relative;background:#000;border:1px solid var(--line);border-radius:var(--r);
       overflow:hidden;box-shadow:0 10px 40px #0008;flex:0 1 auto;max-width:min(74vh,100%)}
#cadre img,#cadre svg{display:block;max-width:100%;height:auto}
#cadre.flash-oui{outline:3px solid var(--oui)}
#cadre.flash-non{outline:3px solid var(--non)}
#cadre.flash-incertain,#cadre.flash-indecis{outline:3px solid var(--unsure)}
#cadre.flash-aucune,#cadre.flash-adresse{outline:3px solid var(--aucune)}
#badge-vu{position:absolute;top:10px;right:10px;background:#0a0c10cc;border:1px solid var(--line);
          border-radius:999px;padding:3px 10px;font-size:.75rem;color:var(--mut);font-family:var(--mono)}
#badge-deja{position:absolute;top:10px;left:10px;background:#0a0c10cc;border:1px solid var(--unsure);
            border-radius:999px;padding:3px 10px;font-size:.75rem;color:var(--unsure);display:none}
#panneau{width:380px;max-width:100%;display:flex;flex-direction:column;gap:12px}
#question{font-size:1.18rem;font-weight:700;line-height:1.3;text-wrap:balance}
#detail{color:var(--mut);font-size:.85rem;font-family:var(--mono)}

/* réponses = keycaps */
#boutons{display:flex;flex-direction:column;gap:8px}
.keycap{display:flex;align-items:center;gap:12px;width:100%;text-align:left;
        background:var(--raise);border:1px solid var(--line);border-bottom-width:3px;
        border-radius:var(--r);padding:11px 14px;color:var(--ink);font-weight:600;font-size:.95rem;
        transition:transform .06s,border-color .12s}
.keycap:hover{border-color:var(--mut)}
.keycap:active{transform:translateY(2px);border-bottom-width:1px}
.keycap .k{font-family:var(--mono);font-weight:bold;min-width:2em;text-align:center;
           border-radius:6px;padding:4px 0;color:#0a0c10}
.keycap.oui .k{background:var(--oui)}.keycap.non .k{background:var(--non)}
.keycap.unsure .k{background:var(--unsure)}.keycap.aucune .k{background:var(--aucune)}
.keycap.neutre .k{background:var(--mut)}
#liste-adr{max-height:236px;overflow:auto;border:1px solid var(--line);border-radius:var(--r);
           font-size:.88rem;background:var(--panel)}
#liste-adr .row{padding:6px 10px;cursor:pointer;display:flex;gap:10px;border-bottom:1px solid var(--line)}
#liste-adr .row:last-child{border-bottom:none}
#liste-adr .row:hover{background:var(--raise)}
#liste-adr .row.choisie{background:#2a3a1a;color:var(--acc)}
.num{font-family:var(--mono);font-weight:bold;min-width:1.6em;color:var(--mut)}
#nav-aide{color:var(--mut);font-size:.8rem;line-height:1.9}

/* ---------- historique de session ---------- */
#histo-barre{position:fixed;bottom:0;left:0;right:0;background:var(--panel);
             border-top:1px solid var(--line);padding:8px 18px;display:flex;gap:10px;align-items:center}
#histo-titre{font-size:.72rem;letter-spacing:.1em;color:var(--mut);font-family:var(--mono)}
#histo{display:flex;gap:5px;overflow-x:auto;flex:1;padding:2px}
.pas{width:14px;height:14px;border-radius:4px;background:var(--raise);border:1px solid var(--line);
     flex:0 0 auto;cursor:pointer}
.pas.oui{background:var(--oui)}.pas.non{background:var(--non)}
.pas.incertain,.pas.indecis{background:var(--unsure)}.pas.aucune{background:var(--aucune)}
.pas.adresse{background:var(--acc)}
.pas.courant{outline:2px solid var(--ink);outline-offset:1px}
body{padding-bottom:52px}

/* toast + série */
#toast{position:fixed;bottom:64px;left:50%;transform:translateX(-50%) translateY(6px);
       background:var(--raise);border:1px solid var(--acc);color:var(--ink);
       padding:8px 18px;border-radius:999px;font-weight:600;font-size:.88rem;
       opacity:0;transition:opacity .2s,transform .2s;pointer-events:none}
#toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
@keyframes pulse{50%{transform:scale(1.35)}}
.pulse{display:inline-block;animation:pulse .3s}
@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important}}

/* modal */
#modal-trieur{display:none;position:fixed;inset:0;z-index:50;background:#000b;
              align-items:center;justify-content:center}
#modal-trieur .boite{background:var(--panel);border:1px solid var(--line);border-radius:14px;
                     padding:26px;max-width:400px;width:90%}
#modal-trieur h2{margin:0 0 4px}
#modal-trieur p{color:var(--mut);margin:0 0 14px;font-size:.9rem}
#champ-trieur{width:100%;padding:11px;border-radius:8px;border:1px solid var(--line);
              background:var(--bg);color:var(--ink);font:inherit}
#modal-trieur .go{width:100%;margin-top:10px;background:var(--acc);color:var(--acc-ink);
                  border:none;border-radius:8px;padding:11px;font-weight:700}
</style></head><body>
<div id="modal-trieur"><div class="boite">
 <h2>Qui farme ?</h2>
 <p>Chaque réponse est signée : c'est ce qui permet de croiser les passes et de corriger ses propres votes.</p>
 <input id="champ-trieur" placeholder="prénom / pseudo" onkeydown="if(event.key==='Enter')definirTrieur(this.value)">
 <button class="go" onclick="definirTrieur(document.getElementById('champ-trieur').value)">Farmer</button>
</div></div>

<header>
 <div id="hud">
  <div id="marque">L'ATELIER<small>Bouchemaine</small></div>
  <div id="produits-sel" style="display:flex;gap:6px"></div>
  <div id="niveaux">
   <button class="niveau actif" id="ong-existence" onclick="changerMode('existence')">Niveau 1 · Existence</button>
   <button class="niveau" id="ong-adresse" onclick="changerMode('adresse')">Niveau 2 · Adresse <span class="sous" id="verrou-adresse"></span></button>
  </div>
  <div id="chips">
   <div class="chip">passe<b id="passe">—</b></div>
   <div class="chip">reste<b id="restants">—</b></div>
   <div class="chip">accord<b id="accord">—</b></div>
   <div class="chip acc">xp<b id="xp">—</b></div>
   <div class="chip acc">série<b id="serie">0</b></div>
   <div class="chip">session<b id="chrono">0:00</b></div>
   <div class="chip">rythme<b id="rythme">—</b></div>
  </div>
  <button id="btn-export" onclick="location.href='/api/export/'+MODE+'.csv?produit='+PRODUIT">Exporter</button>
 </div>
 <div id="jauge-fond"><div id="jauge"></div></div>
</header>

<div id="zone">
 <div id="cadre"><span id="badge-deja">déjà répondu — recliquer corrige</span><span id="badge-vu"></span></div>
 <div id="panneau">
  <div id="question">…</div>
  <div id="detail"></div>
  <div id="boutons"></div>
  <div id="liste-adr" style="display:none"></div>
  <div id="nav-aide" style="display:none"></div>
 </div>
</div>

<div id="histo-barre"><span id="histo-titre">SESSION</span><div id="histo"></div></div>
<div id="toast"></div>
<div id="pause" style="display:none;position:fixed;inset:0;z-index:60;background:#000d;
     align-items:center;justify-content:center;flex-direction:column;gap:10px;text-align:center">
 <div style="font-size:2.2rem;font-family:var(--mono);color:var(--acc)" id="pause-n"></div>
 <div style="color:var(--mut)" id="pause-stats"></div>
 <div style="color:var(--mut);font-size:.85rem">sauvegardé · respire · <span id="pause-cpt">3</span> s</div>
</div>

<script>
let PRODUIT = "piscines", PRODUITS = {}, MODE = "existence", ITEM = null, MON_DERNIER = null, serie = 0;
let actifS = 0, dernierVoteT = null;   // chrono de session (temps ACTIF)
setInterval(() => {
  if (dernierVoteT && (Date.now() - dernierVoteT) < 60000){
    actifS++;
    const m = Math.floor(actifS / 60), s = actifS % 60;
    document.getElementById("chrono").textContent = m + ":" + String(s).padStart(2, "0");
  }
}, 1000);
// Historique de session PAR produit/mode : liste d'items vus + curseur. Reculer
// montre l'item avec sa réponse ; re-répondre CORRIGE le dernier vote.
const histo = {};   // cle() -> [{id, rep}]
const idx = {};     // cle() -> curseur
function cle(){ return PRODUIT + "/" + MODE; }
function H(){ if(!(cle() in histo)){ histo[cle()] = []; idx[cle()] = -1; } return histo[cle()]; }
let TRIEUR = localStorage.getItem("atelier_trieur") || "";

function definirTrieur(n){ n=(n||"").trim(); if(!n) return; TRIEUR=n;
  localStorage.setItem("atelier_trieur", n);
  document.getElementById("modal-trieur").style.display="none"; }
if (!TRIEUR) document.getElementById("modal-trieur").style.display="flex";

async function etat(){
  const e = await (await fetch("/api/etat?produit=" + PRODUIT + "&trieur=" + encodeURIComponent(TRIEUR))).json();
  const m = e[MODE];
  document.getElementById("passe").textContent = m.passe_courante;
  document.getElementById("restants").textContent = m.restants_cette_passe;
  document.getElementById("jauge").style.width =
    (100 * (m.items - m.restants_cette_passe) / Math.max(1, m.items)) + "%";
  document.getElementById("accord").textContent =
    m.accord_moyen === null ? "—" : Math.round(m.accord_moyen * 100) + "%";
  document.getElementById("xp").textContent = e.xp;
  if (e.rythme && e.rythme.votes_par_h)
    document.getElementById("rythme").textContent = e.rythme.votes_par_h + "/h";
  const na = e.adresse.items;
  document.getElementById("verrou-adresse").textContent = na ? `· ${na}` : "· 🔒";
}

function changerMode(m){
  MODE = m;
  document.getElementById("ong-existence").classList.toggle("actif", m === "existence");
  document.getElementById("ong-adresse").classList.toggle("actif", m === "adresse");
  dessinerHisto();
  (idx[cle()] >= 0) ? charger(H()[idx[cle()]].id) : suivant();
}

// Préchargement : pendant que le trieur regarde l'item courant, on va chercher
// le suivant ET on décode son image. Au vote, l'affichage est instantané —
// c'est ça qui tient le rythme (le décodage JPEG2000 coûtait 2-3 s à froid).
let PRECHARGE = null;   // {cle, r, pret:Promise}
function precharger(){
  const c = cle();
  const courant = ITEM ? (ITEM.id || ITEM.id_piscine) : "";
  PRECHARGE = {cle: c, r: null};
  PRECHARGE.pret = (async () => {
    const r = await (await fetch(`/api/tache?produit=${PRODUIT}&mode=${MODE}` +
      `&trieur=${encodeURIComponent(TRIEUR)}&sauf=${encodeURIComponent(courant)}`)).json();
    if (!r.vide){
      const src = r.item.png || r.item.img;
      await new Promise(res => { const im = new Image(); im.onload = im.onerror = res; im.src = src; });
    }
    PRECHARGE.r = r;
  })();
}

async function suivant(){
  // avancer : d'abord dans l'historique, sinon une nouvelle tâche « moins vue »
  if (idx[cle()] < H().length - 1){
    idx[cle()]++;
    return charger(H()[idx[cle()]].id);
  }
  let r;
  if (PRECHARGE && PRECHARGE.cle === cle()){
    await PRECHARGE.pret;
    r = PRECHARGE.r;
    PRECHARGE = null;
    // le préchargé peut avoir déjà été vu dans la session (rare) : on le montre
    // quand même, le serveur l'a choisi parmi les moins vus.
  } else {
    r = await (await fetch(`/api/tache?produit=${PRODUIT}&mode=${MODE}&trieur=${encodeURIComponent(TRIEUR)}`)).json();
  }
  if (r.vide){ afficherVide(); etat(); return; }
  const id = r.item.id || r.item.id_piscine;
  H().push({id, rep: r.mon_dernier || null});
  idx[cle()] = H().length - 1;
  afficher(r);
}
function precedent(){
  if (idx[cle()] > 0){ idx[cle()]--; charger(H()[idx[cle()]].id); }
}
async function charger(id){
  const r = await (await fetch(`/api/item?produit=${PRODUIT}&mode=${MODE}&id=${encodeURIComponent(id)}&trieur=${encodeURIComponent(TRIEUR)}`)).json();
  if (!r.vide) afficher(r);
}

function afficherVide(){
  document.getElementById("cadre").innerHTML = "";
  document.getElementById("boutons").innerHTML = "";
  document.getElementById("liste-adr").style.display = "none";
  document.getElementById("question").textContent = MODE === "adresse"
    ? "Rien à vérifier ici : valide d'abord des piscines au niveau 1."
    : "Tout est fait pour cette passe. Respire, puis relance.";
  document.getElementById("detail").textContent = "";
}

function afficher(r){
  ITEM = r.item; MON_DERNIER = r.mon_dernier || null;
  etat(); dessinerHisto();
  const cadre = document.getElementById("cadre");
  cadre.className = "";
  const badges = `<span id="badge-deja">déjà répondu — recliquer corrige</span>`+
                 `<span id="badge-vu">${r.deja_vu} vote(s)</span>`;
  const boutons = document.getElementById("boutons");
  const liste = document.getElementById("liste-adr");
  if (MODE === "existence"){
    cadre.innerHTML = `<img src="${ITEM.png}" width="560" height="560" style="image-rendering:pixelated">` + badges;
    cadre.querySelector("img").addEventListener("click", clicImage);
    modeSignal = false; cadre.style.cursor = "";
    document.getElementById("question").textContent = PRODUITS[PRODUIT].question;
    document.getElementById("detail").textContent =
      `${ITEM.surface.toFixed(0)} m² · score ${ITEM.score.toFixed(2)} · ${ITEM.id}`;
    liste.style.display = "none"; liste.innerHTML = "";
    document.getElementById("nav-aide").style.display = "";
    document.getElementById("nav-aide").innerHTML =
      `<kbd>Q</kbd> oui · <kbd>D</kbd> non · <kbd>S</kbd> impossible à dire · <kbd>A</kbd> revenir ·
       <kbd>E</kbd> avancer · <kbd>ESPACE</kbd> passer (restera dû) · <kbd>F</kbd> puis clic = piscine vue ailleurs`;
    boutons.innerHTML =
      `<button class="keycap oui" onclick="repondre('oui')"><span class="k">Q</span>${PRODUITS[PRODUIT].bouton_oui}</button>
       <button class="keycap non" onclick="repondre('non')"><span class="k">D</span>${PRODUITS[PRODUIT].bouton_non}</button>
       <button class="keycap unsure" onclick="repondre('incertain')"><span class="k">S</span>Impossible à dire</button>
       <button class="keycap aucune" onclick="armerSignal()"><span class="k">F</span>Je vois une piscine ailleurs</button>`;
  } else {
    cadre.innerHTML = svgAdresse(ITEM) + badges;
    cadre.querySelectorAll(".pin").forEach(g =>
      g.addEventListener("click", () => repondre(ITEM.adresses[+g.dataset.k].id_ban)));
    document.getElementById("question").textContent = "À quelle maison appartient cette piscine ?";
    document.getElementById("detail").textContent = `piscine ${ITEM.id_piscine}`;
    liste.style.display = "block"; liste.innerHTML = "";
    ITEM.adresses.forEach((a, k) => {
      const row = document.createElement("div");
      row.className = "row" + (MON_DERNIER === a.id_ban ? " choisie" : "");
      row.innerHTML = `<span class="num">${k+1}</span><span>${a.texte || a.id_ban} <span style="color:var(--mut)">· ${a.dist_m} m</span></span>`;
      row.onclick = () => repondre(a.id_ban);
      liste.appendChild(row);
    });
    boutons.innerHTML =
      `<button class="keycap aucune" onclick="repondre('aucune')"><span class="k">A</span>Aucune de ces adresses</button>
       <button class="keycap unsure" onclick="repondre('indecis')"><span class="k">S</span>Impossible à dire</button>`;
    document.getElementById("nav-aide").style.display = "";
    document.getElementById("nav-aide").innerHTML =
      `rangée des chiffres <kbd>&</kbd><kbd>é</kbd><kbd>"</kbd>… = maison 1,2,3 · <kbd>A</kbd> aucune ·
       <kbd>S</kbd> impossible · <kbd>←</kbd>/<kbd>→</kbd> ou <kbd>E</kbd> naviguer · <kbd>ESPACE</kbd> passer`;
  }
  document.getElementById("badge-deja").style.display = MON_DERNIER ? "inline" : "none";
  // en bout d'historique (item neuf) : précharger le prochain pendant la réflexion
  if (idx[cle()] === H().length - 1) precharger();
}

function svgAdresse(it){
  const P = 700;
  let s = `<svg width="${P}" height="${P}" viewBox="0 0 ${P} ${P}" style="width:min(74vh,92vw);height:auto">`;
  s += `<image x="0" y="0" width="${P}" height="${P}" href="${it.img}"/>`;
  for (const pc of it.parcelles) for (const ring of pc.rings){
    const d = "M" + ring.map(p=>p.join(",")).join(" L") + " Z";
    s += pc.propre
      ? `<path d="${d}" fill="none" stroke="#00e5ff" stroke-width="2.5" opacity="0.9"/>`
      : `<path d="${d}" fill="none" stroke="#ffeb3b" stroke-width="1" opacity="0.5"/>`;
  }
  for (const ring of it.piscine){
    const d = "M" + ring.map(p=>p.join(",")).join(" L") + " Z";
    s += `<path d="${d}" fill="rgba(255,45,85,0.15)" stroke="#ff2d55" stroke-width="2.5"/>`;
  }
  it.adresses.forEach((a, k) => {
    s += `<g class="pin" data-k="${k}" style="cursor:pointer">`+
         `<circle cx="${a.x}" cy="${a.y}" r="12" fill="#1565c0" stroke="#000" stroke-width="1.5"/>`+
         `<text x="${a.x}" y="${a.y}" fill="#fff" font-size="13" font-weight="bold" text-anchor="middle" dominant-baseline="central" pointer-events="none">${k+1}</text></g>`;
  });
  return s + "</svg>";
}

async function repondre(rep){
  if (!TRIEUR){ document.getElementById("modal-trieur").style.display="flex"; return; }
  if (!ITEM) return;
  const id = MODE === "existence" ? ITEM.id : ITEM.id_piscine;
  const correction = MON_DERNIER !== null;
  const r = await (await fetch("/api/reponse", {method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({produit: PRODUIT, mode: MODE, id_item: id, reponse: rep,
                          trieur: TRIEUR, remplacer: correction})})).json();
  H()[idx[cle()]].rep = rep;
  dernierVoteT = Date.now();
  const cadre = document.getElementById("cadre");
  cadre.className = "flash-" + (["oui","non","incertain","indecis","aucune"].includes(rep) ? rep : "adresse");
  if (!correction){
    serie++;
    const s = document.getElementById("serie");
    s.textContent = serie; s.classList.remove("pulse"); void s.offsetWidth; s.classList.add("pulse");
  }
  toast((correction ? "corrigé" : "+1") + ` · ${r.n_votes} vote(s)` +
        (r.majorite ? ` · majorité « ${r.majorite} » (${Math.round(r.accord*100)}%)` : " · égalité, une passe de plus tranchera"));
  if (r.checkpoint){
    // Pause forcée : 3 s toutes les 100 réponses, pendant que le serveur dumpe
    // le consensus sur disque. Les yeux aussi ont un localStorage.
    const p = document.getElementById("pause");
    document.getElementById("pause-n").textContent = r.total + " votes";
    document.getElementById("pause-stats").textContent =
      `série ${serie} · ${document.getElementById("rythme").textContent} · session ${document.getElementById("chrono").textContent}`;
    p.style.display = "flex";
    let cpt = 3;
    document.getElementById("pause-cpt").textContent = cpt;
    const h = setInterval(() => {
      cpt--;
      document.getElementById("pause-cpt").textContent = cpt;
      if (cpt <= 0){ clearInterval(h); p.style.display = "none"; suivant(); }
    }, 1000);
    return;
  }
  // avance IMMÉDIATE : le flash et le toast vivent leur vie pendant que
  // l'item suivant (préchargé) s'affiche — aucun timer, les navigateurs
  // les étranglent dès que l'onglet perd le focus.
  suivant();
}

let modeSignal = false;
function armerSignal(){
  if (MODE !== "existence") return;
  modeSignal = !modeSignal;
  document.getElementById("cadre").style.cursor = modeSignal ? "crosshair" : "";
  toast(modeSignal ? "clique sur la piscine que tu vois (F pour annuler)" : "signalement annulé");
}
async function clicImage(ev){
  if (!modeSignal || MODE !== "existence" || !ITEM) return;
  const img = ev.currentTarget;
  const rect = img.getBoundingClientRect();
  const fx = (ev.clientX - rect.left) / rect.width;
  const fy = (ev.clientY - rect.top) / rect.height;
  const r = await (await fetch("/api/signalement", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({produit: PRODUIT, id_item: ITEM.id, fx, fy, trieur: TRIEUR})})).json();
  modeSignal = false;
  document.getElementById("cadre").style.cursor = "";
  if (r.ok){
    const m = document.createElement("div");
    m.style.cssText = `position:absolute;left:${fx*100}%;top:${fy*100}%;width:14px;height:14px;
      margin:-7px;border:3px solid var(--acc);border-radius:50%;pointer-events:none`;
    document.getElementById("cadre").appendChild(m);
    toast("piscine signalée · recoupée plus tard avec le cadastre");
  }
}
function toast(txt){
  const t = document.getElementById("toast");
  t.textContent = txt; t.classList.add("on");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("on"), 1700);
}

function dessinerHisto(){
  const conteneur = document.getElementById("histo");
  conteneur.innerHTML = "";
  const h = H();
  h.slice(-60).forEach((e, kRel) => {
    const k = h.length - Math.min(60, h.length) + kRel;
    const d = document.createElement("div");
    let cls = "pas";
    if (e.rep) cls += " " + (["oui","non","incertain","indecis","aucune"].includes(e.rep) ? e.rep : "adresse");
    if (k === idx[cle()]) cls += " courant";
    d.className = cls;
    d.title = e.id + (e.rep ? " · " + e.rep : " · sans réponse");
    d.onclick = () => { idx[cle()] = k; charger(h[k].id); };
    conteneur.appendChild(d);
  });
  conteneur.scrollLeft = conteneur.scrollWidth;
}

const AZERTY = {"&":0, "é":1, '"':2, "'":3, "(":4, "-":5, "è":6, "_":7, "ç":8};
// Mapping main gauche défini par JB (2026-07-16) : Q=oui, D=non, A=arrière,
// E=avant, S=je ne peux pas dire (vote), ESPACE=passer sans voter, F=signaler.
// O/N restent en alias. Au niveau adresse, A garde son sens « aucune » : la
// navigation y passe par les flèches (et E pour avancer).
document.addEventListener("keydown", e => {
  if (document.getElementById("modal-trieur").style.display === "flex") return;
  if (document.getElementById("pause").style.display === "flex") return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const k = e.key.toLowerCase();
  if (k === "arrowleft") return precedent();
  if (k === "arrowright" || k === "e") return suivant();
  if (k === " "){ e.preventDefault(); return suivant(); }
  if (MODE === "existence"){
    if (k === "q" || k === "o") repondre("oui");
    else if (k === "d" || k === "n") repondre("non");
    else if (k === "s" || k === "u") repondre("incertain");
    else if (k === "a") precedent();
    else if (k === "f") armerSignal();
  } else {
    if (e.key in AZERTY && ITEM && ITEM.adresses[AZERTY[e.key]]) repondre(ITEM.adresses[AZERTY[e.key]].id_ban);
    else if (/^[1-9]$/.test(k) && ITEM && ITEM.adresses[+k-1]) repondre(ITEM.adresses[+k-1].id_ban);
    else if (k === "a") repondre("aucune");
    else if (k === "s" || k === "u") repondre("indecis");
  }
});
function changerProduit(p){
  PRODUIT = p;
  document.querySelectorAll("#produits-sel .niveau").forEach(b =>
    b.classList.toggle("actif", b.dataset.p === p));
  const aAdresse = PRODUITS[p].adresse;
  document.getElementById("ong-adresse").style.display = aAdresse ? "" : "none";
  if (!aAdresse && MODE === "adresse") MODE = "existence";
  changerMode(MODE);
}
(async () => {
  const liste = await (await fetch("/api/produits")).json();
  const sel = document.getElementById("produits-sel");
  liste.forEach(p => {
    PRODUITS[p.nom] = p;
    const b = document.createElement("button");
    b.className = "niveau"; b.dataset.p = p.nom;
    b.textContent = p.nom.charAt(0).toUpperCase() + p.nom.slice(1);
    b.onclick = () => changerProduit(p.nom);
    sel.appendChild(b);
  });
  changerProduit(liste[0].nom);
})();
</script></body></html>
"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8199)
    p.add_argument("--candidats",
                   help="parquet des candidats (défaut : Bouchemaine 49035)")
    p.add_argument("--ortho-dir",
                   help="dalles RVB pour le niveau adresse (défaut : 49035)")
    args = p.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    repo = Path(__file__).resolve().parents[2]
    interim = Path(cfg["paths"]["interim"])
    ortho = Path(args.ortho_dir) if args.ortho_dir else \
        repo / "data" / "raw" / "bdortho" / "49035" / "rvb"

    votes = Votes(interim.parent / "atelier" / "atelier.sqlite")
    if votes.vide():
        amorcer_depuis_acquis(votes, repo)

    res = Ressources(cfg, ortho if ortho.exists() else None)
    produits = {}
    for nom, pcfg in PRODUITS.items():
        if not (interim / pcfg["candidats"]).exists():
            log.warning("[%s] candidats absents (%s) — produit non chargé.",
                        nom, pcfg["candidats"])
            continue
        if not (interim / pcfg["vignettes"]).exists():
            log.warning("[%s] vignettes absentes (%s) — produit non chargé "
                        "(générer via 16_tri_visuel --out-dir).", nom, pcfg["vignettes"])
            continue
        produits[nom] = Donnees(cfg, nom, pcfg, res)
    if not produits:
        raise SystemExit("Aucun produit chargeable.")
    Handler.produits = produits
    Handler.votes = votes

    # Chauffe du cache ortho (niveau adresse) : le décodage JPEG2000 à la volée
    # coûte 1-3 s par piscine — inacceptable en farm. On pré-rend tout en fond.
    def chauffer():
        for d in produits.values():
            if d.adressees is None or d.index_dalles is None:
                continue
            n = 0
            import time
            for pid in d.adressees["id_piscine"]:
                try:
                    if d.ortho_jpeg(pid) is not None:
                        n += 1
                except Exception:                      # dalle manquante : tant pis
                    log.debug("chauffe ortho : échec %s", pid)
                time.sleep(0.02)   # laisse toujours la main aux requêtes du farm
            log.info("[%s] cache ortho chaud (%d fonds).", d.nom, n)
    threading.Thread(target=chauffer, daemon=True).start()

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    log.info("Atelier prêt : http://localhost:%d (Ctrl-C pour arrêter).", args.port)
    srv.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
