#!/usr/bin/env bash
#
# soumettre_tri.sh — renvoyer un decisions.csv trié.
#
# Usage :
#   ./handoff/soumettre_tri.sh chemin/vers/decisions.csv ["nom_planche"]
#
#   - chemin/vers/decisions.csv : le fichier exporté par le bouton
#     « Exporter decisions.csv » de la planche de tri (tri_*.html).
#   - nom_planche (optionnel)   : ton nom / identifiant, pour distinguer les
#     contributions. Par défaut « anonyme ».
#
# Ce que fait le script :
#   1. copie le CSV dans handoff/decisions_recus/decisions_{timestamp}_{nom}.csv
#   2. git add + commit + push origin main
#
# Le CSV ne contient que « id_detection,decision » (oui/non/incertain) : aucune
# donnée personnelle (voir handoff/README.md). Ne renvoie jamais autre chose ici.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST_DIR="$SCRIPT_DIR/decisions_recus"

# --- arguments ---------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "ERREUR : chemin du decisions.csv manquant." >&2
  echo "Usage : $0 chemin/vers/decisions.csv [\"nom_planche\"]" >&2
  exit 1
fi

SRC="$1"
NOM="${2:-anonyme}"

if [[ ! -f "$SRC" ]]; then
  echo "ERREUR : fichier introuvable : $SRC" >&2
  exit 1
fi

# nettoyage du nom (garder lettres/chiffres/tiret/underscore)
NOM_CLEAN="$(printf '%s' "$NOM" | tr -c 'A-Za-z0-9_-' '_' )"
[[ -z "$NOM_CLEAN" ]] && NOM_CLEAN="anonyme"

TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$DEST_DIR"
DEST="$DEST_DIR/decisions_${TS}_${NOM_CLEAN}.csv"

cp "$SRC" "$DEST"
echo "Copié : $DEST"

# --- git ---------------------------------------------------------------------
cd "$REPO_DIR"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "AVERTISSEMENT : pas un dépôt git ici — fichier copié mais non versionné." >&2
  echo "Envoie directement $DEST à l'équipe par un autre biais." >&2
  exit 0
fi

git add "$DEST"

if git diff --cached --quiet; then
  echo "Rien de nouveau à committer (fichier identique à un envoi précédent ?)."
  exit 0
fi

git commit -m "Décisions de tri reçues : $(basename "$DEST")"
echo "Commit créé."

# push best-effort : si pas de droits / pas de remote configuré, on ne plante pas
if git push origin main; then
  echo "Poussé sur origin/main. Merci !"
else
  echo "AVERTISSEMENT : le push a échoué (pas de droits push ou git non configuré ?)." >&2
  echo "Le commit est fait en local. Envoie $DEST à l'équipe par un autre biais," >&2
  echo "ou demande un accès push au dépôt." >&2
  exit 0
fi
