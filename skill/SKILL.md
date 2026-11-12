---
name: nawashi-photos
description: Choisir, décliner et suivre l'utilisation des photos de la photothèque nawashi.ch (kDrive) pour les posts et le site — sélection par l'index, crops/formats par canal, crédits, autorisations et règle des 4 semaines. À utiliser dès qu'un visuel nawashi.ch a besoin d'une photo.
---

<!-- BROUILLON — ne pas publier dans le plugin avant validation par Flavien. -->

# nawashi-photos

## Quand l'utiliser
Dès qu'un skill nawashi (évènements, partages, sensibilisation, déclinaisons…) a besoin
d'une photo, ou quand Flavien dit « j'ai ajouté des photos ».

## Règles non négociables
1. **Sélection par l'index uniquement** (`scripts/choisir.py` ou `jq` sur `index.json`).
   N'ouvrir que la preview 512 px, et seulement pour vérifier un choix.
2. **Exclure** : statut `retire` ; toute photo dont elle-même ou un dérivé a un usage
   `prevu` dans les 28 derniers jours, sauf demande explicite de Flavien.
   Ensuite, priorité aux photos les moins utilisées.
3. **Aucune image générée par IA** : recadrer, redimensionner, étalonner seulement.
   Pas de remplissage, pas d'extension.
4. **Crédit** : toujours créditer la photo avec le compte Instagram de Flavien
   (`config.json` → `credit_defaut`), sauf illustration : créditer selon sa `licence`.
5. **Autorisations** : toutes les photos `ecrit-confirme` sont publiables partout.
   **Ne mentionner ni taguer aucune personne**, sauf si Flavien le demande explicitement.
6. **Enregistrer l'usage** dès que le visuel final est livré : `scripts/usages.py`
   (date, canal, skill, référence du post, statut `prevu`). Un dérivé compte pour sa photo.

## Choisir une photo
_(à compléter quand `choisir.py` sera codé : exemples de requêtes par tags, format, espace-texte)_

## Décliner
- Formats : `formats.json` (insta-4x5, story-9x16, entete-16x9, article, og).
- Styles : `styles.json`, uniquement les styles validés.
- Tout nouveau dérivé naît en `proposition` → galerie numérotée → Flavien élimine →
  les autres passent `valide`, les refusés sont supprimés de kDrive.

## Importer
Lister `a-importer/` → identifiant + renommage → previews 512/1000 → description →
proposition de tags → accord de Flavien → `originaux/` + index + commit.
