#!/usr/bin/env python3
"""appliquer_decisions_recues.py — fusionner et appliquer les décisions de tri reçues.

Usage :
    .venv/bin/python handoff/appliquer_decisions_recues.py

Ce que fait le script :
  1. Liste tous les CSV de handoff/decisions_recus/.
  2. Les concatène en dédoublonnant par id_detection. En cas de conflit (le même
     id_detection décidé différemment dans deux fichiers), la décision du fichier
     le plus RÉCENT (mtime) gagne, et un avertissement est loggé.
  3. Écrit le CSV fusionné dans handoff/decisions_recus/_fusion.csv (colonnes
     id_detection,decision — sans PII).
  4. Appelle pipeline/src/16_tri_visuel.py --apply avec ce fichier fusionné et le
     parquet de candidats.

Candidats par défaut : data/interim/piscines_candidates_49_49035.parquet
(Bouchemaine). Modifier CANDIDATS_DEFAUT ci-dessous si la planche change.

Aucune donnée personnelle ne transite ici : uniquement id_detection + oui/non/incertain.
"""
from __future__ import annotations

import logging
import subprocess
import sys
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


def fusionner() -> pd.DataFrame:
    """Concatène tous les CSV reçus, dédoublonne par id_detection (récent gagne)."""
    csvs = sorted(
        (p for p in RECUS_DIR.glob("*.csv") if p.name != FUSION.name),
        key=lambda p: p.stat().st_mtime,
    )
    if not csvs:
        raise SystemExit(f"Aucun CSV de décisions dans {RECUS_DIR}.")

    log.info("%d fichier(s) de décisions à fusionner.", len(csvs))
    # Parcours du plus ancien au plus récent : la dernière écriture par id gagne.
    retenu: dict[str, str] = {}
    provenance: dict[str, str] = {}
    for csv in csvs:
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

    fusion = pd.DataFrame(
        sorted(retenu.items()), columns=["id_detection", "decision"]
    )
    log.info("Fusion : %d décision(s) unique(s).", len(fusion))
    return fusion


def main() -> None:
    candidats = Path(sys.argv[1]) if len(sys.argv) > 1 else CANDIDATS_DEFAUT
    if not candidats.exists():
        raise SystemExit(
            f"Parquet de candidats introuvable : {candidats}\n"
            "Passe le bon chemin en argument, ou récupère les données (bootstrap / pipeline)."
        )
    if not PYTHON.exists():
        raise SystemExit(f"Interpréteur introuvable : {PYTHON}. Lance d'abord ./bootstrap.sh.")

    fusion = fusionner()
    FUSION.write_text(
        fusion.to_csv(index=False), encoding="utf-8"
    )
    log.info("CSV fusionné écrit : %s", FUSION)

    cmd = [
        str(PYTHON), str(TRI),
        "--candidats", str(candidats),
        "--apply", str(FUSION),
    ]
    log.info("Application du tri : %s", " ".join(cmd))
    # cwd = pipeline/src pour satisfaire `from common import ...`
    subprocess.run(cmd, cwd=str(SRC_DIR), check=True)


if __name__ == "__main__":
    main()
