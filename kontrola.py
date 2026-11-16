"""HTML přehled kontrol zpracování – vystup/kontrola.html.

Čte kontrolní CSV, které vytváří zpracuj_data.py, a skládá z nich jednu stránku
se semafory, grafem vývoje a tabulkami. Spouští se automaticky na konci
zpracuj_data.py, samostatně:
    python kontrola.py
"""
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
VYSTUP = ROOT / "vystup"

# Meziroční změna počtu subjektů v rejstříku za ČR, nad kterou je nejspíš chyba v načtení.
MAX_ZMENA = 0.10
# Podíl subjektů rejstříku bez přiřazené obce, nad který je potřeba párování prověřit.
MAX_NEZJISTENO = 0.04
# Roky, kdy je skok v rejstříku známý a v pořádku.
ZLOMY = {1991: "rozjezd rejstříku po roce 1990 (do 1999 roste o desítky procent ročně)",
         1992: "", 1993: "", 1994: "", 1995: "", 1996: "", 1997: "", 1998: "", 1999: "",
         2014: "nový občanský zákoník: spolky a SVJ převedeny do veřejného rejstříku"}


def cislo(x):
    return "" if pd.isna(x) else f"{int(x):,}".replace(",", " ")


def esc(x):
    return html.escape("" if pd.isna(x) else str(x))


def nacti(jmeno):
    cesta = VYSTUP / jmeno
    return pd.read_csv(cesta) if cesta.exists() else pd.DataFrame()


STAVY = {"ok": ("V pořádku", "✓"), "info": ("Známý rozdíl", "i"),
         "varovani": ("Ověřit ručně", "!"), "chyba": ("Nesedí", "✕")}


def odznak(stav):
    text, ikona = STAVY[stav]
    return f'<span class="odznak {stav}"><b>{ikona}</b>{text}</span>'


def karta(nadpis, stav, popis):
    return (f'<div class="karta {stav}"><div class="karta-hlava">{odznak(stav)}</div>'
            f'<h3>{nadpis}</h3><p>{popis}</p></div>')


def nejhorsi(stavy):
    poradi = ["ok", "info", "varovani", "chyba"]
    return max(stavy, key=poradi.index) if len(stavy) else "ok"


def nenulove(k, sloupce):
    """Roky, kde některý z kontrolních rozdílů není nula."""
    s = [c for c in sloupce if c in k]
    maska = k[s].fillna(0).ne(0).any(axis=1)
    return k.loc[maska, "rok"].tolist()


def graf(k):
    def sloupce(hodnoty, roky, trida, nadpis):
        w, h, pad_l, pad_b, pad_t = 460, 220, 8, 26, 26
        platne = [(v, r) for v, r in zip(hodnoty, roky) if pd.notna(v)]
        n = len(platne) or 1
        sirka = (w - pad_l * 2) / n
        maxi = max((v for v, _ in platne), default=1) or 1
        casti = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{nadpis}">',
                 f'<text x="{pad_l}" y="16" class="g-nadpis">{nadpis}</text>']
        for i, (v, r) in enumerate(platne):
            vyska = (h - pad_b - pad_t) * v / maxi
            x = pad_l + i * sirka + 1
            y = h - pad_b - vyska
            zlom = " zlom" if r in ZLOMY and ZLOMY[r] else ""
            casti.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(sirka - 2, 1):.1f}" '
                         f'height="{vyska:.1f}" rx="1.5" class="{trida}{zlom}"><title>{r}: {cislo(v)}</title></rect>')
            if n <= 12 or r % 5 == 0:
                casti.append(f'<text x="{x + (sirka - 2) / 2:.1f}" y="{h - 9}" class="g-osa">{str(r)[2:]}</text>')
        casti.append("</svg>")
        return "".join(casti)

    roky = k.rok.tolist()
    return ('<div class="grafy">'
            + sloupce(k.rejstrik_aktivni.tolist(), roky, "s-a", "Subjekty ve veřejném rejstříku (ARES)")
            + sloupce(k.subjekty_aktivni.tolist(), roky, "s-b", "Všechny subjekty vč. OSVČ (RES)")
            + "</div>")


def zmena(x):
    if pd.isna(x):
        return ""
    return f"<span class='zmena'>{x:+.1%}</span>".replace(".", ",")


def rozdil(x):
    if pd.isna(x):
        return "<td class='c tlumene'>–</td>"
    return f"<td class='c{' chyba-text' if x else ''}'>{int(x):+d}</td>" if x else "<td class='c tlumene'>0</td>"


