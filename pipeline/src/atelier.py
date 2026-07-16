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
            nb = len(v.votes_item(mode, item.get("id") or item.get("id_piscine")))
            self._json({"item": item, "deja_vu": nb})
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
        valides = {"existence": {"oui", "non", "incertain"}}
        if mode not in MODES or (mode in valides and reponse not in valides[mode]):
            self._json({"erreur": "mode ou réponse invalide"}, 400)
            return
        self.votes.ajouter(mode, id_item, reponse, trieur)
        vs = self.votes.votes_item(mode, id_item)
        maj, acc = consensus(vs)
        self._json({"ok": True, "n_votes": len(vs), "majorite": maj, "accord": acc})


# ------------------------------------------------------------------ page HTML

PAGE_HTML = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Atelier — annotation</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#111;color:#eee}
 header{position:sticky;top:0;z-index:10;background:#1c1c1c;padding:10px 16px;box-shadow:0 2px 10px #000c}
 h1{font-size:1.15rem;margin:0 0 8px}
 #onglets{display:flex;gap:8px;margin-bottom:8px}
 .onglet{padding:6px 14px;border-radius:8px;background:#2a2a2a;border:1px solid #444;cursor:pointer;font-weight:bold}
 .onglet.actif{background:#1565c0;border-color:#1e88e5}
 .onglet .verrou{opacity:.7;font-weight:normal;font-size:.85rem}
 #barre{display:flex;gap:16px;align-items:center;flex-wrap:wrap;font-size:.92rem}
 #jauge-fond{flex:1;min-width:120px;height:10px;background:#333;border-radius:5px;overflow:hidden}
 #jauge{height:100%;width:0;background:#4caf50;transition:width .2s}
 .stat b{color:#9ccc65;font-variant-numeric:tabular-nums}
 kbd{background:#333;border-radius:4px;padding:1px 6px;border:1px solid #555}
 #touches{margin-top:6px;font-size:.85rem;color:#bbb}
 button{background:#333;color:#eee;border:1px solid #555;border-radius:6px;padding:6px 12px;cursor:pointer}
 #zone{display:flex;gap:18px;padding:14px 16px;align-items:flex-start;flex-wrap:wrap;justify-content:center}
 #cadre{position:relative;background:#000;border:4px solid #333;border-radius:10px;overflow:hidden}
 #cadre.dec-oui{border-color:#2e7d32}#cadre.dec-non{border-color:#c62828}#cadre.dec-incertain{border-color:#ef6c00}
 #panneau{min-width:280px;max-width:440px;flex:1}
 #verdict{padding:10px 14px;border-radius:8px;font-weight:bold;margin-bottom:10px;background:#222;color:#aaa;min-height:1.2em}
 #verdict.ok{background:#1b5e20;color:#fff}
 #liste-adr{margin-top:8px;font-size:.9rem;max-height:250px;overflow:auto}
 #liste-adr .row{padding:4px 6px;border-radius:5px;cursor:pointer;display:flex;gap:8px}
 #liste-adr .row:hover{background:#262626}
 .num{font-weight:bold;min-width:1.4em}
 .boutons{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
 .boutons button{font-weight:bold;color:#fff}
 #toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:#1565c0;color:#fff;
  padding:8px 18px;border-radius:20px;font-weight:bold;opacity:0;transition:opacity .25s;pointer-events:none}
 svg{display:block}
 .pin{cursor:pointer}
 .pin circle{stroke:#000;stroke-width:1.5}
 .pin text{fill:#fff;font-size:13px;font-weight:bold;text-anchor:middle;dominant-baseline:central;pointer-events:none}
 #modal-trieur{display:none;position:fixed;inset:0;z-index:50;background:#000a;align-items:center;justify-content:center}
 #modal-trieur .boite{background:#1c1c1c;border:1px solid #444;border-radius:12px;padding:24px;max-width:420px;width:90%}
</style></head><body>
<div id="modal-trieur"><div class="boite">
 <h2>Qui joue ?</h2>
 <input id="champ-trieur" style="width:100%;box-sizing:border-box;padding:10px;border-radius:6px;border:1px solid #555;background:#111;color:#eee"
  placeholder="prénom / pseudo" onkeydown="if(event.key==='Enter')definirTrieur(this.value)">
 <button style="width:100%;margin-top:10px;background:#1565c0" onclick="definirTrieur(document.getElementById('champ-trieur').value)">C'est parti</button>
</div></div>
<header>
 <h1>Atelier d'annotation <span style="color:#666">· Bouchemaine · piscines</span></h1>
 <div id="onglets">
  <div class="onglet actif" id="ong-existence" onclick="changerMode('existence')">Niveau 1 · Existence</div>
  <div class="onglet" id="ong-adresse" onclick="changerMode('adresse')">Niveau 2 · Adresse <span class="verrou" id="verrou-adresse"></span></div>
 </div>
 <div id="barre">
  <span class="stat">Passe <b id="passe">—</b></span>
  <span class="stat">Reste <b id="restants">—</b> dans cette passe</span>
  <div id="jauge-fond"><div id="jauge"></div></div>
  <span class="stat">Accord <b id="accord">—</b></span>
  <span class="stat">XP <b id="xp">—</b></span>
  <span class="stat">Série <b id="serie">0</b>🔥</span>
  <button onclick="location.href='/api/export/'+MODE+'.csv'">Exporter le consensus</button>
 </div>
 <div id="touches"></div>
</header>
<div id="zone">
 <div id="cadre"></div>
 <div id="panneau">
  <div id="verdict">…</div>
  <div id="detail"></div>
  <div id="liste-adr"></div>
  <div class="boutons" id="boutons"></div>
 </div>
</div>
<div id="toast"></div>
<script>
let MODE = "existence", ITEM = null, serie = 0;
let TRIEUR = localStorage.getItem("atelier_trieur") || "";
function definirTrieur(n){ n=(n||"").trim(); if(!n) return; TRIEUR=n;
  localStorage.setItem("atelier_trieur", n);
  document.getElementById("modal-trieur").style.display="none"; }
if (!TRIEUR) document.getElementById("modal-trieur").style.display="flex";

const TOUCHES = {
 existence: '<kbd>O</kbd> piscine · <kbd>N</kbd> non · <kbd>U</kbd> incertain · <kbd>S</kbd> passer',
 adresse: 'rangée des chiffres <kbd>&</kbd><kbd>é</kbd><kbd>"</kbd>… = maison 1,2,3 · <kbd>A</kbd> aucune · <kbd>S</kbd> passer'
};

async function etat(){
  const e = await (await fetch("/api/etat")).json();
  const m = e[MODE];
  document.getElementById("passe").textContent = "n°" + m.passe_courante;
  document.getElementById("restants").textContent = m.restants_cette_passe;
  document.getElementById("jauge").style.width =
    (100 * (m.items - m.restants_cette_passe) / Math.max(1, m.items)) + "%";
  document.getElementById("accord").textContent =
    m.accord_moyen === null ? "—" : Math.round(m.accord_moyen * 100) + "%";
  document.getElementById("xp").textContent = e.xp;
  const na = e.adresse.items;
  document.getElementById("verrou-adresse").textContent =
    na ? `(${na} débloquées)` : "🔒 (valide des piscines au niveau 1)";
}

function changerMode(m){
  MODE = m;
  document.getElementById("ong-existence").classList.toggle("actif", m === "existence");
  document.getElementById("ong-adresse").classList.toggle("actif", m === "adresse");
  document.getElementById("touches").innerHTML = TOUCHES[m];
  suivant();
}

async function suivant(){
  const r = await (await fetch("/api/tache?mode=" + MODE)).json();
  etat();
  const cadre = document.getElementById("cadre"), verdict = document.getElementById("verdict");
  cadre.className = ""; verdict.className = ""; verdict.textContent = "…";
  document.getElementById("liste-adr").innerHTML = "";
  if (r.vide){
    cadre.innerHTML = "";
    document.getElementById("detail").textContent = "";
    verdict.textContent = MODE === "adresse"
      ? "Rien à vérifier ici : valide d'abord des piscines au niveau 1."
      : "Rien à trier.";
    document.getElementById("boutons").innerHTML = "";
    return;
  }
  ITEM = r.item;
  if (MODE === "existence"){
    cadre.innerHTML = `<img src="${ITEM.png}" width="520" height="520" style="display:block;image-rendering:pixelated">`;
    document.getElementById("detail").textContent =
      `${ITEM.surface.toFixed(0)} m² · score ${ITEM.score.toFixed(2)} · déjà vu ${r.deja_vu} fois`;
    verdict.textContent = "Y a-t-il une piscine dans le contour rouge ?";
    document.getElementById("boutons").innerHTML =
      `<button style="background:#2e7d32" onclick="repondre('oui')">O · piscine</button>
       <button style="background:#c62828" onclick="repondre('non')">N · non</button>
       <button style="background:#ef6c00" onclick="repondre('incertain')">U · incertain</button>
       <button onclick="suivant()">S · passer</button>`;
  } else {
    cadre.innerHTML = svgAdresse(ITEM);
    cadre.querySelectorAll(".pin").forEach(g =>
      g.addEventListener("click", () => repondre(ITEM.adresses[+g.dataset.k].id_ban)));
    const liste = document.getElementById("liste-adr");
    ITEM.adresses.forEach((a, k) => {
      const row = document.createElement("div"); row.className = "row";
      row.innerHTML = `<span class="num">${k+1}</span><span>${a.texte || a.id_ban} <span style="color:#777">· ${a.dist_m} m</span></span>`;
      row.onclick = () => repondre(a.id_ban);
      liste.appendChild(row);
    });
    document.getElementById("detail").textContent =
      `piscine ${ITEM.id_piscine} · déjà vu ${r.deja_vu} fois`;
    verdict.textContent = "À quelle maison appartient cette piscine ?";
    document.getElementById("boutons").innerHTML =
      `<button style="background:#8e24aa" onclick="repondre('aucune')">A · aucune de ces adresses</button>
       <button onclick="suivant()">S · passer</button>`;
  }
}

function svgAdresse(it){
  const P = 700;
  let s = `<svg width="${P}" height="${P}" viewBox="0 0 ${P} ${P}">`;
  s += `<image x="0" y="0" width="${P}" height="${P}" href="${it.img}"/>`;
  for (const pc of it.parcelles) for (const ring of pc.rings){
    const d = "M" + ring.map(p=>p.join(",")).join(" L") + " Z";
    s += pc.propre
      ? `<path d="${d}" fill="none" stroke="#00e5ff" stroke-width="2.5" opacity="0.9"/>`
      : `<path d="${d}" fill="none" stroke="#ffeb3b" stroke-width="1" opacity="0.55"/>`;
  }
  for (const ring of it.piscine){
    const d = "M" + ring.map(p=>p.join(",")).join(" L") + " Z";
    s += `<path d="${d}" fill="rgba(255,45,85,0.15)" stroke="#ff2d55" stroke-width="2.5"/>`;
  }
  it.adresses.forEach((a, k) => {
    s += `<g class="pin" data-k="${k}"><circle cx="${a.x}" cy="${a.y}" r="12" fill="#1565c0"/>`+
         `<text x="${a.x}" y="${a.y}">${k+1}</text></g>`;
  });
  return s + "</svg>";
}

async function repondre(rep){
  if (!TRIEUR){ document.getElementById("modal-trieur").style.display="flex"; return; }
  if (!ITEM) return;
  const id = MODE === "existence" ? ITEM.id : ITEM.id_piscine;
  const r = await (await fetch("/api/reponse", {method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({mode: MODE, id_item: id, reponse: rep, trieur: TRIEUR})})).json();
  serie++;
  document.getElementById("serie").textContent = serie;
  toast(`+1 · ${r.n_votes} vote(s) sur cet item` +
        (r.majorite ? ` · majorité « ${r.majorite} » (${Math.round(r.accord*100)}%)` : " · égalité, il faudra une passe de plus"));
  suivant();
}

function toast(txt){
  const t = document.getElementById("toast");
  t.textContent = txt; t.style.opacity = 1;
  clearTimeout(t._h); t._h = setTimeout(() => t.style.opacity = 0, 1600);
}

const AZERTY = {"&":0, "é":1, '"':2, "'":3, "(":4, "-":5, "è":6, "_":7, "ç":8};
document.addEventListener("keydown", e => {
  if (document.getElementById("modal-trieur").style.display === "flex") return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const k = e.key;
  if (MODE === "existence"){
    if (k === "o" || k === "O") repondre("oui");
    else if (k === "n" || k === "N") repondre("non");
    else if (k === "u" || k === "U") repondre("incertain");
  } else {
    if (k in AZERTY && ITEM && ITEM.adresses[AZERTY[k]]) repondre(ITEM.adresses[AZERTY[k]].id_ban);
    else if (/^[1-9]$/.test(k) && ITEM && ITEM.adresses[+k-1]) repondre(ITEM.adresses[+k-1].id_ban);
    else if (k === "a" || k === "A") repondre("aucune");
  }
  if (k === "s" || k === "S" || k === " "){ e.preventDefault(); suivant(); }
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
