"""Candidats piscines depuis CoSIA (GPKG IGN, local) ∪ cadastre PCI SYM=65.

Bascule décidée (roadmap tâche 12, `docs/15` §4, `docs/16` §8) : CoSIA — la
couverture du sol par IA de l'IGN, classe « Piscine », Licence Ouverte —
remplace le détecteur HSV v1 comme SOURCE de candidats (rappel mesuré 88,1 %
vs 53 % à Bouchemaine). Le PCI SYM=65 (piscines cadastrées) s'y ajoute quand
son parquet communal existe : corroboration (98 % de oui mesurés) + rattrapage
des piscines que CoSIA rate.

Ce module ne détecte rien : il découpe, fusionne, qualifie et écrit des
candidats au CONTRAT de couche 1 (contrat.py), un parquet PAR commune —
`piscines_candidates_{dept}_{commune}.parquet` — prêt pour 16 (vignettes),
22 (pré-tri) et l'Atelier.

Convention score_detection (feature du pré-tri, re-calibrée par lui) :
  1.0 = CoSIA corroboré PCI · 0.9 = CoSIA seul · 0.8 = PCI seul.

Pièges gérés :
  - une piscine coupée entre deux blocs GPKG 10 km = deux polygones → union
    des géométries qui se touchent avant l'explode ;
  - CoSIA fusionne parfois deux piscines voisines / englobe la plage → les
    filtres surface min/max du config s'appliquent APRÈS l'union ;
  - chemin du disque externe jamais codé en dur : --cosia-dir ou
    `cosia.gpkg_dir` de config.yaml (même logique que 12_extraire_dalles).

Usage :
    python 24_candidats_cosia.py --commune 49015 --cosia-dir "/Volumes/NOIR 1/…"
    python 24_candidats_cosia.py --communes-alm --cosia-dir "…"   # les 29 d'ALM
"""
from __future__ import annotations

import argparse
import logging
import math
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

from common import load_config
from contrat import ids_stables, valider_couche1

log = logging.getLogger("candidats_cosia")

# Angers Loire Métropole — 29 communes, source geo.api.gouv.fr EPCI 244900015
# (relevé 2026-08-06). Bouchemaine (49035) incluse : elle sert de commune
# étalon (vérité humaine complète) pour mesurer CoSIA et entraîner le pré-tri.
COMMUNES_ALM = [
    "49007",  # Angers
    "49307",  # Loire-Authion
    "49353",  # Trélazé
    "49015",  # Avrillé
    "49246",  # Les Ponts-de-Cé
    "49267",  # Saint-Barthélemy-d'Anjou
    "49323",  # Verrières-en-Anjou
    "49214",  # Montreuil-Juigné
    "49035",  # Bouchemaine
    "49200",  # Longuenée-en-Anjou
    "49223",  # Mûrs-Erigné
    "49020",  # Beaucouzé
    "49377",  # Rives-du-Loir-en-Anjou
    "49129",  # Écouflant
    "49298",  # Saint-Léger-de-Linières
    "49278",  # Sainte-Gemmes-sur-Loire
    "49048",  # Briollay
    "49294",  # Saint-Lambert-la-Potherie
    "49241",  # Le Plessis-Grammoire
    "49055",  # Cantenay-Épinard
    "49135",  # Feneu
    "49271",  # Saint-Clément-de-la-Place
    "49306",  # Saint-Martin-du-Fouilloux
    "49339",  # Soulaire-et-Bourg
    "49329",  # Savennières
    "49338",  # Soulaines-sur-Aubance
    "49326",  # Sarrigné
    "49130",  # Écuillé
    "49028",  # Béhuard
]

