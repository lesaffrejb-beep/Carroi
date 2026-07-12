"""Tri visuel humain des candidats piscines — l'étape qui garantit la précision vendable.

Deux modes :

1. Génération de la planche de tri :
       python 16_tri_visuel.py --candidats data/interim/piscines_candidates_49.parquet \
           --ortho-dir data/raw/bdortho/rvb
   → data/interim/tri/vignettes/*.png (crop 60×60 m centré sur chaque candidat)
   → data/interim/tri/tri.html : page statique, raccourcis O (oui) / N (non) /
     U (incertain), navigation ←/→, progression sauvegardée en localStorage,
     bouton d'export → decisions.csv. Ouvrir dans n'importe quel navigateur.

2. Application des décisions :
       python 16_tri_visuel.py --candidats ... --apply data/interim/tri/decisions.csv
   → data/interim/piscines_detectees_{dept}.parquet (methode='valide_humain')
   Seuls les « oui » passent. Refuse d'écrire si le tri est incomplet (>2 % de
   candidats sans décision) : une base à moitié triée n'est pas une base.

Garde-fou : c'est CE fichier de sortie (et lui seul) que 20_join consomme en
production. Les candidats bruts ne se joignent pas, ne s'exportent pas.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import logging
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import from_bounds

from common import ensure_dirs, load_config

log = logging.getLogger("tri")


# ---------------------------------------------------- empreinte de planche
# Une planche de tri (HTML + vignettes) n'est valide QUE pour le parquet de
# candidats depuis lequel elle a été générée. Si les candidats changent (nouveau
# run de détection, seuils différents), les id_detection peuvent se décaler et un
# vieux decisions.csv appliquerait des jugements sur les mauvais biens. On scelle
# donc chaque planche par le SHA-256 (tronqué) du fichier parquet lui-même.

def hash12_parquet(path) -> str:
    """SHA-256 des OCTETS du fichier parquet des candidats, tronqué à 12 hex.

    Empreinte stable : deux personnes qui régénèrent la planche depuis le même
    fichier obtiennent le même hash12 ; un fichier différent (même d'un octet) en
    donne un autre. Pure et testable (ne lit pas le contenu géospatial, juste les
    octets)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def commune_depuis_nom(candidats_path, dept: str) -> str:
    """Extrait la commune du nom piscines_candidates_{dept}_{commune}.parquet.
    Motif absent (nom départemental ou libre) → 'dept'. Pure et testable."""
    m = re.match(rf"piscines_candidates_{re.escape(str(dept))}_(.+)\.parquet$",
                 Path(candidats_path).name)
    return m.group(1) if m else "dept"


def id_planche(candidats_path, dept: str) -> str:
    """Identifiant de planche « {dept}_{commune}_{hash12} » — porté par le HTML
    (data-planche), la clé localStorage et le nom du decisions.csv exporté."""
    return f"{dept}_{commune_depuis_nom(candidats_path, dept)}_{hash12_parquet(candidats_path)}"


# ---------------------------------------------------------------- vignettes

def cle_incertitude(score: float) -> float:
    """Distance au seuil d'indécision 0,5 : petite = cas limite, grande = évident.

    Trier les vignettes par cette clé CROISSANTE fait voir à l'humain les cas
    incertains d'abord (esprit frais), les évidences en rafale à la fin — leçon
    de l'état de l'art (docs/15 §2) : on ne gaspille pas l'attention sur l'évident.
    """
    return abs(float(score) - 0.5)


def indexer_dalles(ortho_dir: Path):
    """Index SPATIAL des emprises de dalles (STRtree) : la recherche linéaire
    coûterait dalles × candidats (7 100 × 100 000 à l'échelle du département)."""
    import geopandas as gpd
    from shapely.geometry import box as sbox

    boxes, paths = [], []
    for p in sorted(ortho_dir.iterdir()):
        if p.suffix.lower() in (".jp2", ".tif", ".tiff"):
            with rasterio.open(p) as src:
                boxes.append(sbox(*src.bounds))
                paths.append(p)
    if not paths:
        raise SystemExit(f"Aucune dalle dans {ortho_dir}.")
    serie = gpd.GeoSeries(boxes)
    return {"serie": serie, "sindex": serie.sindex, "paths": paths}


def dalle_pour(x: float, y: float, index) -> Path | None:
    from shapely.geometry import Point

    hits = index["sindex"].query(Point(x, y), predicate="within")
    return index["paths"][int(hits[0])] if len(hits) else None


def extraire_vignette(path: Path, x: float, y: float, cote_m: float, out_px: int) -> np.ndarray | None:
    """Crop RVB cote_m × cote_m centré sur (x, y), rééchantillonné à out_px."""
    with rasterio.open(path) as src:
        demi = cote_m / 2.0
        win = from_bounds(x - demi, y - demi, x + demi, y + demi, src.transform)
        data = src.read(
            [1, 2, 3], window=win, boundless=True, fill_value=0,
            out_shape=(3, out_px, out_px),
        )
    img = np.transpose(data, (1, 2, 0))
    if img.dtype != np.uint8:
        maxv = float(img.max()) or 1.0
        img = (img.astype(np.float64) / maxv * 255).astype(np.uint8)
    return img


def png_bytes(img: np.ndarray) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    return buf.getvalue()


def jpeg_bytes(img: np.ndarray, quality: int = 82) -> bytes:
    """Ré-encode la vignette en JPEG (qualité 82 par défaut). Pour le mode
    --embarquer : à l'échelle communale, les JPEG inline pèsent ~5× moins que les
    PNG et rendent la planche autonome (un seul fichier, aucune référence externe)."""
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(img).convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def data_uri_jpeg(jpeg: bytes) -> str:
    """Encapsule des octets JPEG en data:URI base64 (src inline pour <img>)."""
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


# ------------------------------------------------ surimpression cadastre

def monde_vers_pixel(wx: float, wy: float, cx: float, cy: float,
                     cote_m: float, out_px: int) -> tuple[float, float]:
    """(x, y) Lambert-93 → (col, row) dans une vignette cote_m × cote_m, out_px de
    côté, centrée sur (cx, cy). L'axe Y est inversé (le nord est en haut de l'image)."""
    demi = cote_m / 2.0
    col = (wx - (cx - demi)) / cote_m * out_px
    row = ((cy + demi) - wy) / cote_m * out_px
    return col, row


def _anneaux(geom):
    """Itère les anneaux (extérieur + trous) d'un (Multi)Polygon ; ignore le reste."""
    gt = getattr(geom, "geom_type", None)
    if gt == "Polygon":
        yield geom.exterior
        yield from geom.interiors
    elif gt == "MultiPolygon":
        for part in geom.geoms:
            yield part.exterior
            yield from part.interiors


def charger_parcelles(cfg: dict) -> "gpd.GeoDataFrame | None":
    """data/interim/parcelles_{dept}.parquet (EPSG:2154, colonnes id/commune/geometry).
    Absent → None + warning (les vignettes seront tracées sans limites cadastrales,
    pas d'échec)."""
    p = Path(cfg["paths"]["interim"]) / f"parcelles_{cfg['dept']}.parquet"
    if not p.exists():
        log.warning("Parcelles absentes (%s) — vignettes sans limites de parcelles.", p)
        return None
    g = gpd.read_parquet(p, columns=["id", "commune", "geometry"])
    log.info("%d parcelles chargées pour la surimpression cadastrale.", len(g))
    return g


def charger_pci_piscines(cfg: dict) -> "gpd.GeoDataFrame | None":
    """Concatène tous les data/interim/piscines_pci_sym65_*.parquet (piscines
    cadastrées PCI, SYM=65, EPSG:2154). Aucun fichier → None (pas de badge, pas
    d'échec). Filtre défensivement sur SYM=65 si la colonne est présente."""
    interim = Path(cfg["paths"]["interim"])
    fichiers = sorted(interim.glob("piscines_pci_sym65_*.parquet"))
    if not fichiers:
        log.warning("Aucun fichier piscines_pci_sym65_*.parquet — pas de badge cadastre.")
        return None
    parts = [gpd.read_parquet(f) for f in fichiers]
    g = pd.concat(parts, ignore_index=True)
    g = gpd.GeoDataFrame(g, geometry="geometry", crs=parts[0].crs)
    if "SYM" in g.columns:
        g = g[g["SYM"].astype(str) == "65"].reset_index(drop=True)
    log.info("%d piscines cadastrées PCI (SYM=65) chargées depuis %d fichier(s).",
             len(g), len(fichiers))
    return g


def corrobore_cadastre(geom, pci: "gpd.GeoDataFrame | None", seuil_m: float = 5.0) -> bool:
    """True si le polygone candidat est à moins de seuil_m d'une piscine cadastrée
    (SYM=65). Pure et testable : pci None/vide → False (robustesse fichiers absents)."""
    if pci is None or len(pci) == 0 or geom is None or geom.is_empty:
        return False
    idx = list(pci.sindex.query(geom.buffer(seuil_m), predicate="intersects"))
    if not idx:
        return False
    return bool(pci.geometry.iloc[idx].distance(geom).min() < seuil_m)


def dessiner_surimpression(img: np.ndarray, cx: float, cy: float, cote_m: float,
                           out_px: int, geom_candidat, parcelles: "gpd.GeoDataFrame | None"):
    """Trace en surimpression sur la vignette : les limites des parcelles qui
    croisent l'emprise du crop (jaune fin semi-transparent), puis le contour du
    polygone candidat en couleur vive (rouge). Retourne un nouvel array RGB."""
    from PIL import Image, ImageDraw
    from shapely.geometry import box as sbox

    pil = Image.fromarray(img).convert("RGBA")
    overlay = Image.new("RGBA", pil.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    demi = cote_m / 2.0

    def trace(geom, fill, width):
        for anneau in _anneaux(geom):
            pts = [monde_vers_pixel(x, y, cx, cy, cote_m, out_px)
                   for x, y in anneau.coords]
            if len(pts) >= 2:
                draw.line(pts, fill=fill, width=width)

    if parcelles is not None and len(parcelles):
        emprise = sbox(cx - demi, cy - demi, cx + demi, cy + demi)
        for i in parcelles.sindex.query(emprise, predicate="intersects"):
            trace(parcelles.geometry.iloc[int(i)], (255, 235, 59, 150), 1)

    if geom_candidat is not None and not geom_candidat.is_empty:
        trace(geom_candidat, (255, 45, 85, 255), 2)

    return np.asarray(Image.alpha_composite(pil, overlay).convert("RGB"))


# ---------------------------------------------------------------- page HTML

HTML_TEMPLATE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Tri piscines — __DEPT__</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#111;color:#eee}
 header{position:sticky;top:0;z-index:10;background:#1c1c1c;padding:10px 16px;box-shadow:0 2px 10px #000c}
 h1{font-size:1.25rem;margin:0 0 6px}
 h1 .rouge{color:#ff2d55}
 #barre{display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:.95rem}
 #compteur{font-variant-numeric:tabular-nums;font-weight:bold}
 #corrobore_count{color:#64b5f6}
 #jauge-fond{flex:1;min-width:140px;height:10px;background:#333;border-radius:5px;overflow:hidden}
 #jauge{height:100%;width:0;background:#4caf50;transition:width .15s}
 #touches{margin-top:6px;font-size:.85rem;color:#bbb}
 button{background:#333;color:#eee;border:1px solid #555;border-radius:6px;padding:6px 12px;cursor:pointer}
 #btn-export{background:#1565c0;border-color:#1e88e5;font-weight:bold}
 #btn-reset{font-size:.78rem;color:#999;background:none;border:none;text-decoration:underline}
 kbd{background:#333;border-radius:4px;padding:1px 6px;border:1px solid #555}
 details#regles{margin:12px 16px;background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:10px 16px;max-width:900px}
 details#regles summary{cursor:pointer;font-weight:bold;font-size:1.05rem}
 details#regles li{margin:5px 0;line-height:1.4}
 #galerie{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;padding:14px 16px}
 .carte{margin:0;position:relative;border:3px solid #333;border-radius:8px;overflow:hidden;cursor:pointer;background:#000}
 .carte img{display:block;width:100%;image-rendering:pixelated}
 .carte figcaption{padding:4px 8px;font-size:.8rem;color:#aaa;background:#1c1c1c}
 .carte.focus{border-color:#fff;box-shadow:0 0 0 3px #fff5}
 .carte.dec-oui{border-color:#2e7d32}.carte.dec-non{border-color:#c62828}.carte.dec-incertain{border-color:#ef6c00}
 .marque{position:absolute;top:8px;right:8px;font-weight:bold;font-size:1rem;padding:2px 10px;border-radius:6px;color:#fff}
 .dec-oui .marque{background:#2e7d32}.dec-non .marque{background:#c62828}.dec-incertain .marque{background:#ef6c00}
 .cad{position:absolute;top:8px;left:8px;font-size:.85rem;font-weight:bold;padding:2px 8px;border-radius:6px;background:#0d47a1;color:#fff;box-shadow:0 0 0 2px #fff3}
 #trieur-actuel b{color:#fff}
 #lien-changer{color:#64b5f6;font-size:.85rem;margin-left:5px}
 #par-trieur{color:#9ccc65;font-variant-numeric:tabular-nums}
 #modal-trieur{display:none;position:fixed;inset:0;z-index:50;background:#000a;align-items:center;justify-content:center}
 #modal-trieur .boite{background:#1c1c1c;border:1px solid #444;border-radius:12px;padding:24px;max-width:420px;width:90%;box-shadow:0 8px 40px #000}
 #modal-trieur h2{margin:0 0 8px;font-size:1.3rem}
 #modal-trieur p{color:#bbb;font-size:.9rem;margin:0 0 16px}
 #modal-trieur .rapides{display:flex;gap:10px;margin-bottom:14px}
 #modal-trieur .rapides button{flex:1;font-size:1.1rem;font-weight:bold;padding:12px}
 #champ-trieur{width:100%;box-sizing:border-box;padding:10px;border-radius:6px;border:1px solid #555;background:#111;color:#eee;margin-bottom:10px}
 #modal-trieur .valider{width:100%;background:#1565c0;border-color:#1e88e5;font-weight:bold;padding:10px}
</style></head><body data-planche="__PLANCHE__">
<div id="modal-trieur">
 <div class="boite">
  <h2>Qui trie ?</h2>
  <p>Ton prénom est enregistré avec tes réponses (traçabilité qualité). Un pseudo convient aussi.</p>
  <div class="rapides">
   <button onclick="definirTrieur('JB')">JB</button>
   <button onclick="definirTrieur('Azan')">Azan</button>
  </div>
  <input id="champ-trieur" type="text" placeholder="ou tape ton prénom / pseudo"
         onkeydown="if(event.key==='Enter')definirTrieur(this.value)">
  <button class="valider" onclick="definirTrieur(document.getElementById('champ-trieur').value)">Commencer à trier</button>
 </div>
</div>
<header>
 <h1>Y a-t-il une piscine dans le <span class="rouge">CONTOUR ROUGE</span> ?</h1>
 <div id="barre">
  <span id="trieur-actuel">Trieur : <b id="trieur-nom">—</b><a href="#" id="lien-changer" onclick="demanderTrieur();return false">changer</a></span>
  <span id="compteur"></span>
  <div id="jauge-fond"><div id="jauge"></div></div>
  <span id="corrobore_count"></span>
  <span id="par-trieur"></span>
  <button id="btn-export" onclick="exporter()">Exporter decisions.csv</button>
  <button id="btn-reset" onclick="if(confirm('Effacer TOUTES les décisions et repartir de zéro ?')){localStorage.removeItem(CLE);location.reload()}">réinitialiser le tri</button>
 </div>
 <div id="touches"><kbd>O</kbd> = piscine · <kbd>N</kbd> = pas une piscine ·
  <kbd>U</kbd> = incertain (sera ÉCARTÉ de la vente) · <kbd>Z</kbd> ou <kbd>←</kbd> = annuler la dernière décision
  — cliquer une vignette déjà triée pour la corriger.</div>
</header>
<details id="regles">
 <summary>Règles du jeu (à lire avant de trier)</summary>
 <p>Vous validez l'<strong>EXISTENCE</strong> de la piscine, pas son adresse (l'adresse est calculée ailleurs, par le cadastre).</p>
 <ul>
  <li><strong>O (oui)</strong> : bassin manifeste dans le contour rouge — enterré, semi-enterré ou hors-sol rigide, même bâché ou hors d'eau.</li>
  <li><strong>N (non)</strong> : bâche/pergola, trampoline, toit ou store bleu, bassin d'ornement/étang, ombre, véhicule…</li>
  <li><strong>U (incertain)</strong> : vous hésitez vraiment. L'incertain n'est JAMAIS vendu — dans le doute, on écarte. Mais si vous êtes sûr à ~90 %, répondez O ou N.</li>
  <li><strong>Piscine du voisin</strong> visible au bord de l'image : IGNOREZ-la, jugez uniquement le contour rouge (elle a sa propre vignette ailleurs).</li>
  <li><strong>Le contour rouge ne couvre qu'un morceau</strong> d'une vraie piscine : O quand même (la géométrie est recollée ailleurs).</li>
  <li><strong>Badge ⌂ cadastré</strong> : le cadastre connaît une piscine ici — quasi certain, allez vite (O sauf contre-évidence flagrante).</li>
  <li><strong>Les traits jaunes</strong> sont les limites de parcelles cadastrales, pour situer.</li>
 </ul>
</details>
<div id="galerie"></div>
<script>
const ITEMS = __ITEMS__;
// Clé de stockage DÉRIVÉE de la planche (data-planche = {dept}_{commune}_{hash12}) :
// deux communes ou deux versions des candidats ne partagent JAMAIS le même
// localStorage — plus de collision, plus de décisions d'une planche écrasant l'autre.
const PLANCHE = document.body.dataset.planche;
const CLE = "tri_" + PLANCHE;
// Identité du trieur : clé GLOBALE (la personne, pas la planche) — le même trieur
// garde son nom d'une planche/commune à l'autre.
const CLE_TRIEUR = "tri_trieur";

// Chaque décision est un objet {d, t, ts} : d = oui/non/incertain, t = trieur,
// ts = horodatage ISO. MIGRATION : une valeur héritée peut être une simple chaîne
// (tri commencé avant l'ajout de l'identité) → {d: chaîne, t: "inconnu", ts: null}.
function normDec(v){
  return (typeof v === "string") ? {d: v, t: "inconnu", ts: null} : v;
}
let dec = JSON.parse(localStorage.getItem(CLE) || "{}");
let migre = false;
for (const id in dec){
  const n = normDec(dec[id]);
  if (n !== dec[id]){ dec[id] = n; migre = true; }
}
if (migre) localStorage.setItem(CLE, JSON.stringify(dec));

let TRIEUR = localStorage.getItem(CLE_TRIEUR) || "";
let histo = [];  // pile d'annulation (session courante)
let i = -1;

// ------------------------------------------------ identité du trieur
function definirTrieur(nom){
  nom = (nom || "").trim();
  if (!nom) return;
  TRIEUR = nom;
  localStorage.setItem(CLE_TRIEUR, TRIEUR);
  document.getElementById("modal-trieur").style.display = "none";
  majTrieur();
}
function demanderTrieur(){
  const champ = document.getElementById("champ-trieur");
  if (champ) champ.value = "";
  document.getElementById("modal-trieur").style.display = "flex";
}
function majTrieur(){
  document.getElementById("trieur-nom").textContent = TRIEUR || "—";
}

// Panneau règles : ouvert par défaut à la PREMIÈRE visite, état mémorisé ensuite.
const regles = document.getElementById("regles");
regles.open = localStorage.getItem(CLE + "_regles") !== "ferme";
regles.addEventListener("toggle",
  () => localStorage.setItem(CLE + "_regles", regles.open ? "ouvert" : "ferme"));

// Galerie : une carte par candidat, chargement paresseux des vignettes.
const gal = document.getElementById("galerie"), cartes = {};
ITEMS.forEach((it, k) => {
  const fig = document.createElement("figure");
  fig.className = "carte";
  fig.dataset.id = it.id;
  fig.dataset.corrobore = it.corrobore ? "1" : "0";
  fig.innerHTML =
    `<img loading="lazy" src="${it.png}" alt="candidat ${it.id}">` +
    (it.corrobore ? '<span class="cad">⌂ cadastré</span>' : '') +
    `<span class="marque"></span>` +
    `<figcaption>${it.surface.toFixed(0)} m² · score ${it.score.toFixed(2)} · ${it.id}</figcaption>`;
  fig.addEventListener("click", () => focaliser(k));
  gal.appendChild(fig);
  cartes[it.id] = fig;
});
const N_CORR = ITEMS.filter(it => it.corrobore).length;
document.getElementById("corrobore_count").textContent =
  `${ITEMS.length} candidats dont ${N_CORR} corroborés cadastre`;

function premierNonTrie(depuis){
  for (let k = depuis; k < ITEMS.length; k++) if (!(ITEMS[k].id in dec)) return k;
  for (let k = 0; k < depuis; k++) if (!(ITEMS[k].id in dec)) return k;
  return Math.max(0, Math.min(depuis, ITEMS.length - 1));
}
function marquer(id){
  const c = cartes[id], o = dec[id], d = o ? o.d : null;
  c.classList.remove("dec-oui", "dec-non", "dec-incertain");
  c.querySelector(".marque").textContent = d ? d.toUpperCase() : "";
  if (d) c.classList.add("dec-" + d);
}
function focaliser(k, defiler = true){
  if (i >= 0) cartes[ITEMS[i].id].classList.remove("focus");
  i = k;
  const c = cartes[ITEMS[i].id];
  c.classList.add("focus");
  if (defiler) c.scrollIntoView({block: "center", behavior: "smooth"});
  maj();
}
function maj(){
  const faits = Object.keys(dec).length, reste = ITEMS.length - faits;
  document.getElementById("compteur").textContent =
    `Reste ${reste} à trier / ${ITEMS.length} total`;
  document.getElementById("jauge").style.width = (100 * faits / ITEMS.length) + "%";
  document.getElementById("btn-export").textContent = reste
    ? `Exporter decisions.csv (il reste ${reste} non triés — l'application refusera au-delà de 2 %)`
    : "Exporter decisions.csv";
  // Compteurs par trieur, en direct, calculés depuis les objets localStorage.
  const parTrieur = {};
  for (const id in dec){
    const t = dec[id].t || "inconnu";
    parTrieur[t] = (parTrieur[t] || 0) + 1;
  }
  document.getElementById("par-trieur").textContent =
    Object.keys(parTrieur).sort().map(t => `${t} : ${parTrieur[t]}`).join(" · ");
}
function decider(v){
  if (!TRIEUR){ demanderTrieur(); return; }  // pas de décision anonyme
  const it = ITEMS[i];
  histo.push({id: it.id, avant: dec[it.id]});
  dec[it.id] = {d: v, t: TRIEUR, ts: new Date().toISOString()};
  localStorage.setItem(CLE, JSON.stringify(dec));
  marquer(it.id);
  focaliser(premierNonTrie(i + 1));
}
function annuler(){
  const h = histo.pop();
  if (!h) return;
  if (h.avant === undefined) delete dec[h.id]; else dec[h.id] = h.avant;
  localStorage.setItem(CLE, JSON.stringify(dec));
  marquer(h.id);
  focaliser(ITEMS.findIndex(it => it.id === h.id));
}
function exporter(){
  const reste = ITEMS.length - Object.keys(dec).length;
  if (reste) alert(`Il reste ${reste} vignette(s) non triée(s) — l'application (--apply) ` +
                   `refusera au-delà de 2 %. Le CSV est exporté quand même.`);
  // Contrat élargi : id_detection,decision,trieur,horodatage. Le format à 2
  // colonnes reste accepté en consommation (rétro-compat) ; on exporte les 4.
  let csv = "id_detection,decision,trieur,horodatage\\n";
  for (const [id, o] of Object.entries(dec))
    csv += `${id},${o.d},${o.t || "inconnu"},${o.ts || ""}\\n`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], {type: "text/csv"}));
  // Nom horodatable côté réception + empreinte de planche : le fichier reçu dit
  // à quelle planche il s'applique (contenu du CSV inchangé : id_detection,decision).
  a.download = "decisions_" + PLANCHE + ".csv"; a.click();
}
document.addEventListener("keydown", e => {
  // Modal d'identité ouvert : on laisse la frappe aller au champ, pas de raccourci.
  if (document.getElementById("modal-trieur").style.display === "flex") return;
  if (e.key === "o" || e.key === "O") decider("oui");
  else if (e.key === "n" || e.key === "N") decider("non");
  else if (e.key === "u" || e.key === "U") decider("incertain");
  else if (e.key === "z" || e.key === "Z" || e.key === "ArrowLeft") annuler();
  else if (e.key === "ArrowRight") focaliser(premierNonTrie(i + 1));
});
// Reprise : restaurer les marques puis sauter à la première vignette non triée.
for (const id of Object.keys(dec)) if (id in cartes) marquer(id);
focaliser(premierNonTrie(0), Object.keys(dec).length > 0);
// À l'ouverture : si aucun trieur mémorisé, demander « Qui trie ? » ; sinon l'afficher.
majTrieur();
if (!TRIEUR) demanderTrieur();
</script></body></html>
"""


def rendre_html(items: list[dict], dept: str, planche: str | None = None) -> str:
    """Injecte les candidats, le département et l'empreinte de planche dans le
    gabarit. Pure et testable : le contrat d'export (id_detection,decision ∈
    oui/non/incertain) est porté par le JS de ce gabarit, les tests vérifient la
    présence des blocs clés. `planche` = {dept}_{commune}_{hash12} ; s'il est absent
    (appel de test minimal), on retombe sur un identifiant purement départemental."""
    if planche is None:
        planche = f"{dept}_dept_000000000000"
    return (HTML_TEMPLATE
            .replace("__PLANCHE__", planche)
            .replace("__DEPT__", dept)
            .replace("__ITEMS__", json.dumps(items)))


def generer_planche(candidats: gpd.GeoDataFrame, ortho_dir: Path, cfg: dict, out_dir: Path,
                    candidats_path, reutiliser_vignettes: bool = False,
                    embarquer: bool = False) -> Path:
    tri_cfg = cfg["tri_visuel"]
    cote_m, out_px = tri_cfg["vignette_m"], tri_cfg["vignette_px"]
    out_dir.mkdir(parents=True, exist_ok=True)

    vign_dir = out_dir / "vignettes"
    vign_dir.mkdir(parents=True, exist_ok=True)

    # --reutiliser-vignettes : ne re-rendre que les PNG manquants (régénérer le
    # HTML seul prend quelques secondes au lieu de ~6 min pour 977 vignettes).
    if reutiliser_vignettes:
        a_rendre = {str(i) for i in candidats["id_detection"]
                    if not (vign_dir / f"{i}.png").exists()}
        log.info("Réutilisation des vignettes existantes : %d PNG à (re)rendre.", len(a_rendre))
    else:
        a_rendre = {str(i) for i in candidats["id_detection"]}

    # L'index des dalles ortho n'est nécessaire QUE pour (re)rendre des vignettes.
    # Si tout est réutilisé (a_rendre vide), on s'en passe : régénérer le HTML (et
    # embarquer les vignettes) ne requiert alors ni les dalles ni le disque externe.
    if a_rendre:
        if ortho_dir is None:
            raise SystemExit(
                f"{len(a_rendre)} vignette(s) à rendre mais --ortho-dir absent. "
                "Fournir les dalles ortho, ou régénérer avec toutes les vignettes présentes."
            )
        index = indexer_dalles(Path(ortho_dir))
    else:
        index = None

    # Surimpression cadastrale : limites de parcelles (le trieur voit si la piscine
    # est chez le voisin) + badge « corroboré » (piscine cadastrée PCI à proximité).
    # Les parcelles (lourdes) ne sont chargées que si des vignettes sont à rendre.
    parcelles = charger_parcelles(cfg) if a_rendre else None
    if parcelles is not None and len(parcelles):
        # Restreindre à l'emprise des candidats (+ marge) : inutile d'indexer les
        # 1,2 M de parcelles du département pour une planche communale.
        minx, miny, maxx, maxy = candidats.total_bounds
        parcelles = parcelles.cx[minx - cote_m:maxx + cote_m, miny - cote_m:maxy + cote_m]
        parcelles.sindex  # force la construction de l'index spatial (mise en cache)
    pci = charger_pci_piscines(cfg)
    if pci is not None and len(pci):
        pci.sindex

    # Vignettes en FICHIERS séparés (pas de base64 embarqué : à l'échelle d'un
    # département — 50-100 k candidats — un HTML monolithique ferait plusieurs Go
    # et tuerait le navigateur ; les <img loading="lazy"> de la galerie ne chargent
    # que les vignettes visibles à l'écran).
    items, sans_dalle, sans_vignette, n_corr = [], 0, 0, 0
    for _, row in candidats.iterrows():
        id_det = str(row["id_detection"])
        img = None
        if id_det in a_rendre:
            pt = row.geometry.representative_point()
            dalle = dalle_pour(pt.x, pt.y, index)
            if dalle is None:
                sans_dalle += 1
                continue
            img = extraire_vignette(dalle, pt.x, pt.y, cote_m, out_px)
            img = dessiner_surimpression(img, pt.x, pt.y, cote_m, out_px, row.geometry, parcelles)
            (vign_dir / f"{id_det}.png").write_bytes(png_bytes(img))
        elif not (vign_dir / f"{id_det}.png").exists():
            # Réutilisation : pas de PNG et pas de re-rendu possible → on écarte.
            sans_vignette += 1
            continue
        if embarquer:
            # Planche autonome : la vignette est ré-encodée JPEG q82 et inline en
            # data:URI (aucune référence vignettes/*.png). Si on n'a pas re-rendu
            # l'image (réutilisation), on relit le PNG existant pour le ré-encoder.
            if img is None:
                from PIL import Image
                img = np.asarray(Image.open(vign_dir / f"{id_det}.png").convert("RGB"))
            png_field = data_uri_jpeg(jpeg_bytes(img))
        else:
            png_field = f"vignettes/{id_det}.png"
        corrobore = corrobore_cadastre(row.geometry, pci)
        n_corr += int(corrobore)
        items.append(
            {
                "id": id_det,
                "png": png_field,
                "surface": float(row["surface_m2"]),
                "score": float(row["score_detection"]),
                "corrobore": int(corrobore),
            }
        )
    if sans_dalle:
        log.warning("%d candidat(s) hors des dalles fournies — vignettes absentes, "
                    "ils resteront SANS décision (le --apply les signalera).", sans_dalle)
    if sans_vignette:
        log.warning("%d candidat(s) sans PNG existant en mode réutilisation — écartés "
                    "(fournir --ortho-dir pour les rendre).", sans_vignette)
    if not items:
        raise SystemExit("Aucune vignette générée — mauvais dossier de dalles ?")

    # Cas incertains d'abord (|score-0,5| croissant), évidences à la fin (docs/15 §2).
    items.sort(key=lambda it: cle_incertitude(it["score"]))

    planche = id_planche(candidats_path, cfg["dept"])
    html = rendre_html(items, cfg["dept"], planche)
    out = out_dir / "tri.html"
    out.write_text(html, encoding="utf-8")
    log.info("Planche de tri : %s (planche=%s, %d vignettes dont %d corroborées "
             "cadastre, %s, ouvrir dans un navigateur).", out, planche, len(items),
             n_corr, "AUTONOME (vignettes inline)" if embarquer else "vignettes externes")
    return out


# ---------------------------------------------------------------- application

SEUIL_INCOMPLET = 0.02  # >2 % de candidats sans décision → refus


def appliquer_decisions(candidats: gpd.GeoDataFrame, decisions: pd.DataFrame) -> gpd.GeoDataFrame:
    """Ne garde que les 'oui'. Pure et testable. Échoue bruyamment si :
    - decisions référence des id inconnus (mélange de fichiers ?)
    - plus de SEUIL_INCOMPLET des candidats n'ont pas de décision (tri bâclé)
    """
    if not {"id_detection", "decision"} <= set(decisions.columns):
        raise ValueError("decisions.csv : colonnes id_detection,decision attendues.")
    # Comparaison en str : les id_detection sont des identifiants stables
    # (contrat.ids_stables), pas des entiers d'ordre de run.
    decisions = decisions.assign(id_detection=decisions["id_detection"].astype(str))
    valides = {"oui", "non", "incertain"}
    inconnues = set(decisions["decision"]) - valides
    if inconnues:
        raise ValueError(f"Décisions invalides : {inconnues} (attendu {valides}).")

    ids_cand = set(candidats["id_detection"].astype(str))
    ids_dec = set(decisions["id_detection"])
    if ids_dec - ids_cand:
        raise ValueError(
            f"{len(ids_dec - ids_cand)} décision(s) pour des id inconnus — le CSV ne "
            "correspond pas à ce fichier de candidats."
        )
    manquants = ids_cand - ids_dec
    if len(manquants) > SEUIL_INCOMPLET * len(ids_cand):
        raise ValueError(
            f"Tri incomplet : {len(manquants)}/{len(ids_cand)} candidats sans décision "
            f"(tolérance {SEUIL_INCOMPLET:.0%}). Finir le tri avant d'appliquer."
        )
    if manquants:
        log.warning("%d candidat(s) sans décision → traités comme 'non' (exclus).", len(manquants))

    oui = set(decisions.loc[decisions["decision"] == "oui", "id_detection"])
    out = candidats[candidats["id_detection"].astype(str).isin(oui)].copy()
    out["methode"] = "valide_humain"
    n_inc = (decisions["decision"] == "incertain").sum()
    log.info("Décisions : %d oui, %d non, %d incertains (exclus — on ne vend pas le doute).",
             len(out), (decisions["decision"] == "non").sum(), n_inc)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidats", required=True, help="parquet de 15_detect_piscines.py")
    p.add_argument("--ortho-dir", help="dalles RVB (mode génération)")
    p.add_argument("--apply", help="decisions.csv exporté depuis tri.html")
    p.add_argument("--reutiliser-vignettes", action="store_true",
                   help="ne re-rendre que les PNG manquants (régénération HTML rapide)")
    p.add_argument("--embarquer", action="store_true",
                   help="planche autonome : vignettes ré-encodées JPEG q82 inline "
                        "(data:URI) dans le HTML, un seul fichier sans référence externe")
    p.add_argument("--planche-hash",
                   help="empreinte (hash12) attendue de la planche à l'application : "
                        "refuse si le parquet de candidats a changé (sauf --force)")
    p.add_argument("--force", action="store_true",
                   help="outrepasse le contrôle d'empreinte de planche (--planche-hash)")
    args = p.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    candidats = gpd.read_parquet(args.candidats)
    log.info("%d candidats chargés depuis %s.", len(candidats), args.candidats)

    if args.apply:
        if args.planche_hash:
            actuel = hash12_parquet(args.candidats)
            if actuel != args.planche_hash:
                msg = (f"la planche a été générée depuis une autre version des "
                       f"candidats — régénérer la planche ou utiliser --force "
                       f"(empreinte attendue {args.planche_hash}, candidats actuels {actuel})")
                if args.force:
                    log.warning("%s [--force : on applique quand même]", msg)
                else:
                    raise SystemExit(msg)
        decisions = pd.read_csv(args.apply)
        valides = appliquer_decisions(candidats, decisions)
        out = Path(cfg["paths"]["interim"]) / f"piscines_detectees_{cfg['dept']}.parquet"
        valides.to_parquet(out)
        log.info("Écrit : %s (%d piscines validées). Prochaine étape : "
                 "20_join_piscines_adresses.py --source-piscines %s", out, len(valides), out)
    elif args.ortho_dir or args.reutiliser_vignettes:
        # --reutiliser-vignettes seul suffit à régénérer le HTML si toutes les
        # vignettes existent déjà (ortho non requise, cf. generer_planche).
        out_dir = Path(cfg["paths"]["interim"]) / "tri"
        ortho = Path(args.ortho_dir) if args.ortho_dir else None
        generer_planche(candidats, ortho, cfg, out_dir,
                        candidats_path=args.candidats,
                        reutiliser_vignettes=args.reutiliser_vignettes,
                        embarquer=args.embarquer)
    else:
        raise SystemExit("Préciser --ortho-dir (générer la planche) ou --apply (appliquer le tri).")


if __name__ == "__main__":
    main()
