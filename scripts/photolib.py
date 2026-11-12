"""Fonctions communes : index.json, vocabulaire, règles d'utilisation, cache local, images."""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "index.json"
CACHE = REPO / "cache"            # images téléchargées / générées localement (gitignoré)
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def charger(nom: str) -> dict:
    return json.loads((REPO / nom).read_text(encoding="utf-8"))


CONFIG = charger("config.json")


def aujourdhui() -> str:
    return dt.date.today().isoformat()


def date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def verifier_slug(s: str, quoi: str = "nom") -> str:
    if not SLUG.match(s):
        raise ValueError(f"{quoi} invalide « {s} » : minuscules, chiffres et traits d'union seulement")
    return s


# --- index.json ------------------------------------------------------------

def lire_index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def ecrire_index(modifier: Callable[[dict], object], message: str | None = None, commit: bool = True):
    """Relit index.json, applique `modifier` (qui ne touche que les entrées concernées),
    valide, écrit, puis commite index.json si `commit`. Renvoie le résultat de `modifier`."""
    index = lire_index()
    resultat = modifier(index)
    valider_index(index)
    INDEX.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if commit and message:
        subprocess.run(["git", "-C", str(REPO), "add", "index.json"], check=True)
        subprocess.run(["git", "-C", str(REPO), "commit", "-q", "-m", message], check=True)
    return resultat


def photo(index: dict, ident: str) -> dict:
    for p in index["photos"]:
        if p["id"] == ident:
            return p
    raise KeyError(f"photo inconnue : {ident}")


def trouver(index: dict, ident: str) -> tuple[dict, dict | None]:
    """(photo, dérivé ou None) pour un id de photo ou de dérivé."""
    for p in index["photos"]:
        if p["id"] == ident:
            return p, None
        for d in p.get("derives", []):
            if d["id"] == ident:
                return p, d
    raise KeyError(f"id inconnu (ni photo ni dérivé) : {ident}")


# --- vocabulaire -----------------------------------------------------------

def valider_tags(tags: dict) -> dict:
    voc = charger("vocabulaire.json")
    propres = {}
    for cle, val in tags.items():
        if cle not in voc or cle.startswith("_") or cle == "type":
            raise ValueError(f"catégorie de tag inconnue : {cle}")
        regle = voc[cle]
        valeurs = [val] if isinstance(val, str) else list(val or [])
        for v in valeurs:
            if v not in regle["valeurs"]:
                raise ValueError(f"valeur « {v} » absente du vocabulaire pour « {cle} » "
                                 f"(autorisées : {', '.join(regle['valeurs']) or 'aucune'})")
        if regle["unique"]:
            if len(valeurs) > 1:
                raise ValueError(f"« {cle} » n'accepte qu'une valeur")
            propres[cle] = valeurs[0] if valeurs else None
        else:
            propres[cle] = valeurs
    return propres


def valider_index(index: dict) -> None:
    """Contrôles essentiels (sans dépendance jsonschema)."""
    ids = set()
    for p in index["photos"]:
        for ident in [p["id"]] + [d["id"] for d in p.get("derives", [])]:
            verifier_slug(ident, "id")
            if ident in ids:
                raise ValueError(f"id en double : {ident}")
            ids.add(ident)
        if p["type"] not in ("photo", "illustration"):
            raise ValueError(f"{p['id']} : type invalide")
        if p["autorisation"]["statut"] not in ("ecrit-confirme", "retire"):
            raise ValueError(f"{p['id']} : statut d'autorisation invalide")
        if p["type"] == "illustration" and not (p.get("source") and p.get("licence")):
            raise ValueError(f"{p['id']} : une illustration doit avoir source et licence")
        valider_tags(p["tags"])
        for d in p.get("derives", []):
            if d["statut"] not in ("proposition", "valide"):
                raise ValueError(f"{d['id']} : statut de dérivé invalide")
        for u in p.get("usages", []):
            if u["statut"] not in ("prevu", "annule"):
                raise ValueError(f"{u['id']} : statut d'usage invalide")


# --- règles d'utilisation ---------------------------------------------------

def usages_actifs(p: dict) -> list[dict]:
    return [u for u in p.get("usages", []) if u["statut"] == "prevu"]


def conflit_usage(p: dict, cible: str | None = None) -> dict | None:
    """Premier usage « prevu » de la photo (dérivés compris, car rangés sur la photo)
    à moins de N jours (avant OU après) de la date cible ; None si la photo est libre."""
    jours = CONFIG["regles"]["exclusion_jours"]
    c = date(cible or aujourdhui())
    for u in usages_actifs(p):
        if abs((date(u["date"]) - c).days) < jours:
            return u
    return None


def disponible(p: dict, cible: str | None = None, inclure_recentes: bool = False) -> bool:
    if p["autorisation"]["statut"] == "retire":
        return False
    return inclure_recentes or conflit_usage(p, cible) is None


# --- kDrive + cache ----------------------------------------------------------

def en_cache(fichier: dict) -> Path:
    """Télécharge (si besoin) un fichier kDrive {chemin, id} dans cache/<chemin>."""
    import kdrive
    dest = CACHE / fichier["chemin"]
    if not dest.exists():
        kdrive.download(fichier["id"], dest)
    return dest


# --- images -------------------------------------------------------------------

def ouvrir(path: Path):
    """Ouvre une image avec l'orientation EXIF appliquée (repère de tous les cadres)."""
    from PIL import Image, ImageOps
    im = Image.open(path)
    return ImageOps.exif_transpose(im)


def orientation(l: int, h: int) -> str:
    r = l / h
    return "carre" if 0.95 <= r <= 1.05 else ("paysage" if r > 1 else "portrait")


def planche(images: list[Path], dest: Path, legendes: list[str] | None = None,
            vignette: int = 360, colonnes: int = 4):
    """Planche contact JPEG numérotée (1, 2, 3…) — une seule image à regarder."""
    from PIL import Image, ImageDraw, ImageFont
    n = len(images)
    colonnes = min(colonnes, n) or 1
    lignes = (n + colonnes - 1) // colonnes
    marge, bandeau = 12, 44
    W = colonnes * (vignette + marge) + marge
    H = lignes * (vignette + bandeau + marge) + marge
    feuille = Image.new("RGB", (W, H), (245, 240, 232))
    dessin = ImageDraw.Draw(feuille)
    try:
        police = ImageFont.load_default(size=26)
        petite = ImageFont.load_default(size=13)
    except TypeError:
        police = petite = ImageFont.load_default()
    for i, path in enumerate(images):
        im = ouvrir(path).convert("RGB")
        im.thumbnail((vignette, vignette))
        x = marge + (i % colonnes) * (vignette + marge)
        y = marge + (i // colonnes) * (vignette + bandeau + marge)
        feuille.paste(im, (x + (vignette - im.width) // 2, y + bandeau + (vignette - im.height) // 2))
        dessin.rectangle([x, y, x + 40, y + 36], fill=(60, 40, 30))
        dessin.text((x + 8, y + 3), str(i + 1), fill="white", font=police)
        if legendes:
            dessin.text((x + 48, y + 12), legendes[i][:48], fill=(60, 40, 30), font=petite)
    dest.parent.mkdir(parents=True, exist_ok=True)
    feuille.save(dest, quality=85)
    return dest
