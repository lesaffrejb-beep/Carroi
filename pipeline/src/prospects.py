"""Cœur pur de la liste de prospects B2B (couche vente, tâche D1 de la roadmap).

Sépare la logique métier (sélection de l'établissement du département, règle de
nom non-nominatif, priorisation) du script réseau `50_prospects_sirene.py`, sur
le même modèle que `detection.py`/`15_` ou `millesimes.py`/`45_`. Testable sans
réseau : toutes les fonctions prennent des dicts déjà décodés de l'API.

Garde-fous portés ici (voir CLAUDE.md §garde-fous ; la liste de prospects est un
fichier d'ENTREPRISES B2B, distinct de la base produit qui reste, elle, sans
aucune donnée nominative) :
- On ne lit JAMAIS le champ `dirigeants` renvoyé par l'API : aucune donnée de
  personne (dirigeant, gérant) n'entre dans le fichier.
- Diffusion INSEE : une unité ou un établissement non-diffusible (statut ≠ 'O')
  est écarté — on respecte le droit à la non-diffusion.
- Règle non-nominative : le nom retenu est une raison sociale ou une enseigne
  (identité d'ENTREPRISE). Un entrepreneur individuel identifiable UNIQUEMENT par
  un nom de personne (ni raison sociale, ni enseigne) est écarté — cohérent avec
  le pilier « jamais de données nominatives ».
"""
from __future__ import annotations

import unicodedata

# Colonnes du livrable sales/prospects_{dept}.csv. Les 6 premières sont imposées
# par la roadmap (D1) ; code_postal + siret sont deux attributs d'ÉTABLISSEMENT
# (donc autorisés) ajoutés pour localiser et dédupliquer les prospects sur le
# terrain — un fichier d'appel sans code postal ni clé de dédup serait inutilisable.
COLONNES = [
    "raison_sociale", "naf", "ville", "tel_si_public", "site_web",
    "priorite", "code_postal", "siret",
]

# Priorisation par mot-clé dans le nom (méthode docs/07 §1). Formes normalisées
# (minuscule, sans accent) : le test de correspondance passe par _norm().
# Signal piscine FORT = quasi-certainement un piscinier (« piscin » couvre piscine,
# piscinier, pisciniste, piscines) → haute. Signal FAIBLE = ambigu : « spa »/« aqua »
# désignent aussi bien un vendeur de jacuzzi (pertinent) qu'un institut de beauté ou
# un hôtel (non pertinent) → moyenne, jamais en tête de fichier.
MOTS_PISCINE_FORT = ("piscin", "pool", "bassin")
MOTS_PISCINE_FAIBLE = ("spa", "aqua")
MOTS_TERRASSE = (
    "pergola", "veranda", "store", "storiste", "abri", "terrasse",
    "menuiserie", "brise soleil",
)
# NAF « probables » produit 1/2 même sans mot-clé dans le nom (43.99C/D maçonnerie
# et pisciniers, 43.32B menuiserie métallique = pergolas/vérandas).
NAF_INDICE = frozenset({"43.99C", "43.99D", "43.32B"})

# Ordre de tri des priorités (croissant = plus prioritaire en haut du fichier).
PRIORITE_RANG = {"haute": 0, "moyenne": 1, "basse": 2}


def _norm(s: str) -> str:
    """Minuscule, sans accent, espaces uniques — pour la recherche de mot-clé."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def etablissement_du_dept(resultat: dict, dept: str) -> dict | None:
    """Établissement ACTIF et DIFFUSIBLE du département cible, ou None.

    Le filtre `departement` de l'API retient l'unité légale ; son SIÈGE peut être
    dans un autre département. On lit donc `matching_etablissements` (les
    établissements ayant matché le filtre) et on prend le premier réellement dans
    le département, actif et diffusible. Le département est dérivé du code commune
    INSEE (préfixe) et, à défaut, du code postal.
    """
    for etab in resultat.get("matching_etablissements") or []:
        commune = str(etab.get("commune") or "")
        cp = str(etab.get("code_postal") or "")
        if not (commune.startswith(dept) or cp.startswith(dept)):
            continue
        if etab.get("etat_administratif") not in (None, "A"):
            continue
        if etab.get("statut_diffusion_etablissement") not in (None, "O"):
            continue
        return etab
    return None


def nom_diffusable(resultat: dict, etab: dict) -> str | None:
    """Nom d'ENTREPRISE à retenir, ou None si seul un nom de personne existe.

    Ordre : raison sociale (personne morale) > enseigne > nom commercial de
    l'établissement (identité commerciale d'un entrepreneur individuel). Si aucun
    des trois, l'entité n'est identifiable que par le nom d'une personne physique :
    on l'écarte (règle non-nominative)."""
    rs = (resultat.get("nom_raison_sociale") or "").strip()
    if rs:
        return rs
    for enseigne in etab.get("liste_enseignes") or []:
        if enseigne and enseigne.strip():
            return enseigne.strip()
    nc = (etab.get("nom_commercial") or "").strip()
    if nc:
        return nc
    return None


def calc_priorite(nom: str, naf: str) -> str:
    """haute (signal piscine fort, cœur produit 1) > moyenne (spa/aqua ambigu,
    pergola/véranda, ou NAF de métier probable) > basse (aucun signal). Le terrain
    descend le fichier de haut en bas ; la tête de liste doit être fiable."""
    n = _norm(nom)
    if any(m in n for m in MOTS_PISCINE_FORT):
        return "haute"
    if any(m in n for m in MOTS_PISCINE_FAIBLE) or any(m in n for m in MOTS_TERRASSE):
        return "moyenne"
    if naf in NAF_INDICE:
        return "moyenne"
    return "basse"


def resultat_vers_ligne(resultat: dict, dept: str) -> tuple[dict | None, str | None]:
    """Transforme un résultat d'API en ligne de prospect.

    Retourne (ligne, None) si le résultat produit un prospect exploitable, sinon
    (None, motif) où motif ∈ {non_diffusible, hors_dept, nominatif_seul} — le
    script agrège ces motifs pour un log honnête de ce qui a été écarté et pourquoi.
    """
    if resultat.get("statut_diffusion") not in (None, "O"):
        return None, "non_diffusible"
    etab = etablissement_du_dept(resultat, dept)
    if etab is None:
        return None, "hors_dept"
    nom = nom_diffusable(resultat, etab)
    if nom is None:
        return None, "nominatif_seul"
    naf = etab.get("activite_principale") or resultat.get("activite_principale") or ""
    ligne = {
        "raison_sociale": nom,
        "naf": naf,
        "ville": etab.get("libelle_commune") or "",
        # Absents de SIRENE : à enrichir au triage manuel via annuaire (docs/07 §1).
        "tel_si_public": "",
        "site_web": "",
        "priorite": calc_priorite(nom, naf),
        "code_postal": etab.get("code_postal") or "",
        "siret": etab.get("siret") or "",
    }
    return ligne, None
