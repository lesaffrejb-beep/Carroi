"""Vérification humaine de l'ADRESSE assignée à une piscine (outil n°2, complément
de 16_tri_visuel).

16_tri_visuel valide l'EXISTENCE de la piscine (O/N/U). Ce script-ci répond à une
autre question : « l'adresse que l'algo a collée sur cette piscine est-elle la
bonne ? ». Il cible les cas douteux — confiance ≠ « haute », jointure ambiguë,
adresse trouvée par simple proximité (`nearest`) — et laisse l'humain trancher
visuellement : il clique sur la maison qu'il juge concernée, l'outil compare avec
l'assignation automatique et affiche « ✓ concorde » ou « ✗ divergence ».

    python 17_verification_adresse.py \
        --source data/interim/piscines_adressees_49_dev.parquet \
        [--ortho-dir data/raw/bdortho/rvb] [--toutes] [--commune 49035]

→ data/interim/verif_adresse/verif.html : page statique autonome (JS inline, aucune
  base live, tout est précalculé et embarqué en JSON). Cliquer une adresse compare
  avec l'assignation ; les choix sont mémorisés (localStorage) et exportables en CSV
  (id_piscine, id_ban_choisi_humain, id_ban_assigne_auto, concordance). Ouvrir dans
  n'importe quel navigateur.

Autonome et indépendant : n'importe RIEN de 20_join / 30_score / detection, et ne
modifie pas 16_tri_visuel — il en réutilise en LECTURE seule les fonctions pures de
projection monde→pixel et d'extraction de vignette (seul import autorisé).
"""
from __future__ import annotations

import argparse
import base64
import importlib
import json
import logging
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point
from shapely.geometry import box as sbox

from common import ensure_dirs, load_config

# Seul import autorisé : les fonctions pures de 16_tri_visuel (lecture seule).
tri = importlib.import_module("16_tri_visuel")

log = logging.getLogger("verif")

# --- Géométrie de la vue (mètres) --------------------------------------------
# La vignette ortho est un crop 120×120 m centré sur la piscine (cf. 15_detect /
# 16_tri). Mais on veut aussi montrer les adresses candidates dans un rayon de
# 150 m — donc plus large que le crop. La VUE (le cadre SVG) couvre 2×rayon pour
# que TOUS les points d'adresse tiennent dans l'image, l'ortho occupant le carré
# central de 120 m.
RAYON_M = 150.0          # rayon de recherche des adresses BAN et parcelles
CROP_ORTHO_M = 120.0     # côté de la vignette ortho (RVB), centrée sur la piscine
VUE_M = 2 * RAYON_M      # côté du cadre SVG (300 m) : englobe tout le rayon
OUT_PX = 600             # côté du cadre SVG en pixels (0,5 m/px)

# Placement de l'ortho (carré central) dans le cadre SVG, en pixels.
IMG_PX = int(round(CROP_ORTHO_M / VUE_M * OUT_PX))          # 240
IMG_OFF = int(round((VUE_M / 2 - CROP_ORTHO_M / 2) / VUE_M * OUT_PX))  # 180

COLS_ADRESSE = ["numero", "rep", "nom_voie", "code_postal", "nom_commune"]


# ------------------------------------------------------------ sélection des cas

