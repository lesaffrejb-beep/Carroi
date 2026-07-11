# DS3 — BD ORTHO 49 : URLs, format, millésimes (prompt ① — débloque B1)

> Collé le 2026-07-11 (Gemini 3.5 Pro). Voir doctrine de lecture dans [README.md](README.md).

## Ce qu'on en retient (analyse 2026-07-11)

**B1 est débloqué. À encoder dans le téléchargeur (et à vérifier au premier run —
consigner les URLs réelles dans la roadmap comme prévu) :**
- Archive départementale RVB :
  `https://data.geopf.fr/telechargement/download/BDORTHO/BDORTHO_1-0_RVB-0M20_JP2-E080_LAMB93_D049_{MILLESIME}-01-01/BDORTHO_1-0_RVB-0M20_JP2-E080_LAMB93_D049_{MILLESIME}-01-01.7z.001`
  (IRC : remplacer `RVB` par `IRC`). Volumes `.7z.001`, `.002`, … — boucler jusqu'au 404.
  Miroir : `http://files.opendatarchives.fr/professionnels.ign.fr/orthohr/…` (mêmes noms).
- Format interne : **JP2 (JPEG2000), profil E080**, dalle 1 km × 1 km, 5000 × 5000 px,
  Lambert-93, ~15-20 Mo/dalle, ~8 000-8 500 dalles pour le 49, **~150-170 Go par spectre**
  (≈ 300 Go RVB+IRC). Nommage interne : `ORTHO_{IRC|RVB}_0M20_JP2_E080_L93_XXXX_YYYY.jp2`
  (coin **Sud-Ouest**, km Lambert-93 ; fenêtre 49 ≈ X 350-470, Y 6650-6770).
