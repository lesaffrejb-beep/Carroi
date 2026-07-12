#!/usr/bin/env bash
#
# bootstrap.sh — prépare l'environnement complet du projet en une commande.
#
# Usage :
#   ./bootstrap.sh
#
# Idempotent (relançable sans dégât). Échoue bruyamment à la moindre étape cassée,
# sauf pour les outils système via brew (explicitement optionnels : signalés, pas bloquants).
#
# Étapes :
#   1. vérifie qu'on est dans un dépôt git, puis git pull
#   2. crée .venv si absent
#   3. installe les dépendances Python (pipeline/requirements.txt)
#   4. (macOS + brew) vérifie/installe les outils système : 7z, osmium, gdal
#   5. lance la suite de tests comme test de sanité
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo "==> Dépôt : $REPO_DIR"

# --- 1. git ------------------------------------------------------------------
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERREUR : pas un dépôt git. Clone le repo d'abord." >&2
  exit 1
fi
echo "==> git pull"
git pull --ff-only || {
  echo "AVERTISSEMENT : git pull non fast-forward (modifs locales ?). On continue." >&2
}

# --- 2. venv -----------------------------------------------------------------
if [[ ! -x ".venv/bin/python" ]]; then
  echo "==> Création de .venv"
  python3 -m venv .venv
else
  echo "==> .venv déjà présent"
fi

# --- 3. dépendances Python ---------------------------------------------------
echo "==> Mise à jour de pip + installation des dépendances"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r pipeline/requirements.txt

# --- 4. outils système (macOS + brew, optionnel) -----------------------------
# 7z (p7zip), osmium (osmium-tool), gdal (ogr2ogr). Vérif AVANT install.
if [[ "$(uname)" == "Darwin" ]]; then
  if command -v brew >/dev/null 2>&1; then
    echo "==> Vérification des outils système (brew)"
    # map "commande à tester" -> "formule brew"
    check_tool() {
      local cmd="$1" formula="$2"
      if command -v "$cmd" >/dev/null 2>&1; then
        echo "    ok : $cmd déjà présent"
      else
        echo "    manquant : $cmd → brew install $formula"
        brew install "$formula" || echo "    AVERTISSEMENT : échec brew install $formula (non bloquant)." >&2
      fi
    }
    check_tool 7z p7zip
    check_tool osmium osmium-tool
    check_tool ogr2ogr gdal
  else
    echo "==> brew absent : outils système (7z, osmium, gdal) non vérifiés (optionnel)."
    echo "    Installe-les manuellement si tu lances le pipeline complet."
  fi
else
  echo "==> Hors macOS : installe 7z, osmium, gdal via ton gestionnaire de paquets si besoin."
fi

# --- 5. tests de sanité ------------------------------------------------------
echo "==> Tests de sanité (pytest)"
.venv/bin/python -m pytest pipeline/tests/ -q

echo "==> Bootstrap terminé."
