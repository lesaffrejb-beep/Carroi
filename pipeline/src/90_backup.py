"""Sauvegarde chiffrée hors-site de l'actif (docs/16 §2).

Construit un tar.gz de data/final + data/exports + sales + data/optout +
data/validation (JAMAIS data/raw ni data/interim : retéléchargeables/volumineux),
le chiffre en CLÉ PUBLIQUE (age ou gpg — pas de passphrase, exécutable sans
interaction), puis l'envoie sur le stockage distant via rclone. Config dans
config.yaml §backup.

Idempotent : l'archive porte la date du jour ; relancer le même jour ré-écrit.
Échec bruyant : outil manquant, config vide ou commande en erreur ⇒ SystemExit.

Prérequis 🧑 (une fois) : installer `age` (ou `gpg`) et `rclone` ; configurer un
remote rclone (ex. Hetzner Storage Box, docs/16 §2) ; renseigner config.yaml §backup
(rclone_remote + destinataire).

Usage :
    python 90_backup.py
    python 90_backup.py --garder-local   # garde aussi l'archive chiffrée dans data/backups/
"""
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import tarfile
import tempfile
from datetime import date
from pathlib import Path

from common import REPO_ROOT, load_config

log = logging.getLogger("backup")


def _exige_binaire(nom: str) -> None:
    if shutil.which(nom) is None:
        raise SystemExit(
            f"'{nom}' introuvable dans le PATH — l'installer avant de sauvegarder "
            "(voir docs/16 §2, prérequis 🧑)."
        )


def dossiers_a_sauvegarder(cfg: dict) -> list[Path]:
    """Les cibles de la sauvegarde (docs/16 §2). data/raw et data/interim en sont
    volontairement absents (retéléchargeables — garde-fou de l'item 8)."""
    cibles = [
        Path(cfg["paths"]["final"]),
        Path(cfg["paths"]["exports"]),
        Path(cfg["paths"]["validation"]),
        Path(cfg["paths"]["optout"]).parent,   # data/optout/
        REPO_ROOT / "sales",
    ]
    return cibles


def construire_tar(cfg: dict, dest_tar: Path) -> list[Path]:
    """tar.gz des dossiers présents ; retourne la liste réellement incluse."""
    presents = [p for p in dossiers_a_sauvegarder(cfg) if p.exists()]
    if not presents:
        raise SystemExit(
            "Rien à sauvegarder : aucun des dossiers final/exports/sales/optout/validation "
            "n'existe encore. (Sauvegarde lancée trop tôt ?)"
        )
    with tarfile.open(dest_tar, "w:gz") as tar:
        for p in presents:
            tar.add(p, arcname=str(p.relative_to(REPO_ROOT)))
    return presents


def chiffrer(cfg: dict, source: Path, dest: Path) -> None:
    methode = cfg["backup"].get("chiffrement", "age")
    destinataire = cfg["backup"].get("destinataire", "")
    if not destinataire:
        raise SystemExit("config backup.destinataire vide — clé de chiffrement requise (docs/16 §2).")
    if methode == "age":
        _exige_binaire("age")
        subprocess.run(["age", "-r", destinataire, "-o", str(dest), str(source)], check=True)
    elif methode == "gpg":
        _exige_binaire("gpg")
        subprocess.run(
            ["gpg", "--yes", "--batch", "--recipient", destinataire,
             "--output", str(dest), "--encrypt", str(source)],
            check=True,
        )
    else:
        raise SystemExit(f"backup.chiffrement inconnu : {methode!r} (attendu 'age' ou 'gpg').")


def envoyer(cfg: dict, chemin: Path) -> str:
    remote = cfg["backup"].get("rclone_remote", "")
    if not remote:
        raise SystemExit("config backup.rclone_remote vide — sauvegarde distante non configurée (docs/16 §2).")
    _exige_binaire("rclone")
    subprocess.run(["rclone", "copy", str(chemin), remote, "--progress"], check=True)
    return remote


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--garder-local", action="store_true",
                   help="garde aussi l'archive chiffrée dans data/backups/")
    args = p.parse_args()

    cfg = load_config()
    if "backup" not in cfg:
        raise SystemExit("Section 'backup:' absente de config.yaml — voir docs/16 §2.")

    jour = date.today().isoformat()
    ext = "age" if cfg["backup"].get("chiffrement", "age") == "age" else "gpg"
    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / f"maps_backup_{cfg['dept']}_{jour}.tar.gz"
        presents = construire_tar(cfg, tar_path)
        log.info("Archive : %d dossier(s) (%s), %.1f Mo",
                 len(presents), ", ".join(p.name for p in presents), tar_path.stat().st_size / 1e6)

        chiffre = Path(tmp) / f"{tar_path.name}.{ext}"
        chiffrer(cfg, tar_path, chiffre)
        log.info("Chiffré (%s) : %s", cfg["backup"].get("chiffrement", "age"), chiffre.name)

        if args.garder_local:
            local_dir = REPO_ROOT / "data" / "backups"   # hors du périmètre sauvegardé (pas de récursion)
            local_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(chiffre, local_dir / chiffre.name)
            log.info("Copie locale : %s", local_dir / chiffre.name)

        remote = envoyer(cfg, chiffre)
    log.info("Sauvegarde terminée → %s (%s)", remote, chiffre.name)


if __name__ == "__main__":
    main()
