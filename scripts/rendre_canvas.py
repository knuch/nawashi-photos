#!/usr/bin/env python3
"""Rend les visuels d'un canvas Claude (fichiers .dc.html) en PNG, pour l'export vers Canva.

Chaque fichier .dc.html est un visuel (slide ou story). Le script :
- retire le runtime du canvas (support.js, script x-dc) et les liens Google Fonts ;
- remplace les URL /_blob/<id> par les fichiers locaux donnés avec --asset ;
- charge Poiret One et Ubuntu en local (paquets npm @fontsource, téléchargés dans cache/fonts) ;
- fait une capture à 1080 px de large (432 × 540 → 1080 × 1350, 432 × 768 → 1080 × 1920).

Usage :
  python scripts/rendre_canvas.py --sortie cache/rendus/post \\
      --asset d33596a5...=chemin/photo.jpg --asset 021590f1...=chemin/logo.svg \\
      canvas/project/Main.dc.html canvas/project/Slide2.dc.html ...
Sortie : cache/rendus/post-1.png, post-2.png… dans l'ordre des fichiers donnés.

Prérequis : pip install playwright (Chrome ou Chromium installé ; --chrome pour son chemin), npm.
Ensuite, dans Canva (connecteur) : create-upload-url + POST de chaque PNG, puis un design aux
bonnes dimensions avec une image pleine page par page (voir « Livrables visuels » du guide).
"""
import argparse, asyncio, pathlib, re, shutil, subprocess, tarfile, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = ROOT / "cache" / "fonts"
FAMILLES = [("Poiret One", "poiret-one", [400]), ("Ubuntu", "ubuntu", [300, 400, 500, 700])]
LATIN_EXT = "U+0100-024F,U+1E00-1EFF,U+2020,U+20A0-20AB,U+20AD-20CF,U+2113,U+2C60-2C7F,U+A720-A7FF"


def polices():
    FONTS.mkdir(parents=True, exist_ok=True)
    for _, slug, _ in FAMILLES:
        if any(FONTS.glob(f"{slug}-latin-*.woff2")):
            continue
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["npm", "pack", f"@fontsource/{slug}", "--silent"], cwd=tmp, check=True,
                           stdout=subprocess.DEVNULL)
            tgz = next(pathlib.Path(tmp).glob("*.tgz"))
            with tarfile.open(tgz) as t:
                t.extractall(tmp, filter="data")
            for f in (pathlib.Path(tmp) / "package" / "files").glob(f"{slug}-latin*-normal.woff2"):
                shutil.copy(f, FONTS / f.name)
    css = ""
    for fam, slug, poids in FAMILLES:
        for w in poids:
            css += f"@font-face{{font-family:'{fam}';font-weight:{w};src:url({(FONTS / f'{slug}-latin-{w}-normal.woff2').as_uri()})}}"
            ext = FONTS / f"{slug}-latin-ext-{w}-normal.woff2"
            if ext.exists():
                css += f"@font-face{{font-family:'{fam}';font-weight:{w};src:url({ext.as_uri()});unicode-range:{LATIN_EXT}}}"
    return css


def preparer(src, assets, css):
    brut = src.read_text()
    m = re.search(r'"\$preview":\{"width":(\d+),"height":(\d+)', brut)
    if not m:
        raise SystemExit(f"{src} : $preview introuvable")
    s = brut.replace('<script src="./support.js"></script>', "")
    s = re.sub(r'<script type="text/x-dc".*?</script>', "", s, flags=re.S)
    s = re.sub(r'<link href="https://fonts.googleapis.com[^>]*>', "", s)
    for blob, chemin in assets.items():
        s = s.replace(f"/_blob/{blob}", pathlib.Path(chemin).resolve().as_uri())
    restants = re.findall(r"/_blob/([0-9a-f]+)", s)
    if restants:
        raise SystemExit(f"{src} : asset sans fichier local : {', '.join(sorted(set(restants)))}")
    s = s.replace("<style>", f"<style>{css} x-dc{{display:block}} helmet{{display:none}}", 1)
    return s, int(m.group(1)), int(m.group(2))


async def rendre(fichiers, sortie, assets, chrome, largeur):
    from playwright.async_api import async_playwright
    css = polices()
    sortie.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        nav = await p.chromium.launch(executable_path=chrome) if chrome else await p.chromium.launch()
        with tempfile.TemporaryDirectory() as tmp:
            for i, src in enumerate(fichiers, 1):
                html, w, h = preparer(pathlib.Path(src), assets, css)
                page_html = pathlib.Path(tmp) / f"{i}.html"
                page_html.write_text(html)
                page = await nav.new_page(viewport={"width": w, "height": h}, device_scale_factor=largeur / w)
                await page.goto(page_html.as_uri())
                await page.evaluate("document.fonts.ready")
                await page.wait_for_timeout(300)
                out = sortie.with_name(f"{sortie.name}-{i}.png")
                await page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": w, "height": h})
                print(out)
        await nav.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("fichiers", nargs="+", help="fichiers .dc.html, dans l'ordre des pages")
    ap.add_argument("--sortie", required=True, help="préfixe des PNG, ex. cache/rendus/post")
    ap.add_argument("--asset", action="append", default=[], help="<id du blob>=<fichier local>")
    ap.add_argument("--chrome", default=shutil.which("google-chrome") or shutil.which("chromium"),
                    help="chemin de Chrome/Chromium (défaut : celui du système, sinon Playwright)")
    ap.add_argument("--largeur", type=int, default=1080, help="largeur de sortie en px (défaut 1080)")
    a = ap.parse_args()
    assets = dict(x.split("=", 1) for x in a.asset)
    asyncio.run(rendre(a.fichiers, pathlib.Path(a.sortie), assets, a.chrome, a.largeur))


if __name__ == "__main__":
    main()
