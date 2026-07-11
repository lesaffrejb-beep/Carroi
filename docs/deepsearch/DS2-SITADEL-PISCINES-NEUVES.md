# DS2 — SITADEL & données d'urbanisme : piscines neuves (prompt ③)

> Collé le 2026-07-11 (Gemini 3.5 Pro). Voir doctrine de lecture dans [README.md](README.md).

## Ce qu'on en retient (analyse 2026-07-11)

**Le produit « fraîcheur » (veille SITADEL) est FAISABLE — c'était la question qui
conditionnait la grille tarifaire 39-59 €/mois de `16`. Recette technique retenue :**
- Filtres : `ANN_COD_ANNEXE = 1` (annexe piscine) × maître d'ouvrage particulier
  (`CAT_COD_CATMO_LOGT/LOC ∈ {10, 11}`) × **nature de décision = OCTROI** (le sweet spot :
  projet validé, chantier pas commencé). JAMAIS baser la veille sur DOC/DAACT
  (sous-déclaration massive : ~15 % des DOC et 30-50 % des DAACT jamais remontées).
- Adresse : anonymisée dans les fichiers ouverts (pas d'adresse en clair — bon pour nous
  côté RGPD), mais **parcelles cadastrales présentes** → jointure parcelle → PCI Vecteur →
  BAN = exactement notre chaîne 20_join existante. Taux de localisation annoncé 95-97 %.
- Licence Ouverte Etalab → revente dérivée OK avec mention « Contient des données SITADEL
  (SDES) — Licence Ouverte ».
- Publication mensuelle (~fin du mois suivant). Transition **SITADEL 3 depuis mars 2026**
  (3 → 15 parcelles/dossier, meilleure couverture des DP sans surface de plancher — le
  biais historique « piscine sans surface de plancher = invisible » se résorbe) :
  instabilité de schéma à prévoir, coder défensivement.
- ⚠ Tout est à vérifier sur les fichiers réels (noms de colonnes exacts, modalités) au
  moment d'écrire le script — codes de variables plausibles mais non audités.
- Le conseil « externaliser à PermisAPI » est REJETÉ (dépendance + coût récurrent contre
  notre doctrine coûts fixes `16` ; volume départemental faible = ingestion maison viable).
  À garder en plan B si SITADEL 3 s'avère ingérable.

**Découverte bonus — PCI Édigéo `SYM=65` (piscines dessinées au cadastre) :**
- Le cadastre brut (couche `tsurf`, symbole 65) contient les piscines *déclarées et levées*,
  géométrie parfaite, Licence Ouverte. Incomplet (jusqu'à ~40 % manquantes — cohérent avec
  notre constat `02` « non fiable comme source principale ») mais idéal comme **couche de
  corroboration** au sens de la doctrine `16` (corrobore le score, ne crée jamais de ligne)
  et pour muscler le mode `--demo` (détection + SYM=65 = confiance maximale).
- À tester sur la commune pilote en phase A (extraction + taux de recouvrement avec OSM
  puis avec la détection).

**Confirmations (pas de changement) :** Fichiers fonciers CEREMA inaccessibles légalement
pour du commercial ; BDNB open tronquée sur ces attributs ; DVF aveugle aux piscines ;
BD TOPO ne couvre que les bassins publics ≥ 25 m. Tout était déjà dans `02`.

---

## Texte brut du deepsearch

Stratégie d'Exploitation des Données Foncières et d'Urbanisme pour la Détection de Piscines Privées

L'élaboration d'une base de données qualifiée recensant les adresses postales équipées de piscines privées constitue un actif stratégique de très haute valeur pour le marché interentreprises (B2B) des professionnels de l'aménagement extérieur. Le modèle économique envisagé repose fondamentalement sur la monétisation d'une asymétrie d'information. La détection initiale, fondée sur l'analyse d'imagerie aérienne à très haute résolution, permet de constituer le socle du produit, tandis que la veille réglementaire alimente un produit dérivé à forte récurrence, qualifié d'abonnement « Fraîcheur ». L'objectif est d'identifier les propriétaires ayant récemment obtenu une autorisation d'urbanisme, déclenchant ainsi des besoins immédiats en matière d'équipements, de sécurité et d'aménagement paysager.

