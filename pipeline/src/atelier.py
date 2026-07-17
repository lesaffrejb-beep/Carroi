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

# Mode FAST : UNE question pour tous les thèmes — « que voyez-vous dans la zone
# rouge ? » — binds façon barre d'action de jeu (main gauche, sans Shift).
# Chaque code compte pour TOUS les produits : « terrasse » sur un candidat
# piscine = négatif piscines ET exemple d'entraînement multi-classes (docs/18).
VOCAB_FAST = [
    ("piscine",  "q", "Piscine",                    "oui"),
    ("terrasse", "w", "Terrasse / dallage",         "oui"),
    ("jardin",   "x", "Jardin / pelouse dégagée",   "oui"),
    ("non",      "d", "Rien de tout ça",            "non"),
    ("incertain","s", "Impossible à dire",          "unsure"),
]

# Registre des produits farmables. En ajouter un = une entrée ici + un parquet de
# candidats + des vignettes (16_tri_visuel --out-dir dédié). Le niveau adresse
# n'existe que si le produit a une base adressée (20_join).
PRODUITS = {
    "piscines": {
        "question": "Y a-t-il une piscine dans le contour rouge ?",
        # (code, touche, libellé, style) — le code part dans les exports ;
        # "positif" débloque le niveau adresse.
        "reponses": [
            ("oui", "q", "Piscine", "oui"),
            ("non", "d", "Pas une piscine", "non"),
            ("incertain", "s", "Impossible à dire", "unsure"),
        ],
        "positifs": ["oui"],
        # Le vocabulaire FAST dit « piscine » là où le produit dit « oui » :
        # on canonise À L'ÉCRITURE, sinon le consensus se scinde en deux
        # classes positives et les items-or (semés en « oui ») ne matchent plus.
        "canonique": {"piscine": "oui"},
        "candidats": "piscines_candidates_49_49035.parquet",
        "vignettes": "tri/vignettes",
        "vignette_m": 60,
        "adressees": "piscines_adressees_49.parquet",
    },
    "terrasses": {
        # Un vote RICHE au lieu d'un oui/non : terrasse minérale et pelouse ne
        # se vendent pas au même client (pergoliste vs paysagiste/pisciniste).
        # Un seul passage humain, la base se découpe par acheteur en aval.
        "question": "Qu'y a-t-il dans la zone rouge ?",
        "reponses": [
            ("terrasse", "q", "Terrasse / dallage minéral", "oui"),
            ("jardin", "w", "Jardin / pelouse dégagée", "oui"),
            ("non", "d", "Ni l'un ni l'autre (toit, route, artefact…)", "non"),
            ("incertain", "s", "Impossible à dire", "unsure"),
        ],
        "positifs": ["terrasse", "jardin"],
        "candidats": "terrasses_a_farmer_49_49035.parquet",
        "vignettes": "tri_terrasses/vignettes",
        "vignette_m": 100,
        "adressees": "terrasses_adressees_49.parquet",   # 26_terrasses_adresses
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
        self.conn.execute("PRAGMA journal_mode=WAL")   # multi-user : lecteurs jamais bloqués
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
        # Trieurs invités (mode en ligne) : un lien-token = une personne, révocable.
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS trieurs ("
            " token TEXT PRIMARY KEY, nom TEXT, taux_ct REAL,"
            " gele INTEGER DEFAULT 0, cree_ts TEXT)")
        self.conn.commit()

    # ------------------------------------------------------- trieurs invités
    def inviter(self, nom: str, taux_ct: float) -> str:
        import secrets
        token = secrets.token_urlsafe(9)
        with self.lock:
            self.conn.execute("INSERT INTO trieurs VALUES (?,?,?,0,?)",
                              (token, nom, taux_ct,
                               datetime.now(timezone.utc).isoformat()))
            self.conn.commit()
        return token

    def trieur_par_token(self, token: str) -> dict | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT token, nom, taux_ct, gele FROM trieurs WHERE token=?",
                (token,)).fetchone()
        return None if row is None else dict(zip(("token", "nom", "taux_ct", "gele"), row))

    def geler(self, token: str, gele: bool = True):
        with self.lock:
            self.conn.execute("UPDATE trieurs SET gele=? WHERE token=?",
                              (int(gele), token))
            self.conn.commit()

    def lister_trieurs(self) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT token, nom, taux_ct, gele FROM trieurs").fetchall()
        return [dict(zip(("token", "nom", "taux_ct", "gele"), r)) for r in rows]

    def cadence_suspecte(self, trieur: str, n: int = 20, seuil_s: float = 0.8) -> bool:
        """Médiane des 20 derniers écarts < 0,8 s = plus vite qu'un humain qui
        REGARDE l'image : robot ou spam. Pure vis-à-vis du reste."""
        with self.lock:
            rows = self.conn.execute(
                "SELECT ts FROM votes WHERE trieur=? ORDER BY rowid DESC LIMIT ?",
                (trieur, n + 1)).fetchall()
        if len(rows) < n + 1:
            return False
        ts = [datetime.fromisoformat(r[0]) for r in rows]
        ecarts = sorted((a - b).total_seconds() for a, b in zip(ts, ts[1:]))
        return ecarts[len(ecarts) // 2] < seuil_s

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

    def lignes(self) -> list[tuple]:
        """Tous les votes (produit, mode, id_item, reponse, trieur) — classement."""
        with self.lock:
            return self.conn.execute(
                "SELECT produit, mode, id_item, reponse, trieur FROM votes").fetchall()

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


def existence_acquise(votes: list[str], positifs: tuple = ("oui",)) -> bool:
    """Le niveau adresse se débloque quand la majorité des votes est une classe
    POSITIVE du produit (piscines : oui ; terrasses : terrasse OU jardin). Pure."""
    maj, _ = consensus(votes)
    return maj in positifs


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
    positifs = tuple(donnees.meta.get("positifs", ["oui"]))
    for _, r in donnees.adressees.iterrows():
        if existence_acquise(votes_existence.get(r["id_detection"], []), positifs):
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

    def _invite(self, jeton: str | None) -> dict | None:
        """Résout un token d'invitation. None = mode local (JB sur sa machine),
        dict = invité (le nom vient du serveur, jamais du client)."""
        return self.votes.trieur_par_token(jeton) if jeton else None

    def _ors(self, produit: str, mode: str) -> dict[str, str]:
        """Questions d'or : items à >= 3 votes, 100 % d'accord. Recalcul <= 1/min."""
        import time
        cache = getattr(Handler, "_cache_ors", {})
        cle_c = (produit, mode)
        ts, val = cache.get(cle_c, (0.0, {}))
        if time.monotonic() - ts > 60:
            val = {}
            for i, vs in self.votes.tout(produit, mode).items():
                maj, acc = consensus(vs)
                if maj and acc == 1.0 and len(vs) >= 3:
                    val[i] = maj
            cache[cle_c] = (time.monotonic(), val)
            Handler._cache_ors = cache
        return val

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
        if u.path == "/api/etat" and q.get("produit", [""])[0] == "tous":
            # État agrégé sur TOUS les produits (HUD des modes fast/slow, qui
            # servent l'union des files) : sommes, passe = min, accord pondéré.
            etats = [etat_global(p, v) for p in self.produits.values()]
            out = {}
            for mode in MODES:
                accs = [(e[mode]["accord_moyen"], e[mode]["votes"])
                        for e in etats if e[mode]["accord_moyen"] is not None]
                poids = sum(w for _, w in accs)
                passes = [e[mode]["passe_courante"] for e in etats if e[mode]["items"]]
                out[mode] = {
                    "items": sum(e[mode]["items"] for e in etats),
                    "passe_courante": min(passes) if passes else 0,
                    "restants_cette_passe": sum(e[mode]["restants_cette_passe"]
                                                for e in etats),
                    "votes": sum(e[mode]["votes"] for e in etats),
                    "accord_moyen": round(sum(a * w for a, w in accs) / poids, 3)
                                    if poids else None,
                }
            out["xp"] = v.total()
            trieur = q.get("trieur", [""])[0]
            if trieur:
                out["rythme"] = v.stats_trieur(trieur)
            self._json(out)
            return
        if d is None:
            self.send_error(404, "produit inconnu")
            return
        produit = d.nom

        if u.path == "/":
            data = PAGE_HTML.encode()
            self._binaire(data, "text/html; charset=utf-8")
        elif u.path == "/api/produits":
            self._json([{"nom": n, "question": p.meta["question"],
                         "reponses": [{"code": c, "touche": k, "libelle": l,
                                       "style": s} for c, k, l, s in p.meta["reponses"]],
                         "adresse": p.adressees is not None}
                        for n, p in self.produits.items()])
        elif u.path == "/api/etat":
            e = etat_global(d, v)
            trieur = q.get("trieur", [""])[0]
            if trieur:
                e["rythme"] = v.stats_trieur(trieur)
            self._json(e)
        elif u.path == "/api/gains":
            invite = self._invite(q.get("jeton", [None])[0])
            if invite is None:
                self._json({"erreur": "jeton requis"}, 403)
                return
            nom = invite["nom"]
            # Validité = conformité au consensus Dawid-Skene sur les items
            # multi-trieurs + taux d'or (items certains réinjectés).
            valides = total_v = ors_ok = ors_tot = 0
            for prod in self.produits:
                for mode in MODES:
                    tout = self.votes.tout(prod, mode)
                    ors = self._ors(prod, mode)
                    # conformité par item : dernier vote du trieur vs majorité
                    # (les exports consensus, eux, passent par Dawid-Skene)
                    for i, vs in tout.items():
                        dern = self.votes.dernier_de(prod, mode, i, nom)
                        if dern is None:
                            continue
                        total_v += 1
                        maj, acc = consensus(vs)
                        conforme = (maj is None) or (dern == maj)
                        if i in ors:
                            ors_tot += 1
                            ors_ok += int(dern == ors[i])
                        if conforme:
                            valides += 1
            taux_or = (ors_ok / ors_tot) if ors_tot else None
            gains = valides * invite["taux_ct"] / 100.0
            if taux_or is not None and taux_or >= 0.98:
                gains *= 1.5                       # bonus qualité (docs/19)
            self._json({"nom": nom, "votes": total_v, "valides": valides,
                        "taux_or": taux_or, "ors_vus": ors_tot,
                        "taux_ct": invite["taux_ct"],
                        "gains_eur": round(gains, 2), "gele": bool(invite["gele"])})
        elif u.path == "/api/impact":
            # La preuve que chaque vote « rapporte » : compteurs RÉELS du
            # pipeline (consensus tranchés, base vendable), jamais inventés.
            out = {"produits": {}}
            for nom, dp in self.produits.items():
                positifs = dp.meta.get("positifs", ["oui"])
                classes = {c: 0 for c in positifs}
                tranches = 0
                for vs in self.votes.tout(nom, "existence").values():
                    maj, _ = consensus(vs)
                    if maj is not None:
                        tranches += 1
                        if maj in classes:
                            classes[maj] += 1
                adresses = sum(1 for vs in self.votes.tout(nom, "adresse").values()
                               if consensus(vs)[0] not in (None, "aucune", "indecis"))
                out["produits"][nom] = {"classes": classes, "tranches": tranches,
                                        "total": len(dp.candidats),
                                        "adresses_vendables": adresses}
            self._json(out)
        elif u.path == "/api/classement":
            # Volume + accord au consensus par trieur : la qualité s'auto-régule
            # quand elle est affichée (et rend le multi-trieurs payé motivant).
            cons = {}
            for nom in self.produits:
                for mode in MODES:
                    for i, vs in self.votes.tout(nom, mode).items():
                        maj, _ = consensus(vs)
                        if maj is not None:
                            cons[(nom, mode, i)] = maj
            stats: dict[str, dict] = {}
            for prod, mode, i, rep, trieur in self.votes.lignes():
                s = stats.setdefault(trieur, {"votes": 0, "vus": 0, "ok": 0})
                s["votes"] += 1
                maj = cons.get((prod, mode, i))
                if maj is not None:
                    s["vus"] += 1
                    s["ok"] += int(rep == maj)
            tableau = [{"trieur": t, "votes": s["votes"],
                        "accord": round(s["ok"] / s["vus"], 3) if s["vus"] else None}
                       for t, s in stats.items()]
            tableau.sort(key=lambda x: -x["votes"])
            self._json(tableau[:10])
        elif u.path == "/api/export/signalements.csv":
            self._csv(v.signalements_csv(), "signalements.csv")
        elif u.path == "/api/tache":
            mode = q.get("mode", ["existence"])[0]
            if mode in ("fast", "slow"):
                # Union des files de tous les produits : on sert le produit qui a
                # le plus de restants dans la passe courante (couverture équilibrée).
                reel = "existence" if mode == "fast" else "adresse"
                sauf = q.get("sauf", [None])[0]
                invite = self._invite(q.get("jeton", [None])[0])
                if invite and invite["gele"]:
                    self._json({"gele": True}, 403)
                    return
                if reel == "existence" and invite and self.rng.random() < 0.10:
                    for nom_or in self.rng.sample(list(self.produits), len(self.produits)):
                        ors = self._ors(nom_or, "existence")
                        if ors:
                            item = self.produits[nom_or].item_existence(
                                self.rng.choice(list(ors)))
                            if item:
                                item["produit"] = nom_or
                                self._json({"item": item, "deja_vu": 0,
                                            "mon_dernier": None})
                                return
                meilleurs = []
                for nom, dp in self.produits.items():
                    if reel == "existence":
                        dispo = dp.ids_disponibles()
                        ids = [i for i in dp.candidats["id_detection"]
                               if i in dispo and i != sauf]
                    else:
                        ids = [i for i in ids_adresse_debloques(
                                   dp, v.tout(nom, "existence"))
                               if i != sauf and dp.item_adresse(i)]
                    if not ids:
                        continue
                    compte = v.compte_par_item(nom, reel)
                    mini = min(compte.get(i, 0) for i in ids)
                    restants = sum(1 for i in ids if compte.get(i, 0) == mini)
                    meilleurs.append((mini, -restants, nom, ids, compte))
                if not meilleurs:
                    self._json({"vide": True})
                    return
                meilleurs.sort()
                _, _, nom, ids, compte = meilleurs[0]
                dp = self.produits[nom]
                tout = v.tout(nom, reel)
                contestes = {i for i, vs in tout.items()
                             if consensus(vs)[0] is None and vs}
                id_item = choisir_moins_vu(ids, compte, self.rng,
                                           prioritaires=contestes)
                item = (dp.item_existence(id_item) if reel == "existence"
                        else dp.item_adresse(id_item))
                if item is None:
                    self._json({"vide": True})
                    return
                item["produit"] = nom
                trieur = q.get("trieur", [""])[0]
                self._json({"item": item,
                            "deja_vu": len(v.votes_item(nom, reel, id_item)),
                            "mon_dernier": v.dernier_de(nom, reel, id_item, trieur)
                                           if trieur else None})
                return
            sauf = q.get("sauf", [None])[0]
            invite = self._invite(q.get("jeton", [None])[0])
            if invite and invite["gele"]:
                self._json({"gele": True}, 403)
                return
            if mode == "existence":
                # Question d'or ~1/10 pour les invités : un item dont la vérité
                # est déjà certaine, indiscernable d'une tâche normale.
                ors = self._ors(produit, mode) if invite else {}
                if ors and self.rng.random() < 0.10:
                    id_or = self.rng.choice(list(ors))
                    item = d.item_existence(id_or)
                    if item:
                        self._json({"item": item, "deja_vu": 0, "mon_dernier": None})
                        return
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
            mode = {"fast": "existence", "slow": "adresse"}.get(mode, mode)
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
            # Dawid-Skene pondère chaque trieur par sa matrice de confusion
            # apprise — il faut les IDENTITÉS, pas juste les réponses.
            import importlib as _il
            ag = _il.import_module("agregation")
            with v.lock:
                rows = v.conn.execute(
                    "SELECT id_item, trieur, reponse FROM votes WHERE produit=? "
                    "AND mode='existence'", (produit,)).fetchall()
            par_item: dict[str, list[tuple[str, str]]] = {}
            for i, tr, r in rows:
                par_item.setdefault(i, []).append((tr, r))
            multi = len({tr for vs in par_item.values() for tr, _ in vs}) >= 3
            ds = ag.consensus_dawid_skene(par_item) if multi else {}
            lignes = ["id_detection,decision,n_votes,accord,methode"]
            for i, vs in sorted(par_item.items()):
                if multi:
                    dec, confiance = ds[i]
                    lignes.append(f"{i},{dec},{len(vs)},{confiance:.2f},dawid-skene")
                else:
                    maj, acc = consensus([r for _, r in vs])
                    lignes.append(f"{i},{maj or 'incertain'},{len(vs)},{acc:.2f},majorite")
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
        mode = {"fast": "existence", "slow": "adresse"}.get(mode, mode)
        reponse, trieur = str(corps["reponse"]), str(corps.get("trieur") or "anonyme")
        invite = self._invite(corps.get("jeton"))
        if invite:
            if invite["gele"]:
                self._json({"gele": True}, 403)
                return
            trieur = invite["nom"]          # l'identité vient du serveur
        # 'indecis' = « je ne peux pas répondre » : un vrai vote (l'item ne
        # reviendra pas cette passe), jamais vendu, exclu du consensus utile.
        valides = {"existence": {r[0] for r in PRODUITS[produit]["reponses"]}
                   | {v[0] for v in VOCAB_FAST}}
        if mode not in MODES or (mode in valides and reponse not in valides[mode]):
            self._json({"erreur": "mode ou réponse invalide"}, 400)
            return
        # Canonise le vocabulaire FAST vers celui du produit (« piscine » → « oui »)
        # AVANT écriture : une seule classe positive en base, or et consensus intacts.
        reponse = PRODUITS[produit].get("canonique", {}).get(reponse, reponse)
        remplace = bool(corps.get("remplacer"))
        if remplace:
            self.votes.remplacer_dernier(produit, mode, id_item, reponse, trieur)
        else:
            self.votes.ajouter(produit, mode, id_item, reponse, trieur)
        if invite and self.votes.cadence_suspecte(trieur):
            self.votes.geler(invite["token"])
            log.warning("Trieur %s GELÉ : cadence de robot.", trieur)
            self._json({"gele": True}, 403)
            return
        vs = self.votes.votes_item(produit, mode, id_item)
        maj, acc = consensus(vs)
        total = self.votes.total()
        # Un REMPLACEMENT ne change pas le total : sans ce garde, un compteur
        # posé pile sur un multiple de 100 redéclenchait la pause à CHAQUE
        # correction (bug signalé par JB le 2026-07-17).
        if not remplace and total % 100 == 0:
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
                    "total": total,
                    "checkpoint": (not remplace) and total % 100 == 0})


