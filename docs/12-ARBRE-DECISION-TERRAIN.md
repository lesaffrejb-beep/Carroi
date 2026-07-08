# Arbre de décision terrain — « si ça, alors ça »

> **Décidé à froid le 2026-07-08, AVANT le premier retour terrain**, pour que les décisions
> chaudes soient des exécutions, pas des débats. Chaque branche s'appuie sur la grille de
> consignation `11` §6 (`sales/prospection_d0.csv`). Toute décision prise via cet arbre se
> consigne dans `08-ROADMAP.md` (journal) avec les chiffres qui l'ont déclenchée.
> Les seuils (500 €, 3/5, 10 RDV…) sont ceux déjà actés dans `09` §4 et `10`.

## 1. Après D0 (5 appels de pré-vente)

```
D0 : 5 appels pisciniers (grille 11 §6 remplie)
│
├─ A. ≥3/5 intérêt fort (interet ≥ 2) ET prix_accepte ≥ 500 €
│   → GO PLEIN : phases A+B à fond [OPUS], RDV bookés pour sept.-oct.
│     Viser 2 pré-commandes signées avant même la base (bon annulable, 11 §3).
│     Ne RIEN changer au plan.
│
├─ B. Intérêt réel (≥3/5 interet ≥ 2) MAIS prix bloqué 150-400 €
│   → Le fichier seul est un produit à 300 €. Deux ripostes À TESTER dans les
│     appels 6-10 (on étend D0, on ne pivote pas encore) :
│     B1. Offre « campagne clé en main » (fichier + impression + envoi routeur,
│         facturé au pli) : le prix psychologique d'une CAMPAGNE est 3-5× celui
│         d'un fichier. Si ≥2/5 mordent → le business devient opérateur de
│         prospection, le fichier devient un coût interne. Marge supérieure,
│         travail récurrent — assumer ce choix explicitement dans 00-VISION.
│     B2. Monter en gamme d'acheteur : mêmes 5 appels vers pergolistes/PAC
│         (panier moyen client final 2-4× piscinier) et abris de piscine.
│
├─ C. « Sans nom/téléphone, ça ne vaut rien » majoritaire (canal_envisage = aucun)
│   → Pivot de CIBLE, pas de produit. Le fichier d'adresses est la matière
│     première de quelqu'un d'autre :
│     C1. Sièges de réseaux/franchises et fabricants (voir §3) — ils ont des
│         équipes marketing qui savent exploiter un fichier postal.
│     C2. Opérateurs de mailing/routeurs locaux et agences de com : leur vendre
│         la donnée en marque blanche (ils la revendent dans leurs campagnes).
│     C3. Si C1+C2 échouent aussi → le modèle « adresses sans contact » est
│         invalidé : STOP produit 1 en l'état, réunion stratégique humaine.
│         (Ne PAS céder à la tentation d'ajouter des données nominatives :
│         garde-fou n°1, non négociable — c'est le modèle qu'on change, pas
│         la ligne rouge.)
│
└─ D. Zéro intérêt, même pas de curiosité (rare : un appel à froid qui propose
    « les adresses des piscines » intrigue toujours)
    → Vérifier le script avant de conclure (10 appels min., créneaux 12-14h/18h+).
      Si confirmé : pivot vertical direct (P3 solaire vers installateurs PV —
      marché dopé aux aides, acheteurs plus gros) sans finir la base piscines.
```

## 2. Après les RDV de preuve (base construite, protocole `00`/`07`)

```
10 RDV menés (règle 09 §4)
│
├─ ≥2 ventes ET prix moyen ≥ 500 € → industrialiser : B5-B6 département complet,
│   puis exclusivités au plus offrant, puis réplication 44/85/72 dès 5 ventes.
│
├─ ≥2 ventes MAIS prix < 300 € → volume : automatiser l'export, vendre en
│   non-exclusif large, et pousser l'option clé en main pour remonter le panier.
│   L'exclusivité reste à ×2,5 minimum ou ne se vend pas.
│
├─ 1 vente ou 0, objection dominante = confiance/qualité → revenir sur B2-terrain
│   (précision réelle), resserrer sur confiance haute, refaire 5 RDV. Une seule
│   itération de ce type autorisée (5 jours max, règle 09 §4).
│
└─ <2 ventes, objection dominante = « pas besoin / pas de budget » → pivot P2/P3
    financé par ce qu'on a appris : les pergolistes ont été approchés en B2 ?
    sinon 5 appels D0 pergolistes AVANT de coder quoi que ce soit pour P2.
```

