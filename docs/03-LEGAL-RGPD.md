# Cadre légal & RGPD — garde-fous non négociables

> **Statut : recherche approfondie effectuée (juillet 2026, sources CNIL/officielles citées). Ce document est le garde-fou central du projet. Aucune vente sans avoir traité la checklist §6.**
> Résumé honnête : **le modèle est juridiquement viable mais PAS anodin.** La prospection postale est licite sans consentement préalable, les licences open data autorisent la revente — mais la base constitue un traitement de données personnelles à part entière, et la prospection commerciale est une **priorité de contrôle CNIL** (sanctions récentes : Solocal 900 k€ en 2025, Hubside 525 k€ en 2024). La conformité est un coût d'entrée réel ET un argument de vente.

## 1. Ce qui est clairement acquis (le socle légal du business)

- **Licences open data : revente autorisée.** BD TOPO, BD ORTHO, RGE ALTI (IGN), cadastre Etalab, BAN sont sous **Licence Ouverte Etalab 2.0** : reproduction, adaptation, **exploitation commerciale et inclusion dans des produits vendus** explicitement autorisées. Seules obligations : mentionner la source et la date de mise à jour (ex. *« Source : IGN BD TOPO — DGFiP/Etalab cadastre — BAN, millésime AAAA »* — le script d'export l'ajoute automatiquement) et ne pas suggérer un endorsement officiel. (Texte : github.com/etalab/licence-ouverte)
- **La prospection B2C par courrier postal est en opt-out**, pas opt-in : aucun consentement préalable requis, contrairement à l'email/SMS (cnil.fr/fr/la-prospection-commerciale-par-courrier-postal). Conditions : information des personnes et possibilité de s'opposer simplement et gratuitement.
- **Le porte-à-porte** n'est pas interdit ; c'est le droit de la consommation (délai de rétractation 14 jours, etc.) qui s'applique à l'acheteur, pas un sujet CNIL en soi — mais le fichier de ciblage derrière, si.

## 2. Ce qu'il faut regarder en face