- **Ordre des bandes IRC : bande 1 = proche infrarouge (PIR), 2 = rouge, 3 = vert.**
  À confronter à ce que suppose `detection.py` (l'appariement RVB/IRC de 15_detect) dès B1.
- Extraction communale sans tout décompresser : `7z x archive.7z.001 -ir!*XXXX_YYYY.jp2 -o…`
  (liste des dalles obtenue par intersection commune Admin Express × tableau d'assemblage
  WFS). ⚠ Il faut quand même télécharger l'archive 7z complète (~150 Go) si elle est
  « solide » — SAUF si le miroir opendatarchives expose l'arborescence JP2 décompressée
  (à vérifier en premier au B1 : c'est le cas de figure le moins cher).
- Alternative moderne à tester au B1 avant tout : le service de téléchargement
  Géoplateforme permet peut-être une sélection par emprise (l'interface cartes.gouv.fr
  génère des archives à l'emprise) — si un endpoint scriptable existe, il bat les 150 Go.

**Millésimes (statut : plausible, NON confirmé par la vérif web du 2026-07-11) :**
- Millésime 49 courant = **2025** (survol été 2025, publication charnière 2025/2026),
  remplaçant 2022. La vérif web dit seulement « l'imagerie 2025 arrive progressivement à
  partir de l'été » → **le run B1 tranche** (10_download consigne le millésime réel ;
  prévoir que 2022 soit encore le dernier publié).
- Prochain survol du 49 : **été 2028**, publication fin 2028/début 2029 (cycle triennal).
  → confirme l'impossibilité d'un abonnement annuel sur la seule ortho (`10` §7) et donne
  la fenêtre du produit « nouvelles piscines » suivant.
- **Opportunité stratégique si le millésime 2025 est confirmé : le diff 2022→2025 est
  possible DÈS LE LANCEMENT** (les archives 2022 restent accessibles — BD ORTHO Historique /
  opendatarchives). Le segment « nouvelles piscines » (le plus chaud, l'imprenable face aux
  brokers nationaux — `15` §2bis) n'attend pas 2028 : détection sur les deux millésimes de
  la même commune + `millesimes.py` (déjà codé et testé). Coût = un 2e passage de détection.

**Ignoré volontairement :** le pipeline « FlatGeobuf + HTTP Range » d'Admin Express
(joli mais nos communes tiennent dans un GPKG déjà téléchargé par 10_download) ; les
digressions NDVI/zones humides (hors produit).

---

## Texte brut du deepsearch

Rapport d'Expertise Géomatique : Ingénierie Stratégique et Mécanismes d'Acquisition Automatisée de la BD ORTHO (IGN) pour le Département du Maine-et-Loire (D049) en 2026

L'Institut National de l'Information Géographique et Forestière (IGN) constitue l'épine dorsale de la connaissance spatiale et du référentiel topographique en France. Au cœur de cette infrastructure de données publiques se trouve la BD ORTHO®, une collection de mosaïques numériques d'orthophotographies couvrant l'intégralité du territoire national avec une précision géométrique et radiométrique exceptionnelle. Dans le contexte spécifique du département du Maine-et-Loire (D049) – un territoire caractérisé par la complexité de son réseau hydrographique (le bassin versant de la Loire, la Maine, l'Authion), la richesse de ses zones humides et la densité de son maillage bocager – l'exploitation de ces données massives dépasse le simple cadre de la cartographie visuelle. Elle répond à des enjeux critiques d'aménagement du territoire, de suivi de l'artificialisation des sols, et d'inventaire écologique de haute précision.

L'année 2026 consacre une évolution paradigmatique dans la diffusion de la donnée géographique française. L'achèvement du déploiement de la Géoplateforme, succédant définitivement aux anciens Géoservices, impose de nouvelles architectures pour la mise à disposition de l'Open Data institutionnel. Les professionnels de la géomatique, les data scientists et les ingénieurs en télédétection se trouvent confrontés à la nécessité de moderniser leurs pipelines d'extraction, de transformation et de chargement (ETL spatial). Le traitement automatisé par script de l'imagerie très haute résolution (20 centimètres) exige une maîtrise rigoureuse des schémas de nommage, des formats de compression avancés, et des méthodes d'accès asynchrones.

Ce rapport exhaustif détaille les spécifications techniques, les fondements algorithmiques et les protocoles logistiques permettant le téléchargement direct et le traitement automatisé de la BD ORTHO (en spectres RVB et Infrarouge Couleur) pour le Maine-et-Loire, en s'appuyant exclusivement sur les infrastructures validées en 2026. L'analyse porte sur la topologie des flux de données, les spécificités du format JPEG2000, la chronologie des campagnes de survol aérien, et la modélisation mathématique permettant l'extraction ciblée d'une entité communale sans recourir aux services web de visualisation, inadaptés aux traitements analytiques de haute performance.

Évolution de l'Architecture de Diffusion : De l'Hébergement Institutionnel à la Résilience Pair-à-Pair

La mise à disposition de téraoctets de données matricielles sous la licence ouverte Etalab 2.0 représente un défi logistique majeur pour les infrastructures étatiques. La transition vers la Géoplateforme, opérée en partenariat avec des acteurs du cloud souverain tels qu'OVHCloud, visait initialement à décloisonner les silos d'information et à offrir une bande passante évolutive pour soutenir l'essor de l'Open Data géographique. Cette infrastructure centralise aujourd'hui l'accès aux vastes archives de la BD ORTHO via le domaine unifié cartes.gouv.fr et son interface de programmation (API) adossée à data.geopf.fr.

Néanmoins, la réalité opérationnelle des ingénieurs confrontés à la nécessité de télécharger des jeux de données atteignant plusieurs centaines de gigaoctets par département révèle certaines limites inhérentes à une distribution purement centralisée. L'accès direct aux serveurs institutionnels par des scripts automatisés (de type wget ou curl) peut occasionnellement se heurter à des mesures de restriction de requêtes (rate-limiting), à des instabilités de connexion lors de sessions prolongées (timeouts), ou à des modifications des en-têtes HTTP de sécurité. Ces aléas compromettent la fiabilité des chaînes de traitement automatisées qui exigent une disponibilité ininterrompue des ressources.

C'est en réponse à ces défis infrastructurels que s'est structurée une alternative d'une résilience remarquable : le projet opendatarchives, hébergé sur le domaine files.opendatarchives.fr. Initiée par des membres fondateurs de la communauté OpenStreetMap France et soutenue par des cadres techniques de l'IGN, cette initiative vise à archiver préventivement le "Service Public de la Donnée de Référence" (SPD). Ce miroir constitue, en 2026, l'infrastructure la plus performante et la plus adaptée pour un téléchargement scripté massif. En répliquant la totalité des archives, ce système s'affranchit des limitations de bande passante étatiques et intègre des protocoles de distribution pair-à-pair (P2P), notamment via l'usage de torrents. La décentralisation de la charge réseau via des outils en ligne de commande comme lftp permet un téléchargement collaboratif ultra-rapide, assurant l'intégrité cryptographique des paquets de données tout en soulageant les serveurs de la Géoplateforme. Pour la mise en place d'un pipeline de données robuste, l'utilisation prioritaire de ce miroir associatif est stratégiquement recommandée.

Construction Algorithmique et Sémantique des URLs de Téléchargement

Pour automatiser la récupération des archives de la BD ORTHO relatives au Maine-et-Loire (D049), le développement d'un script robuste exige une compréhension intime de la nomenclature stricte définie par l'IGN. La traçabilité et l'intégrité des paquets de données reposent sur une concaténation sémantique immuable. En 2026, le millésime de référence en vigueur pour le département 49 est l'édition issue de la campagne photographique de 2025. La chaîne de caractères identifiant de manière univoque une archive intègre successivement : le nom commercial du produit, la version des spécifications techniques, le type de profil spectral, la résolution géométrique native, l'algorithme de compression interne, le système de projection cartographique, le code administratif départemental, et enfin la date de référence légale.

Le schéma de nommage canonique d'un répertoire d'archive pour le produit standard en couleurs naturelles se décline ainsi : BDORTHO_1-0_RVB-0M20_JP2-E080_LAMB93_D049_2025-01-01.
L'homologue scientifique en infrarouge substitue la variable spectrale : BDORTHO_1-0_IRC-0M20_JP2-E080_LAMB93_D049_2025-01-01.

Face à la volumétrie colossale des départements français, l'IGN ne délivre pas la donnée sous la forme d'un fichier unique. Les archives sont méthodiquement segmentées en volumes de compression multi-parties s'appuyant sur l'algorithme LZMA du format 7-Zip. Ces fichiers portent les extensions incrémentales .7z.001, .7z.002, jusqu'à la complétion du volume total.

La conception d'un script de téléchargement doit par conséquent implémenter une boucle itérative. L'algorithme doit générer les URLs en incrémentant le suffixe numérique, envoyer des requêtes HTTP GET, et s'interrompre dès la réception d'un code de statut HTTP 404 (Not Found), signalant la fin géométrique de la segmentation de l'archive. Les fondations de cette automatisation s'appuient sur les structures d'URLs suivantes.

| Infrastructure Source | Produit | URL de Base pour le Segment Initial (.001) |
|---|---|---|
| Géoplateforme (Officiel) | RVB | https://data.geopf.fr/telechargement/download/BDORTHO/BDORTHO_1-0_RVB-0M20_JP2-E080_LAMB93_D049_2025-01-01/BDORTHO_1-0_RVB-0M20_JP2-E080_LAMB93_D049_2025-01-01.7z.001 |
| Géoplateforme (Officiel) | IRC | https://data.geopf.fr/telechargement/download/BDORTHO/BDORTHO_1-0_IRC-0M20_JP2-E080_LAMB93_D049_2025-01-01/BDORTHO_1-0_IRC-0M20_JP2-E080_LAMB93_D049_2025-01-01.7z.001 |
| Opendatarchives (Miroir) | IRC | http://files.opendatarchives.fr/professionnels.ign.fr/orthohr/BDORTHO_1-0_IRC-0M20_JP2-E080_LAMB93_D049_2025-01-01.7z.001 |

Une fois la totalité des segments téléchargée sur le stockage local du serveur de traitement, l'extraction doit être obligatoirement initiée sur le premier segment directeur (.7z.001). Le moteur de décompression (par exemple, le binaire 7z sous les environnements Linux ou Windows) détecte automatiquement la signature de l'archive multi-parties et assemble les volumes subséquents de manière séquentielle en mémoire avant d'écrire les fichiers raster sur le disque. Toute tentative de décompression d'un segment intermédiaire solde invariablement par une erreur de corruption d'en-tête.

Spécifications Topologiques, Profils de Compression et Volumétrie Analytique

La valeur heuristique et la fiabilité d'un traitement géospatial automatisé dépendent intrinsèquement de la connaissance absolue des structures de données ingérées. Historiquement hétérogène dans ses résolutions, l'IGN a standardisé la production de sa BD ORTHO, actant la disparition des anciennes orthophotographies à 50 centimètres (qui relevaient du produit standard) au profit d'une résolution unique et universelle de 20 centimètres par pixel, absorbant de facto l'ancienne nomenclature ORTHO HR®. Cette très haute résolution confère à la donnée une acuité redoutable, permettant la détection automatisée d'éléments structurels de l'aménagement urbain ou la photo-interprétation d'arbres isolés et de haies résiduelles (dents creuses).

Le Format JPEG2000 (JP2) et l'Architecture de la Transformée en Ondelettes

Pendant de nombreuses années, le format GeoTIFF, souvent couplé à une compression LZW ou Deflate, s'est imposé comme le standard de facto de l'industrie géomatique pour le stockage des rasters géoréférencés. Toutefois, la transition vers une résolution native de 20 centimètres a provoqué une inflation exponentielle du poids des données, menaçant de saturer les infrastructures de stockage. En réponse, l'IGN diffuse la BD ORTHO dans un format interne strictement arrêté au standard JPEG2000, identifiable par l'extension de fichier .jp2.

Ce choix technologique est d'une importance capitale pour les processus de vision par ordinateur (Computer Vision). Contrairement au format JPEG traditionnel (basé sur la transformée en cosinus discrète - DCT), qui opère sur des blocs de 8x8 pixels et génère de profonds artefacts de macroblocs en cas de compression sévère, le format JPEG2000 s'appuie sur la transformée en ondelettes discrète (Discrete Wavelet Transform - DWT). Cette structure mathématique analyse l'image à de multiples échelles de résolution simultanément. Elle permet une compression nettement plus efficiente tout en préservant l'intégrité des hautes fréquences spatiales, c'est-à-dire la netteté absolue des contours géographiques. Pour des algorithmes de segmentation par apprentissage profond (Deep Learning) destinés à identifier le bâti ou les lisières forestières, l'absence d'artefacts de blocs est une condition sine qua non de la précision des inférences géométriques.

L'étiquette E080, invariablement présente dans le schéma de nommage des fichiers, documente le profil de compression paramétré par les encodeurs de l'IGN. Ce suffixe cryptique certifie que l'algorithme a conservé 80 % de la quantité d'information radiométrique initiale. Il s'agit d'un profil qualifié d'"optimisé", offrant un ratio exceptionnel entre la fidélité colorimétrique (indispensable pour l'analyse spectrale) et la réduction de l'empreinte de stockage physique. Ce profil contraste avec le paramètre E100, qui représenterait un encodage mathématiquement sans perte, générant des fichiers d'une lourdeur inexploitable pour des échelles départementales.

