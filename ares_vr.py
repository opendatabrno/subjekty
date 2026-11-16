"""Extrakce subjektů veřejného rejstříku z hromadných dat ARES (celá ČR).

Archiv ARES (data/ares/ares_vreo_all.tar.gz) obsahuje jeden XML soubor za každé IČO,
které kdy bylo ve veřejném rejstříku (obchodní, spolkový, nadační rejstřík, rejstřík
ústavů, SVJ a o. p. s.), včetně vymazaných subjektů. Z každého se vezme hlavní záznam
(bez odštěpných závodů) s datem zápisu, výmazu a posledním sídlem.

Výstup data/ares_vr.csv (není v repozitáři, obsahuje IČO jednotlivých subjektů):
    ico, pravni_forma, rejstrik, okres, obec, cast_obce, mop, psc, ruian_adresa,
    datum_zapisu, datum_vymazu
plus data/ares_vr_stav.txt s datem aktualizace databáze ARES (nejnovější Aktualizace_DB).

Spouští ho zpracuj_data.py, když je archiv novější než data/ares_vr.csv; ručně:
    python ares_vr.py
Extrakce celé ČR trvá desítky minut (archiv má přes milion souborů).
"""
import csv
import re
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARCHIV = ROOT / "data" / "ares" / "ares_vreo_all.tar.gz"
CIL = ROOT / "data" / "ares_vr.csv"
STAV = ROOT / "data" / "ares_vr_stav.txt"

RE_VYPIS = re.compile(r"<are:Vypis_VREO>(.*?)</are:Vypis_VREO>", re.S)
RE_ZU = re.compile(r"<are:Zakladni_udaje>(.*?)</are:Zakladni_udaje>", re.S)
RE_AKT = re.compile(r"<are:Aktualizace_DB>(\d{4}-\d{2}-\d{2})</are:Aktualizace_DB>")
RE_TAG = {}

POLE = ["ico", "pravni_forma", "rejstrik", "okres", "obec", "cast_obce", "mop", "psc",
        "ruian_adresa", "datum_zapisu", "datum_vymazu"]


def tag(blok, jmeno):
    r = RE_TAG.get(jmeno)
    if r is None:
        r = RE_TAG[jmeno] = re.compile(rf"<are:{jmeno}>(.*?)</are:{jmeno}>", re.S)
    m = r.search(blok)
    return m.group(1).strip() if m else ""


def zaznam(txt):
    """Hlavní záznam subjektu z jednoho XML; přednost má aktivní, jinak poslední vymazaný."""
    nejlepsi = None
    for v in RE_VYPIS.findall(txt):
        zu = RE_ZU.search(v)
        if not zu:
            continue
        zu = zu.group(1)
        if tag(zu, "Kod_PF") == "999":  # odštěpný závod / pobočka
            continue
        sidlo = tag(zu, "Sidlo")
        rec = {
            "ico": tag(zu, "ICO"),
            "pravni_forma": tag(zu, "Kod_PF"),
            "rejstrik": tag(zu, "Rejstrik"),
            "okres": tag(sidlo, "okres"),
            "obec": tag(sidlo, "obec"),
            "cast_obce": tag(sidlo, "castObce"),
            "mop": tag(sidlo, "mop"),
            "psc": tag(sidlo, "psc"),
            "ruian_adresa": tag(sidlo, "ruianKod"),
            "datum_zapisu": tag(zu, "DatumZapisu"),
            "datum_vymazu": tag(zu, "DatumVymazu"),
        }
        klic = (rec["datum_vymazu"] == "", rec["datum_vymazu"], rec["datum_zapisu"])
        if nejlepsi is None or klic > nejlepsi[0]:
            nejlepsi = (klic, rec)
    return nejlepsi[1] if nejlepsi else None


def extrahuj(archiv=ARCHIV, cil=CIL):
    n_souboru = n_zapsano = 0
    aktualizace = ""
    docasny = cil.with_suffix(".tmp")
    with tarfile.open(archiv, "r:gz") as tf, open(docasny, "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=POLE)
        w.writeheader()
        for m in tf:
            if not m.isfile() or not m.name.endswith(".xml"):
                continue
            n_souboru += 1
            txt = tf.extractfile(m).read().decode("utf-8", "replace")
            a = RE_AKT.search(txt)
            if a and a.group(1) > aktualizace:
                aktualizace = a.group(1)
            rec = zaznam(txt)
            if rec and rec["ico"]:
                w.writerow(rec)
                n_zapsano += 1
            if n_souboru % 200_000 == 0:
                print(f"  ARES: {n_souboru:,} souborů, {n_zapsano:,} subjektů", flush=True)
    docasny.replace(cil)
    STAV.write_text(aktualizace, encoding="utf-8")
    print(f"  ARES: hotovo, {n_souboru:,} souborů, {n_zapsano:,} subjektů, aktualizace DB {aktualizace}")


def je_aktualni():
    return CIL.exists() and STAV.exists() and CIL.stat().st_mtime >= ARCHIV.stat().st_mtime


if __name__ == "__main__":
    if not ARCHIV.exists():
        sys.exit(f"Chybí {ARCHIV} – nejdřív spusť stahni_data.py")
    extrahuj()
