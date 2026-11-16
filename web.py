"""Sestaví web pro GitHub Pages do složky _site/.

Úvodní stránka s popisem a odkazy ke stažení, přehled kontrol a samotná CSV.
Spouští ho workflow .github/workflows/pages.yml, lokálně:
    python web.py
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

import kontrola

ROOT = Path(__file__).resolve().parent
VYSTUP = ROOT / "vystup"
WEB = ROOT / "_site"
REPO = "https://github.com/opendatabrno/subjekty"
TEXTOVE = {"stav_k", "nazev_obce", "okres", "kod_okresu", "kod_kraje", "kraj", "spravni_obvod",
           "nazev_mc", "sekce_nace", "nazev_sekce"}

SADY = [
    ("subjekty_obce.csv", "Subjekty v obcích",
     "Všechny obce ČR, jeden řádek = obec × rok. Klíč rok + kod_obce. Subjekty bez zjištěné obce "
     "jsou v řádku „nezjištěno“ svého okresu."),
    ("subjekty_mestske_casti.csv", "Subjekty v městských částech",
     "MČ a obvody 8 statutárních měst (Praha, Brno, Ostrava, Plzeň, Pardubice, Opava, Liberec, "
     "Ústí nad Labem), jeden řádek = MČ × rok. Klíč rok + kod_mc."),
    ("subjekty_nace_okresy.csv", "Obory (CZ-NACE) v okresech",
     "Jen RES: okres × sekce CZ-NACE 2025 × rok. Velikost podle počtu zaměstnanců jen v posledním roce."),
    ("subjekty_nace_mestske_casti.csv", "Obory (CZ-NACE) v městských částech",
     "Jen RES: MČ × sekce CZ-NACE 2025 × rok, stejné sloupce jako u okresů."),
]

SLOUPCE = [
    ("rok, stav_k", "rok a den, ke kterému platí stav (31. 12., v posledním roce den dat RES)"),
    ("kod_obce, nazev_obce", "kód obce ČSÚ a název; u MČ město, kam patří"),
    ("kod_okresu, okres, kod_kraje, kraj", "okres a kraj (NUTS) podle aktuálního číselníku obcí"),
    ("spravni_obvod, kod_mc, nazev_mc", "jen MČ: správní obvod (Praha), kód ČSÚ a název MČ"),
    ("rejstrik_aktivni", "subjekty zapsané ve veřejném rejstříku (obchodní, spolkový, nadační rejstřík, "
                         "ústavy, SVJ, o. p. s.) a dosud nevymazané, podle ARES; od 1990"),
    ("rejstrik_zapsano, rejstrik_vymazano", "zápisy a výmazy v daném roce"),
    ("rejstrik_sro, …_akciove_spolecnosti, …_druzstva, …_spolky, …_svj, …_ostatni_pravnicke",
     "aktivní subjekty rejstříku podle právní formy (součet = rejstrik_aktivni)"),
    ("subjekty_aktivni", "všechny ekonomické subjekty v RES (ČSÚ) včetně OSVČ, které nezanikly; "
                         "jen za roky, kdy je RES úplný (od konce roku 2022)"),
    ("subjekty_vznikle, subjekty_zanikle", "vzniklé a zaniklé subjekty v roce (RES)"),
    ("fyzicke_osoby, pravnicke_osoby, forma_nezjistena", "aktivní subjekty RES podle typu osoby; "
                                                         "nezjištěná forma = anonymizované zaniklé subjekty"),
    ("sro, akciove_spolecnosti, druzstva, spolky, svj, ostatni_pravnicke",
     "právnické osoby v RES podle právní formy (součet = pravnicke_osoby)"),
    ("sekce_nace, nazev_sekce", "jen tabulky NACE: sekce CZ-NACE 2025 hlavní činnosti (A–V)"),
    ("velikost_0 … velikost_250_plus, velikost_neuvedeno", "jen tabulky NACE, poslední rok: počet "
                                                           "zaměstnanců podle ČSÚ (0, 1–9, 10–49, 50–249, 250+)"),
]


def velikost(cesta):
    mb = cesta.stat().st_size / 1_000_000
    return f"{mb:.1f} MB".replace(".", ",")


def main():
    if not (VYSTUP / "kontrola_souctu.csv").exists():
        print("Chybí výstupy ve vystup/ – nejdřív spusť zpracuj_data.py")
        return 1
    kontrola.main()
    meta = json.loads((VYSTUP / "stav_dat.json").read_text(encoding="utf-8"))
    shutil.rmtree(WEB, ignore_errors=True)
    WEB.mkdir()
    shutil.copy(VYSTUP / "kontrola.html", WEB / "kontrola.html")

    karty = []
    for soubor, nazev, popis in SADY:
        cesta = VYSTUP / soubor
        shutil.copy(cesta, WEB / soubor)
        # xlsx se v repozitáři neukládá, vzniká tady z CSV
        d = pd.read_csv(cesta, dtype=str)
        cisla = [c for c in d.columns if c not in TEXTOVE]
        d[cisla] = d[cisla].apply(pd.to_numeric).astype("Int64")
        xlsx = WEB / cesta.with_suffix(".xlsx").name
        d.to_excel(xlsx, index=False, freeze_panes=(1, 0))
        karty.append(
            f'<div class="karta ok"><h3>{nazev}</h3><p>{popis}</p>'
            f'<p class="meta">{d.rok.min()}–{d.rok.max()} · {kontrola.cislo(len(d))} řádků</p>'
            f'<div class="tlacitka"><a class="tlacitko" href="{soubor}" download>CSV · {velikost(cesta)}</a>'
            f'<a class="tlacitko druhe" href="{xlsx.name}" download>Excel · {velikost(xlsx)}</a></div></div>')
    sloupce = "".join(f"<tr><td><code>{s}</code></td><td>{p}</td></tr>" for s, p in SLOUPCE)
    stav = (VYSTUP / "kontrola_stav.txt").read_text(encoding="utf-8").strip()
    res_stav = pd.Timestamp(meta["res_stav"])
    ares_stav = pd.Timestamp(meta["ares_stav"])
    res_od = meta["res_od"]

    stranka = f"""<!doctype html>