Dimensionnement Spatial, Grille de Pavage et Calcul Volumétrique

L'organisation spatiale de la BD ORTHO ne se conforme pas aux limites administratives sinueuses des départements, mais s'inscrit dans un pavage orthogonal strict et mathématique. Ce carroyage est défini dans le Système de Coordonnées de Référence (SCR) officiel, légal et exclusif de la France métropolitaine : la projection cartographique conique conforme de Lambert 93, indissociable du système géodésique RGF93 (référencé mondialement sous le code EPSG:2154).

Dans ce référentiel, chaque dalle individuelle constituant la mosaïque départementale possède une emprise standardisée mesurant exactement 1 kilomètre de largeur sur 1 kilomètre de hauteur, représentant une superficie physique de 100 hectares. En appliquant la résolution native de 20 centimètres (0,2 mètre) par pixel, les dimensions matricielles internes de chaque fichier .jp2 sont rigoureusement fixées à 5000 colonnes (pixels en X) et 5000 lignes (pixels en Y).

Le système de nommage des fichiers individuels, encapsulés au sein des archives 7-Zip, respecte une nomenclature géométrique stricte basée sur les coordonnées kilométriques du coin inférieur gauche (le coin Sud-Ouest) de la dalle. Le nom de chaque fichier respecte la syntaxe : ORTHO_IRC_0M20_JP2_E080_L93_XXXX_YYYY.jp2. Dans cette formulation, XXXX correspond à la coordonnée planimétrique Est (Easting) exprimée en kilomètres, tandis que YYYY correspond à la coordonnée Nord (Northing). Pour le Maine-et-Loire, département central des Pays de la Loire, les coordonnées géographiques en projection Lambert 93 se situent approximativement dans une fenêtre où l'abscisse X évolue entre 350 et 470 kilomètres, et l'ordonnée Y fluctue entre 6650 et 6770 kilomètres.

