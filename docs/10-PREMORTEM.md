# Pre-mortem — « Juillet 2027 : le projet est mort. Pourquoi ? »

> **Méthode (2026-07-08)** : deux analyses indépendantes à regard neuf, sans le biais du
> projet — un profil « investisseur sceptique + concurrent copieur », un profil « avocat
> RGPD façon contrôleur CNIL + directeur des opérations data B2B ». Ce doc est la synthèse
> convergente, classée par probabilité × impact, avec l'état de chaque patch.
> **À relire avant chaque décision d'investir du temps dans du code.**

## Le verdict, en une phrase

Les deux regards, partis d'angles opposés, arrivent au même diagnostic : *si ce projet meurt,
ce ne sera ni d'une faille technique ni d'une faille juridique de conception — ce sera d'une
**inversion de séquence** : un repo impeccable, un département jamais téléchargé, une LIA
jamais rédigée, et dix coups de fil jamais passés.*

## Les risques majeurs et leur état

| # | Risque | P×I | Patch | État |
|---|---|---|---|---|
| 1 | **Évitement commercial** : le solo technique code au lieu d'appeler ; phases A/C/D vides pendant que P2 avance | ☠☠☠ | Pré-vente AVANT la base : 5 appels pisciniers avec le pitch, objectif « oui, à 800 € je prends ». 3 h, 0 €. + kill-switch calendaire (voir §Règles) | **→ HUMAIN, cette semaine** (roadmap D0) |
| 2 | **Le prix ne tient pas** : une adresse sans contact n'est exploitable qu'en courrier/boîtage ; budget marketing d'une TPE artisanale = 0–3 k€/an ; prix psychologique réel possible : 150–300 € | ☠☠☠ | Tester le prix par téléphone avant de finir la base (= risque 1). Préparer l'offre « fichier + mailing clé en main » via routeur postal (transforme la donnée en campagne, triple le panier) | **→ HUMAIN** (D0) ; offre mailing à drafter `[OPUS]` |
| 3 | **Séquence juridique inversée** : LIA/AIPD/registre spécifiés mais non rédigés ; en contrôle, sans LIA archivée la base légale tombe (art. 6.1.f) et l'AIPD manquante (art. 35) est le grief gratuit | ☠☠☠ | Rédiger LIA + AIPD + registre MAINTENANT (templates CNIL) ; avis avocat (500–1 000 €) lancé avant B5, pas avant la vente | **→ `[OPUS]` drafts + HUMAIN avocat** (C2/C3 avancées) |
| 4 | **Art. 14 sur le stock invendu** : 95 % de la base ne sera jamais mailée donc jamais informée ; l'exemption 14.5.b exige des mesures compensatoires PUBLIQUES | ☠☠ | Plaider 14.5.b proprement dans la LIA : politique de confidentialité publique + encart presse locale au lancement + formulaire d'opposition en ligne AVANT tout courrier | **→ `[OPUS]`** (intégrer à C2) |
| 5 | **Le client vous coule** (responsabilité en chaîne) : le piscinier croise avec un annuaire inversé, spamme, oublie la notice → la plainte remonte au fournisseur | ☠☠ | 4 clauses contrat : interdictions explicites (croisement nominatif, email/SMS), remise de notice y compris porte-à-porte, clause résolutoire, certification annuelle d'usage. + politique précision/remède (remplacement des lignes fausses sous 90 j) | **→ `[OPUS]` draft, HUMAIN avocat** (C3) |
| 6 | **Démo ratée sur la JOINTURE, pas la détection** : l'adresse BAN qui pointe le mauvais pavillon devant le prospect | ☠☠ | Extraits de démo = confiance HAUTE uniquement | **✅ PATCHÉ** (`40_export_client.py --demo`) |
| 7 | **Abonnement fraîcheur physiquement impossible** : BD ORTHO rafraîchie ~tous les 3 ans, pas annuellement — la LTV du modèle reposait sur une sur-promesse (violation du garde-fou n°7 par nos propres docs) | ☠☠ | Offre alignée sur le rythme réel (« à chaque millésime IGN ») + veille SITADEL (permis de construire, mensuel, gratuit) pour les piscines neuves entre millésimes | **✅ PATCHÉ** (docs 00 + 02) ; vérifier date du prochain survol 49 → deepsearch |
| 8 | **Tri visuel qui explose à l'échelle** : si le ratio candidats/vraies piscines terrain dépasse ~4:1, l'option B ne tient pas le département (45–85 h de clic) | ☠☠ | Mesurer le ratio sur la 1re commune réelle AVANT toute industrialisation (B2-terrain) ; la décision A/B existe déjà — la respecter froidement | **→ mesure `[OPUS]`** (B2-terrain) |
| 9 | **Incendie médiatique « fichage des piscines »** post-affaire fisc : un article de PQR = mort commerciale sans sanction | ☠☠ | « Pack incident » écrit à froid : Q&A presse 1 page + procédure réclamation/opposition testée avec adresse factice | **→ `[OPUS]`** (nouvelle tâche C5) |
| 10 | **Saisonnalité inversée** : un piscinier ne décroche pas d'avril à septembre ; il achète d'octobre à février | ☠ | Caler les RDV sur sept.–févr. ; l'été = préparation (B5, C1-C4, POC gratuits « pour la rentrée ») | **✅ intégré** au playbook de séquence |
| 11 | **Marché 49 trop petit** : 20–50 acheteurs solvables, TAM réaliste année 1 : 10–25 k€ max | ☠ | Traiter le 49 comme un test de script de vente ; réplication 44/85/37 + verticales dès 5 ventes, pas « après » | **✅ consigné** (doc 09 §5 moats) |

