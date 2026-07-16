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

PRODUIT = "piscines"          # extensible : terrasses, parkings… même schéma
MODES = ("existence", "adresse")


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
        self.conn.commit()

    def ajouter(self, mode: str, id_item: str, reponse: str, trieur: str):
        with self.lock:
            self.conn.execute(
                "INSERT INTO votes VALUES (?,?,?,?,?,?)",
                (PRODUIT, mode, str(id_item), reponse, trieur,
                 datetime.now(timezone.utc).isoformat()))
            self.conn.commit()

    def compte_par_item(self, mode: str) -> Counter:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id_item, COUNT(*) FROM votes WHERE produit=? AND mode=? "
                "GROUP BY id_item", (PRODUIT, mode)).fetchall()
        return Counter(dict(rows))

    def votes_item(self, mode: str, id_item: str) -> list[str]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT reponse FROM votes WHERE produit=? AND mode=? AND id_item=?",
                (PRODUIT, mode, str(id_item))).fetchall()
        return [r[0] for r in rows]

    def tout(self, mode: str) -> dict[str, list[str]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id_item, reponse FROM votes WHERE produit=? AND mode=?",
                (PRODUIT, mode)).fetchall()
        d: dict[str, list[str]] = {}
        for id_item, rep in rows:
            d.setdefault(id_item, []).append(rep)
        return d

    def total(self) -> int:
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0]

    def vide(self) -> bool:
        return self.total() == 0

    def dernier_de(self, mode: str, id_item: str, trieur: str) -> str | None:
        """Dernière réponse de CE trieur sur cet item (pour l'afficher au retour
        arrière et proposer la correction plutôt que le doublon)."""
        with self.lock:
            row = self.conn.execute(
                "SELECT reponse FROM votes WHERE produit=? AND mode=? AND id_item=? "
                "AND trieur=? ORDER BY rowid DESC LIMIT 1",
                (PRODUIT, mode, str(id_item), trieur)).fetchone()
        return row[0] if row else None

    def remplacer_dernier(self, mode: str, id_item: str, reponse: str, trieur: str):
        """Corrige le DERNIER vote de ce trieur sur cet item (navigation arrière) :
        on supprime sa dernière réponse puis on insère la nouvelle. Le multi-passes
        reste append-only pour tout le reste — corriger sa propre erreur de clic
        n'est pas une nouvelle passe."""
        with self.lock:
            row = self.conn.execute(
                "SELECT rowid FROM votes WHERE produit=? AND mode=? AND id_item=? "
                "AND trieur=? ORDER BY rowid DESC LIMIT 1",
                (PRODUIT, mode, str(id_item), trieur)).fetchone()
            if row:
                self.conn.execute("DELETE FROM votes WHERE rowid=?", (row[0],))
                self.conn.commit()
        self.ajouter(mode, id_item, reponse, trieur)


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


def choisir_moins_vu(ids: list[str], compte: Counter, rng: random.Random) -> str | None:
    """Un id au hasard PARMI les moins votés (couverture uniforme, ordre
    imprévisible — l'ennui vient de la prévisibilité). Pure (rng injecté)."""
    if not ids:
        return None
    mini = min(compte.get(i, 0) for i in ids)
    return rng.choice([i for i in ids if compte.get(i, 0) == mini])


# ------------------------------------------------------------------- données

