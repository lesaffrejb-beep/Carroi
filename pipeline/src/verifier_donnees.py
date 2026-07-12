"""Vérification d'intégrité des données intermédiaires — « travaille-t-on sur
précisément les mêmes fichiers ? », en une commande, sur n'importe quelle machine.

Contexte (docs/17-RISQUES-METHODE.md, R1/R3) : les données brutes (BD ORTHO, 61 Go)
ne vivent que sur le SSD du propriétaire. Les autres machines reconstruisent
data/interim/ via les scripts 10_download → 12_… MAIS les sources « latest »
(cadastre Etalab, BAN) évoluent dans le temps : deux clones lancés à deux dates
peuvent diverger SILENCIEUSEMENT, et une jointure/scoring/tri lancé sur des
données divergentes produit un actif faux sans le moindre message d'erreur.

Ce module fige un MANIFESTE (pipeline/manifeste_donnees.json, COMMITÉ dans git =
la référence partagée) : pour chaque fichier de data/interim/, son SHA-256, sa
taille et son nombre de lignes. `--verifier` compare l'état local au manifeste et
refuse bruyamment si ça diverge.

  python verifier_donnees.py --generer   # (re)fige la référence depuis le local
  python verifier_donnees.py --verifier  # compare le local à la référence

Discipline : APRÈS toute (ré)génération de data/interim, relancer --generer,
committer le manifeste, et consigner le changement de millésime dans docs/08.

Les fonctions de calcul (construire_fichiers, comparer) sont PURES et séparées de
l'I/O — testées dans pipeline/tests/test_verifier_donnees.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("verifier_donnees")

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFESTE_PATH = REPO_ROOT / "pipeline" / "manifeste_donnees.json"
INTERIM_DIR = REPO_ROOT / "data" / "interim"

# Fichiers non-parquet suivis explicitement (millésimes des sources « latest »).
FICHIERS_EXTRA = ("millesimes.yaml",)

# Statuts de comparaison (fichier par fichier).
STATUT_IDENTIQUE = "identique"          # ✓ octet pour octet identique à la référence
STATUT_HASH_DIFFERENT = "hash_different"  # ✗ présent des deux côtés mais contenu différent
STATUT_ABSENT_LOCAL = "absent_local"      # ⚠ dans le manifeste, pas sur cette machine
STATUT_ABSENT_MANIFESTE = "absent_manifeste"  # ⚠ sur cette machine, absent du manifeste

_SYMBOLE = {
    STATUT_IDENTIQUE: "✓ identique",
    STATUT_HASH_DIFFERENT: "✗ hash différent",
    STATUT_ABSENT_LOCAL: "⚠ absent en local",
    STATUT_ABSENT_MANIFESTE: "⚠ absent du manifeste",
}


# --------------------------------------------------------------------------- #
# Fonctions PURES (aucune I/O) — le cœur testable.
# --------------------------------------------------------------------------- #
def entree_depuis_bytes(contenu: bytes, nb_lignes: int | None) -> dict:
    """Entrée de manifeste pour un fichier, calculée depuis ses octets.

    nb_lignes est None pour un fichier non tabulaire (ex. millesimes.yaml).
    """
    return {
        "sha256": hashlib.sha256(contenu).hexdigest(),
        "taille_octets": len(contenu),
        "nb_lignes": nb_lignes,
    }


def construire_fichiers(items: list[tuple[str, bytes, int | None]]) -> dict:
    """Construit la section « fichiers » d'un manifeste depuis une liste de
    (nom, octets, nb_lignes). Trié par nom de fichier (diffs git lisibles).

    Fonction pure : c'est elle qu'on teste sur données synthétiques.
    """
    fichiers: dict[str, dict] = {}
    for nom, contenu, nb_lignes in sorted(items, key=lambda t: t[0]):
        if nom in fichiers:
            raise ValueError(f"Nom de fichier dupliqué dans le manifeste : {nom!r}")
        fichiers[nom] = entree_depuis_bytes(contenu, nb_lignes)
    return fichiers


def comparer(reference: dict, local: dict) -> list[dict]:
    """Compare deux sections « fichiers » (référence vs local).

    Retourne une liste triée par nom, une entrée par fichier de l'union des deux
    côtés : {"nom", "statut", "reference", "local"}. `reference`/`local` sont
    l'entrée (sha/taille/lignes) ou None selon la présence. Fonction pure.
    """
    resultats: list[dict] = []
    for nom in sorted(set(reference) | set(local)):
        ref = reference.get(nom)
        loc = local.get(nom)
        if ref is not None and loc is not None:
            statut = (
                STATUT_IDENTIQUE
                if ref["sha256"] == loc["sha256"]
                else STATUT_HASH_DIFFERENT
            )
        elif ref is not None:
            statut = STATUT_ABSENT_LOCAL
        else:
            statut = STATUT_ABSENT_MANIFESTE
        resultats.append({"nom": nom, "statut": statut, "reference": ref, "local": loc})
    return resultats


def local_est_conforme(resultats: list[dict]) -> bool:
    """Vrai SEULEMENT si tous les fichiers du manifeste sont ✓ identiques en local.

    Les fichiers locaux EN PLUS (absent_manifeste) ne bloquent PAS (ils sont
    signalés mais ne rendent pas les données incohérentes avec la référence).
    """
    for r in resultats:
        if r["statut"] in (STATUT_HASH_DIFFERENT, STATUT_ABSENT_LOCAL):
            return False
    return True


# --------------------------------------------------------------------------- #
# I/O — lecture des fichiers réels, comptage de lignes, manifeste JSON.
# --------------------------------------------------------------------------- #
def _hash_et_taille(path: Path) -> tuple[str, int]:
    """SHA-256 et taille d'un fichier, en streaming (les parquet font jusqu'à
    ~290 Mo : on ne charge pas tout en mémoire)."""
    h = hashlib.sha256()
    taille = 0
    with open(path, "rb") as f:
        for bloc in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloc)
            taille += len(bloc)
    return h.hexdigest(), taille


def _nb_lignes_parquet(path: Path) -> int:
    """Nombre de lignes d'un parquet, via les métadonnées (sans lire les données)."""
    import pyarrow.parquet as pq

    return pq.ParquetFile(path).metadata.num_rows


