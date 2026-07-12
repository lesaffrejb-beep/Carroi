#!/usr/bin/env bash
# verifier_tout.sh — LA commande à lancer AVANT et APRÈS toute tâche (tout LLM/humain).
#
# Enchaîne trois vérifications et agrège le résultat :
#   1. tests du pipeline (pytest)              — la logique tient-elle ?
#   2. intégrité des données (manifeste)       — travaille-t-on sur les mêmes fichiers ?
#   3. propreté de l'arbre git                 — reste-t-il des changements non commités ?
#
# Sortie : « ✅ TOUT EST COHÉRENT » ou « ❌ PROBLÈMES : … » listés.
# Code de sortie agrégé (0 seulement si tout est vert).
#
# Ne s'arrête PAS au premier échec : on veut le tableau complet en une passe.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

PY="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

PROBLEMES=()

echo "======================================================================"
echo " verifier_tout.sh — cohérence méthode (tests + données + git)"
echo "======================================================================"

# --- 1. Tests -------------------------------------------------------------- #
echo
echo ">>> [1/3] Tests du pipeline (pytest)"
if "$PY" -m pytest pipeline/tests/ -q; then
  echo "    ✓ tests verts"
else
  PROBLEMES+=("tests pytest en échec")
fi

# --- 2. Intégrité des données --------------------------------------------- #
echo
echo ">>> [2/3] Intégrité des données (manifeste)"
if [[ -d "data/interim" ]]; then
  if "$PY" pipeline/src/verifier_donnees.py --verifier; then
    echo "    ✓ données conformes à la référence"
  else
    PROBLEMES+=("données divergentes de la référence (voir manifeste)")
  fi
else
  echo "    ⚠ data/interim/ absent — vérification données SAUTÉE (non bloquant)."
  echo "      (machine sans données : reconstruire avant toute jointure/scoring/tri.)"
fi

# --- 3. Propreté de l'arbre git ------------------------------------------- #
echo
echo ">>> [3/3] État de l'arbre git"
SALE="$(git status --short)"
if [[ -z "$SALE" ]]; then
  echo "    ✓ arbre propre (rien à committer)"
else
  echo "$SALE"
  PROBLEMES+=("arbre git sale (changements non commités ci-dessus)")
fi

# --- Bilan agrégé ---------------------------------------------------------- #
echo
echo "======================================================================"
if [[ ${#PROBLEMES[@]} -eq 0 ]]; then
  echo " ✅ TOUT EST COHÉRENT"
  echo "======================================================================"
  exit 0
else
  echo " ❌ PROBLÈMES :"
  for p in "${PROBLEMES[@]}"; do
    echo "    - $p"
  done
  echo "======================================================================"
  exit 1
fi