# ------------------------------------------------------------------ page HTML

PAGE_HTML = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>L'Atelier — farm d'annotation</title>
<style>
/* COCKPIT DE FARM — design issu d'un panel simulé de 10 farmers gamers
   (2026-07-17) : vitesse VISIBLE (votes/min live + record perso), progression
   segmentée en %, rentabilité PROUVÉE (chaîne pipeline avec compteurs réels),
   hotbar clavier façon barre d'action, recap end-of-match au checkpoint.
   Palette : sombre chaud, encre ivoire, UN accent bleu d'eau, sémantique
   feutrée. Bannis : lime acide, violets fluo, dégradés décoratifs. */
:root{
  --bg:#131417; --panel:#1a1b1f; --raise:#232529; --line:#2e3037; --line2:#3d404a;
  --ink:#ebe8e0; --mut:#8f8b81; --acc:#56b6d4; --acc-ink:#06242e; --acc-dim:#23434f;
  --oui:#55a87c; --non:#c96a5c; --unsure:#d2a04a; --aucune:#9a8cc0;
  --r:10px; --mono:ui-monospace,'SF Mono',Menlo,monospace;
}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;margin:0;background:var(--bg);
     color:var(--ink);padding-bottom:52px}
kbd{font-family:var(--mono);font-size:.82em;background:#0a0b0e;border:1px solid var(--line);
    border-bottom-width:2px;border-radius:5px;padding:1px 7px;color:var(--mut)}