def _lister_fichiers_locaux(interim: Path) -> list[Path]:
    """*.parquet (non récursif) + FICHIERS_EXTRA présents, triés par nom."""
    fichiers = list(interim.glob("*.parquet"))
    for nom in FICHIERS_EXTRA:
        p = interim / nom
        if p.exists():
            fichiers.append(p)
    return sorted(fichiers, key=lambda p: p.name)


def scanner_local(interim: Path = INTERIM_DIR) -> dict:
    """Construit la section « fichiers » depuis data/interim/ réel.

    Lève FileNotFoundError si le dossier n'existe pas (machine fraîche) — les
    appelants décident du message et du code de sortie.
    """
    if not interim.exists():
        raise FileNotFoundError(str(interim))
    fichiers: dict[str, dict] = {}
    for path in _lister_fichiers_locaux(interim):
        sha, taille = _hash_et_taille(path)
        nb_lignes = _nb_lignes_parquet(path) if path.suffix == ".parquet" else None
        fichiers[path.name] = {"sha256": sha, "taille_octets": taille, "nb_lignes": nb_lignes}
        log.info("  scanné %s (%d octets, %s lignes)", path.name, taille,
                 nb_lignes if nb_lignes is not None else "-")
    return dict(sorted(fichiers.items()))


def charger_manifeste(path: Path = MANIFESTE_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def ecrire_manifeste(fichiers: dict, path: Path = MANIFESTE_PATH) -> dict:
    """Écrit le manifeste (fichiers + métadonnées informatives) et le retourne."""
    manifeste = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "machine": platform.node(),
        "note": (
            "Référence partagée des données data/interim/. NE PAS éditer à la main. "
            "Régénérer avec : python pipeline/src/verifier_donnees.py --generer, "
            "committer, et consigner le changement de millésime dans docs/08."
        ),
        "fichiers": fichiers,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifeste, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    return manifeste


# --------------------------------------------------------------------------- #
# Commandes CLI.
# --------------------------------------------------------------------------- #
def cmd_generer() -> int:
    if not INTERIM_DIR.exists():
        log.error(
            "data/interim/ est absent : rien à figer. Reconstruire les données "
            "d'abord (bootstrap.sh puis 10_download.py …) avant de générer le manifeste."
        )
        return 2
    log.info("Scan de %s …", INTERIM_DIR)
    fichiers = scanner_local()
    if not fichiers:
        log.error("Aucun fichier suivi trouvé dans data/interim/ — rien à figer.")
        return 2
    manifeste = ecrire_manifeste(fichiers)
    log.info(
        "Manifeste écrit : %s (%d fichier(s), machine %s).",
        MANIFESTE_PATH, len(fichiers), manifeste["machine"],
    )
    log.info(
        "→ Committer pipeline/manifeste_donnees.json ET consigner le millésime "
        "dans docs/08-ROADMAP.md (garde-fou R3)."
    )
    return 0


def cmd_verifier() -> int:
    if not MANIFESTE_PATH.exists():
        log.error(
            "Aucun manifeste de référence (%s) : impossible de vérifier. "
            "Récupérer la version du dépôt (git pull) ou générer la référence "
            "sur la machine qui détient les données (--generer).",
            MANIFESTE_PATH,
        )
        return 2

    manifeste = charger_manifeste()
    reference = manifeste.get("fichiers", {})

    if not INTERIM_DIR.exists():
        log.error(
            "data/interim/ est absent sur cette machine (clone frais). Les %d "
            "fichier(s) de la référence sont TOUS manquants : reconstruire les "
            "données aux bons millésimes (voir docs/08 / millesimes.yaml) avant "
            "toute jointure/scoring/tri.",
            len(reference),
        )
        return 2

    local = scanner_local()
    resultats = comparer(reference, local)

    print(f"\nRéférence : {MANIFESTE_PATH.name} (générée le {manifeste.get('genere_le', '?')} "
          f"sur {manifeste.get('machine', '?')})")
    print(f"Local     : {INTERIM_DIR}\n")
    for r in resultats:
        print(f"  {_SYMBOLE[r['statut']]:22s} {r['nom']}")

    n_diff = sum(1 for r in resultats if r["statut"] == STATUT_HASH_DIFFERENT)
    n_abs_local = sum(1 for r in resultats if r["statut"] == STATUT_ABSENT_LOCAL)
    n_extra = sum(1 for r in resultats if r["statut"] == STATUT_ABSENT_MANIFESTE)
    n_ok = sum(1 for r in resultats if r["statut"] == STATUT_IDENTIQUE)

    print(
        f"\n  {n_ok} identique(s), {n_diff} divergent(s), "
        f"{n_abs_local} manquant(s) en local, {n_extra} en plus (hors référence).\n"
    )

    if local_est_conforme(resultats):
        if n_extra:
            print(
                "✅ Toutes les données de la référence sont présentes et identiques. "
                f"({n_extra} fichier(s) local(aux) en plus, hors référence — sans effet "
                "sur la cohérence, mais à consigner si ce sont de nouvelles couches.)"
            )
        else:
            print("✅ Vos données sont IDENTIQUES à la référence partagée.")
        return 0

    print(
        "❌ VOS DONNÉES DIVERGENT DE LA RÉFÉRENCE — NE PAS lancer de jointure/scoring/tri "
        "(20_/30_/16_) : l'actif produit serait faux sans erreur visible.\n"
        "   Corriger : relancer 10_download.py AUX MÊMES MILLÉSIMES (voir "
        "data/interim/millesimes.yaml de la référence), OU récupérer le manifeste à "
        "jour (git pull) si c'est la référence qui a bougé."
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fige/compare le manifeste d'intégrité de data/interim/ "
                    "(travaille-t-on sur les mêmes fichiers ?)."
    )
    groupe = parser.add_mutually_exclusive_group(required=True)
    groupe.add_argument("--generer", action="store_true",
                        help="(re)fige la référence depuis les données locales et écrit le manifeste.")
    groupe.add_argument("--verifier", action="store_true",
                        help="compare les données locales au manifeste de référence.")
    args = parser.parse_args(argv)

    if args.generer:
        return cmd_generer()
    return cmd_verifier()


if __name__ == "__main__":
    sys.exit(main())
