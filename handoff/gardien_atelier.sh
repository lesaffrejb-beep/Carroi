#!/bin/bash
# Gardien de l'Atelier en ligne : maintient le serveur ET le tunnel vivants
# pendant qu'un farmer distant travaille (retour JB 2026-08-06 : « maintient le
# lien »). Sans ça, un serveur qui tombe = un farmer bloqué sans explication, et
# un tunnel qui redémarre = une URL qui change en silence.
#
#   ./handoff/gardien_atelier.sh            # démarre et surveille
#   cat data/atelier/lien_actuel.txt        # l'URL à donner aux farmers
#
# L'URL est réécrite dans lien_actuel.txt à CHAQUE changement : c'est la source
# de vérité à relire avant d'envoyer un lien à quelqu'un.
set -u
cd "$(dirname "$0")/.."
PORT=8199
LIEN_F="data/atelier/lien_actuel.txt"
LOG_TUNNEL="/tmp/cloudflared_atelier.log"
mkdir -p data/atelier

demarrer_serveur() {
  echo "$(date '+%H:%M:%S') serveur absent → démarrage"
  .venv/bin/python pipeline/src/atelier.py > /tmp/atelier.log 2>&1 &
  for _ in $(seq 1 60); do
    curl -sf -o /dev/null "http://localhost:$PORT/" && return 0
    sleep 1
  done
  echo "$(date '+%H:%M:%S') ÉCHEC : le serveur ne répond pas (voir /tmp/atelier.log)"
  return 1
}

demarrer_tunnel() {
  echo "$(date '+%H:%M:%S') tunnel absent → démarrage"
  pkill -f "cloudflared tunnel --url http://localhost:$PORT" 2>/dev/null
  : > "$LOG_TUNNEL"
  cloudflared tunnel --url "http://localhost:$PORT" > "$LOG_TUNNEL" 2>&1 &
  for _ in $(seq 1 40); do
    URL=$(grep -o "https://[a-z0-9-]*\.trycloudflare\.com" "$LOG_TUNNEL" | head -1)
    [ -n "${URL:-}" ] && break
    sleep 1
  done
  if [ -z "${URL:-}" ]; then
    echo "$(date '+%H:%M:%S') ÉCHEC : pas d'URL de tunnel (voir $LOG_TUNNEL)"
    return 1
  fi
  echo "$URL" > "$LIEN_F"
  echo "$(date '+%H:%M:%S') NOUVELLE URL : $URL"
  echo "   (les liens invités deviennent $URL/?jeton=…)"
  return 0
}

# Empêche la veille tant que le gardien tourne : un Mac endormi = un farmer
# distant coupé net.
caffeinate -dimsu -w $$ &

echo "Gardien démarré (Ctrl-C pour arrêter). Lien courant : $LIEN_F"
while true; do
  # --fail : un code HTTP d'erreur (530 = tunnel mort côté Cloudflare, 502…)
  # doit compter comme un échec de curl, sinon le gardien croit le tunnel
  # vivant alors qu'il ne répond qu'une page d'erreur (bug vécu 2026-08-07 :
  # 33 min sans relance, lien mort donné à un farmer).
  curl -sf -o /dev/null --max-time 10 "http://localhost:$PORT/" || demarrer_serveur
  URL=$(cat "$LIEN_F" 2>/dev/null || true)
  if [ -z "${URL:-}" ] || ! curl -sf -o /dev/null --max-time 20 "$URL/"; then
    demarrer_tunnel
  fi
  sleep 60
done
