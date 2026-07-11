"""Socle commun du pipeline : config, chemins, filtre opt-out, traçabilité.

Tous les scripts du pipeline importent ce module. Les garde-fous implémentés ici
(opt-out, mentions de source) sont des obligations légales — voir docs/03-LEGAL-RGPD.md.
Ne pas les contourner.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import unicodedata
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


def normalise_adresse(s: object) -> str:
    """Normalise une adresse pour le rapprochement opt-out (déterministe) : sans
    accents, en minuscules, ponctuation → espaces, espaces compressés.

    Le rapprochement par adresse est nécessaire au droit d'opposition « par adresse
    seule » de l'art. 11 (une personne s'oppose sans connaître son id BAN — voir
    docs/legal/procedure_reclamation.md), et immunise l'opposition contre un id BAN
    qui changerait de valeur entre deux millésimes.
    """
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def apply_optout(df: pd.DataFrame, cfg: dict, logger: logging.Logger) -> pd.DataFrame:
    """Soustrait les adresses opposées. Appelé par TOUT export. Obligation légale.

    Le retrait se fait sur DEUX clés (union) : l'id BAN ET l'adresse normalisée. Une
    opposition peut n'avoir que l'une des deux (art. 11 « par adresse seule »). On
    refuse bruyamment plutôt que d'ignorer silencieusement une demande :
      - toute ligne d'opposition sans AUCUNE clé exploitable (ni id_ban ni adresse) ;
      - une opposition « par adresse » alors que la base n'a pas de colonne 'adresse'
        (on ne saurait pas l'honorer → on bloque l'export).
    """
    optout = load_optout(cfg)
    if optout.empty:
        logger.info("Opt-out : liste vide, 0 adresse retirée.")
        return df

    ids = {str(x).strip() for x in optout["id_ban"] if pd.notna(x) and str(x).strip()}
    adresses = set()
    if "adresse" in optout.columns:
        adresses = {a for a in optout["adresse"].map(normalise_adresse) if a}

    # Refus bruyant : une opposition sans aucune clé est une demande qu'on ne peut honorer.
    def _sans_cle(row) -> bool:
        a_id = pd.notna(row.get("id_ban")) and bool(str(row.get("id_ban")).strip())
        a_adr = bool(normalise_adresse(row.get("adresse")))
        return not a_id and not a_adr

    n_sans_cle = int(optout.apply(_sans_cle, axis=1).sum())
    if n_sans_cle:
        raise ValueError(
            f"Opt-out : {n_sans_cle} ligne(s) d'opposition sans id_ban NI adresse "
            "exploitable — impossible d'honorer la demande, refus d'exporter "
            "(corriger data/optout/optout.csv)."
        )

    before = len(df)
    masque = df["id_ban"].astype(str).str.strip().isin(ids)
    if adresses:
        if "adresse" not in df.columns:
            raise ValueError(
                "Opt-out : des oppositions « par adresse » existent mais la base n'a "
                "pas de colonne 'adresse' — on ne peut pas les honorer, refus d'exporter."
            )
        masque = masque | df["adresse"].map(normalise_adresse).isin(adresses)

    out = df[~masque].copy()
    logger.info("Opt-out : %d adresse(s) retirée(s) (clés id_ban + adresse).", before - len(out))
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


def borne_basse_wilson(succes: int, n: int, z: float = 1.96) -> float:
    """Borne basse de l'intervalle de confiance de Wilson (score) — 95 % par défaut (z=1,96).

    C'est le taux de précision qu'on ANNONCE au client, jamais l'estimation ponctuelle
    succes/n (protocole docs/06-QUALITE-VALIDATION.md §2, garde-fou n°7 « pas de
    sur-promesse »). Exemple : 96 succès sur 100 → ponctuel 96 %, borne basse Wilson
    ≈ 90,1 % → on annonce 90 %.

    Pourquoi Wilson plutôt que Wald (p ± z·√(p(1-p)/n)) : Wald se dégrade aux proportions
    extrêmes et petits échantillons (il peut sortir de [0, 1] et sous-couvre près de p=1) —
    exactement notre régime, une précision visée ≥ 95 %. Wilson reste dans [0, 1] et garde
    une bonne couverture même à p proche de 1. Fonction pure et déterministe (testable).
    """
    if n <= 0:
        raise ValueError("n doit être > 0 pour mesurer une précision.")
    if not 0 <= succes <= n:
        raise ValueError(f"succes ({succes}) doit être dans [0, n={n}].")
    p = succes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    demi = (z / denom) * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return centre - demi


def archiver_copie_datee(fichier: Path, produit: str, dept: str, cfg: dict,
                         logger: logging.Logger) -> Path:
    """Copie datée de l'actif à chaque (re)génération de data/final/.

    C'est le point-zéro des millésimes (moat n°2, docs/16 §3) : sans cette copie,
    une re-génération écraserait la base précédente et le diff « nouvelles piscines »
    (45_diff) n'aurait plus de référence. Destination :
        data/final/archive/{produit}_{dept}_{AAAA-MM-JJ}.parquet
    Idempotent : une re-génération le même jour réécrit la copie du jour (même clé).
    """
    fichier = Path(fichier)
    if not fichier.exists():
        raise FileNotFoundError(f"Rien à archiver : {fichier} n'existe pas.")
    archive_dir = Path(cfg["paths"]["final"]) / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / f"{produit}_{dept}_{date.today().isoformat()}.parquet"
    shutil.copy2(fichier, dest)
    logger.info("Archive datée de l'actif : %s", dest)
    return dest