Ce rapport exhaustif analyse la viabilité technique, les limites structurelles et le cadre légal entourant l'intégration de la base nationale des autorisations d'urbanisme (SITADEL) et de ses alternatives en données ouvertes (open data). L'analyse se concentre sur les enjeux cruciaux d'identification des piscines neuves, de granularité des adresses postales, de délais de publication des données publiques, et de fiabilité des sources secondaires telles que les Fichiers Fonciers du CEREMA ou le Plan Cadastral Informatisé. Le territoire du Maine-et-Loire (département 49) servira de prisme analytique pour évaluer la réplicabilité de ce modèle d'affaires.

Analyse Structurelle de la Base SITADEL pour la Détection de Piscines

Le Système d'Information et de Traitement Automatisé des Données Élémentaires sur les Logements et les locaux (SITADEL) représente le référentiel national centralisant les informations relatives aux demandes d'autorisations d'urbanisme. Gérée par le Service des Données et Études Statistiques (SDES) du Ministère de la Transition Écologique, cette base est alimentée par les centres instructeurs locaux, principalement les communes et les Établissements Publics de Coopération Intercommunale (EPCI).

Mécanismes de Déclaration et Typologie des Variables

L'identification précise des piscines privées au sein des fichiers bruts de la base SITADEL est techniquement réalisable, bien qu'elle exige une compréhension fine de la codification administrative. Les données statistiques agrégées et publiées par le SDES proviennent directement de la dématérialisation ou de la saisie manuelle des formulaires Cerfa réglementaires. Le cadre légal de l'urbanisme stipule qu'une piscine non couverte de plein air dont la surface de bassin est comprise entre dix et cent mètres carrés nécessite le dépôt d'une déclaration préalable de travaux (Cerfa 13404), tandis qu'un bassin excédant cent mètres carrés ou pourvu d'une couverture fixe ou mobile dont la hauteur dépasse un mètre quatre-vingts requiert un permis de construire (Cerfa 13406).

Le dictionnaire des variables de SITADEL démontre que ces aménagements font l'objet d'un suivi analytique spécifique. La variable déterminante se nomme ANN_COD_ANNEXE, qui correspond au code du type d'annexe rattaché au projet d'urbanisme. La nomenclature de cette variable attribue expressément la modalité « 1 » à la catégorie « Piscine ». Cette granularité descriptive est particulièrement intéressante pour la stratégie globale de l'entreprise, puisque d'autres modalités de cette même variable couvrent des segments de marché connexes. Par exemple, la modalité « 2 » identifie les garages, la modalité « 3 » cible les vérandas, et la modalité « 4 » recense les abris de jardin. Cette structure offre des perspectives d'expansion évidentes pour le produit de phase deux axé sur les terrasses et pergolas.

Toutefois, la seule présence d'une annexe de type piscine ne suffit pas à qualifier un prospect pour un modèle économique orienté vers le commerce de détail (B2B to C). Il est impératif d'isoler les bassins à vocation purement privée et individuelle, en excluant les projets portés par des collectivités territoriales, des complexes hôteliers ou des bailleurs sociaux. Pour opérer cette segmentation, il convient d'appliquer un filtre croisé sur la catégorie du maître d'ouvrage. Les variables CAT_COD_CATMO_LOGT (pour les projets liés au logement) ou CAT_COD_CATMO_LOC (pour les projets liés aux locaux) permettent cette distinction. La sélection exclusive des modalités « 10 », correspondant aux particuliers sans autre indication, ou « 11 », désignant les particuliers purs, garantit que la donnée extraite correspond au profil d'un client final résidentiel classique.

Le Biais Conceptuel de la Surface de Plancher

L'exploitation historique de la base SITADEL a longtemps été complexifiée par des choix d'architecture de données orientés vers la macroéconomie de la construction plutôt que vers l'analyse micro-locale. Sur la plateforme gouvernementale de données ouvertes, les fichiers étaient traditionnellement scindés en deux flux distincts : les listes d'autorisations créant des logements et celles créant des locaux non résidentiels. Cette segmentation posait un problème structurel majeur pour le repérage exhaustif des piscines.

