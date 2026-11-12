# nawashi-photos

Photothèque de nawashi.ch pilotée par des agents Claude : index des photos (tags, crédits,
autorisations), previews légères, déclinaisons (crops, zooms, formats, styles) et suivi
d'utilisation. Les images sont sur kDrive Infomaniak ; ce repo ne contient que les outils
et les métadonnées. Règles complètes : [CLAUDE.md](CLAUDE.md).

## Fichiers
| Fichier | Rôle |
|---|---|
| `index.json` | seule source de vérité : photos, dérivés, usages |
| `index.schema.json` | schéma JSON de l'index |
| `vocabulaire.json` | tags autorisés (vocabulaire fermé, enrichissable) |
| `formats.json` | formats de sortie par canal |
| `styles.json` | styles d'étalonnage validés (paramètres exacts) |
| `config.json` | kDrive (racine, dossiers), crédit par défaut, règles |
| `scripts/kdrive.py` | client API kDrive |
| `scripts/importer.py` | import depuis `a-importer/` |
| `scripts/deriver.py` | crops, zooms, formats, styles |
| `scripts/choisir.py` | requêtes et sélection dans l'index |
| `scripts/usages.py` | suivi d'utilisation |
| `skill/SKILL.md` | brouillon du skill « nawashi-photos » (non publié) |

## Mise en route
```sh
pip install -r requirements.txt
export KDRIVE_ID=…       # identifiant du kDrive
export KDRIVE_TOKEN=…    # jeton API Infomaniak, portée « drive » (inutile en session cloud : le proxy l'injecte)
python scripts/kdrive.py check   # vérifie l'accès et crée l'arborescence manquante
python scripts/kdrive.py ls originaux
```

Réseau requis : `api.infomaniak.com` et le serveur de téléchargement du kDrive
(`1-9-v3-12.download.kdrive.infomaniakusercontent.com`).