button{font:inherit;cursor:pointer;color:inherit}
h3{margin:0 0 10px;font-size:.64rem;letter-spacing:.16em;color:var(--mut);
   font-family:var(--mono);font-weight:600}

/* ---------- HUD : une rangée d'instruments ---------- */
header{position:sticky;top:0;z-index:10;background:var(--panel);border-bottom:1px solid var(--line)}
#hud{display:flex;align-items:center;gap:16px;padding:8px 16px;flex-wrap:wrap}
#marque{font-family:var(--mono);font-weight:bold;letter-spacing:.14em;font-size:.8rem;color:var(--acc)}
#marque small{display:block;letter-spacing:.02em;color:var(--mut);font-weight:normal}
#niveaux{display:flex;gap:2px;background:var(--bg);border:1px solid var(--line);
         border-radius:9px;padding:3px}
.niveau{padding:6px 14px;border:none;border-radius:6px;background:none;
        color:var(--mut);font-weight:650;font-size:.86rem}
.niveau.actif{background:var(--acc);color:var(--acc-ink)}
.niveau .sous{font-weight:normal;font-size:.76rem;opacity:.85}
#chips{display:flex;margin-left:auto;align-items:stretch}
.chip{padding:1px 13px;border-left:1px solid var(--line);text-align:right;
      font-size:.6rem;letter-spacing:.1em;color:var(--mut);font-family:var(--mono);
      text-transform:uppercase;line-height:1.5}
