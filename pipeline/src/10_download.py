"""Téléchargement des sources open data et conversion en GeoParquet.

Sources et justification des URLs : docs/02-DATA-SOURCES.md.
Sorties dans data/interim/ :
    parcelles_{dept}.parquet, batiments_cadastre_{dept}.parquet,
    ban_{dept}.parquet, bdtopo_batiment_{dept}.parquet,
    bdtopo_exclusions_{dept}.parquet, millesimes.yaml

La BD ORTHO n'est PAS téléchargée ici (volumineuse, par lots au moment de la
détection — voir docs/04-PIPELINE-PISCINES.md étape 1b).

Usage :
    python 10_download.py            # tout
    python 10_download.py --only ban # une source
"""
from __future__ import annotations

import argparse
import logging
import subprocess
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
import yaml

from common import ensure_dirs, load_config

log = logging.getLogger("download")

CADASTRE_URL = "https://cadastre.data.gouv.fr/data/etalab-cadastre/latest/geojson/departements/{dept}/cadastre-{dept}-{layer}.json.gz"
BAN_URL = "https://adresse.data.gouv.fr/data/ban/adresses/latest/csv/adresses-{dept}.csv.gz"
# BD TOPO : éditions trimestrielles datées ; le miroir opendatarchives expose un alias latest/.
BDTOPO_MIRROR_INDEX = "https://files.opendatarchives.fr/professionnels.ign.fr/bdtopo/latest/"


def fetch(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        log.info("Déjà présent : %s", dest.name)
        return dest
    log.info("Téléchargement %s", url)
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.rename(dest)
    return dest


def dl_cadastre(cfg: dict, raw: Path, interim: Path, millesimes: dict) -> None:
    dept = cfg["dept"]
    for layer, out_name in (("parcelles", f"parcelles_{dept}"), ("batiments", f"batiments_cadastre_{dept}")):
        src = fetch(CADASTRE_URL.format(dept=dept, layer=layer), raw / f"cadastre-{dept}-{layer}.json.gz")
        gdf = gpd.read_file(src)  # GDAL lit le .json.gz directement
        gdf = gdf.to_crs(cfg["crs_metric"])
        gdf.to_parquet(interim / f"{out_name}.parquet")
        log.info("%s : %d entités", out_name, len(gdf))
    millesimes["Cadastre (DGFiP/Etalab)"] = f"latest@{date.today().isoformat()}"


def dl_ban(cfg: dict, raw: Path, interim: Path, millesimes: dict) -> None:
    dept = cfg["dept"]
    src = fetch(BAN_URL.format(dept=dept), raw / f"adresses-{dept}.csv.gz")
    df = pd.read_csv(src, sep=";", dtype=str)
    df["x"] = pd.to_numeric(df["x"], errors="coerce")
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    # Adresses sans coordonnées : géométrie NaN = plantage silencieux des sjoin
    # en aval. On les écarte BRUYAMMENT ici.
    sans_xy = df["x"].isna() | df["y"].isna()
    if sans_xy.any():
        log.warning("BAN : %d adresse(s) sans coordonnées écartée(s) (%.2f %%).",
                    int(sans_xy.sum()), 100 * sans_xy.mean())
        df = df[~sans_xy]
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["x"], df["y"]), crs=cfg["crs_metric"])
    gdf = gdf.rename(columns={"id": "id_ban"})
    gdf.to_parquet(interim / f"ban_{dept}.parquet")
    log.info("BAN : %d adresses", len(gdf))
    millesimes["BAN"] = f"latest@{date.today().isoformat()}"