En droit de l'urbanisme, un bassin de piscine de plein air ne constitue pas une surface de plancher, ni une surface hors œuvre nette (SHON) selon les anciennes nomenclatures. Par conséquent, de nombreuses déclarations préalables portant exclusivement sur la construction d'une piscine chez un particulier ne généraient aucune surface de plancher supplémentaire. Ces dossiers d'extension ou d'aménagement sans création de logement se retrouvaient souvent exclus des jeux de données principaux publiés en ligne ou dilués dans des fichiers annexes mal documentés.

Ce biais historique connaît néanmoins une résolution progressive. Le déploiement de l'architecture SITADEL 3, dont la mise en production s'intensifie à partir de mars 2026, marque une évolution favorable. Cette refonte du système d'information modifie la remontée des surfaces et le classement des destinations, intégrant de manière plus systématique les indicateurs d'extension, même sans création de surface de plancher. Des acteurs technologiques spécialisés dans le traitement de ces bases confirment que les autorisations d'urbanisme ne créant pas de logements, incluant les annexes spécifiques comme les piscines, sont désormais identifiables de manière plus robuste si l'on consolide l'ensemble des fichiers bruts fournis par le SDES. Le croisement systématique de l'indicateur d'extension avec le code d'annexe permet aujourd'hui d'atteindre une quasi-exhaustivité sur le flux des nouvelles déclarations.

| Variable SITADEL | Description Métier | Modalité Cible pour le Produit | Justification Stratégique |
|---|---|---|---|
| ANN_COD_ANNEXE | Code déterminant la nature de l'annexe au bâtiment. | 1 (Piscine) | Isolation directe de l'objet de la prospection commerciale. |
| CAT_COD_CATMO_LOGT | Catégorie du maître d'ouvrage (demandeur) pour le logement. | 10 ou 11 (Particuliers) | Exclusion stricte des projets professionnels, hôteliers ou publics. |
| NATDEC | Nature de la décision administrative rendue par l'autorité. | Octroi (Autorisation) | Garantie que le projet est validé et prêt à entrer en phase de consultation d'artisans. |
| TCO_COD_TYPCONSTR | Type de la construction visée par la demande. | 5 (Maison individuelle pure) | Maximisation de la probabilité de vente de services d'aménagement paysager ou de sécurité. |

Ingénierie Géospatiale et Granularité de l'Adresse Postale

Le modèle économique défini requiert une précision géographique absolue. Un piscinier ne peut exploiter une information se limitant à l'échelle communale ; son démarchage, qu'il soit physique ou postal, exige une adresse normalisée et géolocalisée. La base SITADEL présente des défis considérables à cet égard, nécessitant la mise en place d'un pipeline de géotraitement sophistiqué.

Les Contraintes de l'Anonymisation et du RGPD

Les données brutes de SITADEL diffusées en données ouvertes font l'objet d'un processus strict d'anonymisation préalable. Conformément aux doctrines de la Commission Nationale de l'Informatique et des Libertés (CNIL) et au Règlement Général sur la Protection des Données (RGPD), le SDES supprime systématiquement l'adresse postale en clair du terrain des travaux, ainsi que l'identité, les coordonnées téléphoniques et l'adresse électronique du pétitionnaire.

Cette absence de données nominatives est fondamentalement un atout pour le positionnement juridique du produit. En s'abstenant de traiter, de stocker ou de revendre des données personnelles, l'entreprise se prémunit contre les risques majeurs de non-conformité. Le produit B2B commercialisé demeure une base de données purement foncière et technique, laissant la responsabilité du démarchage conforme à la charge de l'artisan client, qui agira en tant que responsable de traitement de ses propres campagnes de prospection.

Le Rôle Central de l'Identifiant de Parcelle Cadastrale

Pour pallier l'absence de l'adresse postale explicite, la localisation des événements d'urbanisme s'appuie sur le maillage cadastral. Lors de la constitution de son dossier en mairie, le pétitionnaire doit obligatoirement renseigner la ou les parcelles cadastrales constituant l'assiette foncière de son projet. Ces références sont scrupuleusement enregistrées dans l'application SITADEL.