- **Une adresse postale SANS nom est une donnée personnelle.** La CNIL cite l'adresse comme identifiant indirect ; l'adresse désigne le foyer. L'attribut "a une piscine" rattaché à une adresse = **enrichissement/profilage de foyers**, pleinement dans le champ du RGPD. Ne jamais plaider "il n'y a pas de noms donc pas de RGPD" — c'est faux (sanction NESTOR 2020 : adresses reconstituées ≠ échappatoire).
- **La base légale est l'intérêt légitime (art. 6.1.f)**, et son point faible est le critère des **« attentes raisonnables »** : un propriétaire ne s'attend pas à ce que l'imagerie aérienne serve à le profiler commercialement. C'est LE risque juridique résiduel du modèle, même en pleine conformité. Mitigations : minimisation stricte (adresse + attribut du bien, rien d'autre), information effective, opt-out réel.
- **Article 14 RGPD (données non collectées auprès de la personne)** : obligation d'informer les foyers, au plus tard **au premier contact**. L'exemption "effort disproportionné" est lue restrictivement par la CNIL (sanction Monsanto 400 k€) et **ne tient pas ici : on a l'adresse par construction**. Conséquence opérationnelle : le premier courrier envoyé par l'acheteur doit contenir la notice d'information (voir §5).
- **Sensibilité fiscale** : la DGFiP détecte les piscines non déclarées ("Foncier innovant" — qui a nécessité un décret et une consultation CNIL). Notre fichier ne doit **jamais** contenir ou suggérer une inférence "déclarée/non déclarée", ni être vendu à des fins autres que marketing. Risque réputationnel/presse à garder en tête dans le discours commercial ("on aide les pisciniers locaux", pas "on cartographie les piscines des gens").

## 3. Interdits absolus (le pipeline et les contrats les verrouillent)

1. Vendre ou collecter **noms, téléphones, emails** de particuliers. Adresse + attributs du bien, rien d'autre.
2. Laisser un acheteur utiliser le fichier pour **email/SMS/appels automatisés** (opt-in obligatoire, art. L.34-5 CPCE) → interdiction explicite au contrat : usage limité au courrier postal et à la prospection terrain.
3. Vendre une adresse figurant sur la **liste d'opposition** (`data/optout/optout.csv`) — filtre technique systématique.
4. Toute mention/inférence fiscale ("piscine non déclarée").
5. Croiser la base avec des fichiers nominatifs (annuaires, réseaux sociaux…), même à la demande d'un client.

## 4. Répartition des rôles (à refléter dans le contrat de vente)

- **Nous (vendeur)** : responsable de traitement pour la constitution, l'enrichissement et la cession de la base.
- **L'acheteur** : responsable de traitement **distinct** pour ses campagnes. La jurisprudence CNIL (Solocal, Hubside) exige de l'acheteur qu'il **vérifie réellement** la provenance des données — une simple clause "données conformes RGPD" ne suffit pas. Notre parade commerciale : livrer avec chaque fichier un **dossier de traçabilité** (sources open data, millésimes, méthode) — ça transforme une obligation en argument de vente ("vous êtes couvert, voici la provenance documentée").

## 5. Obligations opérationnelles du vendeur (à mettre en place AVANT la première vente)

1. **LIA (analyse d'intérêt légitime) écrite** + très probablement une **AIPD** (profilage systématique à grande échelle de foyers). Templates CNIL disponibles ; un LLM peut drafter, un avocat valide.
2. **Registre des traitements (art. 30)** : trois fiches — constitution/enrichissement, cession, gestion des oppositions. (Pas de déclaration préalable CNIL : ça n'existe plus depuis 2018.)
3. **Politique de confidentialité publique** (site web une page) décrivant le traitement, les sources, les catégories de destinataires, les droits.
4. **Notice art. 14 pour l'acheteur** : document d'une page que l'acheteur doit inclure dans son **premier courrier** à chaque adresse — identité du responsable, sources ("données publiques IGN/cadastre/BAN"), finalité, droits, et **comment s'opposer en une étape gratuite** (adresse postale + email + page web d'opposition). Fournie avec chaque fichier vendu, obligation contractuelle de l'utiliser.
5. **Machinerie d'opposition** : canal simple (email + formulaire + courrier), traitement ≤ 1 mois, ajout à `optout.csv`, et **propagation aux acheteurs passés** (le registre des ventes `sales/registre.csv` sert à ça).
6. **Durée de conservation** : standard CNIL prospects = 3 ans. Pour une base d'attributs du bien, documenter une politique de rafraîchissement par millésime (chaque nouvelle version des données sources remplace l'ancienne ; pas de conservation d'historiques par adresse au-delà du nécessaire au diff "nouvelles piscines").
7. **Contrat de licence** relu par un avocat (~300–500 €) incluant : périmètre, exclusivité, interdiction de revente, usage courrier postal uniquement, obligation d'inclure la notice art. 14, engagement de répercuter les oppositions.
8. **Avis juridique pré-lancement** recommandé (avocat data, 1 consultation) : le point à faire valider est la LIA face au critère des attentes raisonnables. Budget ~500–1 000 €. Compte tenu du climat d'enforcement (priorité CNIL prospection depuis 2022), c'est une assurance rationnelle, pas du luxe.

## 6. Checklist de conformité pré-vente (bloquante)

- [ ] LIA rédigée et archivée
- [ ] AIPD rédigée (ou décision motivée qu'elle n'est pas requise — improbable)
- [ ] Registre des traitements (3 fiches)
- [ ] Politique de confidentialité en ligne
- [ ] Canal d'opposition opérationnel (email + formulaire + adresse postale) et testé
- [ ] Filtre opt-out actif dans le pipeline d'export (testé avec une adresse factice)
- [ ] Notice art. 14 rédigée, jointe au template de livraison
- [ ] Contrat de licence validé par avocat
- [ ] Mention de source/millésime automatique dans les exports (vérifiée)
- [ ] Avis avocat data sur la LIA obtenu

## 7. Argumentaire client (objection « c'est légal ? »)

> « Le fichier est construit uniquement à partir de données publiques officielles (IGN, cadastre, Base Adresse Nationale) sous licence ouverte qui en autorise l'usage commercial. Il ne contient aucun nom, aucun téléphone, aucun email — uniquement des adresses et des caractéristiques du bien. La prospection par courrier postal est licite sans consentement préalable, c'est la position publique de la CNIL. Je vous livre avec le fichier un dossier de provenance et la notice d'information à joindre à votre premier courrier : vous êtes couvert, et c'est plus que ce que vous donnent la plupart des vendeurs de fichiers. »

## Sources principales

- CNIL — prospection par courrier postal : cnil.fr/fr/la-prospection-commerciale-par-courrier-postal
- CNIL — vente de fichiers clients : cnil.fr/fr/vente-de-fichiers-clients-la-cnil-rappelle-les-regles
- CNIL — intérêt légitime & moissonnage (2025) : cnil.fr/fr/focus-interet-legitime-collecte-par-moissonnage
- Sanctions : NESTOR (2020, 20 k€), ACCOR (2022, 600 k€), Hubside.Store (2024, 525 k€), Solocal Marketing Services (2025, 900 k€)
- Licence Ouverte 2.0 : github.com/etalab/licence-ouverte
- Foncier innovant DGFiP : impots.gouv.fr/actualite/generalisation-du-foncier-innovant
