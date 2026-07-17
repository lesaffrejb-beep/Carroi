"""Agrégation de votes multi-annotateurs — Dawid-Skene (EM), pur numpy.

La majorité simple traite tous les trieurs pareil. Dawid & Skene (1979) apprend
la MATRICE DE CONFUSION de chaque trieur (sa probabilité de répondre j quand la
vérité est k) et pondère les votes en conséquence : un trieur fiable pèse plus,
un trieur qui confond bâche et piscine est corrigé, pas juste moyenné. Gain réel
dès 3 annotateurs qui se recouvrent ; à 1-2 annotateurs l'EM retombe de lui-même
sur (presque) la majorité.

Implémentation EM standard (~60 lignes), sans dépendance au reste du pipeline :
    consensus_dawid_skene(votes) -> {item: (classe, confiance)}
avec votes = {item: [(trieur, reponse), ...]}.

Références : Dawid & Skene 1979 (JRSS-C) ; « Fast Dawid-Skene » (Sinha et al.
2018) n'apporte que de la vitesse, inutile à notre échelle (< 10^5 votes).
"""
from __future__ import annotations

import numpy as np


def consensus_dawid_skene(votes: dict[str, list[tuple[str, str]]],
                          max_iter: int = 60, tol: float = 1e-5
                          ) -> dict[str, tuple[str, float]]:
    """EM de Dawid-Skene. Pure et déterministe (init = vote majoritaire doux).

    Retourne, par item, la classe la plus probable et sa probabilité a
    posteriori (la « confiance », plus informative que le taux d'accord brut).
    """
    items = sorted(votes)
    trieurs = sorted({t for vs in votes.values() for t, _ in vs})
    classes = sorted({r for vs in votes.values() for _, r in vs})
    if not items or not classes:
        return {}
    ii = {v: k for k, v in enumerate(items)}
    tt = {v: k for k, v in enumerate(trieurs)}
    cc = {v: k for k, v in enumerate(classes)}
    nI, nT, nC = len(items), len(trieurs), len(classes)

    # n[i, t, c] = nombre de fois où le trieur t a répondu c sur l'item i (0/1
    # en pratique ; un re-vote écrase côté Atelier, mais l'EM tolère > 1).
    n = np.zeros((nI, nT, nC))
    for it, vs in votes.items():
        for t, r in vs:
            n[ii[it], tt[t], cc[r]] += 1

    # Init : proportions de votes par item (majorité douce).
    T = n.sum(axis=1)                                   # (nI, nC)
    T = T / np.maximum(T.sum(axis=1, keepdims=True), 1e-12)

    prev = None
    for _ in range(max_iter):
        # M : prior des classes + confusion par trieur (lissage de Laplace :
        # aucun trieur n'est jamais « parfait » au point d'écraser les autres).
        p = T.mean(axis=0)                              # (nC,)
        conf = np.einsum("ik,itc->tkc", T, n) + 0.01    # (nT, vérité k, réponse c)
        conf = conf / conf.sum(axis=2, keepdims=True)
        # E : posteriors des items sous indépendance des trieurs.
        logT = np.log(np.maximum(p, 1e-12))[None, :].repeat(nI, axis=0)
        logT = logT + np.einsum("itc,tkc->ik", n, np.log(np.maximum(conf, 1e-12)))
        logT = logT - logT.max(axis=1, keepdims=True)
        T = np.exp(logT)
        T = T / T.sum(axis=1, keepdims=True)
        if prev is not None and np.abs(T - prev).max() < tol:
            break
        prev = T.copy()

    return {it: (classes[int(T[ii[it]].argmax())], float(T[ii[it]].max()))
            for it in items}


def fiabilite_trieurs(votes: dict[str, list[tuple[str, str]]],
                      consensus: dict[str, tuple[str, float]]) -> dict[str, float]:
    """Taux de conformité de chaque trieur au consensus DS (pour le tableau des
    gains ; les items où lui seul a voté sont ignorés — pas d'auto-validation)."""
    ok: dict[str, list[int]] = {}
    for it, vs in votes.items():
        if len({t for t, _ in vs}) < 2:
            continue
        verite = consensus[it][0]
        for t, r in vs:
            ok.setdefault(t, []).append(int(r == verite))
    return {t: float(np.mean(v)) for t, v in ok.items() if v}
