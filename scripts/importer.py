"""Import des photos déposées dans a-importer/ sur kDrive.

Flux (« j'ai ajouté des photos ») :
  1. python scripts/importer.py preparer
       liste a-importer/, télécharge chaque JPEG dans cache/, calcule dimensions,
       orientation, empreinte (doublons), date de prise EXIF, génère les previews
       512 et 1000 px en local et une planche contact numérotée.
       Écrit la fiche d'import cache/import/fiche.json.
  2. L'agent regarde la planche (une seule image), rédige pour chaque photo
       "description", "contexte", "tags" (et "zones" facultatives) dans la fiche, puis
       les propose à Flavien.  python scripts/importer.py fiche  affiche la fiche.
  3. Après accord :  python scripts/importer.py valider [--commit]
       attribue l'identifiant <date-import>-<contexte>-<NNN>, renomme et déplace
       l'original vers originaux/, envoie les previews dans previews/512 et previews/1000,
       ajoute l'entrée à index.json (relu juste avant) et commite.
  Abandon d'une photo :  python scripts/importer.py ignorer <n>  (elle reste dans a-importer/)

Le nom de fichier ne porte aucune métadonnée ; tout est dans index.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

import kdrive
from photolib import (REPO, CACHE, CONFIG, aujourdhui, ecrire_index, lire_index, ouvrir,
                      orientation, planche, valider_tags, verifier_slug)

DOSSIER = CACHE / "import"
FICHE = DOSSIER / "fiche.json"
EXTENSIONS = (".jpg", ".jpeg")
QUALITE = CONFIG["regles"]["jpeg_qualite"]["preview"]


def _date_exif(im) -> str | None:
    try:
        exif = im.getexif()
        brut = exif.get_ifd(0x8769).get(0x9003) or exif.get(0x0132)  # DateTimeOriginal / DateTime
        return brut[:10].replace(":", "-") if brut else None
    except Exception:
        return None


def _previews(src: Path, base: str) -> dict[int, Path]:
    im = ouvrir(src).convert("RGB")
    sorties = {}
    for taille in CONFIG["regles"]["preview_tailles"]:
        copie = im.copy()
        copie.thumbnail((taille, taille), resample=3)  # LANCZOS, côté long = taille
        dest = DOSSIER / str(taille) / f"{base}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        copie.save(dest, quality=QUALITE, optimize=True, progressive=True)
        sorties[taille] = dest
    return sorties


def preparer(_args) -> None:
    deja = {p.get("sha256"): p["id"] for p in lire_index()["photos"]}
    ancienne = json.loads(FICHE.read_text()) if FICHE.exists() else {"photos": []}
    connues = {f["kdrive_id"]: f for f in ancienne["photos"]}
    fichiers = [f for f in kdrive.list_dir(kdrive.resolve("a-importer")) if f["type"] == "file"]
    fiche = {"date_import": aujourdhui(), "photos": []}
    for f in sorted(fichiers, key=lambda x: x["name"]):
        if not f["name"].lower().endswith(EXTENSIONS):
            print(f"  ignoré (pas un JPEG) : {f['name']}")
            continue
        if f["id"] in connues:                      # garder ce que l'agent a déjà rédigé
            fiche["photos"].append(connues[f["id"]])
            continue
        local = DOSSIER / "originaux" / f"{f['id']}.jpg"
        if not local.exists():
            kdrive.download(f["id"], local)
        sha = hashlib.sha256(local.read_bytes()).hexdigest()
        im = ouvrir(local)
        l, h = im.size
        prev = _previews(local, str(f["id"]))
        fiche["photos"].append({
            "kdrive_id": f["id"], "nom_import": f["name"], "octets": f.get("size"),
            "sha256": sha, "doublon_de": deja.get(sha),
            "date_prise": _date_exif(im), "largeur": l, "hauteur": h,
            "orientation": orientation(l, h), "ratio": round(l / h, 3),
            "previews_locales": {str(k): str(v) for k, v in prev.items()},
            "type": "photo", "contexte": None, "description": "", "zones": [],
            "tags": {"plan": [], "technique": [], "personnes": None, "ambiance": [],
                     "lumiere": [], "espace-texte": None, "lieu": None},
            "source": None, "licence": None,
        })
    DOSSIER.mkdir(parents=True, exist_ok=True)
    FICHE.write_text(json.dumps(fiche, indent=2, ensure_ascii=False) + "\n")
    if not fiche["photos"]:
        print("a-importer/ est vide.")
        return
    pl = planche([Path(p["previews_locales"]["512"]) for p in fiche["photos"]], DOSSIER / "planche.jpg",
                 [p["nom_import"] for p in fiche["photos"]])
    for i, p in enumerate(fiche["photos"], 1):
        alerte = f"  ⚠ DOUBLON de {p['doublon_de']}" if p["doublon_de"] else ""
        print(f"{i}. {p['nom_import']}  {p['largeur']}×{p['hauteur']} {p['orientation']}"
              f"  prise {p['date_prise'] or '?'}{alerte}")
    print(f"\nPlanche : {pl}\nFiche à compléter : {FICHE}")


def afficher(_args) -> None:
    fiche = json.loads(FICHE.read_text())
    for i, p in enumerate(fiche["photos"], 1):
        print(f"{i}. {p['nom_import']} — contexte : {p['contexte']}\n   {p['description']}\n   tags : "
              + json.dumps(p["tags"], ensure_ascii=False))


def ignorer(args) -> None:
    fiche = json.loads(FICHE.read_text())
    retiree = fiche["photos"].pop(args.numero - 1)
    FICHE.write_text(json.dumps(fiche, indent=2, ensure_ascii=False) + "\n")
    print(f"Retirée de l'import (reste dans a-importer/) : {retiree['nom_import']}")


def _prochain_numero(index: dict, prefixe: str, pris: set[str]) -> str:
    n = 1
    existants = {p["id"] for p in index["photos"]} | pris
    while f"{prefixe}-{n:03d}" in existants:
        n += 1
    return f"{prefixe}-{n:03d}"


def _controler(p: dict) -> None:
    if p["doublon_de"]:
        raise ValueError(f"{p['nom_import']} est un doublon de {p['doublon_de']} : `ignorer` d'abord")
    if not p["description"].strip():
        raise ValueError(f"{p['nom_import']} : description manquante")
    verifier_slug(p["contexte"] or "", "contexte")
    valider_tags({"contexte": p["contexte"]})
    valider_tags(p["tags"])
    if p["type"] == "illustration" and not (p.get("source") and p.get("licence")):
        raise ValueError(f"{p['nom_import']} : une illustration exige source et licence")


def valider(args) -> None:
    fiche = json.loads(FICHE.read_text())
    if not fiche["photos"]:
        sys.exit("Rien à valider.")
    for p in fiche["photos"]:
        _controler(p)
    if len({p["kdrive_id"] for p in fiche["photos"]}) != len(fiche["photos"]):
        raise ValueError("fiche incohérente (photo en double)")
    date_import = aujourdhui()
    dossier_orig = kdrive.resolve("originaux")
    faites = []
    while fiche["photos"]:
        p = fiche["photos"][0]
        ident = _prochain_numero(lire_index(), f"{date_import}-{p['contexte']}", set())
        nom = f"{ident}.jpg"
        # original : renommer puis déplacer (jamais réencodé)
        kdrive.rename(p["kdrive_id"], nom)
        kdrive.move(p["kdrive_id"], dossier_orig)
        fichiers = {"original": {"chemin": f"originaux/{nom}", "id": p["kdrive_id"],
                                 "largeur": p["largeur"], "hauteur": p["hauteur"], "octets": p["octets"]}}
        for taille, local in p["previews_locales"].items():
            res = kdrive.upload(Path(local), kdrive.resolve(f"previews/{taille}"), nom, conflict="error")
            res = res.get("file", res)
            with Image.open(local) as im:
                lp, hp = im.size
            fichiers[f"preview_{taille}"] = {"chemin": f"previews/{taille}/{nom}", "id": res["id"],
                                             "largeur": lp, "hauteur": hp, "octets": Path(local).stat().st_size}
            cible = CACHE / "previews" / taille / nom          # garder en cache local
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(local, cible)
        entree = {
            "id": ident, "type": p["type"], "date_prise": p["date_prise"],
            "nom_import": p["nom_import"], "sha256": p["sha256"], "fichiers": fichiers,
            "largeur": p["largeur"], "hauteur": p["hauteur"],
            "orientation": p["orientation"], "ratio": p["ratio"],
            "description": p["description"].strip(), "zones": p.get("zones", []),
            "tags": valider_tags({**p["tags"], "contexte": p["contexte"]}),
            "credit": None, "autorisation": {"statut": "ecrit-confirme", "depuis": date_import},
            "personnes_mentionnees": [], "source": p.get("source"), "licence": p.get("licence"),
            "importe_le": date_import, "derives": [], "usages": [],
        }
        # index écrit après chaque photo : un plantage au milieu laisse un état cohérent
        ecrire_index(lambda idx: idx["photos"].append(entree), commit=False)
        fiche["photos"].pop(0)
        FICHE.write_text(json.dumps(fiche, indent=2, ensure_ascii=False) + "\n")
        faites.append(ident)
        print(f"✓ {p['nom_import']} → {ident}")
    if args.commit and faites:
        subprocess.run(["git", "-C", str(REPO), "add", "index.json"], check=True)
        subprocess.run(["git", "-C", str(REPO), "commit", "-q", "-m",
                        f"Import de {len(faites)} photo(s) : " + ", ".join(faites)], check=True)
    shutil.rmtree(DOSSIER)
    print(f"index.json mis à jour ({len(faites)} photo(s))" + (" et commité." if args.commit else "."))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preparer").set_defaults(f=preparer)
    sub.add_parser("fiche").set_defaults(f=afficher)
    s = sub.add_parser("ignorer"); s.add_argument("numero", type=int); s.set_defaults(f=ignorer)
    s = sub.add_parser("valider"); s.add_argument("--commit", action="store_true"); s.set_defaults(f=valider)
    args = ap.parse_args()
    try:
        args.f(args)
    except (ValueError, KeyError, kdrive.KDriveError) as e:
        sys.exit(f"Erreur : {e}")


if __name__ == "__main__":
    main()
