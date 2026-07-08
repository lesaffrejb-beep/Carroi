"""Contrat de couche 1 — validation EXÉCUTABLE de la sortie de tout détecteur.

docs/09-MOTEUR-PROSPECTION.md §2 définit le contrat ; ce module le fait respecter.
Chaque détecteur (piscines, terrasses, et tout futur plugin : parkings, toitures…)
appelle `valider_couche1()` avant d'écrire son parquet. Un détecteur qui viole le
contrat échoue BRUYAMMENT à l'écriture — pas six mois plus tard dans un export client.

Ce module est aussi un garde-fou légal automatisé : il REFUSE toute colonne dont le
nom évoque une donnée nominative (garde-fou n°1 de CLAUDE.md). Aucune session future,
aucun détecteur tiers, ne peut glisser un nom/téléphone/email dans la chaîne sans
casser le pipeline immédiatement.

Usage détecteur :
    from contrat import valider_couche1
    valider_couche1(gdf, crs_attendu="EPSG:2154")   # lève ValueError détaillée sinon
    gdf.to_parquet(out)
"""
from __future__ import annotations

import hashlib
import logging
import re

import geopandas as gpd

log = logging.getLogger("contrat")


def ids_stables(gdf: gpd.GeoDataFrame, prefixe: str) -> list[str]:
    """Identifiants de détection STABLES entre deux runs : dérivés de la position
    (point représentatif arrondi au décimètre), pas de l'ordre d'exécution.

    Pourquoi c'est vital (piège corrigé le 2026-07-08) : avec id = range(n),
    tout re-run (seuil ajusté, nouveau millésime) invalidait silencieusement les
    décisions de tri humain déjà prises, et le produit « nouvelles piscines »
    (diff entre millésimes) était impossible. Avec un id positionnel, une piscine
    inchangée garde son id d'un run à l'autre ; les décisions de tri restent
    valides ; le diff de millésimes est un simple anti-join sur id.

    Collisions (deux détections au même décimètre) : suffixe déterministe après
    tri — jamais silencieux, toujours reproductible.
    """
    pts = gdf.geometry.representative_point()
    bruts = [
        f"{prefixe}_" + hashlib.sha1(f"{x:.1f}:{y:.1f}".encode()).hexdigest()[:12]
        for x, y in zip(pts.x, pts.y)
    ]
    vus: dict[str, int] = {}
    ids = []
    for b in bruts:
        n = vus.get(b, 0)
        vus[b] = n + 1
        ids.append(b if n == 0 else f"{b}-{n}")
    return ids

# Colonnes que TOUT détecteur doit produire (docs/09 §2). Les attributs
# spécifiques au produit s'y ajoutent librement.
COLONNES_REQUISES = ["surface_m2", "score_detection", "methode", "id_detection"]

# Garde-fou n°1 (CLAUDE.md) : motifs de noms de colonnes interdits dans TOUTE
# la chaîne. Volontairement large : un faux positif se renomme, un vrai positif
# est une violation légale.
MOTIFS_INTERDITS = re.compile(
    r"(nom|prenom|prénom|surname|firstname|lastname|proprietaire|propriétaire|owner"
    r"|tel|phone|portable|mobile"
    r"|mail|email|e-mail"
    r"|naissance|birth|age|sexe|gender"
    r"|siren|siret)",  # données d'entreprise : hors périmètre du fichier vendu
    re.IGNORECASE,
)
# Exceptions légitimes connues (mot entier, pas de sous-chaîne piégeuse).
EXCEPTIONS = {"nom_voie", "nom_commune"}  # éléments d'adresse postale, pas d'identité


def colonnes_interdites(colonnes) -> list[str]:
    return [
        c for c in colonnes
        if c not in EXCEPTIONS and MOTIFS_INTERDITS.search(str(c))
    ]


def valider_couche1(gdf: gpd.GeoDataFrame, crs_attendu: str = "EPSG:2154") -> None:
    """Valide la sortie d'un détecteur. Lève ValueError listant TOUTES les
    violations (pas seulement la première : on corrige tout d'un coup)."""
    erreurs: list[str] = []

    if not isinstance(gdf, gpd.GeoDataFrame):
        raise ValueError("La sortie d'un détecteur doit être un GeoDataFrame.")
    if len(gdf) == 0:
        erreurs.append("sortie vide — un détecteur sans résultat doit échouer en amont, "
                       "pas écrire un parquet vide qui passera inaperçu")

    for col in COLONNES_REQUISES:
        if col not in gdf.columns:
            erreurs.append(f"colonne requise manquante : {col}")

    interdites = colonnes_interdites(gdf.columns)
    if interdites:
        erreurs.append(
            f"COLONNES À CONSONANCE NOMINATIVE INTERDITES : {interdites} — "
            "garde-fou légal n°1 (CLAUDE.md), non négociable. Renommer si faux "
            "positif, supprimer si vraie donnée personnelle."
        )

    if gdf.crs is None or gdf.crs.to_string() != crs_attendu:
        erreurs.append(f"CRS {gdf.crs} ≠ attendu {crs_attendu} (calculs métriques en Lambert-93)")

    if len(gdf) > 0:
        geoms = gdf.geometry
        if geoms.isna().any() or geoms.is_empty.any():
            erreurs.append("géométries nulles ou vides présentes")
        elif (~geoms.is_valid).any():
            erreurs.append(f"{int((~geoms.is_valid).sum())} géométrie(s) invalide(s) "
                           "(auto-intersection ?) — corriger à la source, pas par buffer(0) silencieux")

        if "score_detection" in gdf.columns:
            s = gdf["score_detection"]
            if s.isna().any() or (s < 0).any() or (s > 1).any():
                erreurs.append("score_detection hors [0,1] ou NaN")
        if "surface_m2" in gdf.columns:
            surf = gdf["surface_m2"]
            if surf.isna().any() or (surf <= 0).any():
                erreurs.append("surface_m2 ≤ 0 ou NaN")
        if "id_detection" in gdf.columns and gdf["id_detection"].duplicated().any():
            erreurs.append("id_detection non uniques")
        if "methode" in gdf.columns and (gdf["methode"].isna() | (gdf["methode"] == "")).any():
            erreurs.append("methode vide — la traçabilité de la méthode est obligatoire")

    if erreurs:
        raise ValueError(
            "Contrat couche 1 violé (docs/09 §2) :\n  - " + "\n  - ".join(erreurs)
        )
    log.info("Contrat couche 1 : OK (%d lignes, %d colonnes).", len(gdf), len(gdf.columns))
