"""Extraction de la liste de prospects B2B (tâche D1) depuis SIRENE en open data.

Interroge l'API publique « Recherche d'entreprises » (DINUM, gratuite, sans clé)
qui expose SIRENE en open data, et construit `sales/prospects_{dept}.csv` : les
pisciniers et poseurs de pergolas/vérandas du département, à appeler en D0/D3.

Méthode (docs/07 §1) — union de deux passes sur la même base ouverte :
  1. par CODE NAF (43.99C maçonnerie/pisciniers, 43.32B menuiserie métallique…) ;
  2. par MOT-CLÉ dans la raison sociale (« piscine », « pergola », « spa »…), qui
     rattrape les entreprises pertinentes classées sous d'autres NAF (une passe
     `q=piscine` remonte des pisciniers en 43.99D, 41.20B, 70.10Z que les codes
     NAF seuls rateraient).

Garde-fous (implémentés dans prospects.py) : établissements B2B uniquement (le
champ `dirigeants` de l'API n'est JAMAIS lu — aucune donnée de personne), unités
et établissements non-diffusibles écartés, entités identifiables seulement par un
nom de personne écartées. Le fichier va sous sales/ (gitignoré).

Idempotent (ré-exécutable : réécrit le CSV), échoue bruyamment (< min-lignes ⇒
sortie en erreur ; throttling API persistant ⇒ abandon explicite).

Usage :
    python 50_prospects_sirene.py                       # dept de config.yaml
    python 50_prospects_sirene.py --dept 44
    python 50_prospects_sirene.py --naf 43.99C,43.32B --mots-cles piscine,pergola
    python 50_prospects_sirene.py --max-pages 40 --min-lignes 50
"""
from __future__ import annotations

import argparse
import logging
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import requests

from common import REPO_ROOT, load_config
from prospects import COLONNES, PRIORITE_RANG, resultat_vers_ligne

log = logging.getLogger("prospects")

API = "https://recherche-entreprises.api.gouv.fr/search"
PER_PAGE = 25  # maximum autorisé par l'API
NAF_DEFAUT = "43.99C,43.32B,47.78C,96.09Z"  # docs/07 §1
# Mots-clés de la passe plein-texte (docs/07 §1). Seuls ceux qui rendent des
# résultats dans le 49 sont retenus par défaut : « piscine » couvre déjà
# piscinier/pisciniste, et les requêtes multi-mots (« abri piscine », « store
# banne ») ne matchent pas en plein-texte. Élargir via --mots-cles au besoin.
MOTS_DEFAUT = "piscine,spa,pergola,veranda"


def fetch_page(session: requests.Session, params: dict) -> dict:
    """Une page de résultats, avec back-off exponentiel sur 429 (quota API ~7 req/s)."""
    for tentative in range(6):
        r = session.get(API, params=params, timeout=60)
        if r.status_code == 429:
            attente = 2 ** tentative
            log.warning("429 (quota API) — nouvelle tentative dans %ds", attente)
            time.sleep(attente)
            continue
        r.raise_for_status()
        return r.json()
    raise SystemExit("API recherche-entreprises : throttling 429 persistant, abandon.")


def parcourir(session: requests.Session, base_params: dict, max_pages: int):
    """Itère les résultats d'une requête, page par page (établissements actifs)."""
    page = 1
    while page <= max_pages:
        params = dict(base_params, page=page, per_page=PER_PAGE, etat_administratif="A")
        data = fetch_page(session, params)
        results = data.get("results") or []
        if not results:
            break
        yield from results
        if page >= (data.get("total_pages") or 1):
            break
        page += 1
        time.sleep(0.2)  # politesse envers l'API publique


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--dept", help="code département (défaut : config.yaml)")
    p.add_argument("--naf", default=NAF_DEFAUT, help="codes NAF séparés par des virgules")
    p.add_argument("--mots-cles", default=MOTS_DEFAUT, help="mots-clés séparés par des virgules")
    p.add_argument("--max-pages", type=int, default=20, help="pages max par requête (25/page)")
    p.add_argument("--out", help="chemin de sortie (défaut : sales/prospects_{dept}.csv)")
    p.add_argument("--min-lignes", type=int, default=30, help="échoue si moins de prospects")
    args = p.parse_args()

    cfg = load_config()
    dept = args.dept or cfg["dept"]
    out = Path(args.out) if args.out else REPO_ROOT / "sales" / f"prospects_{dept}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    naf_list = [c.strip() for c in args.naf.split(",") if c.strip()]
    mots = [m.strip() for m in args.mots_cles.split(",") if m.strip()]

    session = requests.Session()
    session.headers.update({"User-Agent": "maps-prospects/1.0 (prospection B2B open data)"})

    lignes: dict[str, dict] = {}   # clé de dédup -> ligne
    motifs: Counter = Counter()

    passes = ([("NAF", {"activite_principale": c}) for c in naf_list]
              + [("mot-clé", {"q": m}) for m in mots])
    for kind, base in passes:
        etiquette = base.get("activite_principale") or base.get("q")
        vus = retenus = 0
        for resultat in parcourir(session, dict(base, departement=dept), args.max_pages):
            vus += 1
            ligne, motif = resultat_vers_ligne(resultat, dept)
            if ligne is None:
                motifs[motif] += 1
                continue
            cle = ligne["siret"] or f'{ligne["raison_sociale"]}|{ligne["ville"]}'
            if cle in lignes:
                motifs["doublon"] += 1
                continue
            lignes[cle] = ligne
            retenus += 1
        log.info("Passe %s=%s : %d vus, %d nouveaux prospects", kind, etiquette, vus, retenus)

    df = pd.DataFrame(list(lignes.values()), columns=COLONNES)
    df = df.sort_values(
        by=["priorite", "ville", "raison_sociale"],
        key=lambda s: s.map(PRIORITE_RANG).fillna(9) if s.name == "priorite" else s,
    ).reset_index(drop=True)

    df.to_csv(out, index=False, encoding="utf-8")
    log.info("Écrit %s : %d prospects | par priorité : %s",
             out, len(df), df["priorite"].value_counts().to_dict())
    log.info("Écartés (motif → nombre) : %s", dict(motifs))

    if len(df) < args.min_lignes:
        raise SystemExit(
            f"Seulement {len(df)} prospects (< {args.min_lignes} demandés). Le CSV écrit reflète "
            "l'extraction réelle ; élargir --naf / --mots-cles / --max-pages pour en trouver plus."
        )


if __name__ == "__main__":
    main()
