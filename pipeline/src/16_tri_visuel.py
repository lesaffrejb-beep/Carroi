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
import io
import json
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import from_bounds

from common import ensure_dirs, load_config

log = logging.getLogger("tri")


# ---------------------------------------------------------------- vignettes

def indexer_dalles(ortho_dir: Path) -> list[tuple[tuple, Path]]:
    index = []
    for p in sorted(ortho_dir.iterdir()):
        if p.suffix.lower() in (".jp2", ".tif", ".tiff"):
            with rasterio.open(p) as src:
                index.append((tuple(src.bounds), p))
    if not index:
        raise SystemExit(f"Aucune dalle dans {ortho_dir}.")
    return index


def dalle_pour(x: float, y: float, index) -> Path | None:
    for (x0, y0, x1, y1), p in index:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return p
    return None


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


# ---------------------------------------------------------------- page HTML

HTML_TEMPLATE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Tri piscines — __DEPT__</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#111;color:#eee;display:flex;flex-direction:column;height:100vh}
 header{padding:10px 16px;background:#1c1c1c;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
 #compteur{font-variant-numeric:tabular-nums}
 main{flex:1;display:flex;align-items:center;justify-content:center;position:relative}
 img{max-height:80vh;max-width:90vw;image-rendering:pixelated;outline:2px solid #333}
 .badge{position:absolute;top:12px;right:12px;font-size:2rem;font-weight:bold;padding:4px 14px;border-radius:8px}
 .oui{background:#1b5e20}.non{background:#b71c1c}.incertain{background:#e65100}
 footer{padding:8px 16px;background:#1c1c1c;font-size:.9rem;color:#aaa}
 button{background:#333;color:#eee;border:1px solid #555;border-radius:6px;padding:6px 12px;cursor:pointer}
 kbd{background:#333;border-radius:4px;padding:1px 6px;border:1px solid #555}
</style></head><body>
<header>
 <strong>Tri piscines __DEPT__</strong>
 <span id="compteur"></span>
 <button onclick="exporter()">Exporter decisions.csv</button>
 <button onclick="if(confirm('Effacer toutes les décisions ?')){localStorage.removeItem(CLE);location.reload()}">Réinitialiser</button>
</header>
<main><img id="vue" alt="vignette"><div id="badge" class="badge" hidden></div></main>
<footer><kbd>O</kbd> piscine &nbsp; <kbd>N</kbd> pas piscine &nbsp; <kbd>U</kbd> incertain &nbsp;
 <kbd>←</kbd>/<kbd>→</kbd> naviguer — les décisions sont sauvegardées localement à chaque touche ;
 exporter le CSV à la fin puis lancer <code>16_tri_visuel.py --apply</code>.</footer>
<script>
const ITEMS = __ITEMS__;
const CLE = "tri_piscines___DEPT__";
let dec = JSON.parse(localStorage.getItem(CLE) || "{}");
let i = ITEMS.findIndex(it => !(it.id in dec)); if (i < 0) i = 0;
function maj(){
  const it = ITEMS[i];
  document.getElementById("vue").src = it.png;
  const d = dec[it.id], b = document.getElementById("badge");
  b.hidden = !d; if(d){b.textContent = d.toUpperCase(); b.className = "badge " + d;}
  const faits = Object.keys(dec).length;
  document.getElementById("compteur").textContent =
    `${i+1}/${ITEMS.length} — ${faits} décidé(s) (${(100*faits/ITEMS.length).toFixed(1)} %)` +
    ` — id ${it.id}, ${it.surface} m², score ${it.score}`;
}
function decider(v){ dec[ITEMS[i].id] = v; localStorage.setItem(CLE, JSON.stringify(dec));
  if (i < ITEMS.length - 1) i++; maj(); }
function exporter(){
  let csv = "id_detection,decision\\n";
  for (const [id, v] of Object.entries(dec)) csv += `${id},${v}\\n`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], {type: "text/csv"}));
  a.download = "decisions.csv"; a.click();
}
document.addEventListener("keydown", e => {
  if (e.key === "o" || e.key === "O") decider("oui");
  else if (e.key === "n" || e.key === "N") decider("non");
  else if (e.key === "u" || e.key === "U") decider("incertain");
  else if (e.key === "ArrowRight" && i < ITEMS.length - 1) { i++; maj(); }
  else if (e.key === "ArrowLeft" && i > 0) { i--; maj(); }
});
maj();
</script></body></html>
"""


def generer_planche(candidats: gpd.GeoDataFrame, ortho_dir: Path, cfg: dict, out_dir: Path) -> Path:
    tri_cfg = cfg["tri_visuel"]
    index = indexer_dalles(ortho_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Vignettes en FICHIERS séparés (pas de base64 embarqué : à l'échelle d'un
    # département — 50-100 k candidats — un HTML monolithique ferait plusieurs Go
    # et tuerait le navigateur ; l'interface n'affiche qu'une image à la fois,
    # le navigateur ne charge donc que la vignette courante).
    vign_dir = out_dir / "vignettes"
    vign_dir.mkdir(parents=True, exist_ok=True)
    items, sans_dalle = [], 0
    for _, row in candidats.iterrows():
        pt = row.geometry.representative_point()
        dalle = dalle_pour(pt.x, pt.y, index)
        if dalle is None:
            sans_dalle += 1
            continue
        img = extraire_vignette(dalle, pt.x, pt.y, tri_cfg["vignette_m"], tri_cfg["vignette_px"])
        id_det = str(row["id_detection"])
        (vign_dir / f"{id_det}.png").write_bytes(png_bytes(img))
        items.append(
            {
                "id": id_det,
                "png": f"vignettes/{id_det}.png",
                "surface": float(row["surface_m2"]),
                "score": float(row["score_detection"]),
            }
        )
    if sans_dalle:
        log.warning("%d candidat(s) hors des dalles fournies — vignettes absentes, "
                    "ils resteront SANS décision (le --apply les signalera).", sans_dalle)
    if not items:
        raise SystemExit("Aucune vignette générée — mauvais dossier de dalles ?")

    html = (HTML_TEMPLATE
            .replace("__DEPT__", cfg["dept"])
            .replace("__ITEMS__", json.dumps(items)))
    out = out_dir / "tri.html"
    out.write_text(html, encoding="utf-8")
    log.info("Planche de tri : %s (%d vignettes, autonome, ouvrir dans un navigateur).",
             out, len(items))
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
    args = p.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    candidats = gpd.read_parquet(args.candidats)
    log.info("%d candidats chargés depuis %s.", len(candidats), args.candidats)

    if args.apply:
        decisions = pd.read_csv(args.apply)
        valides = appliquer_decisions(candidats, decisions)
        out = Path(cfg["paths"]["interim"]) / f"piscines_detectees_{cfg['dept']}.parquet"
        valides.to_parquet(out)
        log.info("Écrit : %s (%d piscines validées). Prochaine étape : "
                 "20_join_piscines_adresses.py --source-piscines %s", out, len(valides), out)
    elif args.ortho_dir:
        out_dir = Path(cfg["paths"]["interim"]) / "tri"
        generer_planche(candidats, Path(args.ortho_dir), cfg, out_dir)
    else:
        raise SystemExit("Préciser --ortho-dir (générer la planche) ou --apply (appliquer le tri).")


if __name__ == "__main__":
    main()
