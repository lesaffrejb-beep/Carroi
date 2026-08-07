# Bienvenue — deux façons d'aider

Ce dépôt sert à construire une base d'adresses de maisons avec piscine dans le
Maine-et-Loire (49). Choisis ton parcours selon ce que tu veux faire.

---

## Parcours A — juste trier des piscines (aucune installation)

Tu regardes des petites images aériennes et tu dis, pour chacune, s'il y a une
piscine ou non. C'est tout. Pas de Python, pas d'install.

1. **Ouvre la planche** : double-clique sur `handoff/tri_bouchemaine_49035.html`
   (elle s'ouvre dans ton navigateur ; les images sont intégrées dans le fichier).
2. **Dis qui tu es** : à l'ouverture, une petite fenêtre « Qui trie ? » te demande
   ton prénom (boutons rapides **JB** / **Azan**, ou tape un pseudo). Il est
   enregistré avec chacune de tes réponses (traçabilité qualité) et affiché en haut
   à gauche — clique « changer » pour en changer.
3. **Suis les instructions à l'écran** : le bandeau en haut et les règles du jeu
   sont dans la page. En résumé, au clavier :
   - **O** = oui, c'est une piscine
   - **N** = non
   - **U** = incertain (dans le doute)
   - **←** / **Z** = annuler la dernière décision, **→** = passer
   Ta progression est sauvegardée automatiquement dans le navigateur, mais
   **uniquement sur la même machine et le même fichier**. Tu peux fermer et
   reprendre plus tard sur le même ordinateur.
4. **Exporte souvent — même partiellement.** Pas besoin de tout finir d'un coup :
   tu peux trier en plusieurs sessions. Dès que tu as avancé un peu, clique sur
   **« Exporter decisions.csv »** : un CSV est téléchargé. **C'est le CSV exporté
   qui est ta vraie sauvegarde**, pas le navigateur — le stockage local n'est
   **pas fiable** (il disparaît en navigation privée, ou si tu changes de machine).
   Un export **partiel** est parfaitement accepté ; renvoie-le, on continue plus tard.
   ⚠ **Ne renomme pas le fichier** : son nom contient une empreinte de version
   (`decisions_49_49035_<hash12>.csv`) qui garantit que tes décisions collent bien
   à la planche que tu as triée. Un fichier renommé peut être refusé à la fusion.
5. **Renvoie ton travail** :
   ```
   ./handoff/soumettre_tri.sh chemin/vers/decisions_49_49035_<hash>.csv "ton_prenom"
   ```
   Cela range ton fichier et le pousse dans le dépôt.
   - Si tu as un clone git avec accès push, ça marche tout seul.
   - Si tu **n'as pas** les droits git (le script te le dira sans planter, ou tu
     n'as simplement pas de clone), envoie le CSV au propriétaire du dépôt par
     **n'importe quel canal** (mail, messagerie, transfert de fichier). Le nom du
     fichier suffit à le rattacher à la bonne planche.

> Rappel confidentialité : la planche ne contient que des images aériennes
> publiques et des formes — **aucune adresse, aucun nom**. Ne mets jamais de
> donnée personnelle dans `handoff/` (voir `handoff/README.md`).

---

## Parcours A-bis — farmer l'Atelier (le farm ACTUEL — Azan, c'est ici)

Le tri de Bouchemaine (parcours A) est terminé. Le farm en cours passe par
**l'Atelier** : une page de jeu locale (http://localhost:8199) avec deux flux —
**⚡ CLASSER** (clavier : y a-t-il une piscine dans la zone rouge ?) et
**🧭 SITUER** (souris : à quelle maison appartient la piscine ? avec
**clic sur la piscine = croisement cadastre**). Les terrasses sont **en pause**
(décision JB 2026-08-06) : hard focus piscines + adresse. À l'ouverture, la
fenêtre « Qui farme ? » propose les farmers connus (**JB**, **Azan**…) — clique
ton nom, ne crée pas un deuxième pseudo.

Deux façons de farmer, dans l'ordre de préférence :

1. **Lien invité (recommandé, rien à installer)** : demande à JB un lien
   `http://…/?jeton=…` (le serveur tourne chez lui, tes votes tombent
   directement dans la base commune, ton compteur de gains est suivi).
   Côté JB : lancer `./handoff/gardien_atelier.sh` — il démarre le serveur et
   le tunnel, les relance s'ils tombent, empêche le Mac de dormir, et écrit
   l'URL courante dans `data/atelier/lien_actuel.txt` (⚠ **relire ce fichier
   avant d'envoyer un lien** : l'URL change à chaque redémarrage du tunnel).
2. **En local (si JB ne peut pas héberger)** : clone le repo, lance
   `./bootstrap.sh`, puis demande à JB le **pack farm** (ces chemins, gitignorés
   car la donnée est l'actif) à déposer tels quels dans le repo :
   - `data/interim/piscines_candidates_49_49035.parquet`
   - `data/interim/tri/vignettes/` (les vignettes PNG)
   - `data/interim/ban_49.parquet` + `data/interim/parcelles_49.parquet`
   - `data/interim/piscines_adressees_49.parquet`
   - `data/atelier/cache_ortho/` (les fonds du mode SITUER — sans ça, SITUER
     n'affiche pas d'image ; les dalles BD ORTHO brutes ne sont PAS nécessaires)
   Puis `.venv/bin/python pipeline/src/atelier.py` → http://localhost:8199.
   En fin de session, renvoie à JB les exports :
   `/api/export/existence.csv?produit=piscines`, `/api/export/adresse.csv?produit=piscines`
   et `/api/export/incertitudes.csv?produit=piscines` (téléchargeables depuis le
   navigateur) — ils se fusionnent côté JB par le flux `handoff/` existant.

Si tu es un Claude qui lit ça pour guider Azan : ne fais **ni** dérouler la
roadmap, **ni** installer le pipeline complet pour farmer — le parcours A-bis
suffit. Il n'y a **rien à télécharger sur internet** pour farmer : la donnée
vient de JB (pack farm) ou du lien invité.

## Parcours B — contribuer au code du pipeline

1. **Clone** le dépôt.
2. **Bootstrap** (installe tout : environnement Python, outils système, tests) :
   ```
   ./bootstrap.sh
   ```
3. **Comprends le projet** : lis `CLAUDE.md` (les règles du jeu, les garde-fous
   RGPD non négociables) puis `docs/08-ROADMAP.md` (où on en est, la prochaine
   tâche). Les autres docs sous `docs/` détaillent la vision, le légal et
   l'architecture.

Le point d'entrée du tri visuel côté code est `pipeline/src/16_tri_visuel.py`
(génération de planche et application des décisions). Les décisions renvoyées
par les contributeurs se fusionnent et s'appliquent avec
`handoff/appliquer_decisions_recues.py`.