Dans l'ancienne architecture SITADEL 2, le système limitait la saisie à un maximum de trois parcelles par dossier de demande, ce qui entraînait des pertes de précision pour les projets vastes chevauchant de multiples divisions foncières. Avec la refonte vers SITADEL 3, cette capacité a été significativement étendue, permettant l'enregistrement de quinze parcelles distinctes. L'information parcellaire est décomposée en plusieurs colonnes dans les fichiers tabulaires bruts, incluant généralement le code de la commune, le préfixe de la section, la lettre de la section cadastrale et le numéro de la parcelle.

L'ingénierie de la donnée impose de développer un algorithme de concaténation pour reconstituer l'identifiant unique de parcelle, souvent standardisé sur quatorze caractères. Cet identifiant constitue la clé de voûte de toute l'architecture relationnelle permettant de passer de la sphère administrative à la réalité topographique du Maine-et-Loire.

Protocole de Résolution Spatiale et Jointure avec la Base Adresse Nationale

La transformation de l'identifiant parcellaire en une adresse exploitable commercialement nécessite un géotraitement itératif croisant plusieurs référentiels nationaux de données ouvertes. Ce pipeline garantit le taux de fiabilité exigé lors des rendez-vous de démonstration.

La première étape consiste à apparier l'identifiant parcellaire reconstitué avec le Plan Cadastral Informatisé (PCI) Vecteur. Diffusé par Etalab, le PCI Vecteur fournit les représentations géométriques, sous forme de polygones, de l'ensemble du découpage foncier français. La jointure tabulaire entre SITADEL et le PCI Vecteur permet de matérialiser spatialement le permis de construire. Des retours d'expérience sur des traitements similaires à l'échelle départementale démontrent que ce croisement permet de localiser avec succès entre 95 pour cent et 97 pour cent des autorisations. Les échecs de jointure, marginaux mais existants, s'expliquent par des erreurs de saisie lors de l'instruction du dossier, par des remembrements fonciers ayant entraîné la disparition du numéro de parcelle historique, ou par l'existence de secteurs non encore intégralement numérisés de manière vectorielle.

Une fois le polygone cadastral du projet isolé, la seconde étape opère une jointure spatiale avec la Base Adresse Nationale (BAN). Ce processus géomatique utilise des fonctions d'intersection spatiale pour associer le centre de gravité de la parcelle au point d'adresse le plus pertinent. Dans un territoire semi-rural comme le Maine-et-Loire, une attention particulière doit être portée aux lieux-dits, qui ne disposent pas toujours d'une numérotation métrique normalisée. L'algorithme doit évaluer la distance entre le point d'adresse de la BAN et le polygone cadastral, tout en vérifiant la concordance du code INSEE, afin d'attribuer un score de confiance à la localisation. Seules les adresses atteignant un niveau de précision optimal seront intégrées au mode démonstration de l'application, sécurisant ainsi l'effet de preuve indispensable à la conversion du prospect en client.

Cadre Juridique, Licence d'Exploitation et Dynamique Temporelle

La commercialisation d'une veille sur les nouvelles constructions de piscines, tarifée sous forme d'abonnement, repose sur deux piliers : la légalité inattaquable de la revente des données sources et l'exploitation millimétrée du délai administratif pour frapper le marché avant la concurrence.

Compatibilité de la Licence Ouverte avec le Modèle Économique

L'appropriation et la monétisation de données issues du service public soulèvent légitimement la question des droits de réutilisation. Les jeux de données SITADEL, à l'instar de la majorité des référentiels produits par le Ministère de la Transition Écologique et diffusés sur la plateforme gouvernementale, sont placés sous le régime de la Licence Ouverte, également connue sous le nom d'Open Licence, conçue par la mission Etalab.

