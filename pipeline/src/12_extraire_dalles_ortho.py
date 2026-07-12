"""Extraction ciblée des dalles BD ORTHO depuis les archives 7z multi-volumes.

Industrialise ce qui avait été fait À LA MAIN pour Bouchemaine (49035, tâche B2) :
au lieu d'extraire les 350 dalles (61 Go) puis de trier, on lit l'index `dalles.shp`
EMBARQUÉ dans l'archive, on l'intersecte avec une zone d'intérêt (une commune ou une
bbox), et on n'extrait QUE les dalles utiles (RVB + IRC), dans un dossier plat prêt
pour 15_detect_piscines.py (--ortho-dir rvb/ --irc-dir irc/).

Le chemin des archives n'est PAS codé en dur (le disque externe change de machine) :
il vient de --archives-dir ou de la clé `bdortho.archives_dir` de config.yaml.

Pièges gérés :
  - archives multi-volumes .7z.001..008 : on passe le .001, 7z recolle les volumes ;
  - le nommage IRC insère « -IRC- » avant « -E080 » (RVB non) : on ne reconstruit
    JAMAIS le nom, on utilise le nom réel lu dans l'index dalles.shp de chaque spectre ;
  - l'index préfixe les noms par « ./ » : on le retire.

Usage :
    python 12_extraire_dalles_ortho.py --commune 49035 \
        --archives-dir "/Volumes/NOIR 1/maps-bdortho/D049_2022" \
        --out-dir data/raw/bdortho/49035
    python 12_extraire_dalles_ortho.py --bbox 405000,6700000,410000,6705000 \
        --out-dir data/raw/bdortho/zone_test
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import tempfile
import time
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from common import load_config

log = logging.getLogger("extraire_dalles")

# Motifs d'identification des archives par spectre dans --archives-dir.
SPECTRES = {"rvb": "*RVB*.7z.001", "irc": "*IRC*.7z.001"}


# --------------------------------------------------------------------------
# Fonctions PURES (testables sans les archives réelles de 61 Go)
# --------------------------------------------------------------------------

def nom_dalle(nom_brut: str) -> str:
    """Nom de fichier propre d'une dalle depuis la colonne NOM de dalles.shp.

    L'index préfixe par « ./ » (ex. « ./49-2022-0405-6700-LA93-0M20-E080.jp2 »).
    On retire ce préfixe et tout dossier éventuel, sans jamais reconstruire le nom
    (le suffixe -IRC- diffère entre spectres → on garde le nom réel de l'index).
    """
    if nom_brut is None:
        raise ValueError("Nom de dalle vide dans l'index (colonne NOM manquante ?).")
    return Path(str(nom_brut).lstrip("./")).name


def aoi_depuis_bbox(xmin: float, ymin: float, xmax: float, ymax: float):
    """Zone d'intérêt rectangulaire (Lambert-93) depuis une bbox."""
    if not (xmax > xmin and ymax > ymin):
        raise ValueError(
            f"bbox invalide : attendu xmin<xmax et ymin<ymax, reçu "
            f"({xmin},{ymin},{xmax},{ymax})."
        )
    return box(xmin, ymin, xmax, ymax)


def aoi_depuis_commune(parcelles: gpd.GeoDataFrame, commune: str):
    """Union des géométries des parcelles d'une commune = AOI.

    parcelles : GeoDataFrame avec une colonne 'commune' (code INSEE, ex. '49035').
    Échoue bruyamment si la commune est absente.
    """
    if "commune" not in parcelles.columns:
        raise ValueError("parcelles : colonne 'commune' manquante.")
    sel = parcelles[parcelles["commune"] == commune]
    if sel.empty:
        raise ValueError(f"Commune {commune} introuvable dans les parcelles fournies.")
    return sel.geometry.union_all()


def selectionner_dalles(index: gpd.GeoDataFrame, aoi) -> list[str]:
    """Noms des dalles de l'index dont l'emprise intersecte l'AOI.

    index : GeoDataFrame de l'emprise des dalles, colonne 'NOM'. aoi : géométrie
    (commune ou bbox) dans le MÊME CRS que l'index (Lambert-93). Retourne la liste
    triée et dédoublonnée des noms de fichiers réels à extraire.
    """
    if "NOM" not in index.columns:
        raise ValueError("Index dalles : colonne 'NOM' manquante (dalles.shp inattendu).")
    touchees = index[index.geometry.intersects(aoi)]
    noms = sorted({nom_dalle(n) for n in touchees["NOM"]})
    return noms


# --------------------------------------------------------------------------
# Fonctions IO (nécessitent 7z et les archives)
# --------------------------------------------------------------------------

def trouver_archive(archives_dir: Path, spectre: str) -> Path:
    """Localise le premier volume (.7z.001) d'un spectre dans archives_dir."""
    motif = SPECTRES[spectre]
    matches = sorted(archives_dir.glob(motif))
    if not matches:
        raise SystemExit(
            f"Aucune archive {spectre.upper()} (motif {motif}) dans {archives_dir}."
        )
    if len(matches) > 1:
        raise SystemExit(
            f"Plusieurs archives {spectre.upper()} candidates dans {archives_dir} : "
            f"{[m.name for m in matches]} — lever l'ambiguïté."
        )
    return matches[0]


def extraire_index(archive_001: Path, dest_dir: Path) -> gpd.GeoDataFrame:
    """Extrait dalles.* de l'archive (motif -ir!*dalles.*) et lit le shapefile."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["7z", "e", "-y", f"-o{dest_dir}", str(archive_001), "-ir!*dalles.*"]
    _run_7z(cmd, "extraction de l'index dalles")
    shp = dest_dir / "dalles.shp"
    if not shp.exists():
        raise SystemExit(f"dalles.shp introuvable après extraction dans {dest_dir}.")
    return gpd.read_file(shp)


def extraire_dalles(archive_001: Path, noms: list[str], out_dir: Path) -> int:
    """Extrait les dalles nommées vers out_dir (dossier plat). Idempotent : saute
    celles déjà présentes. Retourne le nombre de dalles réellement extraites."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manquantes = [n for n in noms if not (out_dir / n).exists()]
    deja = len(noms) - len(manquantes)
    if deja:
        log.info("%d/%d dalle(s) déjà présente(s) dans %s, sautée(s).",
                 deja, len(noms), out_dir)
    if not manquantes:
        return 0
    cmd = ["7z", "e", "-y", f"-o{out_dir}", str(archive_001)]
    cmd += [f"-ir!{n}" for n in manquantes]
    _run_7z(cmd, f"extraction de {len(manquantes)} dalle(s)")
    absentes = [n for n in manquantes if not (out_dir / n).exists()]
    if absentes:
        raise SystemExit(
            f"7z n'a pas produit {len(absentes)} dalle(s) attendue(s) : "
            f"{absentes[:5]}… — nom absent de l'archive ?"
        )
    return len(manquantes)


def _run_7z(cmd: list[str], quoi: str) -> None:
    """Lance 7z, échoue bruyamment avec le stderr en cas d'erreur."""
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit(
            f"Échec 7z ({quoi}, code {res.returncode}) :\n"
            f"{res.stderr.strip() or res.stdout.strip()}"
        )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def resoudre_aoi(cfg: dict, commune: str | None, bbox: tuple | None):
    if bbox is not None:
        return aoi_depuis_bbox(*bbox), f"bbox {bbox}"
    interim = Path(cfg["paths"]["interim"])
    dept = cfg["dept"]
    parcelles = gpd.read_parquet(interim / f"parcelles_{dept}.parquet")
    return aoi_depuis_commune(parcelles, commune), f"commune {commune}"


def resoudre_archives_dir(cfg: dict, arg: str | None) -> Path:
    chemin = arg or cfg.get("bdortho", {}).get("archives_dir")
    if not chemin:
        raise SystemExit(
            "Chemin des archives BD ORTHO non fourni : passer --archives-dir ou "
            "renseigner bdortho.archives_dir dans config.yaml (disque externe, hors repo)."
        )
    p = Path(chemin)
    if not p.is_dir():
        raise SystemExit(f"--archives-dir : {p} n'existe pas ou n'est pas un dossier "
                         "(disque externe non monté ?).")
    return p


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--commune", help="code INSEE, ex. 49035 (AOI = union des parcelles)")
    grp.add_argument("--bbox", help="xmin,ymin,xmax,ymax en Lambert-93 (EPSG:2154)")
    p.add_argument("--archives-dir", help="dossier contenant les .7z.001 RVB et IRC "
                   "(sinon lu depuis config.yaml bdortho.archives_dir)")
    p.add_argument("--out-dir", required=True, help="dossier de sortie (sous-dossiers "
                   "rvb/ et irc/ créés automatiquement)")
    args = p.parse_args()

    cfg = load_config()

    bbox = None
    if args.bbox:
        try:
            bbox = tuple(float(x) for x in args.bbox.split(","))
        except ValueError:
            raise SystemExit("--bbox : attendu 4 nombres séparés par des virgules.")
        if len(bbox) != 4:
            raise SystemExit("--bbox : exactement 4 valeurs xmin,ymin,xmax,ymax.")

    archives_dir = resoudre_archives_dir(cfg, args.archives_dir)
    aoi, libelle = resoudre_aoi(cfg, args.commune, bbox)
    out_dir = Path(args.out_dir)
    log.info("AOI : %s | archives : %s | sortie : %s", libelle, archives_dir, out_dir)

    total = 0
    with tempfile.TemporaryDirectory(prefix="bdortho_index_") as tmp:
        for spectre in ("rvb", "irc"):
            archive = trouver_archive(archives_dir, spectre)
            index = extraire_index(archive, Path(tmp) / spectre)
            if index.crs is not None and cfg["crs_metric"] not in str(index.crs):
                aoi_spectre = gpd.GeoSeries([aoi], crs=cfg["crs_metric"]).to_crs(index.crs).iloc[0]
            else:
                aoi_spectre = aoi
            noms = selectionner_dalles(index, aoi_spectre)
            if not noms:
                raise SystemExit(
                    f"Aucune dalle {spectre.upper()} n'intersecte l'AOI ({libelle}) — "
                    "AOI hors du département ou CRS incohérent ?"
                )
            log.info("[%s] %d dalle(s) sélectionnée(s) sur %d dans l'index.",
                     spectre.upper(), len(noms), len(index))
            t0 = time.time()
            n = extraire_dalles(archive, noms, out_dir / spectre)
            log.info("[%s] %d dalle(s) extraite(s) en %.1f s.",
                     spectre.upper(), n, time.time() - t0)
            total += n

    log.info("Terminé. %d dalle(s) extraite(s) au total vers %s.", total, out_dir)


if __name__ == "__main__":
    main()