def tabulka_souctu(k):
    radky = []
    for r in k.itertuples():
        zl = f'<span class="zlom-text">{esc(ZLOMY[r.rok])}</span>' if ZLOMY.get(r.rok) else ""
        kontroly = [r.rejstrik_bilance_rozdil, r.rejstrik_formy_rozdil, r.rejstrik_zdroj_rozdil,
                    r.subjekty_bilance_rozdil, r.subjekty_formy_rozdil, r.subjekty_zdroj_rozdil,
                    r.mc_rejstrik_rozdil, r.mc_subjekty_rozdil, r.nace_rozdil, r.velikost_rozdil]
        radky.append(
            f"<tr><td class='rok'>{r.rok}{zl}</td>"
            f"<td class='c'>{cislo(r.rejstrik_aktivni)}{zmena(r.zmena_rejstrik)}</td>"
            f"<td class='c'>{cislo(r.rejstrik_zapsano)}</td><td class='c'>{cislo(r.rejstrik_vymazano)}</td>"
            f"<td class='c'>{cislo(r.subjekty_aktivni) or '<span class=tlumene>–</span>'}{zmena(r.zmena_subjekty)}</td>"
            f"<td class='c'>{cislo(r.subjekty_vznikle)}</td><td class='c'>{cislo(r.subjekty_zanikle)}</td>"
            + "".join(rozdil(x) for x in kontroly) + f"<td>{odznak(r.stav)}</td></tr>")
    return ("<div class='tab-obal'><table><thead><tr><th>Rok</th><th class='c'>Rejstřík aktivní</th>"
            "<th class='c'>zapsáno</th><th class='c'>vymazáno</th><th class='c'>RES aktivní</th>"
            "<th class='c'>vzniklo</th><th class='c'>zaniklo</th>"
            "<th class='c'>VR bilance</th><th class='c'>VR formy</th><th class='c'>VR zdroj</th>"
            "<th class='c'>RES bilance</th><th class='c'>RES formy</th><th class='c'>RES zdroj</th>"
            "<th class='c'>MČ VR</th><th class='c'>MČ RES</th><th class='c'>NACE</th>"
            "<th class='c'>Velikost</th><th>Stav</th></tr></thead><tbody>"
            + "".join(radky) + "</tbody></table></div>")


def tabulka_parovani(p):
    radky = "".join(
        f"<tr><td>{esc(r.zdroj)}</td><td>{esc(r.ukazatel)}</td><td class='c'>{cislo(r.pocet)}</td>"
        f"<td class='c'>{'' if pd.isna(r.podil) or r.podil == 1 else f'{r.podil:.2%}'.replace('.', ',')}</td></tr>"
        for r in p.itertuples())
    return ("<div class='tab-obal'><table><thead><tr><th>Zdroj</th><th>Ukazatel</th>"
            f"<th class='c'>Počet</th><th class='c'>Podíl</th></tr></thead><tbody>{radky}</tbody></table></div>")


