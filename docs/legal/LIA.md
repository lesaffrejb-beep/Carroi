# Analyse d'intérêt légitime (LIA)

> **DRAFT — à valider par un avocat spécialisé en protection des données avant toute
> première vente.** Ce document met en œuvre la base légale « intérêt légitime »
> (art. 6.1.f RGPD) pour la constitution, l'enrichissement et la cession de la base
> d'adresses qualifiées. Il suit la méthode CNIL du test en trois temps (intérêt →
> nécessité → mise en balance) et intègre le raisonnement art. 14.5.b (stock invendu).
> Toutes les positions juridiques ci-dessous sont tirées de `docs/03-LEGAL-RGPD.md` et
> `docs/10-PREMORTEM.md` (§4, §5) — aucune position nouvelle n'a été inventée ici.

## 0. Métadonnées & éléments à compléter par l'humain avant usage

| Champ | Valeur |
|---|---|
| Responsable de traitement | `[RAISON SOCIALE / NOM COMMERCIAL — à trancher, voir 16 §6.2]` |
| Forme juridique | `[micro-entreprise (BNC) au lancement — à confirmer avec l'avocat, voir 16 §6.1]` |
| Adresse du responsable | `[ADRESSE POSTALE — à compléter]` |
| Contact protection des données | `[opposition@<domaine> — email dédié, voir C4]` |
| Version du document | v0.1 (draft) |
| Date de rédaction | 2026-07-09 |
| Prochaine revue | à chaque nouveau millésime des sources OU à toute évolution de l'usage |

**Bloqueurs humains** : le nom commercial, la forme juridique définitive, l'adresse
postale, l'email d'opposition dédié et l'URL du formulaire d'opposition doivent être
renseignés avant la première utilisation réelle. Tant qu'ils sont entre crochets, ce
document reste un draft interne.

## 1. Description du traitement

- **Finalité** : constituer une base d'adresses postales de biens présentant une
  caractéristique extérieure détectable (piscine privée ; en phase 2, terrasse
  ensoleillée), afin de la **céder à des entreprises B2B** qui l'utilisent pour de la
  **prospection commerciale par courrier postal** (et prospection terrain).
- **Données traitées** (minimisation stricte, garde-fou n°1 de `CLAUDE.md`) : adresse
  postale normalisée (BAN), commune, code INSEE, coordonnées GPS du bien, attribut du
  bien (surface approximative de piscine, type probable, score de confiance).
  **Aucune donnée nominative** : ni nom, ni téléphone, ni email de particulier, jamais.
- **Personnes concernées** : les foyers dont l'adresse figure dans la base. Une adresse
  postale sans nom **reste une donnée personnelle** (identifiant indirect du foyer —
  position CNIL, cf. `03` §2) : cette LIA ne plaide pas « pas de nom donc pas de RGPD ».
- **Sources** : exclusivement des données publiques ouvertes sous Licence Ouverte
  Etalab 2.0 — IGN (BD ORTHO, BD TOPO, RGE ALTI), plan cadastral DGFiP/Etalab, Base
  Adresse Nationale. La licence autorise explicitement l'exploitation commerciale et
  l'inclusion dans un produit vendu (`03` §1).
- **Destinataires** : entreprises clientes (pisciniers, paysagistes, installateurs, etc.),
  responsables de traitement **distincts** pour leurs propres campagnes (`03` §4).