## 3. Options à plus gros ticket (exploration 2026-07-08 — à activer selon les branches)

Classées par ticket potentiel × vitesse d'accès. Aucune ne se lance sans passer par
un D0 dédié (5 appels). Toutes respectent les garde-fous (adresses sans données nominatives).

| Option | Acheteur | Ticket estimé | Vitesse | Risque | Déclencheur |
|---|---|---|---|---|---|
| **Réseaux & franchises (siège)** : Desjoyaux, Waterair, Mondial Piscine, réseaux d'abris | Direction marketing nationale | 5–30 k€ (multi-départements d'un coup) | Lente (cycle 3-6 mois) mais UN deal = une année de CA local | Négociation asymétrique (ils peuvent copier) → vendre l'exclusivité de fraîcheur + le multi-départements déjà prêt | Branche C1, ou dès 3 ventes locales (crédibilité) |
| **Installateurs PAC & énergéticiens** : piscine = proxy parfait (consommation élec + pouvoir d'achat + extérieur) | PME PAC, +gros que pisciniers | 1–5 k€, récurrent | Rapide (mêmes appels D0) | Faible — même produit, autre pitch (« les maisons qui ont les moyens et une facture de chauffage de bassin ») | Branche B2, coût marginal quasi nul |
| **Campagne clé en main** (fichier + routeur postal) | Les mêmes TPE | ×3-5 le fichier, récurrent | Moyenne (trouver le routeur, 1 semaine) | Opérationnel : on devient prestataire, temps humain | Branche B1 — LE test prioritaire si le prix du fichier bloque |
| **Marque blanche data → agences/routeurs locaux** | Agences de com, Mediapost-like locaux | 1-3 k€/an/agence, récurrent | Moyenne | Cannibalise l'exclusivité locale — à cadrer contractuellement | Branche C2 |
| **P3 potentiel solaire toiture** (moteur `solaire.py` prêt) | Installateurs PV (marché aides d'État) | 1–5 k€, marché 20× pisciniers | Moyenne (détecteur pans de toit à coder [FABLE]) | Concurrence des cadastres solaires publics gratuits — vérifier couverture 49 AVANT (deepsearch) | Branche D, ou après 5 ventes P1 |
| **Collectivités / B2G** (parkings, imperméabilisation, piscines non déclarées) | Département, agglos | 5-20 k€/étude | Très lente (marchés publics, 6-18 mois) | Politique ; « piscines non déclarées » = terrain du fisc, image dangereuse | JAMAIS en année 1 ; réévaluer à 50 k€ de CA |
| **Assureurs / diagnostic risque** | Compagnies, courtiers | Potentiellement gros | Lente | **RGPD aggravé** (finalité d'évaluation du bien d'autrui, pas de prospection) → AIPD spécifique + avis avocat AVANT tout contact | Gelé jusqu'à avis avocat explicite |

**Règle transverse** : une option ne s'active que si (a) une branche de l'arbre la déclenche,
(b) le D0 dédié (5 appels) confirme, (c) la décision + les chiffres sont consignés dans `08`.
Jamais deux options en test simultanément (même discipline que « jamais deux détecteurs »).

## 4. Ce que l'humain doit rapporter du terrain (le minimum vital)

Pour que la session LLM suivante puisse exécuter cet arbre sans toi :
1. `sales/prospection_d0.csv` rempli (grille `11` §6) — même incomplet, même moche.
2. Les objections **mot pour mot** (pas résumées : le verbatim contient le pivot).
3. Le prix exact accepté ou refusé, par prospect.
4. Ton ressenti en une phrase par appel (« il a tiqué quand j'ai dit X ») — dans la colonne notes.
