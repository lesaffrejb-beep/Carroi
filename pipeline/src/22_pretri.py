"""Pré-tri appris : le classifieur qui divise le farm des communes suivantes.

Le levier économique mesuré (docs/18 §IA, roadmap 2026-07-16) : l'humain met
2,6 s par vignette ; le détecteur v1 est à 25 % de précision ; aucun seuil
simple n'est acceptable (5-17 % de piscines perdues). Ce module apprend des
labels humains multi-passes de l'Atelier un score P(piscine) par candidat, puis
coupe la file en TROIS :

    p >= t_haut  → AUTO-OUI  (précision mesurée >= objectif, pas de farm)
    p <= t_bas   → AUTO-NON  (rappel préservé : perte de piscines <= tolérance)
    entre les 2  → FARM      (l'humain ne voit plus que l'incertain)

C'est l'architecture de tous les systèmes sérieux (DGFiP « Foncier innovant »,
active learning) : le modèle absorbe l'évident, l'humain tranche le litigieux.

Features : géométrie du polygone (surface, compacité, solidité, score v1) +
statistiques de couleur du crop ortho AUTOUR du candidat (bleus, saturation),
recalculées depuis les vignettes de tri en masquant les surimpressions.
Modèle : HistGradientBoosting + calibration isotonique, validé en GroupKFold
par DALLE (jamais de fuite spatiale : on teste sur des quartiers jamais vus).

Usage :
    # entraîner + choisir les seuils depuis les labels consensus de l'Atelier
    python 22_pretri.py train --produit piscines

    # scorer un parquet de candidats d'une NOUVELLE commune (colonnes pretri_p,
    # pretri_verdict) — la planche de tri / l'Atelier ne farment que le FARM
    python 22_pretri.py apply --candidats data/interim/piscines_candidates_49_XXXXX.parquet

Sorties : data/interim/pretri/{produit}_modele.joblib, {produit}_seuils.json,
{produit}_evaluation.md (le rapport chiffré, à lire avant de faire confiance).
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from common import ensure_dirs, load_config

log = logging.getLogger("pretri")

# Couleurs des surimpressions des vignettes (16_tri_visuel) à MASQUER avant de
# mesurer la couleur du terrain : contour rouge, parcelles jaunes.
OVERLAYS = np.array([[255, 45, 85], [255, 235, 59]], dtype=float)

# Tolérance auto-non : 2 %. Mesure du 2026-07-17 : les piscines sous p=0,001
# sont des bassins couverts/invisibles (3-4 sur 242), la même queue que le
# rappel de tout détecteur — les refuser bloquait toute bande auto-non (1 %
# = 2,4 piscines < 3). La perte est documentée dans chaque rapport.
PERTE_MAX_AUTO_NON = 0.02
PRECISION_MIN_AUTO_OUI = 0.95  # auto-oui : précision mesurée >= 95 %


# ------------------------------------------------------------------- features

def _stats(pix: np.ndarray, prefixe: str) -> dict:
    """Statistiques couleur d'un paquet de pixels RGB (float). Pure."""
    if len(pix) == 0:
        return {}
    r, g, bl = pix[:, 0], pix[:, 1], pix[:, 2]
    maxc, minc = pix.max(axis=1), pix.min(axis=1)
    sat = np.where(maxc > 0, (maxc - minc) / np.maximum(maxc, 1), 0)
    bleuite = bl - (r + g) / 2                       # signature eau vs toit/gazon
    cyan = (bl > r) & (g > r)                        # eau de piscine : bleu-vert
    return {
        f"{prefixe}_bleuite_moy": float(bleuite.mean()),
        f"{prefixe}_bleuite_p90": float(np.percentile(bleuite, 90)),
        f"{prefixe}_cyan_frac": float(cyan.mean()),
        f"{prefixe}_sat_moy": float(sat.mean()),
        f"{prefixe}_lum_moy": float(pix.mean()),
        f"{prefixe}_lum_std": float(pix.std()),
    }


