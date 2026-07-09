# Procédure de réclamation & d'opposition (pack incident)

> **DRAFT — à valider par avocat.** Deux procédures écrites à froid (pre-mortem `10` §9, §4) :
> (A) réclamation qualité « cette adresse est fausse » → remède + étiquette négative ;
> (B) opposition/droits **sans identité** (art. 11 RGPD). Objectif : traiter chaque
> signalement de façon traçable, rapide et gratuite. Une page. Canal unique d'entrée :
> `[opposition@<domaine>]` + formulaire `[URL]` + courrier `[ADRESSE]`.

## A. Réclamation qualité (ligne fausse)

Déclencheur : un client (ou un particulier) signale qu'une adresse livrée ne correspond pas
à un bien équipé (piscine absente, mauvaise parcelle…).

1. **Accuser réception** sous 48 h ouvrées.
2. **Vérifier** l'adresse sur l'orthophoto IGN (Géoportail) — c'est la source de vérité
   (protocole de preuve `00`).
3. **Remédier sous 90 jours** : remplacer la/les ligne(s) fausse(s) par des lignes valides
   équivalentes **ou** émettre un avoir au prorata. Consigner le remède.
4. **Capitaliser** : enregistrer le signalement dans `data/validation/reclamations.csv`
   comme **étiquette négative** (vérité terrain — c'est un actif de recalibration, pas un
   incident, `10` §4). Schéma minimal du fichier (hors git — voir `.gitignore`) :

   `date,adresse,commune,code_insee,motif,verdict_verif,remede,acheteur,export_ref`

   - `motif` : ce qu'affirme le réclamant (ex. « pas de piscine »)
   - `verdict_verif` : `confirmee_fausse` / `en_fait_juste` / `indeterminee` après contrôle
   - `remede` : `remplacement` / `avoir` / `aucun (ligne juste)`
5. **Réinjecter** en calibration : les lignes `confirmee_fausse` alimentent l'échantillon
   négatif du protocole qualité (`06`) et la révision des seuils si un motif se répète.

## B. Opposition & droits sans identité (art. 11 RGPD)

Déclencheur : une personne demande à ne plus figurer dans le fichier / exerce un droit
d'accès, de rectification ou d'effacement.

Principe : nous **ne détenons aucun nom**. Nous n'exigeons donc **aucune pièce d'identité**
et procédons par **matching sur la seule adresse postale** communiquée (art. 11 : le
responsable qui ne peut/n'a pas besoin d'identifier la personne traite la demande sur la
base des informations fournies).

1. **Accuser réception** sous 48 h ouvrées ; aucune justification demandée au requérant.
2. **Normaliser** l'adresse (BAN) et l'ajouter à `data/optout/optout.csv` (hors git). Ce
   fichier est le filtre permanent : **tous** les exports futurs l'excluent (garde-fou n°6,
   jamais désactivé).
3. **Propager aux acheteurs passés** : via `sales/registre.csv`, identifier les livraisons
   contenant cette adresse et **notifier chaque acheteur** de la retirer de ses
   exploitations (obligation contractuelle de répercussion).
4. **Répondre** au requérant : confirmation du retrait et rappel du droit de réclamation
   auprès de la CNIL. **Délai maximum : 1 mois.**
5. **Tracer** : conserver date, canal, adresse opposée et suite donnée (fiche n°3 du
   registre art. 30). L'entrée en liste d'opposition est **permanente par nature**.

## Points de vigilance

- Ne jamais demander l'identité pour un opt-out : ce serait une collecte contraire à la
  minimisation.
- Une réclamation qualité (A) qui est aussi une demande de retrait (B) déclenche **les deux**
  procédures.
- Toute réponse écrite reste factuelle et renvoie à la politique de confidentialité en ligne.
