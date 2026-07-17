# Veille 2026-07-17 — annotation multi-passes, détection piscines, agrégation

> Produite par agent de recherche (session Fable). URLs vérifiées au fetch.
> Synthèse actionnable ; le TOP 5 est intégré à l'arbre des tâches (docs/08).

## Repos à piller

| Repo | Licence | La mécanique à reprendre |
|---|---|---|
| [CVAT](https://github.com/cvat-ai/cvat) | MIT | **Honeypots** : jeu or FIGÉ à la création (anti-apprentissage des golds), injecté 5-10 %, EXCLU de l'export, score par trieur/job ([doc](https://docs.cvat.ai/docs/qa-analytics/quality-control/)) |
| [Label Studio](https://github.com/HumanSignal/label-studio) | Apache 2 | Agrément pairwise (moyenne des accords par paire) ; IoU pour le géométrique. Le dashboard IAA est Enterprise → le réimplémenter chez nous est le bon choix |
| [Argilla](https://github.com/argilla-io/argilla) | Apache 2 | Distribution `min_submitted=N` : l'item disparaît des files dès N réponses — zéro table d'assignation (≈ notre moins-vu-d'abord, validé) |
| [crowd-kit](https://github.com/Toloka/crowd-kit) | Apache 2 | Référence Dawid-Skene ([dawid_skene.py](https://github.com/Toloka/crowd-kit/blob/main/crowdkit/aggregation/classification/dawid_skene.py)) + **Gold Majority Vote** (majorité pondérée par le score questions d'or) |
| [STDL GEPOOL](https://tech.stdl.ch/PROJ-GEPOOL/) | — | Clone institutionnel suisse : Mask R-CNN + registre officiel. Leçon : nettoyer la vérité terrain = +8 pts F1 ; seuil confiance choisi par les métiers |
| [samgeo](https://github.com/opengeos/segment-geospatial) | MIT | SAM sur GeoTIFF : un clic trieur → polygone géoréférencé (upgrade futur des signalements) |
| [torchgeo](https://github.com/microsoft/torchgeo) | MIT | Samplers géospatiaux à la volée (pas de pré-génération de crops) |
| [Jonas1312/swimming-pool-detection](https://github.com/Jonas1312/swimming-pool-detection) | sans licence | Idée : classifieur binaire + Class Activation Maps = localisation gratuite (à réimplémenter, pas copier) |

## Papiers / références

- **Dawid & Skene 1979** (JRSS-C) — implémenté chez nous (`agregation.py`). Variantes :
  Fast-DS (arXiv:1803.02781, inutile à notre échelle), GLAD (NIPS 2009), MACE
  (NAACL 2013) — pas assez de signal à 2-5 trieurs. **À faire : initialiser les
  matrices de confusion avec les scores questions d'or** (esprit Gold Majority Vote).
- **Active learning** : l'incertitude seule sélectionne des lots redondants.
  Recette gagnante (ICCV 2025, « AL Meets Foundation Models ») : proba ∈ [0,3-0,7]
  puis k-means sur embeddings (8-16 clusters), échantillonner par cluster.
- **Foncier Innovant (DGFiP)** : CNN sur BD ORTHO + vérif humaine systématique.
  94 % confirmés = chiffre APRÈS humain ; brut machine 30-60 % d'erreur en zone
  difficile. Notre architecture farm = l'état de l'art industriel, pas un pis-aller.
- **CoSIA** : 15 classes dont Piscine, 20 cm, Licence Ouverte, ~78 % exactitude
  globale (brut de modèle → pré-annotateur, pas une vérité).

## Les 3 pépites hors sentiers battus

1. **FLAIR (IGN)** : dataset BD ORTHO 20 cm, 19 classes DONT piscine, et des
   **modèles pré-entraînés sur Hugging Face** ([FLAIR-INC resnet34-deeplabv3](https://huggingface.co/IGNF/FLAIR-INC_rgb_15cl_resnet34-deeplabv3)).
   Le CNN anti-bâchées part de là, pas de zéro : même imagerie, classe déjà apprise.
2. **CoSIA en flux WMS** (vérifié ce jour : couches `IGNF_COSIA_2017-2020 /
   2021-2023 / 2024-2026` sur data.geopf.fr/wms-r) : le pré-annotateur national
   SANS télécharger le département → débloque la tâche 13 sans le disque NOIR.
3. **OSM + data.gouv « Piscines (OSM) »** : des milliers de polygones positifs
   certains → questions d'or gratuites + positifs d'entraînement.

## Avertissement transverse

Ne jamais comparer notre AUC de pré-tri au « 94 % » du Foncier Innovant (chiffre
post-humain). Et re-passer au farm les items où Dawid-Skene et la majorité
divergent (leçon STDL : la vérité terrain se nettoie).
