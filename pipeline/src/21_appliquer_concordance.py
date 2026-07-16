"""Application de la vérification humaine des adresses (concordance.csv de
17_verification_adresse) à la base adressée de 20_join.

Trois cas par ligne du CSV :
  - concordance true  → l'adresse de l'algo est confirmée (verif_humaine=True) ;
  - id_ban_choisi_humain = autre id BAN → l'adresse est REMPLACÉE par le choix
    humain (attributs BAN rapatriés, source_jointure='humain') ;
  - id_ban_choisi_humain = 'aucune' → aucune adresse candidate ne convient :
    l'adresse est retirée (id_ban NaN) ; 30_score l'exclura de la base vendable.

Usage :
    python 21_appliquer_concordance.py \
        --concordance handoff/concordance_recus/concordance_..._JB_49035.csv
    (par défaut : --adressees data/interim/piscines_adressees_{dept}.parquet,
     réécrit sur place ; relancer ensuite 30_score_qualite.py)

Échoue bruyamment si un id_piscine du CSV est inconnu de la base (mauvais couple
fichier/base) ou si un id BAN choisi n'existe pas dans la BAN du département.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from common import ensure_dirs, load_config

log = logging.getLogger("concordance")

AUCUNE = "aucune"
ATTRS_BAN = ["numero", "rep", "nom_voie", "code_postal", "nom_commune", "code_insee"]
# Colonnes d'adresse remises à zéro quand l'humain répond « aucune ».
COLS_ADRESSE = ["id_ban", "adresse", "numero", "rep", "nom_voie", "code_postal",
                "commune", "code_insee", "dist_adresse_m", "adresse_dans_parcelle"]


def texte_adresse(row) -> str:
    """« numero rep nom_voie » compacté, même format que 20_join. Pure."""
    parts = []
    for c in ("numero", "rep", "nom_voie"):
        v = row.get(c)
        if v is None or (isinstance(v, float) and v != v):
            continue
        s = str(v)
        if s.endswith(".0"):
            s = s[:-2]
        if s:
            parts.append(s)
    return " ".join(parts)


def appliquer_concordance(adressees: gpd.GeoDataFrame, ban: gpd.GeoDataFrame,
                          conc: pd.DataFrame) -> gpd.GeoDataFrame:
    """Applique les verdicts humains. Pure et testable. Retourne une COPIE.

    - Toute piscine présente dans le CSV reçoit verif_humaine=True.
    - Divergence vers un id BAN → adresse remplacée, source_jointure='humain',
      dist_adresse_m recalculée, adresse_dans_parcelle laissée indéterminée (pd.NA) :
      on ne fabrique pas une corroboration cadastrale qui n'a pas été mesurée.
    - 'aucune' → colonnes d'adresse vidées, source_jointure='humain_aucune'.
    """
    if not {"id_piscine", "id_ban_choisi_humain"} <= set(conc.columns):
        raise ValueError("concordance.csv : colonnes id_piscine,id_ban_choisi_humain attendues.")
    out = adressees.copy()
    out["id_piscine"] = out["id_piscine"].astype(str)
    if "verif_humaine" not in out.columns:
        out["verif_humaine"] = False
    # Les colonnes d'adresse doivent pouvoir recevoir pd.NA ('aucune') : les
    # dtypes stricts (bool, int) refuseraient l'assignation (LossySetitemError).
    for c in COLS_ADRESSE:
        if c in out.columns and str(out[c].dtype) not in ("object", "float64"):
            out[c] = out[c].astype("object")

    ids_base = set(out["id_piscine"])
    conc = conc.assign(id_piscine=conc["id_piscine"].astype(str),
                       choix=conc["id_ban_choisi_humain"].astype(str))
    inconnus = set(conc["id_piscine"]) - ids_base
    if inconnus:
        raise ValueError(f"{len(inconnus)} id_piscine du CSV inconnus de la base "
                         f"(ex. {sorted(inconnus)[:5]}) — mauvais couple fichier/base ?")

    ban_idx = ban.drop_duplicates("id_ban").set_index("id_ban")
    choisis = set(conc.loc[conc["choix"] != AUCUNE, "choix"])
    absents = choisis - set(ban_idx.index.astype(str))
    if absents:
        raise ValueError(f"{len(absents)} id BAN choisis absents de la BAN : {sorted(absents)[:5]}")

    n_confirme = n_corrige = n_aucune = 0
    for _, ligne in conc.iterrows():
        masque = out["id_piscine"] == ligne["id_piscine"]
        out.loc[masque, "verif_humaine"] = True
        actuel = out.loc[masque, "id_ban"].astype(str).iloc[0]
        if ligne["choix"] == AUCUNE:
            for c in COLS_ADRESSE:
                if c in out.columns:
                    out.loc[masque, c] = pd.NA
            out.loc[masque, "source_jointure"] = "humain_aucune"
            n_aucune += 1
        elif ligne["choix"] == actuel:
            n_confirme += 1
        else:
            r = ban_idx.loc[ligne["choix"]]
            out.loc[masque, "id_ban"] = ligne["choix"]
            for c in ATTRS_BAN:
                cible = "commune" if c == "nom_commune" else c
                if cible in out.columns:
                    out.loc[masque, cible] = r[c]
            if "adresse" in out.columns:
                out.loc[masque, "adresse"] = texte_adresse(r)
            if "dist_adresse_m" in out.columns:
                out.loc[masque, "dist_adresse_m"] = float(
                    out.loc[masque].geometry.distance(r.geometry).iloc[0])
            if "adresse_dans_parcelle" in out.columns:
                out.loc[masque, "adresse_dans_parcelle"] = pd.NA
            out.loc[masque, "source_jointure"] = "humain"
            n_corrige += 1

    log.info("Concordance appliquée : %d adresses confirmées, %d corrigées, "
             "%d retirées ('aucune').", n_confirme, n_corrige, n_aucune)
    return out


def derniere_concordance(dossier: Path) -> Path:
    """Le CSV de concordance le plus récent (tri lexicographique du nom, qui porte
    le timestamp). Échoue bruyamment si le dossier est vide."""
    fichiers = sorted(dossier.glob("concordance_*.csv"))
    if not fichiers:
        raise SystemExit(f"Aucun concordance_*.csv dans {dossier}.")
    return fichiers[-1]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adressees", help="parquet de 20_join (défaut : interim du dept)")
    p.add_argument("--concordance",
                   help="CSV exporté par la page de vérification (défaut : le plus "
                        "récent de handoff/concordance_recus/)")
    args = p.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    dept = cfg["dept"]
    interim = Path(cfg["paths"]["interim"])

    src = Path(args.adressees) if args.adressees else interim / f"piscines_adressees_{dept}.parquet"
    csv = Path(args.concordance) if args.concordance else derniere_concordance(
        Path(__file__).resolve().parents[2] / "handoff" / "concordance_recus")

    adressees = gpd.read_parquet(src)
    ban = gpd.read_parquet(interim / f"ban_{dept}.parquet")
    conc = pd.read_csv(csv)
    log.info("%d piscines, %d verdicts humains (%s).", len(adressees), len(conc), csv.name)

    out = appliquer_concordance(adressees, ban, conc)
    out.to_parquet(src)
    log.info("Écrit : %s. Prochaine étape : 30_score_qualite.py (les vérifiées "
             "humain passent en confiance haute).", src)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
