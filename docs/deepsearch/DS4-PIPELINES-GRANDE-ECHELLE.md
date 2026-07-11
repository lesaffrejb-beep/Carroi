# DS4 — Pratiques d'ingénierie des pipelines de détection à grande échelle (prompt ⑩)

> Collé le 2026-07-11 (Gemini 3.5 Pro). Voir doctrine de lecture dans [README.md](README.md).

## Ce qu'on en retient (analyse 2026-07-11)

**Rien à changer — nos choix sont revalidés point par point** (le doc `15` §2 reste la
référence ; ce rapport ajoute les chiffres) :
- Frontières de tuiles : recouvrement + fusion des détections tronquées = exactement ce que
  fait `15_detect` (partition des zones intérieures + `fusionner_adjacentes`). Microsoft
  préfère IGNORER une tuile ambiguë plutôt qu'injecter une géométrie douteuse — même esprit
  que notre « incertain ≠ vendu ».
- Seuils de confiance : Google à seuil 0,90 obtient 90-94 % de précision pour ~70 % de
  rappel → confirme le fait n°2 de `15` (le full-auto ne tient pas ≥ 95 %) et notre
  arbitrage précision-via-tri-humain.
- Débits humains observés : validation binaire ~1 000-1 200 vignettes/h → notre estimation
  « ~1 s/vignette, 2-4 h pour 10 000 candidats » (`04` §1b.4) est réaliste, pas optimiste.
- Active learning : gains documentés de 30-70 % d'annotations en moins vs aléatoire →
  notre tri par incertitude (fait 2026-07-11) est la version « du pauvre » du bon réflexe ;
  les variantes avancées (VIG, query-by-committee) ne valent le coup qu'en option A
  multi-départements.
- Régularisation de polygones, conflation GERS, GeoParquet partitionné, Spark : **hors
  échelle** — on vend des adresses, pas des géométries ; mono-machine confirmé (`15` §2
  dernière ligne).
- Bon rappel : masquage par données exogènes (eau, altitude) pour tuer des familles
  entières de faux positifs → notre équivalent local = masque bâti BD TOPO + exclusion
  bassins publics ; si les faux positifs « plans d'eau/étangs » émergent en B2-terrain,
  la couche hydro BD TOPO est le masque à brancher en premier.
