"""18_bilan_tri.py — extraire la valeur du tri manuel : dataset d'entraînement +
courbe de calibration réelle.

Le tri visuel (16_tri_visuel.py) produit, en plus d'une base vendable, un signal
précieux : des milliers de jugements humains « piscine / pas piscine » adossés aux
features géométriques des candidats. Ce script transforme ces jugements en deux
livrables :

1. data/interim/tri_labels_{dept}_{commune}_{hash12}.parquet
   JOIN des décisions × TOUTES les features des candidats (surface_m2, compacite,
   solidite, score_detection, dalle, methode, geometry) + decision + trieur +
   horodatage. C'est le DATASET D'ENTRAÎNEMENT de la roadmap B4 (option A :
   apprendre un classifieur qui reproduit le jugement humain pour pré-trier les
   futures communes). On le sérialise en parquet géospatial, prêt à charger.

2. data/validation/bilan_tri_{dept}_{commune}.md (+ affiché en stdout)
   Rapport d'analyse : répartition O/N/U, courbe de calibration (taux de « oui »
   par tranche de score_detection), taux de « oui » par tranche de surface, effet
   de la corroboration cadastre, compte par trieur, et une section « implications »
   PRUDENTE (suggestions à valider, jamais de modification automatique de config).

Usage :
    python 18_bilan_tri.py --decisions <csv fusionné ou export brut> \
        --candidats data/interim/piscines_candidates_49_49035.parquet

Le CSV de décisions peut être au format 2 colonnes (id_detection,decision) OU
4 colonnes (…,trieur,horodatage) — les deux sont acceptés (rétro-compat).

Échec bruyant si plus de 2 % des id_detection des décisions ne correspondent à
aucun candidat (mauvais couple decisions/candidats).
"""
from __future__ import annotations

import argparse
import importlib
import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from common import ensure_dirs, load_config

log = logging.getLogger("bilan_tri")

# On réutilise les fonctions PURES de 16_tri_visuel (nom de module non importable
# tel quel : chargement par importlib). commune/hash12 pour nommer les sorties,
# charger_pci_piscines/corrobore_cadastre pour recalculer la corroboration.
tri = importlib.import_module("16_tri_visuel")

VALIDES = {"oui", "non", "incertain"}
SEUIL_INCONNUS = 0.02  # >2 % de décisions sans candidat correspondant → échec

# Bornes de la courbe de calibration (score_detection) et des tranches de surface.
BUCKETS_SCORE = [0.55, 0.6, 0.65, 0.7, 0.8, 1.0]
BUCKETS_SURFACE = [8, 15, 30, 60, float("inf")]
LABELS_SURFACE = ["8-15", "15-30", "30-60", "60+"]


# ------------------------------------------------------------ chargement

def charger_decisions(path) -> pd.DataFrame:
    """Lit le CSV de décisions (2 ou 4 colonnes) → DataFrame normalisé avec les
    colonnes id_detection, decision, trieur, horodatage (trieur/horodatage remplis
    par '' / 'inconnu' si absents). Pure hormis la lecture du fichier."""
    df = pd.read_csv(path, dtype=str)
    if not {"id_detection", "decision"} <= set(df.columns):
        raise SystemExit(
            f"{path} : colonnes id_detection,decision attendues, trouvé {list(df.columns)}."
        )
    out = pd.DataFrame({
        "id_detection": df["id_detection"].astype(str).str.strip(),
        "decision": df["decision"].astype(str).str.strip(),
    })
    out["trieur"] = (df["trieur"].fillna("").astype(str).str.strip()
                     if "trieur" in df.columns else "inconnu")
    out["trieur"] = out["trieur"].replace("", "inconnu")
    out["horodatage"] = (df["horodatage"].fillna("").astype(str).str.strip()
                         if "horodatage" in df.columns else "")
    inconnues = set(out["decision"]) - VALIDES
    if inconnues:
        raise SystemExit(f"Décisions invalides : {inconnues} (attendu {VALIDES}).")
    return out