Cette licence a été spécifiquement rédigée pour encourager l'économie de la donnée et l'innovation numérique. Elle est extrêmement permissive et accorde à tout réutilisateur un droit mondial, perpétuel et gratuit d'exploiter l'information. Crucialement pour le modèle d'affaires de la base « Piscines », la Licence Ouverte autorise expressément la réutilisation à des fins commerciales, la création de produits dérivés et l'intégration de la donnée dans des services payants soumis à exclusivité territoriale.

La seule contrepartie exigée par ce cadre contractuel est le respect du droit d'attribution. Le fournisseur de la base qualifiée doit obligatoirement mentionner la paternité de la source originelle. Dans la pratique, il suffit d'insérer dans les conditions générales de vente, les contrats d'exclusivité, ou en bas de page des extraits de fichiers livrés aux pisciniers, une mention explicite telle que : « Contient des données SITADEL produites par le SDES, diffusées sous Licence Ouverte » ou « Source SDES base Sitadel data.gouv.fr ». Cette transparence totale envers les clients consolide par ailleurs l'image de sérieux et de conformité de l'entreprise.

La Chronologie Administrative : Distinguer le Dépôt, l'Autorisation et l'Achèvement

La proposition de valeur de l'abonnement « Fraîcheur » repose sur la temporalité. Pour justifier un prix premium, la donnée doit révéler une intention d'achat certaine, mais non encore concrétisée par le commencement des travaux. La maîtrise du cycle de vie du permis de construire dans SITADEL est donc vitale.

Les centres instructeurs transmettent les mouvements relatifs à la vie des dossiers au pôle inter-régional des statistiques, qui remonte ensuite l'information au SDES. La publication de ces données consolidées est mensuelle, intervenant généralement vers la fin du mois suivant les événements. Cependant, une analyse approfondie des variables temporelles révèle l'existence d'un décalage intrinsèque entre la réalité du terrain et la statistique.

SITADEL consigne plusieurs jalons temporels, dont les plus importants sont la date réelle de dépôt de la demande (DR_DEPOT) et la date de prise en compte (DPC_PREM). Le système qualifie également la nature du mouvement : dépôt initial, décision de l'autorité, déclaration d'ouverture de chantier (DOC) et déclaration attestant l'achèvement et la conformité des travaux (DAACT).

| Jalon SITADEL | Signification Opérationnelle | Pertinence Stratégique pour le Produit |
|---|---|---|
| DEPOT | Le particulier soumet son dossier à la mairie. | Très faible. L'issue est incertaine (risque de refus administratif). |
| DECISION (Octroi) | L'autorisation d'urbanisme est officiellement accordée. | Maximale (Le "Sweet Spot"). Le projet est légalement validé, les devis finaux vont être signés, les travaux n'ont pas débuté. |
| SUIVI (DOC) | Le chantier de la piscine démarre physiquement. | Faible. À ce stade, le particulier a déjà contractualisé avec un piscinier concurrent ou un terrassier. |
| ACHEVEMENT (DAACT) | La piscine est terminée et conforme. | Nulle pour la construction. Potentielle pour la vente ultérieure de contrats d'hivernage ou de sécurité. |

Il est formellement proscrit de conditionner la détection des nouvelles piscines aux déclarations de mise en chantier ou d'achèvement. Les statistiques du Ministère démontrent une sous-déclaration massive de ces étapes finales par les particuliers. Près de quinze pour cent des ouvertures de chantier et trente pour cent, voire cinquante pour cent selon certaines sources, des achèvements de travaux ne font jamais l'objet d'une remontée administrative vers SITADEL. Fonder un modèle de détection sur la DAACT reviendrait à amputer la base d'un tiers de son potentiel commercial et à livrer des pistes de prospection obsolètes. Le ciblage exclusif des décisions d'autorisation d'octroi garantit l'efficacité redoutable de la veille.

Évaluation des Alternatives en Données Ouvertes pour la Détection Finesse

Si SITADEL permet de capter le flux des nouvelles intentions, l'établissement du socle initial de données (les dizaines de milliers de piscines existantes dans le Maine-et-Loire) nécessite le croisement avec d'autres référentiels. La détection par intelligence artificielle sur imagerie aérienne représente l'axe technologique principal, mais sa consolidation par des données foncières ouvertes renforce drastiquement la fiabilité du produit. L'écosystème de la donnée publique offre plusieurs candidats, dont les mérites et les limites légales doivent être strictement pesés.

