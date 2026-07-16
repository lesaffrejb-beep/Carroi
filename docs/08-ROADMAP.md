# Roadmap & journal de bord

> **Ce fichier est le journal du projet.** Chaque session LLM qui termine une tâche met à jour le statut, la date, et surtout ce qui a été **appris/mesuré** (les chiffres réels valent plus que le plan). La session suivante ne sait que ce qui est écrit ici.

## ⚡ PROCHAINE SESSION : COMMENCER ICI (état au 2026-07-12, session Opus — outils de tri + partage)

**Où on en est en une phrase** : le moteur est codé et testé (**193+ tests verts**),
Phase A (chaîne dev OSM, 2 communes) et Phase B jusqu'à B2-terrain sont FAITES,
et **tout l'outillage de tri humain est prêt et partageable sans installation**.
Détection calibrée sur Bouchemaine (49035) : **977 candidats, ratio 3,4:1, rappel
~53 %** vs OSM (BD ORTHO 2022 réelle, 61 Go sur disque externe NOIR). Deux outils de
tri : **`16_tri_visuel.py`** (tri d'existence O/N/U, planche HTML autonome gamifiée —
bandeau question/compteur/progression, règles intégrées, undo Z/←, persistance
localStorage, export `decisions.csv`) et **`17_verification_adresse.py`** (2e outil :
vérification humaine de l'adresse assignée par clic sur la carte des adresses BAN
alentour, pour les cas de confiance non-haute — 7 cas détectés sur le dev Bouchemaine).
**Verrou parcellaire** : la « haute confiance » exige l'adresse DANS la parcelle de la
piscine (colonne `adresse_dans_parcelle`) ; nearest hors-parcelle → basse, jamais
vendue. Badge « cadastré » (PCI SYM=65) sur les vignettes (99/977 corroborés). **Partage
sans install** : dossier `handoff/` (planche autonome ~27 Mo, `soumettre_tri.sh`,
`appliquer_decisions_recues.py`), `bootstrap.sh` (install one-shot) et `ONBOARDING.md`
(parcours A trier / parcours B contribuer). Intégrité verrouillée : empreinte `hash12`
des candidats dans la planche → nom d'export `decisions_{dept}_{commune}_{hash12}.csv`,
refus à la fusion si l'empreinte ne colle pas (sauf `--force`), clé localStorage par
planche, fusion par timestamp du nom de fichier, flag `--embarquer` pour régénérer la
planche autonome. **Extraction ciblée** de dalles BD ORTHO depuis les archives 7z :
`12_extraire_dalles_ortho.py` (par `--commune`/`--bbox`, index `dalles.shp` embarqué).

**Nouveau (2026-07-12, session Fable — autopsie du rappel)** : le plafond de rappel
(~53-55 % vs OSM) est ÉLUCIDÉ — 80 % des manquées sont des piscines **couvertes/vides/
postérieures à 2022**, invisibles pour tout algorithme sur cette image (rappel réel sur
les visibles : **85,8 %**). **B4 volet rappel tranché : pas de modèle IA** ; le levier
est la fusion source cadastre SYM=65 (rappel potentiel 76,6 %, tâche 12, post-D0).
Doctrine `16` §5 amendée en conséquence. 10bis (perfs) clos : mesuré non bloquant.

**Nouveau (2026-07-12 soir, session Fable — arbitrage open source) : DÉCOUVERTE CoSIA.**
L'IGN publie la détection de piscines par IA (classe « Piscine », vecteur, Licence
Ouverte, D49 en millésimes 2020/2022/2025 — fiche `02`, arbitrage complet `15` §4).
Mesuré sur Bouchemaine : **rappel 88,1 % vs OSM, 68 % des piscines couvertes vues,
CoSIA ∪ SYM=65 = 89,2 % sans notre détecteur**. Décisions : CoSIA = source principale
de candidats (tâche 12 amendée, doctrine `16` §5) ; option A (modèle maison) enterrée
définitivement ; samgeo/Label Studio/Download-BDOrtho21 écartés (`15` §4). **Tâche 13
[OPUS] prête : valider CoSIA à l'échelle du département (mesures seules, pas de code).**
⚠ Diff CoSIA 2022→2025 piégé (changement de modèle entre millésimes) : E2 exige une
validation visuelle par ligne. Archives déjà sur NOIR (`COSIA_D049/`).

**Nouveau (2026-07-16, session Fable — mode solo + premier lot de tri)** : la planche
de tri a un **mode « une par une »** (défaut) : la vignette courante s'affiche seule,
à taille et position fixes au centre de l'écran — le regard ne bouge plus, O/N/U
enchaîne. Bascule « Voir la galerie » dans le bandeau, préférence mémorisée par
planche, mêmes raccourcis + gros boutons cliquables. `handoff/tri_bouchemaine_49035.html`
régénéré (même empreinte `2d460d3dc74e` : les décisions localStorage en cours sont
conservées). **TRI BOUCHEMAINE TERMINÉ ET APPLIQUÉ : 977/977 décisions JB**
(deux lots dans `handoff/decisions_recus/`, fusion par récence — 6 « oui » du lot
partiel corrigés en « non » par le lot final). Résultat : **246 oui, 731 non,
0 incertain → `piscines_detectees_49.parquet` (methode=valide_humain)**. Précision
brute du détecteur : 25 % (attendu, ratio 3,4:1 assumé). Bilan `18_bilan_tri`
(`data/validation/bilan_tri_49_49035.md` + dataset labels) : calibration nette
(score 0.80-1.00 → 98 % oui ; 0.55-0.60 → 5 %), badge cadastre confirmé
(**corroborés PCI = 98 % oui** vs 17 % sinon), surfaces 60+ m² presque jamais
piscine (2 %). Suggestion à valider (pas appliquée) : remonter `score_min`
au-dessus de 0,60-0,65 pour réduire le bruit à trier.

**Nouveau (2026-07-16 soir, même session — chaîne aval déroulée + bug de livraison
corrigé)** : `20_join` exécuté sur la base validée humain (246 → 236 adressées, dont
187 via cad_parcelles, 2 ambiguës) puis `30_score` → **`data/final/
piscines_qualifiees_49.parquet` : 230 adresses (162 haute / 36 moyenne / 32 basse)**.
**BUG CORRIGÉ dans `30_score_qualite.py`** : `set_geometry()` sans `.rename("geometry")`
écrasait la colonne `id_ban` par les points adresse ET laissait le POLYGONE piscine
dans le fichier final (violation minimisation) — corrigé, fonction extraite
(`remplacer_geometrie_par_adresse`), test de régression dans `test_garde_fous.py`
(244 tests verts), base régénérée saine. Page de vérification d'adresse générée pour
les **68 cas non-haute** : `handoff/verif_adresse_bouchemaine_49035.html` (ortho
communale, clic sur la maison, export concordance.csv).

**Nouveau (2026-07-16 nuit — vérification d'adresses TERMINÉE et appliquée)** :
JB a vérifié les **69 cas non-haute** avec l'outil 17 refondu (ortho pleine vue,
clavier AZERTY main gauche Q/D/S/Z/A + rangée des chiffres, auto-avance, choix
« aucune », protocole en aveugle réellement respecté). Verdicts : **51 confirmées,
17 corrigées, 1 sans adresse valable**. Nouveau script **`21_appliquer_concordance.py`**
(verdicts → base adressée ; verif_humaine=True ; corrections avec attributs BAN ;
'aucune' → adresse retirée) + `30_score` : une adresse vérifiée humain prime sur
les heuristiques → **base finale : 228 adresses, 100 % confiance haute**
(existence validée humain + adresse confirmée ou corrigée humain sur tous les cas
douteux). CSV archivés dans `handoff/concordance_recus/`.

**⚡ PROCHAINE ACTION** : protocole précision `06` §2 (échantillon aléatoire, borne
basse de Wilson) pour le chiffre affichable en démo, puis kit de vente — et toujours
**D0 avant tout code : aucun prospect appelé, l'inversion de séquence reste LE
risque n°1. La base est prête, l'excuse « le produit n'est pas fini » ne tient plus.** Soi-même (ouvrir `handoff/tri_bouchemaine_49035.html`
ou générer la planche via `16_tri_visuel.py`) OU faire trier par un ami/bénévole via
`handoff/` (voir `ONBOARDING.md` parcours A). Puis **appliquer les décisions**
(`appliquer_decisions_recues.py` → `16 --apply`) → **mesurer la précision réelle**
(borne basse de Wilson, `06` §2) → débloquer **B4** (décision A/B modèle) et **B5**
(industrialisation département). AUCUN prospect appelé — l'inversion de séquence (`10`)
reste LE risque n°1 : la priorité absolue n'est toujours pas le code, c'est D0.

