# Pipeline Produit 2 — Terrasses ensoleillées / potentiel pergola

> **Phase 2. Ne pas commencer avant que le produit Piscines soit validé et vendu au moins une fois** (voir ROADMAP). Ce document fixe l'architecture décidée après recherche ; l'exécution est à la charge des sessions suivantes.

## Décision d'architecture : PAS de Google Solar API

Question posée au départ : « Google Solar API ? » → **Non. Recherche faite (juillet 2026), verdict sans ambiguïté :**

1. **CGU incompatibles avec le business** (Google Maps Platform Service Specific Terms, section Solar) :
   - stockage des données limité à **30 jours consécutifs** puis suppression obligatoire → impossible de constituer une base ;
   - **revente / redistribution / œuvres dérivées interdites** → on ne peut pas vendre les scores dérivés ;
   - usage autorisé restreint au dimensionnement/marketing de **systèmes à énergie solaire** pour une adresse donnée, avec opt-in de l'occupant pour le marketing — une pergola n'est pas un système solaire.
2. **Couverture incertaine en rural** : qualité MEDIUM dans les bourgs, BASE ou rien dans les hameaux du 49.
3. **Coût récurrent** : ~2 000–10 000 $ le balayage du département, à re-payer (cache 30 jours), pour ~100 k bâtiments.

**Alternative retenue : 100 % open data IGN, Licence Ouverte 2.0 (stockage et revente de produits dérivés explicitement autorisés) :**

| Donnée | Produit IGN | Résolution | Usage |
|---|---|---|---|
| Relief + sursol (arbres, bâtiments) | **LiDAR HD** — MNS/MNT/MNH dérivés prêts à l'emploi (GeoTIFF 0,5 m, dalles 1 km, via cartes.gouv.fr ; le 49 est déjà couvert) | 0,5 m | Calcul d'ombrage/ensoleillement |
| Photo aérienne | **BD ORTHO** (RVB + IRC) | 20 cm | Détection des terrasses minérales (option) |
| Emprises bâtiments | **BD TOPO** | — | Délimiter maison vs jardin |
| Parcelles | **Cadastre Etalab** | — | Unité "jardin" = parcelle − bâti |
| Adresses | **BAN** | — | Adresse livrable |

## Architecture du calcul

Principe : pour chaque parcelle de maison individuelle, calculer les **heures de soleil direct** sur la zone "jardin proche de la maison", à trois dates (21 juin, équinoxe, 21 décembre), à partir du MNS (qui contient arbres et bâtiments, donc les ombres portées réelles).

1. **Cibler avant de calculer** (le département fait ~7 100 dalles LiDAR d'1 km² — ne JAMAIS tout traiter) : partir de la base d'adresses de maisons individuelles (déjà construite par le pipeline Piscines : parcelles + bâti + BAN), et ne télécharger que les dalles MNS intersectant ces parcelles, par lots de communes.
2. **Zone d'intérêt par parcelle** : parcelle − emprise bâtiment − tampon 1 m le long des limites ; ne garder que la partie à moins de ~15 m de la façade (une pergola se vend adossée ou proche de la maison). Orientation de la zone par rapport au bâtiment (sud/sud-ouest = bonus).
3. **Ensoleillement** : ~~GRASS GIS `r.sun`~~ → **décision révisée 2026-07-08 : moteur natif `pipeline/src/solaire.py`** (position solaire astronomique + projection d'ombres vectorisée numpy sur le MNS, heures de soleil direct aux trois dates via `score_trois_dates`). Justification consignée dans l'en-tête du module : le besoin est un classement en heures de soleil direct (pas des kWh), GRASS est une dépendance système lourde et non testable unitairement, le moteur natif est couvert par 12 tests physiques (`pipeline/tests/test_solaire.py` : hauteur du soleil à midi par saison, longueur d'ombre = h/tan(alt), direction d'ombre, durée du jour été/hiver à 47,5°N). `r.sun` reste l'option si l'irradiance kWh devient un argument de vente.
4. **Score par adresse** : moyenne des heures de soleil sur les pixels de la zone d'intérêt, pondérée été/mi-saison. Classes : `plein-soleil` (> 7 h au 21 juin ET > 4 h à l'équinoxe sur ≥ 20 m² contigus), `bon`, `ombragé` (exclu de la vente). Seuils à calibrer sur le terrain (voir validation).
5. **(Option, phase 2b)** Détection de terrasse minérale existante sur BD ORTHO 20 cm (segmentation NDVI simple avec la bande IR : minéral non végétalisé adjacent à la maison). Attribut `terrasse_detectee` = argument de vente supplémentaire, pas un prérequis.

## Pourquoi c'est vendable (et vérifiable en RDV)

La preuve en RDV est moins immédiate que pour les piscines (on ne "voit" pas les heures de soleil sur une photo). Protocole de preuve adapté :
- montrer l'orthophoto de 5 adresses : terrain dégagé au sud, pas d'arbres — cohérent avec le score ;
- montrer la carte d'ombres calculée superposée à l'orthophoto (visuellement parlant : les ombres calculées correspondent aux ombres visibles sur la photo — c'est le "wahou" du RDV) ;
- vendre le score comme un **pré-filtre statistique** : « au lieu de distribuer 10 000 flyers, ciblez les 1 500 maisons où une pergola a un sens ».

## Étapes d'exécution (pour la session LLM qui prendra ce chantier)

1. Vérifier la disponibilité des dalles **MNS LiDAR HD** dérivées pour le 49 sur cartes.gouv.fr (téléchargement IGNF_MNS-LIDAR-HD). Si des dalles manquent : rasteriser soi-même le nuage de points LAZ (PDAL, `pdal pipeline` writers.gdal, 0,5 m) — prévoir le stockage (plusieurs centaines de Go pour le département brut ; d'où le ciblage par communes).
2. Prototyper sur **une commune** (suggestion : une commune péri-urbaine d'Angers, mix maisons récentes/anciennes) : téléchargement dalles, r.sun aux 3 dates, scores, carte de contrôle.
3. Calibration terrain : 20 adresses scorées `plein-soleil` vérifiées sur orthophoto + Street-level si dispo légalement (pas de scraping Google — se contenter de l'orthophoto IGN).
4. Validation qualité selon `06-QUALITE-VALIDATION.md` (précision ≥ 90 % acceptable pour ce produit — c'est un score, pas un fait binaire ; l'annoncer comme tel au client).
5. Industrialiser sur le département par lots de communes ; sortie `data/final/terrasses_qualifiees_49.parquet` avec les mêmes colonnes contractuelles que Piscines + `score_soleil`, `heures_soleil_juin`, `orientation`, pour réutiliser tel quel `40_export_client.py` (`--produit terrasses`).

## Pièges connus (ne pas les redécouvrir)

- **Millésime LiDAR vs réalité** : le LiDAR du 49 date de ~2021-2023 ; les arbres poussent, des maisons neuves apparaissent. Croiser avec le millésime BD TOPO le plus récent ; signaler le millésime dans l'export.
- **r.sun et la latitude/turbidité** : utiliser les coefficients de turbidité Linke par défaut mensuel (~3 en Anjou) ; ce qui compte est le *classement relatif* des parcelles, pas la valeur absolue en kWh.
- **CRS** : MNS IGN en Lambert-93 — rester en 2154 de bout en bout.
- **Ne pas vendre "heures de soleil garanties"** : vendre un score comparatif. Le contrat/README de livraison le formule ainsi.
