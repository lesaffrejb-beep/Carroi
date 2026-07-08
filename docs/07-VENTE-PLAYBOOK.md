# Playbook de vente

> À utiliser une fois la base validée (`06-QUALITE-VALIDATION.md` passé). Pas avant.

## 1. Construire la liste de prospects (clients B2B)

Sources pour identifier les acheteurs dans le 49 :
- Annuaire Pages Jaunes / Google Maps : "piscinier", "pisciniste", "entretien piscine", "abri piscine", "pergola", "store banne", "véranda" + villes du 49 (Angers, Cholet, Saumur, Segré…).
- Base SIRENE (open data, gratuite) : codes NAF `4399C` (travaux de maçonnerie — inclut pisciniers), `4332B` (menuiserie métallique — pergolas/vérandas), `4778C`, `9609Z`. Filtrer département 49, établissements actifs. → un script d'extraction SIRENE est prévu dans `pipeline/` (voir ROADMAP).
- Réseaux de franchises présents localement (Desjoyaux, Waterair, Mondial Piscine, Komilfo, Storistes de France…) : les franchisés locaux ont des budgets marketing.

Prioriser : entreprises avec site web actif et avis Google récents (= budget marketing, culture de l'acquisition).

## 2. Prise de contact

Canal : téléphone direct au gérant (TPE : le gérant décroche), ou passage physique. L'email froid marche mal sur cette cible.

Script d'ouverture (piscines) :
> « Bonjour, je suis [prénom], j'ai constitué la carte de toutes les piscines privées du Maine-et-Loire à partir de données géographiques officielles. Autour de [ville du prospect], dans un rayon de 30 km, j'en ai [N]. Je peux passer 15 minutes vous montrer — vous vérifiez vous-même des adresses au hasard, et si c'est bidon vous me mettez dehors. »

Points clés :
- Donner le **chiffre exact** de leur zone dès le premier appel (le générer avant d'appeler : `pipeline/` produit l'extrait rayon 30 km en une commande).
- Ne rien envoyer par écrit avant le RDV (pas d'échantillon par email : ça se copie).

## 3. Le RDV de preuve (protocole détaillé)

Matériel : ordinateur portable, extrait local imprimé ET numérique, connexion (partage 4G en secours), Géoportail IGN en favori.

Déroulé (20 min max) :
1. **2 min** — cadrer : « Je ne vends pas un logiciel, je vends une liste d'adresses. Voilà comment je l'ai construite » (données IGN/cadastre officielles, en une phrase).
2. **5 min** — la preuve : le prospect choisit 5 numéros de ligne au hasard dans la liste. Pour chaque adresse : Géoportail → vue aérienne → piscine visible. Annoncer le taux de précision mesuré.
3. **3 min** — la valeur : « Un client piscine vaut combien pour vous en LTV ? » (entretien annuel récurrent : souvent 500–1 500 €/an). « Si cette liste vous apporte 3 clients, elle est remboursée combien de fois ? »
4. **5 min** — l'offre : extrait 30 km non-exclusif à [prix], ou exclusivité de zone à [prix ×3–5]. Mentionner qu'on voit d'autres pisciniers de la zone cette semaine (vrai → urgence naturelle de l'exclusivité).
5. **Closing** — paiement à la livraison du fichier. Livrer un CSV + un PDF cartographique (voir `pipeline/` : export commercial).

Objections types :
- *« Je peux le faire moi-même sur Google Maps »* → « Bien sûr, à raison d'une commune par jour. Moi c'est déjà fait, vérifié, avec les adresses postales exactes prêtes pour un mailing. Votre temps de gérant vaut plus que ça. »
- *« C'est légal ? »* → réponse préparée dans `03-LEGAL-RGPD.md` §"Argumentaire client". En résumé : adresses sans noms, prospection courrier postal = licite, et le client reçoit avec le fichier une notice de conformité qui lui explique ses obligations.
- *« Les données datent de quand ? »* → donner le millésime exact des données sources (tracé dans chaque export) et vendre l'abonnement fraîcheur.

## 4. Contrat & livraison

- Contrat de licence de données simple (1–2 pages) : périmètre géographique, exclusivité oui/non + durée, interdiction de revente/partage du fichier, millésime, taux de précision annoncé, pas de garantie d'exhaustivité. **Un template de contrat doit être relu par un avocat avant la première vente** (coût ~200–400 €, non négociable — voir garde-fous).
- Chaque fichier livré est **tatoué** : 2–3 adresses-témoins contrôlées (adresses réelles avec piscine, mais dont la combinaison exacte de formatage identifie l'acheteur) pour détecter une revente sauvage. Le mécanisme est décrit dans `06-QUALITE-VALIDATION.md`.
- Livrer avec le fichier : notice RGPD acheteur (une page, voir `03-LEGAL-RGPD.md`) — c'est un argument de vente ("je vous mets en conformité") autant qu'une protection.

## 5. Cycle d'expansion

1. 4–5 POC gratuits ou à prix cassé contre témoignage → références locales.
2. Vente non-exclusive en volume sur le 49.
3. Une fois 3–4 clients par métier : proposer l'exclusivité au plus gros (racheter la zone).
4. Répliquer le pipeline sur les départements voisins (44, 85, 37, 72) — le code est paramétré par numéro de département.
5. Produit 2 (terrasses/pergolas) lancé auprès des clients existants d'abord.