**⚠ Incident du 2026-07-11 (17h30-17h45)** : la quasi-totalité de l'arbre de travail a été
supprimée pendant une session (cause exacte inconnue — concomitant avec le `git init` +
fetch du dépôt `github.com/lesaffrejb-beep/maps`, probablement une étape de re-clonage
restée inachevée). Restauré depuis `origin/main` (eafbbcf, PR #11) + fichiers survivants
(D1, 90_backup, deepsearchs). Perdu et NON récupérable : les 3 correctifs d'audit
garde-fous + 6 tests (jamais poussés — refaire, tâche 5bis) et la variante locale des
tâches 6/8 (les versions cloud PR #10/#11, fonctionnellement équivalentes, font foi).
**Leçon : commit + push après CHAQUE tâche, sans exception.**

**File d'attente — chaque tâche est autonome et cadrée ; une session Opus prend LA PREMIÈRE
non cochée de son niveau, la fait EN ENTIER, consigne, commit/push, et s'arrête. Ne pas
improviser au-delà du cadre ; si quelque chose bloque ou surprend, le consigner ici et
s'arrêter proprement.**

1. `[HUMAIN — en cours, RDV imminents]` **D0** : appels de pré-vente avec le kit `11`,
   réponses dans `sales/prospection_d0.csv`, puis dérouler l'arbre `12`.
   Munitions nouvelles (deepsearch ⑦, `docs/deepsearch/DS5`) : brokers = 0,15-0,80 €/contact
   en LOCATION + minimums 350-650 € + données déclaratives périmées ; leads = 30-150 €/pièce
   revendus à 3-5 concurrents. Et si le millésime BD ORTHO 2025 se confirme (B1), le diff
   2022→2025 rend les « nouvelles piscines » vendables dès le lancement.

2. `[OPUS — ✅ FAIT 2026-07-09, mergé PR #8]` **C2 : drafts légaux.**
   Livrables : `docs/legal/LIA.md`, `docs/legal/AIPD.md`, `docs/legal/registre_art30.md`,
   `docs/legal/politique_confidentialite.md`, `docs/templates/notice_art14.txt` complétée.
   → **Fait** : 5 fichiers créés, chacun marqué DRAFT, art. 14.5.b traité dans LIA §4.4 +
   AIPD §4, les 4 clauses `10` §5 intégrées en LIA §4.5 / registre fiche n°2. **Bloqueurs
   🧑 à renseigner avant usage réel** (placeholders `[...]` dans les 5 docs) : nom commercial
   (`16` §6.2), forme juridique, adresse postale, email `opposition@<domaine>`, URL du
   formulaire (C4). **Reste 🧑** : avis avocat data sur la LIA (bloquant lancement, `03` §5.8).

3. `[OPUS — ✅ FAIT 2026-07-09, mergé PR #9]` **C5 : pack incident.** →
   `docs/legal/qa_presse.md` + `docs/legal/procedure_reclamation.md` (≤ 1 page chacun ;
   schéma `reclamations.csv` défini ; porte-parole/URL en placeholders 🧑).

4. `[OPUS — ✅ FAIT 2026-07-11]` **D1 : liste de prospects.** → Cœur pur
   `pipeline/src/prospects.py` + CLI `50_prospects_sirene.py` + `tests/test_prospects.py`
   (9 verts). Source = API publique **« Recherche d'entreprises » (DINUM)** (SIRENE sans
   clé, NAF pointés `43.99C`). Méthode **hybride NAF + mot-clé** (fidèle à `07` §1 — les
   pisciniers se dispersent hors des 4 NAF : trouvés aussi en 43.99D, 41.20B, 70.10Z,
   47.52A/B, 81.30Z via `q=piscine`). **969 prospects** dans `sales/prospects_49.csv`
   (hors git), dont **43 « haute »** (pisciniers avérés, 142 communes). Garde-fous :
   `dirigeants` jamais lu ; non-diffusibles écartés ; 451 EI identifiables par un nom de
   personne écartés. Colonnes tel/site vides (absentes de SIRENE). **Reste 🧑** : triage
   manuel du haut de liste (site web actif + avis Google, `07` §12) avant les appels D0/D3.
   ⚠ Ces fichiers ont survécu à l'incident mais ne sont PAS commités → commit/push
   en tête de la prochaine session Opus.

5. `[OPUS — ✅ FAIT 2026-07-11/12 — voir Phases A & B et le journal]`
   **A1-A4 puis B1 + B2-terrain.** Ordre strict : A1 (10_download ; si le miroir BD TOPO
   échoue → --bdtopo-url), A2 (OSM 2 communes), A3 (20→35 en --dev ; consigner %
   cad_parcelles vs nearest), **A3bis (nouveau, deepsearch ③)** : extraire les piscines
   PCI Édigéo `SYM=65` (couche tsurf) sur les 2 communes tests et consigner le taux de
   recouvrement avec OSM — si > 50 %, brancher SYM=65 comme couche de corroboration au
   score (doctrine `16` : corrobore, ne crée JAMAIS de ligne), A4 (contrôle visuel 30
   lignes Géoportail, consigner le taux), B1 (dalles ortho 1 commune — URLs/nommage/7z
   dans `docs/02` §BD ORTHO ; consigner le MILLÉSIME RÉEL constaté [2022 ou 2025 ?] et
   l'ordre des bandes IRC vérifié), B2-terrain (15_detect sur la commune ; consigner ratio
   candidats/piscines-OSM, précision, rappel ; calibrer les seuils `detection:` de
   config.yaml en consignant AVANT/APRÈS chaque seuil ; si les étangs/plans d'eau polluent,
   brancher la couche hydro BD TOPO en masque — DS4). Fini = tableau de mesures ci-dessous
   rempli. NE PAS : lancer le département entier ; modifier detection.py/solaire.py (seuils
   config UNIQUEMENT — si ça ne suffit pas, consigner et s'arrêter : déclencheur [FABLE]).

5bis. `[OPUS — ✅ FAIT 2026-07-11]` **Refait les 3 correctifs d'audit garde-fous perdus
   dans l'incident** : (1) `common.apply_optout` : double clé id_ban + adresse normalisée
   (`common.normalise_adresse`, pure/testable), refus bruyant si ligne d'opposition sans
   aucune clé ou si la base n'a pas de colonne adresse ; (2) `40_export.exiger_version_tracable`
   REFUSE tout export non-demo si `pipeline_version()` == "unknown" (démo autorisée) ;
   (3) `tatouer()` retourne `(df, temoins)` (≤ 5 id_ban marqués) + colonnes
   `version_pipeline` et `temoins_tatouage` au registre des ventes. **+6 tests**
   (test_garde_fous, dont opposition art. 11 par adresse seule). **124 tests verts**,
   commit/push faits.

6. `[✅ FAIT 2026-07-11, mergé PR #10 — implémentation cloud]` **Leçons de l'état de
   l'art** (doc 15 §2) : (a) tri des vignettes par incertitude (`cle_incertitude`, 16_tri) ;
   (b) précision annoncée = borne basse de Wilson 95 % (`common.borne_basse_wilson`),
   protocole `06` §2 récrit, +7 tests dans test_garde_fous. (La variante locale
   `qualite.py`/test_tri/test_qualite décrite avant l'incident est perdue et caduque —
   la version PR #10 fait foi.) Conséquence honnête inchangée : 97/100 → ~91,5 % annoncés
   (ne passe pas 95 %) ; agrandir n est le levier.

7. `[OPUS — ✅ FAIT 2026-07-11]` **Généralisation cosmétique** (doc 09 §6) : 20_join
   `--source` (alias rétro-compatible, réconciliation dans la fonction pure
   `resoudre_source` — refus bruyant si les deux flags divergent), 30_score `--produit`
   (lit `cfg[produit]`, fichiers `{produit}_…`, défaut piscines, comportement piscines
   strictement inchangé). +12 tests (`test_cli_flags.py`), **140 tests verts**.

8. `[✅ FAIT 2026-07-11 — (a)+(b) mergés PR #11, (c) restauré]` **Décisions
   opérationnelles → code** (`16-DECISIONS-OPERATIONNELLES.md`) : (a) 40_export produit
   un .xlsx client à côté du CSV (`ecrire_xlsx`, en-tête figé A2, filtres, largeurs ;
   openpyxl aux requirements) ; (b) 30_score : copie datée
   `data/final/archive/{produit}_{dept}_{AAAA-MM-JJ}.parquet` (`archiver_copie_datee`) ;
   (c) `90_backup.py` (tar de final/exports/sales/optout/validation, chiffrement age|gpg
   clé publique, rclone, idempotent, JAMAIS raw/interim) + clé `backup:` de config.yaml
   (réajoutée post-incident, placeholders 🧑). ⚠ 90_backup.py non commité (survivant de
   l'incident) → commit/push prochaine session. **🧑 avant usage de (c)** : installer
   `age` (ou gpg) + `rclone`, créer un remote rclone (Hetzner Storage Box, `16` §2),
   renseigner `config.yaml` §backup.

9. `[OPUS — après le premier re-run de détection sur un nouveau millésime, OU dès que
   B2-terrain tourne si le millésime 2025 est confirmé (diff 2022→2025, voir docs/02)]`
   **45_diff_millesimes.py** : CLI mince autour de `millesimes.py` (cœur fait et testé).
   Args : --avant X.parquet --apres Y.parquet [--tolerance-m 8]. Sorties :
   `{produit}_nouvelles_{dept}.parquet` (contrat couche 1 intact) + log des
   conservées/disparues + REFUS d'écrire si > 50 % de « nouvelles » (recalage suspect).
   NE PAS : toucher à millesimes.py ; vendre les « disparues ».

9bis. `[OPUS — avec le kit de vente, pas de code]` **Grille de lecture client A+/A/B**
   (idée 🧑 2026-07-11) : traduire nos niveaux internes en langage acheteur —
   **A+** = existence validée par un humain (100 % des lignes vendues, par construction) ×
   confiance d'ADRESSE **A** (haute : adresse corroborée dans la parcelle, ~94 % mesuré) /
   **B** (moyenne) ; « basse » et « incertain » ne sont JAMAIS vendus. Usage client à
   documenter dans `07`/`11` : porte-à-porte sur A, courrier sur B, coût d'acquisition
   pondéré par le risque de faux positif. Chaque niveau annoncé avec sa précision MESURÉE
   (borne basse de Wilson, `06` §2) — jamais de % inventé.

10. `[OPUS — APRÈS D0 uniquement (règle « pas de code produit avant »)]` **Ingestion
   SITADEL** (spec complète dans `docs/02` §SITADEL, issue de la deepsearch ③) : filtres
   ANN_COD_ANNEXE=1 × particulier × OCTROI, jointure parcelle → PCI → BAN via 20_join,
   sortie compatible couche 1. Auditer les noms de colonnes réels AVANT de coder
   (transition SITADEL 3). C'est le moteur de l'« abonnement fraîcheur » (grille `16`).

10bis. `[✅ CLOS 2026-07-12 — MESURÉ NON BLOQUANT, ne pas « optimiser »]`
   **Les fragilités de scalabilité listées ici (audit 2026-07-12) ont été BANC-D'ESSAYÉES
   sur données réelles avant toute refonte — verdict : fausse alerte.** Run départemental
   complet simulé (43 095 polygones OSM région, parcelles/BAN/bâtiments du 49 entiers,
   machine de dev) : `joindre_parcelle` **0,6 s**, `joindre_adresse` + corroboration
   **1,1 s**, chargement parcelles 1,2 M lignes **1,0 s**, sindex **0,3 s** (le
   « ~5 min » du constat initial ne se reproduit pas). Les `.apply(axis=1)` row-wise
   ne portent que sur les lignes jointes — même ×10 candidats, on parle de secondes.
   **Décision : AUCUNE refonte. Ne pas dépenser de session là-dessus tant qu'un run B5
   réel n'a pas montré > 10 min sur un poste de travail.** (Leçon de méthode : mesurer
   avant d'optimiser — le constat initial était une lecture de code, pas une mesure.)

11. `[FABLE — seulement si déclenché]` : option A détection (déclencheur : B2-terrain
   plafonne < 95 % après calibration ; noter — doc 15 + DS5 : partir des poids
   `sp-swimming-pools` CC-BY-4.0 + annotation manuelle BD ORTHO ; JAMAIS AGPL/images
   Google ; l'option A améliore rappel et débit, PAS la précision finale, le tri humain
   reste) ; détecteur P3 pans de toiture (déclencheur : branche D de l'arbre `12`, ou
   5 ventes P1 — noter DS5 : les cadastres solaires publics du 49 sont consultation
   unitaire, pas de listes → P3 non menacé ; la couche Cerema « potentiel solaire »
   téléchargeable = intrant possible).

12. `[OPUS — APRÈS D0 (code produit), à brancher au moment de B5 — AMENDÉE 2026-07-12
   soir : CoSIA ajouté]` **Fusion de sources de candidats : CoSIA ∪ SYM=65 ∪ détection**
   (décisions B4 + arbitrage open source du 2026-07-12, doctrine `16` §5) : construire
   la couche 1 candidats comme l'UNION dédupliquée (appariement spatial < 5 m,
   priorité de géométrie : cosia > detection > cadastre) des trois sources, colonne
   `origine` ∈ {cosia, detection, cadastre} + colonnes booléennes de corroboration
   croisée. Tous les candidats passent le MÊME tri visuel humain (règle d'écran :
   « eau visible OU couverture/abri de piscine manifeste » = O) et le même verrou
   parcellaire. Filtre commercial ≥ 8 m² appliqué à toutes les sources. Effet mesuré
   (Bouchemaine, vs OSM) : détection seule 54,9 % → ∪ SYM=65 76,6 % → ∪ CoSIA **89,5 %**.
   NE PAS : vendre une ligne non validée par un humain sur photo ; toucher aux seuils
   de détection. Pré-requis : tâche 13 (mesure CoSIA département) + SYM=65 sur tout
   le 49 (A3bis ne l'a fait que sur les 2 communes tests).

13. `[OPUS — exécutable MAINTENANT : mesures uniquement, AUCUN code produit]`
   **CoSIA à l'échelle du département — valider avant de brancher.** Les archives sont
   déjà téléchargées (`/Volumes/NOIR 1/maps-bdortho/COSIA_D049/COSIA_D049_{2022,2025}.7z`,
   dalles GPKG 10 km, couche unique, colonnes `numero`/`classe`/`geometry`, L93 natif).
   Mode opératoire (reproduire la méthode de `data/validation/eval_cosia.py`) :
   (a) extraire les dalles 2022 du 49 entier, filtrer `classe='Piscine'` (where SQL au
   read_file, PAS de chargement complet), concaténer → consigner : total brut, total
   ≥ 8 m², par commune (top 20) ; (b) croiser avec `piscines_osm_dev.parquet` (7 269
   OSM dans le 49) : rappel CoSIA vs OSM au département (Bouchemaine a donné 88,1 % —
   si le chiffre départemental s'effondre < 75 %, s'arrêter et consigner) ; (c) refaire
   (a) sur 2025, consigner le delta global par classe (à Bouchemaine : -30 % de
   polygones toutes classes = changement de modèle, PAS la réalité) ; (d) échantillonner
   30 « nouvelles » (2025 sans 2022 à < 8 m, ≥ 8 m²) réparties sur 5+ communes,
   générer les vignettes ortho 2022 (12_extraire + code planche de l'autopsie) et
   compter à l'œil : vraie nouvelle / déjà là en 2022 (raté modèle 2022) / faux positif
   → ce taux décide si E2 « nouvelles piscines » est vendable dès maintenant. Consigner
   tout ici + artefacts dans `data/validation/`. NE PAS : modifier le pipeline,
   committer des données, dépasser ce cadre.

**Interdit tant que D0/D3 n'ont pas parlé : tout nouveau code produit** (`10` §Règles ;
dérogation moteur du 2026-07-08 close — le moteur est fini). La tâche 5bis (restauration
de garde-fous EXISTANTS) et la tâche 5 (runs sur données réelles, pas de nouveau code)
ne tombent pas sous cette interdiction.

**Deepsearchs** : ①②③④⑤⑦⑨⑩ **reçues le 2026-07-11**, rangées dans `docs/deepsearch/`
(synthèse + arbitrages en tête de chaque fiche), `13-DEEPSEARCH.md` supprimé. **Restent
à lancer par l'humain (prompts conservés ici)** :

> **⑥ Routeurs postaux — coût réel de l'offre « campagne clé en main » (branche B1 de `12`)** :
> Pour envoyer des campagnes de courrier adressé B2C en France (500 à 5 000 plis par
> campagne, format lettre ou carte postale) : quels prestataires/routeurs acceptent les
> petits volumes en 2026 (Merci Facteur pro, Maileva, Mediapost, imprimeurs-routeurs
> régionaux Pays de la Loire) ? Prix indicatif TOUT COMPRIS par pli (impression couleur +
> mise sous pli + affranchissement) aux volumes 500 / 2 000 / 5 000, délais, et minimum
> de commande. API disponible ?

> **⑧ Loi APER (ombrières de parkings) + données parkings/PLU — cible n°1 de `14`** :
> 1. Loi APER (10 mars 2023, art. 40) et décrets : obligations EXACTES d'équipement en
> ombrières PV des parkings extérieurs existants en 2026 — seuil (1 500 m² ? places ?),
> part à couvrir, échéances par taille, exemptions, sanctions ? Assouplissements/reports
> depuis 2023 ? 2. Parkings en open data : couche BD TOPO (thème, attributs de surface) ?
> Sinon OSM (amenity=parking, couverture France) ou autre source ouverte avec emprise ?
> 3. Géoportail de l'urbanisme : téléchargement en masse du zonage PLU (zones U/AU) d'un
> département (format, URL d'API/atom, licence) ?

## État au 2026-07-11 soir (session Fable — deepsearchs, incident, restauration)

**Deepsearchs ①②③④⑤⑦⑨⑩ reçues et arbitrées** (détail : `docs/deepsearch/README.md`).
Les arbitrages, en bref — **AUCUN pivot, 4 ajustements** :
1. **B1 débloqué** (①) : URLs/nommage/format BD ORTHO complets dans `docs/02`. Millésime 49
   = probablement 2025 (non confirmé — B1 tranche). Prochain survol 2028. Si 2025 confirmé :
   **diff 2022→2025 possible dès le lancement** → « nouvelles piscines » sans attendre 2028.
2. **SITADEL viable** (③) → l'« abonnement fraîcheur » 39-59 €/mois de `16` a sa recette
   technique (docs/02 §SITADEL) ; script = tâche 10, APRÈS D0. Bonus : **PCI Édigéo SYM=65**
   = couche piscines cadastrées, corroboration idéale (tâche 5/A3bis).
3. **P2 : biais crue 7 mars 2024 sur MNT/MNH** (②, plausible) + ZICAD → pièges consignés
   dans `05`. Pas bloquant (P2 est en phase 2), mais à vérifier au premier run P2.
4. **namR EN LIQUIDATION (vérifié : prononcée le 01/07/2026)** (⑨) → doc `15` corrigé :
   la thèse technique tient, le modèle « lac de données générique grands comptes » est
   mort ; notre modèle (activable, local, coûts fixes ~115 €/mois) est le contre-modèle
   exact. ④⑤⑦⑩ : confirmations (cadastres solaires = pas de concurrence sur les listes ;
   datasets : CC-BY-4.0 OK / AGPL et Google interdits ; chiffres brokers/leads pour le
   kit `11` ; pratiques pipelines = nos choix validés).

**Incident de perte de données** (17h30-17h45) : arbre de travail quasi intégralement
supprimé pendant la session (concomitant du `git init` + fetch de
`github.com/lesaffrejb-beep/maps` — vraisemblablement un re-clonage 🧑 inachevé ; cause
exacte non établie). Restauration : `git reset --hard origin/main` (eafbbcf) + survivants
non commités (prospects.py, 50_prospects_sirene.py, 90_backup.py, test_prospects.py,
sales/prospects_49.csv, docs/deepsearch/). Perdu définitivement : les 3 correctifs d'audit
+ 6 tests (→ tâche 5bis) et la variante locale des tâches 6/8 (versions cloud PR #10/#11
retenues). **118 tests verts** après restauration (`.venv/bin/python -m pytest`).

## État au 2026-07-11 (session Fable — audit des modules jamais audités)

> **✅ RÉSOLU 2026-07-11 (tâche 5bis) : les 3 correctifs de code décrits ci-dessous,
> perdus dans l'incident, ont été REFAITS et testés (124 tests verts, commit/push).
> Les constats (a)-(e) restent valables.**

Le journal du 2026-07-08 notait : « l'agent d'audit externe a été interrompu ; audit refait
à la main sur 10/16/20/25/30/35 ». Les modules restants (15, 40, common, contrat, detection,
geometrie, millesimes, solaire, terrasses) n'avaient JAMAIS été audités — dont toute la
chaîne des garde-fous légaux. Audit fait ; verdicts :

- **corrects tels quels** : solaire.py (formules d'azimut, pas diagonal `res/|drow|`, ordre
  de propagation — tout vérifié), geometrie.py (pile monotone correcte, reset par ligne),
  terrasses.py, detection.py, millesimes.py, 15_detect (partition des zones intérieures
  exacte pour chevauchement pair — 128 px l'est).
- **3 failles de garde-fous corrigées** (✅ REFAITES le 2026-07-11, tâche 5bis) :
  1. `apply_optout` ne matchait QUE sur id_ban → une opposition art. 11 « par adresse
     seule » (prévue par procedure_reclamation.md et C4) était silencieusement ignorée ;
     un id BAN changeant de millésime démariait l'opposition. Correctif : double clé
     id_ban + adresse normalisée ; refus bruyant si ligne d'opposition sans aucune clé
     ou si la base n'a pas de colonne adresse.
  2. `pipeline_version()` retournait « unknown » sans bloquer → garde-fou n°4 contournable.
     Correctif : 40_export REFUSE tout export non-demo si la version est inconnue.
  3. Le registre des ventes ne consignait ni adresses-témoins du tatouage ni version
     (exigés par le garde-fou n°5). Correctif : `tatouer()` retourne les témoins (≤ 5
     id_ban marqués), colonnes `version_pipeline` + `temoins_tatouage` au registre.
- **Constats non bloquants, consignés sans correction** (à reprendre si besoin) :
  (a) ~~le dossier de travail n'est PAS un dépôt git~~ → RÉSOLU le 2026-07-11 (remote
  `lesaffrejb-beep/maps`, origin/main restauré) — le refus d'export sans version git est
  opérationnel (5bis refaite) ; (b) detection/forme garde des candidats
  jusqu'à 400 m² dont les formes allongées (> 25,6 m) peuvent dépasser le chevauchement de
  fenêtre — auto-réparé par fusionner_adjacentes dans la quasi-totalité des cas, à
  surveiller en B2-terrain ; (c) millesimes.py : `set(ja)` reconstruit par élément (perf,
  cosmétique) ; (d) contrat.py : le motif interdit « age » matche en sous-chaîne (une
  future colonne `ombrage`/`village` casserait le pipeline — comportement voulu, juste le
  savoir) ; (e) DeprecationWarning numpy 2.5 dans 15_detect (rasterio `.read`), sans effet.

## État au 2026-07-07 (session fondation)

Fait par la session d'architecture :
- Recherche approfondie et verdicts : sources de données (`02`), Google Solar API **écarté** pour cause de CGU (`05`), cadre légal RGPD complet (`03`).
- Toute la documentation structurante (docs 00→08) + garde-fous dans `CLAUDE.md`.
- Code écrit (non exécuté sur données réelles — à tester au premier run) : `common.py`, `10_download.py`, `20_join_piscines_adresses.py`, `30_score_qualite.py`, `35_stats_prospection.py`, `40_export_client.py`.

## État au 2026-07-08 (session détection — Fable 5)

Stratégie d'orchestration décidée : les tâches à haute complexité algorithmique/architecturale
sont traitées par les sessions Fable 5 ; les tâches d'exécution mécanique (téléchargements,
débogage de chaîne sur données réelles, drafts de documents, scripts simples) sont **réservées
aux sessions Opus 4.8** — elles sont marquées `[OPUS]` ci-dessus.

Fait par cette session :
- **B2 (code) + B3 : étape 1b implémentée et testée.** `detection.py` (cœur pur : masque HSV+IRC,
  morphologie, vectorisation géoréférencée, filtres de forme, score, fusion inter-dalles),
  `15_detect_piscines.py` (orchestration par dalles/fenêtres avec chevauchement, partition des
  zones intérieures = zéro doublon par construction, masque bâti BD TOPO, appariement RVB/IRC
  par emprise, échecs bruyants), `16_tri_visuel.py` (vignettes + page de tri HTML autonome
  O/N/U + application des décisions avec refus des tris incomplets >2 %).
- **25 tests** (`pipeline/tests/`) : détection sur scènes synthétiques, propriétés du
  fenêtrage, intégration bout-en-bout, garde-fous. Tous verts au 2026-07-08.
- Config `detection:` + `tri_visuel:` ajoutées à `config.yaml` (seuils **non calibrés** sur
  données réelles — valeurs physiquement raisonnables à ajuster en B2-terrain).
- requirements.txt : + rasterio, scikit-image ≥ 0.26, scipy, pillow, pytest.

## Phase A — Chaîne technique en mode dev (OSM, 2-3 communes)

Objectif : chaîne 10→40 qui tourne de bout en bout. Aucune vente possible à ce stade.

- [x] **A1.** `[OPUS — ✅ FAIT 2026-07-11]` `10_download.py` lancé sur le 49. **URLs/millésimes réels** :
  cadastre Etalab `latest` (parcelles 161 Mo gz → ~800k, bâtiments 48 Mo), BAN `latest`
  (353 333 adresses), **BD TOPO 3-5 GPKG D049 millésime 2025-12-15** (miroir opendatarchives,
  scraper OK ; bâtiment 951 847, exclusions 5 680). **Bug corrigé** : `gpd.read_file(.json.gz)`
  ne marche plus avec pyogrio (geopandas ≥ 1) → lecture via `/vsigzip/{chemin absolu}`.
  `7z`/`osmium`/`gdal` installés (brew).
- [x] **A2.** `[OPUS — ✅ FAIT 2026-07-11]` OSM Pays-de-la-Loire (Geofabrik) → `osmium tags-filter
  w/leisure=swimming_pool` → lu via pyogrio (pas besoin d'ogr2ogr), 81 `indoor` écartées →
  `data/interim/piscines_osm_dev.parquet` (43 095 ; **7 269 dans le 49**, le reste 44/53/72/85).
  **Communes tests choisies** (comptage OSM par commune) : **Bouchemaine 49035** (péri-urbain
  Angers, 286) + **Saint-Melaine-sur-Aubance 49308** (rural, 87).
- [x] **A3.** `[OPUS — ✅ FAIT 2026-07-11]` Chaîne `20→30 --dev→35 --dev` déroulée sur les 2 communes.
  **3 bugs réels corrigés** (voir journal) : (1) `sjoin_nearest` vs index `id_piscine` en
  double ; (2) **`cad_parcelles` : format BAN ≠ format Etalab** (séparateurs `|`+`,`, format
  espacé 15 car. vs compact 14 car.) → `normaliser_ref_cadastrale`, la jointure passe de
  **0 % → 96 % (dept)** ; (3) `id_ban` en doublon dans la BAN (0,02 %) → dédup au chargement.
  **% via cad_parcelles : 78 % (Bouchemaine) / 92 % (rural)** — bien > 50 %, PAS besoin du
  dataset « Adresses cadastre ». Vendables : 260 (Bouchemaine) / 85 (rural). +4 tests (test_join).
- [x] **A3bis.** `[OPUS — ✅ FAIT 2026-07-11]` PCI Édigéo lu via driver GDAL natif (couche
  exacte `TSURF_id`, attribut `SYM`, `SYM=="65"`, déjà en L93 ; archives .tar.bz2 par feuille
  sur cadastre.data.gouv.fr/…/edigeo/feuilles/49/{INSEE}/). **238 piscines cadastrées**
  (165 Bouchemaine + 73 St-Melaine) → `data/interim/piscines_pci_sym65_{INSEE}.parquet`.
  **Recouvrement (buffer 5 m)** : 86,1 % des SYM=65 ont une piscine OSM (92,1 % à
  Bouchemaine) ; dans l'autre sens, seulement 55 % des OSM sont cadastrées (piscines
  non déclarées ou faux positifs OSM — non tranché). **Décision : > 50 % → corroboration
  au score VALIDÉE** ; le branchement effectif dans 30_score (bonus de confiance si
  SYM=65 à proximité, ne crée JAMAIS de ligne — doctrine `16`) = petite tâche `[OPUS]`
  à faire avec le premier run production, pas avant.
- [x] **A4.** `[OPUS — ✅ FAIT 2026-07-11 (proxy auto) + 🧑 œil Géoportail]` Proxy objectif
  « le point-adresse tombe-t-il dans la parcelle de la piscine ? » : global **78,5 %**, mais
  **94 % via cad_parcelles** (fiable, cohérent avec l'objectif ≥ 95 %) contre **23 % via
  nearest** (le fallback met souvent l'adresse sur une parcelle voisine — déjà exclu de la
  confiance « haute » par 30_score). Échantillon 30 lignes + URLs Géoportail :
  `data/validation/a4_controle_visuel_49035.csv` → **🧑 contrôle visuel humain à faire**.

## Phase B — Détection BD ORTHO (l'actif)

- [x] **B1 (téléchargement). ✅ FAIT 2026-07-11.** 🧑 a autorisé le téléchargement complet
  (disque externe **NOIR**, 2 To, 223 Go libres). **Correction de l'estimation doc** : les
  archives réelles D049 2022 font **~31 Go/spectre (61 Go RVB+IRC)**, PAS ~150-170 Go/spectre
  comme deepsearch ① l'estimait — 8 volumes .7z.001-008 chacun (dernier volume < 4 Go,
  les autres pile 4 GiB = limite 7z), 712 dalles JP2 par spectre. Intégrité vérifiée (`7z t`
  OK sur les deux archives). **Millésime confirmé = 2022** (seul publié pour le D049 ;
  2023-2025 = 404 sur data.geopf.fr → diff « nouvelles » 2022→2025 (E2) pas mobilisable
  pour l'instant). Stockage : `/Volumes/NOIR 1/maps-bdortho/D049_2022/` (HORS DU REPO,
  disque externe — ne jamais copier ces archives dans data/ du Mac, pas la place).
  Reste : extraire les dalles de Bouchemaine (49035), vérifier l'ordre des bandes IRC,
  lancer B2-terrain.
- [x] **B2-code.** ~~Implémenter `15_detect_piscines.py`~~ **Fait 2026-07-08**.
- [x] **B2-terrain. ✅ FAIT 2026-07-11** sur Bouchemaine (49035, BD ORTHO 2022 réelle, 4 dalles
  5×5 km extraites du disque NOIR). **Bande NIR confirmée = bande 1** (ratio réflectance
  végétation/global 1,13 vs 0,76/0,86 pour les bandes 2/3 — hypothèse config.yaml validée,
  aucun changement requis). **Calibration seuils (AVANT → APRÈS, consignée dans
  config.yaml)** : `surface_min_m2` 4→8 (aligné filtre commercial, gratuit) ;
  `score_min` 0,35→0,55 (seul levier qui fait vraiment baisser le ratio). **Résultat
  mesuré sur le run réel** : 2614→977 candidats, **ratio candidats/OSM 9,1:1→3,4:1**
  (repasse sous le seuil d'alerte 4:1 de `10` §8), **rappel 58,0%→53,1%** (perte
  modérée, acceptable — le tri humain ne peut de toute façon pas absorber 9:1 à
  l'échelle département). Note : le rappel plafonne autour de 55-58% quel que soit
  le seuil (cf. sweep) — B4 (décision A/B option modèle) sera à réévaluer si ce
  plafond s'avère insuffisant après tri humain réel (16_tri_visuel, non fait cette
  session — candidats prêts dans `data/interim/piscines_candidates_49_49035.parquet`).
- [x] **B3.** ~~Outil de tri visuel~~ **Fait 2026-07-08** (+ tri par incertitude 2026-07-11, PR #10).
- [x] **B4 (volet rappel). ✅ TRANCHÉ 2026-07-12 (session Fable — autopsie du rappel).**
  **Décision : PAS de modèle entraîné (option B maintenue). Le levier de rappel est la
  fusion de sources, pas l'algorithme.** Preuve (Bouchemaine, 286 piscines OSM,
  artefacts `data/validation/autopsie_rappel_49035.{csv,png}` + scripts) :
  - Sur les 129 manquées : **103 (80 %) n'ont AUCUN signal eau dans l'ortho 2022** —
    la planche contact montre massivement des **piscines couvertes** (bâches/abris
    clairs : teinte médiane 0,167 hors fenêtre cyan, saturation médiane 0,044 ≈ gris),
    plus quelques vides/eau verte/postérieures à 2022. 16 ont un signal < 8 m²,
    seulement **10 sont récupérables par réglage** de seuils/filtres.
  - **Rappel sur les piscines réellement visibles en 2022 : 85,8 %** (157/183). Le
    détecteur colorimétrique est près de son plafond PHYSIQUE ; un modèle entraîné sur
    la même image 2022 ne peut pas voir de l'eau sous une bâche — il n'achèterait que
    quelques points, au prix de l'annotation + contraintes licence (DS5).
  - Les couvertes ne sont pas perdues : **46/103 sont déjà dans PCI SYM=65**.
    **Rappel détection ∪ SYM=65 = 76,6 %** (219/286, +21,7 pts gratuits, licence
    Etalab propre) + 8 piscines SYM=65 hors OSM et hors détection (stock net).
    → tâche 12 ci-dessous (fusion source cadastre) + amendement doctrine `16` §5.
  - ⚠ Volet PRÉCISION toujours ouvert : si le tri humain révèle une précision
    irrécupérable < 95 %, ré-examiner l'option A — mais pour la précision, pas le rappel.
- [ ] **B5.** `[OPUS]` Industrialiser sur le département par lots de dalles + tri humain. Sortie : `piscines_detectees_49.parquet`. (Pré-requis git ✅ résolu 2026-07-11.)
- [ ] **B6.** `[OPUS]` Chaîne complète 20→30 en mode production ; `35 --dept` pour le chiffre total.

## Phase C — Qualité & légal (bloquants avant vente)

- [ ] **C1.** Protocole de validation `06` §2 (100 adresses aléatoires ; annoncer la borne basse de Wilson 95 %). Consigner le rapport.
- [x] **C2.** ~~Checklist légale `03` §6~~ **Fait 2026-07-09** (`docs/legal/`, 5 drafts « à valider avocat » ; bloqueurs 🧑 = nom/forme/adresse/email/URL + avis avocat).
- [ ] **C3.** Contrat de licence draft + **relecture avocat** (action humaine, à planifier tôt : compter 2 semaines de délai).
- [ ] **C4.** Canal d'opposition opérationnel (email DÉDIÉ + page web statique avec formulaire) + test du filtre opt-out avec une adresse factice + process art. 11 écrit (opposition sans identité : matching par adresse seule — nécessite la 5bis).
- [x] **C5.** ~~« Pack incident » (pre-mortem `10` §9)~~ **Fait 2026-07-09**.

## Phase D — Vente

> **Règles de séquence issues du pre-mortem (`docs/10-PREMORTEM.md`) — priment sur tout :**
> D0 se fait AVANT la suite de la phase A/B. Kill-switch : si au 15/10/2026 il n'y a ni LIA
> validée ni 5 RDV bookés, gel total du code. Saisonnalité : les pisciniers achètent
> d'oct. à fév. — l'été sert à préparer, pas à vendre.

- [ ] **D0. [HUMAIN, cette semaine]** Pré-vente avant la base : appeler 5 pisciniers du 49
  avec le pitch (`00` + `07`). Objectif : tester le prix réel (« à 800 € vous prenez ? ») et
  l'appétence pour une offre « fichier + mailing clé en main ». Consigner chaque réponse ici.
- [x] **D1.** ~~Liste de prospects B2B~~ **Fait 2026-07-11** (`sales/prospects_49.csv`, 969
  prospects dont 43 pisciniers avérés ; voir tâche 4). Enrichissement tel/site + triage = 🧑.
- [ ] **D2.** `41_export_carte.py` (PDF carte pour RDV) — à écrire, simple (matplotlib + contextily).
- [ ] **D3.** 4-5 RDV de preuve (protocole `07` §3). Consigner objections réelles et prix acceptés.
- [ ] **D4.** Premières ventes ; registre des ventes tenu ; ajuster la grille tarifaire de `00` avec les prix réels.

## État au 2026-07-08 (2e passe session Fable — architecture moteur + cœur solaire)

- **`docs/09-MOTEUR-PROSPECTION.md` créé** : le repo est officiellement un moteur de
  prospection multi-produits (5 couches, seule la couche « détecteur » est spécifique à un
  produit). Portefeuille de produits scoré (P1 piscines → P7) + **critères de pivot chiffrés
  décidés à froid** (Go/No-Go P1 : 10 RDV, < 2 ventes ou < 300 €/extrait ⇒ pivot P2 ou P3).
- **Cœur du produit 2 écrit et testé : `pipeline/src/solaire.py`** (12 tests physiques
  verts). Moteur natif remplace GRASS r.sun (docs/05 §3). Réutilisable pour P3 (toitures PV).
- **Détecteur produit 2 complet** (`terrasses.py` + `25_terrasses.py`, mosaïque inter-dalles
  pour les ombres, masque MNH, classes sur surface contiguë). Le produit 2 n'attend plus que
  les dalles MNS/MNH réelles `[OPUS]` — mais reste bloqué par « P1 vendu d'abord » (docs/05).

## Phase E — Extension (après premières ventes)

- [ ] **E1.** Produit 2 Terrasses (architecture prête : `05` ; ⚠ pièges crue 2024/ZICAD ajoutés) — prototype 1 commune.
- [ ] **E2.** Diff de millésimes → produit "nouvelles piscines" (prospects chauds). ⚠ Possible dès le lancement si millésime 2025 confirmé en B1 (diff 2022→2025).
- [ ] **E3.** Réplication département voisin (44 ou 85) : re-dérouler A→D avec `dept` changé dans config.

## Journal des mesures

| Date | Étape | Mesure / décision | Détail |
|---|---|---|---|
| 2026-07-07 | fondation | Google Solar API écarté | CGU : cache 30 j, revente interdite, usage hors énergie solaire interdit |
| 2026-07-07 | fondation | OSM = dev only | ODbL share-alike incompatible avec vente/exclusivité |
| 2026-07-07 | fondation | Piscines privées absentes de BD TOPO/cadastre Etalab | détection maison sur BD ORTHO requise |
| 2026-07-08 | B2-code/B3 | Étape 1b codée + testée (25 tests verts) | seuils config.yaml = a priori physiques, PAS calibrés terrain |
| 2026-07-08 | B2-code | Sans IRC, la végétation bleutée devient faux positif (test le prouve) | IRC obligatoire en production ; `methode='hsv_sans_irc'` trace la dégradation |
| 2026-07-08 | orchestration | Répartition modèles : tâches `[OPUS]` = exécution ; Fable = algorithmique/architecture | deepsearch Gemini demandée à l'humain : URLs/format BD ORTHO 49 (RVB+IRC) |
| 2026-07-08 | architecture | Repo = moteur multi-produits (doc 09) ; critères de pivot chiffrés | un pivot = un détecteur + une doc, l'aval est mutualisé |
| 2026-07-08 | P2 (cœur) | solaire.py natif remplace GRASS r.sun ; 12 tests physiques verts | même cœur réutilisable P3 toitures PV ; kWh non nécessaires (classement) |
| 2026-07-08 | pre-mortem | 2 analyses indépendantes → `docs/10-PREMORTEM.md` | risque n°1 : inversion de séquence ; kill-switch 15/10/2026 adopté |
| 2026-07-08 | pre-mortem | Abonnement « annuel » impossible (BD ORTHO ~3 ans) — corrigé dans `00` | parade : SITADEL ajouté à `02` ; millésime 49 à vérifier (deepsearch) |
| 2026-07-08 | pre-mortem | `40_export_client.py --demo` : extraits RDV = confiance haute uniquement | le maillon fragile en démo est la jointure d'adresse, pas la détection |
| 2026-07-08 | vente | Kit D0 complet (`11`) | positionnement honnête « je finalise la carte » |
| 2026-07-08 | stratégie | Arbre de décision terrain (`12`) : branches décidées à froid + 7 options gros ticket scorées | franchises siège 5-30 k€, PAC, clé en main ×3-5, marque blanche ; assureurs GELÉ |
| 2026-07-08 | orchestration | CLAUDE.md : ordre de lecture + routage [OPUS]/[FABLE]/[HUMAIN] | la tour de contrôle est transmise |
| 2026-07-08 | R&D moteur | contrat.py + ombres_rapide ×59 + ids stables + tri en fichiers | 82 tests verts ; le moteur est clos |
| 2026-07-08 | audit pièges | 5 pièges corrigés (BAN sans x/y, --bdtopo-url, millésimes non datés, 2 scans linéaires → index spatiaux) | audit refait à la main sur 10/16/20/25/30/35 |
| 2026-07-08 | cibles moteur | Doc `14` : attribut→acheteur, top 3 arbitré (① ombrières APER, ② foncier divisible, ③ grandes toitures) | tickets 10-100× ; s'active via l'arbre `12`, ne double PAS D0-pisciniers |
| 2026-07-08 | R&D géométrie | `geometrie.py` : rectangle libre maximal à orientation libre — 8 tests | 90 tests verts ; deepsearch ⑧ (APER/parkings/PLU) demandée |
| 2026-07-08 | état de l'art | Doc `15` : Foncier innovant = 94 % annoncé + polémique faux positifs ; DL brut ≈ 80/85 % | nos choix validés (tri humain = LA différence) |
| 2026-07-08 | état de l'art 2 | APER : assouplie (Huwart) mais échéances 2026/2028 MAINTENUES, bon de commande avant le 31/12/2026 → cible ① brûlante | namR (coté) valide la thèse ; artisans locaux = angle mort des gros |
| 2026-07-08 | concurrence P1 | ⚠ Cartégie/Easyfichiers louent déjà des fichiers piscines NOMINATIFS (1 M+, téléphones) | repositionnement P1 dans kit `11` ; segment imprenable = « nouvelles » locales |
| 2026-07-08 | R&D millésimes | `millesimes.py` : diff par appariement spatial un-pour-un — 7 tests | garde-fou : > 50 % de « nouvelles » = recalage suspect, refus de vendre |
| 2026-07-08 | décisions op | Doc `16` : livrable ZIP xlsx+csv+pdf+notices, stockage local + backup chiffré, grille tarifaire v1 (490 € lancement → 39-59 €/mois veille), doctrine de recoupement, micro-entreprise, budget ~115 €/mois | 🧑 restent : nom commercial, forme juridique, RC pro, numéro dédié |
| 2026-07-09 | C2 légal | 5 drafts rédigés (`docs/legal/`), art. 14.5.b traité, 4 clauses `10` §5 portées par la LIA | bloqueurs 🧑 = nom/forme/adresse/email/URL + avis avocat data (bloquant lancement) |
| 2026-07-09 | C5 pack incident | Q&A presse + procédure réclamation/opposition ≤ 1 page chacun | remède 90 j + `reclamations.csv` ; opposition art. 11 par adresse seule ; « à ne jamais dire » cadré |
| 2026-07-11 | audit garde-fous | 3 failles corrigées (opt-out par adresse art. 11, refus d'export sans version git, témoins de tatouage au registre) + 6 tests | ⚠ **correctifs PERDUS dans l'incident du 2026-07-11 (jamais poussés) → tâche 5bis** ; les constats (a)-(e) restent valables |
| 2026-07-11 | D1 prospects | `prospects.py` + CLI + 9 tests → `sales/prospects_49.csv` : **969 prospects, 43 « haute »** | API « Recherche d'entreprises » DINUM (SIRENE sans clé, NAF pointé) ; hybride NAF+mot-clé ; garde-fous non-nominatifs (451 EI écartés) ; survivants de l'incident, À COMMITER |
| 2026-07-11 | env | venv projet `.venv/` avec tout requirements.txt + `7z` (brew p7zip) | le Python système n'a pas les deps géo → `.venv/bin/python -m pytest` |
| 2026-07-11 | items 6+8 | Implémentations CLOUD mergées : PR #10 (cle_incertitude + borne_basse_wilson + docs/06) et PR #11 (ecrire_xlsx + archiver_copie_datee) ; 90_backup.py (8c) écrit localement (survivant) + clé `backup:` réajoutée | les variantes locales décrites avant l'incident (qualite.py, test_tri/export/archive) sont perdues et caduques — versions cloud font foi |
| 2026-07-11 | deepsearch | ①②③④⑤⑦⑨⑩ reçues, rangées (`docs/deepsearch/`), arbitrées : B1 débloqué, SITADEL viable (tâche 10), PCI SYM=65 en corroboration (A3bis), crue LiDAR 2024 = piège P2, datasets AGPL/Google interdits, chiffres brokers/leads pour kit `11` | vérifs web : namR liquidation CONFIRMÉE (01/07/2026) ; millésime ortho 2025 et crue 7/3/2024 PLAUSIBLES non confirmés (B1 / 1er run P2 tranchent) ; ⑥ et ⑧ restent à lancer |
| 2026-07-11 | ⚠ INCIDENT | Arbre de travail quasi intégralement supprimé en cours de session (concomitant git init+fetch ; cause exacte non établie) ; restauré via `git reset --hard origin/main` + survivants | perdu : correctifs audit (→ 5bis) ; **118 tests verts** post-restauration ; leçon : COMMIT+PUSH après chaque tâche |
| 2026-07-11 | 5bis garde-fous | Refait les 3 correctifs perdus + 6 tests : opt-out double clé id_ban+adresse (art. 11 par adresse seule), refus d'export non-démo sans version git, témoins+version au registre des ventes | `common.normalise_adresse` (pure), `40_export.exiger_version_tracable`, `tatouer()→(df,temoins)` ; **124 tests verts** ; répond à « faut-il refaire ? » = c'était la seule perte de code de l'incident |
| 2026-07-11 | A1 téléchargements | Sources réelles 49 : cadastre Etalab latest, BAN latest (353 333), **BD TOPO 3-5 2025-12-15** (bât. 951 847, excl. 5 680) | bug corrigé : `.json.gz` illisible par pyogrio → `/vsigzip/` ; 7z/osmium/gdal installés |
| 2026-07-11 | A2 OSM dev | 43 095 piscines OSM région → **7 269 dans le 49** ; communes tests Bouchemaine 49035 (286) + St-Melaine-s-Aubance 49308 (87) | source `_dev` ODbL, jamais en final/ |
| 2026-07-11 | A3 chaîne dev | 20→30→35 OK sur 2 communes ; **3 bugs réels corrigés** ; **cad_parcelles 0 %→96 %** après `normaliser_ref_cadastrale` ; vendables 260 / 85 | bugs : sjoin_nearest vs index id_piscine, format cad BAN≠Etalab (sép. `\|`+`,`, espacé 15 vs compact 14), id_ban doublons ; +4 tests (test_join) |
| 2026-07-11 | A4 contrôle | Proxy « adresse dans la parcelle » : **94 % via cad_parcelles vs 23 % via nearest** (global 78,5 %) | confirme : cad_parcelles = fiable (→ haute confiance), nearest = fallback à ne pas vendre en haute ; œil Géoportail 🧑 sur 30 lignes exportées |
| 2026-07-11 | B1 sondage accès | BD ORTHO D049 : **millésime dispo = 2022** (pas de 2025 → pas de diff 2022→2025 pour l'instant) ; accès = **archive 7z ~300 Go RVB+IRC** uniquement (pas de dalle décompressée) ; voie WMS = code neuf (bloqué pré-D0/`[FABLE]`) | **🧑 décision requise** : 300 Go, ou WMS (dérogation), ou différer Phase B après D0 |
| 2026-07-11 | B1 téléchargement | 🧑 a autorisé ; archives réelles **61 Go** (PAS ~300 Go estimé) sur disque externe NOIR ; dalles réelles = **5×5 km** (pas 1 km comme supposé), nommage `49-2022-XXXX-YYYY-...jp2`, index shapefile `dalles.shp` embarqué dans l'archive (bien plus fiable que calculer les bounds à la main) | corrige 2 hypothèses de la deepsearch ① (taille archive, taille dalle) |
| 2026-07-11 | B2-terrain | Bande NIR confirmée = bande 1 (physique : réflectance végétation +13 % vs -14/-24 % bandes 2/3) ; seuils calibrés `surface_min_m2` 4→8, `score_min` 0,35→0,55 ; **ratio candidats/OSM 9,1:1→3,4:1**, rappel 58,0%→53,1% sur Bouchemaine (977 candidats) | rappel plafonne ~55-58 % quel que soit le seuil → si insuffisant après tri humain réel, réexaminer B4 (option A modèle) |
| 2026-07-11 | A3bis PCI SYM=65 | 238 piscines cadastrées (165+73) ; couche `TSURF_id`, attr `SYM`, L93 natif ; **86,1 % des SYM=65 ont une OSM < 5 m** (sens inverse 55 %) → **corroboration au score validée**, branchement différé au 1er run prod | 2 feuilles 49308 sans couche TSURF (légitime) ; parquets en interim/ |
| 2026-07-11 | item 7 flags | 20_join `--source` (alias, `resoudre_source` pure) + 30_score `--produit` ; +12 tests, **140 verts** | comportement piscines inchangé |
| 2026-07-11 | tri visuel prêt | **Planche générée : `data/interim/tri/tri.html` (977 vignettes, Bouchemaine)** — raccourcis O/N/U, export decisions.csv puis `16 --apply` | **🧑 LE tri humain est LA prochaine action produit** : ~20-30 min, donne la vraie précision et débloque B4/C1 |
| 2026-07-11 | verrou parcellaire | Retour 🧑 (« piscine chez le voisin ») → colonne `adresse_dans_parcelle` (20_join, point BAN dans la parcelle de la piscine, tol. 2 m) ; « haute » l'EXIGE, `nearest`+hors-parcelle → **basse, jamais vendue**. Effet 49035 : haute 193→182, moyenne 67→37, basse 4→45 (41 adresses à risque déclassées) ; 49308 : 74/11 → 74/6/5. **149 tests verts** | ferme la faille A4 (nearest = 23 % bonne parcelle) ; `calculer_confiance` factorisée pure + rétro-compat parquet ancien |
| 2026-07-12 | refonte UX tri | Planche `16_tri_visuel.py` refondue en jeu autonome : bandeau question/compteur/progression, règles du jeu intégrées, raccourcis O/N/U, **undo Z/←**, **persistance localStorage**, export `decisions.csv` (contrat `id_detection,decision`) | rend le tri faisable par un non-technique sans accompagnement ; badge « cadastré » (PCI SYM=65) sur les vignettes, 99/977 corroborés |
| 2026-07-12 | partage sans install | `handoff/` (planche autonome `tri_bouchemaine_49035.html` ~27 Mo double-clic, `soumettre_tri.sh`, `appliquer_decisions_recues.py`, ZÉRO PII) + `bootstrap.sh` (venv+requirements+outils brew+tests) + `ONBOARDING.md` (parcours A trier / B contribuer) + routage express en tête de `CLAUDE.md` | un ami peut trier sans rien installer ; `12_extraire_dalles_ortho.py` extrait les dalles ciblées depuis les archives 7z (`--commune`/`--bbox`, index `dalles.shp`) |
| 2026-07-12 | outil 17 vérif adresse | `17_verification_adresse.py` : 2e outil de tri humain — vérification de l'adresse assignée par clic sur la carte des adresses BAN alentour, pour les cas de confiance non-haute | **7 cas à vérifier** détectés sur le dev Bouchemaine |
| 2026-07-12 | fixes d'intégrité | Empreinte `hash12` des candidats dans la planche (`data-planche`, nom d'export `decisions_{dept}_{commune}_{hash12}.csv`, **refus à l'apply si mismatch** sauf `--force`) ; clé localStorage **par planche** ; fusion par **timestamp du nom de fichier** (pas mtime) ; flag `--embarquer` pour régénérer la planche autonome | motivé par 3 scénarios de perte/invalidation identifiés (décisions collées à la mauvaise planche, écrasement de localStorage, ordre de fusion faux). **193+ tests verts** |
| 2026-07-12 | autopsie rappel (B4) | Bouchemaine, 286 OSM : 129 manquées = **103 sans signal eau 2022** (bâches/abris clairs — hue méd. 0,167, sat 0,044 —, vides, post-2022 ; 46/103 pourtant au cadastre SYM=65), 16 signal < 8 m², **10 seules récupérables par seuils**. Rappel sur visibles : **85,8 %**. Détection ∪ SYM=65 : **76,6 %** (+8 hors OSM). → **B4 rappel = option B maintenue, pas de modèle** ; fusion cadastre = tâche 12 ; doctrine `16` §5 amendée | méthode : rejouer `masque_eau` exact aux emplacements OSM manqués (scripts + CSV + planche contact dans `data/validation/autopsie_*`) ; ⚠ rappel brut vs OSM = métrique structurellement biaisée (risque R10 de `17`) |
| 2026-07-12 | 10bis mesuré | Banc d'essai run départemental simulé (43 095 polygones, données 49 entières) : jointures **< 2 s au total**, chargements ~1 s — les « hotspots » de la lecture de code ne se reproduisent pas | 10bis CLOS sans refonte ; règle : pas d'optimisation sans mesure > 10 min sur run réel |
| 2026-07-12 | découverte CoSIA (arbitrage OSS) | Survey open source vérifié → **CoSIA IGN** (absent du survey) : classe Piscine, vecteur GPKG L93, LO 2.0, D49 2020/2022/2025 (~1 Go). Bouchemaine : **rappel 88,1 %** vs OSM, **68 % des couvertes** vues, 98,7 % de nos détections couvertes, **∪ SYM=65 = 89,2 % sans notre HSV** ; 53 CoSIA-seules ≥ 8 m² = majoritairement vraies hors-sol (planche) ; 2025 : -30 % de polygones toutes classes (modèle changé) → diff naïf interdit, 52 « nouvelles » brutes à valider à l'œil | → tâche 12 amendée (union 3 sources, 89,5 % potentiel), tâche 13 [OPUS] (mesure dept), option A enterrée, samgeo/LabelStudio/Download-BDOrtho21 écartés (`15` §4), `02` corrigé (« fait établi n°1 » périmé) ; artefacts `data/validation/cosia_*`, archives sur NOIR |
| 2026-07-12 | identité trieur + bilan | Planche `16` : modal « Qui trie ? » (JB/Azan/pseudo, clé localStorage globale), décisions stockées `{d,t,ts}` (migration chaîne→objet), CSV export 4 col `id_detection,decision,trieur,horodatage` (format 2 col **toujours accepté**, rétro-compat stricte apply+fusion) ; nouveau `18_bilan_tri.py` → dataset d'entraînement `tri_labels_*.parquet` (features × décision, roadmap B4 option A) + rapport calibration réelle (taux « oui » par bucket score/surface, effet corroboration cadastre, compte par trieur, implications prudentes) | **243 tests verts** ; planches régénérées `data-planche=49_49035_2d460d3dc74e` (inchangé) ; vérifié en navigateur (modal, objet {d,t,ts}, compteur par trieur, migration) |

## Tableau de mesures B2-terrain (à remplir par la session Opus de la tâche 5)

| Mesure | Valeur | Commentaire |
|---|---|---|
| Commune test (INSEE) | Bouchemaine 49035 (péri-urb.) + St-Melaine-s-Aubance 49308 (rural) | choisies par comptage OSM |
| Millésime BD ORTHO constaté (B1) | **2022** (seul dispo D049 ; pas de 2025) | diff « nouvelles » 2022→2025 pas mobilisable maintenant |
| Ordre des bandes IRC vérifié (B1) | | attendu : 1=PIR, 2=R, 3=V (deepsearch ①) |
| % jointures cad_parcelles (A3) | **78 % Bouchemaine / 92 % rural** (après correctif format) | > 50 % → PAS d'« Adresses cadastre » |
| Recouvrement SYM=65 vs OSM (A3bis) | **86,1 %** des SYM=65 ↔ OSM (sens inverse : 55 %) | > 50 % → corroboration au score VALIDÉE (branchement différé) |
| Taux contrôle visuel 30 lignes (A4) | proxy auto **94 % via cad_parcelles / 23 % via nearest** | œil Géoportail 🧑 : a4_controle_visuel_49035.csv |
| Candidats bruts 15_detect (B2) | **977** (Bouchemaine, après calibration) | avant calibration : 2614 |
| Ratio candidats / piscines OSM | **3,4:1** | avant calibration : 9,1:1 (seuil d'alerte 4:1 dépassé) |
| Précision après tri (échantillon) | *(16_tri_visuel non fait cette session)* | objectif ≥ 95 % (borne basse Wilson) |
| Rappel vs OSM | **53,1 %** | avant calibration : 58,0 % ; plafond ~55-58 % quel que soit le seuil (sweep) |
| Rappel sur piscines VISIBLES 2022 (autopsie B4) | **85,8 %** (157/183) | 103/286 OSM sans signal eau dans l'ortho 2022 (couvertes/vides/post-2022) — plafond physique, pas algorithmique |
| Rappel détection ∪ cadastre SYM=65 (potentiel) | **76,6 %** (219/286) | fusion source = tâche 12 (post-D0) ; + 8 SYM=65 hors OSM |
| Rappel CoSIA 2022 vs OSM | **88,1 %** (252/286) | voit 68 % des couvertes ; ∪ SYM=65 = 89,2 % ; ∪ tout = **89,5 %** |
| Seuils modifiés (avant → après) | `surface_min_m2` 4→8 ; `score_min` 0,35→0,55 | `hsv`/`irc`/`compacite`/`solidite` inchangés |