L'évaluation de la volumétrie totale à gérer pour le D049 nécessite une modélisation mathématique du territoire. Le Maine-et-Loire s'étend sur une superficie administrative d'environ 7 166 kilomètres carrés. Néanmoins, le tuilage raster ne s'arrête pas net sur les frontières communales. L'IGN calcule une boîte englobante (Bounding Box) rectangulaire qui circonscrit l'intégralité des extrémités géographiques du département, générant inévitablement un excédent de dalles "vides" ou partielles sur les marges extérieures (le fameux "débord"). L'analyse du graphe de mosaïquage permet d'estimer qu'approximativement 8 000 à 8 500 dalles de 1 km² sont générées pour assurer la couverture totale et ininterrompue du D049.

Sur le plan informatique, une matrice image de 5000x5000 pixels (soit 25 millions de pixels), codée sur 8 bits par canal colorimétrique pour 3 canaux distincts, occupe un poids brut en mémoire de 75 mégaoctets lorsqu'elle n'est pas compressée. L'application de la compression JPEG2000 au profil E080 réduit drastiquement cette empreinte : le poids d'une dalle oscille généralement entre 15 et 20 mégaoctets. Cette variation pondérale est dictée par la complexité entropique de la scène photographiée ; les zones urbaines denses (comme le centre-ville d'Angers ou de Saumur), riches en détails à haute fréquence, génèrent des fichiers significativement plus lourds que les vastes étendues agricoles monotones de la vallée de l'Authion.

En agrégeant ces paramètres, le volume physique total du jeu de données décompressé sur disque pour une couverture départementale unique s'élève à environ 150 à 170 gigaoctets. L'exigence de traiter conjointement les spectres RVB et IRC porte le volume de données brutes extraites à manipuler à plus de 300 gigaoctets pour le seul département du Maine-et-Loire. Il convient de souligner que les archives compressées au format .7z téléchargées initialement pèseront un poids très similaire. En effet, l'algorithme LZMA de 7-Zip ne parvient pas à compresser davantage des fichiers JPEG2000 qui ont déjà fait l'objet d'un encodage mathématique à entropie maximale ; l'archive joue donc principalement un rôle structurel de conteneur d'assemblage et de transport.

| Paramètre Technique du Fichier Brut | Spécification Officielle (Édition 2026) |
|---|---|
| Encodage Matriciel | JPEG2000 (.jp2) via Transformée en Ondelettes |
| Qualité Radiométrique | Profil E080 (Optimisé, 80 % d'information préservée) |
| Résolution Géométrique Native | 20 centimètres / pixel |
| Emprise Spatiale (Tuile) | 1 kilomètre x 1 kilomètre (100 hectares) |
| Taille de la Matrice (Pixels) | 5000 x 5000 pixels par tuile |
| Système Géodésique et Cartographique | Lambert 93 (RGF93) / EPSG:2154 |
| Volume Total Estimé (D049, par spectre) | 150 à 170 Gigaoctets (après extraction) |

Architecture Multispectrale et Ingénierie Radiométrique de l'Infrarouge Couleur (IRC)

La colorimétrie des données d'observation de la Terre transcende la simple question de la perception visuelle humaine ; elle constitue la matrice informationnelle fondamentale pour le développement d'algorithmes de diagnostic environnemental. Le produit RVB (comprenant les canaux Rouge, Vert, et Bleu) demeure l'outil de prédilection pour l'aménagement topographique, le cadastre et la restitution visuelle anthropocentrée. Cependant, le produit IRC (Infrarouge Couleur), techniquement qualifié de composition en fausses couleurs, s'affirme comme l'instrument scientifique par excellence pour l'analyse automatisée de la biomasse végétale, de la pédo-hydrologie et du suivi écologique des territoires.

Le capteur numérique embarqué lors des prises de vues aériennes (PVA) capture l'énergie électromagnétique bien au-delà du spectre visible. Le produit IRC de la BD ORTHO substitue intentionnellement l'un des canaux visibles par une bande spectrale située dans le proche infrarouge. L'ordre formel des bandes matricielles inscrites dans l'en-tête (header) des fichiers .jp2 IRC est strictement encodé de la manière suivante :
Canal 1 (Bande 1) : Proche Infrarouge (PIR), enregistrant les longueurs d'onde comprises entre 0,8 et 1,1 micromètres.
Canal 2 (Bande 2) : Spectre Rouge (lumière visible).
Canal 3 (Bande 3) : Spectre Vert (lumière visible).

La maîtrise de cette architecture à trois bandes est une condition préalable absolue pour tout script d'analyse raster (utilisant par exemple la bibliothèque rasterio en Python ou le package terra sous R). L'exploitation du Canal 1 (le Proche Infrarouge) est le moteur de la télédétection environnementale. Les lois de la physique optique démontrent que, dans cette plage de longueurs d'onde (0,8 - 1,1 µm), l'énergie électromagnétique n'est que très marginalement absorbée par les structures organiques des feuilles (moins de 10 % d'absorption). En réalité, l'écrasante majorité de ce rayonnement traverse l'épiderme végétal pour être massivement réfléchie et dispersée par la structure cellulaire interne, particulièrement par le parenchyme palissadique et lacuneux.

Cette réflectance est directement proportionnelle à la santé et à la densité des chloroplastes. Ainsi, plus l'activité chlorophyllienne d'un couvert végétal est intense, plus la valeur radiométrique (le niveau de gris du pixel) enregistrée dans le Canal 1 sera proche de sa valeur maximale. Dans la composition colorée classique de l'IRC (où la bande PIR est affectée au canal rouge de l'écran d'affichage), la végétation saine apparaît d'un rouge écarlate éclatant. À l'opposé du spectre de réflectance, l'eau libre ou fortement chargée en humidité absorbe la quasi-totalité du rayonnement proche infrarouge, se traduisant par des valeurs de pixels extrêmement faibles, apparaissant d'un noir absolu ou d'un bleu très sombre sur les images composées.

Cette dichotomie spectrale radicale confère au produit IRC sa valeur inestimable pour les ingénieries de l'État et les bureaux d'études environnementaux opérant dans le Maine-et-Loire. Ce département, irrigué par l'artère de la Loire et maillé par ses affluents majeurs (la Mayenne, la Sarthe, le Layon, l'Oudon), est le théâtre d'enjeux écologiques colossaux liés à la préservation des zones humides. Les services de la Direction Régionale de l'Environnement, de l'Aménagement et du Logement (DREAL) des Pays de la Loire utilisent historiquement et massivement la BD ORTHO pour la pré-localisation par photo-interprétation et l'inventaire systématique des zones humides élémentaires (ZHE) et de leurs espaces de fonctionnalités.