- Doctrine DGFiP explicitée : le fisc ASSUME un taux de validation bas (ratisser large,
  l'humain filtre) — c'est notre pipeline aussi, mais NOUS ne vendons que le post-tri.

---

## Texte brut du deepsearch

Pratiques d'Ingénierie des Pipelines de Détection à Grande Échelle : Architectures Géospatiales, Post-Traitement et Apprentissage Actif

L'extraction automatisée des empreintes de bâtiments à l'échelle planétaire représente l'un des défis les plus complexes de l'ingénierie géospatiale contemporaine. Entre 2023 et 2026, l'industrie a franchi un cap décisif, passant de la simple segmentation sémantique d'images satellitaires à la production de jumeaux numériques topologiquement corrects, sémantiquement enrichis et interopérables. Des initiatives colossales telles que le projet Google Open Buildings, qui recense plus de 1,8 milliard d'empreintes dans les pays du Sud, les jeux de données Global ML Building Footprints de Microsoft couvrant l'Amérique et l'Europe, ou encore la base de données unifiée de la fondation Overture Maps avec ses 2,7 milliards de polygones, ont défini de nouveaux standards. L'ingénierie derrière ces pipelines ne se résume plus à l'entraînement de réseaux de neurones profonds (Deep Neural Networks - DNN) ; elle intègre des architectures distribuées de traitement de données, des heuristiques de régularisation géométrique avancées, et des mécanismes de conflation probabiliste.

La création de bases de données vectorielles à l'échelle du pétaoctet exige de résoudre des problèmes inhérents à la nature même de l'imagerie terrestre. Les images satellitaires (telles que celles de Maxar, Airbus, ou Sentinel-2) doivent être découpées en tuiles pour être traitées par les unités de traitement graphique (GPU), ce qui engendre inévitablement des coupures artificielles des bâtiments situés sur les lignes de démarcation. Une fois les probabilités d'appartenance à la classe « bâtiment » calculées au niveau du pixel, la transformation de ces matrices en polygones vectoriels utilisables par les systèmes d'information géographique (SIG) nécessite d'abandonner les algorithmes gloutons traditionnels au profit de méthodes imposant des contraintes architecturales préalables. De plus, la viabilité économique et technique de ces modèles repose de plus en plus sur des plateformes d'annotation impliquant des opérateurs humains (Human-in-the-Loop), dont la productivité est méticuleusement mesurée. Face aux coûts exorbitants de l'annotation manuelle, le tri des données par incertitude, ou apprentissage actif (Active Learning), s'impose comme une nécessité structurelle pour améliorer les algorithmes sans labelliser aveuglément des millions de vignettes redondantes.

Architectures des Modèles d'Extraction et Segmentation Sémantique

Le fondement de tout pipeline de détection à grande échelle repose sur la capacité d'un réseau de neurones convolutif à isoler les pixels appartenant à une structure bâtie. Les architectures déployées par les acteurs majeurs de l'industrie témoignent d'une évolution vers des modèles capables de gérer des résolutions variables et des contextes géographiques hétérogènes.

Historiquement, le réseau U-Net a constitué la norme pour ce type de tâche. Le pipeline original de Google Open Buildings, par exemple, s'appuie fortement sur des architectures dérivées de U-Net équipées d'encodeurs ResNet, optimisées par des fonctions de perte spécifiques (comme la perte KL douce et le mixup) pour équilibrer les faux positifs et les faux négatifs lors de la détection de plus de 516 millions de bâtiments en Afrique. Récemment, Google a fait évoluer ses modèles vers des approches basées sur des étudiants et des enseignants (student-teacher models) pour son jeu de données Open Buildings 2.5D Temporal. Ce modèle ingère des piles d'images Sentinel-2 à basse résolution (10 mètres) et exploite les micro-décalages d'angle de vue entre différentes passes satellitaires (revisites tous les cinq jours) pour reconstituer une prédiction de haute résolution (50 centimètres), de manière analogue aux algorithmes de photographie computationnelle utilisés dans les smartphones.

De son côté, l'ingénierie de Microsoft repose sur le réseau ResNet34 associé à des couches de sur-échantillonnage RefineNet. Entraîné sur un corpus diversifié de plus de cinq millions d'images étiquetées couvrant des environnements variés (montagnes, forêts, déserts, zones côtières), ce modèle purement convolutif traite des patchs de 256x256 pixels à une résolution de 30 centimètres (1 pied par pixel) en utilisant 32 GPU via le toolkit CNTK.

D'autres initiatives documentées s'orientent vers des architectures hybrides ou basées sur les transformateurs visuels. Par exemple, des architectures comme ViTCapsNets combinent des Vision Transformers avec des réseaux à capsules (Capsule Networks) pour préserver les informations de pose spatiale et les relations géométriques souvent perdues par les opérations de regroupement (max-pooling) des réseaux convolutifs classiques. Dans le projet GlobalBuildingAtlas, le réseau d'extraction s'appuie sur une architecture UPerNet utilisant un squelette ConvNeXt-Tiny, supervisé par une perte d'entropie croisée augmentée par une perte auxiliaire extraite de la troisième couche du squelette pour renforcer la représentation des caractéristiques.

Ingénierie du Tuilage et Déduplication aux Frontières Spatiales

La cartographie à l'échelle mondiale impose de diviser la surface terrestre en grilles discrètes. Cette segmentation est vitale pour distribuer l'inférence sur des grappes de serveurs, mais elle pose des problèmes topologiques majeurs aux frontières de ces tuiles.

Formatage Cloud-Natif et Indexation Spatiale

L'interopérabilité et la performance des requêtes à grande échelle reposent désormais sur des formats géospatiaux cloud-natifs. L'industrie a massivement adopté le format GeoParquet (notamment la version 1.1) et le format PMTiles. Ces formats permettent de s'affranchir des limitations historiques des fichiers GeoJSON ou Shapefile, qui nécessitent d'être entièrement chargés en mémoire.

Le partitionnement des données est structuré selon des index spatiaux hiérarchiques. Google privilégie la grille S2, tandis que Microsoft utilise des Quadkeys basés sur la projection Web Mercator. Ce partitionnement est fondamental pour les performances. Dans un fichier GeoParquet contenant 100 millions d'entités, les métadonnées des boîtes englobantes (bbox) permettent aux moteurs de requête (comme DuckDB ou les serveurs de tuiles tels que tileserver-rs) d'ignorer des groupes entiers de lignes (Row Groups) qui n'intersectent pas la zone demandée. Les temps de réponse passent ainsi de plusieurs secondes à moins de la milliseconde pour des tuiles en cache, grâce à la descente de prédicats (Predicate Pushdown).

| Système d'Indexation | Acteur Principal | Avantage Technique pour le Tuilage | Format de Stockage Privilégié |
|---|---|---|---|
| S2 Grid | Google, VIDA | Subdivision sphérique limitant les distorsions aux pôles, idéal pour les plafonds de 20 millions d'empreintes par partition. | GeoParquet, FlatGeobuf |
| Web Mercator Quadkey | Microsoft | Alignement direct avec les standards de cartographie web, facilitant la transformation en tuiles vectorielles (MVT). | GeoParquet (Delta Tables) |

Gestion des Troncatures aux Frontières d'Images

Lorsqu'une image est divisée en patchs (généralement de 512x512 ou 4096x4096 pixels) pour être traitée par un GPU, un bâtiment chevauchant la ligne de démarcation sera analysé par fragments. Si ce phénomène n'est pas corrigé, le modèle produira des polygones scindés, avec des bords parfaitement droits et artificiels qui ne correspondent à aucune réalité architecturale.

Pour mitiger ce problème de troncature, la première ligne de défense consiste à appliquer des marges de recouvrement (overlapping buffers). L'image est extraite avec une bordure spatiale supplémentaire autour de la zone cible. Par exemple, l'API Vertex AI de Google permet aux développeurs de définir un recouvrement automatique des tuiles (tile overlap) lors de l'inférence. Ce tampon garantit que le contexte structurel immédiat d'un bâtiment situé sur le bord d'une tuile (comme son ombre portée ou les structures adjacentes) est inclus dans le champ récepteur du réseau, évitant ainsi les erreurs de classification en bordure.

Une seconde approche documentée relève du post-traitement adaptatif. Des algorithmes tels que le Scale-Adaptive and Truncation-aware Non-Maximum Suppression (SC-NMS) ont été développés spécifiquement pour la télédétection. Au lieu d'appliquer une suppression non maximale classique (qui supprimerait simplement les détections redondantes), le SC-NMS analyse les relations géométriques entre les boîtes englobantes générées et les limites de l'image. Lorsqu'une détection touche le bord d'une tuile, l'algorithme signale une troncature potentielle et fusionne activement (Merge) ce vecteur avec le polygone correspondant généré dans la tuile adjacente, reconstituant ainsi l'intégrité de la frontière du bâtiment. Chez Microsoft, lorsque les tuiles d'imagerie adjacentes proviennent de capteurs différents ou ont des dates d'acquisition très éloignées, les réseaux de détection s'embrouillent face à l'arête artificielle créée. Dans de tels cas, l'approche conservatrice de Microsoft consiste simplement à ignorer ces tuiles spécifiques, acceptant un vide (gap) dans la couverture plutôt que d'injecter des géométries aberrantes.

Post-Traitement des Polygones : De la Simplification à la Régularisation

Une fois les pixels identifiés, l'étape de polygonisation convertit ces amas de pixels matriciels en vecteurs. La complexité de cette tâche est souvent sous-estimée. Les pixels forment des contours en "escalier" (aliasing) qui doivent être lissés, mais un lissage excessif détruit la topologie de l'architecture.

Les Failles des Algorithmes Gloutons

La méthode standard de l'industrie géospatiale pour simplifier un vecteur est l'algorithme de Douglas-Peucker. Bien qu'il réduise efficacement le nombre de sommets en fonction d'une tolérance géométrique, il s'agit d'un algorithme glouton (greedy) dépourvu de contexte sémantique. Il se contente de relier des points distants, ce qui arrondit les coins des bâtiments rectangulaires, coupe les détails architecturaux perpendiculaires et génère des géométries en zigzag ou des angles arbitraires incompatibles avec les techniques de construction humaines. Les empreintes brutes issues des LiDAR ou des rasters nécessitent donc un nettoyage structurel approfondi.

Optimisation sous Contraintes A Priori (Approche Microsoft)

Pour pallier les insuffisances du Douglas-Peucker, Microsoft a développé un algorithme de polygonisation propriétaire basé sur l'optimisation de l'espace global des caractéristiques de prédiction. Cet algorithme force le respect de propriétés architecturales humaines a priori, qui sont définies manuellement et dont les seuils sont ajustés automatiquement de manière itérative.

Les contraintes fondamentales documentées par l'ingénierie de Microsoft sont les suivantes :
La longueur absolue et relative des arêtes : Une ligne de polygone ne peut exister que si sa longueur dépasse un seuil de viabilité structurelle, fixé empiriquement à environ 3 mètres. Toute irrégularité vectorielle plus petite est ignorée et lissée dans la continuité du mur.
L'orthogonalité probabiliste : L'algorithme part du postulat que les murs consécutifs d'un bâtiment sont majoritairement perpendiculaires. Il applique des forces de régularisation pour redresser les angles approchant les 90 degrés afin qu'ils soient parfaitement droits.
Le lissage des angles aigus : Les angles consécutifs très serrés sont irréalistes d'un point de vue architectural. L'algorithme définit un seuil dynamique (par exemple, 30 degrés) en dessous duquel l'angle est supprimé ou remodelé.
Le parallélisme par alignement sur l'angle dominant : L'algorithme calcule l'axe de rotation principal du bâtiment. Il contraint ensuite la quasi-totalité des arêtes secondaires à s'aligner sur cet angle dominant (avec une tolérance de l'angle dominant ±nπ/2), garantissant que la structure globale conserve une forme cohérente, même si l'image satellitaire était floue ou partiellement masquée.

Régularisation par Réseaux de Neurones et Graphes

D'autres pipelines privilégient des approches entièrement neuronales pour la régularisation. Dans des implémentations dérivées de U-Net, des couches sont ajoutées spécifiquement pour identifier non seulement le bâtiment, mais aussi ses bordures et les zones de contact entre bâtiments adjacents, afin d'accentuer la démarcation entre des structures très denses (comme dans les bidonvilles ou les habitats informels).

Le pipeline du projet GlobalBuildingAtlas intègre un réseau neuronal distinct pour la régularisation des cartes de bâtiments. Plutôt que de post-traiter le vecteur, ce réseau prend en entrée le masque binaire bruité produit par le modèle de segmentation primaire. Ce second modèle a été entraîné sur des masques volontairement dégradés (bruit ajouté aux sommets polygonaux) pour apprendre à isoler et redessiner proprement les formes avant même que le traceur de contours de GDAL ne soit appliqué.

Par ailleurs, l'utilisation des réseaux de neurones sur graphes (Graph Neural Networks - GNN) offre une méthode novatrice. Un algorithme de segmentation préalable (comme le Simple Linear Iterative Clustering - SLIC) divise l'image en superpixels. Ces superpixels deviennent les nœuds d'un graphe, et leurs adjacences en constituent les arêtes. Les réseaux GraphSAGE affinent ensuite ces régions en propageant l'information entre les nœuds adjacents, modifiant dynamiquement la forme du polygone en respectant le contexte spatial environnant. Cette méthode est particulièrement documentée comme étant supérieure pour l'identification dans les quartiers informels d'Amérique Latine et d'Afrique, où l'hétérogénéité des toits (chevauchements, matériaux de récupération) rend l'approche de Microsoft caduque.

Gestion des Faux Positifs et Masquage Environnemental

La télédétection automatisée souffre intrinsèquement de confusions visuelles. Les algorithmes d'intelligence artificielle peuvent aisément interpréter de grands conteneurs maritimes, des rochers carrés, des serres agricoles, des structures géologiques, ou des reflets spéculaires sur l'eau comme étant des toitures. Le traitement de ces faux positifs est donc une composante majeure de l'ingénierie des pipelines, combinant des méthodes statistiques internes et des exclusions géographiques externes.

Filtrage Interne par Score de Confiance

Google Open Buildings gère ce problème en attribuant à chaque empreinte générée un score de confiance prédictive compris entre 0 et 1. Plutôt que de décider ce qui est un bâtiment ou non en interne, Google délègue cette responsabilité à l'utilisateur final en suggérant des seuils. Les recommandations d'ingénierie précisent qu'un seuil de confiance strict (souvent égal ou supérieur à 0,90) permet d'atteindre une précision de 90 % à 94 %, éliminant ainsi les confusions avec les matériaux naturels. Le revers de cette approche est une réduction drastique du rappel (estimé autour de 70 %), signifiant que 30 % des véritables bâtiments ne sont pas signalés à un seuil aussi exigeant.

Microsoft adopte une approche différente en ne publiant pas les scores de confiance individuels avec ses données ouvertes, mais en appliquant ce filtrage au sein de son pipeline. Sur un corpus évalué en Amérique du Nord, Microsoft revendique un taux résiduel de faux positifs inférieur à 1 %.

Agrégation Temporelle (Rolling Time-Window)

Pour surmonter les erreurs ponctuelles dues aux nuages, à la qualité atmosphérique ou aux structures temporaires, l'analyse temporelle multivariée s'avère extrêmement efficace. Dans le pipeline Google Open Buildings 2.5D, une technique d'agrégation sur fenêtre glissante (Rolling Time-Window Aggregation) est appliquée au niveau du pixel sur des images trimestrielles.

Selon l'Algorithme 1 décrit dans leur documentation technique, un pixel n'est confirmé comme contenant une structure bâtie que si le modèle le classifie positivement sur au moins trois trimestres consécutifs (soit une fenêtre de 9 à 12 mois). Une évaluation de la clarté (Clarity Score de 1 à 4) pondère cette décision en fonction des données de couverture nuageuse (UDM). Cette constance temporelle détruit virtuellement les faux positifs liés aux chantiers, véhicules en stationnement prolongé, ou anomalies météorologiques.

Masquage Externe (Water & Elevation Masking)

Même avec des modèles performants, certaines configurations naturelles trompent systématiquement l'IA. Pour les éradiquer, les ingénieurs croisent systématiquement leurs prédictions avec des bases de données géographiques faisant autorité :
Masquage Altimétrique : Moins de 0,004 % de la population mondiale réside au-dessus de 5 000 mètres d'altitude, et le plus haut village permanent connu culmine à 5 100 mètres. L'ingénierie consiste donc à superposer le modèle d'élévation NASADEM et à supprimer brutalement tout "bâtiment" détecté au-dessus de 5 100 mètres.
Masquage Hydrologique : En s'appuyant sur les données du Global Surface Water (GSW) du Centre Commun de Recherche (JRC), qui analysent les transitions aquatiques depuis 1984, le pipeline élimine toutes les détections d'empreintes qui croisent des étendues d'eau permanentes ou saisonnières. Cela supprime les faux positifs liés aux bateaux amarrés ou aux fermes aquacoles.

Faux Positifs Tolérés : Le Cas de l'Administration Fiscale Française (DGFiP)

Il est intéressant d'analyser comment la tolérance aux faux positifs change selon l'objectif du pipeline. Le projet « Foncier Innovant » de la Direction Générale des Finances Publiques (DGFiP) en France, soutenu par l'Institut national de l'information géographique et forestière (IGN) et l'algorithmique de Capgemini et Google, vise à détecter les piscines non déclarées pour redresser l'assiette de la taxe foncière.

Dans ce contexte précis, la minimisation des faux positifs n'est pas la priorité absolue. L'algorithme s'avère particulièrement propice à confondre une bâche agricole, une grande serre, ou une piscine tubulaire non soumise à l'impôt avec une piscine maçonnée. Les syndicats et observateurs rapportent que lors du second passage algorithmique, le taux de détection chute de 20 % à 40 %, et la note de doctrine fiscale indique qu'il est « pleinement assumé des taux de validation plus faibles, incluant une part de rejets parfois significative, qui est la contrepartie d'une volonté de ne pas écarter abusivement des détections fiscalisables ». Ici, le faux positif est considéré comme un coût de traitement inhérent ; la machine ratisse large, et l'élimination définitive du faux positif est déléguée au travail de contrôle asynchrone réalisé ex post par un inspecteur humain avant la mise en recouvrement de l'impôt. La stratégie s'est avérée financièrement rentable, ayant permis l'identification de 20 000 piscines irrégulières en 2022 générant 10 millions d'euros de recouvrement.

Conflation et Normalisation Multi-Sources : L'Approche Overture Maps

Face à la fragmentation des bases de données (Google, Microsoft, OSM, bases de données locales), l'unification des informations nécessite des processus de conflation lourds pour éviter de compter un même bâtiment plusieurs fois. C'est l'objectif de la fondation Overture Maps, qui utilise des techniques d'appariement algorithmique complexes pour fondre ces milliards de géométries divergentes.

Architecture de Déduplication et Clustering par Graphes

L'algorithme de conflation s'appuie sur le Global Entity Reference System (GERS), qui attribue un identifiant unique (GERS ID, anciennement basé sur des attributs locaux, évoluant vers un format UUID généré de manière aléatoire et persistante) à chaque structure du monde réel.

Le processus de déduplication et de correspondance des bâtiments s'opère dans des environnements de calcul distribué (Apache Spark) via des fonctions SQL spatiales (Spatial SQL). La méthode ne se résume pas à vérifier si les centroïdes se chevauchent. La pipeline Overture fonctionne en créant un graphe spatial :
Génération d'Arêtes (Edges) : Des jointures spatiales distribuées évaluent les milliards de polygones des différentes sources. Un chevauchement important (intersection over union - IoU), une correspondance des empreintes au sol, ou une distance minimale entre centroïdes crée une arête mathématique entre deux entités sources.
Identification des Composantes Connexes (Connected Components) : À l'aide de bibliothèques telles que GraphFrames, le système analyse le réseau de nœuds. Tous les enregistrements partageant des connexions fortes forment une « composante connexe », représentant ainsi un groupe de polygones candidats (clusters of likely-same-entity candidates) qui correspondent probablement au même lieu physique.
Sélection et Priorisation : Une fois le cluster identifié, l'algorithme doit décider quelle forme polygonale retenir pour la base de données finale. Overture applique une règle de priorité stricte favorisant la connaissance humaine locale par rapport aux générations d'IA. La hiérarchie de préséance s'établit ainsi : OpenStreetMap > Google Open Buildings > Microsoft Building Footprints.

Ces choix sont traçables. L'ingénierie d'Overture génère mensuellement des « fichiers de pont » (Bridge Files) en format Parquet. Ces fichiers associent l'identifiant universel GERS au record_id exact de la donnée source, exposant ainsi l'intégralité du processus de conflation algorithmique au grand public.

Métriques Qualité : Évaluation et Protocoles d'Échantillonnage

La fiabilité d'une base de données générée par l'IA ne peut être jugée par de simples pourcentages globaux. Les concepteurs de modèles comme Microsoft et Google publient un éventail de métriques qui scrutent tant l'exactitude de la classification sémantique que la fidélité de la géométrie vectorielle par rapport à des références tracées à la main (ground truth).

Le Triptyque de l'Évaluation Géométrique

L'évaluation s'appuie classiquement sur les ratios de Précision (capacité à ne pas générer de faux positifs) et de Rappel (capacité à détecter toutes les structures existantes). À titre d'exemple, le modèle nord-américain de Microsoft affiche une Précision de 98,5 % pour un Rappel de 92,4 %.
Cependant, l'exactitude des empreintes s'évalue au moyen de métriques purement géométriques :

| Métrique Spatiale | Valeur Type (Microsoft) | Description Technique de la Mesure |
|---|---|---|
| Intersection sur Union (IoU) | 0.85 - 0.86 | Standard mesurant la qualité du chevauchement exact entre le polygone prédit et la vérité terrain. |
| Distance de Forme (Shape Distance) | 0.33 - 0.40 | Mesure la similarité mathématique entre les contours extérieurs des polygones indépendamment de leur emplacement absolu. |
| Erreur de Rotation Dominante | 1.6° - 2.5° | Quantifie la déviation en degrés de l'axe principal du polygone prédit par rapport à l'axe réel du bâtiment. |
| Erreur par Pixel | ~1.15 % | Taux de pixels mal classés lors de la première étape de segmentation sémantique (avant polygonisation). |

Méthodologie d'Échantillonnage et Intervalles de Confiance

Étant donné la nature non-exhaustive des bases de référence mondiales, la validation des performances repose sur l'échantillonnage de contrôle rigoureux. Ces méthodes nécessitent des prélèvements suffisamment larges pour satisfaire aux critères de représentativité statistique (intervalles de confiance).

L'ingénierie de mesure de la qualité utilise des formules dérivées de la théorie des sondages. Pour valider l'exactitude d'un sous-ensemble (comme les 146 000 empreintes de la ville de Butuan évaluées aux Philippines), le nombre minimal de vérifications humaines n est déterminé par la formule :

n = (z² · p · (1 − p)) / d²

où z représente le score Z pour un intervalle de confiance cible (par exemple 1,96 pour une fiabilité de 95 %), p la proportion attendue d'exactitude (généralement évaluée expérimentalement), et d correspond à la marge d'erreur admissible. Dans l'exemple de Butuan, cette équation a exigé la vérification manuelle de 13 371 empreintes par des opérateurs pour pouvoir fixer un seuil de confiance optimal et valider le filtrage du jeu de données.

D'autres analyses indépendantes mesurent la dispersion des données (Median Absolute Deviation - MAD) lors de la comparaison spatiale. Des chercheurs évaluant les bases de Microsoft et de Google ont défini un seuil de signification statistique à 1,96 déviation absolue médiane par rapport à l'écart de surface moyen, permettant d'identifier de manière indiscutable les bâtiments pour lesquels les algorithmes de polygonisation divergeaient de manière pathologique (souvent dû au fait que Microsoft englobe de multiples structures denses sous un même polygone, là où Google tend à les fragmenter).

Outillage "Human-in-the-Loop" : Productivité et Débits Réalistes

Malgré la sophistication de ces pipelines, la capacité d'apprentissage des modèles repose intégralement sur des données vérifiées par des humains. Cette ingénierie de la boucle de rétroaction (Human-in-the-Loop - HITL) a dû se transformer en une chaîne d'assemblage industrielle, où la gestion du temps d'attention des annotateurs définit le coût du projet.

Débits d'Annotation Observés

Les rapports de l'industrie issus d'entreprises spécialisées (Label Your Data, CloudFactory, Labelbox) et de projets humanitaires (MapSwipe) fournissent des statistiques extrêmement précises sur la vélocité des opérateurs :
Validation Binaire et Tri Rapide : Pour des tâches simples consistant à vérifier la présence d'une structure (par exemple, confirmer une prédiction de l'IA par un "oui" ou un "non"), un projet comme MapSwipe a calibré son ingénierie sur un temps de traitement estimé à 3 secondes par tâche (ou par tuile). À ce rythme, le débit horaire théorique atteint 1 200 tâches par heure.
Correction Assistée par l'IA : Les agences professionnelles rapportent que des opérateurs qualifiés, bénéficiant d'une pré-annotation par modèle (où ils se contentent d'ajuster les sommets d'un polygone plutôt que de le dessiner de zéro), peuvent maintenir un débit d'environ 1 000 vignettes validées à l'heure, tout en préservant une précision supérieure à 99 %.

| Type d'Intervention Humaine | Tâche Demandée à l'Annotateur | Débit Réaliste Constaté | Gain par rapport au tracé manuel |
|---|---|---|---|
| Validation Binaire | Identifier si un objet (bâtiment, nuage) est présent sur la vignette. | 1 000 - 1 200 images / heure | Critique (Tri très haut volume) |
| Ajustement Assisté (Model-Assisted) | Redimensionner un polygone ou une boîte englobante pré-dessiné par l'IA. | Très variable, mais nettement supérieur à la création pure. | Modéré à Élevé |

Gestion de la Fatigue et Assurance Qualité (QA)

Un tel rendement engendre inévitablement des erreurs humaines. Les pipelines HITL intègrent des mécanismes d'assurance qualité systématiques pour repérer les défaillances. Il est commun d'allouer de 2 à 3 spécialistes de l'assurance qualité pour vérifier le travail de 10 à 20 annotateurs.

Les plateformes injectent secrètement des images de référence (gold standard) dont la réponse est déjà connue pour tester l'attention continue de l'opérateur. Les ingénieurs calculent en permanence l'accord inter-annotateurs (Inter-Annotator Agreement - IAA), souvent via le coefficient Kappa de Fleiss. Si le coefficient Kappa chute en deçà d'un certain seuil (ce qui signifie que les annotateurs humains sont en désaccord fréquent sur un type d'image), le système déclenche une alerte. Ce désaccord est souvent le signe précurseur d'une dérive de données (data drift) nécessitant l'intervention d'experts de haut niveau et un réapprentissage du modèle.

L'Évolution Vers l'Apprentissage Actif (Active Learning)

Acheter des heures d'annotation aléatoires pour des millions d'images s'avère non seulement ruineux, mais aussi inefficace. Une grande partie de l'imagerie terrestre se ressemble (des milliers de kilomètres carrés de forêt ou d'océan), et étiqueter manuellement des exemples redondants n'apporte aucun gain marginal de performance au réseau de neurones.

C'est ici qu'interviennent les protocoles d'Apprentissage Actif (Active Learning). Au lieu de sélectionner aléatoirement les vignettes à soumettre aux humains, un algorithme évalue le sous-ensemble de données pour lequel le modèle de détection est le moins confiant ou le plus désorienté. En orientant l'effort humain exclusivement vers ces cas complexes, les études documentées en télédétection concluent que l'apprentissage actif permet d'atteindre l'exactitude de classification ciblée avec 30 % à 70 % d'exemples annotés en moins par rapport à une sélection aléatoire. Des expériences ont démontré que pour atteindre 99,5 % de la performance d'un modèle saturé de données, les méthodes d'apprentissage actif requièrent de 3,7 à plus de 10,6 fois moins de labellisation qu'un échantillonnage aléatoire.

Stratégies d'Échantillonnage par Incertitude (Uncertainty Sampling)

Les algorithmes traditionnels d'apprentissage actif s'appuient sur l'extraction mathématique de l'incertitude du réseau de neurones face à une image :
Échantillonnage de Moindre Confiance (Least Confidence) : L'algorithme sélectionne la prédiction pour laquelle la probabilité absolue pour la classe la plus vraisemblable est la plus basse. C'est l'approche la plus directe, mais elle est très sensible aux erreurs de calibration du modèle.
Échantillonnage par la Marge (Margin Sampling) : Le modèle calcule la différence de probabilité entre sa première prédiction et sa deuxième prédiction la plus probable. Une différence minime indique une forte ambiguïté, propulsant cette image en haut de la file d'attente d'annotation.
Incertitude Basée sur l'Entropie (Entropy Sampling) : Utilise la théorie de l'information pour évaluer la dispersion de toutes les probabilités des différentes classes. Une forte entropie correspond à une incapacité globale du modèle à discerner le contenu.
Requête par Comité (Query-by-Committee) : Un ensemble (ensemble) de modèles différents analyse la même image. Plus le désaccord entre les modèles du comité est grand, plus la vignette est prioritaire pour la vérification humaine.

Les Limites de l'Incertitude et l'Introduction de la Diversité

Bien qu'efficace, l'échantillonnage par simple incertitude souffre d'un défaut critique identifié par les ingénieurs : le biais d'échantillonnage. Si un modèle est mauvais pour détecter des toits métalliques rouillés, l'algorithme d'incertitude remplira la file d'attente des opérateurs avec un million d'exemples de toits métalliques rouillés. Or, apprendre la même leçon à l'excès n'apporte plus d'informations au modèle (redondance).

Les pipelines modernes de détection géospatiale (2025-2026) intègrent donc des contraintes de diversité :
Méthodes à double objectif (Dual-Objective AL) : Les algorithmes évaluent d'abord l'incertitude (souvent en s'appuyant sur des modèles de fondation comme le Segment Anything Model de Meta pour repérer les écarts de délimitation). Ensuite, ils évaluent la diversité des masques à l'aide de l'analyse des caractéristiques pour éviter d'échantillonner des objets trop similaires visuellement au sein d'un même lot.
Gain d'Information de Vendi (VIG - Vendi Information Gain) : Il s'agit d'une politique avancée qui ne se contente pas d'examiner l'incertitude d'une prédiction isolée. En utilisant des réseaux neuronaux avec dropout, le VIG mesure comment la labellisation d'une image spécifique réduirait mathématiquement l'incertitude à l'échelle de l'ensemble de la base de données. Les tests documentés démontrent que le VIG permet d'atteindre une précision prédictive de 88 % en n'utilisant que 10 % des données disponibles (soit une amélioration de 12 % par rapport aux algorithmes d'apprentissage actif de base pour la même quantité d'effort humain).

Synthèse

L'analyse de l'ingénierie contemporaine déployée par Microsoft, Google et Overture Maps démontre que la détection d'objets à grande échelle dans le domaine spatial a largement dépassé le simple défi de la vision par ordinateur pour s'inscrire dans une logique d'ingénierie globale de la donnée. Le problème de fond ne réside plus dans la détection au niveau du pixel, mais dans l'harmonisation spatiale et architecturale.

Microsoft a prouvé qu'un nettoyage purement neuronal était insuffisant, imposant avec succès des règles architecturales probabilistes (a priori properties telles que l'orthogonalité contrainte) pour garantir l'utilisabilité SIG des empreintes de bâtiments. Google a démontré l'absolue nécessité de l'agrégation temporelle et du masquage croisé avec des données hydrologiques (GSW) ou d'élévation (NASADEM) pour éradiquer des faux positifs réfractaires à toute simple classification d'image. De son côté, l'initiative Overture Maps a relevé le défi de la conflation mondiale en abandonnant les jointures naïves au profit d'infrastructures de graphes distribués (Spark, Composantes Connexes), offrant avec le système GERS une traçabilité fondamentale dans la manière dont les conflits entre sources sont arbitrés.

Cependant, le pilier qui soutient l'amélioration continue de ces systèmes demeure le facteur humain. Gérer l'attention d'annotateurs soumis à des cadences extrêmes de 1 200 tâches par heure impose un outillage algorithmique extrêmement rigoureux (ratios QA, calculs d'accords inter-annotateurs). L'adoption de protocoles d'apprentissage actif ne répond pas qu'à une recherche de performance théorique, elle incarne une solution économique indispensable. La migration documentée de l'échantillonnage basique par moindre confiance vers des algorithmes de réduction de l'entropie globale comme le Gain d'Information de Vendi (VIG) prouve que l'industrie cherche continuellement à extraire le signal le plus significatif du bruit ambiant des pétabytes d'imagerie terrestre. L'avenir de ces pipelines ne réside pas dans l'entraînement sur des volumes de données plus massifs, mais dans la sélection de plus en plus intelligente des données à observer.
