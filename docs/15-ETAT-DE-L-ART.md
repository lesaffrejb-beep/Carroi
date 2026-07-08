# État de l'art — ce que font les géants, et ce qu'on en retient à notre échelle

> **2026-07-08.** Deux recherches web ciblées vérifiées (sources en bas) + analyse.
> Le reste (acteurs US, namR/KelFoncier, pratiques de pipeline) est consigné en prompts
> deepsearch ⑨-⑩ dans `13-DEEPSEARCH.md` — à compléter quand l'humain les lance.
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
| **Tri par incertitude (active learning « du pauvre »)** : présenter d'abord les candidats au score intermédiaire, valider en masse les scores extrêmes | pas encore : le tri présente tout dans l'ordre | 🔧 amélioration à 20 lignes, tâche [OPUS] ajoutée |
| **Intervalle de confiance sur la précision mesurée** (Wilson) plutôt qu'un point sur 100 adresses | protocole 06 = point simple | 🔧 à ajouter au protocole C1 (formule dans la tâche) |
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

## 3. Ce qui reste à apprendre (prompts ⑨-⑩ de `13-DEEPSEARCH.md`)

Cape Analytics/Nearmap/Betterview (pricing et attributs vendus aux assureurs US),
namR/Kermap (santé économique des équivalents français — namR vend des attributs issus
d'open data retraité : c'est NOTRE thèse, leur trajectoire est un signal), KelFoncier
(pricing réel, réputation), et les pratiques publiées des pipelines Microsoft Building
Footprints / Google Open Buildings (dédup, post-traitement à l'échelle).

## Sources

- [impots.gouv.fr — Généralisation du Foncier innovant](https://www.impots.gouv.fr/actualite/generalisation-du-foncier-innovant)
- [Solidaires Finances Publiques — Foncier Innovant : Efficience occulte](https://solidairesfinancespubliques.org/vie-des-services/cadastre/6581-foncier-innovant-efficience-occulte.html)
- [La Gazette des Communes — la DGFiP s'attaque au bâti isolé](https://www.lagazettedescommunes.com/947784/avec-foncier-innovant-et-lia-la-dgfip-sattaque-au-bati-isole/)
- [collectivites-locales.gouv.fr — Le Foncier innovant](https://www.collectivites-locales.gouv.fr/animer-les-territoires/environnement-et-urbanisme/le-cadastre/le-foncier-innovant)
- [Periopsis — Swimming Pool Detection via Deep Learning](https://www.periopsis.com/blog/pool-finder/) (précision ~80 % / rappel ~85 %)
- [satellite-image-deep-learning/techniques (GitHub)](https://github.com/satellite-image-deep-learning/techniques)