L'analyse algorithmique de la signature spectrale du proche infrarouge permet aux scripts de délimiter avec une précision chirurgicale les interfaces eau-terre, de cartographier l'extension des ripisylves, et de détecter les niveaux d'hygrométrie des sols gorgés d'eau, remplaçant ou orientant avantageusement de longues, coûteuses et complexes campagnes de sondages pédologiques sur le terrain. Par ailleurs, l'IRC est mobilisé pour l'analyse automatisée de la densité des réseaux de haies bocagères. La segmentation de la canopée via l'indice de végétation par différence normalisée (NDVI), aisément calculable en isolant et en soustrayant le Canal 2 (Rouge) du Canal 1 (PIR), permet de localiser les chênes pédonculés sénescents qui constituent des habitats cruciaux pour des espèces d'insectes protégées, telles que le Lucane Cerf-volant (Lucanus cervus) ou le Grand Capricorne (Cerambyx cerdo), dont la préservation est un enjeu de conservation majeur en Maine-et-Loire.

Dynamique Temporelle, Millésimes et Programmation des Campagnes de Survol Aérien

La pertinence analytique, tout autant que la force probante juridique d'une donnée géographique (notamment dans le cadre des documents d'urbanisme locaux ou des contentieux environnementaux), est intimement subordonnée à son actualité temporelle. La production industrielle de la BD ORTHO par l'IGN n'est pas un processus continu, mais obéit à des cycles de rafraîchissement programmés et contraints par de multiples facteurs logistiques et météorologiques. Les opérations de Prises de Vues Aériennes (PVA) exigent une mobilisation des flottes d'avions capteurs durant des fenêtres temporelles estivales très précises, s'étendant généralement de la fin du mois d'avril jusqu'au mois d'octobre. Ces conditions strictes garantissent une hauteur du soleil optimale pour minimiser les ombres portées du bâti urbain, une absence critique de couverture nuageuse, et une phénologie végétale à son apogée permettant d'optimiser l'analyse de l'activité chlorophyllienne.

