# Analyse d'impact relative à la protection des données (AIPD / DPIA)

> **DRAFT — à valider par un avocat spécialisé en protection des données avant toute
> première vente.** AIPD requise car le traitement constitue un **profilage de foyers à
> grande échelle** (croisement de deux critères des lignes directrices : évaluation/notation
> de caractéristiques d'un bien + traitement à grande échelle). Structure calquée sur la
> méthode et l'outil PIA de la CNIL (contexte → principes fondamentaux → risques →
> validation). Positions juridiques tirées de `docs/03-LEGAL-RGPD.md` et
> `docs/10-PREMORTEM.md` uniquement.

## 0. Métadonnées & bloqueurs humains

| Champ | Valeur |
|---|---|
| Responsable de traitement | `[RAISON SOCIALE / NOM COMMERCIAL — voir 16 §6.2]` |
| Adresse | `[ADRESSE POSTALE — à compléter]` |
| Contact / opposition | `[opposition@<domaine> — voir C4]` |
| Version | v0.1 (draft) |
| Date | 2026-07-09 |
| LIA associée | `docs/legal/LIA.md` |

**Bloqueurs** identiques à la LIA : nom commercial, forme juridique, adresse, email
d'opposition, URL du formulaire — à renseigner avant usage réel.

## 1. Vue d'ensemble du traitement (contexte)

- **Nature** : détection automatisée de caractéristiques de biens (piscine ; puis terrasse
  ensoleillée) sur imagerie aérienne publique, rattachement à l'adresse postale, et
  **cession B2B** d'un fichier de ciblage pour prospection par courrier postal.
- **Finalité** : voir `LIA.md` §1. Prospection commerciale postale ; base légale art. 6.1.f.
- **Enjeux** : commercial (l'actif = la base) ; réputationnel (sensibilité « fichage des
  piscines » post-affaire fisc, `03` §2, `10` §9) ; juridique (prospection = priorité de
  contrôle CNIL, sanctions récentes Solocal 900 k€, Hubside 525 k€).
- **Responsable** : `[à compléter]`, responsable de traitement pour la constitution,
  l'enrichissement et la cession. L'acheteur est responsable **distinct** pour ses
  campagnes (`03` §4).
- **Sous-traitants** : aucun sous-traitant sur la donnée en phase 1 (tout tourne en local,
  `16` §2 ; pas de cloud tant qu'il n'y a pas 5+ départements). Le stockage distant de
  sauvegarde reçoit **exclusivement des archives chiffrées** (age/gpg, `16` §2) — le
  prestataire n'a jamais accès au clair.

## 2. Données, cycle de vie et destinataires