CSS = """
:root{--bg:#f7f6f3;--panel:#fff;--text:#1d1f23;--muted:#6b6f76;--line:#e4e2dc;
--ok:#2f7d4f;--ok-bg:#e6f2ea;--info:#3a6ea5;--info-bg:#e7eef7;--warn:#a86a00;--warn-bg:#fbf0d9;
--err:#b3261e;--err-bg:#fbe5e3;--s-a:#3a6ea5;--s-b:#c26a2e;--accent:#2f7d4f;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15171a;--panel:#1d2024;--text:#e8e6e1;
--muted:#9a9ea5;--line:#30343a;--ok:#6cc08f;--ok-bg:#1c3326;--info:#86b2e0;--info-bg:#1d2a3a;--warn:#e0b04f;
--warn-bg:#3a2e14;--err:#f08a80;--err-bg:#3d1f1c;--s-a:#6f9fd4;--s-b:#e0925a;--accent:#6cc08f;}}
:root[data-theme="dark"]{--bg:#15171a;--panel:#1d2024;--text:#e8e6e1;--muted:#9a9ea5;--line:#30343a;--ok:#6cc08f;
--ok-bg:#1c3326;--info:#86b2e0;--info-bg:#1d2a3a;--warn:#e0b04f;--warn-bg:#3a2e14;--err:#f08a80;--err-bg:#3d1f1c;
--s-a:#6f9fd4;--s-b:#e0925a;--accent:#6cc08f;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 16px 64px}
header h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}
header p{margin:0;color:var(--muted)}
h2{font-size:18px;margin:40px 0 6px}
.popis{color:var(--muted);margin:0 0 14px;max-width:780px}
.karty{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:22px}
.karta{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;border-top:3px solid var(--line)}
.karta.ok{border-top-color:var(--ok)}.karta.info{border-top-color:var(--info)}
.karta.varovani{border-top-color:var(--warn)}.karta.chyba{border-top-color:var(--err)}
.karta h3{font-size:15px;margin:10px 0 4px}.karta p{margin:0;color:var(--muted);font-size:14px}
.odznak{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-weight:600;padding:2px 9px 2px 3px;border-radius:999px;white-space:nowrap}
.odznak b{display:inline-grid;place-items:center;width:18px;height:18px;border-radius:50%;color:var(--panel);font-size:11px}
.odznak.ok{background:var(--ok-bg);color:var(--ok)}.odznak.ok b{background:var(--ok)}
.odznak.info{background:var(--info-bg);color:var(--info)}.odznak.info b{background:var(--info)}
.odznak.varovani{background:var(--warn-bg);color:var(--warn)}.odznak.varovani b{background:var(--warn)}
.odznak.chyba{background:var(--err-bg);color:var(--err)}.odznak.chyba b{background:var(--err)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}
.panel ul{margin:0;padding-left:20px}.panel li{margin:4px 0}
.grafy{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.grafy svg{width:100%;height:auto;display:block}
.g-nadpis{font-size:13px;font-weight:600;fill:var(--text)}.g-osa{font-size:11px;fill:var(--muted);text-anchor:middle}
.s-a{fill:var(--s-a)}.s-b{fill:var(--s-b)}rect.zlom{opacity:.75;stroke:var(--text);stroke-dasharray:3 2;stroke-width:1}
.tab-obal{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
thead th{font-size:12.5px;color:var(--muted);font-weight:600;background:var(--panel);position:sticky;top:0}
tbody tr:last-child td{border-bottom:0}
.c{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.rok{font-weight:600;white-space:nowrap}.zlom-text{display:block;font-weight:400;font-size:12px;color:var(--muted);white-space:normal;max-width:200px}
.tlumene{color:var(--muted);font-size:12.5px}.chyba-text{color:var(--err);font-weight:600}
.zmena{display:block;font-size:12px;color:var(--muted)}
code{font-family:ui-monospace,Consolas,monospace;font-size:13px;background:var(--line);padding:1px 5px;border-radius:4px}
footer{margin-top:48px;color:var(--muted);font-size:13px}
"""