## Ce que dirait un concurrent (à ne jamais oublier)

- Copier ce business après avoir vu la démo : **2-4 semaines, < 500 €** avec les mêmes outils IA.
  Le code et les tests ne le ralentissent pas d'une heure. La seule chose qui le décourage
  vraiment : **un marché local déjà verrouillé par exclusivités** et un gâteau trop petit pour
  se lever le matin. Conclusion déjà actée (doc 09 §5) : le moat, c'est la vitesse de signature.
- Il vendrait à 90 % de précision, moitié prix, et le prospect ne verrait pas la différence
  en RDV. Notre parade : l'exclusivité et la politique de remplacement, pas la sur-qualité.

## Les 3 hypothèses les plus dangereuses (aucune n'est testée à ce jour)

1. « Un piscinier paiera 500–1 500 € une liste d'adresses sans contact. » — testable en
   une semaine au téléphone, sans base.
2. « L'option B tient l'échelle départementale à ≥ 95 % de précision. » — testable sur UNE
   commune réelle (ratio candidats/piscines OSM).
3. « La mise à jour est vendable en abonnement. » — dépend de la date du prochain millésime
   BD ORTHO 49, jamais vérifiée (→ deepsearch en cours).

## Règles de séquence (adoptées suite au pre-mortem — priment sur l'envie de coder)

1. **D0 avant tout** : 5 appels de pré-vente avant de télécharger la moindre dalle. Le script
   d'appel teste le prix ET l'offre mailing clé en main.
2. **Kill-switch calendaire** : si au **15/10/2026** il n'y a ni LIA validée ni 5 RDV bookés,
   **gel total du code** jusqu'à correction. (Le critère Go/No-Go « 10 RDV / 2 ventes » de
   doc 09 §4 reste en vigueur ensuite.)
3. Interdiction d'écrire du code non bloquant pour la phase D tant que D3 (RDV de preuve)
   n'a pas eu lieu. Les sessions LLM qui reçoivent une demande contraire doivent le signaler
   (même mécanisme que les garde-fous de CLAUDE.md).
4. Chaque réclamation client « cette adresse est fausse » entre dans `data/validation/` comme
   étiquette négative : c'est un actif (vérité terrain), pas un incident.

## Sur/sous-investissement (auto-critique assumée)

Le pre-mortem pointe que ~80 % de l'effort à ce jour (architecture multi-produits, moteur
solaire, 45 tests) porte sur des choses qu'un client ne verra jamais — y compris `solaire.py`,
écrit en contradiction avec la règle « P2 après la première vente P1 ». Défense partielle :
ce travail est celui que l'humain ne peut pas faire lui-même et il de-risque les pivots ;
mais la critique est retenue — **plus aucun code produit avant D0/D3**. Le sous-investissement
(demande client, offre concurrente, millésimes, phase A) est intégralement de l'exécution
`[OPUS]` + humain : c'est là que va toute l'énergie maintenant.