def features_couleur(png_path: Path, geom, cx: float, cy: float,
                     cote_m: float) -> dict | None:
    """Couleur DANS le polygone candidat + contraste avec son voisinage.

    Leçon du premier entraînement (2026-07-17) : des stats sur une fenêtre de
    24 m diluent une piscine de 4 m dans la pelouse — les piscines perdues
    avaient exactement la couleur moyenne du décor. On rasterise donc le
    polygone dans le repère de la vignette (monde→pixel de 16_tri_visuel) et on
    mesure DEDANS, DEHORS (anneau de contexte), et la DIFFÉRENCE."""
    import importlib
    from PIL import Image, ImageDraw

    tri16 = importlib.import_module("16_tri_visuel")
    if not png_path.exists() or geom is None or geom.is_empty:
        return None
    img = np.asarray(Image.open(png_path).convert("RGB"), dtype=float)
    out_px = img.shape[0]
    masque = Image.new("1", (out_px, out_px), 0)
    dr = ImageDraw.Draw(masque)
    for anneau in tri16._anneaux(geom):
        pts = [tri16.monde_vers_pixel(x, y, cx, cy, cote_m, out_px)
               for x, y in anneau.coords]
        if len(pts) >= 3:
            dr.polygon(pts, fill=1)
    m = np.asarray(masque, dtype=bool)
    pix = img.reshape(-1, 3)
    # surimpressions écartées partout (contour rouge tracé SUR le polygone)
    d = np.linalg.norm(pix[:, None, :] - OVERLAYS[None, :, :], axis=2)
    net = d.min(axis=1) > 60
    dedans = pix[m.reshape(-1) & net]
    dehors = pix[~m.reshape(-1) & net]
    if len(dedans) < 8:
        return None
    f = _stats(dedans, "in") | _stats(dehors, "ctx")
    for k in ("bleuite_moy", "cyan_frac", "sat_moy", "lum_moy"):
        if f"in_{k}" in f and f"ctx_{k}" in f:
            f[f"d_{k}"] = f[f"in_{k}"] - f[f"ctx_{k}"]
    return f


FEATURES_GEO = ["surface_m2", "compacite", "solidite", "score_detection"]


def table_features(candidats: gpd.GeoDataFrame, vignettes_dir: Path,
                   cote_m: float = 60.0) -> pd.DataFrame:
    """Assemble la matrice de features (géométrie + couleur). Les candidats sans
    vignette gardent des NaN couleur (HistGradientBoosting les gère nativement)."""
    lignes = []
    for _, r in candidats.iterrows():
        d = {"id_detection": str(r["id_detection"]),
             "dalle": str(r.get("dalle", "?"))}
        for f in FEATURES_GEO:
            d[f] = float(r[f]) if f in r and pd.notna(r[f]) else np.nan
        pt = r.geometry.representative_point()
        coul = features_couleur(vignettes_dir / f"{r['id_detection']}.png",
                                r.geometry, pt.x, pt.y, cote_m)
        d.update(coul or {})
        lignes.append(d)
    return pd.DataFrame(lignes)


def labels_consensus(db: Path, produit: str) -> pd.Series:
    """Labels binaires depuis les votes de l'Atelier : majorité stricte
    oui→1 / non→0 ; égalités et « incertain » majoritaires sont ÉCARTÉS de
    l'entraînement (on n'apprend pas sur du doute)."""
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT id_item, reponse FROM votes WHERE produit=? "
                        "AND mode='existence'", (produit,)).fetchall()
    conn.close()
    votes: dict[str, list[str]] = {}
    for i, r in rows:
        votes.setdefault(i, []).append(r)
    lab = {}
    for i, vs in votes.items():
        c = Counter(vs).most_common()
        if len(c) > 1 and c[0][1] == c[1][1]:
            continue
        # Les votes multi-classes de l'Atelier sont des combos « jardin+oui » :
        # un composant « oui » suffit (la piscine est là, peu importe le reste).
        if "oui" in c[0][0].split("+"):
            lab[i] = 1
        elif c[0][0] == "non":
            lab[i] = 0
    return pd.Series(lab, name="y")


# ----------------------------------------------------------------- entraînement

