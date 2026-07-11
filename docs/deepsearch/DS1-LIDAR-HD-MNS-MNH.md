# DS1 — LiDAR HD : dalles MNS/MNH du 49 (prompt ②)

> Collé le 2026-07-11 (Gemini 3.5 Pro). Voir doctrine de lecture dans [README.md](README.md).

## Ce qu'on en retient (analyse 2026-07-11)

**Exploitable directement (à vérifier au premier run P2, pas avant) :**
- Téléchargement direct sans auth : racine `https://diffusion-lidarhd.ign.fr/mnx/` ;
  interfaces `cartes.gouv.fr/telechargement/IGNF_MNS-LIDAR-HD` et `..._MNH-LIDAR-HD`.
- Tableaux d'assemblage via WFS `https://data.geopf.fr/wfs/ows` — couches
  `IGNF_MNS_LIDAR-HD:dalle` et `IGNF_MNH_LIDAR-HD:dalle` (BBOX → URL de chaque dalle).
- Format : GeoTIFF float32, 50 cm, dalles 1 km, Lambert-93/IGN69, nommage par coordonnées
  km (Angers ≈ X 0430 / Y 6710). Cohérent avec `05-PIPELINE-TERRASSES.md`.
- Couverture 49 quasi complète mais PAS garantie 100 % (livraison par blocs, ~15 mois de
  délai vol→raster) → le fallback PDAL de `05` §Étapes reste la bonne parade.

**⚠ Le point qui change quelque chose — crue du 7 mars 2024 (plausible, à vérifier
empiriquement) :** une partie des vols du 49 (bassins Sarthe/Loir, Basses Vallées
Angevines, Authion) aurait été acquise en crue. Conséquences physiques si vrai :
- MNT = surface de l'eau (plate, surélevée) dans les lits majeurs → **MNH sous-estimé**
  (bâtiments et arbres « raccourcis » de la hauteur de la lame d'eau) ;
- acquisition hivernale « leaf-off » → MNS sous-estime la canopée d'été (le masque
  MNH « canopée » de `terrasses.py` devient moins protecteur en zone boisée).
- Vérification empirique au premier run P2 : chercher les grandes zones de pente
  strictement nulle hors plans d'eau BD TOPO le long de la Sarthe/du Loir.
