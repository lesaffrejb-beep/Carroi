# État de l'art — ce que font les géants, et ce qu'on en retient à notre échelle

> **2026-07-08**, complété **2026-07-11** (deepsearchs ⑨-⑩ reçues et analysées —
> rapports bruts + synthèses dans `docs/deepsearch/`).
> **Verdict global : nos choix d'architecture sont alignés avec ce que les géants ont
> appris à leurs dépens.** Deux chiffres le prouvent, et trois leçons en découlent.

## 1. Les deux faits vérifiés qui calibrent tout

**Fait n°1 — Le fisc, avec Google et Capgemini, annonce 94 % de détection… et se fait
étriller sur les faux positifs.** Le « Foncier innovant » DGFiP (IA sur les mêmes orthos
IGN que nous) : ~140 000 piscines détectées, ~40 M€ de recettes. Mais : taux de détection
*annoncé* 94 %, note interne (citée par le syndicat Solidaires Finances Publiques) admettant
des « taux de validation revus à la baisse » pour ne pas perdre de détections taxables, un
second passage d'algorithme qui ferait chuter la détection de 20-40 %, et une presse qui
titre sur « l'algorithme qui se trompe ». Traduction pour nous :
- **Personne, même avec ces moyens, ne tient ≥ 95 % en full-auto.** Notre tri humain
  obligatoire (16_tri) n'est pas un pis-aller artisanal, c'est LA différence qualité.
- **Le risque réputationnel des faux positifs est documenté chez le géant** : notre mode
  `--demo` (confiance haute seule) et la politique de remplacement sont les bonnes parades.
- Leur volume valide notre marché : ~140 000 piscines non déclarées trouvées = le stock
  total (déclarées incluses) est énorme, département par département.

**Fait n°2 — Le deep learning brut sur ce problème fait ~80-85 %, pas 95.** Les benchmarks
publiés de détection de piscines sur imagerie 0,3-0,5 m tournent autour de **80 % de
précision / 85 % de rappel** en pur modèle. Traduction :
- L'option A (YOLOv8-seg/U-Net fine-tuné) améliorera le **rappel et le débit**, pas la
  précision finale : le tri humain reste dans la boucle quelle que soit l'option. La
  décision A/B de la roadmap porte donc sur « combien de candidats à trier », pas sur
  « peut-on supprimer le tri ». Consigné tel quel dans le critère B4.
- Notre seuillage HSV+IRC n'a pas à rougir s'il produit un ratio candidats/vrais ≤ 4:1 :
  la précision finale vient du tri, pas du détecteur.

## 2. Les leçons d'architecture (validées ou à ajouter)

| Pratique des géants | Chez nous | Verdict |
|---|---|---|
| Human-in-the-loop assumé (le fisc a des agents qui valident) | 16_tri obligatoire, incertains exclus | ✅ déjà aligné |
| Précision annoncée ≠ précision mesurée (le fisc l'a payé en presse) | garde-fou n°7 + protocole 06 | ✅ déjà aligné |
| Détection = commodité, la VALEUR est la donnée consolidée + fraîcheur | doc 09 §5 (moats : actif temporel) | ✅ déjà aligné |
| Étiquettes accumulées → réentraînement continu | clics du tri conservés (ids stables) | ✅ prévu, à exploiter en option A |
| **Tri par incertitude (active learning « du pauvre »)** : présenter d'abord les candidats au score intermédiaire, valider en masse les scores extrêmes | `cle_incertitude` dans 16_tri (PR #10) | ✅ fait 2026-07-11 ; DS4 chiffre le gain (30-70 % d'annotations en moins vs aléatoire) |
| **Intervalle de confiance sur la précision mesurée** (Wilson) plutôt qu'un point sur 100 adresses | `common.borne_basse_wilson` + protocole 06 §2 (PR #10) | ✅ fait 2026-07-11 |
| Masquage par données exogènes pour tuer des familles de faux positifs (Google : eau/altitude) | masque bâti BD TOPO ; si les étangs polluent B2-terrain → brancher la couche hydro BD TOPO | ✅ aligné, extension identifiée (DS4) |
| COG/STAC/Dask, infra cloud | mono-machine, fenêtrage, index spatiaux | ✅ NE PAS adopter — overkill documenté pour 1-3 départements ; réévaluer à 10+ |

## 2 bis. Trois faits de la seconde passe (2026-07-08, recherches ciblées)

