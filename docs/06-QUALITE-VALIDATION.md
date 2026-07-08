# Qualité, validation & tatouage

> Rien ne se vend, rien ne se montre en RDV, tant que le protocole de ce document n'a pas été passé et ses résultats consignés dans `docs/08-ROADMAP.md`.

## 1. Métriques

- **Précision** (la seule qu'on vend) : parmi les adresses de la base, % dont l'attribut est vrai (piscine réellement présente / terrasse réellement ensoleillée). **Seuil de commercialisation : ≥ 95 %.**
- **Rappel** (usage interne) : % des piscines réelles qu'on a captées. On ne le promet jamais au client ("on ne garantit pas l'exhaustivité"), mais on le mesure sur 2–3 communes pour connaître notre couverture.
- **Qualité d'adressage** : % d'adresses de la base qui correspondent bien à la parcelle contenant la piscine (et pas au voisin). C'est LE risque du pipeline (jointure spatiale piscine→parcelle→adresse). Cible : ≥ 97 % sur l'échantillon contrôlé.

## 2. Protocole de validation (avant toute vente)

1. **Échantillon aléatoire** : tirer 100 lignes au hasard de la base départementale (`random_state` fixé et consigné, pour reproductibilité).
2. **Contrôle visuel humain** : pour chaque ligne, ouvrir l'adresse sur le Géoportail IGN (orthophoto la plus récente) et vérifier : (a) piscine visible, (b) piscine bien sur la parcelle de l'adresse, pas chez le voisin, (c) adresse plausible (pas un lieu-dit à 500 m).
   - C'est ~2 h de travail humain. Ne pas déléguer à un LLM sans vision fiable de l'orthophoto ; si un LLM le fait via captures d'écran, un humain re-vérifie 20 lignes derrière.
3. **Consigner** : précision mesurée, erreurs typiques rencontrées, date, millésime des sources → tableau dans `08-ROADMAP.md` + fichier `data/validation/rapport-YYYYMMDD.md`.
4. Si précision < 95 % : analyser les erreurs (piscines démontées depuis le millésime ? bassins d'ornement ? erreurs de jointure ?), corriger les filtres (surface min/max, distance max piscine→bâtiment…), relancer. Itérer.

## 3. Filtres de qualité intégrés au pipeline (piscines)

Justification détaillée dans `04-PIPELINE-PISCINES.md` ; résumé des garde-fous :
- Surface : garder 8 m² ≤ surface ≤ 150 m² (élimine pataugeoires/bassins d'ornement et bassins agricoles/publics).
- Exclure les piscines sur parcelles sans bâtiment d'habitation à proximité (< 60 m) — élimine bassins isolés.
- Exclure les piscines **collectives/publiques** : parcelles de campings, hôtels, équipements publics (croisement avec les zones d'activité BD TOPO + OSM `tourism=camp_site|hotel`, `leisure=sports_centre`). Un piscinier veut des particuliers.
- Dédoublonnage : une adresse = une ligne, même si plusieurs polygones piscine sur la parcelle (garder le plus grand).
- Filtre opt-out : `data/optout/optout.csv` soustrait de chaque export, systématiquement.

## 4. Score de confiance

Chaque ligne porte un score (haute/moyenne/basse confiance) selon :
- distance piscine ↔ bâtiment le plus proche de la parcelle,
- qualité du géocodage BAN (adresse à la parcelle vs interpolée),
- ambiguïté de la jointure (piscine chevauchant deux parcelles).

Les exports commerciaux **par défaut ne contiennent que haute + moyenne confiance**. La basse confiance reste en interne.

## 5. Tatouage des fichiers livrés (anti-revente)

Objectif : détecter si un acheteur revend/partage le fichier, et le prouver.

Mécanisme (léger, sans fausses données — on ne vend pas d'adresses bidon) :
- Pour chaque livraison, générer une **empreinte de formatage** unique : variations invisibles mais déterministes propres à l'acheteur — ordre de tri secondaire, casse de certaines abréviations de voie ("Av." vs "AV" vs "Avenue") sur un sous-ensemble de lignes choisi par hash de l'ID acheteur, arrondi des coordonnées à la 5e vs 6e décimale sur certaines lignes.
- Consigner l'empreinte dans `sales/registre.csv` (hors git). Un fichier retrouvé dans la nature se réattribue par comparaison.
- Le contrat de licence mentionne explicitement le tatouage (effet dissuasif) sans en décrire le mécanisme.

## 6. Fraîcheur

- Noter le millésime de chaque source dans chaque export (imposé par le script d'export).
- À chaque nouveau millésime IGN : relancer le pipeline, faire le **diff** ancien/nouveau → le fichier "nouvelles piscines" (prospects chauds, prix premium) et la liste des disparues (à retirer des bases vendues en abonnement).
