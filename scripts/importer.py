"""Import des photos déposées dans a-importer/ (à coder après validation du schéma).

Étapes prévues :
  1. lister a-importer/ sur kDrive
  2. attribuer un identifiant <date>-<contexte>-<lieu>-<NNN> et renommer
  3. générer les previews 512 et 1000 px (previews/512, previews/1000)
  4. préparer une fiche par photo (dimensions, orientation calculées ; description
     et tags proposés par l'agent) pour validation par Flavien
  5. après accord : déplacer vers originaux/ et écrire l'entrée dans index.json
"""