def entrainer_evaluer(X: pd.DataFrame, y: np.ndarray, groupes: np.ndarray):
    """CV GroupKFold par dalle → probabilités out-of-fold HONNÊTES, puis modèle
    final entraîné sur tout + calibration isotonique. Retourne (modele, p_oof)."""
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import GroupKFold, cross_val_predict

    base = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08,
                                          max_leaf_nodes=31, random_state=0)
    cv = GroupKFold(n_splits=min(5, len(np.unique(groupes))))
    p_oof = cross_val_predict(base, X, y, cv=cv, groups=groupes,
                              method="predict_proba")[:, 1]
    # list(...) : un générateur de splits rendrait le modèle impossible à pickler
    final = CalibratedClassifierCV(base, method="isotonic",
                                   cv=list(cv.split(X, y, groupes)))
    final.fit(X, y)
    return final, p_oof


def choisir_seuils(y: np.ndarray, p: np.ndarray,
                   perte_max: float = PERTE_MAX_AUTO_NON,
                   precision_min: float = PRECISION_MIN_AUTO_OUI) -> dict:
    """Seuils depuis les probabilités out-of-fold (jamais depuis le train). Pure.

    t_bas  : plus GRAND seuil tel que la part de piscines sous le seuil <= perte_max.
    t_haut : plus PETIT seuil tel que la précision au-dessus >= precision_min."""
    # Tri croissant + sommes cumulées : perte(t) et précision(t) se lisent en
    # O(1) pour chaque seuil. On balaye TOUTE la grille (la précision cumulée
    # n'est pas monotone : s'arrêter au premier échec rate l'optimum).
    ordre = np.argsort(p)
    ps, ys = p[ordre], y[ordre]
    npool = max(1, int(y.sum()))
    cum_bas = np.cumsum(ys)                        # piscines perdues si t_bas = ps[i]
    ok_bas = np.where(cum_bas / npool <= perte_max)[0]
    t_bas = float(ps[ok_bas[-1]]) if len(ok_bas) else 0.0
    cum_haut = np.cumsum(ys[::-1])[::-1]           # piscines à p >= ps[i]
    n_haut = np.arange(len(ys), 0, -1)             # candidats à p >= ps[i]
    prec = cum_haut / n_haut
    ok_haut = np.where((prec >= precision_min) & (n_haut >= 10))[0]
    t_haut = float(ps[ok_haut[0]]) if len(ok_haut) else 1.0
    if t_haut <= t_bas:               # garde-fou : bandes dégénérées
        t_haut = min(1.0, t_bas + 0.05)
    auto_non, farm, auto_oui = p <= t_bas, (p > t_bas) & (p < t_haut), p >= t_haut
    return {
        "t_bas": t_bas, "t_haut": t_haut,
        "n": int(len(y)), "n_piscines": int(y.sum()),
        "auto_non": int(auto_non.sum()),
        "auto_oui": int(auto_oui.sum()),
        "farm": int(farm.sum()),
        "farm_frac": float(farm.mean()),
        "piscines_perdues_auto_non": int(y[auto_non].sum()),
        "precision_auto_oui": float(y[auto_oui].mean()) if auto_oui.sum() else None,
        "perte_max": perte_max, "precision_min": precision_min,
    }