L'Impasse Juridique des Fichiers Fonciers (CEREMA)

Les Fichiers Fonciers, élaborés par le CEREMA à partir de la matrice cadastrale numérisée (MAJIC) de la Direction Générale des Finances Publiques, représentent théoriquement le graal absolu de la connaissance du bâti français. Cette base d'origine fiscale décrit chaque local, chaque parcelle et chaque propriétaire avec une exhaustivité sans pareille.

Sur le plan de l'architecture des données, l'identification des piscines y est d'une clarté absolue. Les Fichiers Fonciers structurent les dépendances isolées du bâti principal dans une table dédiée, nommée pb60_pevdependance. Au sein de cette table, la variable cconad, qui explicite la nature des dépendances ne communiquant pas par l'intérieur avec l'habitation, dispose d'une modalité spécifique et exclusive nommée « Piscine ». Mieux encore, la table principale décrivant le local propose une variable agrégée, nbpiscine, qui comptabilise le nombre exact de bassins rattachés à une propriété.

Cependant, l'intégration de cette ressource dans un produit B2B privé se heurte à une barrière légale infranchissable. Contrairement aux données SITADEL, les Fichiers Fonciers natifs ne sont pas soumis à la Licence Ouverte. En raison du secret fiscal et de la sensibilité des données patrimoniales, leur distribution est rigoureusement restreinte à un cercle fermé d'ayants droit publics. Seuls les services déconcentrés de l'État, les collectivités territoriales, les agences d'urbanisme, les établissements publics fonciers et certains chercheurs spécifiquement accrédités peuvent prétendre à leur obtention. Toute demande nécessite la signature d'un acte d'engagement formel prohibant l'exploitation commerciale et circonscrivant l'usage à la mise en œuvre de politiques publiques d'aménagement du territoire. En tant qu'entreprise privée visant la commercialisation de listes de prospection, l'accès légal à ces données est impossible, ce qui disqualifie définitivement le CEREMA comme source d'approvisionnement direct.

Le Mirage de la BDNB et de la Base DVF

La Base de Données Nationale des Bâtiments (BDNB), produite par le Centre Scientifique et Technique du Bâtiment (CSTB), fusionne de multiples référentiels, dont les Fichiers Fonciers. Bien que le CSTB diffuse une version ouverte de la BDNB (BDNB Open), l'analyse approfondie de son dictionnaire de données révèle que les attributs précis issus de la fiscalité, tels que le détail exhaustif de la variable cconad ou le décompte exact nbpiscine, sont systématiquement masqués, tronqués ou réservés à la version restreinte destinée aux ayants droit publics. L'ouverture de la BDNB se concentre davantage sur les indicateurs de performance énergétique ou morphologique, rendant son exploitation pour le ciblage spécifique des piscines privées inopérante en accès libre.

La base des Demandes de Valeurs Foncières (DVF+), qui recense l'intégralité des transactions immobilières à titre onéreux, présente également des limites rédhibitoires pour l'objectif visé. Premièrement, elle est par nature aveugle aux constructions neuves réalisées par des propriétaires conservant leur bien foncier. Une piscine ajoutée à une maison existante n'y laissera aucune trace documentaire. Deuxièmement, bien que la base détaille la surface du bâti principal, le nombre de pièces et la nature du bien, l'existence d'une piscine ou d'aménagements extérieurs spécifiques n'est pas codifiée dans les variables transmises lors de la mutation. DVF+ ne présente donc aucun intérêt pour la veille ou la constitution du stock de piscines.

La Base TOPO de l'IGN : Une Échelle Inadaptée au Résidentiel

L'Institut National de l'Information Géographique et Forestière (IGN) met à disposition la BD TOPO, une modélisation vectorielle tridimensionnelle des infrastructures du territoire. En explorant les spécifications techniques de cette base, on constate l'existence d'une classe d'objets dénommée « Zone d'activité ou d'intérêt », qui comporte effectivement une nomenclature incluant les piscines.