RE_BLOC = re.compile(r"D0\d{2}_\d{4}_(\d{3})_(\d{4})_vecto\.gpkg$")
# Tuilage CoSIA : blocs de 10 km. ⚠ Le Y du nom est le coin NORD-ouest (haut),
# pas le sud : D049_2022_420_6710 couvre x 420-430 km, y 6700-6710 km (vérifié
# sur les bounds réels des GPKG le 2026-08-06 — l'hypothèse « coin SO » coûtait
# 58 points de rappel en silence).
COTE_BLOC_M = 10_000
SEUIL_CORROBORATION_M = 5.0   # même seuil que 16_tri_visuel.corrobore_cadastre

SCORES = {"cosia+pci": 1.0, "cosia": 0.9, "pci_sym65": 0.8}


# --------------------------------------------------------------------------
# Fonctions pures / testables
# --------------------------------------------------------------------------

def bbox_bloc(nom_fichier: str) -> tuple[float, float, float, float] | None:
    """Emprise L93 d'un bloc CoSIA depuis son NOM (coin sud-ouest en km)."""
    m = RE_BLOC.search(nom_fichier)
    if not m:
        return None
    x, y_nord = int(m.group(1)) * 1000, int(m.group(2)) * 1000
    return (x, y_nord - COTE_BLOC_M, x + COTE_BLOC_M, y_nord)


def blocs_pour_aoi(cosia_dir: Path, aoi) -> list[Path]:
    """Blocs GPKG dont l'emprise 10 km intersecte l'AOI. Échoue bruyamment si
    le dossier ne contient aucun bloc reconnaissable (disque absent, mauvais
    chemin) — jamais un résultat vide silencieux."""
    from shapely.geometry import box
    tous = sorted(cosia_dir.glob("*_vecto.gpkg"))
    if not tous:
        raise FileNotFoundError(
            f"Aucun bloc CoSIA (*_vecto.gpkg) dans {cosia_dir} — disque NOIR "
            "branché ? archive extraite ?")
    keep = []
    for p in tous:
        bb = bbox_bloc(p.name)
        if bb and box(*bb).intersects(aoi):
            keep.append(p)
    return keep