.chip b{display:block;font-size:1.3rem;line-height:1.15;color:var(--ink);font-weight:600}
.chip.acc b{color:var(--acc)}
.chip.grand b{font-size:1.65rem}
#save{font-size:.68rem;color:var(--mut);font-family:var(--mono);text-align:right;line-height:1.6}
#save a{color:var(--acc)}

/* rail de progression segmenté (passe courante, tous produits) */
#rail{position:relative;height:24px;background:#0e0f12;border-top:1px solid var(--line)}
#jauge{position:absolute;top:0;bottom:0;left:0;width:0;background:var(--acc-dim);
       border-right:2px solid var(--acc);transition:width .3s}
#rail-ticks{position:absolute;inset:0;background:repeating-linear-gradient(90deg,
            transparent 0 calc(5% - 1px),#2e303766 calc(5% - 1px) 5%)}
#rail-info{position:absolute;inset:0;display:flex;justify-content:space-between;
           align-items:center;padding:0 16px;font-family:var(--mono);font-size:.7rem;
           color:var(--mut);pointer-events:none}
#rail-info b{color:var(--ink)}
#obj{color:var(--acc)}

/* ---------- plateau : stats | scène | adresses ---------- */
#zone{display:grid;grid-template-columns:288px minmax(0,1fr) auto;gap:18px;
      padding:16px;align-items:start;max-width:1560px;margin:0 auto}
@media (max-width:1080px){#zone{grid-template-columns:1fr}#gauche{order:2}}
#gauche{display:flex;flex-direction:column;gap:14px;position:sticky;top:88px}
.carte{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);
       padding:12px 14px}
.etape{display:flex;align-items:baseline;gap:8px;padding:6px 0}
.etape+.etape{border-top:1px dashed #2e303788}
.etape .lbl{font-size:.8rem;color:var(--mut);flex:1;min-width:0}
.etape b{font-family:var(--mono);font-size:1.02rem;font-weight:600}
.etape .delta{font-family:var(--mono);font-size:.74rem;color:var(--oui);min-width:3em;text-align:right}
.maillon{text-align:center;color:var(--line2);font-size:.68rem;font-family:var(--mono);
         letter-spacing:.1em;padding:2px 0}
.rang{display:flex;gap:8px;align-items:baseline;padding:5px 0;font-size:.84rem}
.rang+.rang{border-top:1px dashed #2e303788}
.rang .pos{font-family:var(--mono);color:var(--mut);min-width:1.3em}
.rang .nom{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rang .acc2{font-family:var(--mono);font-size:.76rem;color:var(--mut)}
.rang b{font-family:var(--mono)}
.rang.moi{color:var(--acc)}
.rang.moi .nom::after{content:" ← toi";font-size:.7rem}

/* ---------- scène : question, image, hotbar ---------- */
#scene{display:flex;flex-direction:column;align-items:center;gap:10px;min-width:0}
#question{font-size:1.24rem;font-weight:750;line-height:1.3;text-wrap:balance;text-align:center}
#detail{color:var(--mut);font-size:.76rem;font-family:var(--mono);text-align:center}
#cadre{position:relative;background:#000;border:1px solid var(--line);border-radius:var(--r);
       overflow:hidden;box-shadow:0 14px 44px #0009;max-width:100%}
/* l'image ne doit JAMAIS pousser la hotbar sous le pli : hauteur bornée par
   la place restante (header 118 + question 66 + hotbar 96 + aide 40 + marges) */
#cadre img,#cadre svg{display:block;max-width:100%;width:auto;height:auto;
       max-height:calc(100vh - 330px);min-height:300px;transition:transform .12s ease-out}
#cadre.zoom img,#cadre.zoom svg{transform:scale(2.2);transform-origin:var(--ox,50%) var(--oy,50%)}
#cadre.flash-oui{outline:3px solid var(--oui)}
#cadre.flash-non{outline:3px solid var(--non)}
#cadre.flash-unsure,#cadre.flash-incertain,#cadre.flash-indecis{outline:3px solid var(--unsure)}
#cadre.flash-aucune,#cadre.flash-adresse{outline:3px solid var(--aucune)}
#badge-vu{position:absolute;top:10px;right:10px;background:#0a0b0ecc;border:1px solid var(--line);
          border-radius:999px;padding:3px 10px;font-size:.75rem;color:var(--mut);font-family:var(--mono)}
#badge-deja{position:absolute;top:10px;left:10px;background:#0a0b0ecc;border:1px solid var(--unsure);
            border-radius:999px;padding:3px 10px;font-size:.75rem;color:var(--unsure);display:none}

/* hotbar : la barre d'action, sous l'image, une touche = un geste */
#boutons{display:flex;gap:10px;flex-wrap:wrap;justify-content:center}
.keycap{display:flex;flex-direction:column;align-items:center;gap:6px;min-width:106px;max-width:150px;
        background:var(--raise);border:1px solid var(--line);border-bottom-width:3px;
        border-radius:var(--r);padding:10px 10px;color:var(--ink);font-weight:600;
        font-size:.78rem;line-height:1.25;text-align:center;
        transition:transform .05s,border-color .12s}
.keycap:hover{border-color:var(--line2);background:#26282d}
.keycap:active{transform:translateY(2px);border-bottom-width:1px}
.keycap .k{font-family:var(--mono);font-weight:700;font-size:1.05rem;width:2.2em;
           padding:3px 0;border-radius:7px;color:#0b0c10}
.keycap.oui .k{background:var(--oui)}.keycap.non .k{background:var(--non)}
.keycap.unsure .k{background:var(--unsure)}.keycap.aucune .k{background:var(--aucune)}
.keycap.neutre .k{background:var(--mut)}
#nav-aide{color:var(--mut);font-size:.78rem;line-height:2;text-align:center;max-width:60ch}

/* ---------- adresses (mode SITUER) ---------- */
#droite{width:330px;max-width:100%;position:sticky;top:88px}
#liste-adr{max-height:72vh;overflow:auto;border:1px solid var(--line);border-radius:var(--r);
           font-size:.86rem;background:var(--panel)}
#liste-adr .row{padding:7px 10px;cursor:pointer;display:flex;gap:10px;border-bottom:1px solid #2e303788}
#liste-adr .row:last-child{border-bottom:none}
#liste-adr .row:hover{background:var(--raise)}
#liste-adr .row.choisie{background:var(--acc-dim);color:var(--acc)}
.num{font-family:var(--mono);font-weight:bold;min-width:1.6em;color:var(--mut)}

/* ---------- ruban de session ---------- */
#histo-barre{position:fixed;bottom:0;left:0;right:0;background:var(--panel);
             border-top:1px solid var(--line);padding:8px 16px;display:flex;gap:10px;align-items:center}
#histo-titre{font-size:.66rem;letter-spacing:.14em;color:var(--mut);font-family:var(--mono)}
#histo{display:flex;gap:5px;overflow-x:auto;flex:1;padding:2px}
.pas{width:14px;height:14px;border-radius:4px;background:var(--raise);border:1px solid var(--line);
     flex:0 0 auto;cursor:pointer}
