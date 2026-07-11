# Sources de données — vérifiées (recherche juillet 2026)

> Chaque source ci-dessous a été vérifiée : contenu réel, format, URL de téléchargement, licence. Les sessions suivantes n'ont PAS à refaire cette recherche — seulement à vérifier que les URLs/millésimes sont à jour au moment du run.

## Fait établi n°1 : les piscines privées ne sont dans AUCUNE base ouverte toute faite

- **BD TOPO (IGN)** ne contient que les piscines **publiques** (couche `zone_d_activite_ou_d_interet` avec `nature='Piscine'`, bassins ≥ 25 m ouverts au public, et `terrain_de_sport` avec `nature='Bassin de natation'`). La couche `construction_surfacique` n'a pas de nature "piscine". Rendement attendu dans le 49 : quelques dizaines d'équipements publics — inutile pour notre produit, utile pour EXCLURE les bassins publics.
- **"Foncier innovant" (DGFiP)** : les ~120 000 piscines détectées par IA par le fisc sont des données fiscales, **non publiées**. Seule la méthode est publique. En revanche, son **entrée** (BD ORTHO) est ouverte → on peut répliquer la détection nous-mêmes, légalement.
- **Cadastre Etalab** : les couches retraitées (parcelles, bâtiments) ne contiennent pas les piscines. Le PCI brut (Edigéo) en contient parfois comme "détails topographiques", mais de façon incohérente selon les communes — non fiable comme source principale.

**Conséquence architecturale : le produit Piscines = détection maison sur orthophoto IGN + jointure adresse.** Détail dans `04-PIPELINE-PISCINES.md`.

## Sources utilisées

### BD ORTHO / ORTHO HR (IGN) — la matière première de la détection
- Orthophotos RVB + **IRC (infrarouge)** du département, résolution **20 cm**, rafraîchies ~tous les 3 ans.
- Licence **Ouverte Etalab 2.0** → détection dérivée librement commercialisable (mention de source obligatoire).
- **Détails opérationnels (deepsearch ①, 2026-07-11 — `docs/deepsearch/DS3-BD-ORTHO-49.md` ; à confirmer au run B1)** :
  - Archive départementale multi-volumes 7z :
    `https://data.geopf.fr/telechargement/download/BDORTHO/BDORTHO_1-0_{RVB|IRC}-0M20_JP2-E080_LAMB93_D049_{MILLESIME}-01-01/…​.7z.001` (`.002`… jusqu'au 404) ; miroir `files.opendatarchives.fr/professionnels.ign.fr/orthohr/` (vérifier D'ABORD si le miroir expose l'arborescence JP2 décompressée → téléchargement par dalle possible, sinon archive complète ~150-170 Go/spectre).
  - Format interne : **JP2 (JPEG2000, profil E080)**, dalles 1 km (5000×5000 px), nommées `ORTHO_{IRC|RVB}_0M20_JP2_E080_L93_XXXX_YYYY.jp2` (coin Sud-Ouest, km Lambert-93 ; 49 ≈ X 350-470, Y 6650-6770, ~8 000-8 500 dalles).
  - **Bandes IRC : 1 = proche IR, 2 = rouge, 3 = vert** — à confronter aux hypothèses de `detection.py` dès B1.
  - Extraction d'une commune sans tout décompresser : `7z x archive.7z.001 -ir!*XXXX_YYYY.jp2 -o…` (liste de dalles = intersection commune × tableau d'assemblage WFS).
  - Millésime 49 : **probablement 2025** (remplace 2022 ; publication charnière 2025/2026 — NON confirmé par la vérif web du 2026-07-11, B1 tranche et consigne). Prochain survol : **été 2028** (publication fin 2028/2029).
  - **Opportunité** : si 2025 confirmé, le diff **2022→2025** (`millesimes.py`) rend le segment « nouvelles piscines » disponible dès le lancement (archives 2022 : BD ORTHO historique / opendatarchives).
- L'IRC sert à éliminer les faux positifs végétation (une piscine n'a aucune signature végétale) et les bâches vertes.