class Donnees:
    """Charge une fois : candidats (vignettes existence), base adressée (items
    adresse via les fonctions pures de 17), BAN, parcelles, index de dalles."""

    def __init__(self, cfg: dict, candidats_path: Path, ortho_dir: Path | None):
        interim = Path(cfg["paths"]["interim"])
        dept = cfg["dept"]
        self.vignettes_dir = interim / "tri" / "vignettes"
        self.cache_dir = interim.parent / "atelier" / "cache_ortho"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        cand = gpd.read_parquet(candidats_path)
        self.candidats = cand.assign(id_detection=cand["id_detection"].astype(str))
        log.info("%d candidats (existence).", len(self.candidats))

        adressees = gpd.read_parquet(interim / f"piscines_adressees_{dept}.parquet")
        adressees = adressees.assign(
            id_detection=adressees["id_detection"].astype(str),
            id_piscine=adressees["id_piscine"].astype(str))
        self.adressees = adressees
        self.id_piscine_vers_detection = dict(
            zip(adressees["id_piscine"], adressees["id_detection"]))
        self.ban = gpd.read_parquet(interim / f"ban_{dept}.parquet").to_crs(cfg["crs_metric"])
        self.ban = self.ban.drop_duplicates("id_ban")
        self.ban.sindex
        pparc = interim / f"parcelles_{dept}.parquet"
        self.parcelles = (gpd.read_parquet(pparc, columns=["id", "geometry"])
                          .to_crs(cfg["crs_metric"]) if pparc.exists() else None)
        if self.parcelles is not None:
            self.parcelles.sindex
        self.index_dalles = tri.indexer_dalles(ortho_dir) if ortho_dir else None
        self._cache_items_adresse: dict[str, dict] = {}

    # --- existence -----------------------------------------------------------
    def item_existence(self, id_detection: str) -> dict | None:
        row = self.candidats[self.candidats["id_detection"] == id_detection]
        if row.empty:
            return None
        r = row.iloc[0]
        return {"id": id_detection,
                "png": f"/api/vignette/{id_detection}.png",
                "surface": float(r["surface_m2"]),
                "score": float(r["score_detection"])}

    # --- adresse -------------------------------------------------------------
    def item_adresse(self, id_piscine: str) -> dict | None:
        if id_piscine in self._cache_items_adresse:
            return self._cache_items_adresse[id_piscine]
        row = self.adressees[self.adressees["id_piscine"] == id_piscine]
        if row.empty or not row.iloc[0].geometry or row.iloc[0].geometry.geom_type == "Point":
            return None
        item = v17.construire_item(row.iloc[0], self.ban, self.parcelles, image_b64=None)
        if not item["adresses"]:
            return None                       # rien à cliquer : invérifiable
        item["img"] = f"/api/ortho/{id_piscine}.jpg"
        self._cache_items_adresse[id_piscine] = item
        return item

    def ortho_jpeg(self, id_piscine: str) -> bytes | None:
        cache = self.cache_dir / f"{id_piscine}.jpg"
        if cache.exists():
            return cache.read_bytes()
        if self.index_dalles is None:
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
            votes.ajouter("existence", str(r["id_detection"]), str(r["decision"]),
                          str(r.get("trieur", "import")))
        log.info("Amorçage existence : %d votes importés de %s.", len(df), fusion.name)
    conc_dir = repo / "handoff" / "concordance_recus"
    fichiers = sorted(conc_dir.glob("concordance_*.csv")) if conc_dir.exists() else []
    if fichiers:
        df = pd.read_csv(fichiers[-1])
        for _, r in df.iterrows():
            votes.ajouter("adresse", str(r["id_piscine"]),
                          str(r["id_ban_choisi_humain"]), "JB")
        log.info("Amorçage adresse : %d votes importés de %s.", len(df), fichiers[-1].name)


# ------------------------------------------------------------------- serveur

def etat_global(donnees: Donnees, votes: Votes) -> dict:
    """Statistiques de progression par mode : items, couverture de la passe
    courante, passe minimale/maximale, accord moyen sur les items votés."""
    out = {}
    ids_exist = list(donnees.candidats["id_detection"])
    tout_exist = votes.tout("existence")
    ids_adresse = ids_adresse_debloques(donnees, tout_exist)
    for mode, ids in (("existence", ids_exist), ("adresse", ids_adresse)):
        t = votes.tout(mode)
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
    ids = []
    for _, r in donnees.adressees.iterrows():
        if existence_acquise(votes_existence.get(r["id_detection"], [])):
            ids.append(r["id_piscine"])
    return ids