def joindre(decisions: pd.DataFrame, candidats: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """JOIN décisions × features des candidats. Échoue bruyamment si trop de
    décisions pointent vers des id inconnus (mauvais couple decisions/candidats)."""
    cand = candidats.copy()
    cand["id_detection"] = cand["id_detection"].astype(str)
    ids_cand = set(cand["id_detection"])
    ids_dec = set(decisions["id_detection"])
    inconnus = ids_dec - ids_cand
    if len(inconnus) > SEUIL_INCONNUS * max(1, len(ids_dec)):
        raise SystemExit(
            f"{len(inconnus)}/{len(ids_dec)} décision(s) pour des id_detection inconnus "
            f"(> {SEUIL_INCONNUS:.0%}) — le CSV ne correspond pas à ces candidats. "
            f"Exemples : {sorted(list(inconnus))[:5]}"
        )
    if inconnus:
        log.warning("%d décision(s) sur des id inconnus — ignorée(s) dans le JOIN.",
                    len(inconnus))
    labels = cand.merge(decisions, on="id_detection", how="inner")
    return gpd.GeoDataFrame(labels, geometry="geometry", crs=cand.crs)


# ------------------------------------------------------------ statistiques

def taux_oui_par_bucket(labels: pd.DataFrame, valeurs: pd.Series,
                        bornes, etiquettes) -> pd.DataFrame:
    """Pour chaque tranche : n total décidé, n oui, taux de oui (oui/total).
    Pure et testable. Les valeurs hors bornes sont ignorées (bucket NaN écarté)."""
    cats = pd.cut(valeurs, bins=bornes, labels=etiquettes,
                  include_lowest=True, right=False)
    df = pd.DataFrame({"bucket": cats, "decision": labels["decision"].values})
    lignes = []
    for etq in etiquettes:
        sub = df[df["bucket"] == etq]
        n = len(sub)
        n_oui = int((sub["decision"] == "oui").sum())
        taux = (n_oui / n) if n else float("nan")
        lignes.append({"tranche": etq, "n": n, "oui": n_oui, "taux_oui": taux})
    return pd.DataFrame(lignes)


def bornes_score(labels: pd.DataFrame) -> list[float]:
    """Bornes de calibration ajustées : on abaisse la première borne au min observé
    si des scores tombent sous 0,55 (sinon ils seraient exclus silencieusement)."""
    bornes = list(BUCKETS_SCORE)
    mn = float(labels["score_detection"].min())
    if mn < bornes[0]:
        bornes = [round(mn, 3)] + bornes
    return bornes


def etiquettes_depuis_bornes(bornes) -> list[str]:
    return [f"{bornes[k]:.2f}-{bornes[k + 1]:.2f}" for k in range(len(bornes) - 1)]


def taux_par_corroboration(labels: gpd.GeoDataFrame, cfg: dict) -> pd.DataFrame | None:
    """Recalcule la corroboration cadastre (charger_pci_piscines + corrobore_cadastre
    de 16_tri_visuel) et croise avec la décision. None si le PCI est indisponible."""
    try:
        pci = tri.charger_pci_piscines(cfg)
    except Exception as e:  # noqa: BLE001 — on veut un bilan même sans PCI
        log.warning("Corroboration indisponible (chargement PCI : %s).", e)
        return None
    if pci is None or len(pci) == 0:
        log.warning("Aucune piscine PCI chargée — section corroboration omise.")
        return None
    pci.sindex
    corr = labels.geometry.apply(lambda g: tri.corrobore_cadastre(g, pci))
    df = pd.DataFrame({"corrobore": corr.values, "decision": labels["decision"].values})
    lignes = []
    for flag, etq in [(True, "corroborés cadastre"), (False, "non corroborés")]:
        sub = df[df["corrobore"] == flag]
        n = len(sub)
        n_oui = int((sub["decision"] == "oui").sum())
        lignes.append({"groupe": etq, "n": n, "oui": n_oui,
                       "taux_oui": (n_oui / n) if n else float("nan")})
    return pd.DataFrame(lignes)


# ------------------------------------------------------------ rapport

def _tbl(df: pd.DataFrame, cols: list[str], entetes: list[str]) -> str:
    lignes = ["| " + " | ".join(entetes) + " |",
              "|" + "|".join(["---"] * len(entetes)) + "|"]
    for _, r in df.iterrows():
        cellules = []
        for c in cols:
            v = r[c]
            if c == "taux_oui":
                cellules.append("n/a" if pd.isna(v) else f"{v:.0%}")
            else:
                cellules.append(str(v))
        lignes.append("| " + " | ".join(cellules) + " |")
    return "\n".join(lignes)


def construire_rapport(labels: gpd.GeoDataFrame, n_candidats: int, dept: str,
                       commune: str, calib: pd.DataFrame, surf: pd.DataFrame,
                       corr: pd.DataFrame | None) -> str:
    total = len(labels)
    reste = n_candidats - total
    n_oui = int((labels["decision"] == "oui").sum())
    n_non = int((labels["decision"] == "non").sum())
    n_inc = int((labels["decision"] == "incertain").sum())
    taux_inc = (n_inc / total) if total else float("nan")

    par_trieur = (labels.groupby("trieur")["decision"].count()
                  .sort_index().reset_index(name="n"))

    lignes = [
        f"# Bilan du tri manuel — {dept} / {commune}",
        "",
        f"- Candidats total : **{n_candidats}**",
        f"- Décisions appliquées : **{total}** (reste **{reste}** non trié)",
        f"- Répartition : **{n_oui} oui** · **{n_non} non** · **{n_inc} incertain**",
        f"- Taux d'incertitude : **{taux_inc:.1%}**" if total else "- Taux d'incertitude : n/a",
        "",
        "## Courbe de calibration — taux de « oui » par tranche de score_detection",
        "",
        "La probabilité qu'un candidat soit une vraie piscine, mesurée sur le tri",
        "humain, par tranche de score du détecteur. C'est la calibration RÉELLE.",
        "",
        _tbl(calib, ["tranche", "n", "oui", "taux_oui"],
             ["score", "n décidé", "oui", "taux oui"]),
        "",
        "## Taux de « oui » par tranche de surface",
        "",
        _tbl(surf, ["tranche", "n", "oui", "taux_oui"],
             ["surface (m²)", "n décidé", "oui", "taux oui"]),
        "",
        "## Compte par trieur",
        "",
        _tbl(par_trieur, ["trieur", "n"], ["trieur", "n décisions"]),
        "",
    ]

    if corr is not None:
        lignes += [
            "## Effet de la corroboration cadastre",
            "",
            "Taux de « oui » selon qu'une piscine cadastrée (PCI SYM=65) est à",
            "proximité (< 5 m) — mesure la tenue du badge « ⌂ cadastré ».",
            "",
            _tbl(corr, ["groupe", "n", "oui", "taux_oui"],
                 ["groupe", "n décidé", "oui", "taux oui"]),
            "",
        ]

    # ------- implications AUTOMATIQUES mais prudentes (suggestions à valider)
    implications = []
    for _, r in calib.iterrows():
        if r["n"] >= 10 and not pd.isna(r["taux_oui"]) and r["taux_oui"] < 0.20:
            implications.append(
                f"- Tranche de score **{r['tranche']}** : seulement {r['taux_oui']:.0%} "
                f"de « oui » sur {int(r['n'])} cas → **suggestion à valider** : "
                "remonter `detection.score_min` au-dessus de cette tranche réduirait "
                "le bruit à trier. (Ne PAS modifier config.yaml automatiquement.)"
            )
    if corr is not None:
        c_ok = corr[corr["groupe"] == "corroborés cadastre"]
        if len(c_ok) and c_ok.iloc[0]["n"] >= 10 and not pd.isna(c_ok.iloc[0]["taux_oui"]) \
                and c_ok.iloc[0]["taux_oui"] > 0.95:
            implications.append(
                f"- Les candidats corroborés cadastre sont « oui » à "
                f"{c_ok.iloc[0]['taux_oui']:.0%} → **le badge ⌂ cadastré tient sa "
                "promesse** (quasi-certitude, tri accéléré justifié)."
            )
    if not implications:
        implications.append("- Aucune implication automatique déclenchée sur cet échantillon.")

    lignes += [
        "## Implications (suggestions à valider — aucune modification automatique)",
        "",
        *implications,
        "",
    ]
    return "\n".join(lignes)


# ------------------------------------------------------------ main

def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--decisions", required=True,
                   help="CSV de décisions (2 ou 4 colonnes)")
    p.add_argument("--candidats", required=True,
                   help="parquet de candidats (features)")
    args = p.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)

    candidats = gpd.read_parquet(args.candidats)
    decisions = charger_decisions(args.decisions)
    log.info("%d candidats, %d décisions chargées.", len(candidats), len(decisions))

    labels = joindre(decisions, candidats)
    log.info("%d candidats décidés (join).", len(labels))

    commune = tri.commune_depuis_nom(args.candidats, cfg["dept"])
    h12 = tri.hash12_parquet(args.candidats)

    # 1) dataset d'entraînement (parquet géospatial)
    interim = Path(cfg["paths"]["interim"])
    out_labels = interim / f"tri_labels_{cfg['dept']}_{commune}_{h12}.parquet"
    labels.to_parquet(out_labels)
    log.info("Dataset d'entraînement écrit : %s (%d lignes).", out_labels, len(labels))

    # 2) statistiques
    bornes = bornes_score(labels)
    calib = taux_oui_par_bucket(labels, labels["score_detection"],
                                bornes, etiquettes_depuis_bornes(bornes))
    surf = taux_oui_par_bucket(labels, labels["surface_m2"],
                               BUCKETS_SURFACE, LABELS_SURFACE)
    corr = taux_par_corroboration(labels, cfg)

    rapport = construire_rapport(labels, len(candidats), cfg["dept"], commune,
                                 calib, surf, corr)
    out_md = Path(cfg["paths"]["validation"]) / f"bilan_tri_{cfg['dept']}_{commune}.md"
    out_md.write_text(rapport, encoding="utf-8")
    log.info("Rapport écrit : %s", out_md)
    print("\n" + rapport)


if __name__ == "__main__":
    main()