### Cadastre Etalab (parcelles) — le pivot piscine → adresse
- GeoJSON par département : `https://cadastre.data.gouv.fr/data/etalab-cadastre/latest/geojson/departements/49/cadastre-49-parcelles.json.gz` (idem `cadastre-49-batiments.json.gz`). Millésimes datés, alias `latest`.
- Champ clé : `id` = identifiant parcellaire 14 caractères (INSEE 5 + préfixe 3 + section 2 + numéro 4).
- Licence Ouverte 2.0.
- **PCI brut Édigéo, couche `tsurf`, symbole `SYM=65` = piscines cadastrées** (deepsearch ③,
  `docs/deepsearch/DS2`) : les piscines *déclarées et levées* y figurent avec une géométrie
  parfaite, Licence Ouverte. INCOMPLET (jusqu'à ~40 % manquantes — confirme le « non fiable
  comme source principale » ci-dessus) mais excellente **couche de corroboration** au sens de
  la doctrine `16` (corrobore le score, ne crée jamais de ligne) et booster du mode `--demo`
  (détection + SYM=65 = confiance maximale). À tester sur la commune pilote en phase A.

### BAN (Base Adresse Nationale) — l'adresse livrable
- CSV par département : `https://adresse.data.gouv.fr/data/ban/adresses/latest/csv/adresses-49.csv.gz`.
- Champs utiles : `id` (→ notre `id_ban`), `numero`, `rep`, `nom_voie`, `code_postal`, `code_insee`, `nom_commune`, `x`, `y` (Lambert-93), `lon`, `lat`, `type_position`, `source_position`, `certification_commune`, et surtout **`cad_parcelles`** : liste (séparateur `|`) d'identifiants parcellaires 14 caractères rattachés à l'adresse. Couverture de `cad_parcelles` variable selon les communes → prévoir le fallback "adresse BAN la plus proche dans la parcelle / à < 50 m même commune".
- Complément si `cad_parcelles` trop lacunaire dans le 49 : dataset "Adresses extraites du cadastre" (data.gouv.fr), nativement indexé par parcelle.
- Licence Ouverte 2.0.

### BD TOPO (IGN) — bâtiments + exclusions
- GPKG par département : `https://data.geopf.fr/telechargement/download/BDTOPO/BDTOPO_3-5_TOUSTHEMES_GPKG_LAMB93_D049_{DATE}/....7z` (éditions trimestrielles le 15 mars/juin/sept/déc ; miroir : files.opendatarchives.fr/professionnels.ign.fr/bdtopo/). Couches utilisées : `batiment` (distance piscine↔habitation), `zone_d_activite_ou_d_interet` + `terrain_de_sport` (exclusion des bassins publics/collectifs).
- Licence Ouverte 2.0.

### LiDAR HD / MNS 0,5 m (IGN) — produit 2 uniquement
- Voir `05-PIPELINE-TERRASSES.md`. Le 49 est couvert (acquisition précoce Pays de la Loire). Dérivés MNS/MNT/MNH GeoTIFF 0,5 m sur cartes.gouv.fr. Licence Ouverte 2.0.
- **Accès direct (deepsearch ②, `docs/deepsearch/DS1`)** : racine `https://diffusion-lidarhd.ign.fr/mnx/` ; tableaux d'assemblage WFS `https://data.geopf.fr/wfs/ows`, couches `IGNF_MNS_LIDAR-HD:dalle` / `IGNF_MNH_LIDAR-HD:dalle` (BBOX → URL de chaque dalle). Float32, dalles 1 km, Lambert-93/IGN69.
- **⚠ Millésime 49 acquis en partie pendant la crue du 7 mars 2024** (plausible, à vérifier au 1er run P2) : MNT = surface de l'eau dans les lits majeurs (Sarthe/Loir/Basses Vallées Angevines/Authion) → **MNH sous-estimé** en zone inondable ; acquisition « leaf-off » → canopée d'été sous-estimée. ZICAD (Saumur…) = NoData définitif. Pièges détaillés dans `05` §Pièges.

