"""Export commercial : extrait territorialisé de la base qualifiée, prêt à livrer.

C'est le SEUL script autorisé à produire un fichier destiné à un client.
Il impose les garde-fous : filtre opt-out, filtre de confiance, mention de source,
tatouage acheteur, enregistrement dans le registre des ventes.

Usage :
    python 40_export_client.py --centre "47.4712,-0.5518" --rayon-km 30 \
        --acheteur "PISCINES DUPONT SARL" --produit piscines
    python 40_export_client.py --communes 49007,49099 --acheteur "..." --produit piscines
    python 40_export_client.py --dept --acheteur "..." --produit piscines

Entrée : data/final/piscines_qualifiees_{dept}.parquet (produit par 30_score_qualite.py)
Sorties dans data/exports/{acheteur_slug}_{date}/ :
    - {produit}_{zone}.csv          fichier livrable
    - README_LIVRAISON.txt          mentions de source, millésimes, taux de précision
    - notice_art14.txt              copie de la notice RGPD acheteur (docs/templates/)
Le PDF cartographique est généré séparément (voir 41_export_carte.py, à écrire).
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import re
import unicodedata
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd

from common import REPO_ROOT, apply_optout, ensure_dirs, load_config, source_attribution

log = logging.getLogger("export_client")

# Colonnes livrées au client — RIEN d'autre ne sort, quel que soit le contenu interne.
# Garde-fou minimisation (docs/03-LEGAL-RGPD.md §5) : si une colonne nominative
# apparaissait un jour dans la base interne par erreur, elle ne sortirait pas d'ici.
COLONNES_LIVREES = [
    "id_ban", "adresse", "code_postal", "commune", "code_insee",
    "lat", "lon", "surface_m2", "confiance",
]


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def tatouer(df: pd.DataFrame, acheteur: str) -> pd.DataFrame:
    """Empreinte de formatage déterministe propre à l'acheteur (anti-revente).

    Aucune donnée n'est faussée : on ne varie que des détails de représentation.
    Mécanisme documenté dans docs/06-QUALITE-VALIDATION.md §5. L'empreinte est
    reconstructible depuis le nom d'acheteur => réattribution d'un fichier fuité.
    """
    df = df.copy()
    seed = int(hashlib.sha256(acheteur.encode()).hexdigest(), 16)

    # 1. Tri secondaire dépendant de l'acheteur (le tri primaire reste commune/CP, lisible).
    df["_h"] = df["id_ban"].map(lambda x: hashlib.sha256(f"{seed}{x}".encode()).hexdigest())
    df = df.sort_values(["commune", "code_postal", "_h"]).drop(columns="_h")

    # 2. Précision des coordonnées : 6 décimales partout, 5 sur un sous-ensemble ~10 %
    #    sélectionné par hash(acheteur, id_ban). Écart max ~1 m, sans effet d'usage.
    def _marque(id_ban: str) -> bool:
        return int(hashlib.sha256(f"{seed}:{id_ban}".encode()).hexdigest(), 16) % 10 == 0

    marques = df["id_ban"].map(_marque)
    for col in ("lat", "lon"):
        df[col] = df[col].astype(float).round(6)
        df.loc[marques, col] = df.loc[marques, col].round(5)
    return df


def registre_vente(cfg: dict, acheteur: str, produit: str, zone: str, n: int, fichier: Path) -> None:
    """Registre des ventes (hors git) — requis pour exclusivités, propagation des
    oppositions aux acheteurs passés, et réattribution du tatouage."""
    reg = REPO_ROOT / "sales" / "registre.csv"
    reg.parent.mkdir(exist_ok=True)
    ligne = pd.DataFrame([{
        "date": date.today().isoformat(),
        "acheteur": acheteur,
        "produit": produit,
        "zone": zone,
        "nb_lignes": n,
        "fichier": str(fichier),
        "exclusivite": "",   # à remplir à la main si contrat d'exclusivité
    }])
    ligne.to_csv(reg, mode="a", header=not reg.exists(), index=False)
    log.info("Vente consignée dans %s", reg)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--produit", choices=["piscines", "terrasses"], required=True)
    p.add_argument("--acheteur", required=True, help="Raison sociale de l'acheteur")
    zone = p.add_mutually_exclusive_group(required=True)
    zone.add_argument("--centre", help='"lat,lon" du centre (ex. adresse de l\'entreprise cliente)')
    zone.add_argument("--communes", help="codes INSEE séparés par des virgules")
    zone.add_argument("--dept", action="store_true", help="département entier")
    p.add_argument("--rayon-km", type=float, default=None)
    p.add_argument("--demo", action="store_true",
                   help="extrait de démonstration RDV : confiance HAUTE uniquement "
                        "(une adresse fausse sur cinq devant le prospect tue la réputation "
                        "locale — pre-mortem docs/10 §risque n°6)")
    args = p.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    rayon = args.rayon_km or cfg["export"]["rayon_defaut_km"]

    base = Path(cfg["paths"]["final"]) / f"{args.produit}_qualifiees_{cfg['dept']}.parquet"
    if not base.exists():
        raise SystemExit(
            f"Base introuvable : {base}\n"
            "Lancer d'abord le pipeline (voir docs/04-PIPELINE-PISCINES.md) "
            "et la validation qualité (docs/06-QUALITE-VALIDATION.md)."
        )
    gdf = gpd.read_parquet(base)
    log.info("Base chargée : %d lignes.", len(gdf))

    # --- Garde-fous, dans l'ordre ---
    if args.demo:
        gdf = gdf[gdf["confiance"] == "haute"]
        log.info("Mode DÉMO : confiance haute uniquement (%d lignes).", len(gdf))
    else:
        gdf = gdf[gdf["confiance"].isin(cfg["export"]["confiances_vendues"])]
    gdf = apply_optout(gdf, cfg, log)

    # --- Découpe territoriale ---
    if args.centre:
        lat, lon = (float(x) for x in args.centre.split(","))
        centre = gpd.GeoSeries.from_xy([lon], [lat], crs=cfg["crs_output"]).to_crs(cfg["crs_metric"])[0]
        gdf_m = gdf.to_crs(cfg["crs_metric"])
        gdf = gdf[gdf_m.geometry.distance(centre) <= rayon * 1000]
        zone_label = f"rayon-{rayon:g}km-{lat:.4f}-{lon:.4f}"
    elif args.communes:
        codes = [c.strip() for c in args.communes.split(",")]
        gdf = gdf[gdf["code_insee"].isin(codes)]
        zone_label = "communes-" + "-".join(codes)
    else:
        zone_label = f"dept-{cfg['dept']}"

    if gdf.empty:
        raise SystemExit("0 ligne dans la zone demandée — vérifier le centre/rayon.")
    log.info("Zone %s : %d lignes livrables.", zone_label, len(gdf))

    # --- Livrable ---
    df = pd.DataFrame(gdf.drop(columns="geometry"))
    df["lat"] = gdf.to_crs(cfg["crs_output"]).geometry.y
    df["lon"] = gdf.to_crs(cfg["crs_output"]).geometry.x
    manquantes = [c for c in COLONNES_LIVREES if c not in df.columns]
    if manquantes:
        raise SystemExit(f"Colonnes attendues absentes de la base : {manquantes}")
    df = tatouer(df[COLONNES_LIVREES], args.acheteur)

    prefixe_demo = "DEMO-" if args.demo else ""
    out_dir = Path(cfg["paths"]["exports"]) / f"{prefixe_demo}{slugify(args.acheteur)}_{date.today().isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"{args.produit}_{zone_label}.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")  # BOM : ouverture propre dans Excel

    # Millésimes : écrits par les scripts amont dans data/interim/millesimes.yaml.
    import yaml
    mfile = Path(cfg["paths"]["interim"]) / "millesimes.yaml"
    millesimes = yaml.safe_load(mfile.read_text()) if mfile.exists() else {"ATTENTION millésimes non renseignés": "?"}

    (out_dir / "README_LIVRAISON.txt").write_text(
        f"Livraison : {args.produit} — {zone_label}\n"
        f"Acheteur : {args.acheteur}\n"
        f"Nombre d'adresses : {len(df)}\n"
        f"{source_attribution(millesimes)}\n\n"
        "Ce fichier est concédé sous licence d'utilisation (voir contrat) : usage limité à la\n"
        "prospection par courrier postal et en personne ; email/SMS/appels automatisés interdits ;\n"
        "revente et partage interdits. Joindre la notice d'information (notice_art14.txt) au\n"
        "premier courrier adressé à chaque destinataire.\n",
        encoding="utf-8",
    )
    notice = REPO_ROOT / "docs" / "templates" / "notice_art14.txt"
    if notice.exists():
        (out_dir / "notice_art14.txt").write_text(notice.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        log.warning("docs/templates/notice_art14.txt absent — À CRÉER avant toute livraison réelle (obligation légale).")

    registre_vente(cfg, f"{prefixe_demo}{args.acheteur}", args.produit, zone_label, len(df), out_csv)
    log.info("Export prêt : %s", out_dir)


if __name__ == "__main__":
    main()
