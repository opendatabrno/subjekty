"""Stahování akcí insolvenčního rejstříku (ISIR) z veřejné webové služby ISIR_PUBLIC_WS.

Služba vrací akce (události řízení) po 1 000 kusech podle pořadového čísla, hromadný soubor
neexistuje. Skript proto pokračuje od posledního staženého čísla a dodržuje provozní podmínky
ISIR: nejvýš 3 000 požadavků denně a 50 za minutu (výchozí interval 30 s = 2 880 denně).
Celá historie od roku 2008 je přes 50 tisíc volání, tedy zhruba tři až čtyři týdny běhu;
měsíční aktualizace pak potřebuje jen stovky volání.

Z akcí se ukládá jen to, co je potřeba pro souhrnné počty (stav řízení jen při změně):
    id, zalozeno, zverejneno, spis, typ, stav, vec_zrusena, udalost_zrusena, skonceni,
    role, druh_osoby, ic, pravni_forma, druh_adresy, obec, psc, okres
Jména, rodná čísla, data narození ani ulice se neukládají. Data jsou jen v data/isir/
(není v repozitáři), výstupy obsahují jen souhrnné počty.

Výstup:
    data/isir/akce.csv        akce, které nesou stav řízení, osobu dlužníka nebo zrušení záznamu
    data/isir/posledni_id.txt pořadové číslo poslední zpracované akce (pokračování po přerušení)
    data/isir/stav.json       průběh stahování

Použití:
    python isir.py                     # stahuje, dokud nedožene aktuální stav
    python isir.py --interval 30       # pauza mezi voláními v sekundách
    python isir.py --max-volani 500    # skončí po daném počtu volání (měsíční aktualizace)
"""
import argparse
import csv
import html
import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
SLOZKA = ROOT / "data" / "isir"
AKCE = SLOZKA / "akce.csv"
POSLEDNI = SLOZKA / "posledni_id.txt"
STAV = SLOZKA / "stav.json"

URL = "https://isir.justice.cz:8443/isir_public_ws/IsirWsPublicService"
HLAVICKY = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""',
            "User-Agent": "opendatabrno-subjekty (souhrnne statistiky)"}
DOTAZ_ID = ('<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            'xmlns:typ="http://isirpublicws.cca.cz/types/"><soapenv:Body><typ:getIsirWsPublicIdDataRequest>'
            '<idPodnetu>{id}</idPodnetu></typ:getIsirWsPublicIdDataRequest></soapenv:Body></soapenv:Envelope>')
DOTAZ_POSLEDNI = ('<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
                  'xmlns:typ="http://isirpublicws.cca.cz/types/"><soapenv:Body>'
                  '<typ:getIsirWsPublicPosledniIdDataRequest/></soapenv:Body></soapenv:Envelope>')

POLE = ["id", "zalozeno", "zverejneno", "spis", "typ", "stav", "vec_zrusena", "udalost_zrusena",
        "skonceni", "role", "druh_osoby", "ic", "pravni_forma", "druh_adresy", "obec", "psc", "okres"]


def lokalni(tag):
    return tag.rsplit("}", 1)[-1]


def text(el, jmeno):
    for x in el.iter():
        if lokalni(x.tag) == jmeno:
            return (x.text or "").strip()
    return ""


def volani(telo, pokusu=6):
    """SOAP volání s opakováním při výpadku (prodlužující se pauza, max. ~30 min)."""
    for pokus in range(pokusu):
        try:
            r = requests.post(URL, data=telo.encode("utf-8"), headers=HLAVICKY, timeout=180)
            if r.status_code == 200:
                return ET.fromstring(r.content)
            chyba = f"HTTP {r.status_code}"
        except (requests.RequestException, ET.ParseError) as e:
            chyba = str(e)[:200]
        pauza = 60 * 2 ** pokus
        print(f"  ISIR: {chyba}, další pokus za {pauza} s", flush=True)
        time.sleep(pauza)
    raise RuntimeError("ISIR neodpovídá")


def posledni_na_serveru():
    koren = volani(DOTAZ_POSLEDNI)
    return int(text(koren, "cisloPosledniId") or 0)


