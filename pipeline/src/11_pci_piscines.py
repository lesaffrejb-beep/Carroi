"""Piscines cadastrées (PCI Édigéo, symbole SYM=65) par commune.

Industrialisation de l'extraction ad hoc A3bis (roadmap `08` § « PCI SYM=65 pour
les 28 communes ALM »). Le Plan Cadastral Informatisé de la DGFiP, diffusé en
Édigéo par cadastre.data.gouv.fr (Licence Ouverte), porte dans sa couche des
« topos surfaciques » un symbole 65 = piscine. C'est une source de candidats
GRATUITE, légale et indépendante de CoSIA : 86,1 % des SYM=65 de Bouchemaine ont
une piscine OSM à moins de 5 m, et 8 SYM=65 y sont hors OSM et hors détection.

Sortie, une par commune, au schéma EXACT des parquets A3bis :
    data/interim/piscines_pci_sym65_{INSEE}.parquet  →  SYM, feuille, geometry
    (Lambert-93 EPSG:2154 — le PCI est nativement en L93 sur la métropole)
consommée telle quelle par `24_candidats_cosia.charger_pci_commune`.

Arborescence de la source (vérifiée le 2026-08-07) :
    …/dgfip-pci-vecteur/latest/edigeo/feuilles/{dept}/{INSEE}/edigeo-{feuille}.tar.bz2
`latest` redirige vers le millésime courant (2026-06-01 au 2026-08-07) ; l'index
HTML du dossier communal liste les archives — il n'y a PAS de convention de
nommage devinable (les sections varient d'une commune à l'autre), donc on parse
l'index. Une commune absente de la source rend un index vide (HTTP 200, 0 lien) :
c'est un warning, pas un crash — les autres communes continuent.

Pièges gérés :
  - une feuille sans couche `TSURF_id` (légitime : 2 feuilles de 49308) ;
  - une feuille sans aucun SYM=65 (la majorité des feuilles rurales) ;
  - une commune sans aucune piscine cadastrée → parquet VIDE au bon schéma,
    jamais d'exception (l'aval sait lire un parquet vide) ;
  - le CRS déclaré par le driver Édigéo est un WKT « IGNF » équivalent mais non
    identifié EPSG:2154 → on le force au CRS métrique du config.

Usage :
    python 11_pci_piscines.py --commune 49035
    python 11_pci_piscines.py --communes 49035,49308 --force
    python 11_pci_piscines.py --communes-alm          # les 29 communes d'ALM
"""
from __future__ import annotations

import argparse
import importlib
import logging
import re
import tarfile
import tempfile
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

from common import load_config

log = logging.getLogger("pci_piscines")

# Liste ALM : une seule définition dans le repo (24_candidats_cosia), importée.
COMMUNES_ALM = importlib.import_module("24_candidats_cosia").COMMUNES_ALM

BASE_URL = "https://cadastre.data.gouv.fr/data/dgfip-pci-vecteur/latest/edigeo/feuilles"
COUCHE_TSURF = "TSURF_id"
SYM_PISCINE = "65"
COLONNES = ["SYM", "feuille", "geometry"]

RE_ARCHIVE = re.compile(r"edigeo-[A-Za-z0-9_]+\.tar\.bz2")

PAUSE_S = 0.4          # politesse : ~2,5 req/s max vers cadastre.data.gouv.fr
RETRIES = 3
TIMEOUT_S = 120
UA = "maps-pipeline/11_pci_piscines (open data, contact via le dépôt)"


# --------------------------------------------------------------------------
# Fonctions pures / testables (aucun réseau, aucun disque)
# --------------------------------------------------------------------------

def url_index_commune(dept: str, insee: str) -> str:
    """URL de l'index HTML listant les feuilles Édigéo d'une commune."""
    return f"{BASE_URL}/{dept}/{insee}/"


def url_feuille(dept: str, insee: str, archive: str) -> str:
    """URL d'une archive de feuille (`archive` = nom de fichier tar.bz2)."""
    return f"{BASE_URL}/{dept}/{insee}/{archive}"


def parser_index_feuilles(html: str) -> list[str]:
    """Noms des archives `edigeo-*.tar.bz2` d'un index HTML de commune.

    L'index nginx répète le nom dans le href ET dans le texte du lien → on
    déduplique. Retour trié pour rendre le traitement déterministe (et donc les
    logs comparables d'un run à l'autre). Liste vide = commune absente de la
    source (l'appelant décide quoi en faire ; ici : warning explicite).
    """
    return sorted(set(RE_ARCHIVE.findall(html)))


