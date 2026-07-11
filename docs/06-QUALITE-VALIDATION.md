# Qualité, validation & tatouage

> Rien ne se vend, rien ne se montre en RDV, tant que le protocole de ce document n'a pas été passé et ses résultats consignés dans `docs/08-ROADMAP.md`.

## 1. Métriques

- **Précision** (la seule qu'on vend) : parmi les adresses de la base, % dont l'attribut est vrai (piscine réellement présente / terrasse réellement ensoleillée). On **annonce la borne basse de l'intervalle de Wilson à 95 %**, jamais l'estimation ponctuelle `succès/n` (garde-fou n°7 « pas de sur-promesse » ; leçon état de l'art `15` §2). **Seuil de commercialisation : borne basse ≥ 95 %.**
- **Rappel** (usage interne) : % des piscines réelles qu'on a captées. On ne le promet jamais au client ("on ne garantit pas l'exhaustivité"), mais on le mesure sur 2–3 communes pour connaître notre couverture.
- **Qualité d'adressage** : % d'adresses de la base qui correspondent bien à la parcelle contenant la piscine (et pas au voisin). C'est LE risque du pipeline (jointure spatiale piscine→parcelle→adresse). Cible : ≥ 97 % sur l'échantillon contrôlé.

## 2. Protocole de validation (avant toute vente)

1. **Échantillon aléatoire** : tirer au hasard un échantillon de la base départementale (`random_state` fixé et consigné, pour reproductibilité). 100 lignes est le minimum ; **agrandir à 200-400** si l'on veut resserrer l'intervalle assez pour que la borne basse dépasse 95 % (à n = 100, la borne basse est sévère — voir §2 bis).
2. **Contrôle visuel humain** : pour chaque ligne, ouvrir l'adresse sur le Géoportail IGN (orthophoto la plus récente) et vérifier : (a) piscine visible, (b) piscine bien sur la parcelle de l'adresse, pas chez le voisin, (c) adresse plausible (pas un lieu-dit à 500 m).
   - C'est ~2 h de travail humain. Ne pas déléguer à un LLM sans vision fiable de l'orthophoto ; si un LLM le fait via captures d'écran, un humain re-vérifie 20 lignes derrière.
3. **Consigner** : taille de l'échantillon `n`, nombre de succès, estimation ponctuelle `p̂ = succès/n`, **et la borne basse de Wilson à 95 %** (= le taux annoncé, calculé par `common.borne_basse_wilson(succès, n)`), erreurs typiques, date, millésime des sources → tableau dans `08-ROADMAP.md` + fichier `data/validation/rapport-YYYYMMDD.md`.
4. Si la **borne basse < 95 %** : analyser les erreurs (piscines démontées depuis le millésime ? bassins d'ornement ? erreurs de jointure ?), corriger les filtres (surface min/max, distance max piscine→bâtiment…), relancer. Itérer. Ne jamais annoncer le point pour « rattraper » un intervalle trop large — c'est agrandir `n` qui resserre l'intervalle, pas changer le chiffre annoncé.

### 2 bis. Pourquoi la borne basse, et pourquoi `n` compte

On mesure une précision sur un échantillon fini : l'estimation ponctuelle `p̂` n'est
qu'un point, avec une incertitude d'autant plus grande que `n` est petit. Annoncer `p̂`
(« 96 % ! ») serait une sur-promesse au sens du garde-fou n°7. On annonce donc la **borne
basse** de l'intervalle de Wilson à 95 % : le chiffre en dessous duquel la vraie précision
n'a que 2,5 % de chances de se trouver.

Ordre de grandeur (via `common.borne_basse_wilson`) : 96/100 → ponctuel 96 %, borne
basse ≈ 90 % ; 196/200 (même 98 % ponctuel) → borne basse ≈ 95 %. Conséquence pratique :
pour **annoncer** ≥ 95 % de façon défendable, il faut un échantillon plus grand que 100, pas
un meilleur discours. Wilson (et non Wald) parce qu'au voisinage de p = 1 et à petit `n`,
l'approximation de Wald sous-couvre et peut sortir de [0, 1].

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
