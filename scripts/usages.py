"""Suivi d'utilisation des photos.

Une utilisation compte dès que le visuel final est livré : l'enregistrer à ce moment-là.
Un dérivé compte pour sa photo d'origine (l'usage est rangé sur la photo, avec l'id du dérivé).

  python scripts/usages.py ajouter <id-photo-ou-derive> --canal instagram --skill nawashi-evenements
          [--reference slug-ou-url] [--date AAAA-MM-JJ (date de publication, défaut aujourd'hui)]
          [--note …] [--forcer]   (--forcer = demande explicite de Flavien malgré la règle des 28 jours)
  python scripts/usages.py annuler <id-usage> [--note …]
  python scripts/usages.py lister [--photo <id>] [--depuis AAAA-MM-JJ] [--tous]
Ajoute --commit pour commiter index.json.
"""
from __future__ import annotations

import argparse
import sys

from photolib import (aujourdhui, conflit_usage, date, ecrire_index, lire_index, trouver,
                      verifier_slug)


def ajouter(args) -> None:
    jour = args.date or aujourdhui()
    date(jour)

    def modif(index):
        p, d = trouver(index, args.id)
        if p["autorisation"]["statut"] == "retire":
            raise ValueError(f"{p['id']} est retirée : aucune utilisation possible")
        if d and d["statut"] != "valide":
            raise ValueError(f"le dérivé {d['id']} n'est pas validé")
        c = conflit_usage(p, jour)
        if c and not args.forcer:
            raise ValueError(f"{p['id']} a déjà un usage le {c['date']} ({c['canal']}, {c['id']}) "
                             f"à moins de 28 jours : choisir une autre photo, ou --forcer sur demande explicite")
        tous = [u["id"] for x in index["photos"] for u in x["usages"] if u["id"].startswith(f"u-{jour}-")]
        n = 1
        while f"u-{jour}-{n:03d}" in tous:
            n += 1
        u = {"id": f"u-{jour}-{n:03d}", "date": jour, "canal": verifier_slug(args.canal, "canal"),
             "skill": args.skill, "reference": args.reference, "derive": d["id"] if d else None,
             "statut": "prevu", "note": args.note}
        p["usages"].append(u)
        return p, u

    p, u = ecrire_index(modif, None, commit=False)
    if args.commit:
        _commit(f"Usage {u['id']} : {args.id} ({u['canal']}, {u['skill']})")
    print(f"{u['id']} enregistré pour {p['id']} — {u['canal']} le {u['date']}")


def annuler(args) -> None:
    def modif(index):
        for p in index["photos"]:
            for u in p["usages"]:
                if u["id"] == args.id:
                    u["statut"] = "annule"
                    if args.note:
                        u["note"] = args.note
                    return p
        raise KeyError(f"usage inconnu : {args.id}")

    p = ecrire_index(modif, commit=False)
    if args.commit:
        _commit(f"Usage {args.id} annulé ({p['id']})")
    print(f"{args.id} annulé ({p['id']})")


def lister(args) -> None:
    for p in lire_index()["photos"]:
        if args.photo and p["id"] != args.photo:
            continue
        for u in sorted(p["usages"], key=lambda x: x["date"]):
            if u["statut"] == "annule" and not args.tous:
                continue
            if args.depuis and u["date"] < args.depuis:
                continue
            print(f"{u['id']}  {u['date']}  {u['statut']:<7} {u['canal']:<16} {u['skill']:<24} "
                  f"{u['derive'] or p['id']}  {u.get('reference') or ''}")


def _commit(message: str) -> None:
    import subprocess
    from photolib import REPO
    subprocess.run(["git", "-C", str(REPO), "add", "index.json"], check=True)
    subprocess.run(["git", "-C", str(REPO), "commit", "-q", "-m", message], check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("ajouter")
    s.add_argument("id"); s.add_argument("--canal", required=True); s.add_argument("--skill", required=True)
    s.add_argument("--reference"); s.add_argument("--date"); s.add_argument("--note")
    s.add_argument("--forcer", action="store_true"); s.add_argument("--commit", action="store_true")
    s.set_defaults(f=ajouter)
    s = sub.add_parser("annuler"); s.add_argument("id"); s.add_argument("--note")
    s.add_argument("--commit", action="store_true"); s.set_defaults(f=annuler)
    s = sub.add_parser("lister"); s.add_argument("--photo"); s.add_argument("--depuis")
    s.add_argument("--tous", action="store_true"); s.set_defaults(f=lister)
    args = ap.parse_args()
    try:
        args.f(args)
    except (KeyError, ValueError) as e:
        sys.exit(f"Erreur : {e}")


if __name__ == "__main__":
    main()