def main():
    k = nacti("kontrola_souctu.csv")
    if k.empty:
        print("Chybí vystup/kontrola_souctu.csv – nejdřív spusť zpracuj_data.py")
        return 1
    p = nacti("kontrola_parovani.csv")
    meta_cesta = VYSTUP / "stav_dat.json"
    meta = json.loads(meta_cesta.read_text(encoding="utf-8")) if meta_cesta.exists() else {}

    vr = ["rejstrik_bilance_rozdil", "rejstrik_formy_rozdil", "rejstrik_zdroj_rozdil"]
    rs = ["subjekty_bilance_rozdil", "subjekty_formy_rozdil", "pravnicke_formy_rozdil",
          "subjekty_zdroj_rozdil", "nace_rozdil", "velikost_rozdil"]
    mc = ["mc_rejstrik_rozdil", "mc_subjekty_rozdil"]
    skok = (k.zmena_rejstrik.abs() > MAX_ZMENA) & ~k.rok.isin(ZLOMY)
    k["stav"] = "ok"
    k.loc[skok, "stav"] = "varovani"
    k.loc[k.rok.isin(nenulove(k, vr + rs + mc)), "stav"] = "chyba"

    chyby_vr, chyby_rs, chyby_mc = nenulove(k, vr), nenulove(k, rs), nenulove(k, mc)
    stav_vr = "chyba" if chyby_vr else ("varovani" if skok.any() else "ok")
    stav_rs = "chyba" if chyby_rs else "ok"
    stav_mc = "chyba" if chyby_mc else "ok"
    popis_vr = (f"Nesedí součty v letech {', '.join(map(str, chyby_vr))}." if chyby_vr else
                f"Podezřelý meziroční skok: {', '.join(map(str, k.loc[skok, 'rok']))}." if skok.any() else
                "Stav = loňský stav + zápisy − výmazy, součet právních forem = celkem, přímý přepočet ze zdroje sedí.")
    popis_rs = (f"Nesedí součty v letech {', '.join(map(str, chyby_rs))}." if chyby_rs else
                "Bilance, formy, CZ-NACE i velikostní kategorie dávají součet za ČR.")
    popis_mc = (f"Rozdíl v letech {', '.join(map(str, chyby_mc))}." if chyby_mc else
                "Součet MČ (včetně „nezjištěno“) se rovná řádkům měst v tabulce obcí.")

    def podil(zdroj, ukazatel):
        r = p[(p.zdroj == zdroj) & (p.ukazatel == ukazatel)]
        return float(r.podil.iloc[0]) if len(r) else 0.0
    nezj = podil("ARES", "území: nezjištěno") + podil("ARES", "území: jen okres")
    stav_par = "varovani" if nezj > MAX_NEZJISTENO else "info"
    popis_par = (f"Subjekty rejstříku bez obce: {nezj:.1%} (většinou dávno vymazané se starou adresou). "
                 "Anonymizované zaniklé subjekty RES jsou v řádku „nezjištěno“.").replace(".", ",", 1)

    roky = f"{k.rok.min()}–{k.rok.max()}"
    stranka = f"""<!doctype html>
<html lang="cs"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kontrola zpracování</title><style>{CSS}</style></head><body><main>
<header><h1>Kontrola zpracování – ekonomické subjekty</h1>
<p>Roky {roky} · RES k {esc(meta.get('res_stav', ''))}, ARES k {esc(meta.get('ares_stav', ''))}
· vygenerováno {datetime.now():%d. %m. %Y %H:%M}</p></header>

<section class="karty">
{karta("Součty rejstříku (ARES)", stav_vr, popis_vr)}
{karta("Součty RES", stav_rs, popis_rs)}
{karta("MČ proti obcím", stav_mc, popis_mc)}
{karta("Přiřazení k území", stav_par, popis_par)}
</section>

<h2>Vývoj v čase (ČR)</h2>
<p class="popis">Čárkovaně jsou roky se známým zlomem. RES je úplný až od konce roku {meta.get('res_od', '')}.</p>
<div class="panel">{graf(k)}</div>

<h2>Součty po letech</h2>
<p class="popis">Sloupce s rozdíly musí být nulové: bilance (stav − loňský stav − vzniky + zániky), formy
(součet skupin právních forem − celkem), zdroj (součet obcí − přímý přepočet ze zdroje), MČ (součet MČ − řádky měst),
NACE (součet okresů po sekcích − součet obcí) a velikost (jen poslední rok).</p>
{tabulka_souctu(k)}

<h2>Párování a úplnost</h2>
<p class="popis">Jak se subjekty přiřadily k obci: adresní místo RÚIAN, kód obce/MČ z RES, stejné IČO v RES,
název obce a okresu. Zbytek je v řádcích „nezjištěno“.</p>
{tabulka_parovani(p) if not p.empty else "<p>Chybí vystup/kontrola_parovani.csv.</p>"}

<footer>Zdroj: soubory v <code>vystup/</code> vytvořené <code>zpracuj_data.py</code>. Podrobnosti v README.</footer>
</main></body></html>"""
    cil = VYSTUP / "kontrola.html"
    cil.write_text(stranka, encoding="utf-8")

    celkem = nejhorsi([stav_vr, stav_rs, stav_mc, stav_par])
    ikony = {"ok": "✅", "info": "ℹ️", "varovani": "⚠️", "chyba": "❌"}
    posledni = k.iloc[-1]
    souhrn = [f"## Kontrola zpracování: {ikony[celkem]} {STAVY[celkem][0]}", "",
              f"Poslední rok **{posledni.rok}** (stav k {posledni.stav_k}): ve veřejném rejstříku "
              f"{cislo(posledni.rejstrik_aktivni)} subjektů, v RES {cislo(posledni.subjekty_aktivni)} aktivních subjektů.",
              "", "| Kontrola | Stav | Detail |", "|---|---|---|"]
    for nazev, stav, popis in [("Součty rejstříku", stav_vr, popis_vr), ("Součty RES", stav_rs, popis_rs),
                               ("MČ proti obcím", stav_mc, popis_mc), ("Přiřazení k území", stav_par, popis_par)]:
        souhrn.append(f"| {nazev} | {ikony[stav]} {STAVY[stav][0]} | {re.sub(r'</?code>', '`', popis)} |")
    (VYSTUP / "kontrola_souhrn.md").write_text("\n".join(souhrn) + "\n", encoding="utf-8")
    (VYSTUP / "kontrola_stav.txt").write_text(celkem, encoding="utf-8")
    print(f"Kontrola: {STAVY[celkem][0]} -> {cil}")


if __name__ == "__main__":
    sys.exit(main())