- **Durée de conservation** (`16` §6.5) : la base commercialisée est conservée tant
  qu'elle est au catalogue (millésime le plus récent + archives de millésimes, nécessaires
  au produit « nouvelles piscines » par diff) ; les exports clients et le registre des
  ventes sont conservés 5 ans (preuve contractuelle) ; la liste d'opposition est conservée
  de façon permanente par nature (c'est un filtre).

## 2. Étape 1 — L'intérêt poursuivi est-il légitime ?

Un intérêt légitime doit être **licite, réel et présent**, et suffisamment précis.

- **Licite** : la commercialisation de fichiers de prospection est une activité légale ;
  la prospection commerciale **par courrier postal est en opt-out** (aucun consentement
  préalable requis — position publique de la CNIL, `03` §1). Les sources sont utilisées
  dans le strict respect de leur licence (exploitation commerciale autorisée).
- **Réel et présent** : il existe une demande B2B identifiée (artisans locaux qui doivent
  cibler leur prospection sans budget d'acquisition digital), et l'activité de vente est
  effective, non hypothétique.
- **Intérêt de tiers** : l'intérêt commercial légitime des entreprises clientes à
  identifier des prospects pertinents sur leur zone est également reconnu comme un intérêt
  susceptible de fonder l'art. 6.1.f.

**Conclusion étape 1** : l'intérêt (commercialiser une base de ciblage postal B2B à partir
de données publiques ouvertes) est légitime.

## 3. Étape 2 — Le traitement est-il nécessaire ?

Le traitement doit être **nécessaire** à la finalité, sans moyen moins intrusif atteignant
le même but.

- **Adéquation** : pour permettre une prospection postale ciblée « propriétaires de
  piscine », il faut disposer de l'adresse du bien et de l'attribut. Il n'existe **aucune
  base ouverte** listant les piscines privées (vérifié, `02` / journal `08`) : la détection
  sur orthophoto est la seule voie.
- **Minimisation** : on ne collecte **que** l'adresse + l'attribut du bien. On exclut par
  construction toute donnée nominative, tout numéro, tout email — c'est le moyen le moins
  intrusif compatible avec la finalité. La doctrine de recoupement (`16` §5) interdit même
  de créer une ligne sur une source non vérifiable ; la détection ortho reste la source de
  vérité.
- **Alternatives écartées** :
  - Croiser avec des fichiers nominatifs → **interdit** (garde-fou n°1, `03` §3.5) et non
    nécessaire à la finalité (le courrier postal se distribue sur l'adresse seule).
  - Prospection email/SMS → hors périmètre : interdite sans opt-in (art. L.34-5 CPCE),
    verrouillée au contrat (`03` §3.2, clause ci-dessous).

**Conclusion étape 2** : le traitement est nécessaire et déjà réduit au minimum de données
compatible avec la finalité.

## 4. Étape 3 — Mise en balance (le point sensible)

Le test central : l'intérêt poursuivi **prévaut-il** sur les droits, libertés et **attentes
raisonnables** des personnes concernées ?

### 4.1 Le risque résiduel identifié honnêtement

Le point faible reconnu (`03` §2) est le critère des **attentes raisonnables** : un
propriétaire ne s'attend pas à ce que l'imagerie aérienne publique serve à profiler son
foyer à des fins commerciales. C'est **le** risque juridique résiduel du modèle, même en
pleine conformité. Cette LIA ne le masque pas ; elle le traite par des mesures
compensatoires.

### 4.2 Éléments qui pèsent en faveur de la mise en balance

- **Impact faible sur la vie privée** : aucune donnée sensible, aucune donnée nominative,
  aucun profilage de la personne (seule une **caractéristique du bien** est attribuée) ;
  la finalité (recevoir éventuellement une offre commerciale par courrier) est de faible
  intrusivité et sans effet juridique ni décision automatisée sur la personne.
- **Sources publiques et ouvertes**, dont la réutilisation commerciale est expressément
  autorisée par la licence — les personnes ne sont pas « re-collectées » auprès d'un tiers
  opaque.
- **Canal de prospection le moins intrusif** (courrier postal, opt-out reconnu par la CNIL)
  — et interdiction contractuelle de tout autre canal.

### 4.3 Mesures compensatoires effectives (conditionnent la validité de la balance)

1. **Minimisation stricte** appliquée par le pipeline (scan anti-nominatif automatisé,
   `contrat.py` ; garde-fou n°1).
2. **Information effective** :
   - **Politique de confidentialité publique** en ligne (voir
     `docs/legal/politique_confidentialite.md`), décrivant traitement, sources,
     destinataires et droits — **mesure art. 14.5.b, cf. §5 ci-dessous**.
   - **Notice art. 14** jointe à chaque fichier vendu, que l'acheteur a l'obligation
     contractuelle d'insérer dans son **premier courrier** à chaque adresse (voir
     `docs/templates/notice_art14.txt`).
3. **Droit d'opposition réel, simple et gratuit** : email dédié + formulaire en ligne +
   courrier, traitement ≤ 1 mois, ajout à `data/optout/optout.csv`, filtre appliqué
   **systématiquement** à tous les exports (garde-fou n°6) et **propagation aux acheteurs
   passés** via le registre des ventes (`sales/registre.csv`).
4. **Encadrement contractuel de l'aval** : quatre clauses opposables à l'acheteur (§4.5).
5. **Pas de finalité fiscale ni d'inférence « déclarée / non déclarée »** — interdiction
   absolue (`03` §3.4) ; la base ne comporte ni ne suggère jamais un tel attribut.

### 4.4 Traitement de l'art. 14.5.b — le stock invendu

Constat (`10` §4) : ~95 % des adresses de la base ne seront jamais mailées, donc jamais
informées individuellement au premier contact. L'exemption d'« effort disproportionné »
(art. 14.5.b) n'est mobilisable que si des **mesures compensatoires publiques** sont
prises. Elles le sont, **avant tout envoi de courrier** :

- **Politique de confidentialité publique et accessible** décrivant le traitement, les
  sources et les droits ;
- **Encart d'information dans la presse locale** au lancement (mesure publique de portée
  départementale) ;