class Handler(BaseHTTPRequestHandler):
    donnees: Donnees = None       # injectés au démarrage
    votes: Votes = None
    rng = random.Random()

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
        d, v = self.donnees, self.votes

        if u.path == "/":
            data = PAGE_HTML.encode()
            self._binaire(data, "text/html; charset=utf-8")
        elif u.path == "/api/etat":
            self._json(etat_global(d, v))
        elif u.path == "/api/tache":
            mode = q.get("mode", ["existence"])[0]
            if mode == "existence":
                ids = list(d.candidats["id_detection"])
                id_item = choisir_moins_vu(ids, v.compte_par_item("existence"), self.rng)
                item = d.item_existence(id_item) if id_item else None
            else:
                ids = ids_adresse_debloques(d, v.tout("existence"))
                # ne proposer que les items qui ont des candidates cliquables
                ids = [i for i in ids if d.item_adresse(i)]
                id_item = choisir_moins_vu(ids, v.compte_par_item("adresse"), self.rng)
                item = d.item_adresse(id_item) if id_item else None
            if item is None:
                self._json({"vide": True})
                return
            id_item = item.get("id") or item.get("id_piscine")
            trieur = q.get("trieur", [""])[0]
            self._json({"item": item, "deja_vu": len(v.votes_item(mode, id_item)),
                        "mon_dernier": v.dernier_de(mode, id_item, trieur) if trieur else None})
        elif u.path == "/api/item":
            # Item PRÉCIS (navigation avant/arrière dans l'historique de session).
            mode = q.get("mode", ["existence"])[0]
            id_item = q.get("id", [""])[0]
            trieur = q.get("trieur", [""])[0]
            item = d.item_existence(id_item) if mode == "existence" else d.item_adresse(id_item)
            if item is None:
                self._json({"vide": True})
                return
            self._json({"item": item, "deja_vu": len(v.votes_item(mode, id_item)),
                        "mon_dernier": v.dernier_de(mode, id_item, trieur) if trieur else None})
        elif u.path.startswith("/api/vignette/"):
            data = d.vignette_png(u.path.rsplit("/", 1)[1].removesuffix(".png"))
            if data is None:
                self.send_error(404)
            else:
                self._binaire(data, "image/png")
        elif u.path.startswith("/api/ortho/"):
            data = d.ortho_jpeg(u.path.rsplit("/", 1)[1].removesuffix(".jpg"))
            if data is None:
                self.send_error(404)
            else:
                self._binaire(data, "image/jpeg")
        elif u.path == "/api/export/existence.csv":
            lignes = ["id_detection,decision,n_votes,accord"]
            for i, vs in sorted(v.tout("existence").items()):
                maj, acc = consensus(vs)
                lignes.append(f"{i},{maj or 'incertain'},{len(vs)},{acc:.2f}")
            self._csv("\n".join(lignes) + "\n", "existence_consensus.csv")
        elif u.path == "/api/export/adresse.csv":
            assigne = dict(zip(d.adressees["id_piscine"],
                               d.adressees["id_ban"].astype(str)))
            lignes = ["id_piscine,id_ban_choisi_humain,id_ban_assigne_auto,concordance,n_votes,accord"]
            for i, vs in sorted(v.tout("adresse").items()):
                maj, acc = consensus(vs)
                auto = assigne.get(i, "")
                conc = str(maj == auto).lower() if maj and auto and auto != "nan" else ""
                lignes.append(f"{i},{maj or ''},{auto if auto != 'nan' else ''},{conc},{len(vs)},{acc:.2f}")
            self._csv("\n".join(lignes) + "\n", "adresse_consensus.csv")
        else:
            self.send_error(404)

    # ----------------------------------------------------------------- POST
    def do_POST(self):
        if urlparse(self.path).path != "/api/reponse":
            self.send_error(404)
            return
        corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        mode, id_item = corps["mode"], str(corps["id_item"])
        reponse, trieur = str(corps["reponse"]), str(corps.get("trieur") or "anonyme")
        # 'indecis' = « je ne peux pas répondre » : un vrai vote (l'item ne
        # reviendra pas cette passe), jamais vendu, exclu du consensus utile.
        valides = {"existence": {"oui", "non", "incertain"}}
        if mode not in MODES or (mode in valides and reponse not in valides[mode]):
            self._json({"erreur": "mode ou réponse invalide"}, 400)
            return
        if corps.get("remplacer"):
            self.votes.remplacer_dernier(mode, id_item, reponse, trieur)
        else:
            self.votes.ajouter(mode, id_item, reponse, trieur)
        vs = self.votes.votes_item(mode, id_item)
        maj, acc = consensus(vs)
        self._json({"ok": True, "n_votes": len(vs), "majorite": maj, "accord": acc})


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
  <div id="marque">L'ATELIER<small>Bouchemaine · piscines</small></div>
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
  </div>
  <button id="btn-export" onclick="location.href='/api/export/'+MODE+'.csv'">Exporter</button>
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
  <div id="nav-aide"><kbd>←</kbd>/<kbd>Q</kbd> revenir · <kbd>→</kbd>/<kbd>D</kbd> avancer ·
   <kbd>S</kbd> passer sans répondre (l'item restera dû)</div>
 </div>
</div>

<div id="histo-barre"><span id="histo-titre">SESSION</span><div id="histo"></div></div>
<div id="toast"></div>

<script>
let MODE = "existence", ITEM = null, MON_DERNIER = null, serie = 0;
// Historique de session PAR MODE : liste d'items vus + curseur. Reculer montre
// l'item avec sa réponse ; re-répondre CORRIGE le dernier vote (pas de doublon).
const histo = {existence: [], adresse: []};   // [{id, rep}]
const idx = {existence: -1, adresse: -1};
let TRIEUR = localStorage.getItem("atelier_trieur") || "";

function definirTrieur(n){ n=(n||"").trim(); if(!n) return; TRIEUR=n;
  localStorage.setItem("atelier_trieur", n);
  document.getElementById("modal-trieur").style.display="none"; }
if (!TRIEUR) document.getElementById("modal-trieur").style.display="flex";

async function etat(){
  const e = await (await fetch("/api/etat")).json();
  const m = e[MODE];
  document.getElementById("passe").textContent = m.passe_courante;
  document.getElementById("restants").textContent = m.restants_cette_passe;
  document.getElementById("jauge").style.width =
    (100 * (m.items - m.restants_cette_passe) / Math.max(1, m.items)) + "%";
  document.getElementById("accord").textContent =
    m.accord_moyen === null ? "—" : Math.round(m.accord_moyen * 100) + "%";
  document.getElementById("xp").textContent = e.xp;
  const na = e.adresse.items;
  document.getElementById("verrou-adresse").textContent = na ? `· ${na}` : "· 🔒";
}

function changerMode(m){
  MODE = m;
  document.getElementById("ong-existence").classList.toggle("actif", m === "existence");
  document.getElementById("ong-adresse").classList.toggle("actif", m === "adresse");
  dessinerHisto();
  (idx[m] >= 0) ? charger(histo[m][idx[m]].id) : suivant();
}

async function suivant(){
  // avancer : d'abord dans l'historique, sinon une nouvelle tâche « moins vue »
  if (idx[MODE] < histo[MODE].length - 1){
    idx[MODE]++;
    return charger(histo[MODE][idx[MODE]].id);
  }
  const r = await (await fetch(`/api/tache?mode=${MODE}&trieur=${encodeURIComponent(TRIEUR)}`)).json();
  if (r.vide){ afficherVide(); etat(); return; }
  const id = r.item.id || r.item.id_piscine;
  histo[MODE].push({id, rep: r.mon_dernier || null});
  idx[MODE] = histo[MODE].length - 1;
  afficher(r);
}
function precedent(){
  if (idx[MODE] > 0){ idx[MODE]--; charger(histo[MODE][idx[MODE]].id); }
}
async function charger(id){
  const r = await (await fetch(`/api/item?mode=${MODE}&id=${encodeURIComponent(id)}&trieur=${encodeURIComponent(TRIEUR)}`)).json();
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
    document.getElementById("question").textContent = "Y a-t-il une piscine dans le contour rouge ?";
    document.getElementById("detail").textContent =
      `${ITEM.surface.toFixed(0)} m² · score ${ITEM.score.toFixed(2)} · ${ITEM.id}`;
    liste.style.display = "none"; liste.innerHTML = "";
    boutons.innerHTML =
      `<button class="keycap oui" onclick="repondre('oui')"><span class="k">O</span>Piscine</button>
       <button class="keycap non" onclick="repondre('non')"><span class="k">N</span>Pas une piscine</button>
       <button class="keycap unsure" onclick="repondre('incertain')"><span class="k">U</span>Impossible à dire</button>`;
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
       <button class="keycap unsure" onclick="repondre('indecis')"><span class="k">U</span>Impossible à dire</button>`;
  }
  document.getElementById("badge-deja").style.display = MON_DERNIER ? "inline" : "none";
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
    body: JSON.stringify({mode: MODE, id_item: id, reponse: rep, trieur: TRIEUR,
                          remplacer: correction})})).json();
  histo[MODE][idx[MODE]].rep = rep;
  const cadre = document.getElementById("cadre");
  cadre.className = "flash-" + (["oui","non","incertain","indecis","aucune"].includes(rep) ? rep : "adresse");
  if (!correction){
    serie++;
    const s = document.getElementById("serie");
    s.textContent = serie; s.classList.remove("pulse"); void s.offsetWidth; s.classList.add("pulse");
  }
  toast((correction ? "corrigé" : "+1") + ` · ${r.n_votes} vote(s)` +
        (r.majorite ? ` · majorité « ${r.majorite} » (${Math.round(r.accord*100)}%)` : " · égalité, une passe de plus tranchera"));
  setTimeout(suivant, correction ? 350 : 220);
}

function toast(txt){
  const t = document.getElementById("toast");
  t.textContent = txt; t.classList.add("on");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("on"), 1700);
}

function dessinerHisto(){
  const conteneur = document.getElementById("histo");
  conteneur.innerHTML = "";
  const h = histo[MODE];
  h.slice(-60).forEach((e, kRel) => {
    const k = h.length - Math.min(60, h.length) + kRel;
    const d = document.createElement("div");
    let cls = "pas";
    if (e.rep) cls += " " + (["oui","non","incertain","indecis","aucune"].includes(e.rep) ? e.rep : "adresse");
    if (k === idx[MODE]) cls += " courant";
    d.className = cls;
    d.title = e.id + (e.rep ? " · " + e.rep : " · sans réponse");
    d.onclick = () => { idx[MODE] = k; charger(h[k].id); };
    conteneur.appendChild(d);
  });
  conteneur.scrollLeft = conteneur.scrollWidth;
}

const AZERTY = {"&":0, "é":1, '"':2, "'":3, "(":4, "-":5, "è":6, "_":7, "ç":8};
document.addEventListener("keydown", e => {
  if (document.getElementById("modal-trieur").style.display === "flex") return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const k = e.key;
  if (k === "ArrowLeft" || k === "q" || k === "Q") return precedent();
  if (k === "ArrowRight" || k === "d" || k === "D") return suivant();
  if (k === "s" || k === "S" || k === " "){ e.preventDefault(); return suivant(); }
  if (MODE === "existence"){
    if (k === "o" || k === "O") repondre("oui");
    else if (k === "n" || k === "N") repondre("non");
    else if (k === "u" || k === "U") repondre("incertain");
  } else {
    if (k in AZERTY && ITEM && ITEM.adresses[AZERTY[k]]) repondre(ITEM.adresses[AZERTY[k]].id_ban);
    else if (/^[1-9]$/.test(k) && ITEM && ITEM.adresses[+k-1]) repondre(ITEM.adresses[+k-1].id_ban);
    else if (k === "a" || k === "A") repondre("aucune");
    else if (k === "u" || k === "U") repondre("indecis");
  }
});
changerMode("existence");
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
    candidats = Path(args.candidats) if args.candidats else \
        interim / f"piscines_candidates_{cfg['dept']}_49035.parquet"
    ortho = Path(args.ortho_dir) if args.ortho_dir else \
        repo / "data" / "raw" / "bdortho" / "49035" / "rvb"

    votes = Votes(interim.parent / "atelier" / "atelier.sqlite")
    if votes.vide():
        amorcer_depuis_acquis(votes, repo)

    Handler.donnees = Donnees(cfg, candidats, ortho if ortho.exists() else None)
    Handler.votes = votes

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    log.info("Atelier prêt : http://localhost:%d (Ctrl-C pour arrêter).", args.port)
    srv.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