- Parade si confirmé : masquer/dégrader la confiance des parcelles en lit majeur
  (croiser avec surfaces hydro BD TOPO + zones planes anormales) — PAS d'hybridation
  RGE ALTI en phase 2 (overkill : on classe des jardins, pas de l'hydraulique).
- Impact business faible : les maisons cibles de P2 sont rarement en zone inondable,
  mais une adresse fausse en démo coûte cher → flag, pas pivot.

**ZICAD (confirmé comme mécanisme général) :** zones militaires (Saumur…) = NoData
définitif dans MNS/MNH. À consigner comme trou de couverture assumé dans les exports P2.

**Ignoré volontairement :** la section « rectification hydrologique » (hybridation
RGE ALTI 2013, lissage focal) — pertinente pour de l'hydraulique, pas pour un score
d'ensoleillement de jardins. Ne pas implémenter.

---

## Texte brut du deepsearch

Rapport d'Expertise Technique : Exploitation des Produits Dérivés LiDAR HD (MNS et MNH) de l'IGN pour le Département du Maine-et-Loire (49)

1. Contextualisation Stratégique et Fondements Technologiques du Programme LiDAR HD

L'appréhension topographique et morphologique du territoire national français a franchi un seuil technologique décisif avec le déploiement du programme LiDAR Haute Densité (LiDAR HD), coordonné par l'Institut national de l'information géographique et forestière (IGN). Inscrit initialement dans le cadre du plan France Relance avec un budget de cinquante-sept millions d'euros, ce projet titanesque ambitionne de cartographier l'intégralité du territoire métropolitain et des départements d'outre-mer (à l'exception de la Guyane) d'ici l'horizon 2025-2026. Cette initiative représente une rupture fondamentale par rapport aux campagnes photogrammétriques traditionnelles ou aux bases de données altimétriques historiques de type RGE ALTI, en offrant une résolution et une précision tridimensionnelle inédites pour l'action publique, la prévention des risques, la gestion forestière et l'aménagement du territoire.

La technologie sous-jacente repose sur la télémétrie par laser aéroporté (Light Detection and Ranging). Les aéronefs de l'IGN, ou ceux des groupements de sous-traitants mandatés, survolent le territoire en émettant des impulsions lumineuses dans le spectre du proche infrarouge, typiquement à une longueur d'onde de 1064 nanomètres. La fréquence d'émission de ces impulsions, associée à une vitesse de vol calibrée autour de 260 kilomètres par heure (72 mètres par seconde) et un recouvrement inter-bandes de trente pour cent, garantit une densité moyenne de dix points par mètre carré au sol. Le récepteur embarqué capte les échos réfléchis par les différentes surfaces interceptées par le faisceau laser, enregistrant avec une précision nanoseconde le temps de vol de chaque photon, ce qui permet d'en déduire la distance exacte et, par couplage avec des centrales inertielles et des systèmes de positionnement par satellites (GNSS), les coordonnées absolues en trois dimensions de chaque point d'impact.

Le cahier des charges rigoureux de l'IGN impose des tolérances géométriques extrêmement strictes pour ces nuages de points bruts. La précision altimétrique absolue (l'axe Z) doit être inférieure à dix centimètres, tandis que la précision planimétrique absolue (les axes X et Y) doit être inférieure à cinquante centimètres sur des surfaces dures et planes. Une fois ces données acquises, un défi majeur d'ingénierie informatique débute : la classification sémantique de milliards de points. Contrairement aux approches historiques qui se limitaient à distinguer le sol du reste pour produire des Modèles Numériques de Terrain (MNT), le programme LiDAR HD intègre des processus hybrides mêlant algorithmes heuristiques traditionnels et intelligence artificielle (Deep Learning) pour attribuer à chaque point une classe spécifique. Le nuage de points est ainsi segmenté en diverses catégories : le sol nu, les surfaces en eau, la végétation stratifiée en trois niveaux (basse, moyenne et haute), les bâtiments, les ponts, et les artefacts.

C'est à partir de cette matrice de points classifiés que l'IGN procède à la dérivation des modèles matriciels, dits "MNx", qui font l'objet de la présente analyse. Le Modèle Numérique de Surface (MNS) est généré en interpolant systématiquement les points présentant l'élévation maximale pour une maille donnée, capturant ainsi l'enveloppe supérieure visible du territoire, incluant la canopée forestière, les toitures, les infrastructures et le sol dénudé. À l'inverse, le Modèle Numérique de Terrain (MNT) est produit en isolant rigoureusement les points classés comme "sol" et "eau", puis en appliquant des algorithmes de triangulation (comme les réseaux irréguliers triangulés ou TIN) pour interpoler les zones rendues invisibles par le couvert végétal ou le bâti. Le Modèle Numérique de Hauteur (MNH), quant à lui, n'est pas une donnée directement acquise mais un produit dérivé calculé par soustraction matricielle stricte entre le MNS et le MNT. Ce MNH exprime ainsi la hauteur relative de tous les éléments du sursol par rapport au terrain naturel, constituant une donnée d'entrée fondamentale pour la modélisation de la biomasse, l'urbanisme réglementaire ou la cartographie des risques de co-visibilité.

Pour un projet d'entreprise ciblant le département du Maine-et-Loire (49), la maîtrise technique de ces produits dérivés est primordiale. L'intégration de ces rasters dans un pipeline d'analyse spatiale requiert une compréhension exhaustive des protocoles de diffusion mis en place par l'État, des architectures de nommage des fichiers, des formats d'encodage géospatiaux, ainsi que des spécificités géomorphologiques et temporelles des campagnes de vol ayant couvert le territoire angevin.

2. Architectures de Diffusion et Protocoles d'Accès aux Données Matricielles

La stratégie de diffusion de l'information géographique souveraine a profondément évolué avec l'avènement de la Géoplateforme, destinée à remplacer progressivement les infrastructures historiques du portail Géoservices. Pour répondre aux besoins industriels d'acquisition en masse des dalles MNS et MNH sur un territoire aussi vaste que le Maine-et-Loire, il convient de dépasser l'usage des interfaces graphiques de téléchargement manuel pour s'orienter vers des protocoles d'accès directs et programmatiques.

2.1. Les Canaux d'Acquisition Directs et les Chemins d'Accès

L'État met à disposition plusieurs paradigmes d'accès aux données matricielles, chacun répondant à des contraintes d'automatisation différentes. Pour un utilisateur souhaitant visualiser et sélectionner interactivement des dalles, le portail cartes.gouv.fr propose des interfaces dédiées. Le chemin d'accès public pour le téléchargement interactif du Modèle Numérique de Surface est https://cartes.gouv.fr/telechargement/IGNF_MNS-LIDAR-HD, et celui correspondant au Modèle Numérique de Hauteur est https://cartes.gouv.fr/telechargement/IGNF_MNH-LIDAR-HD. Ces interfaces permettent de définir des polygones d'emprise et de générer des archives compressées contenant les dalles intersectées.

Néanmoins, dans le cadre d'un projet d'entreprise nécessitant une intégration continue ou le traitement exhaustif des milliers de kilomètres carrés du département 49, cette méthode manuelle est proscrite. L'approche industrielle requiert l'accès direct aux serveurs de fichiers (Directory Listing) mis en place par l'IGN. L'URL racine permettant d'accéder directement à l'arborescence des fichiers matriciels MNS, MNT et MNH est https://diffusion-lidarhd.ign.fr/mnx/. Ce répertoire ouvert expose les fichiers bruts, permettant à des scripts Python ou à des utilitaires en ligne de commande tels que wget ou curl d'aspirer les données de manière séquentielle ou asynchrone, sans nécessiter d'authentification ou de jetons d'accès, les données étant distribuées sous Licence Ouverte (Etalab 2.0).

Pour identifier avec précision quelles dalles doivent être rapatriées depuis cette racine, le développeur SIG doit s'appuyer sur les services web de type Web Feature Service (WFS). Le WFS permet d'interroger la base de données de l'IGN pour récupérer les polygones d'emprise (les tableaux d'assemblage) de chaque dalle existante. Le point d'entrée principal de l'API de la Géoplateforme pour ces requêtes spatiales est https://data.geopf.fr/wfs/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities. Au sein de ce service, les couches de données contenant la géométrie des dalles et leurs métadonnées associées portent des identifiants spécifiques. Pour le MNS, il s'agit de la couche IGNF_MNS_LIDAR-HD:dalle (ou historiquement IGNF_LIDAR-HD_TA:mns-dalle), et pour le MNH, de la couche IGNF_MNH_LIDAR-HD:dalle (ou IGNF_LIDAR-HD_TA:mnh-dalle).

En forgeant une requête spatiale (opérateur BBOX) encadrant les coordonnées géographiques du Maine-et-Loire, le service WFS retourne une réponse au format XML/GML ou GeoJSON. Cette réponse documente de manière exhaustive chaque dalle interceptant le département, fournissant non seulement son emprise spatiale exacte, son statut de disponibilité, mais également l'URL directe du fichier GeoTIFF correspondant hébergé sur le domaine diffusion-lidarhd.ign.fr. Cette mécanique permet de construire des pipelines de données résilients, capables de se mettre à jour automatiquement dès que l'IGN publie de nouveaux blocs sur le territoire.

2.2. Spécifications du Format, Projections Cartographiques et Résolution

Les produits dérivés MNS et MNH sont standardisés selon des spécifications informatiques et géodésiques extrêmement rigoureuses, indispensables pour garantir l'interopérabilité des calculs volumétriques et altimétriques.

Le format de diffusion exclusif pour ces modèles matriciels est le GeoTIFF (Geographic Tagged Image File Format, extension .tif), une évolution du format TIFF classique intégrant nativement les balises de géoréférencement (projection, coordonnées de l'origine, taille du pixel) dans l'en-tête du fichier. Pour éviter les artefacts d'arrondi et conserver la précision centimétrique issue du nuage de points, l'IGN encode ces rasters en trente-deux bits virgule flottante (32-bit floating point). Ce niveau de profondeur de pixel est crucial : un encodage en nombres entiers (16 bits) produirait un phénomène de "terrassement" ou d'escalier sur les pentes douces, rendant les calculs de rugosité hydraulique ou d'exposition solaire caducs.

La résolution spatiale (le pas de la grille) nominale retenue pour le programme national est de cinquante centimètres. Cela signifie que chaque pixel de l'image GeoTIFF représente une surface réelle de 0,25 mètre carré au sol. Cette ultra-haute résolution permet de modéliser avec fidélité les faîtages de toitures, les haies bocagères fines, les murets de soutènement, ou encore les micro-reliefs hydrographiques qui jalonnent le bassin de la Loire. Une version sous-échantillonnée à cinq mètres de résolution est également générée pour faciliter les calculs à l'échelle macroscopique ou régionale, réduisant ainsi drastiquement la charge de calcul en mémoire vive (RAM).

Le système de coordonnées de référence (SCR) est le fondement de la validité juridique et technique de ces données. En planimétrie (les axes horizontaux X et Y), les dalles sont projetées dans le système Lambert 93, associé à l'identifiant EPSG:2154. Cette projection conique conforme sécante est le standard légal pour la France métropolitaine, assurant que les mesures de distances et d'angles conservent leur justesse. En altimétrie (l'axe vertical Z), les valeurs encodées dans les pixels du GeoTIFF sont exprimées en mètres selon le référentiel du Nivellement Général de la France (NGF), plus précisément le système IGN69. Cette cohérence tridimensionnelle garantit que le MNS et le MNH peuvent être superposés sans aucune translation avec le cadastre, les réseaux enterrés ou les bases de données d'occupation du sol.

| Caractéristique Technique | Spécification Officielle IGN LiDAR HD |
|---|---|
| Format de Fichier | GeoTIFF (.tif) |
| Encodage Radiométrique | 32 bits virgule flottante (floating point) |
| Résolution Spatiale (Pas) | 50 centimètres (0,5 m) et déclinaison à 5 mètres |
| Projection Planimétrique | RGF93 / Lambert 93 (Code EPSG:2154) |
| Référentiel Altimétrique | NGF - IGN69 (Altitudes exprimées en mètres) |
| Poids Moyen par Dalle | ~24 Mo (non compressé pour 1 km² à 50 cm de résolution) |

2.3. Schéma Syntaxique et Mécanique de Nommage des Dalles

La distribution géographique des données obéit à un pavage régulier du territoire sous forme de dalles carrées d'un kilomètre de côté. Le nommage de ces fichiers matriciels est conçu pour être sémantiquement transparent, permettant aux algorithmes de déterminer la localisation exacte d'un fichier en parsant uniquement sa chaîne de caractères.

La nomenclature formelle s'appuie sur l'identification des coordonnées du point d'ancrage de la dalle, généralement son coin supérieur gauche (Nord-Ouest). Le schéma de base documenté par la structure des données ouvertes indique une forme nominale structurée autour des axes de projection. La syntaxe générique prend la forme explicite de la combinaison de l'identifiant du produit, de la coordonnée en abscisse (Xmin) et de la coordonnée en ordonnée (Ymax), souvent formatée comme [PRODUIT]_[Xmin]_[Ymax]_MNS-TIF ou une déclinaison équivalente propre aux chaînes de production récentes de la Géoplateforme.

Dans la nomenclature exhaustive observée sur les serveurs de l'IGN, un nom de fichier matriciel MNS complet adoptera une structure similaire à : MNS_LHD_FXX_[Xmin]_[Ymax]_LAMB93_IGN69.tif (ou des variations syntaxiques mineures validées par les contrôles de qualité, telles que dtm0m50_LHD_FXX_[Xmin]_[Ymax]_... pour le MNT à 50 cm). Dans ce formalisme, LHD identifie le programme LiDAR HD, et FXX certifie l'appartenance à la France métropolitaine. Les variables cruciales [Xmin] et [Ymax] sont exprimées en kilomètres dans le référentiel Lambert 93.

À titre d'illustration pratique pour le Maine-et-Loire, une dalle située au cœur de la ville d'Angers correspond approximativement à une abscisse (X) de 430 kilomètres et une ordonnée (Y) de 6710 kilomètres en projection Lambert 93. L'algorithme de téléchargement de l'entreprise devra donc forger une requête pour localiser une chaîne de caractères contenant _0430_6710_ au sein de l'arborescence du domaine diffusion-lidarhd.ign.fr/mnx/. Cette prévisibilité syntaxique dispense les systèmes d'information géographiques de devoir ouvrir le fichier physique pour en extraire l'enveloppe spatiale, optimisant ainsi considérablement les temps de traitement lors de la constitution de la base de données interne.

| Champ Syntaxique | Signification et Format Attendu |
|---|---|
| Produit | Identifiant matriciel : MNS, MNT ou MNH |
| Programme | LHD (LiDAR HD) |
| Territoire | FXX (France Métropolitaine) |
| Coordonnée Xmin | Abscisse minimale de la dalle, en kilomètres Lambert 93 (ex: 0430) |
| Coordonnée Ymax | Ordonnée maximale de la dalle, en kilomètres Lambert 93 (ex: 6710) |
| Système de Référence | LAMB93_IGN69 (Garantie de la projection et de l'altimétrie) |

3. État de la Couverture du Maine-et-Loire (49) en 2026 et Stratégies de Contingence

L'évaluation de la complétude du programme LiDAR HD sur un département spécifique nécessite de distinguer la phase d'acquisition aérienne des phases de post-traitement algorithmique. En 2026, l'IGN a achevé la vaste majorité des campagnes d'acquisition aéroportées couvrant l'hexagone, l'objectif d'achèvement de la captation étant initialement fixé à fin 2025 ou courant 2026.

3.1. Progression des Livraisons Raster et Lacunes Potentielles

Bien que l'acquisition physique du Maine-et-Loire soit actée et que la diffusion des nuages de points classifiés sous format LAZ ou COPC soit très largement disponible sur la Géoplateforme, l'entreprise doit anticiper une discordance temporelle concernant les produits dérivés matriciels. Le processus industriel de l'IGN implique un décalage substantiel, estimé en moyenne à une quinzaine de mois entre le vol d'acquisition, l'étalonnage de la trajectographie, la classification hybride par intelligence artificielle, le contrôle qualité humain et la rasterisation finale des modèles MNS, MNT et MNH.

De fait, bien que la couverture du Maine-et-Loire en dalles matricielles s'approche d'une complétude totale en 2026, il serait périlleux d'affirmer que 100 % des pixels du département sont couverts par un GeoTIFF validé et publié. Le processus de validation s'opérant par "blocs" d'acquisition géographiques (de l'ordre de 50 km par 50 km), des zones spécifiques, notamment les marges départementales ou des secteurs ayant nécessité des reprises d'algorithmes complexes, peuvent temporairement manquer à l'appel lors de l'interrogation du service WFS.

Par ailleurs, un écueil légal et sécuritaire entrave structurellement l'atteinte d'une couverture matricielle de 100 %. Le territoire français est parsemé de Zones Interdites à la Captation Aérienne des Données (ZICAD). Le Maine-et-Loire, abritant des infrastructures sensibles, notamment militaires (telles que les installations liées aux écoles de cavalerie de Saumur ou certains pôles de communication), est directement concerné. Conformément à la réglementation en vigueur protégeant le secret de la défense nationale, l'IGN procède à un masquage délibéré et irréversible de ces périmètres lors de la génération des MNS et MNH. Sur ces emprises, le fichier GeoTIFF contiendra une valeur d'encodage spécifique (NoData), et il n'existe aucune procédure civile permettant d'outrepasser cette restriction pour récupérer la topographie ou le sursol censuré.

3.2. Méthodologie de Rasterisation Manuelle depuis les Nuages de Points

Face à l'éventualité de zones manquantes (en dehors des ZICAD) où les dalles MNS ou MNH n'auraient pas encore été publiées, le projet d'entreprise ne doit pas subir de blocage opérationnel. La disponibilité précoce des nuages de points classifiés permet en effet d'opérer une rasterisation autonome.

La méthodologie consiste à rapatrier les fichiers de nuages de points correspondants (généralement distribués au format indexé spatialement COPC - Cloud Optimized Point Cloud - ou LAZ) via le flux IGNF_NUAGES-DE-POINTS-LIDAR-HD:dalles. Ces fichiers contiennent des millions de points tridimensionnels assortis d'un attribut de classification (allant de la classe 1 pour les entités non classifiées à la classe 9 pour l'eau, en passant par la classe 2 pour le sol et la classe 6 pour le bâti).

Pour générer un Modèle Numérique de Surface (MNS) à une résolution de 50 centimètres, les outils géospatiaux (tels que la bibliothèque lidR sous l'environnement R, la suite PDAL en ligne de commande, ou les algorithmes de la boîte à outils LAStools intégrés à QGIS) vont balayer le nuage de points et superposer une grille virtuelle de 0,5 m de côté. Pour chaque cellule de la grille, l'algorithme identifiera le point présentant l'élévation (Z) maximale, indépendamment de sa classe sémantique (à l'exclusion des points catégorisés comme artefacts ou bruits), et inscrira cette valeur dans le pixel du raster.

La génération du Modèle Numérique de Terrain (MNT) obéit à une logique différente. L'algorithme filtrera rigoureusement le nuage de points pour ne conserver que les entités étiquetées "sol" (classe 2) et potentiellement "eau" (classe 9). Le logiciel déploiera ensuite un réseau triangulé irrégulier (TIN) ou une méthode d'interpolation par pondération inverse à la distance (IDW) pour créer une surface continue de 50 cm de résolution, extrapolant ainsi le relief sous les bâtiments ou les forêts.

Enfin, la création du Modèle Numérique de Hauteur (MNH) s'effectue par une simple opération d'algèbre de cartes (Map Algebra), en soustrayant matriciellement le MNT préalablement calculé du MNS généré (Raster_MNS - Raster_MNT = Raster_MNH). Cette chaîne de traitement locale garantit à l'entreprise une autonomie totale et la capacité de finaliser la couverture du 49 sans dépendre du calendrier résiduel de l'IGN.

4. L'Anomalie du Millésime : L'Acquisition LiDAR face aux Crues de Mars 2024

La donnée géospatiale la plus critique dans l'exploitation des campagnes LiDAR aéroportées est la date précise d'acquisition, communément appelée millésime. Contrairement aux bases de données topographiques entretenues de manière continue, un vol LiDAR fige la morphologie du territoire à un instant T précis. La compréhension intime des conditions environnementales prévalant lors de ce vol est une condition sine qua non pour la justesse des modélisations futures.

Le département du Maine-et-Loire présente un contexte hydrogéologique complexe. Territoire de confluences, il est drainé par la Loire, mais également par les Basses Vallées Angevines qui collectent les eaux de la Mayenne, de la Sarthe et du Loir avant de former la Maine au cœur d'Angers. Le croisement des archives d'acquisition de l'IGN et des signalements techniques remontés par les experts géomaticiens de la communauté établit formellement que de vastes séquences de vol couvrant ce département, et particulièrement les bassins versants de la Sarthe et du Loir, ont été opérées à la charnière de l'hiver et du printemps 2024, avec un point d'orgue autour du 7 mars 2024.

4.1. Les Conséquences Physiques d'un Levé en Période de Crue

La criticité de ce millésime du 7 mars 2024 réside dans le fait qu'il a coïncidé avec un épisode de crue significatif affectant le réseau hydrographique angevin. De multiples témoignages d'utilisateurs professionnels ont acté que les rivières étaient sorties de leur lit mineur au moment du passage des aéronefs de l'IGN, inondant largement les lits majeurs et les plaines alluviales environnantes ("les rivières étant en crue au moment du levé par l'IGN (7 mars 2024)").

La physique de la télémétrie laser est formelle face à de telles conditions. Les faisceaux émis dans le domaine du proche infrarouge (1064 nm) sont fortement absorbés par l'eau, générant une pénurie d'échos en retour ("dropouts") au-dessus des surfaces liquides. Lorsque l'eau est trouble ou présente des matières en suspension, certains échos de surface peuvent être enregistrés. Dans le processus de génération du Modèle Numérique de Terrain (MNT), les algorithmes de l'IGN assimilent la surface de l'eau à l'élévation du sol naturel, interpolant un plan d'eau plat entre les berges.

En période d'étiage, ce processus modélise correctement le lit mineur. Cependant, sous le régime de crue de mars 2024, la nappe d'eau s'étendait sur des kilomètres carrés de prairies, de routes submersibles et de fossés de drainage. Par conséquent, la topographie réelle de ces lits majeurs, parfois submergée sous plusieurs mètres de colonne d'eau, a été physiquement oblitérée de l'enregistrement. Le MNT diffusé par l'IGN sur ces secteurs inondés du Maine-et-Loire ne représente donc pas le sol véritable, mais l'altitude du pic de crue du 7 mars 2024, se traduisant par des surfaces anormalement planes et surélevées.

4.2. Impact en Cascade sur les Modèles MNS et MNH

L'altération du MNT par l'élévation temporaire du plan d'eau entraîne un effet de bord en cascade sur l'ensemble des produits dérivés, et tout particulièrement sur le Modèle Numérique de Hauteur (MNH), compromettant directement son utilisation brute pour des applications d'ingénierie.

Le MNH étant la soustraction du MNT au MNS, toute erreur altimétrique positive sur le sol fictif réduit mathématiquement la hauteur des éléments du sursol. Prenons l'exemple d'une infrastructure agricole de six mètres de haut située dans la zone d'expansion des crues près de Durtal ou de Cheffes-sur-Sarthe. Si, le 7 mars 2024, le bâtiment baignait dans deux mètres d'eau, le MNT a été interpolé à l'altitude de la crue, soit deux mètres au-dessus du sol réel. L'impulsion laser ayant percuté la toiture, le MNS enregistre correctement l'altitude absolue du bâtiment. Toutefois, la soustraction opérée par l'IGN pour générer le MNH (Altitude MNS - Altitude MNT inondé) indiquera que le bâtiment ne mesure que quatre mètres de hauteur relative.

Ce phénomène affecte identiquement la caractérisation de la végétation ripisylve ou des haies bocagères du Maine-et-Loire. Les troncs étant partiellement immergés, la hauteur de la canopée calculée dans le MNH s'en trouve artificiellement amputée, ce qui induit de graves biais dans l'estimation de la biomasse forestière, le calcul des volumes de bois sur pied ou la modélisation de la rugosité aérodynamique du territoire.

| Entité Modélisée (en zone inondable) | État Réel Hors Crue | Modélisation MNS (Alt. Absolue) | Modélisation MNT (Alt. Sol) | MNH Résultant (Hauteur MNS-MNT) | Biais du Millésime Mars 2024 |
|---|---|---|---|---|---|
| Bâtiment de 6 mètres | Sol à 20m, Toit à 26m | 26 m | 22 m (Lame d'eau de 2m) | 4 m | Sous-estimation de 2 mètres |
| Arbre de 15 mètres | Sol à 18m, Cime à 33m | 33 m | 20 m (Lame d'eau de 2m) | 13 m | Sous-estimation de 2 mètres |
| Route Submersible | Sol à 21m | 23 m (Surface de l'eau) | 23 m (Surface de l'eau) | 0 m | Perte totale de la topographie |

Un second biais temporel lié à ce millésime précoce de mars 2024 concerne la phénologie. L'acquisition a été réalisée en période hivernale, avant le débourrement printanier de la majorité des feuillus (chênes, frênes, peupliers) qui composent les forêts et le bocage du département. Cette configuration en l'absence de feuilles ("leaf-off") est certes idéale pour permettre aux impulsions laser de percer la canopée et d'atteindre le sol (garantissant un excellent MNT en zone non inondée), mais elle fragilise la construction du MNS sur les zones boisées. Le laser rebondissant principalement sur l'ossature des branches, le MNS peut sous-estimer la densité réelle et le sommet absolu du dôme foliaire estival, une variable à intégrer dans les marges d'erreur des algorithmes de calcul de biomasse.

5. Intégration Métier et Stratégies de Rectification Analytique

L'intégration des dalles MNS et MNH dans les chaînes de valeur de l'entreprise exige non seulement des compétences en ingénierie logicielle pour orchestrer les téléchargements, mais surtout une expertise en science de la donnée spatiale pour pallier les anomalies physiques inhérentes au millésime du Maine-et-Loire.

5.1. Cas d'Usage Stratégiques : Du Solaire à l'Urbanisme

Les produits dérivés matriciels permettent de systématiser des analyses qui requéraient auparavant de coûteuses campagnes aéroportées privées ou des relevés topographiques au sol fastidieux.

Dans le domaine de la transition énergétique, l'évaluation du potentiel solaire des toitures à l'échelle du département (cadastre solaire) s'appuie fondamentalement sur l'exploitation du Modèle Numérique de Surface (MNS). L'ingénierie consiste à injecter le MNS de l'IGN dans des algorithmes d'ensoleillement (de type Solar Radiation ou Hillshade). Il est impératif d'utiliser le MNS et non le MNH pour cette tâche. Le MNS intègre en effet l'altitude absolue du terrain, permettant aux algorithmes de calculer la trajectoire du soleil et d'anticiper les ombres portées par la topographie environnante (par exemple, l'ombre hivernale générée par les coteaux tuffacés dominant la Loire dans le Saumurois, ou l'impact des crêtes du Layon).

Pour les acteurs de l'aménagement du territoire, la télécommunication ou l'assurance, le Modèle Numérique de Hauteur (MNH) est le vecteur privilégié pour la création de Jumeaux Numériques urbains. En combinant par croisement spatial les polygones d'emprise des bâtiments (issus de la couche BD TOPO® de l'IGN ou du cadastre) avec la matrice du MNH, les outils SIG peuvent extraire des métriques statistiques complexes pour chaque édifice : hauteur maximale au faîtage, hauteur médiane, profil de la toiture (plate ou à double pente). Cette automatisation permet de cartographier instantanément la rugosité urbaine, d'identifier les extensions construites non déclarées, ou de simuler la propagation des ondes radiofréquences en détectant le moindre obstacle arboré de plus de quelques mètres de haut.

5.2. Rectification Hydrologique : Hybridation des Modèles Altimétriques

L'altération de la topographie dans les Basses Vallées Angevines et les lits majeurs de la Sarthe, du Loir et de la Maine due aux crues du 7 mars 2024 impose à l'entreprise de développer un algorithme de correction (raster patching ou mosaicking) sous peine de fournir des résultats erronés à ses clients ou à ses instances décisionnelles. L'usage brut du LiDAR HD 2024 pour modéliser des zones d'expansion de crues (PPRI) ou calculer des déblais/remblais en zone inondable est techniquement disqualifié par l'aplatissement du relief opéré par la masse d'eau.

La méthodologie de remédiation repose sur la fusion de données multi-sources. Le protocole analytique recommandé se déploie en plusieurs étapes :
Premièrement, isoler spatialement les emprises affectées par la crue. Cette opération s'effectue en appliquant un masque sur le MNT généré à partir du LiDAR HD. Les zones d'eau planes peuvent être détectées par des algorithmes d'analyse géomorphologique repérant les pentes strictement nulles (slope = 0) couplés à l'extraction de la classe "eau" du nuage de points originel.
Dans un second temps, l'entreprise doit purger ces zones inondées des dalles MNS et MNT du LiDAR HD, créant ainsi des vides de données délibérés.
Enfin, ces vides doivent être comblés mathématiquement par des données altimétriques issues des référentiels historiques de l'IGN. Le recours aux dalles du RGE ALTI® (qui présente une résolution de un mètre ou cinq mètres selon les secteurs) acquises lors de campagnes antérieures (par exemple le millésime 2013 évoqué par les géomaticiens locaux), réalisées en période de basses eaux, permet de restituer la topographie exacte du sol et des berges. Une interpolation de lissage focal le long des lignes de couture entre le modèle récent (2024) et le modèle historique (2013) garantira la continuité des écoulements pour les calculs hydrauliques futurs.

6. Synthèse et Orientations Stratégiques

L'intégration des modèles matriciels MNS et MNH issus du programme LiDAR HD de l'IGN représente une opportunité transformationnelle pour les projets d'entreprise nécessitant une connaissance millimétrique du territoire. Le département du Maine-et-Loire bénéficie d'une couverture de données d'une très haute résolution spatiale (50 centimètres), ouvrant le champ à des modélisations impossibles il y a encore une décennie.

Pour garantir la pérennité et la robustesse de l'exploitation de ces produits dérivés en open data, les ingénieurs et décideurs doivent impérativement articuler leur architecture autour de trois piliers fondamentaux.

L'automatisation des flux d'acquisition s'impose comme une nécessité absolue face à la volumétrie des données. L'interrogation dynamique des services WFS de la Géoplateforme, via le ciblage des couches IGNF_MNS_LIDAR-HD:dalle et IGNF_MNH_LIDAR-HD:dalle, couplée à la construction algorithmique des requêtes de téléchargement direct sur le répertoire diffusion-lidarhd.ign.fr/mnx/, permettra au système d'information de l'entreprise de se maintenir en permanence synchronisé avec les publications itératives de l'État. La maîtrise de la syntaxe de nommage des fichiers GeoTIFF, s'appuyant sur les coordonnées Lambert 93 de la tuile kilométrique, fluidifiera les opérations d'indexation interne.

Par ailleurs, l'entreprise doit conserver une agilité de traitement face aux délais inhérents à l'ingénierie publique. La disponibilité des dalles matricielles pouvant être retardée par les opérations de contrôle qualité de l'IGN ou amputée par la présence de zones militaires restreintes, le développement d'une capacité interne de rasterisation des nuages de points classifiés (fichiers LAZ ou COPC) vers des formats MNS, MNT et MNH garantit une indépendance opérationnelle totale.

Finalement, la vigilance à l'égard de l'historique environnemental de l'acquisition est le garant de la rigueur scientifique des livrables. La documentation irréfutable attestant que de vastes portions du Maine-et-Loire ont été captées lors des crues hivernales, avec un point focal au 7 mars 2024, impose une grande circonspection. L'altération du MNT par l'élévation de la lame d'eau, et par corollaire la sous-estimation dramatique du MNH (hauteur des bâtiments et de la végétation) dans les plaines inondées de la Sarthe, du Loir ou de l'Authion, exigent la mise en place de processus de remédiation géospatiale. L'hybridation des modèles récents avec des données topographiques de période sèche s'imposera comme le standard de qualité pour toute analyse hydraulique, assurantielle ou d'urbanisme dans ces secteurs vulnérables.