Néanmoins, les règles de saisie dictées par l'IGN excluent catégoriquement le marché résidentiel privé. La définition officielle stipule que seules les piscines ouvertes au public, dotées d'un grand bassin de natation d'une longueur minimale de vingt-cinq mètres, doivent être numérisées. Les spécifications précisent de manière univoque que même les piscines des centres de vacances ou des établissements hôteliers sont exclues de cette catégorisation. La BD TOPO ne recense donc aucune piscine individuelle, la rendant de fait obsolète pour la détection de ciblages B2B dans le secteur de l'habitat individuel.

Le Cadastre Vectoriel (EDIGEO) : L'Arme Stratégique Insoupçonnée

L'exploration des méandres techniques des données ouvertes permet d'identifier une ressource magistrale et souvent sous-exploitée : le Plan Cadastral Informatisé (PCI) Vecteur, dans sa structuration native brute.

Diffusé sous Licence Ouverte par Etalab, le PCI Vecteur ne se contente pas de dessiner les limites de propriété. Dans ses formats d'exportation originels (notamment le format standard EDIGEO ou ses transcriptions en GeoJSON, comme la couche tsurf), le cadastre incorpore une nomenclature symbolique précise utilisée par les géomètres du service du cadastre pour qualifier certaines emprises surfaciques. La documentation technique de ces données topologiques révèle que la variable SYM (pour Symbole) prend la valeur spécifique 65 (ou SYM=65) pour désigner officiellement la géométrie d'une piscine.

Cette découverte est fondamentale pour l'économie du projet. L'exploitation de ce champ spécifique présente des avantages considérables, surclassant largement les autres alternatives documentaires :
Exactitude Géométrique et Topologique : Le polygone de la piscine (SYM=65) est nativement intégré dans le système de coordonnées du cadastre et imbriqué dans la parcelle mère. Le problème de la jointure spatiale pour rattacher le bassin à une adresse est résolu d'emblée, garantissant un géocodage d'une perfection absolue.
Accessibilité Juridique : Contrairement aux Fichiers Fonciers du CEREMA, le PCI Vecteur d'Etalab est totalement ouvert à la réutilisation commerciale.
Actualisation Fiscale : Toute piscine déclarée légalement aux services des impôts, et ayant fait l'objet d'un levé ou d'une mise à jour de la planche cadastrale, se retrouve automatiquement caractérisée par ce symbole surfacique.

L'extraction systématique des entités SYM=65 du cadastre vectoriel du Maine-et-Loire permet de constituer quasi instantanément une liste massive de dizaines de milliers d'adresses équipées. L'effort d'ingénierie se réduit à une simple requête spatiale sur des bases de données de type PostGIS, ce qui est infiniment moins coûteux et complexe que l'entraînement d'algorithmes d'intelligence artificielle sur des téraoctets d'orthophotographies.

Cependant, il convient de nuancer l'exhaustivité de cette source. Le cadastre ne modélise que la réalité légalement déclarée et topographiquement mise à jour. L'inertie administrative et l'ampleur des fraudes ou omissions de déclaration génèrent des écarts substantiels. Des analyses comparatives locales démontrent que, dans certains territoires ruraux ou périurbains typiques du Maine-et-Loire, le différentiel entre les piscines visibles par satellite et celles officiellement recensées dans le cadastre peut atteindre jusqu'à quarante pour cent. Le PCI Vecteur ne peut donc pas, à lui seul, constituer l'intégralité du produit. Il doit être considéré comme une couche de vérification et de consolidation massive, venant appuyer et compléter la détection par analyse d'image, assurant ainsi une base de données d'une complétude inégalée sur le marché.

Recommandations pour l'Architecture Technique et le Déploiement

À la lumière de cette investigation exhaustive des sources de données urbaines, l'architecture opérationnelle visant à propulser les bases « Piscines » et l'abonnement « Fraîcheur » doit s'articuler autour d'une hybridation pragmatique des technologies, alliant la puissance de la télédétection aux certitudes de l'open data administratif.

Synthèse Technologique pour le Produit Initial (Le Stock)

