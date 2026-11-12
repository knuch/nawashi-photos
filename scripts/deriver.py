"""Déclinaisons d'une photo : crop, zoom, format par canal, style.

Uniquement recadrer, redimensionner et étalonner (Pillow). Aucune génération, aucun
remplissage, aucune extension d'image : si le cadre ne tient pas dans la photo, erreur.
Les cadres sont en pixels de l'original une fois l'orientation EXIF appliquée.

  python scripts/deriver.py creer <id-photo> --nature crop|zoom|format|style
        [--format insta-4x5]            clé de formats.json (taille et ratio de sortie)
        [--sujet mains]                 ce que montre le crop/zoom (entre dans le nom)
        [--cadre x,y,l,h]               cadre exact en px
        [--zone mains]                  cadre ajusté autour d'une zone de l'index
        [--centre 0.6,0.4]              centre du cadre en fractions (défaut : centre)
        [--echelle 0.5]                 taille du cadre / plus grand cadre possible (zoom)
        [--style nb]                    style validé de styles.json
        [--etalonnage '{"contraste":1.1}' --nom-style chaud]   proposition de style
        [--agrandir]                    autorise un agrandissement (sinon refusé)
     → crée le fichier, l'envoie dans derives/, l'ajoute à l'index en « proposition ».
  python scripts/deriver.py galerie [--photo <id>] [--html]
     → numérote toutes les propositions : planche contact JPEG (+ page HTML) dans cache/galerie/
  python scripts/deriver.py trier --retirer 2,5 [--commit]
     → numéros de la dernière galerie : retirés = supprimés de kDrive et de l'index,
       les autres passent en « valide ».  (--retirer aucun : tout valider)
  python scripts/deriver.py regenerer <id-derive>   → refait le fichier depuis sa recette (cache/)
  python scripts/deriver.py valider-style <nom> --depuis <id-derive> [--commit]
     → inscrit l'étalonnage exact de ce dérivé comme style dans styles.json

Étalonnage — clés et ordre d'application (identiques pour styles et ajustements ponctuels) :
  chaleur (-1…1, R×(1+0,1c) et B×(1−0,1c)) → luminosite → contraste → saturation (facteurs
  ImageEnhance, 1 = neutre) → noir_blanc (true : niveaux de gris ITU-R 601) → nettete (facteur).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageEnhance

import kdrive
from photolib import (CACHE, CONFIG, REPO, aujourdhui, charger, ecrire_index, en_cache,
                      lire_index, ouvrir, photo, planche, trouver, verifier_slug)

QUALITE = CONFIG["regles"]["jpeg_qualite"]["derive"]
GALERIE = CACHE / "galerie"
CLES = ["chaleur", "luminosite", "contraste", "saturation", "noir_blanc", "nettete"]


# --- traitement d'image -------------------------------------------------------

def etalonner(im: Image.Image, params: dict) -> Image.Image:
    inconnues = set(params) - set(CLES)
    if inconnues:
        raise ValueError(f"paramètres d'étalonnage inconnus : {', '.join(sorted(inconnues))}")
    im = im.convert("RGB")
    if params.get("chaleur"):
        c = float(params["chaleur"])
        r, g, b = im.split()
        r = r.point(lambda v: min(255, round(v * (1 + 0.1 * c))))
        b = b.point(lambda v: min(255, round(v * (1 - 0.1 * c))))
        im = Image.merge("RGB", (r, g, b))
    for cle, classe in (("luminosite", ImageEnhance.Brightness), ("contraste", ImageEnhance.Contrast),
                        ("saturation", ImageEnhance.Color)):
        if cle in params and params[cle] != 1:
            im = classe(im).enhance(float(params[cle]))
    if params.get("noir_blanc"):
        im = im.convert("L").convert("RGB")
    if "nettete" in params and params["nettete"] != 1:
        im = ImageEnhance.Sharpness(im).enhance(float(params["nettete"]))
    return im


def produire(original: Path, recette: dict, dest: Path) -> Path:
    im = ouvrir(original)
    icc = im.info.get("icc_profile")
    c = recette["cadre"]
    im = im.crop((c["x"], c["y"], c["x"] + c["l"], c["y"] + c["h"]))
    s = recette["sortie"]
    if (s["largeur"], s["hauteur"]) != im.size:
        im = im.resize((s["largeur"], s["hauteur"]), Image.LANCZOS)
    im = etalonner(im, recette.get("etalonnage") or {})
    dest.parent.mkdir(parents=True, exist_ok=True)
    opts = {"quality": QUALITE, "optimize": True, "progressive": True}
    if icc:
        opts["icc_profile"] = icc            # garder le profil couleur, pas d'EXIF ni métadonnées
    im.save(dest, **opts)
    return dest


def calculer_cadre(p: dict, ratio: float | None, args) -> dict:
    L, H = p["largeur"], p["hauteur"]
    if args.cadre:
        x, y, l, h = (int(v) for v in args.cadre.split(","))
        if ratio and abs(l / h - ratio) / ratio > 0.01:
            raise ValueError(f"cadre {l}×{h} : ratio {l/h:.3f} ≠ format {ratio:.3f}")
    else:
        ratio = ratio or L / H
        cx, cy = (float(v) for v in args.centre.split(",")) if args.centre else (0.5, 0.5)
        lmax = min(L, H * ratio)                     # plus grand cadre au ratio voulu
        if args.zone:
            z = next((z for z in p.get("zones", []) if z["nom"] == args.zone), None)
            if not z:
                raise ValueError(f"zone « {args.zone} » absente de {p['id']}")
            cx, cy = z["x"] + z["l"] / 2, z["y"] + z["h"] / 2
            l = max(z["l"] * L, z["h"] * H * ratio) * 1.08   # petite marge autour de la zone
            l = min(l, lmax)
        else:
            l = lmax * (args.echelle or 1)
        h = l / ratio
        l, h = round(l), round(h)
        x = round(min(max(cx * L - l / 2, 0), L - l))
        y = round(min(max(cy * H - h / 2, 0), H - h))
    if x < 0 or y < 0 or x + l > L or y + h > H:
        raise ValueError(f"le cadre {x},{y},{l},{h} sort de la photo ({L}×{H}) : pas d'extension d'image")
    return {"x": x, "y": y, "l": l, "h": h}


# --- commandes ----------------------------------------------------------------------

def creer(args) -> None:
    index = lire_index()
    p = photo(index, args.id)
    if p["autorisation"]["statut"] == "retire":
        raise ValueError(f"{p['id']} est retirée")
    fmt = charger("formats.json")[args.format] if args.format else None
    ratio = fmt["largeur"] / fmt["hauteur"] if fmt and fmt["hauteur"] else None
    cadre = calculer_cadre(p, ratio, args)
    if fmt:
        lo = fmt["largeur"]
        ho = fmt["hauteur"] or round(cadre["h"] * lo / cadre["l"])
    else:
        lo, ho = cadre["l"], cadre["h"]
    if lo > cadre["l"] and not args.agrandir:
        raise ValueError(f"le cadre ({cadre['l']} px de large) est plus petit que la sortie ({lo} px) : "
                         f"cadre plus large, autre photo, ou --agrandir (×{lo / cadre['l']:.2f})")
    etal = {}
    style = None
    if args.style:
        styles = charger("styles.json")
        if args.style not in styles:
            raise ValueError(f"style « {args.style} » non validé (styles.json : {', '.join(styles) or 'vide'})")
        etal.update(styles[args.style]["parametres"])
        style = args.style
    if args.etalonnage:
        etal.update(json.loads(args.etalonnage))
        style = args.nom_style or style
        if not style:
            raise ValueError("--etalonnage exige --nom-style (nom du style proposé)")
    parties = [p["id"], args.nature, args.sujet, args.format, style]
    base = "-".join(verifier_slug(x, "partie de nom") for x in parties if x)
    existants = {d["id"] for d in p["derives"]}
    ident, n = base, 2
    while ident in existants:
        ident, n = f"{base}-{n}", n + 1
    recette = {"cadre": cadre, "sortie": {"largeur": lo, "hauteur": ho}}
    if etal:
        recette["etalonnage"] = etal
    local = produire(en_cache(p["fichiers"]["original"]), recette, CACHE / "derives" / f"{ident}.jpg")
    res = kdrive.upload(local, kdrive.resolve("derives"), f"{ident}.jpg")
    res = res.get("file", res)
    derive = {"id": ident, "nature": args.nature, "sujet": args.sujet, "format": args.format,
              "style": style, "fichier": {"chemin": f"derives/{ident}.jpg", "id": res["id"],
                                          "largeur": lo, "hauteur": ho, "octets": local.stat().st_size},
              "recette": recette, "statut": "proposition", "cree_le": aujourdhui()}
    ecrire_index(lambda idx: photo(idx, p["id"])["derives"].append(derive), commit=False)
    print(f"proposition : {ident}  ({lo}×{ho}, cadre {cadre})\n  local : {local}")


def galerie(args) -> None:
    props = [(p, d) for p in lire_index()["photos"] for d in p["derives"]
             if d["statut"] == "proposition" and (not args.photo or p["id"] == args.photo)]
    if not props:
        print("Aucune proposition en attente.")
        return
    chemins = [CACHE / d["fichier"]["chemin"] if (CACHE / d["fichier"]["chemin"]).exists()
               else en_cache(d["fichier"]) for _, d in props]
    GALERIE.mkdir(parents=True, exist_ok=True)
    (GALERIE / "galerie.json").write_text(json.dumps([d["id"] for _, d in props], indent=1))
    pl = planche(chemins, GALERIE / "planche.jpg", [d["id"].removeprefix(p["id"] + "-") for p, d in props])
    print(f"{len(props)} proposition(s) :")
    for i, (_, d) in enumerate(props, 1):
        print(f"  {i}. {d['id']}")
    print(f"Planche : {pl}")
    if args.html:
        print(f"HTML : {_html(props, chemins)}")


def _html(props, chemins) -> Path:
    cartes = []
    for i, ((p, d), c) in enumerate(zip(props, chemins), 1):
        im = Image.open(c).convert("RGB")
        im.thumbnail((560, 560))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=78)
        b64 = base64.b64encode(buf.getvalue()).decode()
        cartes.append(f'<figure><span class="n">{i}</span><img src="data:image/jpeg;base64,{b64}" '
                      f'alt="Proposition {i}"><figcaption>{d["id"].removeprefix(p["id"] + "-")}'
                      f'<small>{p["id"]} · {d["fichier"]["largeur"]}×{d["fichier"]["hauteur"]}</small>'
                      f'</figcaption></figure>')
    page = GALERIE / "galerie.html"
    page.write_text(GABARIT.replace("{{CARTES}}", "\n".join(cartes)).replace("{{N}}", str(len(props))),
                    encoding="utf-8")
    return page


def trier(args) -> None:
    ordre = json.loads((GALERIE / "galerie.json").read_text())
    retirer = set() if args.retirer.strip().lower() == "aucun" else {int(x) for x in args.retirer.split(",") if x.strip()}
    if not retirer <= set(range(1, len(ordre) + 1)):
        raise ValueError(f"numéros hors galerie (1–{len(ordre)})")
    a_retirer = {ordre[i - 1] for i in retirer}
    index = lire_index()
    for ident in ordre:
        _, d = trouver(index, ident)
        if d is None or d["statut"] != "proposition":
            raise ValueError(f"{ident} n'est plus une proposition : refaire la galerie")
    for ident in a_retirer:                      # kDrive d'abord, puis l'index
        _, d = trouver(index, ident)
        kdrive.trash(d["fichier"]["id"])
        (CACHE / d["fichier"]["chemin"]).unlink(missing_ok=True)

    def modif(idx):
        for p in idx["photos"]:
            p["derives"] = [d for d in p["derives"] if d["id"] not in a_retirer]
            for d in p["derives"]:
                if d["id"] in ordre:
                    d["statut"], d["valide_le"] = "valide", aujourdhui()

    ecrire_index(modif, commit=False)
    gardes = [i for i in ordre if i not in a_retirer]
    if args.commit:
        _commit(f"Dérivés : {len(gardes)} validé(s), {len(a_retirer)} retiré(s)")
    (GALERIE / "galerie.json").unlink()
    print(f"validés : {len(gardes)} ; supprimés de kDrive : {len(a_retirer)}")


def regenerer(args) -> None:
    p, d = trouver(lire_index(), args.id)
    if not d:
        raise ValueError(f"{args.id} n'est pas un dérivé")
    print(produire(en_cache(p["fichiers"]["original"]), d["recette"], CACHE / "regeneres" / f"{d['id']}.jpg"))


def valider_style(args) -> None:
    verifier_slug(args.nom, "nom de style")
    _, d = trouver(lire_index(), args.depuis)
    if not d or not d["recette"].get("etalonnage"):
        raise ValueError(f"{args.depuis} n'a pas d'étalonnage à reprendre")
    chemin = REPO / "styles.json"
    styles = json.loads(chemin.read_text(encoding="utf-8"))
    if args.nom in styles:
        raise ValueError(f"le style « {args.nom} » existe déjà")
    styles[args.nom] = {"parametres": d["recette"]["etalonnage"], "valide_le": aujourdhui(),
                        "exemple": d["id"]}
    chemin.write_text(json.dumps(styles, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.commit:
        subprocess.run(["git", "-C", str(REPO), "add", "styles.json"], check=True)
        subprocess.run(["git", "-C", str(REPO), "commit", "-q", "-m", f"Style validé : {args.nom}"], check=True)
    print(f"style « {args.nom} » : {styles[args.nom]['parametres']}")


def _commit(message: str) -> None:
    subprocess.run(["git", "-C", str(REPO), "add", "index.json"], check=True)
    subprocess.run(["git", "-C", str(REPO), "commit", "-q", "-m", message], check=True)


GABARIT = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Propositions de dérivés</title>
<style>
:root{--fond:#f5f0e8;--texte:#3c281e;--carte:#fffaf3;--accent:#7a4a2e;--doux:#8a7566}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--fond:#1d1814;--texte:#efe6dc;--carte:#2a231d;--accent:#d29a6c;--doux:#a8968a}}
:root[data-theme="dark"]{--fond:#1d1814;--texte:#efe6dc;--carte:#2a231d;--accent:#d29a6c;--doux:#a8968a}
*{box-sizing:border-box}body{margin:0;background:var(--fond);color:var(--texte);font:16px/1.4 system-ui,sans-serif;padding:24px 16px}
h1{font-weight:500;font-size:1.4rem;margin:0 0 4px}p{color:var(--doux);margin:0 0 20px}
.grille{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}
figure{margin:0;background:var(--carte);border-radius:10px;overflow:hidden;position:relative}
img{display:block;width:100%;height:auto}
.n{position:absolute;top:8px;left:8px;background:var(--accent);color:#fff;font-weight:700;min-width:34px;height:34px;border-radius:17px;display:grid;place-items:center;font-size:1.05rem}
figcaption{padding:8px 10px;font-size:.85rem;word-break:break-all}small{display:block;color:var(--doux)}
</style></head><body>
<h1>{{N}} propositions</h1><p>Indique les numéros à retirer ; les autres seront validées.</p>
<div class="grille">
{{CARTES}}
</div></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("creer")
    s.add_argument("id"); s.add_argument("--nature", required=True, choices=["crop", "zoom", "format", "style"])
    s.add_argument("--format"); s.add_argument("--sujet"); s.add_argument("--cadre"); s.add_argument("--zone")
    s.add_argument("--centre"); s.add_argument("--echelle", type=float); s.add_argument("--style")
    s.add_argument("--etalonnage"); s.add_argument("--nom-style"); s.add_argument("--agrandir", action="store_true")
    s.set_defaults(f=creer)
    s = sub.add_parser("galerie"); s.add_argument("--photo"); s.add_argument("--html", action="store_true")
    s.set_defaults(f=galerie)
    s = sub.add_parser("trier"); s.add_argument("--retirer", required=True)
    s.add_argument("--commit", action="store_true"); s.set_defaults(f=trier)
    s = sub.add_parser("regenerer"); s.add_argument("id"); s.set_defaults(f=regenerer)
    s = sub.add_parser("valider-style"); s.add_argument("nom"); s.add_argument("--depuis", required=True)
    s.add_argument("--commit", action="store_true"); s.set_defaults(f=valider_style)
    args = ap.parse_args()
    try:
        args.f(args)
    except (KeyError, ValueError, kdrive.KDriveError) as e:
        sys.exit(f"Erreur : {e}")


if __name__ == "__main__":
    main()