def cas_a_verifier(gdf: gpd.GeoDataFrame, toutes: bool = False) -> gpd.GeoDataFrame:
    """Filtre les piscines dont l'adresse mérite une vérification humaine.

    Priorité à la colonne `confiance` (produite par 30_score) : on garde tout ce
    qui n'est PAS « haute ». Si elle est absente (parquet issu de 20_join, avant
    scoring), on retombe sur un proxy équivalent : jointure ambiguë OU adresse
    trouvée par simple proximité (`source_jointure == 'nearest'`) OU pas d'adresse.
    `--toutes` désactive le filtre (debug / relecture complète). Pure et testable.
    """
    if toutes:
        return gdf
    if "confiance" in gdf.columns:
        return gdf[gdf["confiance"].astype(str) != "haute"].copy()
    if {"jointure_ambigue", "source_jointure"} & set(gdf.columns):
        amb = gdf["jointure_ambigue"].fillna(True) if "jointure_ambigue" in gdf.columns \
            else False
        src = gdf.get("source_jointure")
        nearest = src.astype(str).eq("nearest") if src is not None else False
        sans_adr = gdf["id_ban"].isna() if "id_ban" in gdf.columns else False
        return gdf[amb | nearest | sans_adr].copy()
    log.warning("Ni 'confiance' ni colonnes de jointure : aucun filtre applicable, "
                "toutes les piscines seront à vérifier.")
    return gdf


# -------------------------------------------------------------- texte d'adresse

def texte_adresse_ban(row) -> str:
    """Adresse lisible depuis une ligne BAN (numero rep nom_voie, code_postal
    commune). Tolère les valeurs manquantes (NaN → chaîne vide). Pure."""
    def val(c):
        v = row.get(c)
        if v is None:
            return ""
        try:
            import math
            if isinstance(v, float) and math.isnan(v):
                return ""
        except (TypeError, ValueError):
            pass
        s = str(v)
        return s[:-2] if s.endswith(".0") else s

    ligne = " ".join(p for p in (val("numero"), val("rep"), val("nom_voie")) if p)
    ville = " ".join(p for p in (val("code_postal"), val("nom_commune")) if p)
    return ", ".join(p for p in (ligne.strip(), ville.strip()) if p)


# --------------------------------------------------- projection géom → pixels

def geom_en_anneaux_pixels(geom, cx: float, cy: float) -> list[list[list[float]]]:
    """(Multi)Polygon → liste d'anneaux, chaque anneau = liste de [col, row] dans
    le cadre VUE_M × VUE_M (OUT_PX). Réutilise les fonctions pures de 16_tri_visuel
    (_anneaux + monde_vers_pixel). Pure et testable."""
    rings = []
    for anneau in tri._anneaux(geom):
        pts = [[round(c, 1), round(r, 1)]
               for c, r in (tri.monde_vers_pixel(x, y, cx, cy, VUE_M, OUT_PX)
                            for x, y in anneau.coords)]
        if len(pts) >= 2:
            rings.append(pts)
    return rings


def adresses_pour_piscine(ban: gpd.GeoDataFrame, cx: float, cy: float,
                          id_ban_assignee) -> list[dict]:
    """Toutes les adresses BAN dans RAYON_M autour de (cx, cy), projetées en pixels,
    avec leur texte et un flag `assignee` (True = adresse actuellement retenue par
    le pipeline pour cette piscine). Triées par distance croissante. Pure (ban en
    mémoire ; sindex construit à la volée si absent)."""
    centre = Point(cx, cy)
    idx = list(ban.sindex.query(centre.buffer(RAYON_M), predicate="intersects"))
    sub = ban.iloc[idx].copy()
    if len(sub) == 0:
        return []
    sub["_dist"] = sub.geometry.distance(centre)
    sub = sub[sub["_dist"] <= RAYON_M].sort_values("_dist")
    cible = None if id_ban_assignee is None else str(id_ban_assignee)
    res = []
    for _, r in sub.iterrows():
        col, row = tri.monde_vers_pixel(r.geometry.x, r.geometry.y, cx, cy, VUE_M, OUT_PX)
        res.append({
            "id_ban": str(r["id_ban"]),
            "texte": texte_adresse_ban(r),
            "x": round(col, 1),
            "y": round(row, 1),
            "dist_m": round(float(r["_dist"]), 1),
            "assignee": bool(cible is not None and str(r["id_ban"]) == cible),
        })
    return res