Les survols aériens s'opèrent par le tracé de bandes de vol parallèles. Les avions numériques de l'IGN maintiennent un taux de recouvrement (overlap) longitudinal et latéral considérable entre chaque cliché photographique. Cette redondance visuelle n'est pas un artefact, mais une nécessité absolue pour le traitement de corrélation stéréoscopique. La géométrie tridimensionnelle extraite de ces recouvrements permet de générer des Modèles Numériques de Terrain (MNT) et des Modèles Numériques de Surface (MNS) de haute précision, algorithmes indispensables pour procéder à la rectification géométrique des images et éliminer le dévers des objets en élévation (orthorectification).

En 2026, l'investigation approfondie des catalogues et des graphes de mosaïquage de la Géoplateforme certifie que le millésime actuel de la BD ORTHO en vigueur pour le département du Maine-et-Loire (D049) date de l'année 2025. Cette ambitieuse campagne de vol, exécutée au cours de l'été 2025, a traversé des phases complexes de traitements photogrammétriques intensifs, de mosaïquage d'ajustement aux lignes de rupture, d'égalisation radiométrique globale, et d'orthorectification durant l'automne. La publication officielle de ces téraoctets d'imagerie en accès libre sous licence ouverte Etalab 2.0 a été finalisée à la charnière de la fin 2025 et du début de l'année 2026. Ce millésime 2025 vient remplacer formellement, tant pour les administrations que pour le secteur privé, l'édition de référence précédente qui datait de la campagne photographique de 2022 pour ce même département.

L'organisation des campagnes de l'IGN à l'échelle nationale s'inscrit dans un cycle de rafraîchissement industriel hautement standardisé, dicté par les impératifs des politiques publiques européennes et nationales. L'urgence du suivi du Registre Parcellaire Graphique (RPG) pour les aides de la Politique Agricole Commune, ainsi que les obligations législatives découlant de la loi Climat et Résilience concernant le suivi rigoureux de l'artificialisation et de la consommation des espaces naturels, agricoles et forestiers (via la base de données OCS GE), exigent une actualisation fréquente du territoire. Ce cycle de rotation nominal de l'imagerie a ainsi été fixé à un rythme triennal (tous les trois ans) pour l'ensemble des départements de la France métropolitaine.

Par une simple déduction arithmétique de ce calendrier industriel de long terme, le planning prévisionnel pour le Maine-et-Loire est fermement établi. La prochaine campagne d'acquisition par survol aérien (PVA) pour le département 49 interviendra lors de la saison estivale de l'année 2028. En tenant compte des délais de calcul photogrammétrique, la publication des dalles rectifiées issues de cette future campagne est attendue entre le dernier trimestre 2028 et le premier trimestre de l'année 2029.

| Paramètre Chronologique | Échéance et Millésimes |
|---|---|
| Millésime Historique Récent | Édition 2022 |
| Millésime Actuel (Référence 2026) | Édition 2025 |
| Fréquence Industrielle de Mise à Jour | Cycle Triennal (actualisation tous les 3 ans) |
| Période de Prises de Vues Aériennes (PVA) | Phénologie Estivale (Avril à Octobre) |
| Date Prévisionnelle du Prochain Survol | Été 2028 |