| Élément | Détail |
|---|---|
| Catégories de données | Adresse postale (BAN), commune, code INSEE, coordonnées GPS du bien, attribut du bien (surface piscine, type probable, score de confiance) |
| Données exclues (par construction) | Nom, téléphone, email, tout identifiant direct de personne ; toute inférence fiscale « déclarée / non déclarée » |
| Sources | IGN (BD ORTHO, BD TOPO, RGE ALTI), cadastre DGFiP/Etalab, BAN — Licence Ouverte Etalab 2.0 |
| Flux | `data/raw` → `data/interim` → `data/final` (l'actif) → `data/exports/{acheteur}` (voir `16` §3) |
| Destinataires | Entreprises clientes B2B (responsables de traitement distincts) |
| Durées de conservation | Base = tant qu'au catalogue (millésimes + archives) ; exports + registre = 5 ans ; opt-out = permanent (`16` §6.5) |
| Transferts hors UE | Aucun |

## 3. Principes fondamentaux — proportionnalité & nécessité

- **Finalité déterminée, explicite et légitime** : oui (voir LIA §2). Pas de réutilisation
  incompatible ; usage aval verrouillé par contrat (courrier postal uniquement).
- **Minimisation** : seuls l'adresse et l'attribut du bien sont traités ; scan
  anti-nominatif automatisé du pipeline (`contrat.py`). La doctrine de recoupement (`16` §5)
  interdit de créer une ligne sur une source non vérifiable ; OSM est même exclu du score
  de confiance (contamination ODbL).
- **Exactitude** : détection validée par protocole qualité (`06`, précision ≥ 95 % annoncée
  en **borne basse d'intervalle de Wilson**, jamais « 100 % ») ; tri humain des cas
  incertains ; politique de remplacement des lignes fausses sous 90 j ; réclamations
  réinjectées comme étiquettes négatives (`data/validation/`).
- **Conservation limitée** : voir §2 ; politique de rafraîchissement par millésime, pas de
  conservation d'historiques par adresse au-delà du nécessaire au diff « nouvelles ».
- **Base légale** : art. 6.1.f, documentée dans la LIA.

## 4. Mesures garantissant les droits des personnes

| Droit | Mise en œuvre |
|---|---|
| Information (art. 13/14) | Politique de confidentialité publique + notice art. 14 au premier courrier + encart presse locale au lancement (mesures 14.5.b, cf. LIA §4.4) |
| Opposition | Email dédié + formulaire en ligne + courrier ; traitement ≤ 1 mois ; ajout à `optout.csv` ; **filtre systématique** de tous les exports (garde-fou n°6) |
| Accès / rectification / effacement | Par les mêmes canaux ; l'effacement se matérialise par l'entrée en liste d'opposition + retrait des exports futurs |
| Opposition sans identité (art. 11) | Le responsable ne détenant pas de nom, l'exercice des droits se fait **par l'adresse** (matching par adresse seule) — procédure écrite dans `docs/legal/procedure_reclamation.md` (C5) |
| Propagation aux acheteurs | Registre des ventes `sales/registre.csv` → répercussion des oppositions aux acheteurs passés |
| Réclamation CNIL | Mentionnée dans la notice et la politique de confidentialité |
| Décision automatisée (art. 22) | Aucune décision produisant des effets juridiques sur la personne |

## 5. Risques sur la sécurité des données

Trois événements redoutés (grille CNIL) : accès illégitime, modification non désirée,
disparition de données. **La base est l'actif** : sa fuite est à la fois un risque RGPD et
un risque commercial (un concurrent copie le business, `10`).

| Événement redouté | Sources de risque / menaces | Gravité | Vraisemblance | Mesures |
|---|---|---|---|---|
| **Accès illégitime** (fuite de la base ou d'un export) | Vol/perte de machine ou de disque ; compromission d'un canal de livraison ; ré-identification par croisement aval par un acheteur indélicat | Élevée (impact vie privée + perte de l'actif) | Moyenne | Aucune donnée nominative (ré-identification directe impossible) ; **pas de portail/SaaS** (surface d'attaque supprimée, `16` §1) ; disque local, jamais de base sur le cloud (`16` §2) ; **livraison chiffrée / lien à durée limitée**, jamais de PJ email pour un département ; sauvegardes **chiffrées** (age/gpg) ; interdiction contractuelle de croisement nominatif + clause résolutoire |
| **Modification non désirée** (données fausses livrées) | Erreur de détection ; erreur de jointure d'adresse (le maillon fragile en démo, `10` §6) ; corruption de fichier | Moyenne | Moyenne | Protocole qualité `06` (≥ 95 % borne Wilson) ; tri humain ; export démo en confiance **haute uniquement** ; archive datée à chaque écriture de `data/final` (`16` §3) ; politique de remplacement 90 j ; pipeline idempotent, échec bruyant (pas de `except: pass`) |
| **Disparition de données** (perte de l'actif ou des registres) | Panne disque ; suppression accidentelle | Moyenne (l'actif est régénérable ; les registres, non) | Faible/Moyenne | Sauvegarde 3-2-1 allégée : copie chiffrée hebdo de `final/exports/sales/optout/validation` sur SSD externe **et** stockage distant chiffré (`16` §2) ; `data/raw` volontairement non sauvegardé (retéléchargeable) ; script `90_backup.py` idempotent (tâche [OPUS]) |

## 6. Risque spécifique « attentes raisonnables » (droits & libertés)

Au-delà de la sécurité, le risque principal du traitement est celui identifié dans la LIA
§4.1 : un propriétaire ne s'attend pas à être profilé à partir d'imagerie aérienne.

- **Gravité** : modérée (impact = recevoir du courrier commercial ; aucune donnée sensible,
  aucun effet juridique).
- **Vraisemblance de préjudice** : faible, sous réserve des mesures d'information et
  d'opposition effectives.
- **Traitement** : mesures compensatoires publiques art. 14.5.b (LIA §4.4) + minimisation +
  opt-out réel + discours commercial cadré (« on aide les pisciniers locaux », jamais « on
  cartographie les piscines des gens », `03` §2 ; pack presse `10` §9 / C5).
- **Risque résiduel assumé** : oui — c'est précisément le point que l'avis avocat data doit
  valider avant lancement (`03` §5.8). L'AIPD ne le clôt pas unilatéralement.

## 7. Validation et plan d'action

**Avis motivé (draft)** : le traitement présente des risques **maîtrisés** sur la sécurité
(grâce à l'absence de données nominatives, l'absence de portail et le chiffrement) et un
**risque résiduel « attentes raisonnables » modéré mais réel**, traité par des mesures
compensatoires et à **faire valider par un avocat data**. L'AIPD ne peut être considérée
comme finalisée qu'après cet avis.

| Action | Responsable | Statut |
|---|---|---|
| Rédiger LIA | [OPUS] | ✅ fait (draft) |
| Rédiger AIPD | [OPUS] | ✅ fait (draft) |
| Politique de confidentialité en ligne | [OPUS] draft / 🧑 mise en ligne | draft fait |
| Notice art. 14 finalisée | [OPUS] | ✅ fait (draft) |
| Canal d'opposition opérationnel + testé (C4) | 🧑 | à faire |
| Filtre opt-out testé avec adresse factice | [OPUS]/🧑 | à faire (C4) |
| 4 clauses contrat + politique remède (C3) | 🧑 + avocat | à faire |
| **Avis avocat data sur la LIA / attentes raisonnables** | 🧑 | **à faire — bloquant lancement** |
| Encart presse locale au lancement | 🧑 | à faire |

**Réexamen de l'AIPD** : à chaque nouveau millésime, à tout changement de finalité/périmètre,
à l'ajout d'un produit (terrasses = réexamen), et sans délai en cas d'incident ou de
contrôle.