def parcelles_pour_piscine(parcelles, cx: float, cy: float, id_parcelle) -> list[dict]:
    """Contours (en pixels) des parcelles qui croisent la vue, en marquant celle de
    la piscine (`propre=True`). parcelles None/vide → []. Pure et testable."""
    if parcelles is None or len(parcelles) == 0:
        return []
    demi = VUE_M / 2
    emprise = sbox(cx - demi, cy - demi, cx + demi, cy + demi)
    cible = None if id_parcelle is None else str(id_parcelle)
    out = []
    for i in parcelles.sindex.query(emprise, predicate="intersects"):
        r = parcelles.iloc[int(i)]
        rings = geom_en_anneaux_pixels(r.geometry, cx, cy)
        if rings:
            out.append({
                "id": str(r["id"]),
                "propre": bool(cible is not None and str(r["id"]) == cible),
                "rings": rings,
            })
    return out


# --------------------------------------------------------- construction d'un item

def construire_item(pisc, ban, parcelles, image_b64: str | None = None) -> dict:
    """Assemble le dict JSON embarqué pour UNE piscine : centre pixel, image (base64
    ou None), adresses candidates (dont l'assignée), contours de parcelles, et le
    rappel de l'assignation automatique. Ne dépend pas de rasterio (image passée en
    paramètre) → testable sans dalle ortho. Pure."""
    geom = pisc.geometry
    pt = geom.representative_point()
    cx, cy = pt.x, pt.y
    id_ban_assignee = pisc.get("id_ban")
    if id_ban_assignee is not None and (isinstance(id_ban_assignee, float)
                                        and id_ban_assignee != id_ban_assignee):
        id_ban_assignee = None  # NaN
    id_parcelle = pisc.get("id_parcelle")

    adresses = adresses_pour_piscine(ban, cx, cy, id_ban_assignee)
    adresse_assignee = next((a["texte"] for a in adresses if a["assignee"]), None)
    if adresse_assignee is None and pisc.get("adresse"):
        adresse_assignee = str(pisc.get("adresse"))

    return {
        "id_piscine": str(pisc.get("id_piscine", pisc.name)),
        "img": image_b64,                       # data URI base64 ou None
        "piscine": geom_en_anneaux_pixels(geom, cx, cy),
        "adresses": adresses,
        "parcelles": parcelles_pour_piscine(parcelles, cx, cy, id_parcelle),
        "id_ban_assignee": None if id_ban_assignee is None else str(id_ban_assignee),
        "adresse_assignee": adresse_assignee,
        "confiance": str(pisc.get("confiance")) if pisc.get("confiance") is not None else None,
        "source_jointure": str(pisc.get("source_jointure"))
                           if pisc.get("source_jointure") is not None else None,
    }


# ---------------------------------------------------------------- vignette ortho

def vignette_base64(index, cx: float, cy: float) -> str | None:
    """Crop ortho RVB CROP_ORTHO_M centré sur (cx, cy) → data URI PNG base64, ou
    None si le point tombe hors des dalles. Réutilise 16_tri_visuel."""
    dalle = tri.dalle_pour(cx, cy, index)
    if dalle is None:
        return None
    img = tri.extraire_vignette(dalle, cx, cy, CROP_ORTHO_M, IMG_PX)
    b64 = base64.b64encode(tri.png_bytes(img)).decode("ascii")
    return "data:image/png;base64," + b64


# ---------------------------------------------------------------- page HTML

