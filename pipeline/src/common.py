"""Socle commun du pipeline : config, chemins, filtre opt-out, traçabilité.

Tous les scripts du pipeline importent ce module. Les garde-fous implémentés ici
(opt-out, mentions de source) sont des obligations légales — voir docs/03-LEGAL-RGPD.md.
Ne pas les contourner.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "pipeline" / "config.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Résout les chemins relatifs par rapport à la racine du repo.
    for key, val in cfg["paths"].items():
        cfg["paths"][key] = str(REPO_ROOT / val)
    return cfg


def ensure_dirs(cfg: dict) -> None:
    for key in ("raw", "interim", "final", "exports", "validation"):
        Path(cfg["paths"][key]).mkdir(parents=True, exist_ok=True)
    Path(cfg["paths"]["optout"]).parent.mkdir(parents=True, exist_ok=True)


def pipeline_version() -> str:
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def load_optout(cfg: dict) -> pd.DataFrame:
    """Liste d'opposition (droit d'opposition RGPD, art. 21).

    Format attendu de data/optout/optout.csv :
        id_ban,adresse,date_demande
    id_ban est la clé de jointure (identifiant BAN de l'adresse). Si le fichier
    n'existe pas encore, retourne une liste vide — mais le filtre reste appelé
    sur chaque export, sans exception.
    """
    path = Path(cfg["paths"]["optout"])
    if not path.exists():
        return pd.DataFrame(columns=["id_ban", "adresse", "date_demande"])
    df = pd.read_csv(path, dtype=str)
    if "id_ban" not in df.columns:
        raise ValueError(f"{path}: colonne 'id_ban' manquante — format invalide, on refuse d'exporter.")
    return df


def apply_optout(df: pd.DataFrame, cfg: dict, logger: logging.Logger) -> pd.DataFrame:
    """Soustrait les adresses opposées. Appelé par TOUT export. Obligation légale."""
    optout = load_optout(cfg)
    if optout.empty:
        logger.info("Opt-out : liste vide, 0 adresse retirée.")
        return df
    before = len(df)
    out = df[~df["id_ban"].isin(set(optout["id_ban"]))].copy()
    logger.info("Opt-out : %d adresse(s) retirée(s).", before - len(out))
    return out


def source_attribution(millesimes: dict[str, str]) -> str:
    """Mention de source obligatoire (Licence Ouverte 2.0) embarquée dans chaque export.

    millesimes: ex. {"BD TOPO (IGN)": "2026-03", "Cadastre (DGFiP/Etalab)": "2026-04", "BAN": "2026-06"}
    """
    parts = [f"{name} millésime {m}" for name, m in millesimes.items()]
    return (
        "Source : "
        + " ; ".join(parts)
        + f" — Licence Ouverte 2.0. Généré le {date.today().isoformat()}, pipeline {pipeline_version()}."
    )
