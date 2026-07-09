# Registre des activités de traitement (art. 30 RGPD)

> **DRAFT — à valider par un avocat.** Registre du responsable de traitement (il n'existe
> plus de déclaration préalable CNIL depuis 2018, `03` §5.2 — ce registre est l'obligation
> qui la remplace). Trois fiches, conformément à `03` §5.2 : (1) constitution /
> enrichissement de la base, (2) cession aux clients, (3) gestion des oppositions et
> demandes de droits. À tenir à jour et à présenter en cas de contrôle.

## 0. Identité du responsable (à compléter — bloqueurs humains)

| Champ | Valeur |
|---|---|
| Responsable de traitement | `[RAISON SOCIALE / NOM COMMERCIAL — voir 16 §6.2]` |
| Forme juridique | `[micro-entreprise (BNC) — voir 16 §6.1]` |
| Adresse | `[ADRESSE POSTALE — à compléter]` |
| Contact protection des données | `[opposition@<domaine> — voir C4]` |
| Délégué à la protection des données (DPO) | Non désigné (non obligatoire ; à réévaluer si l'activité s'étend) |
| Date de création du registre | 2026-07-09 · version v0.1 (draft) |

---

## Fiche n°1 — Constitution et enrichissement de la base

| Rubrique | Contenu |
|---|---|
| **Finalité(s)** | Constituer et enrichir une base d'adresses de biens présentant une caractéristique extérieure détectable (piscine ; puis terrasse ensoleillée) en vue de sa cession B2B pour prospection postale |
| **Base légale** | Intérêt légitime (art. 6.1.f) — voir `LIA.md` |
| **Catégories de personnes** | Foyers dont l'adresse figure dans la base (identifiés indirectement par l'adresse ; **aucun nom**) |
| **Catégories de données** | Adresse postale (BAN), commune, code INSEE, coordonnées GPS du bien, attribut du bien (surface piscine, type probable, score de confiance) |
| **Données sensibles** | Aucune |
| **Source des données** | Données publiques ouvertes : IGN (BD ORTHO, BD TOPO, RGE ALTI), cadastre DGFiP/Etalab, BAN — Licence Ouverte Etalab 2.0 |
| **Destinataires internes** | Le responsable uniquement (traitement local, `16` §2) |
| **Sous-traitants** | Aucun sur la donnée en clair ; stockage distant de sauvegarde = archives **chiffrées** uniquement |
| **Transferts hors UE** | Aucun |
| **Durée de conservation** | Tant que la base est au catalogue : millésime courant + archives datées des millésimes (nécessaires au produit « nouvelles » par diff) ; pas d'historique par adresse au-delà de ce besoin (`16` §6.5) |
| **Mesures de sécurité** | Traitement local ; pas de portail/SaaS ; sauvegardes chiffrées (age/gpg) ; scan anti-nominatif automatisé (`contrat.py`) ; pipeline idempotent à échec bruyant |

---

## Fiche n°2 — Cession de la base à des clients (prospection B2B)

| Rubrique | Contenu |
|---|---|
| **Finalité(s)** | Céder des extraits territorialisés de la base à des entreprises pour leur prospection commerciale **par courrier postal** (et terrain) |
| **Base légale** | Intérêt légitime (art. 6.1.f) — LIA §2 |
| **Catégories de personnes** | Foyers dont l'adresse figure dans l'extrait vendu |
| **Catégories de données** | Identiques à la fiche n°1 (adresse + attribut du bien ; **jamais** de données nominatives) |
| **Destinataires** | Entreprises clientes B2B, **responsables de traitement distincts** pour leurs campagnes (`03` §4) |
| **Encadrement des destinataires** | Contrat de licence imposant : usage courrier postal / terrain uniquement, interdiction de croisement nominatif et d'email/SMS/appels auto, remise obligatoire de la notice art. 14 (y.c. porte-à-porte), clause résolutoire, certification annuelle d'usage (les 4 clauses `10` §5 + LIA §4.5) |
| **Transferts hors UE** | Aucun |
| **Durée de conservation** | Exports clients et **registre des ventes** (`sales/registre.csv` : acheteur, périmètre, exclusivité, adresses-témoins du tatouage) conservés **5 ans** (preuve contractuelle, `16` §6.5) |
| **Livraison / sécurité** | Lien de téléchargement à durée limitée **ou** remise en main propre (clé USB) ; jamais de PJ email non chiffrée pour un département ; tatouage de traçabilité et mention source/millésime automatiques dans l'export |
| **Traçabilité** | Chaque livraison consignée au registre des ventes (garde-fou n°5) ; chaque export embarque millésimes + date + `git describe` du pipeline (garde-fou n°4) |

---

## Fiche n°3 — Gestion des oppositions et des demandes de droits

| Rubrique | Contenu |
|---|---|
| **Finalité(s)** | Recevoir et traiter les demandes d'opposition, d'accès, de rectification et d'effacement ; garantir l'exclusion durable des adresses concernées de tous les exports |
| **Base légale** | Respect d'une obligation légale (art. 6.1.c) — exercice des droits (chap. III RGPD) |
| **Catégories de personnes** | Toute personne exerçant un droit (propriétaire/occupant d'une adresse) |
| **Catégories de données** | Adresse postale opposée ; date et canal de la demande ; suite donnée. **Aucune identité requise** : l'exercice se fait par l'adresse (art. 11 — le responsable ne détient pas de nom, matching par adresse seule) |
| **Canaux** | Email dédié `[opposition@<domaine>]` + formulaire en ligne `[URL]` + courrier postal `[adresse]` |
| **Délai de traitement** | ≤ 1 mois |
| **Destinataires** | Répercussion aux **acheteurs passés** concernés (via `sales/registre.csv`) pour retrait de leurs propres exploitations |
| **Emplacement** | `data/optout/optout.csv` (hors git — donnée personnelle) ; filtre appliqué **systématiquement** à tous les exports (garde-fou n°6, jamais désactivé) |
| **Transferts hors UE** | Aucun |
| **Durée de conservation** | **Permanente par nature** : une adresse opposée doit rester filtrée indéfiniment (`16` §6.5) |
| **Mesures de sécurité** | Fichier hors git, inclus dans les sauvegardes chiffrées ; procédure écrite `docs/legal/procedure_reclamation.md` (C5) |

---

## Tenue du registre

- Mise à jour à chaque évolution d'une finalité, d'une catégorie de données, d'un
  destinataire type ou d'une durée de conservation.
- Ajout d'une **fiche n°4 (Terrasses)** lors du lancement du produit 2 (réexamen LIA/AIPD).
- Versionné et daté ; l'historique des versions vaut preuve de tenue.
