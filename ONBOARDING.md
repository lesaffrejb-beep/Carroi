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
