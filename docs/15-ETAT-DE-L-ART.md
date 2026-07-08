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
