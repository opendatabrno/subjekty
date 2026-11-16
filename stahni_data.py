"""Stažení otevřených dat o ekonomických subjektech a číselníků.

Ukládá do složky data/ (není v repozitáři):
    data/ares/ares_vreo_all.tar.gz      hromadná data ARES – veřejný rejstřík (~870 MB)
    data/res/res_data.csv               Registr ekonomických subjektů ČSÚ (~550 MB)
    data/ruian/RRRRMMDD_OB_ADR_csv.zip  adresní místa RÚIAN celé ČR (~65 MB)
    data/zdroje.json                    odkud a s jakým datem se co stáhlo
a do ciselniky/ (v repozitáři):
    pscoco.csv, cnumnuts.csv            obce, okresy a kraje (volby.gov.cz, stejně jako u obyvatel)
    pravni_formy.csv                    číselník právních forem ČSÚ (kód 56)
    velikost.csv                        velikostní kategorie podle počtu zaměstnanců ČSÚ (kód 579)

Velké soubory se stahují jen tehdy, když je na serveru novější verze (hlavička Last-Modified),
takže měsíční běh bez nových dat nic nestahuje.

Zdroje:
  - ARES:  https://ares.gov.cz/otevrena-data/ares_vreo_all.tar.gz (MF ČR, aktualizace zhruba měsíčně)
  - RES:   https://opendata.czso.cz/data/od_org03/res_data.csv (ČSÚ, aktualizace měsíčně)
  - RÚIAN: https://vdp.cuzk.cz/vymenny_format/csv/ (ČÚZK, stav k poslednímu dni měsíce)

Použití:
    python stahni_data.py            # vše, co je nové nebo chybí
    python stahni_data.py --prepsat  # stáhnout znovu
"""
import argparse
import csv
import io
import json
import sys
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CISELNIKY = ROOT / "ciselniky"
ZDROJE = DATA / "zdroje.json"

ARES_URL = "https://ares.gov.cz/otevrena-data/ares_vreo_all.tar.gz"
RES_URL = "https://opendata.czso.cz/data/od_org03/res_data.csv"
RUIAN_URL = "https://vdp.cuzk.cz/vymenny_format/csv/{datum}_OB_ADR_csv.zip"
VOLBY = "https://volby.gov.cz/opendata/ps2025/csv_od/"
ISMS = ("https://apl2.czso.cz/iSMS/do_cis_export?kodcis={kod}&typdat=0&cisvaz=&datpohl="
        "&cisjaz=203&format=2&separator=%2C")

HLAVICKY = {"User-Agent": "Mozilla/5.0 (opendatabrno-subjekty)"}


def nacti_zdroje():
    if ZDROJE.exists():
        return json.loads(ZDROJE.read_text(encoding="utf-8"))
    return {}


def uloz_zdroje(z):
    ZDROJE.write_text(json.dumps(z, ensure_ascii=False, indent=2), encoding="utf-8")


def last_modified(url):
    r = requests.head(url, headers=HLAVICKY, timeout=60, allow_redirects=True)
    if r.status_code != 200:
        return None
    lm = r.headers.get("Last-Modified")
    return parsedate_to_datetime(lm).date().isoformat() if lm else ""


