"""Choisir des photos par l'index, sans ouvrir d'image.

  python scripts/choisir.py chercher [filtres] [--date AAAA-MM-JJ] [--limite N] [--json]
      Filtres de tags : --plan mains --technique suspension --contexte rope-jam
        --personnes duo --ambiance intime --lumiere naturelle --espace-texte oui --lieu bulle
        (répéter une option = OU ; options différentes = ET)
      --type photo|illustration   --orientation paysage|portrait|carre
      --format insta-4x5          ne garde que les photos assez grandes pour ce format
      --texte mot                 cherche dans la description
      --inclure-recentes          lève la règle des 28 jours (demande explicite de Flavien)
      Exclut toujours les photos « retire ». Tri : moins utilisées d'abord, puis plus ancien usage.
  python scripts/choisir.py voir <id>          fiche complète d'une photo (JSON)
  python scripts/choisir.py preview <id> [512|1000]   télécharge la preview dans cache/ et
      affiche son chemin (à n'ouvrir que pour vérifier un choix, en 512 de préférence)
  python scripts/choisir.py planche <id> <id> …       planche contact numérotée des previews 512
"""
from __future__ import annotations

import argparse
import json
import sys

from photolib import (CACHE, aujourdhui, charger, conflit_usage, disponible, en_cache,
                      lire_index, planche, trouver, usages_actifs)

CATEGORIES = ["plan", "technique", "contexte", "personnes", "ambiance", "lumiere", "espace-texte", "lieu"]


def _correspond(p: dict, args) -> bool:
    for cat in CATEGORIES:
        voulues = getattr(args, cat.replace("-", "_"))
        if voulues:
            val = p["tags"].get(cat)
            vals = val if isinstance(val, list) else [val]
            if not set(voulues) & set(vals):
                return False
    if args.type and p["type"] != args.type:
        return False
    if args.orientation and p["orientation"] not in args.orientation:
        return False
    if args.texte and args.texte.lower() not in p["description"].lower():
        return False
    if args.format:
        f = charger("formats.json")[args.format]
        if f["hauteur"] is None:
            ok = p["largeur"] >= f["largeur"]
        else:  # plus grand cadre au bon ratio qui tient dans la photo
            r = f["largeur"] / f["hauteur"]
            l = min(p["largeur"], p["hauteur"] * r)
            ok = l >= f["largeur"]
        if not ok:
            return False
    return True


def chercher(args) -> None:
    cible = args.date or aujourdhui()
    res, exclues = [], 0
    for p in lire_index()["photos"]:
        if not _correspond(p, args):
            continue
        if not disponible(p, cible, args.inclure_recentes):
            exclues += 1
            continue
        actifs = usages_actifs(p)
        res.append((len(actifs), max((u["date"] for u in actifs), default=""), p))
    res.sort(key=lambda t: (t[0], t[1], t[2]["id"]))
    res = res[: args.limite]
    if args.json:
        print(json.dumps([{"id": p["id"], "usages": n, "dernier_usage": d or None,
                           "orientation": p["orientation"], "description": p["description"],
                           "tags": p["tags"], "derives_valides": [x["id"] for x in p["derives"]
                                                                if x["statut"] == "valide"]}
                          for n, d, p in res], ensure_ascii=False, indent=1))
    else:
        for n, d, p in res:
            print(f"{p['id']}  [{p['orientation']}, {n} usage(s){', dernier ' + d if d else ''}]\n"
                  f"   {p['description'][:160]}")
    print(f"— {len(res)} résultat(s) ; {exclues} exclue(s) (retirée ou utilisée à ±28 j du {cible})",
          file=sys.stderr)


def voir(args) -> None:
    p, d = trouver(lire_index(), args.id)
    print(json.dumps(d or p, ensure_ascii=False, indent=1))
    if not d:
        c = conflit_usage(p)
        if c:
            print(f"⚠ indisponible aujourd'hui : usage {c['id']} du {c['date']}", file=sys.stderr)


def preview(args) -> None:
    p, _ = trouver(lire_index(), args.id)
    print(en_cache(p["fichiers"][f"preview_{args.taille}"]))


def faire_planche(args) -> None:
    index = lire_index()
    photos = [trouver(index, i)[0] for i in args.ids]
    chemins = [en_cache(p["fichiers"]["preview_512"]) for p in photos]
    print(planche(chemins, CACHE / "planches" / "choix.jpg", [p["id"] for p in photos]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("chercher")
    for cat in CATEGORIES:
        s.add_argument(f"--{cat}", action="append")
    s.add_argument("--type", choices=["photo", "illustration"])
    s.add_argument("--orientation", action="append", choices=["paysage", "portrait", "carre"])
    s.add_argument("--format")
    s.add_argument("--texte")
    s.add_argument("--date")
    s.add_argument("--inclure-recentes", action="store_true")
    s.add_argument("--limite", type=int, default=10)
    s.add_argument("--json", action="store_true")
    s.set_defaults(f=chercher)
    s = sub.add_parser("voir"); s.add_argument("id"); s.set_defaults(f=voir)
    s = sub.add_parser("preview"); s.add_argument("id"); s.add_argument("taille", nargs="?", default="512",
                                                                       choices=["512", "1000"])
    s.set_defaults(f=preview)
    s = sub.add_parser("planche"); s.add_argument("ids", nargs="+"); s.set_defaults(f=faire_planche)
    args = ap.parse_args()
    try:
        args.f(args)
    except (KeyError, ValueError) as e:
        sys.exit(f"Erreur : {e}")


if __name__ == "__main__":
    main()