- **Formulaire d'opposition en ligne opérationnel AVANT toute campagne** de l'un des
  acheteurs.

Pour les adresses effectivement mailées, l'information individuelle art. 14 est délivrée
via la **notice jointe au premier courrier** (obligation contractuelle de l'acheteur), au
plus tard au premier contact — l'exemption 14.5.b n'est donc invoquée que pour le stock
non contacté, avec mesures publiques compensatoires à l'appui.

### 4.5 Les quatre clauses contractuelles (mitigation « responsabilité en chaîne », `10` §5)

La mise en balance **repose sur** l'existence de ces clauses dans le contrat de licence
(livrable C3, à valider par avocat). Elles sont ici des mesures de la LIA, pas de simples
conditions commerciales :

1. **Interdictions explicites** : interdiction de croiser le fichier avec tout fichier
   nominatif (annuaire inversé, réseaux sociaux…) ; interdiction d'usage en email / SMS /
   appels automatisés (usage limité au **courrier postal** et à la **prospection terrain**).
2. **Remise obligatoire de la notice art. 14** au premier contact, **y compris en
   porte-à-porte**.
3. **Clause résolutoire** : résiliation de plein droit en cas de manquement aux
   obligations RGPD (notamment défaut de notice ou usage interdit).
4. **Certification annuelle d'usage** par l'acheteur (attestation de conformité de
   l'usage réel du fichier).

S'y ajoute la **politique de précision et de remède** : remplacement des lignes fausses
signalées sous 90 jours, avec entrée de la réclamation dans `data/validation/` comme
étiquette négative (`10` §5, `12`).

### 4.6 Conclusion de la mise en balance

Sous réserve de la **mise en œuvre effective et vérifiée** de l'ensemble des mesures des
§4.3 à §4.5 (elles conditionnent la conclusion) et de la **validation par un avocat data**
du point « attentes raisonnables » (`03` §5.8), l'intérêt légitime poursuivi est
susceptible de prévaloir sur les droits et libertés des personnes concernées, compte tenu
du faible impact, de la minimisation, du canal opt-out et de l'information + opposition
effectives. **Le risque résiduel « attentes raisonnables » subsiste et est assumé** ; il
justifie à lui seul l'avis avocat préalable et la rédaction d'une AIPD (voir
`docs/legal/AIPD.md`).

## 5. Décision & suivi

- **Base légale retenue** : art. 6.1.f RGPD (intérêt légitime).
- **AIPD** : requise (profilage de foyers à grande échelle) — voir `AIPD.md`.
- **Conditions de validité** : mesures §4.3–§4.5 opérationnelles et testées + avis avocat
  obtenu (checklist `03` §6).
- **Réexamen** : à chaque nouveau millésime des sources, à tout élargissement de la
  finalité ou du périmètre de données, et sans délai en cas de plainte ou de contrôle.
- **Traçabilité** : cette LIA est archivée et datée ; toute modification est journalisée
  (nouvelle version + motif), conformément à la logique de traçabilité des millésimes
  (garde-fou n°4).