HTML_TEMPLATE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Vérif. adresse — __DEPT__</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#111;color:#eee}
 header{position:sticky;top:0;z-index:10;background:#1c1c1c;padding:10px 16px;box-shadow:0 2px 10px #000c}
 h1{font-size:1.2rem;margin:0 0 6px}
 h1 .bleu{color:#64b5f6}
 #barre{display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:.95rem}
 #compteur{font-variant-numeric:tabular-nums;font-weight:bold}
 #jauge-fond{flex:1;min-width:140px;height:10px;background:#333;border-radius:5px;overflow:hidden}
 #jauge{height:100%;width:0;background:#4caf50;transition:width .15s}
 button{background:#333;color:#eee;border:1px solid #555;border-radius:6px;padding:6px 12px;cursor:pointer}
 #btn-export{background:#1565c0;border-color:#1e88e5;font-weight:bold}
 #btn-reset{font-size:.78rem;color:#999;background:none;border:none;text-decoration:underline}
 kbd{background:#333;border-radius:4px;padding:1px 6px;border:1px solid #555}
 #touches{margin-top:6px;font-size:.85rem;color:#bbb}
 details#regles{margin:12px 16px;background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:10px 16px;max-width:900px}
 details#regles summary{cursor:pointer;font-weight:bold;font-size:1.05rem}
 details#regles li{margin:5px 0;line-height:1.4}
 #scene{display:flex;gap:18px;flex-wrap:wrap;padding:14px 16px;align-items:flex-start}
 #cadre{position:relative;flex:0 0 auto;background:#000;border:2px solid #333;border-radius:8px}
 svg{display:block;touch-action:none}
 .pin{cursor:pointer}
 .pin circle{stroke:#000;stroke-width:1.5}
 .pin text{fill:#fff;font-size:13px;font-weight:bold;text-anchor:middle;dominant-baseline:central;pointer-events:none}
 .pin.assignee circle{stroke:#ffca28;stroke-width:3}
 .pin.choisi circle{stroke:#fff;stroke-width:3}
 #panneau{flex:1;min-width:280px;max-width:460px}
 #verdict{padding:12px 14px;border-radius:8px;font-weight:bold;font-size:1.05rem;margin-bottom:12px;min-height:1.2em;background:#222;color:#aaa}
 #verdict.ok{background:#1b5e20;color:#fff}
 #verdict.ko{background:#b71c1c;color:#fff}
 #verdict.neutre{background:#4a3800;color:#ffd54f}
 .champ{margin:8px 0;font-size:.95rem}.champ b{color:#90caf9}
 #liste-adr{margin-top:10px;font-size:.9rem;max-height:240px;overflow:auto;border-top:1px solid #333;padding-top:8px}
 #liste-adr .row{padding:4px 6px;border-radius:5px;cursor:pointer;display:flex;gap:8px}
 #liste-adr .row:hover{background:#262626}
 #liste-adr .row.assignee{color:#ffca28}
 #liste-adr .num{font-weight:bold;min-width:1.4em}
 #nav{margin-top:14px;display:flex;gap:10px;align-items:center}
 .legende{font-size:.8rem;color:#999;margin-top:8px}
 .legende .b{color:#ffca28}
</style></head><body>
<header>
 <h1>Cliquez la <span class="bleu">maison</span> qui correspond à cette piscine</h1>
 <div id="barre">
  <span id="compteur"></span>
  <div id="jauge-fond"><div id="jauge"></div></div>
  <button id="btn-export" onclick="exporter()">Exporter concordance.csv</button>
  <button id="btn-reset" onclick="if(confirm('Effacer toutes les vérifications ?')){localStorage.removeItem(CLE);location.reload()}">réinitialiser</button>
 </div>
 <div id="touches"><kbd>←</kbd>/<kbd>→</kbd> piscine précédente / suivante · cliquer un
  cercle numéroté = « c'est cette maison » · le cerclé <span style="color:#ffca28">jaune</span>
  est l'adresse qu'a choisie l'algo.</div>
</header>
<details id="regles">
 <summary>À quoi sert cet outil (à lire une fois)</summary>
 <ul>
  <li>La piscine (contour <span style="color:#ff2d55">rouge</span>) est déjà connue et validée. Ici on vérifie seulement <strong>quelle adresse</strong> lui revient.</li>
  <li>Le cercle <span style="color:#ffca28">jaune</span> est l'adresse assignée <strong>automatiquement</strong> (jointure cadastre/proximité). Vous ne la voyez qu'après avoir cliqué, pour ne pas être influencé.</li>
  <li>Cliquez le cercle de la maison que <strong>vous</strong> jugez concernée. L'outil dit aussitôt si ça <strong>concorde</strong> (✓ vert) ou <strong>diverge</strong> (✗ rouge) de l'algo.</li>
  <li>Les traits <span style="color:#ffeb3b">jaunes fins</span> sont les limites de parcelles ; la parcelle de la piscine est <span style="color:#00e5ff">cyan</span>.</li>
  <li>Une divergence n'est pas une erreur de votre part : elle signale une adresse à corriger en aval. Tout est loggé et exportable.</li>
 </ul>
</details>
<div id="scene">
 <div id="cadre"></div>
 <div id="panneau">
  <div id="verdict">Cliquez une maison pour comparer…</div>
  <div class="champ">Piscine <b id="pid"></b></div>
  <div class="champ">Confiance algo : <b id="pconf"></b> · jointure : <b id="psrc"></b></div>
  <div id="assigne-bloc" class="champ" style="display:none">Adresse assignée par l'algo :<br><b id="passigne"></b></div>
  <div class="legende">Adresses dans un rayon de __RAYON__ m (<span class="b">jaune</span> = assignée) :</div>
  <div id="liste-adr"></div>
  <div id="nav">
   <button onclick="aller(-1)">← Précédent</button>
   <button onclick="aller(1)">Suivant →</button>
   <span id="pos"></span>
  </div>
 </div>
</div>
<script>
const ITEMS = __ITEMS__;
const VUE = __VUE__;            // {out_px, img_px, img_off}
const CLE = "verif_adresse___DEPT__";
let choix = JSON.parse(localStorage.getItem(CLE) || "{}");  // id_piscine -> id_ban_choisi
let i = 0;

function svgItem(it){
  const P = VUE.out_px;
  let s = `<svg width="${P}" height="${P}" viewBox="0 0 ${P} ${P}">`;
  // fond : ortho si dispo, sinon damier gris
  if (it.img)
    s += `<image x="${VUE.img_off}" y="${VUE.img_off}" width="${VUE.img_px}" height="${VUE.img_px}" href="${it.img}"/>`;
  else
    s += `<rect x="0" y="0" width="${P}" height="${P}" fill="#20242a"/>`+
         `<rect x="${VUE.img_off}" y="${VUE.img_off}" width="${VUE.img_px}" height="${VUE.img_px}" fill="none" stroke="#444" stroke-dasharray="4 4"/>`;
  // parcelles (voisines fines jaunes, propre cyan épaisse)
  for (const pc of it.parcelles) for (const ring of pc.rings){
    const d = "M" + ring.map(p=>p.join(",")).join(" L") + " Z";
    s += pc.propre
      ? `<path d="${d}" fill="none" stroke="#00e5ff" stroke-width="2.5" opacity="0.9"/>`
      : `<path d="${d}" fill="none" stroke="#ffeb3b" stroke-width="1" opacity="0.55"/>`;
  }
  // contour piscine (rouge)
  for (const ring of it.piscine){
    const d = "M" + ring.map(p=>p.join(",")).join(" L") + " Z";
    s += `<path d="${d}" fill="rgba(255,45,85,0.15)" stroke="#ff2d55" stroke-width="2.5"/>`;
  }
  // pastilles d'adresse cliquables (numérotées)
  const dejaChoisi = choix[it.id_piscine];
  it.adresses.forEach((a, k) => {
    const cls = "pin" + (a.assignee ? " assignee" : "") +
                (dejaChoisi === a.id_ban ? " choisi" : "");
    s += `<g class="${cls}" data-k="${k}">`+
         `<circle cx="${a.x}" cy="${a.y}" r="12" fill="#1565c0"/>`+
         `<text x="${a.x}" y="${a.y}">${k+1}</text></g>`;
  });
  s += `</svg>`;
  return s;
}

function verdict(it, idBanChoisi){
  const v = document.getElementById("verdict");
  const bloc = document.getElementById("assigne-bloc");
  bloc.style.display = "block";
  document.getElementById("passigne").textContent = it.adresse_assignee || "(aucune)";
  if (!it.id_ban_assignee){
    v.className = "neutre";
    v.textContent = "L'algo n'avait assigné AUCUNE adresse à cette piscine.";
    return;
  }
  if (idBanChoisi === it.id_ban_assignee){
    v.className = "ok";
    v.textContent = "✓ concorde avec l'assignation automatique";
  } else {
    v.className = "ko";
    const a = it.adresses.find(x => x.id_ban === it.id_ban_assignee);
    v.textContent = "✗ divergence — l'algo avait assigné : " +
                    (a ? a.texte : (it.adresse_assignee || it.id_ban_assignee));
  }
}

function choisir(it, k){
  const a = it.adresses[k];
  if (!a) return;
  choix[it.id_piscine] = a.id_ban;
  localStorage.setItem(CLE, JSON.stringify(choix));
  render();          // re-render pour marquer le cercle choisi
  verdict(it, a.id_ban);
  maj();
}

function render(){
  const it = ITEMS[i];
  document.getElementById("cadre").innerHTML = svgItem(it);
  document.getElementById("cadre").querySelectorAll(".pin").forEach(g =>
    g.addEventListener("click", () => choisir(it, +g.dataset.k)));
  // liste d'adresses (miroir cliquable)
  const liste = document.getElementById("liste-adr");
  liste.innerHTML = "";
  it.adresses.forEach((a, k) => {
    const row = document.createElement("div");
    row.className = "row" + (a.assignee ? " assignee" : "");
    row.innerHTML = `<span class="num">${k+1}</span><span>${a.texte || a.id_ban} `+
                    `<span style="color:#777">· ${a.dist_m} m</span></span>`;
    row.addEventListener("click", () => choisir(it, k));
    liste.appendChild(row);
  });
  document.getElementById("pid").textContent = it.id_piscine;
  document.getElementById("pconf").textContent = it.confiance || "—";
  document.getElementById("psrc").textContent = it.source_jointure || "—";
  document.getElementById("pos").textContent = `${i+1} / ${ITEMS.length}`;
  // si déjà vérifiée, ré-affiche le verdict ; sinon invite
  const dejaChoisi = choix[it.id_piscine];
  if (dejaChoisi){ verdict(it, dejaChoisi); }
  else {
    const v = document.getElementById("verdict");
    v.className = ""; v.textContent = "Cliquez une maison pour comparer…";
    document.getElementById("assigne-bloc").style.display = "none";
  }
}

function aller(d){
  i = (i + d + ITEMS.length) % ITEMS.length;
  render();
}
function maj(){
  const faits = ITEMS.filter(it => it.id_piscine in choix).length;
  const reste = ITEMS.length - faits;
  document.getElementById("compteur").textContent =
    `Reste ${reste} à vérifier / ${ITEMS.length} total`;
  document.getElementById("jauge").style.width = (100 * faits / ITEMS.length) + "%";
}
function exporter(){
  let csv = "id_piscine,id_ban_choisi_humain,id_ban_assigne_auto,concordance\\n";
  for (const it of ITEMS){
    const c = choix[it.id_piscine];
    if (c === undefined) continue;
    const conc = it.id_ban_assignee ? (c === it.id_ban_assignee) : "";
    csv += `${it.id_piscine},${c},${it.id_ban_assignee || ""},${conc}\\n`;
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], {type: "text/csv"}));
  a.download = "concordance.csv"; a.click();
}
document.addEventListener("keydown", e => {
  if (e.key === "ArrowLeft") aller(-1);
  else if (e.key === "ArrowRight") aller(1);
});
render();
maj();
</script></body></html>
"""


def rendre_html(items: list[dict], dept: str) -> str:
    """Injecte les items, le département et la géométrie de vue dans le gabarit.
    Pure et testable (aucune I/O)."""
    vue = {"out_px": OUT_PX, "img_px": IMG_PX, "img_off": IMG_OFF}
    return (HTML_TEMPLATE
            .replace("__DEPT__", dept)
            .replace("__RAYON__", str(int(RAYON_M)))
            .replace("__VUE__", json.dumps(vue))
            .replace("__ITEMS__", json.dumps(items)))


# ---------------------------------------------------------------- orchestration

def generer(source: gpd.GeoDataFrame, ban: gpd.GeoDataFrame, parcelles, cfg: dict,
            out_dir: Path, ortho_dir: Path | None = None) -> Path:
    """Construit la page de vérification depuis les piscines déjà filtrées."""
    ban = ban.drop_duplicates("id_ban")
    ban.sindex  # force l'index spatial (recherche par rayon)
    if parcelles is not None and len(parcelles):
        parcelles.sindex

    index = tri.indexer_dalles(ortho_dir) if ortho_dir else None
    if index is None:
        log.warning("Pas de dossier ortho (--ortho-dir) : vignettes sans fond ortho "
                    "(points d'adresse + parcelles seulement).")

    items, sans_ortho = [], 0
    for _, pisc in source.iterrows():
        img = None
        if index is not None:
            pt = pisc.geometry.representative_point()
            img = vignette_base64(index, pt.x, pt.y)
            if img is None:
                sans_ortho += 1
        items.append(construire_item(pisc, ban, parcelles, image_b64=img))

    if index is not None and sans_ortho:
        log.warning("%d piscine(s) hors des dalles fournies — vignette sans fond ortho.",
                    sans_ortho)

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "verif.html"
    out.write_text(rendre_html(items, cfg["dept"]), encoding="utf-8")
    log.info("Page de vérification : %s (%d piscines à vérifier, autonome, ouvrir "
             "dans un navigateur).", out, len(items))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True,
                   help="parquet de piscines jointes/scorées (20_join ou 30_score)")
    p.add_argument("--ortho-dir", help="dalles RVB pour le fond des vignettes (optionnel)")
    p.add_argument("--commune", help="code INSEE pour restreindre à une commune")
    p.add_argument("--toutes", action="store_true",
                   help="inclure aussi les piscines à confiance 'haute' (debug)")
    args = p.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    dept = cfg["dept"]
    interim = Path(cfg["paths"]["interim"])

    source = gpd.read_parquet(args.source).to_crs(cfg["crs_metric"])
    source = source[source.geometry.notna() & ~source.geometry.is_empty].reset_index(drop=True)
    if "id_piscine" not in source.columns:
        source["id_piscine"] = source.index.astype(str)
    log.info("%d piscines chargées depuis %s.", len(source), args.source)

    a_verifier = cas_a_verifier(source, toutes=args.toutes)
    log.info("%d piscines à vérifier (%s).", len(a_verifier),
             "toutes" if args.toutes else "confiance ≠ haute / jointure douteuse")
    if len(a_verifier) == 0:
        raise SystemExit("Aucune piscine à vérifier — rien à générer (essayer --toutes).")

    ban = gpd.read_parquet(interim / f"ban_{dept}.parquet").to_crs(cfg["crs_metric"])
    parcelles = None
    pparc = interim / f"parcelles_{dept}.parquet"
    if pparc.exists():
        parcelles = gpd.read_parquet(pparc, columns=["id", "geometry"]).to_crs(cfg["crs_metric"])
    else:
        log.warning("Parcelles absentes (%s) — pas de contours cadastraux.", pparc)

    if args.commune:
        ban = ban[ban["code_insee"] == args.commune]

    out_dir = interim / "verif_adresse"
    generer(a_verifier, ban, parcelles, cfg, out_dir,
            ortho_dir=Path(args.ortho_dir) if args.ortho_dir else None)


if __name__ == "__main__":
    main()