### OpenStreetMap — usage INTERNE uniquement (⚠ licence)
- `leisure=swimming_pool` (souvent tracées depuis le cadastre) : couverture réelle mais très inégale selon les communes. Extraction : Geofabrik `pays-de-la-loire-latest.osm.pbf` + `osmium tags-filter w/leisure=swimming_pool`.
- **Licence ODbL, share-alike : toute base dérivée publiquement diffusée (= vendue) devrait être licenciée ODbL**, ce qui détruirait exclusivité et interdiction de revente. **Règle du projet : les géométries OSM n'entrent JAMAIS dans le produit vendu.** Usages autorisés : développement/débogage du pipeline de jointure, estimation du rappel, et éventuellement constitution de masques d'entraînement (voir le point licence dans `04-PIPELINE-PISCINES.md` — par prudence on privilégie l'annotation manuelle).

### SITADEL (SDES) — permis de construire : la fraîcheur entre deux millésimes ortho
- Base ouverte des autorisations d'urbanisme (mise à jour mensuelle, data.gouv.fr) : les
  déclarations préalables/permis « piscine » donnent les piscines NEUVES — le segment le plus
  chaud — sans attendre le prochain survol BD ORTHO (~3 ans). Identifiée par le pre-mortem
  (`10` §7) comme la parade à l'impossibilité d'un abonnement annuel sur la seule ortho.
- **Évaluation faite (deepsearch ③, 2026-07-11 — `docs/deepsearch/DS2`) : le produit
  « fraîcheur » est FAISABLE.** Recette (codes plausibles, à auditer sur les fichiers réels
  au moment d'écrire le script) :
  - Filtres : `ANN_COD_ANNEXE = 1` (piscine) × maître d'ouvrage particulier
    (`CAT_COD_CATMO_* ∈ {10,11}`) × **décision = OCTROI** (jamais DOC/DAACT : sous-déclarées
    à 15-50 %) ;
  - Adresse : anonymisée (bien pour nous) mais **parcelles cadastrales fournies** →
    parcelle → PCI → BAN = notre chaîne 20_join (taux de localisation annoncé 95-97 %) ;
  - Licence Ouverte (mention « Contient des données SITADEL (SDES) ») ; publication
    mensuelle ; **transition SITADEL 3 depuis mars 2026** (schéma instable, coder défensif ;
    3 → 15 parcelles/dossier, meilleure couverture des DP sans surface de plancher) ;
  - Externalisation type PermisAPI : REJETÉE (coût récurrent + dépendance vs doctrine `16`) ;
    plan B seulement si SITADEL 3 s'avère ingérable.
- Le script d'ingestion reste à écrire — APRÈS D0 (règle « pas de code produit avant »).

### SIRENE (INSEE) — prospects B2B (les acheteurs, pas la base vendue)
- Base ouverte des entreprises : filtrer département 49 + codes NAF pisciniers/pergolistes pour construire la liste d'appels. Voir `07-VENTE-PLAYBOOK.md`.

## Récapitulatif licences

| Source | Licence | Vendable en dérivé ? |
|---|---|---|
| BD ORTHO, BD TOPO, LiDAR HD (IGN) | Licence Ouverte 2.0 | **Oui** (mention source + millésime) |
| Cadastre Etalab, BAN | Licence Ouverte 2.0 | **Oui** (idem) |
| OSM | ODbL (share-alike) | **Non pour notre modèle** — interne uniquement |
| Google Solar API | CGU propriétaires | **Non** (stockage 30 j max, revente interdite) |

## Notes opérationnelles

- Les URLs exactes portent des millésimes datés : `10_download.py` doit résoudre l'alias `latest`/l'édition la plus récente au moment du run et consigner le millésime dans `data/interim/millesimes.yaml`.
- Certains hôtes officiels (geoservices.ign.fr, cadastre.data.gouv.fr) peuvent être capricieux derrière un proxy : le miroir opendatarchives est un fallback fiable pour la BD TOPO.