def code_feuille(archive: str) -> str:
    """`edigeo-490350000A03.tar.bz2` → `490350000A03` (identifiant de feuille)."""
    return archive.removeprefix("edigeo-").removesuffix(".tar.bz2")


def filtrer_sym65(gdf: gpd.GeoDataFrame, feuille: str) -> gpd.GeoDataFrame:
    """Topos surfaciques de symbole 65 (piscines) d'une feuille, au schéma final.

    Échoue bruyamment si la couche n'a pas d'attribut SYM : ce serait un
    changement de format de la source, pas un cas métier — mieux vaut le voir.
    """
    if "SYM" not in gdf.columns:
        raise ValueError(
            f"{feuille} : couche {COUCHE_TSURF} sans attribut SYM — format de "
            "la source modifié ? (on refuse de deviner)")
    out = gdf.loc[gdf["SYM"].astype(str) == SYM_PISCINE].copy()
    out["SYM"] = out["SYM"].astype(str)
    out["feuille"] = feuille
    return out[COLONNES]


def parquet_vide(crs: str) -> gpd.GeoDataFrame:
    """Schéma de sortie sans aucune ligne (commune sans piscine cadastrée)."""
    vide = gpd.GeoDataFrame(
        {"SYM": pd.Series(dtype=str), "feuille": pd.Series(dtype=str)},
        geometry=gpd.GeoSeries([], crs=crs))
    return vide[COLONNES]


# --------------------------------------------------------------------------
# Réseau
# --------------------------------------------------------------------------

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    return s


def _get(session: requests.Session, url: str, stream: bool = False):
    """GET avec retries et back-off. Échoue bruyamment après RETRIES tentatives."""
    derniere = None
    for tentative in range(1, RETRIES + 1):
        try:
            r = session.get(url, timeout=TIMEOUT_S, stream=stream)
            r.raise_for_status()
            return r
        except requests.RequestException as e:  # réseau ou HTTP non-2xx
            derniere = e
            if tentative < RETRIES:
                attente = PAUSE_S * 2 ** tentative
                log.warning("Échec %s (tentative %d/%d) : %s — retry dans %.1fs",
                            url, tentative, RETRIES, e, attente)
                time.sleep(attente)
    raise RuntimeError(f"Téléchargement impossible après {RETRIES} tentatives : {url}") from derniere


def lister_feuilles(session: requests.Session, dept: str, insee: str) -> list[str]:
    """Archives de feuilles publiées pour la commune (via l'index HTML)."""
    r = _get(session, url_index_commune(dept, insee))
    time.sleep(PAUSE_S)
    return parser_index_feuilles(r.text)


