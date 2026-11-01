"""Applique le thème « Simple Header - Blue » à un rapport Power BI au format PBIR.

    python outils/appliquer_theme_powerbi.py "brvm/powerbi/reporting_brvm_actions.Report"
    python outils/appliquer_theme_powerbi.py "umoa-titres/powerbi/Reporting BI.Report"

Le thème et ses fonds de page sont dans ``outils/theme_simple_header_blue/``, copiés tels quels du
modèle Power BI « Simple Header - Blue ». Le script :

1. enregistre le thème comme thème personnalisé du rapport et les fonds SVG comme ressources, et
   retire les anciennes ressources de marque (thème, logos) ;
2. pose sur chaque page le fond « Overview » du modèle (bandeau en haut, fond gris #d2d2d2) ;
3. retire les logos et les bandeaux dessinés, place le titre de la page dans la bande haute et le
   sous-titre dans la bande basse du bandeau, en blanc ;
4. remplace les couleurs de l'ancienne charte par celles du thème.

Rejouable : un rapport déjà migré reste identique. Fermer le rapport dans Power BI Desktop avant.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

THEME_DIR = Path(__file__).resolve().parent / "theme_simple_header_blue"
THEME = "Simple-Header---Blue.json"
FOND = "Overview.svg"
SVGS = sorted(p.name for p in THEME_DIR.glob("*.svg"))

# Bandeau du modèle (1280 × 75) : bande haute 0-37, bande basse 37-75, pavé gauche 0-192.
TITRE = {"x": 204, "y": 2, "width": 1060, "height": 34}
SOUS_TITRE = {"x": 204, "y": 39, "width": 1060, "height": 34}
HAUT_BANDEAU = 75

# Ancienne charte -> thème (foncé #1F2F4C, moyen #2C4770, clair #3B5E94).
COULEURS = {"#08306B": "#1F2F4C", "#0B2A5B": "#1F2F4C", "#1B2A4A": "#1F2F4C",
            "#0B5CAB": "#2C4770", "#1C86D1": "#3B5E94", "#3E9BE9": "#3B5E94"}
MARQUE = re.compile(r"cgf", re.I)
TEXTES = [(re.compile(r"\s*CGF Gestion\s*·\s*", re.I), ""), (re.compile(r"\bCGF Gestion\b", re.I), ""),
          (re.compile(r"\bCGF\b", re.I), "")]


def lire(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def ecrire(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def lit(v: str) -> dict:
    return {"expr": {"Literal": {"Value": v}}}


def fond_de_page() -> dict:
    return {"background": [{"properties": {
        "image": {"image": {
            "name": lit("'Overview'"),
            "url": {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources",
                                                     "PackageType": 1, "ItemName": FOND}}},
            "scaling": lit("'Normal'")}},
        "transparency": lit("0D"),
        "color": {"solid": {"color": lit("'#d2d2d2'")}}}}]}


def rapport(report: Path) -> None:
    chemin = report / "definition" / "report.json"
    r = lire(chemin)
    ancien = r["themeCollection"].get("customTheme", {})
    r["themeCollection"]["customTheme"] = {
        "name": THEME, "reportVersionAtImport": ancien.get("reportVersionAtImport", "5.4"),
        "type": "RegisteredResources"}
    for paquet in r["resourcePackages"]:
        if paquet["name"] == "RegisteredResources":
            garder = [i for i in paquet["items"]
                      if not MARQUE.search(i["name"]) and i["name"] != THEME and i["name"] not in SVGS]
            paquet["items"] = ([{"name": THEME, "path": THEME, "type": "CustomTheme"}] + garder
                               + [{"name": s, "path": s, "type": "Image"} for s in SVGS])
    ecrire(chemin, r)
    res = report / "StaticResources" / "RegisteredResources"
    res.mkdir(parents=True, exist_ok=True)
    for f in res.iterdir():
        if MARQUE.search(f.name):
            f.unlink()
    for f in [THEME, *SVGS]:
        shutil.copy2(THEME_DIR / f, res / f)


def _texte(vis: dict) -> list:
    try:
        return vis["visual"]["objects"]["general"][0]["properties"]["paragraphs"]
    except (KeyError, IndexError):
        return []


def _blanc(paragraphes: list, taille: str) -> None:
    for par in paragraphes:
        for run in par.get("textRuns", []):
            style = run.setdefault("textStyle", {})
            style["color"] = "#FFFFFF"
            style["fontSize"] = taille


def visuel(chemin: Path) -> str:
    """Migre un visuel ; rend « supprimé », « titre », « sous-titre » ou « »."""
    brut = chemin.read_text(encoding="utf-8")
    vis = json.loads(brut)
    v = vis.get("visual", {})
    pos = vis["position"]
    t = v.get("visualType")
    dans_bandeau = pos["y"] < HAUT_BANDEAU - 10
    # Logos de l'ancienne marque, bandeaux dessinés en forme pleine largeur.
    if (t == "image" and MARQUE.search(brut)) or (
            t == "shape" and dans_bandeau and pos["width"] >= 1200):
        shutil.rmtree(chemin.parent)
        return "supprimé"
    role = ""
    if t == "textbox":
        paragraphes = _texte(vis)
        for par in paragraphes:
            for run in par.get("textRuns", []):
                for motif, rempl in TEXTES:
                    run["value"] = motif.sub(rempl, run["value"])
        nom = vis["name"]
        if nom.endswith("_hdr") or (dans_bandeau and pos["y"] < 30):
            role = "titre"
            pos.update(TITRE)
            _blanc(paragraphes, "18px")
            v.pop("visualContainerObjects", None)          # plus de fond navy : le bandeau suffit
        elif nom.endswith("_sub") or (pos["y"] < HAUT_BANDEAU + 40 and pos["width"] >= 1200):
            role = "sous-titre"
            pos.update(SOUS_TITRE)
            _blanc(paragraphes, "11px")
            v.pop("visualContainerObjects", None)
    elif dans_bandeau or (t == "card" and pos["y"] < HAUT_BANDEAU + 10 and pos["height"] <= 40):
        # Carte posée sur l'ancien bandeau (date de mise à jour) : dans le pavé gauche du nouveau.
        pos.update({"x": 6, "y": 6, "width": 180, "height": 62})
    texte = json.dumps(vis, indent=2, ensure_ascii=False)
    for ancienne, nouvelle in COULEURS.items():
        texte = re.sub(re.escape(ancienne), nouvelle, texte, flags=re.I)
    chemin.write_text(texte + "\n", encoding="utf-8")
    return role


def pages(report: Path) -> dict:
    bilan = {}
    for page in sorted((report / "definition" / "pages").iterdir()):
        if not (page / "page.json").exists():
            continue
        p = lire(page / "page.json")
        p.setdefault("objects", {}).update(fond_de_page())
        ecrire(page / "page.json", p)
        roles = [visuel(f) for f in sorted((page / "visuals").glob("*/visual.json"))]
        bilan[p["displayName"]] = {r: roles.count(r) for r in set(roles) if r}
    return bilan


def main(chemin: str) -> None:
    report = Path(chemin).resolve()
    if not (report / "definition" / "report.json").exists():
        raise SystemExit(f"{report} n'est pas un dossier .Report au format PBIR")
    rapport(report)
    for page, roles in pages(report).items():
        print(f"{page} : {roles}")
    restes = [str(f.relative_to(report)) for f in report.rglob("*")
              if f.is_file() and f.suffix in (".json", ".svg") and MARQUE.search(f.read_text(encoding="utf-8"))]
    print("mentions de l'ancienne marque restantes :", restes or "aucune")


if __name__ == "__main__":
    for c in sys.argv[1:]:
        main(c)
