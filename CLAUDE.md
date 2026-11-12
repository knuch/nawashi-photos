# nawashi-photos

Boîte à outils de la photothèque de nawashi.ch (association de shibari, Suisse romande,
gérée par Flavien alias Tengu). Utilisée par des agents Claude ; source du skill
« nawashi-photos » du plugin nawashi (le skill du plugin renvoie à ce dépôt). Réponds en français et tutoie Flavien.

## Architecture (décidée — ne pas remettre en cause sans demander)
- **Images sur kDrive Infomaniak, jamais dans le repo** (`.gitignore` bloque jpg/png/webp/tif).
  Racine : `/Private/nawashi/nawashi-photos` (id et sous-dossiers dans `config.json`).
  ```
  nawashi-photos/
  ├── a-importer/        dépôt des JPEG plein format par Flavien
  ├── originaux/         originaux traités : on n'y touche plus jamais
  ├── previews/512/      pour les agents
  ├── previews/1000/     pour travailler
  └── derives/           crops, zooms, formats par canal, styles
  ```
- Le repo contient : `scripts/`, `config.json`, `vocabulaire.json`, `formats.json`,
  `styles.json`, `index.json` (**seule source de vérité**), `index.schema.json`, `skill/SKILL.md`.
- Accès kDrive : `scripts/kdrive.py` (API Infomaniak, stdlib). Variables `KDRIVE_ID` et
  `KDRIVE_TOKEN`. Dans les sessions cloud, le proxy injecte le jeton : `KDRIVE_TOKEN`
  peut être absente. **Ne jamais écrire le jeton dans un fichier, un commit ou une sortie.**
  WebDAV kDrive = plan B. Les téléchargements redirigent vers
  `1-9-v3-12.download.kdrive.infomaniakusercontent.com` (hôte à autoriser dans l'environnement).
- Pas de Docker, pas de GitHub Actions. Python + Pillow (`pip install -r requirements.txt`).
- Commit et push directs sur `main` autorisés **dans ce repo uniquement** (pas de PR).
  Les autres repos de Flavien passent toujours par une PR.

## Contraintes
- **Économiser les tokens** : choisir par l'index (`jq`, `scripts/choisir.py`). N'ouvrir une
  image qu'en preview 512 px, et seulement pour vérifier un choix.
- **Aucune image générée par IA** : recadrer, redimensionner, étalonner uniquement.
  Pas de remplissage génératif, pas d'extension d'image (si un format ne rentre pas, on
  recadre plus serré ou on change de photo).
- Métadonnées dans `index.json` uniquement : jamais dans l'EXIF ni dans les noms de fichiers.
  (Lire l'EXIF à l'import pour la date est permis.)
- Nommage : minuscules, chiffres, traits d'union ; ni accents, ni espaces, ni caractères spéciaux.
  - Original : `2026-11-12-rope-jam-001.jpg` = `<date d'import>-<contexte>-<NNN>` (numéro par date + contexte ;
    pas de lieu dans le nom, le lieu est un tag)
  - Dérivé : `2026-11-12-rope-jam-001-crop-mains-insta-4x5-nb.jpg` = `<id>-<nature>-<sujet>-<format>-<style>`
  - Renommer/réorganiser : toujours par un script qui met à jour `index.json` en même temps.
- Avant d'écrire `index.json` : le relire, ne modifier que les entrées concernées, puis commiter.

## Crédits et autorisations
- Toutes les photos sont de Flavien ; crédit = **@nawashi.ch** (`config.json` → `credit_defaut`).
- Toutes les personnes photographiées ont donné un consentement explicite et écrit pour la
  communication nawashi.ch sur toutes les plateformes, avec nom et identification :
  statut par défaut `ecrit-confirme`, publiable partout.
- Statut `retire` : photo exclue de toute sélection (dérivés compris).
- **Aucune mention ni tag de personne par défaut**, seulement sur demande explicite de Flavien.
- Type `illustration` : réservé aux illustrations libres de droit fournies par Flavien.
  Toutes sont libres de droit : licence par défaut « libre de droit », sans attribution.
  **Ne jamais demander de licence ni de source à Flavien** (`source` reste facultative).
  Pas de crédit @nawashi.ch sur une illustration.

## Tags
Vocabulaire fermé dans `vocabulaire.json` ; une valeur n'est ajoutée que si aucune existante
ne convient (avec l'accord de Flavien). Orientation, dimensions et ratio sont calculés.
Chaque photo a une description courte rédigée une fois à l'import (pose, cadrage, ambiance,
zones intéressantes pour un crop), plus des `zones` facultatives (fractions 0–1) pour les crops.

Lieux (`vocabulaire.json` → `lieu.libelles`) : `bulle` = **« salle de pole à Bulle »**, toujours
générique, ne jamais nommer l'entité qui accueille ; `lafabrik-cucheturelle` = LaFabrik,
Cucheturelle (Forum des cordes) ; `epfl` = EPFL, Lausanne (festival Japan Impact).

## Déclinaisons
- `formats.json` : insta-4x5 1080×1350, story-9x16 1080×1920, entete-16x9 1920×1080,
  article 1200 px de large, og 1200×630.
- `styles.json` : vide au départ ; un style n'y entre (paramètres exacts) qu'après validation.
- Chaque dérivé stocke sa **recette** (cadre en px, sortie, étalonnage) pour être regénéré à l'identique.
- **Validation par élimination** : tout nouveau crop/zoom/style naît en `proposition` ;
  galerie numérotée (artefact Claude, sinon planche contact JPEG numérotée) ; Flavien dit
  lesquelles retirer → les autres passent en `valide`, les refusées sont supprimées de kDrive.

## Suivi d'utilisation
- Chaque utilisation : date, canal, skill, référence du post, statut `prevu` (annulable → `annule`).
- Une utilisation compte dès que le visuel final est livré. Un dérivé compte pour sa photo d'origine.
- **Règle stricte** : une photo (dérivés compris) ayant un usage `prevu` à moins de 28 jours de la
  date visée, **avant ou après** (un post programmé bloque déjà la photo), est exclue, sauf demande
  explicite (`--inclure-recentes` / `--forcer`). Sinon priorité aux moins utilisées.

## Import (« j'ai ajouté des photos »)
Lister `a-importer/` → attribuer un identifiant et renommer → previews 512 et 1000 px →
rédiger la description → proposer les tags → **après accord**, déplacer vers `originaux/`
et mettre à jour l'index, puis commiter.
JPEG et PNG acceptés : un PNG est exporté en JPEG (qualité 95, transparence aplatie sur blanc)
à l'import ; le JPEG devient l'original (`converti_depuis: "png"`) et le PNG déposé va à la corbeille.
Corriger une fiche après import : `importer.py modifier <id> --tags '{…}' --description … --commit`.
Changer le contexte (donc l'identifiant) : `importer.py renommer <id> --contexte … --commit`
(renomme original, previews et dérivés sur kDrive et met l'index à jour d'un coup).

## Commandes
```sh
python scripts/kdrive.py check                       # accès + arborescence
python scripts/importer.py preparer                  # fiche + planche contact (cache/import/)
python scripts/importer.py valider --commit          # après accord de Flavien
python scripts/choisir.py chercher --plan mains --format insta-4x5 [--date …] [--json]
python scripts/choisir.py preview <id>               # preview 512 en cache, pour vérifier
python scripts/deriver.py creer <id> --nature crop --sujet mains --zone mains --format insta-4x5
python scripts/deriver.py galerie --html             # propositions numérotées
python scripts/deriver.py trier --retirer 2,5 --commit
python scripts/usages.py ajouter <id-photo-ou-derive> --canal instagram --skill … --reference … --date … --commit
python scripts/rendre_canvas.py --sortie cache/rendus/post --asset <blob>=<fichier> f1.dc.html …   # canvas → PNG 1080 px (export Canva)
```
`cache/` (gitignoré) garde les images téléchargées et générées. Après un commit, `git push`.
