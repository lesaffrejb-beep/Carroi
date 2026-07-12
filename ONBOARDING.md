# Bienvenue — deux façons d'aider

Ce dépôt sert à construire une base d'adresses de maisons avec piscine dans le
Maine-et-Loire (49). Choisis ton parcours selon ce que tu veux faire.

---

## Parcours A — juste trier des piscines (aucune installation)

Tu regardes des petites images aériennes et tu dis, pour chacune, s'il y a une
piscine ou non. C'est tout. Pas de Python, pas d'install.

1. **Ouvre la planche** : double-clique sur `handoff/tri_bouchemaine_49035.html`
   (elle s'ouvre dans ton navigateur ; les images sont intégrées dans le fichier).
2. **Suis les instructions à l'écran** : le bandeau en haut et les règles du jeu
   sont dans la page. En résumé, au clavier :
   - **O** = oui, c'est une piscine
   - **N** = non
   - **U** = incertain (dans le doute)
   - **←** / **Z** = annuler la dernière décision, **→** = passer
   Ta progression est sauvegardée automatiquement dans le navigateur : tu peux
   fermer et reprendre plus tard sur le même ordinateur.
3. **Exporte** : quand tu as fini (ou une bonne session), clique sur
   **« Exporter decisions.csv »**. Un fichier `decisions.csv` est téléchargé.
4. **Renvoie ton travail** :
   ```
   ./handoff/soumettre_tri.sh chemin/vers/decisions.csv "ton_prenom"
   ```
   Cela range ton fichier et le pousse dans le dépôt.
   - Si tu as un clone git avec accès push, ça marche tout seul.
   - Si tu **n'as pas** les droits git, le script te le dira sans planter :
     envoie simplement le `decisions.csv` à l'équipe par un autre biais (mail,
     messagerie...).

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
