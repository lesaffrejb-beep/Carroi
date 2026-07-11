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

## Sources

- [impots.gouv.fr — Généralisation du Foncier innovant](https://www.impots.gouv.fr/actualite/generalisation-du-foncier-innovant)
- [Solidaires Finances Publiques — Foncier Innovant : Efficience occulte](https://solidairesfinancespubliques.org/vie-des-services/cadastre/6581-foncier-innovant-efficience-occulte.html)
- [La Gazette des Communes — la DGFiP s'attaque au bâti isolé](https://www.lagazettedescommunes.com/947784/avec-foncier-innovant-et-lia-la-dgfip-sattaque-au-bati-isole/)
- [collectivites-locales.gouv.fr — Le Foncier innovant](https://www.collectivites-locales.gouv.fr/animer-les-territoires/environnement-et-urbanisme/le-cadastre/le-foncier-innovant)
- [Periopsis — Swimming Pool Detection via Deep Learning](https://www.periopsis.com/blog/pool-finder/) (précision ~80 % / rappel ~85 %)
- [satellite-image-deep-learning/techniques (GitHub)](https://github.com/satellite-image-deep-learning/techniques)