def telecharger_feuille(session: requests.Session, dept: str, insee: str,
                        archive: str, cache_dir: Path) -> Path:
    """Archive en cache local ; ne retélécharge jamais un fichier déjà complet."""
    dest = cache_dir / archive
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    url = url_feuille(dept, insee, archive)
    log.info("Téléchargement %s", url)
    r = _get(session, url, stream=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(1 << 18):
            f.write(chunk)
    tmp.rename(dest)
    time.sleep(PAUSE_S)
    return dest


# --------------------------------------------------------------------------
# Lecture Édigéo
# --------------------------------------------------------------------------

def lire_tsurf(archive: Path) -> gpd.GeoDataFrame | None:
    """Couche `TSURF_id` d'une archive Édigéo, via le driver GDAL natif.

    L'archive contient un jeu de fichiers (.THF, .VEC, .DIC…) : GDAL s'ouvre sur
    le .THF. Retourne None si la feuille n'a pas de couche TSURF (cas légitime,
    ex. 2 feuilles de 49308) — l'appelant loggue et continue.
    """
    import pyogrio

    with tempfile.TemporaryDirectory(prefix="edigeo_") as tmp:
        dossier = Path(tmp)
        with tarfile.open(archive, "r:bz2") as tar:
            # filter="data" : refuse les chemins absolus / ".." d'une archive
            # distante (dispo Python ≥ 3.12 ; sinon comportement historique).
            if hasattr(tarfile, "data_filter"):
                tar.extractall(dossier, filter="data")
            else:  # pragma: no cover - Python < 3.12
                tar.extractall(dossier)
        thfs = sorted(dossier.glob("*.THF"))
        if not thfs:
            raise ValueError(f"{archive.name} : aucun fichier .THF dans l'archive.")
        couches = {nom for nom, _ in pyogrio.list_layers(thfs[0])}
        if COUCHE_TSURF not in couches:
            return None
        return pyogrio.read_dataframe(thfs[0], layer=COUCHE_TSURF)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def extraire_commune(cfg: dict, insee: str, session: requests.Session,
                     dept: str, out_dir: Path | None = None,
                     force: bool = False) -> Path | None:
    """Télécharge (ou réutilise) les feuilles d'une commune et écrit son parquet.

    Retourne le chemin du parquet, ou None si la commune est absente de la
    source (warning) ou si le parquet existe déjà et que --force n'est pas posé.
    """
    interim = Path(cfg["paths"]["interim"])
    dest_dir = out_dir or interim
    out = dest_dir / f"piscines_pci_sym65_{insee}.parquet"
    if out.exists() and not force:
        log.info("[%s] %s existe déjà — passé (--force pour régénérer).", insee, out)
        return None

    feuilles = lister_feuilles(session, dept, insee)
    if not feuilles:
        log.warning("[%s] aucune feuille Édigéo publiée à %s — commune absente de "
                    "la source (fusionnée ? code INSEE périmé ?), on continue.",
                    insee, url_index_commune(dept, insee))
        return None

    cache_dir = Path(cfg["paths"]["raw"]) / "edigeo_pci" / insee
    cache_dir.mkdir(parents=True, exist_ok=True)
    log.info("[%s] %d feuille(s) Édigéo à traiter.", insee, len(feuilles))

    morceaux: list[gpd.GeoDataFrame] = []
    sans_tsurf = 0
    for archive in feuilles:
        chemin = telecharger_feuille(session, dept, insee, archive, cache_dir)
        tsurf = lire_tsurf(chemin)
        if tsurf is None:
            sans_tsurf += 1
            log.info("[%s] %s : pas de couche %s (feuille sans topo surfacique).",
                     insee, archive, COUCHE_TSURF)
            continue
        piscines = filtrer_sym65(tsurf, archive)
        if not piscines.empty:
            morceaux.append(piscines)

    crs = cfg["crs_metric"]
    if morceaux:
        gdf = gpd.GeoDataFrame(pd.concat(morceaux, ignore_index=True),
                               geometry="geometry")
        # Le driver Édigéo déclare un WKT « RGF93 Lambert 93 » (IGNF) équivalent
        # mais non identifié EPSG:2154 : on force, sans reprojeter.
        gdf = gdf.set_crs(crs, allow_override=True)[COLONNES]
    else:
        log.warning("[%s] aucune piscine cadastrée (SYM=%s) sur %d feuille(s) — "
                    "parquet vide écrit.", insee, SYM_PISCINE, len(feuilles))
        gdf = parquet_vide(crs)

    dest_dir.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(out)
    log.info("[%s] %d piscine(s) SYM=%s sur %d feuille(s) (%d sans %s) → %s",
             insee, len(gdf), SYM_PISCINE, len(feuilles), sans_tsurf,
             COUCHE_TSURF, out)
    return out


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--commune", help="code INSEE d'une commune")
    grp.add_argument("--communes", help="codes INSEE séparés par des virgules")
    grp.add_argument("--communes-alm", action="store_true",
                     help="les 29 communes d'Angers Loire Métropole")
    p.add_argument("--dept", help="département de la source (défaut : celui du config)")
    p.add_argument("--out-dir", help="dossier de sortie (défaut : data/interim)")
    p.add_argument("--force", action="store_true",
                   help="régénérer un parquet déjà présent")
    args = p.parse_args()

    cfg = load_config()
    dept = args.dept or cfg["dept"]
    communes = (COMMUNES_ALM if args.communes_alm
                else [c.strip() for c in args.communes.split(",")] if args.communes
                else [args.commune])
    out_dir = Path(args.out_dir) if args.out_dir else None

    session = _session()
    ecrits, absentes = 0, []
    for insee in communes:
        chemin = extraire_commune(cfg, insee, session, dept,
                                  out_dir=out_dir, force=args.force)
        if chemin is not None:
            ecrits += 1
        elif not (out_dir or Path(cfg["paths"]["interim"])).joinpath(
                f"piscines_pci_sym65_{insee}.parquet").exists():
            absentes.append(insee)
    log.info("Terminé : %d parquet(s) écrit(s) sur %d commune(s) demandée(s).",
             ecrits, len(communes))
    if absentes:
        log.warning("Communes sans données Édigéo : %s", ", ".join(absentes))


if __name__ == "__main__":
    main()
