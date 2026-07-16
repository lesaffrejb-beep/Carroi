#!/usr/bin/env bash
# Double-clic = l'Atelier s'ouvre. C'est le SEUL écran où JB doit interagir.
# Démarre le serveur s'il ne tourne pas déjà, puis ouvre le navigateur.
cd "$(dirname "$0")"
if ! curl -s -o /dev/null --max-time 2 http://localhost:8199/api/produits; then
  nohup .venv/bin/python pipeline/src/atelier.py --port 8199 >> /tmp/atelier.log 2>&1 &
  echo "Démarrage de l'Atelier (10 s)…"
  for i in $(seq 1 30); do
    sleep 1
    curl -s -o /dev/null --max-time 1 http://localhost:8199/api/produits && break
  done
fi
open http://localhost:8199
