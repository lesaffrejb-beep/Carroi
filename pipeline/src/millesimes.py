"""Diff de millésimes — le moteur du produit « nouvelles piscines » (et de tout diff).

Compare deux sorties de détection (contrat couche 1) issues de deux millésimes
de source et classe chaque objet : NOUVEAU (dans après, pas dans avant),
DISPARU (dans avant, pas dans après), CONSERVÉ (apparié).

Pourquoi ce n'est pas un simple join sur id_detection : les ids stables sont
dérivés de la position, mais entre deux millésimes d'orthophoto la MÊME piscine
est redétectée à quelques dizaines de centimètres près (recalage, contours) —
son id change. L'appariement est donc SPATIAL : plus proche voisin réciproque
sous tolérance, un-pour-un (appariement glouton par distance croissante —
optimal pour des objets épars comme des piscines, où deux candidates au même
« avant » sont rarissimes et la plus proche gagne).

Enjeu commercial : les « nouveaux » sont le segment premium (docs/00 — un
propriétaire qui vient de construire achète abri/entretien/chauffage), et le
point-zéro des millésimes est le moat n°2 (docs/09 §5). Un faux « nouveau »
(piscine existante ratée à l'appariement) = un client démarché pour rien et
une crédibilité entamée : la tolérance se règle, les cas limites se testent.

Fonctions pures, testées dans pipeline/tests/test_millesimes.py.
"""
from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np

log = logging.getLogger("millesimes")


def apparier(
    avant: gpd.GeoDataFrame,
    apres: gpd.GeoDataFrame,
    tolerance_m: float = 8.0,
) -> list[tuple[int, int, float]]:
    """Appariement spatial un-pour-un entre deux ensembles de détections.

    Retourne [(pos_avant, pos_apres, distance_m), …] (positions ilocs).
    Glouton par distance croissante : chaque objet de chaque côté est apparié
    au plus une fois, les paires les plus proches d'abord. tolerance_m couvre
    le recalage inter-millésimes (l'ortho bouge de < 1 m, les contours de
    détection de quelques m) sans apparier la piscine du voisin (> 8 m).
    """
    if tolerance_m <= 0:
        raise ValueError("tolerance_m doit être > 0")
    if avant.crs != apres.crs:
        raise ValueError(f"CRS différents : {avant.crs} vs {apres.crs} — reprojeter d'abord.")
    if len(avant) == 0 or len(apres) == 0:
        return []

    c_avant = avant.geometry.centroid
    c_apres = apres.geometry.centroid
    # Toutes les paires candidates sous tolérance, via l'index spatial.
    gauche, droite = c_apres.sindex.query(
        c_avant.geometry.values, predicate="dwithin", distance=tolerance_m
    )
    if len(gauche) == 0:
        return []
    d = c_avant.iloc[gauche].distance(c_apres.iloc[droite], align=False).values

    paires = []
    pris_avant: set[int] = set()
    pris_apres: set[int] = set()
    for k in np.argsort(d):
        i, j = int(gauche[k]), int(droite[k])
        if i in pris_avant or j in pris_apres:
            continue
        pris_avant.add(i)
        pris_apres.add(j)
        paires.append((i, j, float(d[k])))
    return paires


def diff_millesimes(
    avant: gpd.GeoDataFrame,
    apres: gpd.GeoDataFrame,
    tolerance_m: float = 8.0,
) -> dict[str, gpd.GeoDataFrame]:
    """Classe les détections « après » vs « avant ».

    Retourne {"nouvelles", "conservees", "disparues"} :
      - nouvelles   : lignes d'APRÈS sans correspondant (le produit premium) ;
      - conservees  : lignes d'APRÈS appariées, + colonnes id_detection_avant
                      et derive_m (distance d'appariement, diagnostic recalage) ;
      - disparues   : lignes d'AVANT sans correspondant (piscines comblées,
                      bâchées en dur, ou faux positifs de l'ancien millésime —
                      à examiner, jamais à vendre).
    """
    paires = apparier(avant, apres, tolerance_m)
    ia = [p[0] for p in paires]
    ja = [p[1] for p in paires]

    conservees = apres.iloc[ja].copy() if ja else apres.iloc[0:0].copy()
    if ja:
        conservees["id_detection_avant"] = avant.iloc[ia]["id_detection"].values
        conservees["derive_m"] = [round(p[2], 2) for p in paires]

    nouvelles = apres.iloc[[k for k in range(len(apres)) if k not in set(ja)]].copy()
    disparues = avant.iloc[[k for k in range(len(avant)) if k not in set(ia)]].copy()

    log.info(
        "Diff millésimes (tol %.1f m) : %d conservées (dérive méd. %s m), "
        "%d NOUVELLES, %d disparues.",
        tolerance_m, len(conservees),
        round(float(np.median([p[2] for p in paires])), 2) if paires else "-",
        len(nouvelles), len(disparues),
    )
    if len(avant) and len(nouvelles) > 0.5 * len(apres):
        log.warning(
            "Plus de 50 %% de « nouvelles » : recalage suspect entre millésimes "
            "ou tolérance trop faible — vérifier sur carte AVANT de vendre quoi "
            "que ce soit (un faux « nouveau » = un client démarché pour rien)."
        )
    return {"nouvelles": nouvelles, "conservees": conservees, "disparues": disparues}