def geometries_saines(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Ne garde que des (Multi)Polygones valides et non vides."""
    g = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    g["geometry"] = g.geometry.make_valid()
    g = g[g.geometry.geom_type.isin(("Polygon", "MultiPolygon"))]
    return g.explode(index_parts=False, ignore_index=True)


def fusionner_bords_de_blocs(gdf: gpd.GeoDataFrame,
                             soudure_m: float = 1.5) -> gpd.GeoDataFrame:
    """Une piscine coupée par le tuilage 10 km OU fragmentée par la
    vectorisation CoSIA (branche d'arbre, margelle) = plusieurs polygones →
    soudure dilate-érode de `soudure_m` puis explode. Conserve pour chaque
    polygone final le bloc source (colonne `dalle`, groupe spatial du pré-tri).
    Mesuré à Bouchemaine (2026-08-06) : soudure 1,5 m + surface_min 3 m² =
    rappel 98,4 % vs vérité humaine (91,1 % sans)."""
    from shapely.ops import unary_union
    if soudure_m > 0:
        union = unary_union(list(gdf.geometry.buffer(soudure_m))).buffer(-soudure_m)
    else:
        union = unary_union(list(gdf.geometry))
    parts = gpd.GeoDataFrame(geometry=[union], crs=gdf.crs).explode(
        index_parts=False, ignore_index=True)
    # ré-attribue le bloc source par le point représentatif
    sidx = gdf.sindex
    dalles = []
    for pt in parts.geometry.representative_point():
        hits = sidx.query(pt, predicate="intersects")
        dalles.append(gdf.iloc[hits[0]]["dalle"] if len(hits) else "?")
    parts["dalle"] = dalles
    return parts


def attributs_forme(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """surface_m2, compacite (4πA/P²), solidite (A/aire convexe) — les mêmes
    features de forme que le détecteur v1, attendues par le pré-tri 22."""
    a = gdf.geometry.area
    p = gdf.geometry.length
    gdf["surface_m2"] = a
    gdf["compacite"] = (4 * math.pi * a / (p * p)).where(p > 0, 0.0)
    gdf["solidite"] = (a / gdf.geometry.convex_hull.area).clip(upper=1.0)
    return gdf


def charger_cosia_commune(cosia_dir: Path, aoi, crs: str) -> gpd.GeoDataFrame:
    """Polygones classe Piscine des blocs intersectant l'AOI, découpés à l'AOI."""
    import pyogrio
    frames = []
    for bloc in blocs_pour_aoi(cosia_dir, aoi):
        gdf = pyogrio.read_dataframe(
            bloc, where="classe = 'Piscine'", bbox=tuple(aoi.bounds))
        if gdf.empty:
            continue
        gdf = gdf.to_crs(crs) if gdf.crs else gdf.set_crs(crs)
        gdf["dalle"] = bloc.stem
        frames.append(gdf[["geometry", "dalle"]])
    if not frames:
        return gpd.GeoDataFrame(columns=["geometry", "dalle"], crs=crs)
    brut = geometries_saines(pd.concat(frames, ignore_index=True))
    brut = brut[brut.geometry.intersects(aoi)]
    if brut.empty:
        return gpd.GeoDataFrame(columns=["geometry", "dalle"], crs=crs)
    return fusionner_bords_de_blocs(brut)


def charger_pci_commune(interim: Path, commune: str) -> gpd.GeoDataFrame | None:
    """Piscines cadastrées PCI SYM=65 de la commune, si le parquet existe
    (extraction A3bis — pas encore industrialisée pour toutes les communes)."""
    p = interim / f"piscines_pci_sym65_{commune}.parquet"
    if not p.exists():
        return None
    pci = gpd.read_parquet(p)
    pci = pci[pci["SYM"].astype(str) == "65"]
    return geometries_saines(pci) if not pci.empty else None


def construire_candidats(cosia: gpd.GeoDataFrame, pci: gpd.GeoDataFrame | None,
                         s_min: float, s_max: float) -> gpd.GeoDataFrame:
    """Fusion CoSIA ∪ PCI → candidats qualifiés (méthode + score).

    - CoSIA corroboré par un symbole PCI à < 5 m → `cosia+pci` (score 1.0) ;
    - CoSIA seul → `cosia` (0.9) ;
    - symbole PCI sans CoSIA à < 5 m → candidat `pci_sym65` (0.8) — le
      rattrapage des piscines que CoSIA n'a pas vues (souvent couvertes).
    Les filtres surface s'appliquent à TOUTES les sources."""
    cosia = cosia.copy()
    cosia["methode"] = "cosia"
    if pci is not None and not pci.empty:
        sidx = cosia.sindex if not cosia.empty else None
        orphelins = []
        for geom in pci.geometry:
            proches = (sidx.query(geom.buffer(SEUIL_CORROBORATION_M),
                                  predicate="intersects")
                       if sidx is not None else [])
            if len(proches):
                cosia.iloc[list(proches),
                           cosia.columns.get_loc("methode")] = "cosia+pci"
            else:
                orphelins.append(geom)
        if orphelins:
            extra = gpd.GeoDataFrame(
                {"methode": ["pci_sym65"] * len(orphelins),
                 "dalle": ["pci"] * len(orphelins)},
                geometry=orphelins, crs=cosia.crs)
            cosia = pd.concat([cosia, extra], ignore_index=True)
    cand = attributs_forme(cosia)
    avant = len(cand)
    cand = cand[(cand["surface_m2"] >= s_min) & (cand["surface_m2"] <= s_max)]
    log.info("Filtre surface [%s-%s m²] : %d → %d candidats.",
             s_min, s_max, avant, len(cand))
    cand = cand.reset_index(drop=True)
    cand["score_detection"] = cand["methode"].map(SCORES)
    return cand


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def aoi_commune(parcelles: gpd.GeoDataFrame, commune: str):
    """Union des parcelles de la commune = AOI. Même contrat que
    12_extraire_dalles_ortho.aoi_depuis_commune, mais répare d'abord les
    géométries invalides (Loire-Authion en contient : TopologyException)."""
    sel = parcelles[parcelles["commune"] == commune]
    if sel.empty:
        raise ValueError(f"Commune {commune} introuvable dans les parcelles.")
    return sel.geometry.make_valid().union_all()


def generer_commune(cfg: dict, cosia_dir: Path, commune: str,
                    parcelles: gpd.GeoDataFrame,
                    out_dir: Path | None = None, force: bool = False) -> Path:
    interim = Path(cfg["paths"]["interim"])
    dest = out_dir or interim
    out = dest / f"piscines_candidates_{cfg['dept']}_{commune}.parquet"
    if out.exists() and not force:
        # Un parquet de candidats existant peut porter des VOTES (ids liés) :
        # l'écraser invaliderait le farm déjà fait (cas Bouchemaine v1).
        raise SystemExit(
            f"{out} existe déjà — il peut porter des votes. Relancer avec "
            "--force pour écraser, ou --out-dir pour écrire ailleurs.")
    aoi = aoi_commune(parcelles, commune)
    cosia = charger_cosia_commune(cosia_dir, aoi, cfg["crs_metric"])
    pci = charger_pci_commune(interim, commune)
    log.info("[%s] CoSIA : %d polygones piscine · PCI SYM=65 : %s.",
             commune, len(cosia), len(pci) if pci is not None else "absent")
    ccfg = cfg.get("cosia", {})
    cand = construire_candidats(
        cosia, pci,
        # Seuil bas PROPRE à CoSIA (3 m², pas les 8 m² du détecteur v1) : une
        # piscine couverte dont CoSIA ne voit qu'un coin fait 2-6 m² — la
        # couper coûtait 7 points de rappel (mesure Bouchemaine 2026-08-06).
        float(ccfg.get("surface_min_m2", 3.0)),
        float(cfg["piscines"]["surface_max_m2"]))
    if cand.empty:
        log.warning("[%s] aucun candidat — commune sans piscine CoSIA ?", commune)
    cand["commune"] = commune
    cand["id_detection"] = ids_stables(cand, "pisc")
    cand = cand.set_crs(cfg["crs_metric"], allow_override=True)
    if not cand.empty:
        valider_couche1(cand, crs_attendu=cfg["crs_metric"])
    dest.mkdir(parents=True, exist_ok=True)
    cand.to_parquet(out)
    log.info("[%s] %d candidats → %s", commune, len(cand), out)
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--commune", help="code INSEE d'une commune")
    grp.add_argument("--communes", help="codes INSEE séparés par des virgules")
    grp.add_argument("--communes-alm", action="store_true",
                     help="les 29 communes d'Angers Loire Métropole")
    p.add_argument("--cosia-dir",
                   help="dossier des blocs GPKG CoSIA (sinon cosia.gpkg_dir du config)")
    p.add_argument("--out-dir", help="dossier de sortie (défaut : data/interim)")
    p.add_argument("--force", action="store_true",
                   help="écraser un parquet de candidats existant (danger : votes liés)")
    args = p.parse_args()

    cfg = load_config()
    cosia_dir = Path(args.cosia_dir or cfg.get("cosia", {}).get("gpkg_dir") or "")
    if not cosia_dir.name or not cosia_dir.exists():
        raise SystemExit(
            "Dossier CoSIA introuvable : passer --cosia-dir ou renseigner "
            "cosia.gpkg_dir dans config.yaml (disque NOIR branché ?).")
    communes = (COMMUNES_ALM if args.communes_alm
                else args.communes.split(",") if args.communes
                else [args.commune])
    interim = Path(cfg["paths"]["interim"])
    parcelles = gpd.read_parquet(interim / f"parcelles_{cfg['dept']}.parquet",
                                 columns=["commune", "geometry"])
    for c in communes:
        generer_commune(cfg, cosia_dir, c.strip(), parcelles,
                        out_dir=Path(args.out_dir) if args.out_dir else None,
                        force=args.force)


if __name__ == "__main__":
    main()