.pas.oui{background:var(--oui)}.pas.non{background:var(--non)}
.pas.incertain,.pas.indecis,.pas.unsure{background:var(--unsure)}.pas.aucune{background:var(--aucune)}
.pas.adresse{background:var(--acc)}
.pas.courant{outline:2px solid var(--ink);outline-offset:1px}

/* toast + pulsations */
#toast{position:fixed;bottom:64px;left:50%;transform:translateX(-50%) translateY(6px);
       background:var(--raise);border:1px solid var(--acc);color:var(--ink);
       padding:8px 18px;border-radius:999px;font-weight:600;font-size:.88rem;
       opacity:0;transition:opacity .2s,transform .2s;pointer-events:none;z-index:40}
#toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
@keyframes pulse{50%{transform:scale(1.35)}}
.pulse{display:inline-block;animation:pulse .3s}
@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important}}

/* ---------- checkpoint : écran de fin de manche ---------- */
#pause{display:none;position:fixed;inset:0;z-index:60;background:#000d;
       align-items:center;justify-content:center}
#pause .recap{background:var(--panel);border:1px solid var(--line);border-radius:14px;
              padding:26px 30px;max-width:520px;width:92%;text-align:center}
#pause h2{margin:0;font-family:var(--mono);letter-spacing:.2em;font-size:.8rem;color:var(--mut)}
#pause-n{font-size:2.6rem;font-family:var(--mono);color:var(--acc);font-weight:700;margin:6px 0 2px}
#recap-grille{display:flex;justify-content:center;gap:0;margin:12px 0}
#recap-grille .chip{border-left:1px solid var(--line);text-align:center}
#recap-grille .chip:first-child{border-left:none}
#pause-stats{color:var(--mut);font-size:.86rem}
#recap-impact{margin:12px 0;padding:10px;background:var(--bg);border-radius:8px;
              font-size:.86rem;color:var(--ink);line-height:1.6}
#pause .hint{color:var(--mut);font-size:.8rem;margin-top:10px}

/* modal pseudo */
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
  <div id="marque">L'ATELIER<small>Bouchemaine · 49</small></div>
  <div id="niveaux">
   <button class="niveau actif" id="ong-fast" onclick="changerMode('fast')">⚡ CLASSER <span class="sous">clavier</span></button>
   <button class="niveau" id="ong-slow" onclick="changerMode('slow')">🧭 SITUER <span class="sous" id="verrou-adresse">souris</span></button>
  </div>
  <div id="chips">
   <div class="chip acc grand" title="votes de la dernière minute — ta vitesse instantanée">v/min<b id="vpm">0</b></div>
   <div class="chip" title="ton record de votes sur une minute (toutes sessions)">record<b id="pb">0</b></div>
   <div class="chip acc">série<b id="serie">0</b></div>
   <div class="chip" title="accord moyen entre trieurs sur les items votés">accord<b id="accord">—</b></div>
   <div class="chip acc">xp<b id="xp">—</b></div>
   <div class="chip acc" id="chip-gains" style="display:none">gains<b id="gains">—</b></div>
   <div class="chip">session<b id="chrono">0:00</b></div>
   <div class="chip" style="display:none">rythme<b id="rythme">—</b></div>
  </div>
  <span id="save" title="Chaque réponse est écrite en base à l'instant du clic. Le CSV n'est qu'une copie de consultation.">✓ sauvegarde auto<br>
   <a href="#" onclick="location.href='/api/export/'+REEL()+'.csv?produit='+PRODUIT;return false">télécharger le CSV</a></span>
 </div>
 <div id="rail">
  <div id="jauge"></div><div id="rail-ticks"></div>
  <div id="rail-info"><span>passe <b id="passe">—</b> · reste <b id="restants">—</b></span>
   <span id="rail-pct"></span><span id="obj"></span></div>
 </div>
</header>

<div id="zone">
 <aside id="gauche">
  <section class="carte">
   <h3>LA CHAÎNE — CE QUE TES VOTES FABRIQUENT</h3>
   <div class="etape"><span class="lbl">réponses signées</span><b id="pipe-votes">—</b><span class="delta" id="pipe-votes-d"></span></div>
   <div class="maillon">↓ consensus multi-passes</div>
   <div class="etape"><span class="lbl">zones tranchées</span><b id="pipe-tranches">—</b><span class="delta" id="pipe-tranches-d"></span></div>
   <div class="maillon">↓ la base qui se vend</div>
   <div class="etape"><span class="lbl">🏊 piscines confirmées</span><b id="pipe-oui">—</b><span class="delta" id="pipe-oui-d"></span></div>
   <div class="etape"><span class="lbl">🪨 terrasses</span><b id="pipe-terrasse">—</b><span class="delta" id="pipe-terrasse-d"></span></div>
   <div class="etape"><span class="lbl">🌿 jardins</span><b id="pipe-jardin">—</b><span class="delta" id="pipe-jardin-d"></span></div>
   <div class="etape"><span class="lbl">📍 adresses vendables</span><b id="pipe-adresses">—</b><span class="delta" id="pipe-adresses-d"></span></div>
   <div class="maillon">↓ et l'IA de pré-tri apprend de chaque vote<br>(farm ÷50 sur la prochaine commune)</div>
  </section>
  <section class="carte">
   <h3>FARMERS</h3>
   <div id="classement-corps"><span style="color:var(--mut);font-size:.8rem">—</span></div>
  </section>
 </aside>

 <div id="scene">
  <div id="question">…</div>
  <div id="detail"></div>
  <div id="cadre"><span id="badge-deja">déjà répondu — recliquer corrige</span><span id="badge-vu"></span></div>
  <div id="boutons"></div>
  <div id="nav-aide" style="display:none"></div>
 </div>

 <aside id="droite" style="display:none">
  <div id="liste-adr" style="display:none"></div>
 </aside>
</div>

<div id="histo-barre"><span id="histo-titre">SESSION</span><div id="histo"></div></div>
<div id="toast"></div>
<div id="pause">
 <div class="recap">
  <h2>CHECKPOINT</h2>
  <div id="pause-n"></div>
  <div id="recap-grille">
   <div class="chip">session<b id="recap-session">—</b></div>
   <div class="chip acc">v/min<b id="recap-vpm">—</b></div>
   <div class="chip">record<b id="recap-pb">—</b></div>
  </div>
  <div id="recap-impact"></div>
  <div id="pause-stats"></div>
  <div class="hint">consensus sauvegardé sur disque · <kbd>ESPACE</kbd> reprendre · auto dans <span id="pause-cpt">5</span> s</div>
 </div>
</div>

