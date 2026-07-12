#!/usr/bin/env python3
"""appliquer_decisions_recues.py — fusionner et appliquer les décisions de tri reçues.

Usage :
    .venv/bin/python handoff/appliquer_decisions_recues.py [chemin/candidats.parquet] [--force]

Ce que fait le script :
  1. Liste tous les CSV de handoff/decisions_recus/.
  2. EXCLUT ceux dont l'empreinte de planche (hash12 dans le NOM du fichier,
     motif decisions_*_{hash12}.csv) ne correspond pas au parquet de candidats
     courant : une planche périmée = un jugement invalide. Les anciens noms sans
     hash sont tolérés (warning). --force inclut tout.
  3. Concatène les CSV retenus en dédoublonnant par id_detection. En cas de
     conflit (même id décidé différemment), la décision du fichier le plus RÉCENT
     gagne — la récence est lue dans le TIMESTAMP DU NOM (decisions_YYYYMMDD_HHMMSS_…,
     tel que produit par soumettre_tri.sh), PAS dans le mtime (qu'un git clone
     réécrit). Fallback mtime seulement si le nom n'est pas horodaté (warning).
  4. Écrit le CSV fusionné dans handoff/decisions_recus/_fusion.csv (colonnes
     id_detection,decision — sans PII).
  5. Appelle pipeline/src/16_tri_visuel.py --apply avec ce fichier fusionné, le
     parquet de candidats et --planche-hash (double contrôle d'empreinte).

Candidats par défaut : data/interim/piscines_candidates_49_49035.parquet
(Bouchemaine). Modifier CANDIDATS_DEFAUT ci-dessous si la planche change.

Aucune donnée personnelle ne transite ici : uniquement id_detection + oui/non/incertain.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("appliquer")

HANDOFF_DIR = Path(__file__).resolve().parent
REPO_ROOT = HANDOFF_DIR.parent
RECUS_DIR = HANDOFF_DIR / "decisions_recus"
FUSION = RECUS_DIR / "_fusion.csv"
SRC_DIR = REPO_ROOT / "pipeline" / "src"
TRI = SRC_DIR / "16_tri_visuel.py"
CANDIDATS_DEFAUT = REPO_ROOT / "data" / "interim" / "piscines_candidates_49_49035.parquet"
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

# hash12 = 12 hex en fin de nom, juste avant .csv (decisions_..._{hash12}.csv).
RE_HASH = re.compile(r"_([0-9a-f]{12})\.csv$")
# Timestamp produit par soumettre_tri.sh : decisions_YYYYMMDD_HHMMSS_…
RE_TS = re.compile(r"decisions_(\d{8})_(\d{6})_")


# ------------------------------------------------------ empreinte & horodatage
# Fonctions pures et testables (aucun accès disque hormis hash12_fichier).

def hash12_fichier(path) -> str:
    """SHA-256 des octets du parquet, tronqué à 12 hex (même définition que
    16_tri_visuel.hash12_parquet — dupliquée pour garder ce script autonome)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def hash12_du_nom(nom: str) -> str | None:
    """Extrait l'empreinte de planche du nom du CSV, ou None si absente."""
    m = RE_HASH.search(nom)
    return m.group(1) if m else None


def timestamp_du_nom(nom: str) -> float | None:
    """Epoch extrait du timestamp contenu dans le NOM (decisions_YYYYMMDD_HHMMSS_…),
    ou None si le nom n'est pas horodaté / non parsable."""
    m = RE_TS.search(nom)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp()
    except ValueError:
        return None


def filtrer_par_hash(csvs, hash_courant: str, force: bool = False):
    """Sépare (retenus, exclus) selon l'empreinte de planche du nom.

    - nom sans hash12 : toléré (ancien format), retenu avec warning ;
    - hash12 == hash_courant : retenu ;
    - hash12 != hash_courant : exclu (sauf force=True → retenu).
    Pure et testable."""
    retenus, exclus = [], []
    for p in csvs:
        h = hash12_du_nom(p.name)
        if h is None:
            log.warning("Nom sans empreinte de planche (%s) — inclus sans "
                        "vérification (ancien format).", p.name)
            retenus.append(p)
        elif h == hash_courant or force:
            if h != hash_courant:
                log.warning("Empreinte %s ≠ planche courante %s (%s) — inclus car "
                            "--force.", h, hash_courant, p.name)
            retenus.append(p)
        else:
            exclus.append(p)
    return retenus, exclus


