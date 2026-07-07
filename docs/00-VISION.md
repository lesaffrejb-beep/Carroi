# Vision & Modèle économique

> **Ce document est la référence stratégique du projet. Toute session LLM qui travaille sur ce repo doit le lire en premier (après CLAUDE.md).**

## Le produit

On vend de la **donnée qualifiée**, pas du logiciel. Deux produits, construits sur le même socle technique (département 49 — Maine-et-Loire — comme territoire pilote, réplicable ailleurs) :

### Produit 1 — Base "Piscines" (à construire EN PREMIER)
Une base d'adresses postales de propriétés équipées d'une piscine privée, avec attributs :
- Adresse postale normalisée (BAN)
- Commune, code INSEE, coordonnées GPS
- Surface approximative de la piscine (m²)
- Type probable (enterrée / hors-sol si distinguable)
- Score de confiance de la détection

**Clients cibles** : pisciniers (entretien, rénovation, sécurité), vendeurs d'abris/couvertures, paysagistes, vendeurs de pompes à chaleur piscine, magasins de produits d'entretien.
**Pitch de vente** : *« J'ai la liste des X adresses avec piscine dans un rayon de 30 km autour de votre entreprise. »*

### Produit 2 — Base "Terrasses ensoleillées / potentiel pergola" (PHASE 2)
Une base d'adresses de maisons avec espace extérieur exposé sud/sud-ouest à fort ensoleillement, sans ombrage existant détecté :
- Adresse postale normalisée
- Score d'ensoleillement de la zone terrasse/jardin (heures de soleil annuelles estimées)
- Orientation de la façade jardin
- Présence détectée d'une terrasse minérale (optionnel, phase avancée)

**Clients cibles** : installateurs de pergolas (bioclimatiques notamment), storistes, vérandalistes, paysagistes.
**Pitch** : *« Voici les adresses où une pergola se vend : terrasse plein sud, pas d'ombrage, maison individuelle. »*

## Pourquoi Piscines d'abord

1. **La détection est faisable avec des moyens maîtrisés** : aucune base ouverte ne liste les piscines privées (vérifié — voir `02-DATA-SOURCES.md`), mais une piscine se détecte très bien sur l'orthophoto IGN 20 cm (donnée ouverte, revendable) avec un modèle de segmentation standard — c'est exactement ce qu'a fait le fisc. Problème visuellement simple (tache turquoise géométrique), abondamment documenté.
2. **La preuve est triviale en RDV** : ouvrir une vue aérienne sur 5 adresses au hasard de la base et montrer la piscine. Effet démonstration immédiat.
3. **Le marché est dense** : le 49 compte des dizaines de milliers de piscines privées (~3,5 M en France) ; les pisciniers locaux sont nombreux et faciles à identifier.
4. **La barrière à l'entrée protège le prix** : puisque la donnée n'existe pas toute faite, un concurrent doit refaire le travail de détection. C'est un vrai actif, pas un re-packaging d'open data.

Le produit Terrasses est plus différenciant (personne d'autre ne le fait) mais plus complexe et plus incertain — on le finance avec les revenus du produit Piscines.

## Modèle de revenus

| Offre | Description | Prix indicatif (à valider en RDV) |
|---|---|---|
| Extract local non-exclusif | Adresses piscines dans un rayon de 30 km autour du client | 500–1 500 € selon volume |
| Département complet non-exclusif | Tout le 49 | 2 000–4 000 € |
| **Exclusivité sectorielle locale** | Un seul piscinier servi par zone | ×3 à ×5 le prix non-exclusif |
| Abonnement fraîcheur | Mise à jour annuelle (nouvelles piscines = prospects chauds "construction récente") | 30–40 % du prix initial / an |

Règles :
- **Ne jamais vendre le fichier brut complet à bas prix.** On vend des extraits territorialisés. Le fichier complet reste l'actif.
- **L'exclusivité fait exploser le prix** mais gèle la zone : ne l'accorder que par écrit, par secteur d'activité ET par zone géographique, avec durée limitée (12 mois).
- Les "nouvelles piscines" (détectées entre deux millésimes de données) sont le segment le plus chaud : propriétaire qui vient d'investir → besoins immédiats (entretien, abri, sécurité, chauffage). Prix premium.

## Protocole de preuve (RDV)

Objectif du POC en rendez-vous : prouver en < 5 minutes que la base est vraie.

1. Demander au prospect sa commune ou son adresse d'entreprise.
2. Sortir l'extrait rayon 30 km (préparé à l'avance ou généré sur place — voir `pipeline/`).
3. Choisir **4–5 adresses au hasard** (laisser le prospect choisir les lignes lui-même : ça tue l'objection "tu as trié les meilleures").
4. Ouvrir chaque adresse dans le Géoportail IGN (vue aérienne) → la piscine est visible.
5. Annoncer le taux de précision mesuré (voir `06-QUALITE-VALIDATION.md` — on ne promet que ce qu'on a mesuré).
6. Closer sur un extrait local, upsell exclusivité.

**Garde-fou** : ne jamais montrer/vendre la base avant d'avoir passé la validation qualité (précision ≥ 95 % mesurée sur échantillon aléatoire). Une seule démo ratée devant un prospect tue la réputation locale.

## Ce qu'on ne fait PAS (limites du modèle)

- On ne vend **jamais** de noms, téléphones, emails de particuliers. Uniquement des adresses postales + attributs du bien. (Cadre légal : voir `03-LEGAL-RGPD.md` — c'est ce qui rend le modèle défendable.)
- On ne prétend pas à l'exhaustivité ni au 100 % : on vend un taux de précision mesuré.
- On ne démarche pas les particuliers nous-mêmes : nos clients sont des **entreprises** (B2B). Ce sont elles, responsables de traitement, qui prospectent.
- Pas de scraping de services propriétaires (Google Maps, etc.) en violation de leurs CGU. Le socle est en open data (licences compatibles avec la revente — vérifié dans `03-LEGAL-RGPD.md`).