<script>
const VOCAB = [
  {code:"piscine",  touche:"q", libelle:"Piscine",                  style:"oui"},
  {code:"terrasse", touche:"w", libelle:"Terrasse / dallage",       style:"oui"},
  {code:"jardin",   touche:"x", libelle:"Jardin / pelouse dégagée", style:"oui"},
  {code:"non",      touche:"d", libelle:"Rien de tout ça",          style:"non"},
  {code:"incertain",touche:"s", libelle:"Impossible à dire",        style:"unsure"},
];
let PRODUIT = "piscines", PRODUITS = {}, MODE = "fast", ITEM = null, MON_DERNIER = null, serie = 0;
// fast = existence (clavier), slow = adresse (souris) — le serveur fait la même équivalence
const REEL = () => MODE === "slow" ? "adresse" : "existence";
let actifS = 0, dernierVoteT = null;   // chrono de session (temps ACTIF)
// Vitesse VISIBLE (panel farmers №1) : votes de la dernière minute, en live,
// face au record perso toutes sessions. Le record ne se bat qu'en jouant.
let voteTimes = [], sessionVotes = 0;
let PB = +(localStorage.getItem("atelier_pb") || 0), pbBattu = false;
setInterval(() => {
  if (dernierVoteT && (Date.now() - dernierVoteT) < 60000){
    actifS++;
    const m = Math.floor(actifS / 60), s = actifS % 60;
    document.getElementById("chrono").textContent = m + ":" + String(s).padStart(2, "0");
  }
  voteTimes = voteTimes.filter(t => Date.now() - t < 60000);
  document.getElementById("vpm").textContent = voteTimes.length;
  if (voteTimes.length > PB){
    PB = voteTimes.length;
    localStorage.setItem("atelier_pb", PB);
    const e = document.getElementById("pb");
    e.textContent = PB; e.classList.remove("pulse"); void e.offsetWidth; e.classList.add("pulse");
    if (!pbBattu && PB >= 8){ pbBattu = true; toast("🏆 NOUVEAU RECORD : " + PB + " votes/min"); }
  }
}, 1000);
document.getElementById("pb").textContent = PB;
// Historique de session PAR produit/mode : liste d'items vus + curseur. Reculer
// montre l'item avec sa réponse ; re-répondre CORRIGE le dernier vote.
const histo = {};   // cle() -> [{id, rep}]
const idx = {};     // cle() -> curseur
function cle(){ return MODE; }
function H(){ if(!(cle() in histo)){ histo[cle()] = []; idx[cle()] = -1; } return histo[cle()]; }
const JETON = new URLSearchParams(location.search).get("jeton") || "";
let TRIEUR = localStorage.getItem("atelier_trieur") || "";
if (JETON) TRIEUR = "(invité)";   // l'identité réelle est résolue par le serveur

function definirTrieur(n){ n=(n||"").trim(); if(!n) return; TRIEUR=n;
  localStorage.setItem("atelier_trieur", n);
  document.getElementById("modal-trieur").style.display="none"; }
if (!TRIEUR && !JETON) document.getElementById("modal-trieur").style.display="flex";

async function majGains(){
  if (!JETON) return;
  const g = await (await fetch("/api/gains?jeton=" + JETON)).json();
  if (g.gele){ document.body.innerHTML = "<p style='padding:40px;font-size:1.2rem'>Compte suspendu — contacte JB.</p>"; return; }
  const c = document.getElementById("chip-gains");
  c.style.display = "";
  document.getElementById("gains").textContent = g.gains_eur.toFixed(2) + " €";
  c.title = `${g.valides}/${g.votes} validés · or ${g.taux_or===null?"—":Math.round(g.taux_or*100)+"%"} · ${g.taux_ct} ct/label`;
}
setInterval(majGains, 30000); majGains();

async function etat(){
  const e = await (await fetch("/api/etat?produit=tous&trieur=" + encodeURIComponent(TRIEUR))).json();
  const m = e[REEL()];
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
  // rail : % de couverture de la passe + prochain jalon (le checkpoint des 100)
  const pct = Math.round(100 * (m.items - m.restants_cette_passe) / Math.max(1, m.items));
  document.getElementById("rail-pct").textContent = pct + " % de la passe";
  document.getElementById("obj").textContent = "◈ checkpoint dans " + (100 - (e.xp % 100)) + " votes";
  document.getElementById("pipe-votes").textContent = e.xp;
}

// LA CHAÎNE (panel farmers №3) : compteurs RÉELS du pipeline + delta de session.
// Voir « +1 adresse vendable » apparaître à cause de SOI, c'est le moteur du farm.
let IMPACT0 = null, IMPACT = null;
const esc = s => String(s).replace(/[<>&]/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;"}[c]));
async function majImpact(){
  IMPACT = await (await fetch("/api/impact")).json();
  if (!IMPACT0) IMPACT0 = JSON.parse(JSON.stringify(IMPACT));
  const P = IMPACT.produits, P0 = IMPACT0.produits;
  const somme = (obj, f) => Object.values(obj).reduce((a, p) => a + f(p), 0);
  const pose = (id, v, v0) => {
    document.getElementById(id).textContent = v;
    document.getElementById(id + "-d").textContent = v > v0 ? "+" + (v - v0) : "";
  };
  pose("pipe-tranches", somme(P, p => p.tranches), somme(P0, p => p.tranches));
  pose("pipe-oui", (P.piscines || {classes:{}}).classes.oui || 0,
                   (P0.piscines || {classes:{}}).classes.oui || 0);
  pose("pipe-terrasse", (P.terrasses || {classes:{}}).classes.terrasse || 0,
                        (P0.terrasses || {classes:{}}).classes.terrasse || 0);
  pose("pipe-jardin", (P.terrasses || {classes:{}}).classes.jardin || 0,
                      (P0.terrasses || {classes:{}}).classes.jardin || 0);
  pose("pipe-adresses", somme(P, p => p.adresses_vendables),
                        somme(P0, p => p.adresses_vendables));
  document.getElementById("pipe-votes-d").textContent = sessionVotes ? "+" + sessionVotes : "";
}
setInterval(majImpact, 20000); majImpact();

// FARMERS (panel №4) : volume + accord au consensus. La précision affichée
// s'auto-régule — personne ne veut être le spammeur du tableau.
async function majClassement(){
  const t = await (await fetch("/api/classement")).json();
  document.getElementById("classement-corps").innerHTML = t.slice(0, 5).map((r, i) =>
    `<div class="rang${r.trieur === TRIEUR ? " moi" : ""}"><span class="pos">${i + 1}</span>` +
    `<span class="nom">${esc(r.trieur)}</span>` +
    `<span class="acc2">${r.accord === null ? "—" : Math.round(r.accord * 100) + "%"}</span>` +
    `<b>${r.votes}</b></div>`).join("") || "<span style='color:var(--mut)'>—</span>";
}
setInterval(majClassement, 60000); majClassement();

function changerMode(m){
  MODE = m;
  document.getElementById("ong-fast").classList.toggle("actif", m === "fast");
  document.getElementById("ong-slow").classList.toggle("actif", m === "slow");
  dessinerHisto();
  const h = H();
  (idx[cle()] >= 0) ? charger(h[idx[cle()]].id, h[idx[cle()]].produit) : suivant();
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
      `&trieur=${encodeURIComponent(TRIEUR)}&sauf=${encodeURIComponent(courant)}&jeton=${JETON}`)).json();
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
    const e = H()[idx[cle()]];
    return charger(e.id, e.produit);
  }
  let r;
  if (PRECHARGE && PRECHARGE.cle === cle()){
    await PRECHARGE.pret;
    r = PRECHARGE.r;
    PRECHARGE = null;
    // le préchargé peut avoir déjà été vu dans la session (rare) : on le montre
    // quand même, le serveur l'a choisi parmi les moins vus.
  } else {
    r = await (await fetch(`/api/tache?produit=${PRODUIT}&mode=${MODE}&trieur=${encodeURIComponent(TRIEUR)}&jeton=${JETON}`)).json();
  }
  if (r.vide){ afficherVide(); etat(); return; }
  const id = r.item.id || r.item.id_piscine;
  H().push({id, rep: r.mon_dernier || null, produit: r.item.produit || PRODUIT});
  idx[cle()] = H().length - 1;
  afficher(r);
}
function precedent(){
  if (idx[cle()] > 0){ idx[cle()]--; const e = H()[idx[cle()]]; charger(e.id, e.produit); }
}
async function charger(id, produit){
  const r = await (await fetch(`/api/item?produit=${produit || PRODUIT}&mode=${MODE}&id=${encodeURIComponent(id)}&trieur=${encodeURIComponent(TRIEUR)}`)).json();
  if (!r.vide){ r.item.produit = produit || PRODUIT; afficher(r); }
}