Ingénierie d'Extraction Chirurgicale : Modélisation Algorithmique d'une Enclave Communale

L'un des dilemmes majeurs rencontrés par les architectes de systèmes d'information géographique (SIG) et les développeurs réside dans la rigidité de la granularité des livraisons de données massives. Lorsqu'un processus d'analyse automatisé — tel que l'entraînement d'un réseau neuronal convolutif (CNN) pour la détection sémantique de l'imperméabilisation des sols, ou le calcul d'un inventaire de haies bocagères — est explicitement restreint à l'emprise territoriale d'une unique commune spécifique (par exemple, la commune du Lion-d'Angers), le téléchargement systématique et le stockage persistant des 150 à 300 gigaoctets englobant l'intégralité du département s'avèrent être un gaspillage astronomique de ressources réseau, de cycles de processeur (CPU), et d'espace disque.

Face à cette problématique, une solution de facilité consisterait à interroger les flux dynamiques mis à disposition par la Géoplateforme, tels que les services Web Map Service (WMS) ou Web Map Tile Service (WMTS). Cependant, l'utilisation de ces protocoles de visualisation est formellement proscrite dans un contexte de traitement géospatial pur et de télédétection. Les raisons en sont multiples et fondamentales sur le plan mathématique :
Les flux WMS opèrent un rééchantillonnage de l'image (resampling) à la volée, fusionnant ou interpolant les pixels originaux.
Ils imposent de surcroît des reprojections géométriques instables, transformant souvent la projection Lambert 93 native vers des référentiels conçus pour la cartographie web grand public, tels que le Pseudo-Mercator ou Web Mercator (EPSG:3857) popularisé par Google, détruisant ainsi l'intégrité métrique de l'image.
Pire encore, le serveur délivre systématiquement un flux compressé dynamiquement dans des formats destructifs à l'instar du JPEG classique 8-bits. Cette compression détruit irréversiblement les valeurs radiométriques discrètes des pixels originaux, rendant le calcul d'indices spectraux (comme le NDVI) totalement caduc, biaisé, et dépourvu de toute valeur scientifique.

L'objectif impérieux est donc d'obtenir les dalles géospatiales brutes originelles, au format JPEG2000 (.jp2), tout en s'affranchissant du téléchargement et de la décompression du volume départemental intégral. Pour contourner l'architecture monolithique des archives 7-Zip, un script robuste doit implémenter une logique d'intersection topologique en cascade. Cette méthodologie d'extraction chirurgicale s'articule autour de quatre phases algorithmiques, détaillées ci-après pour garantir la reproductibilité du traitement.

Phase 1 : Acquisition Haute Performance des Référentiels Vectoriels

La phase d'amorçage exige l'acquisition de la géométrie polygonale absolue définissant les limites administratives de la commune ciblée. Le référentiel officiel approprié, mis à jour continuellement, est la base Admin Express de l'IGN. L'innovation technologique de l'année 2026 dans ce domaine réside dans la diffusion native de ces couches vectorielles aux formats FlatGeobuf et GeoParquet, accessibles via des URLs statiques de téléchargement partiel sur cartes.gouv.fr.

Le format FlatGeobuf est particulièrement optimisé pour les architectures de scripting. Contrairement à un fichier Shapefile traditionnel qui impose de lire le fichier dans son entièreté, FlatGeobuf intègre un index spatial binaire (R-Tree) dès les premiers octets de l'en-tête du fichier. Cette caractéristique fondamentale permet aux bibliothèques d'abstraction de données géographiques (telles que GDAL/OGR) d'émettre des requêtes HTTP Range spécifiques au serveur. Ainsi, le script télécharge uniquement les octets correspondant à la géométrie exacte de la commune requise, épargnant le rapatriement inutile des dizaines de mégaoctets constituant la base de données de toutes les communes de France métropolitaine.

Concomitamment, le script doit acquérir le "Tableau d'assemblage" (TA) spécifique à la BD ORTHO du Maine-et-Loire. Ce tableau est un jeu de données vectorielles (généralement délivré sous la forme d'un GeoPackage ou d'un flux Web Feature Service - WFS) qui matérialise physiquement le carroyage exact des dalles de 1 kilomètre carré sur le territoire. Chaque polygone composant ce damier possède une table d'attributs contenant la chaîne de caractères primordiale : l'identifiant nominatif de la dalle correspondante (c'est-à-dire la syntaxe XXXX_YYYY liée aux coordonnées Lambert 93).

Phase 2 : Modélisation Spatiale et Génération de la Liste de Dalles

Disposant en mémoire des deux entités géométriques, le script recourt à une bibliothèque d'analyse spatiale avancée (par exemple, la librairie Geopandas couplée à Shapely en langage Python, ou le module spatial sf intégré à l'environnement R). L'algorithme lance une opération d'intersection topologique (un Spatial Join ou une fonction géométrique ST_Intersects si le traitement est déporté sur une base PostGIS).

Le moteur géométrique croise le polygone délimitant la commune avec la grille orthogonale du Tableau d'assemblage. L'algorithme identifie et isole tous les carrés du TA dont la géométrie croise ou est incluse dans la limite administrative de la commune, englobant consciencieusement les dalles marginales qui sont simplement effleurées ou scindées par la frontière de l'entité territoriale. Le résultat de cette opération booléenne est la compilation d'une liste textuelle exhaustive regroupant les identifiants stricts des dalles requises pour couvrir la commune (par exemple : L93_0412_6723.jp2, L93_0413_6723.jp2, L93_0412_6724.jp2, etc.).

Phase 3 : Extraction Sémantique et Partielle de l'Archive Multivolume

C'est lors de l'acquisition finale des dalles raster que se révèle le défi inhérent à l'architecture de compression choisie par l'IGN. La méthodologie officielle implique obligatoirement de télécharger la suite logicielle des volumes de l'archive 7-Zip (.7z.001 jusqu'au dernier incrément). Le format 7-Zip est historiquement compilé par les administrateurs de l'IGN en mode "archive solide" (Solid Archive). Cette spécification d'encodage implique que le dictionnaire de compression algorithmique est partagé de manière continue sur l'ensemble des fichiers encapsulés. Cette solidarité des blocs de données interdit catégoriquement le téléchargement partiel d'un unique volume .7z pour en extraire un fichier précis ; le script est donc astreint à télécharger l'intégralité des 150 gigaoctets des volumes 7-Zip départementaux et à les stocker dans un répertoire temporaire d'amortissement local.