<html lang="cs"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ekonomické subjekty ČR</title><style>{kontrola.CSS}
.meta{{font-size:13px;margin-top:8px!important}}
.tlacitko{{display:inline-block;margin-top:12px;padding:7px 14px;border-radius:8px;background:var(--accent);
color:var(--panel);text-decoration:none;font-weight:600;font-size:14px}}
.tlacitko:hover{{filter:brightness(1.1)}}
.tlacitka{{display:flex;gap:8px;flex-wrap:wrap}}
.tlacitko.druhe{{background:transparent;color:var(--accent);box-shadow:inset 0 0 0 1.5px var(--accent)}}
a{{color:var(--info)}}
.odkazy{{display:flex;gap:16px;flex-wrap:wrap;margin-top:14px;align-items:center}}
</style></head><body><main>
<header><h1>Ekonomické subjekty v obcích ČR</h1>
<p>Počty firem, spolků, OSVČ a dalších subjektů po obcích a městských částech, se vznikem a zánikem
po letech. Jen z otevřených dat: veřejný rejstřík z ARES (od 1990), Registr ekonomických subjektů ČSÚ
(od {res_od}) a adresy z RÚIAN.</p>
<div class="odkazy">{kontrola.odznak(stav)}<a href="kontrola.html">Přehled kontrol</a>
<a href="{REPO}">Zdrojový kód a dokumentace</a></div></header>

<h2>Datové sady</h2>
<section class="karty">{''.join(karty)}</section>

<h2>Sloupce</h2>
<p class="popis">Sloupce <code>rejstrik_*</code> jsou z veřejného rejstříku (ARES), ostatní z RES (ČSÚ).
Kategorie se sčítají: formy dávají celkem, stav = loňský stav + vzniklé − zaniklé. Řádky tabulky obcí
a MČ nesčítej dohromady – MČ jsou části měst, která jsou v tabulce obcí jako celek.</p>
<div class="tab-obal"><table><thead><tr><th>Sloupec</th><th>Význam</th></tr></thead>
<tbody>{sloupce}</tbody></table></div>

<h2>Na co si dát pozor</h2>
<div class="panel"><ul>
<li><b>Jen poslední sídlo.</b> ARES i RES uvádějí jen současné (u zaniklých poslední) sídlo. Subjekt, který
se přestěhoval, se v minulých letech počítá v obci, kde sídlí dnes; historické rozložení po obcích a MČ
je proto přibližné.</li>
<li><b>Veřejný rejstřík není všechno.</b> <code>rejstrik_*</code> nezahrnuje OSVČ ani subjekty mimo rejstřík
(např. obce, příspěvkové organizace). Úplný počet je <code>subjekty_aktivni</code> z RES, ten ale existuje
až od konce roku {res_od}: ČSÚ v otevřeném RES drží zaniklé subjekty jen zhruba čtyři roky zpětně.</li>
<li><b>Zaniklé fyzické osoby jsou v RES anonymizované</b> (jen IČO a datum zániku). Jsou v řádku „nezjištěno“
s <code>forma_nezjistena</code>; součty za ČR jsou úplné, ale v obcích chybí OSVČ, které později zanikly.
Proto čísla obcí v letech {res_od}–{res_stav.year - 1} rostou rychleji, než odpovídá skutečnosti.
Rok 2023 má navíc hromadné výmazy neaktivních subjektů (únor a březen).</li>
<li><b>Výmaz z rejstříku je opožděný</b> oproti faktickému konci činnosti, často o roky (likvidace).</li>
<li><b>Zlom v roce 2014:</b> s novým občanským zákoníkem přešly do veřejného rejstříku spolky a SVJ
(+150 tis. zápisů za ČR).</li>
<li><b>Obor (CZ-NACE 2025) a velikost</b> jsou podle současného stavu v RES, ne historického. Velikost je
uvedená jen za poslední rok; u poloviny subjektů ji ČSÚ neuvádí.</li>
<li><b>Rok {res_stav.year} je neúplný</b> (stav k {res_stav:%d. %m. %Y}, rejstřík k {ares_stav:%d. %m. %Y}).</li>
<li>OSVČ a další fyzické osoby jsou jen v souhrnných počtech, žádné údaje o jednotlivých osobách.</li>
</ul></div>

<footer>Zdroj: <a href="https://ares.gov.cz/">ARES – Ministerstvo financí ČR</a> (hromadná data veřejného
rejstříku, stav k {ares_stav:%d. %m. %Y}) · <a href="https://csu.gov.cz/">ČSÚ – Registr ekonomických subjektů</a>
(otevřená data, stav k {res_stav:%d. %m. %Y}) · <a href="https://vdp.cuzk.cz/">ČÚZK – RÚIAN</a>
· aktualizováno {datetime.now():%d. %m. %Y}</footer>
</main></body></html>"""
    (WEB / "index.html").write_text(stranka, encoding="utf-8")
    print(f"Web: {WEB}")


if __name__ == "__main__":
    sys.exit(main())