def rapport_md(seuils: dict, auc: float, produit: str) -> str:
    s = seuils
    return f"""# Pré-tri {produit} — évaluation (out-of-fold, GroupKFold par dalle)

- **AUC : {auc:.3f}** sur {s['n']} candidats ({s['n_piscines']} piscines).
- Seuils : auto-non ≤ {s['t_bas']:.3f} < farm < {s['t_haut']:.3f} ≤ auto-oui.

| Bande | Candidats | Contenu mesuré |
|---|---|---|
| AUTO-NON | {s['auto_non']} | {s['piscines_perdues_auto_non']} piscine(s) perdue(s) (tolérance {s['perte_max']:.0%}) |
| FARM (humain) | {s['farm']} | **{s['farm_frac']:.0%} du volume initial seulement** |
| AUTO-OUI | {s['auto_oui']} | précision {('%.0f%%' % (100*s['precision_auto_oui'])) if s['precision_auto_oui'] is not None else '— (bande vide : objectif inatteignable, tout l évident reste au farm)'} (objectif ≥ {s['precision_min']:.0%}) |

Rappel de doctrine : l'auto-oui n'est PAS vendable sans l'étape adresse ; le
farm reste la source de vérité ; réentraîner à chaque commune terminée
(les labels s'accumulent, le modèle s'améliore, le farm rétrécit).
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["train", "apply"])
    ap.add_argument("--produit", default="piscines")
    ap.add_argument("--candidats", help="apply : parquet de candidats à scorer ; "
                                        "train : défaut Bouchemaine")
    ap.add_argument("--labels", help="train : CSV id_detection,label (0/1) au lieu "
                                     "du consensus Atelier — sert à entraîner sur "
                                     "des candidats re-générés (ex. CoSIA) dont les "
                                     "ids ne portent pas encore de votes")
    ap.add_argument("--vignettes-dir", help="dossier des vignettes PNG (défaut : "
                                            "data/interim/tri/vignettes)")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    interim = Path(cfg["paths"]["interim"])
    out_dir = interim / "pretri"
    out_dir.mkdir(parents=True, exist_ok=True)
    vignettes = (Path(args.vignettes_dir) if args.vignettes_dir else
                 {"piscines": interim / "tri" / "vignettes",
                  "terrasses": interim / "tri_terrasses" / "vignettes"}[args.produit])
    defaut = {"piscines": interim / "piscines_candidates_49_49035.parquet",
              "terrasses": interim / "terrasses_a_farmer_49_49035.parquet"}[args.produit]
    import joblib

    if args.action == "train":
        cand = gpd.read_parquet(Path(args.candidats) if args.candidats else defaut)
        X = table_features(cand, vignettes)
        if args.labels:
            lab = pd.read_csv(args.labels, dtype={"id_detection": str})
            y = lab.set_index("id_detection")["label"].astype(int)
            log.info("Labels fournis (%s) : %d exemples (%d positifs).",
                     args.labels, len(y), int(y.sum()))
        else:
            y = labels_consensus(interim.parent / "atelier" / "atelier.sqlite", args.produit)
        X = X[X["id_detection"].isin(y.index)].reset_index(drop=True)
        yy = y.loc[X["id_detection"]].to_numpy()
        cols = [c for c in X.columns if c not in ("id_detection", "dalle")]
        log.info("Entraînement : %d exemples, %d features, %d dalles.",
                 len(X), len(cols), X["dalle"].nunique())
        from sklearn.metrics import roc_auc_score
        modele, p_oof = entrainer_evaluer(X[cols], yy, X["dalle"].to_numpy())
        auc = roc_auc_score(yy, p_oof)
        seuils = choisir_seuils(yy, p_oof)
        joblib.dump({"modele": modele, "features": cols}, out_dir / f"{args.produit}_modele.joblib")
        (out_dir / f"{args.produit}_seuils.json").write_text(json.dumps(seuils, indent=1))
        rapport = rapport_md(seuils, auc, args.produit)
        (out_dir / f"{args.produit}_evaluation.md").write_text(rapport)
        print(rapport)
    else:
        if not args.candidats:
            raise SystemExit("apply : --candidats requis.")
        paquet = joblib.load(out_dir / f"{args.produit}_modele.joblib")
        seuils = json.loads((out_dir / f"{args.produit}_seuils.json").read_text())
        cand = gpd.read_parquet(args.candidats)
        X = table_features(cand, vignettes)
        p = paquet["modele"].predict_proba(X[paquet["features"]])[:, 1]
        cand["pretri_p"] = p
        cand["pretri_verdict"] = np.select(
            [p <= seuils["t_bas"], p >= seuils["t_haut"]],
            ["auto_non", "auto_oui"], default="farm")
        cand.to_parquet(args.candidats)
        log.info("Scoré : %s — %s", args.candidats,
                 cand["pretri_verdict"].value_counts().to_dict())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
