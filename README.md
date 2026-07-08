# Bases de données géolocalisées qualifiées — Maine-et-Loire (49)

Business : constituer et vendre à des professionnels locaux (pisciniers, installateurs de pergolas…) des bases d'**adresses postales qualifiées par des attributs du bien** — « ces adresses ont une piscine », « ces adresses ont une terrasse plein sud » — construites exclusivement à partir de **données publiques ouvertes** (IGN, cadastre, BAN — Licence Ouverte 2.0, revente de dérivés autorisée).

**Aucune donnée nominative, jamais.** Adresses + attributs du bien, point. C'est le pilier légal du modèle (voir `docs/03-LEGAL-RGPD.md`).

## Lire dans l'ordre

| Doc | Contenu |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Instructions et garde-fous pour les sessions LLM |
| [`docs/00-VISION.md`](docs/00-VISION.md) | Produits, prix, protocole de preuve en RDV |
| [`docs/01-ARCHITECTURE.md`](docs/01-ARCHITECTURE.md) | Architecture technique |
| [`docs/02-DATA-SOURCES.md`](docs/02-DATA-SOURCES.md) | Sources vérifiées (URLs, licences, pièges) |
| [`docs/03-LEGAL-RGPD.md`](docs/03-LEGAL-RGPD.md) | Cadre légal, checklist de conformité bloquante |
| [`docs/04-PIPELINE-PISCINES.md`](docs/04-PIPELINE-PISCINES.md) | Produit 1 — guide d'exécution |
| [`docs/05-PIPELINE-TERRASSES.md`](docs/05-PIPELINE-TERRASSES.md) | Produit 2 — architecture (dont verdict Google Solar API : écarté) |
| [`docs/06-QUALITE-VALIDATION.md`](docs/06-QUALITE-VALIDATION.md) | Validation, score de confiance, tatouage anti-revente |
| [`docs/07-VENTE-PLAYBOOK.md`](docs/07-VENTE-PLAYBOOK.md) | Prospection B2B, scripts, RDV, contrat |
| [`docs/08-ROADMAP.md`](docs/08-ROADMAP.md) | **Journal de bord — commencer ici pour savoir où on en est** |

## Décisions structurantes (résumé)

1. **Produit 1 = piscines**, détectées sur orthophoto IGN 20 cm (aucune base ouverte ne liste les piscines privées ; la détection maison est l'actif et la barrière à l'entrée).
2. **Google Solar API écarté** (CGU : stockage 30 jours max, revente interdite) → produit 2 basé sur LiDAR HD IGN, gratuit et librement commercialisable.
3. **OSM en développement uniquement** (licence ODbL incompatible avec l'exclusivité).
4. Les données ne rentrent jamais dans git : le repo = code + config + docs ; l'actif vit dans `data/` (local, sauvegardé à part).
