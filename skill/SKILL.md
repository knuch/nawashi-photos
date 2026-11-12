---
name: nawashi-photos
description: Choisir, décliner et suivre l'utilisation des photos de la photothèque nawashi.ch (kDrive) pour les posts Instagram, stories, le site et les newsletters — sélection par l'index, crops/formats par canal, crédit @nawashi.ch, autorisations et règle des 28 jours. À utiliser dès qu'un visuel nawashi.ch a besoin d'une photo, ou quand Flavien dit « j'ai ajouté des photos ».
---

<!-- BROUILLON — ne pas publier dans le plugin avant validation par Flavien. -->

# nawashi-photos

Photothèque : images sur kDrive (`/Private/nawashi/nawashi-photos`), métadonnées dans
`index.json` du repo knuch/nawashi-photos (seule source de vérité). Scripts dans `scripts/`.

## Règles non négociables
1. **Choisir par l'index, pas par les images.** `choisir.py chercher` (ou `jq` sur `index.json`).
   N'ouvrir qu'une preview 512 px (`choisir.py preview <id>`), et seulement pour vérifier un choix ;
   pour comparer plusieurs photos, une seule planche (`choisir.py planche <id> <id> …`).
2. **Exclusions** : photos `retire` toujours exclues ; photo (dérivés compris) avec un usage
   `prevu` à moins de 28 jours de la date de publication visée, avant ou après, exclue sauf
   demande explicite de Flavien. Ensuite, priorité aux moins utilisées (tri par défaut).
3. **Aucune image générée par IA** : recadrer, redimensionner, étalonner uniquement.
   Pas de remplissage, pas d'extension. Si le cadre ne tient pas : autre cadre ou autre photo.
4. **Crédit** : « Photo : @nawashi.ch » sur tout visuel publié. Illustration : créditer selon
   sa `licence` (texte `attribution` exact si `attribution_requise`).
5. **Personnes** : toutes ont donné un consentement écrit (statut `ecrit-confirme`, publiable
   partout), mais **ne mentionner ni taguer personne** sauf demande explicite de Flavien.
6. **Lieux** : écrire « salle de pole à Bulle », jamais le nom de l'entité qui accueille.
7. **Enregistrer l'usage dès que le visuel final est livré** — avec la date de publication prévue :
   `usages.py ajouter <id-photo-ou-derive> --canal … --skill … --reference … --date … --commit`
   puis `git push`. Flavien peut l'annuler (`usages.py annuler <id-usage>`).
8. `index.json` ne se modifie que par les scripts (ils le relisent juste avant d'écrire).

## Choisir une photo
```sh
python scripts/choisir.py chercher --contexte rope-jam --espace-texte oui --format insta-4x5 --date 2026-12-05
python scripts/choisir.py chercher --plan mains --plan noeud --ambiance intime --json --limite 5
python scripts/choisir.py voir <id>          # fiche complète, dérivés validés et usages
```
Une option répétée = OU, des options différentes = ET. `--format` écarte les photos trop petites.
Préférer un dérivé `valide` existant au bon format avant d'en créer un nouveau.

## Décliner
```sh
python scripts/deriver.py creer <id> --nature format --format story-9x16 [--centre 0.6,0.4]
python scripts/deriver.py creer <id> --nature crop --sujet mains --zone mains --format insta-4x5
python scripts/deriver.py creer <id> --nature zoom --sujet noeud --format insta-4x5 --centre 0.7,0.6 --echelle 0.5
python scripts/deriver.py creer <id> --nature style --format og --style nb
```
Formats : insta-4x5, story-9x16, entete-16x9, article, og (`formats.json`).
Styles : uniquement ceux de `styles.json`. Un nouveau style se propose avec
`--etalonnage '{"contraste":1.1,"chaleur":0.3}' --nom-style chaud`, puis
`deriver.py valider-style chaud --depuis <id-derive>` une fois validé par Flavien.

**Validation par élimination** : tout dérivé naît en `proposition`.
1. `deriver.py galerie --html` → publier `cache/galerie/galerie.html` en artefact Claude
   (sinon montrer `cache/galerie/planche.jpg`), propositions numérotées.
2. Flavien donne les numéros à retirer → `deriver.py trier --retirer 2,5 --commit`
   (retirées supprimées de kDrive, les autres `valide`) → `git push`.
Seuls les dérivés `valide` peuvent être utilisés.

## Importer (« j'ai ajouté des photos »)
1. `python scripts/importer.py preparer` → fiche `cache/import/fiche.json` + planche numérotée.
   Les doublons (même empreinte qu'une photo indexée) sont signalés : `importer.py ignorer <n>`.
2. Regarder la planche (une image), puis remplir pour chaque photo dans la fiche :
   `contexte`, `description` courte (pose, cadrage, ambiance, zones intéressantes pour un crop),
   `tags` (vocabulaire de `vocabulaire.json` uniquement), `zones` facultatives
   (`{"nom":"mains","x":0.55,"y":0.6,"l":0.3,"h":0.3}`, fractions de l'image).
   Si aucune valeur ne convient, proposer un ajout au vocabulaire à Flavien, sans l'ajouter seul.
3. Présenter à Flavien : numéro, description, tags. Corriger selon ses retours.
4. Après accord : `python scripts/importer.py valider --commit` puis `git push`.
   Identifiant attribué : `<date d'import>-<contexte>-<NNN>`.