function afficherVide(){
  document.getElementById("cadre").innerHTML = "";
  document.getElementById("boutons").innerHTML = "";
  document.getElementById("liste-adr").style.display = "none";
  document.getElementById("question").textContent = MODE === "slow"
    ? "Rien à situer : classe d'abord des zones en mode ⚡."
    : "Tout est fait pour cette passe. Respire, puis relance.";
  document.getElementById("detail").textContent = "";
}

function afficher(r){
  ITEM = r.item; MON_DERNIER = r.mon_dernier || null;
  PRODUIT = ITEM.produit || PRODUIT;   // le vote part vers le produit de L'ITEM
  etat(); dessinerHisto();
  const cadre = document.getElementById("cadre");
  cadre.className = "";
  const badges = `<span id="badge-deja">déjà répondu — recliquer corrige</span>`+
                 `<span id="badge-vu">${r.deja_vu} vote(s)</span>`;
  const boutons = document.getElementById("boutons");
  const liste = document.getElementById("liste-adr");
  if (REEL() === "existence"){
    cadre.innerHTML = `<img src="${ITEM.png}" width="560" height="560" style="image-rendering:pixelated">` + badges;
    cadre.querySelector("img").addEventListener("click", clicImage);
    modeSignal = false; cadre.style.cursor = "";
    document.getElementById("question").textContent = "Que voyez-vous dans la zone rouge ?";
    document.getElementById("detail").textContent =
      `${PRODUIT} · ${ITEM.surface.toFixed(0)} m² · score ${ITEM.score.toFixed(2)} · ${ITEM.id}`;
    liste.style.display = "none"; liste.innerHTML = "";
    document.getElementById("droite").style.display = "none";
    document.getElementById("nav-aide").style.display = "";
    document.getElementById("nav-aide").innerHTML =
      VOCAB.map(r => `<kbd>${r.touche.toUpperCase()}</kbd> ${r.libelle.toLowerCase()}`).join(" · ") +
      ` · <kbd>V</kbd> loupe · <kbd>A</kbd> revenir · <kbd>E</kbd> avancer · <kbd>ESPACE</kbd> passer (restera dû)` +
      (PRODUIT === "piscines" ? ` · <kbd>F</kbd> puis clic = piscine vue ailleurs` : "");
    boutons.innerHTML =
      VOCAB.map(r => `<button class="keycap ${r.style}" onclick="repondre('${r.code}')">` +
                    `<span class="k">${r.touche.toUpperCase()}</span>${r.libelle}</button>`).join("") +
      (PRODUIT === "piscines"
        ? `<button class="keycap aucune" onclick="armerSignal()"><span class="k">F</span>Je vois une piscine ailleurs</button>` : "");
  } else {
    cadre.innerHTML = svgAdresse(ITEM) + badges;
    cadre.querySelectorAll(".pin").forEach(g =>
      g.addEventListener("click", () => repondre(ITEM.adresses[+g.dataset.k].id_ban)));
    document.getElementById("question").textContent = "À quelle maison appartient la zone rouge ?";
    document.getElementById("detail").textContent = `${PRODUIT} · ${ITEM.id_piscine}`;
    document.getElementById("droite").style.display = "";
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
       <kbd>S</kbd> impossible · <kbd>V</kbd> loupe · <kbd>←</kbd>/<kbd>→</kbd> ou <kbd>E</kbd> naviguer · <kbd>ESPACE</kbd> passer`;
  }
  document.getElementById("badge-deja").style.display = MON_DERNIER ? "inline" : "none";
  // en bout d'historique (item neuf) : précharger le prochain pendant la réflexion
  if (idx[cle()] === H().length - 1) precharger();
}

function svgAdresse(it){
  const P = 700;
  let s = `<svg width="${P}" height="${P}" viewBox="0 0 ${P} ${P}" style="width:auto;height:auto">`;
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
  // Anti-chevauchement : les pastilles proches se repoussent (répulsion
  // itérative), un trait fin relie chaque pastille à sa VRAIE position —
  // en lotissement dense, 5 numéros pouvaient se superposer et bloquer le clic.
  const pos = it.adresses.map(a => ({x: a.x, y: a.y}));
  const R = 13, MIN = 2 * R + 2;
  for (let iter = 0; iter < 60; iter++){
    let bouge = false;
    for (let i = 0; i < pos.length; i++) for (let j = i + 1; j < pos.length; j++){
      let dx = pos[j].x - pos[i].x, dy = pos[j].y - pos[i].y;
      let d = Math.hypot(dx, dy);
      if (d < MIN){
        if (d < 1){ dx = 1; dy = 0; d = 1; }
        const p = (MIN - d) / 2 / d;
        pos[i].x -= dx * p; pos[i].y -= dy * p;
        pos[j].x += dx * p; pos[j].y += dy * p;
        bouge = true;
      }
    }
    if (!bouge) break;
  }
  pos.forEach(q => { q.x = Math.min(P - R, Math.max(R, q.x));
                     q.y = Math.min(P - R, Math.max(R, q.y)); });
  it.adresses.forEach((a, k) => {
    const q = pos[k];
    const deplace = Math.hypot(q.x - a.x, q.y - a.y) > 2;
    s += `<g class="pin" data-k="${k}" style="cursor:pointer">` +
         (deplace ? `<line x1="${a.x}" y1="${a.y}" x2="${q.x}" y2="${q.y}" stroke="#eae7df" stroke-width="1" opacity="0.55"/>` +
                    `<circle cx="${a.x}" cy="${a.y}" r="2.5" fill="#eae7df" opacity="0.8"/>` : "") +
         `<circle cx="${q.x}" cy="${q.y}" r="${R}" fill="#2b5f8a" stroke="#000" stroke-width="1.5"/>` +
         `<text x="${q.x}" y="${q.y}" fill="#fff" font-size="13" font-weight="bold" text-anchor="middle" dominant-baseline="central" pointer-events="none">${k+1}</text></g>`;
  });
  return s + "</svg>";
}

async function repondre(rep){
  if (!TRIEUR){ document.getElementById("modal-trieur").style.display="flex"; return; }
  if (!ITEM) return;
  const id = REEL() === "existence" ? ITEM.id : ITEM.id_piscine;
  const correction = MON_DERNIER !== null;
  const r = await (await fetch("/api/reponse", {method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({produit: PRODUIT, mode: MODE, id_item: id, reponse: rep,
                          trieur: TRIEUR, remplacer: correction, jeton: JETON})})).json();
  if (r.gele){ majGains(); return; }
  H()[idx[cle()]].rep = rep;
  dernierVoteT = Date.now();
  const cadre = document.getElementById("cadre");
  const styleRep = REEL() === "existence"
    ? (VOCAB.find(r => r.code === rep) || {}).style
    : null;
  cadre.className = "flash-" + (styleRep || (["aucune","indecis"].includes(rep) ? rep : "adresse"));
  if (!correction){
    serie++; sessionVotes++; voteTimes.push(Date.now());
    const s = document.getElementById("serie");
    s.textContent = serie; s.classList.remove("pulse"); void s.offsetWidth; s.classList.add("pulse");
  }
  if (!correction && serie > 0 && serie % 25 === 0)
    toast(`🔥 SÉRIE ${serie} — sans faute ni pause`);
  else
    toast((correction ? "corrigé" : "+1") + ` · ${r.n_votes} vote(s)` +
          (r.majorite ? ` · majorité « ${r.majorite} » (${Math.round(r.accord*100)}%)` : " · égalité, une passe de plus tranchera"));
  if (r.checkpoint){ montrerRecap(r); return; }
  // avance IMMÉDIATE : le flash et le toast vivent leur vie pendant que
  // l'item suivant (préchargé) s'affiche — aucun timer, les navigateurs
  // les étranglent dès que l'onglet perd le focus.
  suivant();
}

// Checkpoint des 100 = écran de fin de manche (panel farmers №6) : stats de
// session + ce que la session a débloqué DERRIÈRE. ESPACE saute — un farmer
// lancé ne se laisse pas interrompre.
let PAUSE_H = null;
function montrerRecap(r){
  document.getElementById("pause-n").textContent = r.total + " votes";
  document.getElementById("recap-session").textContent = sessionVotes;
  document.getElementById("recap-vpm").textContent = voteTimes.length;
  document.getElementById("recap-pb").textContent = PB;
  document.getElementById("pause-stats").textContent =
    `série ${serie} · session ${document.getElementById("chrono").textContent}`;
  majImpact().then(() => {
    const P = IMPACT.produits, P0 = IMPACT0.produits;
    const d = (f) => Object.keys(P).reduce((a, n) => a + f(P[n]) - (P0[n] ? f(P0[n]) : f(P[n])), 0);
    const dt = d(p => p.tranches), da = d(p => p.adresses_vendables);
    document.getElementById("recap-impact").textContent = (dt || da)
      ? `Cette session a tranché ${dt} zone(s) et rendu ${da} adresse(s) vendable(s). Chaque vote a servi.`
      : "Tes votes épaississent le consensus : la prochaine passe tranchera.";
  });
  document.getElementById("pause").style.display = "flex";
  let cpt = 5;
  document.getElementById("pause-cpt").textContent = cpt;
  PAUSE_H = setInterval(() => {
    cpt--;
    document.getElementById("pause-cpt").textContent = cpt;
    if (cpt <= 0) finirRecap();
  }, 1000);
}
function finirRecap(){
  clearInterval(PAUSE_H); PAUSE_H = null;
  document.getElementById("pause").style.display = "none";
  suivant();
}

let modeSignal = false;
function armerSignal(){
  if (REEL() !== "existence") return;
  modeSignal = !modeSignal;
  document.getElementById("cadre").style.cursor = modeSignal ? "crosshair" : "";
  toast(modeSignal ? "clique sur la piscine que tu vois (F pour annuler)" : "signalement annulé");
}
async function clicImage(ev){
  if (!modeSignal || REEL() !== "existence" || !ITEM) return;
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
// Loupe V (panel farmers №7) : zoom 2,2× dont l'origine SUIT la souris —
// on inspecte un doute sans jamais quitter le flux ni changer de mode.
document.getElementById("cadre").addEventListener("mousemove", ev => {
  const el = ev.currentTarget, rc = el.getBoundingClientRect();
  el.style.setProperty("--ox", ((ev.clientX - rc.left) / rc.width * 100) + "%");
  el.style.setProperty("--oy", ((ev.clientY - rc.top) / rc.height * 100) + "%");
});

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
    if (e.rep){
      // « oui » = code canonique serveur (fast « piscine » réécrit à l'écriture)
      const st = (VOCAB.find(r => r.code === e.rep) || {}).style ||
                 (e.rep === "oui" ? "oui" : null);
      cls += " " + (st || (["aucune","indecis"].includes(e.rep) ? e.rep : "adresse"));
    }
    if (k === idx[cle()]) cls += " courant";
    d.className = cls;
    d.title = e.id + (e.rep ? " · " + e.rep : " · sans réponse");
    d.onclick = () => { idx[cle()] = k; charger(h[k].id, h[k].produit); };
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
  if (document.getElementById("pause").style.display === "flex"){
    if (e.key === " "){ e.preventDefault(); finirRecap(); }
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const k = e.key.toLowerCase();
  if (k === "arrowleft") return precedent();
  if (k === "arrowright" || k === "e") return suivant();
  if (k === " "){ e.preventDefault(); return suivant(); }
  if (k === "v") return document.getElementById("cadre").classList.toggle("zoom");
  if (REEL() === "existence"){
    const rep = VOCAB.find(r => r.touche === k);
    if (rep) repondre(rep.code);
    else if (k === "n") repondre("non");
    else if (k === "u") repondre("incertain");
    else if (k === "a") precedent();
    else if (k === "f" && PRODUIT === "piscines") armerSignal();
  } else {
    if (e.key in AZERTY && ITEM && ITEM.adresses[AZERTY[e.key]]) repondre(ITEM.adresses[AZERTY[e.key]].id_ban);
    else if (/^[1-9]$/.test(k) && ITEM && ITEM.adresses[+k-1]) repondre(ITEM.adresses[+k-1].id_ban);
    else if (k === "a") repondre("aucune");
    else if (k === "s" || k === "u") repondre("indecis");
  }
});
(async () => {
  // Plus de sélecteur de thème : les modes fast/slow servent l'UNION des files
  // de tous les produits, le serveur choisit l'item et son thème.
  const liste = await (await fetch("/api/produits")).json();
  liste.forEach(p => { PRODUITS[p.nom] = p; });
  PRODUIT = liste[0].nom;
  changerMode("fast");
})();
</script></body></html>
"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inviter", metavar="NOM",
                   help="créer un lien d'invitation pour NOM et sortir")
    p.add_argument("--taux-ct", type=float, default=1.5,
                   help="rémunération en centimes par label validé (défaut 1,5)")
    p.add_argument("--trieurs", action="store_true",
                   help="lister les invités (token, nom, taux, gelé) et sortir")
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
    if args.inviter:
        token = votes.inviter(args.inviter, args.taux_ct)
        print(f"Invitation {args.inviter} ({args.taux_ct} ct/label) :")
        print(f"  http://localhost:{args.port}/?jeton={token}")
        print("(remplacer localhost par l'URL du tunnel une fois en ligne)")
        return
    if args.trieurs:
        for tr in votes.lister_trieurs():
            print(f"{tr['nom']:<16} taux {tr['taux_ct']} ct  "
                  f"{'GELÉ' if tr['gele'] else 'actif'}  ?jeton={tr['token']}")
        return
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
