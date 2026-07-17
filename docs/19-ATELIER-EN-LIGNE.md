# 19 — Atelier en ligne : multi-user, PoW rémunéré, et la suite techno

> Créé 2026-07-17 (demande JB : farm multi-user en ligne, amis rémunérés au
> proof-of-work). Statut : ARCHITECTURE — l'implémentation est découpée en
> tâches en fin de doc.

## 1. Ce qu'on a déjà (et qui est déjà multi-user)

Le schéma de données est prêt : chaque vote porte `(produit, mode, id_item,
reponse, trieur, ts)`. La rémunération, l'anti-fraude et les stats par personne
sont des REQUÊTES, pas des refontes. Il manque : l'accès distant, l'identité
non-falsifiable, et la concurrence d'écriture.

## 2. Architecture cible (v1 en ligne, ~simple)

- **Un seul serveur** (la machine de JB via tunnel Cloudflare/Tailscale Funnel,
  ou VPS à 5 €). SQLite reste suffisant en WAL (écritures = quelques/s).
- **Identité par lien-token** : JB génère `https://…/?t=abc123` par ami
  (table `trieurs(token, nom, taux_ct_par_label)`). Pas de mot de passe, pas
  d'email : un lien = une personne. Révocable.
- **Anti-fraude = PoW par l'accord** (comme reCAPTCHA/MTurk) :
  1. **Questions d'or** : items à ≥3 votes 100 % accord, réinjectés ~1/10 sans
     que le trieur le sache. Taux d'or < 90 % → session non payée, token gelé.
  2. **Cadence** : < 0,8 s/vote soutenu = robot → gel.
  3. **Accord a posteriori** : payé = vote CONFORME au consensus final (ou
     minoritaire mais « défendable » : l'item était contesté).
- **Rémunération** : `votes_valides × taux` ; tableau de bord par trieur
  (déjà : stats_trieur). Référence coût mesuré : JB = 2,6 s/label → à 3 ct/label
  un ami motivé gagne ~40 €/h ; à 1 ct ~14 €/h. Recommandation : **1,5 ct/label
  + bonus qualité** (×1,5 si or ≥ 98 %) — sous le coût MTurk qualité équivalente.
- **Ce qui NE change PAS** : votes append-only, moins-vu-d'abord, multi-passes,
  exports consensus. Le pré-tri (22) réduit le volume À PAYER : on ne met en
  ligne QUE la bande farm.

## 3. Grille tarifaire produit (données, hors annotation)

Coûts mesurés : farm ~9 min/commune post-pré-tri, pipeline automatique.
Valeur client : 1 piscine rénovée = 5-15 k€ de CA pisciniste ; 1 vente sur 100
adresses paye la liste 50×.

| Offre | Contenu | Prix indicatif |
|---|---|---|
| Commune témoin | ~230 adresses vérifiées 2× humain | **190 €** |
| Pack 5 communes (couronne) | ~1 000 adresses | **690 €** |
| Département 49 | 15-25 k adresses (post-CoSIA) | **2 900 €** ; **+1 500 €/an** mise à jour millésime |
| Exclusivité secteur (1 métier, 1 zone) | la liste + personne d'autre 12 mois | **×2,5** le prix zone |
| Terrasses/pergolas (produit 2) | même grille, lancement −30 % early | — |

Plancher : jamais < 0,50 €/adresse vérifiée (coût de re-création concurrent >
1 €). Tout export tatoué (adresses-témoins, doctrine 06/16).

## 4. Veille techno à faire (session dédiée, WebSearch/WebFetch)

- Repos : Label Studio, CVAT, Argilla (mécaniques d'agrément), segment-geospatial,
  torchgeo, DINOv2/SAM2 têtes légères, doft/obia piscines.
- Papiers : active learning for aerial imagery, label aggregation (Dawid-Skene —
  mieux que la majorité simple quand ≥3 trieurs !), test-time augmentation coût/qualité.
- Écosystème FR : CoSIA (retours d'usage), Foncier Innovant (méthodo publiée),
  data.gouv réutilisations piscines.

## 5. Tâches

- **[FABLE] atelier-en-ligne v1** : table trieurs+tokens, WAL, questions d'or,
  page « mon compteur / mes gains », gel auto. (~1 session)
- **[OPUS] tunnel** : Cloudflare tunnel + doc d'installation amis (lien+3 lignes).
- **[FABLE] Dawid-Skene** : remplacer la majorité simple quand ≥3 trieurs.
- **[OPUS] veille** : exécuter §4, consigner ici.