**La loi APER tient — et le timing est MAINTENANT.** La loi Huwart (nov. 2025) a assoupli
la solarisation des parkings (min. 35 % de la moitié à ombrager en PV, le reste combinable
avec de la végétalisation) mais **les échéances 2026/2028 sont maintenues**, et le report à
2028 exige un bon de commande de panneaux **avant le 31 décembre 2026**. Conséquence : le
fichier « parkings > 1 500 m² non équipés » (cible n°1 de `14`) a une fenêtre de vente
brûlante au 2e semestre 2026 — chaque gestionnaire en retard doit commander dans les mois
qui viennent. ([Le Moniteur](https://www.lemoniteur.fr/reglementation/droit-de-l-environnement/comment-la-loi-huwart-assouplit-les-obligations-de-solarisation-des-parkings.IK43XNPCT5F3NIUKRLLGSEELVA.html),
[Banque des Territoires](https://www.banquedesterritoires.fr/ombrieres-photovoltaiques-sur-parkings-le-decret-pris-en-application-de-larticle-40-de-la-loi-aper),
[service-public](https://entreprendre.service-public.gouv.fr/vosdroits/F38187))

**namR valide la thèse par l'existence.** Société française cotée (IPO 2021, ~8 M€ levés,
+5 M€ en 2023) qui vend 200 attributs sur 34 M de bâtiments **entièrement issus d'open data
retraité** — à des grands comptes, collectivités, assureurs. Notre thèse « open data
retraité = donnée vendable » est un business model prouvé ; et leur cible grands comptes
laisse les artisans locaux — notre terrain — totalement libres.
([namR](https://namr.com/fr/nos-solutions/nos-attributs/), [Le Moniteur](https://www.lemoniteur.fr/article/la-start-up-qui-connait-tout-du-bati-francais.2139049))

> **⚠ CORRECTION 2026-07-11 — namR est en liquidation judiciaire** (prononcée le
> 01/07/2026 par le tribunal de Paris, vérifié sur les communiqués réglementaires ;
> redressement fin 2025, perte nette 8,2 M€ en 2024 pour 2,9 M€ de CA ; la cession
> d'actifs à Addactis ~4,2 M€ ne semble pas s'être concrétisée avant la liquidation).
> Lecture révisée : namR valide la thèse TECHNIQUE (open data retraité = vendable) et
> **invalide le modèle commercial généraliste** — lac de données sans finalité opérationnelle,
> grands comptes à cycles > 18 mois, R&D continue à coûts fixes lourds. Notre modèle est
> l'inverse exact (donnée activable, artisan local, cycle court, coûts ~115 €/mois, batch
> tous les 3 ans) : la faillite de namR RENFORCE nos choix `00`/`09`/`16` au lieu de les
> menacer. Analyse complète : `docs/deepsearch/DS5-CONCURRENCE-SOLAIRE-GEANTS.md`.

**⚠ La concurrence sur P1 est RÉELLE et nominative.** [Cartégie](https://www.cartegie.com/en/data/btoc-basics/swimming-pool-owners)
loue un fichier de 1 M+ de propriétaires de piscines avec ~200 000 téléphones ;
[Easyfichiers](https://www.easyfichiers.com/fr/fichier-proprietaires-piscine) et d'autres
(source IDAIA : permis de construire + détection aérienne) vendent l'équivalent en ligne.
Le risque n°8 du pre-mortem est confirmé nommément. Conséquences appliquées :
- le pitch P1 « fichier seul » se repositionne : ACHAT définitif (vs location), vérifiabilité
  ligne à ligne sur la zone, ZÉRO risque RGPD/Bloctel pour le client, et l'EXCLUSIVITÉ
  locale qu'un broker national ne vendra jamais — contre-objection ajoutée au kit `11` §4 ;
- le segment où les brokers ne peuvent PAS suivre : les « nouvelles piscines » locales
  fraîches (leur base nationale a une fraîcheur inconnue par commune) → le moteur de diff
  de millésimes est implémenté (`millesimes.py`, appariement spatial un-pour-un, testé) ;
- ça renforce l'arbitrage `14` : les cibles ①② (ombrières, foncier) n'ont pas de broker
  installé équivalent, le trio gros-ticket monte encore d'un cran en priorité relative.

## 3. Deepsearchs ⑨-⑩ reçues (2026-07-11) — l'essentiel

Rapports bruts et synthèses critiques dans `docs/deepsearch/` (DS4 pipelines, DS5 géants).
À retenir en plus des sections ci-dessus :
- **Cape Analytics/EagleView** : la valeur = intégration dans le flux de travail du client
  + ROI chiffrable (inspection évitée à 35 $) + human-in-the-loop sous seuil de confiance.
  Transposé chez nous : formuler le ROI en « coût d'un lead évité » (les plateformes vendent
  le lead piscine 30-150 €, mutualisé à 3-5 artisans — chiffres pour le kit `11` §4).
- **Brokers** (Cartégie & co) : 0,15-0,80 €/contact en LOCATION + minimums 350-650 € ;
  données déclaratives périmées. Contre-objection chiffrée → kit `11` §4.
- **KelFoncier** : hyper-spécialisation + ROI immédiat = le modèle qui marche en France.
- **Kermap** : ~550 k€ de CA, dépendance B2G/subventions — pas notre voie.
- **Pipelines Microsoft/Google (DS4)** : chevauchement de fenêtres, fusion aux frontières,
  seuils de confiance (0,90 → 90-94 % précision / ~70 % rappel), débit humain 1 000-1 200
  vignettes/h — tous nos choix confirmés, rien à adopter de plus à notre échelle.
- **Datasets piscines (DS5)** : si l'option A se déclenche → partir de `sp-swimming-pools`
  (CC-BY-4.0, poids initiaux) + fine-tuning sur BD ORTHO annotée main ; JAMAIS
  `osm-swimming-pools` (AGPL contaminante) ni BH-POOLS (images Google, CGU).

## 4. Survey open source arbitré (2026-07-12, session Fable — vérifié + mesuré)

Un survey LLM du paysage open source a été passé au crible. Verdict global confirmé :
l'open source ne couvre QUE la détection (notre « commodité ») ; rien n'existe sur le
tri humain léger, la jointure adresse RGPD-propre, le diff objet, la consolidation —
le moat est intact. Arbitrages pièce par pièce :

- **⭐ CoSIA (IGN) — LA découverte, absente du survey** : l'État publie la détection
  par IA (classe « Piscine », France entière, vecteur, Licence Ouverte 2.0, plusieurs
  millésimes). **Mesuré sur Bouchemaine : rappel 88,1 % vs OSM, 68 % des piscines
  couvertes vues, quasi-sur-ensemble de notre HSV (98,7 %).** Décision : CoSIA devient
  source principale de candidats aux côtés de SYM=65 (fiche complète `02`, doctrine
  `16` §5, exécution tâche 13 de `08`). Conséquence stratégique : l'option A (modèle
  maison) est **définitivement enterrée** — l'État entraîne et publie mieux que ce
  qu'on ferait, gratuitement, sur nos propres dalles.
- **samgeo / segment-geospatial (MIT, SAM + prompts texte)** : écarté. Les retours
  publiés confirment « masques de qualité pour piscines à l'eau claire » — même mode
  d'échec que notre HSV sur les bâches (l'autopsie du rappel a montré que c'est LE
  problème), GPU ≥ 8 Go requis, et dominé par CoSIA sur toute la ligne.
- **Download-BDOrtho21** : rien à prendre — notre `12_extraire_dalles_ortho.py` fait
  mieux (index `dalles.shp` embarqué dans l'archive, extraction ciblée sans tout
  décompresser).
- **Label Studio / CVAT** : NON. Variante AGPL (contamination), lourds à installer —
  notre planche zéro-install double-clic est précisément le différenciateur d'usage
  (un bénévole trie sans rien installer). Le format d'export 4 colonnes actuel suffit ;
  on pourra s'inspirer de l'active learning (tri par incertitude : déjà fait, PR #10).
- **Jonas1312 / cv2-pool-detection / NAIP** : pédagogiques, inférieurs à l'existant. Rien.
- **Détecteurs custom (ex-option A, `sp-swimming-pools` CC-BY-4.0)** : la note DS5
  ci-dessus reste exacte mais est rendue CADUQUE par CoSIA — ne réévaluer que si CoSIA
  était retiré ou sa qualité s'effondrait sur un autre département.

## 5. VLM propriétaires payants — arbitrage (2026-08-05, session Fable, demande JB)

Contexte : la vague X d'août 2026 (Qwen3.8-Max « meilleur VLM de détection d'objets »,
démo Tilebox = 247 centrales PV détectées zero-shot sur tout le Brandebourg en trois
prompts) pose la question « faut-il PAYER un modèle pour détecter nos piscines ? ».
**Réponse arbitrée : NON pour détecter, OUI marginalement pour arbitrer.** Le
raisonnement, à conserver car il resservira à chaque nouvelle vague de modèles :

**Fait n°1 — la démo Brandebourg est exactement notre situation, sauf qu'en France
l'État a déjà payé la facture.** Tilebox a dû faire tourner un VLM généraliste parce
qu'aucune couche publique de centrales PV n'existait. Pour les piscines du 49, CoSIA
donne le même livrable, produit par un modèle *spécialiste* entraîné sur nos propres
dalles, gratuit, en Licence Ouverte, sur 3 millésimes (§4 ci-dessus, mesuré : rappel
88,1 %, CoSIA ∪ SYM=65 = 89,5 %). Payer un généraliste pour reproduire un spécialiste
gratuit est un anti-pattern : **avant de payer un modèle, vérifier que l'État ne l'a
pas déjà fait tourner.**

**Fait n°2 — les benchmarks cités ne mesurent pas notre tâche.** Le « 60 % mAP (single
box) / 80 % mAP (multi-box) » de Qwen3.8-Max est un mAP de détection généraliste :
loin des 95 % de précision exigés par `06`, et le mAP ne dit rien du mode d'échec qui
nous tue (bâches, ardoises bleues, trampolines). Notre pré-tri maison, lui, est mesuré
sur NOS données : AUC 0,997, 249 auto-oui à 95 % de précision. Règle R10 de `17`
appliquée : un chiffre de benchmark public ne déclenche aucune décision coûteuse.

**Fait n°3 — le coût API n'est jamais le poste dominant ; le temps humain l'est.**
Prix constatés au 2026-08-05, par vignette (~1 image + prompt court, ~2 000 tokens) :
Gemini 3 Flash ~0,004 $ · Qwen3.8-Max ~0,011 $ (2 $/M in, 6 $/M out, GA 2026-08-03) ·
Claude Opus 5 ~0,018 $. À l'échelle du 49 (~30-40 k candidats), un passage VLM complet
coûte 140-700 € — non-bloquant en absolu, mais **inutile** vu le fait n°1, alors que
50 h de tri humain brut (à ~600-700 vignettes/h mesurées sur la planche) coûtent la
seule ressource réellement rare du projet. Chiffrage complet : `16` §4 bis.

**Décision.** Ordre de préséance des sources de candidats, non négociable sans mesure :
**(1) CoSIA ∪ SYM=65 gratuit → (2) pré-tri maison `22_pretri` gratuit → (3) VLM payant
en DEUXIÈME AVIS sur la seule bande incertaine → (4) humain sur les désaccords + tirage
aléatoire de validation.** Un VLM ne devient candidat au rang (1) que si CoSIA disparaît,
s'effondre sur un autre département, ou pour un produit SANS couche publique équivalente
(cf. `14` : ombrières, friches — c'est là que la démo Tilebox est réellement transposable).

**Ré-évaluation** : ne rouvrir ce dossier que sur un fait mesuré (nouveau département
sans CoSIA, ou test §E de `06` montrant le VLM au-dessus du pré-tri sur NOS 977 labels
Bouchemaine), jamais sur une annonce de modèle.

## Sources

- [impots.gouv.fr — Généralisation du Foncier innovant](https://www.impots.gouv.fr/actualite/generalisation-du-foncier-innovant)
- [Solidaires Finances Publiques — Foncier Innovant : Efficience occulte](https://solidairesfinancespubliques.org/vie-des-services/cadastre/6581-foncier-innovant-efficience-occulte.html)
- [La Gazette des Communes — la DGFiP s'attaque au bâti isolé](https://www.lagazettedescommunes.com/947784/avec-foncier-innovant-et-lia-la-dgfip-sattaque-au-bati-isole/)
- [collectivites-locales.gouv.fr — Le Foncier innovant](https://www.collectivites-locales.gouv.fr/animer-les-territoires/environnement-et-urbanisme/le-cadastre/le-foncier-innovant)
- [Periopsis — Swimming Pool Detection via Deep Learning](https://www.periopsis.com/blog/pool-finder/) (précision ~80 % / rappel ~85 %)
- [satellite-image-deep-learning/techniques (GitHub)](https://github.com/satellite-image-deep-learning/techniques)
- [CoSIA — Géoplateforme, ressource de téléchargement](https://data.geopf.fr/telechargement/resource/COSIA) · [fiche data.gouv.fr](https://www.data.gouv.fr/datasets/cosia) · [modèles FLAIR (IGNF, Hugging Face)](https://huggingface.co/IGNF)
- [opengeos/segment-geospatial (samgeo)](https://github.com/opengeos/segment-geospatial) · [retour d'expérience piscines (granular.ai)](https://www.granular.ai/resources/blog/detecting-pools-in-urban-areas-using-sam-geo)
- §5 (VLM payants, 2026-08-05) : [Qwen 3.8 Max — 2 $/6 $ par MTok, GA 2026-08-03](https://www.developersdigest.tech/blog/qwen-3-8-max-release-2026) · [OpenRouter — qwen3.8-max](https://openrouter.ai/qwen/qwen3.8-max) · [eesel — Qwen3.8-Max pricing & hidden costs](https://www.eesel.ai/blog/qwen38-max-pricing) · posts X du 2026-08-04/05 (@skalskip92 : mAP single/multi-box ; @__snamber : run Brandebourg via Tilebox) — captures fournies par JB, non archivées dans le repo.