def cle_recence(path: Path):
    """Clé de départage des conflits : (epoch, nom). Le timestamp du NOM prime ;
    fallback mtime (avec warning) seulement si le nom n'est pas horodaté."""
    ts = timestamp_du_nom(path.name)
    if ts is None:
        ts = path.stat().st_mtime
        log.warning("Nom non horodaté (%s) — départage par mtime (fragile après "
                    "git clone).", path.name)
    return (ts, path.name)


def fusionner(csvs_ordonnes) -> pd.DataFrame:
    """Concatène les CSV (donnés du plus ANCIEN au plus récent), dédoublonne par
    id_detection : la dernière écriture (donc la plus récente) gagne les conflits."""
    retenu: dict[str, str] = {}
    provenance: dict[str, str] = {}
    for csv in csvs_ordonnes:
        df = pd.read_csv(csv, dtype=str)
        if not {"id_detection", "decision"} <= set(df.columns):
            raise SystemExit(
                f"{csv.name} : colonnes id_detection,decision attendues, trouvé {list(df.columns)}."
            )
        for _, row in df.iterrows():
            idd = str(row["id_detection"]).strip()
            dec = str(row["decision"]).strip()
            if idd in retenu and retenu[idd] != dec:
                log.warning(
                    "Conflit sur id_detection=%s : '%s' (%s) remplacé par '%s' (%s, plus récent).",
                    idd, retenu[idd], provenance[idd], dec, csv.name,
                )
            retenu[idd] = dec
            provenance[idd] = csv.name

    fusion = pd.DataFrame(sorted(retenu.items()), columns=["id_detection", "decision"])
    log.info("Fusion : %d décision(s) unique(s).", len(fusion))
    return fusion


def collecter_et_ordonner(hash_courant: str, force: bool):
    """Liste les CSV reçus, filtre par empreinte, ordonne du plus ancien au plus
    récent (timestamp du nom). Retourne (retenus_ordonnes, exclus)."""
    csvs = [p for p in RECUS_DIR.glob("*.csv") if p.name != FUSION.name]
    if not csvs:
        raise SystemExit(f"Aucun CSV de décisions dans {RECUS_DIR}.")

    retenus, exclus = filtrer_par_hash(csvs, hash_courant, force=force)
    if exclus:
        log.warning("%d fichier(s) EXCLU(S) (empreinte de planche différente — "
                    "utiliser --force pour forcer) :", len(exclus))
        for p in exclus:
            log.warning("  écarté : %s", p.name)
    if not retenus:
        raise SystemExit(
            "Aucun CSV ne correspond à la planche courante (empreinte "
            f"{hash_courant}). Régénérer la planche ou utiliser --force."
        )
    retenus.sort(key=cle_recence)
    log.info("%d fichier(s) retenu(s) à fusionner (ordre chronologique du nom).",
             len(retenus))
    return retenus, exclus


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("candidats", nargs="?", default=str(CANDIDATS_DEFAUT),
                    help="parquet de candidats (défaut : Bouchemaine)")
    ap.add_argument("--force", action="store_true",
                    help="inclure aussi les CSV d'une autre empreinte de planche")
    args = ap.parse_args()

    candidats = Path(args.candidats)
    if not candidats.exists():
        raise SystemExit(
            f"Parquet de candidats introuvable : {candidats}\n"
            "Passe le bon chemin en argument, ou récupère les données (bootstrap / pipeline)."
        )
    if not PYTHON.exists():
        raise SystemExit(f"Interpréteur introuvable : {PYTHON}. Lance d'abord ./bootstrap.sh.")

    hash_courant = hash12_fichier(candidats)
    log.info("Empreinte de la planche courante : %s (%s).", hash_courant, candidats.name)

    retenus, _ = collecter_et_ordonner(hash_courant, args.force)
    fusion = fusionner(retenus)
    FUSION.write_text(fusion.to_csv(index=False), encoding="utf-8")
    log.info("CSV fusionné écrit : %s", FUSION)

    cmd = [
        str(PYTHON), str(TRI),
        "--candidats", str(candidats),
        "--apply", str(FUSION),
        "--planche-hash", hash_courant,
    ]
    if args.force:
        cmd.append("--force")
    log.info("Application du tri : %s", " ".join(cmd))
    # cwd = pipeline/src pour satisfaire `from common import ...`
    subprocess.run(cmd, cwd=str(SRC_DIR), check=True)


if __name__ == "__main__":
    main()