Cependant, la prouesse algorithmique réside dans le fait qu'il n'est absolument pas nécessaire de décompresser la totalité des 150 gigaoctets sur le disque dur, une opération qui serait effroyablement lente et détruirait prématurément les disques à semi-conducteurs (SSD) par une usure excessive des cycles d'écriture (I/O). Le programme exécutable binaire 7z autorise la transmission d'arguments restrictifs spécifiant une liste explicite de fichiers à extraire de l'archive parente. Le script doit générer dynamiquement la commande système en concaténant les identifiants nominatifs obtenus à l'issue de la phase d'intersection spatiale :

Commande système modélisée :
7z x BDORTHO_1-0_IRC-0M20_JP2-E080_LAMB93_D049_2025-01-01.7z.001 -ir!*0412_6723.jp2 -ir!*0413_6723.jp2 -o/chemin_du_serveur/dossier_destination_commune/

Dans cette configuration, l'outil de décompression explorera virtuellement l'archive solide résidant en mémoire vive et n'écrira matériellement sur le disque local de destination que les dalles brutes JP2 identifiées comme recouvrant la commune ciblée. Une fois l'extraction des dalles achevée, le script procédera à la suppression automatique (garbage collection) de l'archive 7-Zip temporaire de 150 gigaoctets. Ce mécanisme permet une économie drastique des capacités de stockage persistantes et une fulgurance accrue du processus d'acquisition pour des chaînes de production à haute fréquence.

Phase 4 (Alternative Décentralisée) : Exploitation des Arborescences Dégelées

Dans l'éventualité où l'architecture locale du serveur de traitement interdirait catégoriquement le téléchargement temporaire d'un fichier tampon de 150 gigaoctets, la stratégie de contournement la plus viable repose sur l'exploitation approfondie de l'arborescence du miroir OpenDatArchives. De manière ponctuelle et informelle, les administrateurs de ce miroir procèdent à un "dégel" des archives compactes, exposant l'arborescence native des fichiers matriciels JP2 ou TIFF directement accessibles via un annuaire HTTP ouvert (Open Directory) naviguable.

Si l'analyse préalable des en-têtes HTTP de files.opendatarchives.fr confirme la présence de cette structure désolidarisée pour le millésime 2025 du département 49, l'algorithme est en mesure de générer une boucle générant les URLs absolues de chaque dalle individuelle de la commune ciblée. Le script ordonnera alors un rapatriement asynchrone ultra-ciblé, téléchargeant les dalles de 20 mégaoctets l'une après l'autre via des protocoles natifs tels que wget ou l'accélérateur aria2c. Bien que cette configuration de téléchargement granulaire frôle la perfection conceptuelle, il est crucial d'avertir que le maintien d'arborescences décompressées requiert des capacités de stockage colossales de la part de l'hébergeur bénévole du miroir. Par conséquent, cette disponibilité n'est pas contractuellement garantie dans le temps, ce qui érige la méthode de l'extraction par ligne de commande 7-Zip itérative comme la solution la plus résiliente et la plus sûre pour un environnement de production informatique en 2026.