def stahni(url, cil, popis):
    """Stáhne url do cil přes dočasný soubor (přerušené stažení nepřepíše starou verzi)."""
    cil.parent.mkdir(parents=True, exist_ok=True)
    docasny = cil.with_name(cil.name + ".stahuje")
    print(f"  {popis}: stahuji {url}", flush=True)
    with requests.get(url, headers=HLAVICKY, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(docasny, "wb") as f:
            for kus in r.iter_content(1 << 20):
                f.write(kus)
    docasny.replace(cil)
    print(f"  {popis}: {cil.stat().st_size / 1e6:,.0f} MB")


def stahni_velky(klic, url, cil, popis, zdroje, prepsat):
    lm = last_modified(url)
    if lm is None:
        if cil.exists():
            print(f"  {popis}: server neodpovídá, zůstává stará verze")
            return
        sys.exit(f"{popis}: soubor {url} není dostupný")
    stary = zdroje.get(klic, {})
    if not prepsat and cil.exists() and stary.get("last_modified") == lm:
        print(f"  {popis}: beze změny (verze {lm})")
        return
    stahni(url, cil, popis)
    zdroje[klic] = {"url": url, "last_modified": lm, "stazeno": date.today().isoformat()}
    uloz_zdroje(zdroje)


def stahni_ruian(zdroje, prepsat):
    """Adresní místa celé ČR k poslednímu dni minulého (případně předminulého) měsíce."""
    slozka = DATA / "ruian"
    prvni = date.today().replace(day=1)
    for _ in range(3):
        posledni = prvni - timedelta(days=1)
        datum = posledni.strftime("%Y%m%d")
        cil = slozka / f"{datum}_OB_ADR_csv.zip"
        if cil.exists() and not prepsat:
            print(f"  RÚIAN: stav k {posledni:%d. %m. %Y} už je stažený")
            break
        url = RUIAN_URL.format(datum=datum)
        if last_modified(url) is not None:
            stahni(url, cil, "RÚIAN")
            for stary in slozka.glob("*_OB_ADR_csv.zip"):  # starší stavy už nejsou potřeba
                if stary != cil:
                    stary.unlink()
            break
        prvni = posledni.replace(day=1)
    else:
        if not any(slozka.glob("*_OB_ADR_csv.zip")):
            sys.exit("RÚIAN: soubor adresních míst se nepodařilo najít")
        return
    zdroje["ruian"] = {"url": RUIAN_URL.format(datum=datum), "stav_k": posledni.isoformat(),
                       "stazeno": date.today().isoformat()}
    uloz_zdroje(zdroje)


def isms(kod):
    r = requests.get(ISMS.format(kod=kod), headers=HLAVICKY, timeout=60)
    r.raise_for_status()
    r.encoding = "utf-8"
    return list(csv.DictReader(io.StringIO(r.text)))


def zapis_csv(cesta, radky, pole):
    with open(cesta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=pole, lineterminator="\n")
        w.writeheader()
        w.writerows(radky)


def stahni_ciselniky():
    CISELNIKY.mkdir(exist_ok=True)
    for jmeno in ("pscoco.csv", "cnumnuts.csv"):
        r = requests.get(VOLBY + jmeno, headers=HLAVICKY, timeout=60)
        r.raise_for_status()
        # volby.gov.cz posílá CRLF; v repozitáři je LF, jinak by každý běh na Linuxu hlásil změnu
        (CISELNIKY / jmeno).write_bytes(r.content.replace(b"\r\n", b"\n"))
    formy = [{"kod_pravni_formy": r["chodnota"], "pravni_forma": r["text"].strip()} for r in isms(56)]
    zapis_csv(CISELNIKY / "pravni_formy.csv", formy, ["kod_pravni_formy", "pravni_forma"])
    vel = [{"kod_velikosti": r["chodnota"], "velikost": r["text"].strip()} for r in isms(579)]
    zapis_csv(CISELNIKY / "velikost.csv", vel, ["kod_velikosti", "velikost"])
    print("  číselníky obcí, právních forem a velikostí aktualizovány")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--prepsat", action="store_true", help="stáhnout znovu i nezměněné soubory")
    a = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    zdroje = nacti_zdroje()
    stahni_ciselniky()
    stahni_ruian(zdroje, a.prepsat)
    stahni_velky("res", RES_URL, DATA / "res" / "res_data.csv", "RES", zdroje, a.prepsat)
    stahni_velky("ares", ARES_URL, DATA / "ares" / "ares_vreo_all.tar.gz", "ARES", zdroje, a.prepsat)


if __name__ == "__main__":
    sys.exit(main())