def dl_bdtopo(cfg: dict, raw: Path, interim: Path, millesimes: dict,
              bdtopo_url: str | None = None) -> None:
    """BD TOPO : archive 7z départementale (~1-2 Go). On extrait 3 couches utiles.

    L'URL exacte porte l'édition (ex. BDTOPO_3-5_TOUSTHEMES_GPKG_LAMB93_D049_2026-06-15).
    On scrape l'index du miroir pour trouver l'archive du département — si le miroir
    change, chercher l'édition courante sur geoservices.ign.fr/bdtopo et passer
    l'URL via --bdtopo-url.
    """
    dept = cfg["dept"]
    if bdtopo_url:
        name = bdtopo_url.rsplit("/", 1)[-1]
        archive = fetch(bdtopo_url, raw / name)
    else:
        idx = requests.get(BDTOPO_MIRROR_INDEX, timeout=120)
        idx.raise_for_status()
        import re
        pattern = rf"BDTOPO_[\d-]+_TOUSTHEMES_GPKG_LAMB93_D0?{dept}_[\d-]+\.7z"
        matches = sorted(set(re.findall(pattern, idx.text)))
        if not matches:
            raise SystemExit(
                f"Archive BD TOPO D{dept} introuvable sur {BDTOPO_MIRROR_INDEX} — "
                "récupérer l'URL sur geoservices.ign.fr/bdtopo et relancer avec --bdtopo-url."
            )
        name = matches[-1]
        archive = fetch(BDTOPO_MIRROR_INDEX + name, raw / name)
    millesimes["BD TOPO (IGN)"] = name.rsplit("_", 1)[-1].removesuffix(".7z")

    extract_dir = raw / name.removesuffix(".7z")
    if not extract_dir.exists():
        log.info("Extraction %s (long)…", name)
        subprocess.run(["7z", "x", "-y", f"-o{extract_dir}", str(archive)], check=True,
                       capture_output=True)
    gpkgs = list(extract_dir.rglob("*.gpkg"))
    if not gpkgs:
        raise SystemExit(f"Aucun GPKG trouvé sous {extract_dir}")
    gpkg = gpkgs[0]

    bat = gpd.read_file(gpkg, layer="batiment", columns=["cleabs", "usage_1", "geometry"])
    bat.to_crs(cfg["crs_metric"]).to_parquet(interim / f"bdtopo_batiment_{dept}.parquet")
    log.info("BD TOPO batiment : %d", len(bat))

    # Zones d'exclusion : équipements publics/collectifs (piscines publiques, campings,
    # hôtels, zones sportives) — un piscinier veut des particuliers.
    excl = []
    zai = gpd.read_file(gpkg, layer="zone_d_activite_ou_d_interet")
    excl.append(zai[zai["categorie"].isin(["Sport", "Culture et loisirs", "Hébergement"]) |
                    (zai.get("nature").astype(str).str.contains("Piscine|Camping|Village de vacances", na=False))])
    sport = gpd.read_file(gpkg, layer="terrain_de_sport")
    excl.append(sport)
    exclusions = gpd.GeoDataFrame(pd.concat(excl, ignore_index=True), crs=zai.crs)
    exclusions.to_crs(cfg["crs_metric"]).to_parquet(interim / f"bdtopo_exclusions_{dept}.parquet")
    log.info("Zones d'exclusion : %d", len(exclusions))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--only", choices=["cadastre", "ban", "bdtopo"])
    p.add_argument("--bdtopo-url", help="URL directe de l'archive 7z BD TOPO si le scraping du miroir échoue")
    args = p.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    raw, interim = Path(cfg["paths"]["raw"]), Path(cfg["paths"]["interim"])

    mfile = interim / "millesimes.yaml"
    millesimes = yaml.safe_load(mfile.read_text()) if mfile.exists() else {}

    steps = {
        "cadastre": dl_cadastre,
        "ban": dl_ban,
        "bdtopo": lambda *a: dl_bdtopo(*a, bdtopo_url=args.bdtopo_url),
    }
    for name, fn in steps.items():
        if args.only and name != args.only:
            continue
        fn(cfg, raw, interim, millesimes)
        mfile.write_text(yaml.safe_dump(millesimes, allow_unicode=True))
    log.info("Terminé. Millésimes : %s", millesimes)


if __name__ == "__main__":
    main()
