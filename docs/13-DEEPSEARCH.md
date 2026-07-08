# Prompts de deepsearch (Gemini/Perplexity) — à lancer par l'humain

> Chaque prompt est autonome : copier-coller tel quel. **Coller les résultats dans
> `08-ROADMAP.md` (journal)** ou en commentaire de PR pour que la session LLM suivante
> les exploite. Priorité de haut en bas. Cocher quand fait.

## ① BD ORTHO 49 — URLs, format, millésimes (bloque B1) — PRIORITAIRE

> Je dois télécharger la BD ORTHO de l'IGN (orthophotos aériennes françaises) pour le
> département 49 (Maine-et-Loire), en RVB **et** en IRC (infrarouge couleur), résolution
> 20 cm, pour un traitement automatisé par script. Donne-moi, vérifié en 2026 :
> 1. Les URLs de téléchargement direct des dalles BD ORTHO D049 (RVB et IRC séparément) :
>    géoplateforme data.geopf.fr, cartes.gouv.fr, et le miroir files.opendatarchives.fr —
>    lequel marche le mieux en téléchargement scripté (wget/curl), et le schéma de nommage
>    exact des archives (millésime le plus récent pour le 49, format 7z ?).
> 2. Le format interne : JP2 (JPEG2000) ou GeoTIFF ? Taille et emprise d'une dalle
>    (1 km × 1 km ?), grille de nommage des fichiers, ordre des bandes du produit IRC
>    (le proche-infrarouge est-il en bande 1 ?), volume total pour un département.
> 3. **La date du millésime BD ORTHO actuel du 49 ET la date prévue du prochain survol**
>    (calendrier de renouvellement PVA/BD ORTHO par département).
> 4. Un moyen de télécharger seulement les dalles d'une commune (flux WMS/WMTS exclu —
>    il me faut les dalles brutes) ?

## ② LiDAR HD — dalles MNS/MNH du 49 (bloque le produit 2)

> L'IGN diffuse les produits dérivés LiDAR HD (MNS, MNT, MNH raster 0,5 m ou 1 m) en
> open data. Pour le département 49 (Maine-et-Loire), vérifié en 2026 :
> 1. URLs de téléchargement direct des dalles **MNS** et **MNH** (pas le nuage de points
>    LAZ brut) : cartes.gouv.fr / data.geopf.fr / diffusion-lidarhd — le chemin exact et
>    le schéma de nommage des dalles (1 km, GeoTIFF, Lambert-93 ?).
> 2. La couverture réelle du 49 : 100 % livré en dérivés raster ? Sinon quelles zones
>    manquent et faut-il rasteriser soi-même le LAZ (PDAL) ?
> 3. La date d'acquisition LiDAR du 49 (millésime à afficher dans les exports).

## ③ SITADEL — piscines neuves via permis de construire (produit « fraîcheur »)

> La base SITADEL (SDES, data.gouv.fr) recense les autorisations d'urbanisme françaises.
> Vérifié en 2026 : 1. Les déclarations préalables et permis pour PISCINES y sont-ils
> identifiables (champ nature/catégorie des travaux) ? 2. Quelle granularité d'adresse :
> adresse complète du terrain, parcelle cadastrale, ou seulement la commune ? (Les fichiers
> « à la commune » ne me servent pas — existe-t-il une version géolocalisée ou à la
> parcelle, même en accès restreint ?) 3. Licence exacte et fraîcheur (délai entre le
> dépôt du permis et l'apparition dans la base) ? 4. Alternatives open data pour détecter
> des piscines/constructions NEUVES à l'adresse près (DVF+, fichiers fonciers CEREMA ?).

## ④ Cadastre solaire public — concurrence gratuite du produit 3

> Avant de lancer un produit « potentiel solaire des toitures » payant en Maine-et-Loire :
> existe-t-il déjà un cadastre solaire public GRATUIT couvrant le 49 (Angers Loire
> Métropole, région Pays de la Loire, ou national type « potentiel solaire » de l'IGN /
> Enedis / Otovo…) ? Pour chacun : couverture géographique exacte, granularité (par pan
> de toit ?), les données sont-elles téléchargeables/réutilisables commercialement ou
> seulement consultables ? Verdict : un installateur PV du 49 a-t-il déjà accès gratuit
> à l'équivalent de ce que je vendrais ?

## ⑤ Datasets/poids publics de détection de piscines (option A, si B2-terrain plafonne)

> Liste les datasets annotés et modèles pré-entraînés PUBLICS de détection de piscines
> sur imagerie aérienne/satellite (Hugging Face, Kaggle, Zenodo, papers with code) :
> nom, taille, résolution des images, et surtout **licence exacte** (usage commercial du
> modèle entraîné autorisé ?). Inclure les datasets français (IGN/BD ORTHO) s'il en existe.

## ⑥ Routeurs postaux — coût réel de l'offre « campagne clé en main » (branche B1 de `12`)

> Pour envoyer des campagnes de courrier adressé B2C en France (500 à 5 000 plis par
> campagne, format lettre ou carte postale) : quels prestataires/routeurs acceptent les
> petits volumes en 2026 (Merci Facteur pro, Maileva, Mediapost, imprimeurs-routeurs
> régionaux Pays de la Loire) ? Prix indicatif TOUT COMPRIS par pli (impression couleur +
> mise sous pli + affranchissement) aux volumes 500 / 2 000 / 5 000, délais, et minimum
> de commande. API disponible ?

## ⑦ Concurrence directe — qui vend déjà des fichiers « propriétaires de piscine » ?

> En France en 2026, qui vend déjà des fichiers de prospection ciblant les propriétaires
> de piscines privées (courtiers en données, brokers B2B type Cartégie/Solvup/annuaires,
> plateformes de leads travaux) ? Pour chaque offre trouvée : ce qui est vendu exactement
> (avec ou sans coordonnées nominatives), le prix public s'il existe, la source annoncée
> des données. Même question pour « propriétaires de maisons avec jardin/terrasse ».
> Objectif : préparer la contre-objection « j'ai trouvé moins cher avec les téléphones ».

## Fait / résultats

| # | Lancée le | Résultat collé dans | Verdict en une ligne |
|---|---|---|---|
| ① | | | |
| ② | | | |
| ③ | | | |
| ④ | | | |
| ⑤ | | | |
| ⑥ | | | |
| ⑦ | | | |