La promesse commerciale faite aux pisciniers repose sur l'exhaustivité et la précision. Pour recenser l'ensemble du parc existant dans le département pilote du Maine-et-Loire, le moteur de production doit fusionner deux flux distincts.

D'une part, le balayage systématique de l'orthophotographie à vingt centimètres de résolution de l'IGN par un réseau de neurones convolutifs (segmentation sémantique) permet de repérer l'intégralité des bassins, y compris les piscines hors-sol ou les installations non déclarées, compensant ainsi les angles morts de la fiscalité. D'autre part, l'ingestion de la couche surfacique du PCI Vecteur filtrée sur l'attribut SYM=65 permet d'identifier formellement les bassins légaux avec une géométrie incontestable.

L'algorithme de fusion de données opérera une intersection spatiale entre les détections de l'intelligence artificielle et les polygones cadastraux. Une détection visuelle superposée à une entité SYM=65 recevra un score de confiance de l'ordre de quatre-vingt-dix-neuf pour cent. Cette donnée ultra-qualifiée constituera le fer de lance de la force de vente. Le rattachement des parcelles aux points de la Base Adresse Nationale (BAN) clôturera le processus, garantissant que chaque ligne vendue comporte une adresse normalisée exploitable pour des campagnes de publipostage ou de démarchage physique.

Externalisation Stratégique pour l'Abonnement de Veille

Si la base initiale assure la trésorerie de lancement, l'abonnement mensuel de veille sur les nouvelles intentions de construction génère la récurrence financière et fidélise la clientèle. Le ciblage doit impérativement s'opérer sur la variable d'autorisation (DECISION d'octroi) de la base SITADEL pour devancer la concurrence artisanale.

Toutefois, le maintien d'un pipeline d'ingestion interne pour la base SITADEL représente un risque d'ingénierie important. L'instabilité actuelle liée à la transition vers SITADEL 3, les fréquentes restructurations de colonnes, et la complexité des redressements statistiques opérés par le SDES exigent une maintenance continue. Face au volume relativement restreint de nouvelles déclarations mensuelles à l'échelle d'un seul département, le coût de développement en interne est disproportionné.

La recommandation stratégique consiste à recourir à une externalisation partielle via des agrégateurs de données spécialisés, tels que PermisAPI, qui absorbent la complexité du retraitement de SITADEL et fournissent directement l'information géocodée et qualifiée (surface, présence d'annexe piscine) via une interface de programmation (API) robuste. Pour un coût d'acquisition de données de l'ordre de quelques centimes par requête, l'entreprise sécurise son approvisionnement en leads de haute qualité, qu'elle peut immédiatement valoriser à fort prix auprès des installateurs détenteurs de l'exclusivité sectorielle.

Sécurisation du Protocole de Démonstration Commerciale

L'ultime maillon de la création de valeur réside dans la conviction du client lors du rendez-vous commercial. L'effet de surprise et la démonstration instantanée de la maîtrise territoriale sont les leviers de la conclusion de la vente.

Le cahier des charges impose de garantir un taux de précision supérieur à quatre-vingt-quinze pour cent lors de la phase de démonstration (mode --demo). Pour sanctuariser ce taux de conversion, le script d'extraction utilisé par le commercial en clientèle ne devra puiser que dans le sous-ensemble de la base bénéficiant de la double validation : un score de détection visuelle extrêmement élevé couplé à une inscription cadastrale confirmée (SYM=65). En cas de doute sur la qualité du rattachement avec la BAN, particulièrement fréquent dans les zones d'habitat dispersé (lieux-dits) caractéristiques de la ruralité angevine, l'enregistrement devra être exclu de l'échantillon de démonstration. L'ouverture aléatoire de cinq adresses sur le Géoportail de l'IGN devant le prospect validera irréfutablement la réalité du produit, pulvérisant les objections sur la fiabilité de la donnée.

En respectant scrupuleusement les contraintes de l'open data et en naviguant avec agilité entre les ressources topographiques de l'IGN, l'héritage cadastral d'Etalab et les flux administratifs du SDES, le projet s'assure une assise juridique inattaquable et une avance technologique décisive sur un marché local particulièrement dense et lucratif.