def zpracuj_akci(data, stavy):
    """Z jedné akce vrátí řádek k uložení, nebo None, když nenese nic potřebného.

    Stav řízení nese skoro každá akce; ukládá se jen při změně (stavy = poslední stav podle spisu).
    """
    r = {k: "" for k in POLE}
    r["id"] = text(data, "id")
    r["zalozeno"] = text(data, "datumZalozeniUdalosti")[:19]
    r["zverejneno"] = text(data, "datumZverejneniUdalosti")[:19]
    r["spis"] = text(data, "spisovaZnacka")
    r["typ"] = text(data, "typUdalosti")
    pozn = text(data, "poznamka")
    if pozn:
        try:
            p = ET.fromstring(html.unescape(pozn).encode("utf-8") if "&lt;" in pozn else pozn.encode("utf-8"))
        except ET.ParseError:
            p = None
        if p is not None:
            r["stav"] = text(p, "druhStavRizeni")
            r["vec_zrusena"] = text(p, "datumVecZrusena")[:10]
            r["udalost_zrusena"] = text(p, "datumUdalostZrusena")[:10]
            r["skonceni"] = text(p, "datumSkonceniVeci")[:10]
            for osoba in (x for x in p.iter() if lokalni(x.tag) == "osoba"):
                role = text(osoba, "druhRoleVRizeni")
                if role != "DLUŽNÍK":
                    continue  # věřitelé, správci apod. se neukládají
                r["role"] = role
                r["druh_osoby"] = text(osoba, "druhOsoby")
                r["ic"] = text(osoba, "ic")
                r["pravni_forma"] = text(osoba, "druhPravniForma")
                adresa = next((x for x in osoba.iter() if lokalni(x.tag) == "adresa"), None)
                if adresa is not None:
                    r["druh_adresy"] = text(adresa, "druhAdresy")
                    r["obec"] = text(adresa, "mesto")
                    r["psc"] = text(adresa, "psc").replace(" ", "")
                    r["okres"] = text(adresa, "okres")
                break
    if r["stav"]:
        if stavy.get(r["spis"]) == r["stav"]:
            r["stav"] = ""
        else:
            stavy[r["spis"]] = r["stav"]
    if r["stav"] or r["role"] or r["vec_zrusena"] or r["udalost_zrusena"] or r["skonceni"]:
        return r
    return None


def uloz_stav(**kw):
    STAV.write_text(json.dumps(kw, ensure_ascii=False, indent=2), encoding="utf-8")


def stahuj(interval, max_volani=None):
    SLOZKA.mkdir(parents=True, exist_ok=True)
    od = int(POSLEDNI.read_text().strip()) if POSLEDNI.exists() else 0
    cil = posledni_na_serveru()
    print(f"  ISIR: pokračuji od akce {od:,}, poslední na serveru {cil:,}", flush=True)
    novy = not AKCE.exists()
    stavy = {}
    if not novy:  # poslední známý stav každého řízení, aby se neukládaly opakované stavy
        with open(AKCE, newline="", encoding="utf-8") as f:
            for radek in csv.DictReader(f):
                if radek["stav"]:
                    stavy[radek["spis"]] = radek["stav"]
    n_volani = n_akci = n_ulozeno = 0
    with open(AKCE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=POLE)
        if novy:
            w.writeheader()
        while od < cil and (max_volani is None or n_volani < max_volani):
            zacatek = time.monotonic()
            koren = volani(DOTAZ_ID.format(id=od))
            n_volani += 1
            stav = text(koren, "stav")
            if stav and stav != "OK":
                raise RuntimeError(f"ISIR vrátil stav {stav}: {text(koren, 'popisChyby')}")
            data = [x for x in koren.iter() if lokalni(x.tag) == "data"]
            if not data:
                break
            for d in data:
                radek = zpracuj_akci(d, stavy)
                if radek:
                    w.writerow(radek)
                    n_ulozeno += 1
            n_akci += len(data)
            od = max(int(text(d, "id")) for d in data)
            f.flush()
            POSLEDNI.write_text(str(od))  # až po zápisu řádků; při pádu se nanejvýš zopakují
            if n_volani % 20 == 0:
                posledni_datum = text(data[-1], "datumZalozeniUdalosti")[:10]
                print(f"  ISIR: {n_volani:,} volání, akce {od:,} / {cil:,} ({posledni_datum}), "
                      f"uloženo {n_ulozeno:,}", flush=True)
                uloz_stav(posledni_id=od, cil=cil, posledni_datum=posledni_datum,
                          aktualizovano=datetime.now().isoformat(timespec="seconds"))
            if od >= cil:
                cil = posledni_na_serveru()
            time.sleep(max(0.0, interval - (time.monotonic() - zacatek)))
    uloz_stav(posledni_id=od, cil=cil, hotovo=od >= cil,
              aktualizovano=datetime.now().isoformat(timespec="seconds"))
    print(f"  ISIR: konec, {n_volani:,} volání, {n_akci:,} akcí, uloženo {n_ulozeno:,}; "
          f"poslední akce {od:,} z {cil:,}", flush=True)
    return od >= cil


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--interval", type=float, default=30.0, help="pauza mezi voláními v s (min. 1,2)")
    ap.add_argument("--max-volani", type=int, default=None)
    a = ap.parse_args()
    stahuj(max(a.interval, 1.2), a.max_volani)


if __name__ == "__main__":
    sys.exit(main())
