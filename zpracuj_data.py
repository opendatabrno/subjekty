"""Zpracování dat ARES, RES a RÚIAN do datových sad ekonomických subjektů ve vystup/.

Vstupy (stahuje stahni_data.py do data/):
    data/ares/ares_vreo_all.tar.gz -> data/ares_vr.csv (ares_vr.py, jen když je archiv nový)
    data/res/res_data.csv          Registr ekonomických subjektů ČSÚ
    data/ruian/*_OB_ADR_csv.zip    adresní místa RÚIAN (adresní místo -> obec, MČ)
    ciselniky/                     obce, okresy, kraje, právní formy, velikost, CZ-NACE 2025

Výstupy ve vystup/:
    subjekty_obce.csv              obec × rok (všechny obce ČR + „nezjištěno“ za okres)
    subjekty_mestske_casti.csv     MČ × rok (8 statutárních měst s MČ + „nezjištěno“ za město)
    subjekty_nace_okresy.csv       okres × sekce CZ-NACE × rok (jen RES)
    subjekty_nace_mestske_casti.csv MČ × sekce CZ-NACE × rok (jen RES)
    kontrola_souctu.csv            součtové kontroly za ČR po letech
    kontrola_parovani.csv          jak se subjekty přiřadily k území, NACE a velikosti
    ciselniky/mestske_casti.csv    MČ s kódy ČSÚ (z číselníku obcí a RÚIAN)

Použití:
    python zpracuj_data.py
Na konci spustí kontrola.py (vystup/kontrola.html, souhrn pro pull request).
"""
import io
import os
import json
import sys
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

import ares_vr

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CISELNIKY = ROOT / "ciselniky"
VYSTUP = ROOT / "vystup"

PRVNI_ROK = 1990          # první rok výstupu (stav k 31. 12. 1990 zahrnuje i starší zápisy)
NEZJISTENO = "nezjištěno"

# Skupiny právních forem (kódy ČSÚ, číselník 56; starší kódy 102–108 jsou fyzické osoby zapsané v OR)
FYZICKE = {"101", "102", "103", "104", "105", "106", "107", "108", "424", "425"}
SKUPINY = {"112": "sro", "121": "akciove_spolecnosti", "932": "akciove_spolecnosti",
           "205": "druzstva", "933": "druzstva",
           "706": "spolky", "736": "spolky", "701": "spolky", "906": "spolky", "936": "spolky",
           "145": "svj"}
SKUPINY_PO = ["sro", "akciove_spolecnosti", "druzstva", "spolky", "svj", "ostatni_pravnicke"]

# Velikostní kategorie podle počtu zaměstnanců (ČSÚ, číselník 579)
VELIKOST = {"110": "velikost_0", "120": "velikost_1_9", "130": "velikost_1_9",
            "210": "velikost_10_49", "220": "velikost_10_49", "230": "velikost_10_49",
            "240": "velikost_50_249", "310": "velikost_50_249", "320": "velikost_50_249"}
VELIKOSTI = ["velikost_0", "velikost_1_9", "velikost_10_49", "velikost_50_249",
             "velikost_250_plus", "velikost_neuvedeno"]


def velikost_skupina(kod):
    if kod in VELIKOST:
        return VELIKOST[kod]
    if isinstance(kod, str) and kod.isdigit() and int(kod) >= 330:
        return "velikost_250_plus"
    return "velikost_neuvedeno"


def forma_skupina(kod):
    if kod in FYZICKE:
        return "fyzicke_osoby"
    return SKUPINY.get(kod, "ostatni_pravnicke")


# --- číselníky ---------------------------------------------------------------

def nacti_ciselnik_obci():
    """Obce s okresem a krajem (volby.gov.cz) a vazba MČ -> obec."""
    p = pd.read_csv(CISELNIKY / "pscoco.csv")
    nuts = pd.read_csv(CISELNIKY / "cnumnuts.csv").set_index("NUMNUTS")
    p = p[p.KRAJ.isin(nuts.index)].copy()  # bez volebních okrsků v zahraničí
    p["kod_okresu"] = p.OKRES.map(lambda k: "CZ0100" if k == 1100 else nuts.at[k, "NUTS"])
    p["okres"] = p.OKRES.map(lambda k: "Praha" if k == 1100 else nuts.at[k, "NAZEVNUTS"])
    p["kod_kraje"] = p.KRAJ.map(lambda k: nuts.at[k, "NUTS"])
    p["kraj"] = p.KRAJ.map(lambda k: nuts.at[k, "NAZEVNUTS"])
    obce = p.drop_duplicates("OBEC_PREZ").rename(columns={"OBEC_PREZ": "kod_obce"})[
        ["kod_obce", "kod_okresu", "okres", "kod_kraje", "kraj"]].copy()
    mc = p[p.OBEC != p.OBEC_PREZ].rename(columns={"OBEC": "kod_mc", "NAZEVOBCE": "nazev_mc",
                                                    "OBEC_PREZ": "kod_obce"})[
        ["kod_mc", "nazev_mc", "kod_obce"]].drop_duplicates("kod_mc").copy()
    return obce, mc


def nacti_ruian():
    """Adresní místa RÚIAN: kod_adm -> kod_obce, kod_mc. Mezivýsledek se drží v data/ruian_am.csv."""
    zipy = sorted((DATA / "ruian").glob("*_OB_ADR_csv.zip"))
    if not zipy:
        sys.exit("Chybí adresní místa RÚIAN – spusť stahni_data.py")
    archiv = zipy[-1]
    cache = DATA / "ruian_am.csv"
    nazvy = DATA / "ruian_nazvy.csv"
    if cache.exists() and nazvy.exists() and cache.stat().st_mtime >= archiv.stat().st_mtime:
        return (pd.read_csv(cache, dtype="Int64"), pd.read_csv(nazvy, dtype=str),
                archiv.name[:8])
    print(f"  RÚIAN: načítám {archiv.name}", flush=True)
    casti = []
    sloupce = {"Kód ADM": "kod_adm", "Kód obce": "kod_obce", "Název obce": "nazev_obce",
               "Kód MOMC": "kod_mc", "Název MOMC": "nazev_mc", "Název obvodu Prahy": "spravni_obvod"}
    with zipfile.ZipFile(archiv) as z:
        for jmeno in z.namelist():
            if not jmeno.endswith(".csv"):
                continue
            d = pd.read_csv(io.BytesIO(z.read(jmeno)), sep=";", encoding="cp1250", dtype=str,
                            usecols=list(sloupce))
            casti.append(d.rename(columns=sloupce))
    r = pd.concat(casti, ignore_index=True)
    n = r[["kod_obce", "nazev_obce", "kod_mc", "nazev_mc", "spravni_obvod"]].drop_duplicates(
        ["kod_obce", "kod_mc"])
    n.to_csv(nazvy, index=False)
    am = r[["kod_adm", "kod_obce", "kod_mc"]].astype("Int64")
    am.to_csv(cache, index=False)
    return am, n.astype(str).replace("nan", pd.NA), archiv.name[:8]


# --- přiřazení k území -------------------------------------------------------

def norm(text):
    if not isinstance(text, str):
        return ""
    return text.strip().lower().replace("–", "-").replace(" - ", "-")


class Uzemi:
    """Převod kódů ČSÚ / RÚIAN / názvů na (kod_obce, kod_mc, kod_okresu)."""

    def __init__(self, obce, mc, am):
        self.obce = obce.set_index("kod_obce")
        self.mc = mc.set_index("kod_mc")
        self.mesta_s_mc = set(mc.kod_obce)
        self.am = am.dropna(subset=["kod_adm"]).set_index("kod_adm")
        self.okres_obce = self.obce.kod_okresu

    def z_iczuj(self, kody):
        """ICZUJ z RES: kód obce, nebo u statutárních měst kód MČ."""
        k = pd.to_numeric(kody, errors="coerce").astype("Int64")
        out = pd.DataFrame({"kod_obce": pd.array([pd.NA] * len(k), dtype="Int64"),
                            "kod_mc": pd.array([pd.NA] * len(k), dtype="Int64")}, index=kody.index)
        je_mc = k.isin(self.mc.index)
        out.loc[je_mc, "kod_mc"] = k[je_mc]
        out.loc[je_mc, "kod_obce"] = k[je_mc].map(self.mc.kod_obce).astype("Int64")
        je_obec = ~je_mc & k.isin(self.obce.index)
        out.loc[je_obec, "kod_obce"] = k[je_obec]
        return out

    def z_adresy(self, kody):
        k = pd.to_numeric(kody, errors="coerce").astype("Int64")
        j = pd.DataFrame({"kod_adm": k}).join(self.am, on="kod_adm")
        j.index = kody.index
        j.loc[~j.kod_obce.isin(self.obce.index), ["kod_obce", "kod_mc"]] = pd.NA
        j.loc[~j.kod_mc.isin(self.mc.index), "kod_mc"] = pd.NA
        return j[["kod_obce", "kod_mc"]]


def doplnit(cil, zdroj, metoda, nazev):
    """Do prázdných kod_obce v cil doplní hodnoty ze zdroj; u měst s MČ doplní i chybějící MČ."""
    zdroj = zdroj.astype({"kod_obce": "Int64", "kod_mc": "Int64"})
    prazdne = (cil.kod_obce.isna() & zdroj.kod_obce.notna()).to_numpy()
    for c in ("kod_obce", "kod_mc"):
        cil.loc[prazdne, c] = zdroj.loc[prazdne, c].array
    cil.loc[prazdne, metoda] = nazev
    bez_mc = (cil.kod_mc.isna() & zdroj.kod_mc.notna() & (cil.kod_obce == zdroj.kod_obce)).fillna(False).to_numpy()
    cil.loc[bez_mc, "kod_mc"] = zdroj.loc[bez_mc, "kod_mc"].array
    cil.loc[bez_mc & ~prazdne, "metoda_mc"] = nazev


# --- načtení zdrojů ----------------------------------------------------------

def opravit_poradi(d):
    """Zánik před vznikem (chyba ve zdroji): subjekt se počítá jako vzniklý a zaniklý týž den."""
    d["zanik_pred_vznikem"] = d.zanik < d.vznik
    d.loc[d.zanik_pred_vznikem, "zanik"] = d.loc[d.zanik_pred_vznikem, "vznik"]


def nacti_res(uzemi):
    cesta = DATA / "res" / "res_data.csv"
    if not cesta.exists():
        sys.exit("Chybí data/res/res_data.csv – spusť stahni_data.py")
    print("  RES: načítám", flush=True)
    d = pd.read_csv(cesta, dtype=str, usecols=["ICO", "OKRESLAU", "DDATVZN", "DDATZAN", "FORMA",
                                               "KATPO", "NACE2025", "ICZUJ", "KODADM", "DATPLAT"])
    stav = pd.to_datetime(d.DATPLAT, errors="coerce").max()
    n_vse = len(d)
    # Zaniklé subjekty bez údajů (anonymizované, prakticky jen fyzické osoby): RES u nich
    # uvádí jen IČO a datum zániku. Počítají se do řádku „nezjištěno“ s formou „nezjištěná“
    # a jako aktivní od doby před začátkem řady, aby součty za ČR byly úplné.
    bez_udaju = d.DDATVZN.isna() & d.FORMA.isna() & d.ICZUJ.isna() & d.DDATZAN.notna()
    d["vznik"] = pd.to_datetime(d.DDATVZN, errors="coerce")
    d.loc[bez_udaju, "vznik"] = pd.Timestamp("1900-01-01")
    d["zanik"] = pd.to_datetime(d.DDATZAN, errors="coerce")
    opravit_poradi(d)
    d["forma"] = d.FORMA.map(forma_skupina)
    d.loc[bez_udaju, "forma"] = "forma_nezjistena"
    d["anonymizovany"] = bez_udaju
    d["sekce_nace"] = d.NACE2025.str[:2].map(NACE.sekce_nace)
    d["velikost"] = d.KATPO.map(velikost_skupina)
    u = uzemi.z_iczuj(d.ICZUJ)
    u["metoda"] = pd.NA
    u.loc[u.kod_obce.notna(), "metoda"] = "kód obce/MČ (ICZUJ)"
    u["metoda_mc"] = pd.NA
    doplnit(u, uzemi.z_adresy(d.KODADM), "metoda", "adresní místo RÚIAN")
    u["kod_okresu"] = u.kod_obce.map(uzemi.okres_obce)
    u["kod_okresu"] = u.kod_okresu.fillna(d.OKRESLAU)
    u.loc[u.kod_obce.isna() & u.kod_okresu.notna(), "metoda"] = "jen okres"
    u.loc[bez_udaju, "metoda"] = "anonymizovaný zaniklý subjekt (jen IČO)"
    u["metoda"] = u.metoda.fillna(NEZJISTENO)
    d = d.join(u)
    info = {"res_radku": n_vse, "res_bez_udaju": int(bez_udaju.sum()), "res_stav": stav}
    return d, info


def nacti_ares(uzemi, res):
    if not ares_vr.ARCHIV.exists():
        sys.exit(f"Chybí {ares_vr.ARCHIV} – spusť stahni_data.py")
    if not ares_vr.je_aktualni():
        print("  ARES: extrahuji veřejný rejstřík z archivu (desítky minut)", flush=True)
        ares_vr.extrahuj()
    d = pd.read_csv(ares_vr.CIL, dtype=str)
    stav = pd.Timestamp(ares_vr.STAV.read_text(encoding="utf-8").strip())
    d["vznik"] = pd.to_datetime(d.datum_zapisu, errors="coerce")
    d["zanik"] = pd.to_datetime(d.datum_vymazu, errors="coerce")
    opravit_poradi(d)
    d["forma"] = d.pravni_forma.map(forma_skupina).replace("fyzicke_osoby", "ostatni_pravnicke")
    d["v_res"] = d.ico.isin(set(res.ICO))

    u = uzemi.z_adresy(d.ruian_adresa)
    u["metoda"] = pd.NA
    u.loc[u.kod_obce.notna(), "metoda"] = "adresní místo RÚIAN"
    u["metoda_mc"] = pd.NA
    # stejný subjekt v RES (podle IČO) – kód obce/MČ, který RES uvádí
    r = res.drop_duplicates("ICO").set_index("ICO")[["kod_obce", "kod_mc"]]
    zr = d[["ico"]].join(r, on="ico")[["kod_obce", "kod_mc"]]
    doplnit(u, zr, "metoda", "RES podle IČO")
    # podle názvu okresu a obce, u měst s MČ podle názvu MČ (mop / část obce)
    doplnit(u, podle_nazvu(d, uzemi), "metoda", "název obce a okresu")
    u["kod_okresu"] = u.kod_obce.map(uzemi.okres_obce)
    okresy = {norm(v): k for k, v in uzemi.obce.drop_duplicates("kod_okresu").set_index(
        "kod_okresu").okres.items()}
    okresy[norm("Hlavní město Praha")] = "CZ0100"
    u["kod_okresu"] = u.kod_okresu.fillna(d.okres.map(lambda x: okresy.get(norm(x))))
    u.loc[u.kod_obce.isna() & u.kod_okresu.notna(), "metoda"] = "jen okres"
    u["metoda"] = u.metoda.fillna(NEZJISTENO)
    d = d.join(u)
    return d, {"ares_stav": stav, "ares_subjektu": len(d)}


def podle_nazvu(d, uzemi):
    o = uzemi.obce.reset_index()
    o["n_obce"] = o.kod_obce.map(NAZVY_OBCI).map(norm)
    o["n_okres"] = o.okres.map(norm)
    jednoznacne = o.drop_duplicates(["n_okres", "n_obce"], keep=False)
    klic = dict(zip(zip(jednoznacne.n_okres, jednoznacne.n_obce), jednoznacne.kod_obce))
    praha = {norm(n): k for n, k in zip(o.n_obce, o.kod_obce) if k == 554782}
    okres = d.okres.map(norm).replace({norm("Hlavní město Praha"): norm("Praha")})
    obec = d.obec.map(norm)
    kod = pd.Series([klic.get((a, b)) for a, b in zip(okres, obec)], index=d.index, dtype="Int64")
    kod = kod.fillna(pd.Series([praha.get(b) for b in obec], index=d.index, dtype="Int64"))
    mc = uzemi.mc.reset_index()
    mc_klic = {(k, norm(n)): m for m, n, k in zip(mc.kod_mc, mc.nazev_mc, mc.kod_obce)}
    kod_mc = pd.Series(
        [mc_klic.get((k, norm(a))) or mc_klic.get((k, norm(b))) if pd.notna(k) else None
         for k, a, b in zip(kod, d.mop, d.cast_obce)], index=d.index, dtype="Int64")
    return pd.DataFrame({"kod_obce": kod, "kod_mc": kod_mc})


# --- bilance po letech -------------------------------------------------------

def bilance(d, klice, posledni_rok, stav_posledni, od_roku=PRVNI_ROK):
    """Aktivní k 31. 12. (v posledním roce ke dni dat), vzniklé a zaniklé v roce, po klíčích.

    Subjekt je aktivní ke dni t, když vznik <= t a (zánik chybí nebo zánik > t).
    """
    d = d[d.vznik.notna() & (d.vznik <= stav_posledni)].copy()
    d.loc[d.zanik > stav_posledni, "zanik"] = pd.NaT
    roky = list(range(od_roku, posledni_rok + 1))
    rv = d.vznik.dt.year.clip(lower=od_roku)
    rz = d.zanik.dt.year.clip(lower=od_roku)
    # číselné klíče: chybějící = -1, textové = "" (pandas 3 má text jako dtype str, ne object)
    k = [d[c].fillna(-1) if pd.api.types.is_numeric_dtype(d[c]) else d[c].astype(object).fillna("")
         for c in klice]
    vz = d.groupby(k + [rv]).size()
    za = d[d.zanik.notna()].groupby(k + [rz[d.zanik.notna()]]).size()
    vz.index.names = za.index.names = klice + ["rok"]
    vzn = d[d.vznik.dt.year >= od_roku].groupby(k + [d.vznik.dt.year]).size()
    zan = d[d.zanik.dt.year >= od_roku].groupby(k + [d.zanik.dt.year]).size()
    vzn.index.names = zan.index.names = klice + ["rok"]
    t = pd.concat({"vz": vz, "za": za}, axis=1, sort=False).fillna(0)
    t = t.unstack("rok").reindex(columns=pd.MultiIndex.from_product([["vz", "za"], roky], names=[None, "rok"]),
                                 fill_value=0).fillna(0)
    aktivni = (t["vz"] - t["za"]).cumsum(axis=1).stack().rename("aktivni")
    vysl = pd.DataFrame({"aktivni": aktivni})
    vysl["vznikle"] = vzn.reindex(vysl.index).fillna(0)
    vysl["zanikle"] = zan.reindex(vysl.index).fillna(0)
    return vysl.astype(int)


def rozpad(d, klice, sloupec, posledni_rok, stav, od_roku=PRVNI_ROK):
    """Aktivní subjekty po kategoriích sloupce (formy, velikost) jako sloupce."""
    b = bilance(d, klice + [sloupec], posledni_rok, stav, od_roku).aktivni
    return b.unstack(sloupec, fill_value=0)


def tabulka(d, klice, posledni_rok, stav, prefix, od_roku=PRVNI_ROK, formy=True):
    b = bilance(d, klice, posledni_rok, stav, od_roku)
    if formy:
        f = rozpad(d, klice, "forma", posledni_rok, stav, od_roku)
        b = b.join(f, how="left").fillna(0)
    b = b.astype(int)
    return b.rename(columns=lambda c: prefix(c))


# --- hlavní ------------------------------------------------------------------

class Nace:
    def __init__(self):
        n = pd.read_csv(CISELNIKY / "nace_2025.csv", dtype=str)
        self.sekce_nace = dict(zip(n.oddil_nace, n.sekce_nace))
        self.nazvy = dict(zip(n.sekce_nace, n.nazev_sekce))


NACE = None
NAZVY_OBCI = {}


def uloz(df, jmeno):
    cesta = VYSTUP / jmeno
    df.to_csv(cesta, index=False, encoding="utf-8-sig", lineterminator="\n")
    print(f"  {jmeno}: {len(df):,} řádků")


def main():
    global NACE, NAZVY_OBCI
    VYSTUP.mkdir(exist_ok=True)
    NACE = Nace()
    obce, mc = nacti_ciselnik_obci()
    am, nazvy, ruian_stav = nacti_ruian()
    nazvy["kod_obce"] = pd.to_numeric(nazvy.kod_obce)
    NAZVY_OBCI = nazvy.drop_duplicates("kod_obce").set_index("kod_obce").nazev_obce.to_dict()
    # názvy MČ a správní obvody Prahy z RÚIAN (číselník voleb má u Prahy jen kódy MČ)
    rm = nazvy.dropna(subset=["kod_mc"]).copy()
    rm["kod_mc"] = pd.to_numeric(rm.kod_mc)
    mc = mc.merge(rm[["kod_mc", "spravni_obvod"]], on="kod_mc", how="left")
    mc["nazev_obce"] = mc.kod_obce.map(NAZVY_OBCI)
    mc[["kod_obce", "nazev_obce", "spravni_obvod", "kod_mc", "nazev_mc"]].sort_values(
        ["nazev_obce", "kod_mc"]).to_csv(CISELNIKY / "mestske_casti.csv", index=False,
                                         encoding="utf-8-sig", lineterminator="\n")
    uzemi = Uzemi(obce, mc, am)

    res, info_res = nacti_res(uzemi)
    ares, info_ares = nacti_ares(uzemi, res)
    stav = info_res["res_stav"]
    rok = stav.year
    stav_ares = min(info_ares["ares_stav"], stav)
    # RES obsahuje zaniklé subjekty jen od určitého roku – stav je úplný od konce předchozího roku
    zmin = res.zanik.min()
    res_od = zmin.year if (zmin.month, zmin.day) != (1, 1) else zmin.year - 1
    print(f"  RES: stav {stav:%d. %m. %Y}, nejstarší zánik {zmin:%d. %m. %Y} -> řada od {res_od}; "
          f"ARES: stav {info_ares['ares_stav']:%d. %m. %Y}")

    pre_vr = lambda c: {"aktivni": "rejstrik_aktivni", "vznikle": "rejstrik_zapsano",
                        "zanikle": "rejstrik_vymazano"}.get(c, f"rejstrik_{c}")
    pre_res = lambda c: {"aktivni": "subjekty_aktivni", "vznikle": "subjekty_vznikle",
                         "zanikle": "subjekty_zanikle"}.get(c, c)
    sl_vr = ["rejstrik_aktivni", "rejstrik_zapsano", "rejstrik_vymazano"] + [
        f"rejstrik_{s}" for s in SKUPINY_PO]
    sl_res = ["subjekty_aktivni", "subjekty_vznikle", "subjekty_zanikle", "fyzicke_osoby",
              "pravnicke_osoby", "forma_nezjistena"] + SKUPINY_PO

    def spoj(klice):
        vr = tabulka(ares, klice, rok, stav_ares, pre_vr)
        rs = tabulka(res, klice, rok, stav, pre_res, od_roku=res_od)
        t = vr.join(rs, how="outer")
        for c in sl_vr + sl_res:
            if c not in t and c != "pravnicke_osoby":
                t[c] = 0
        t["pravnicke_osoby"] = t[SKUPINY_PO].sum(axis=1, min_count=1)
        t = t.reset_index()
        t.loc[t.rok < res_od, sl_res] = pd.NA
        t.loc[t.rok == res_od, ["subjekty_vznikle", "subjekty_zanikle"]] = pd.NA
        t[sl_vr] = t[sl_vr].fillna(0)
        return t

    def stav_k(r):
        return stav.date().isoformat() if r == rok else f"{r}-12-31"

    # --- obce ---
    t = spoj(["kod_obce", "kod_okresu"])
    t["kod_obce"] = t.kod_obce.replace(-1, pd.NA).astype("Int64")
    t["kod_okresu"] = t.kod_okresu.replace("", pd.NA)
    # všechny obce číselníku, i bez subjektů
    mrizka = pd.MultiIndex.from_product([obce.kod_obce, range(PRVNI_ROK, rok + 1)],
                                        names=["kod_obce", "rok"]).to_frame(index=False)
    mrizka["kod_okresu"] = mrizka.kod_obce.map(uzemi.okres_obce)
    t = mrizka.merge(t, on=["kod_obce", "kod_okresu", "rok"], how="outer")
    t[sl_vr] = t[sl_vr].fillna(0)
    jr = ["subjekty_aktivni", "fyzicke_osoby", "pravnicke_osoby", "forma_nezjistena"] + SKUPINY_PO
    t.loc[t.rok >= res_od, jr] = t.loc[t.rok >= res_od, jr].fillna(0)
    t.loc[t.rok > res_od, ["subjekty_vznikle", "subjekty_zanikle"]] = \
        t.loc[t.rok > res_od, ["subjekty_vznikle", "subjekty_zanikle"]].fillna(0)
    ok = obce.set_index("kod_okresu")[["okres", "kod_kraje", "kraj"]].drop_duplicates()
    ok = ok[~ok.index.duplicated()]
    t = t.join(ok, on="kod_okresu")
    t["nazev_obce"] = t.kod_obce.map(NAZVY_OBCI).fillna(NEZJISTENO)
    t["rok"] = t.rok.astype(int)
    t["stav_k"] = t.rok.map(stav_k)
    t = t.sort_values(["rok", "kod_okresu", "kod_obce"], na_position="last")
    sloupce_obce = ["rok", "stav_k", "kod_obce", "nazev_obce", "kod_okresu", "okres",
                    "kod_kraje", "kraj"] + sl_vr + sl_res
    obce_out = t[sloupce_obce].copy()
    cele = sl_vr + sl_res
    obce_out[cele] = obce_out[cele].astype("Int64")
    obce_out["rok"] = obce_out.rok.astype(int)
    uloz(obce_out, "subjekty_obce.csv")

    # --- městské části ---
    a_m = ares[ares.kod_obce.isin(uzemi.mesta_s_mc)]
    r_m = res[res.kod_obce.isin(uzemi.mesta_s_mc)]
    vr = tabulka(a_m, ["kod_obce", "kod_mc"], rok, stav_ares, pre_vr)
    rs = tabulka(r_m, ["kod_obce", "kod_mc"], rok, stav, pre_res, od_roku=res_od)
    m = vr.join(rs, how="outer").reset_index()
    for c in sl_vr + sl_res:
        if c not in m and c != "pravnicke_osoby":
            m[c] = 0
    m["pravnicke_osoby"] = m[SKUPINY_PO].sum(axis=1, min_count=1)
    m.loc[m.rok < res_od, sl_res] = pd.NA
    m.loc[m.rok == res_od, ["subjekty_vznikle", "subjekty_zanikle"]] = pd.NA
    m["kod_mc"] = m.kod_mc.replace(-1, pd.NA).astype("Int64")
    mrizka = pd.MultiIndex.from_product([mc.kod_mc, range(PRVNI_ROK, rok + 1)],
                                        names=["kod_mc", "rok"]).to_frame(index=False)
    mrizka["kod_obce"] = mrizka.kod_mc.map(mc.set_index("kod_mc").kod_obce)
    m = mrizka.merge(m, on=["kod_obce", "kod_mc", "rok"], how="outer")
    m[sl_vr] = m[sl_vr].fillna(0)
    jen_res = ["subjekty_aktivni", "fyzicke_osoby", "pravnicke_osoby", "forma_nezjistena"] + SKUPINY_PO
    m.loc[m.rok >= res_od, jen_res] = m.loc[m.rok >= res_od, jen_res].fillna(0)
    m.loc[m.rok > res_od, ["subjekty_vznikle", "subjekty_zanikle"]] = \
        m.loc[m.rok > res_od, ["subjekty_vznikle", "subjekty_zanikle"]].fillna(0)
    mi = mc.set_index("kod_mc")
    m["nazev_obce"] = m.kod_obce.map(NAZVY_OBCI)
    m["spravni_obvod"] = m.kod_mc.map(mi.spravni_obvod)
    m["nazev_mc"] = m.kod_mc.map(mi.nazev_mc).fillna(NEZJISTENO)
    m["rok"] = m.rok.astype(int)
    m["stav_k"] = m.rok.map(stav_k)
    m = m.sort_values(["rok", "nazev_obce", "kod_mc"], na_position="last")
    mc_out = m[["rok", "stav_k", "kod_obce", "nazev_obce", "spravni_obvod", "kod_mc", "nazev_mc"]
               + sl_vr + sl_res].copy()
    mc_out[cele] = mc_out[cele].astype("Int64")
    mc_out["rok"] = mc_out.rok.astype(int)
    uloz(mc_out, "subjekty_mestske_casti.csv")

    # --- CZ-NACE (jen RES) ---
    res["sekce_nace"] = res.sekce_nace.fillna("")

    def nace(df, klice):
        b = bilance(df, klice + ["sekce_nace"], rok, stav, res_od)
        f = rozpad(df, klice + ["sekce_nace"], "forma", rok, stav, res_od)
        b["fyzicke_osoby"] = f.get("fyzicke_osoby", 0)
        b["forma_nezjistena"] = f.get("forma_nezjistena", 0)
        b["pravnicke_osoby"] = f.drop(columns=["fyzicke_osoby", "forma_nezjistena"],
                                      errors="ignore").sum(axis=1)
        v = rozpad(df, klice + ["sekce_nace"], "velikost", rok, stav, res_od)
        b = b.join(v.reindex(columns=VELIKOSTI, fill_value=0)).fillna(0).astype(int).reset_index()
        b = b.rename(columns={"aktivni": "subjekty_aktivni", "vznikle": "subjekty_vznikle",
                              "zanikle": "subjekty_zanikle"})
        b.loc[b.rok == res_od, ["subjekty_vznikle", "subjekty_zanikle"]] = pd.NA
        b.loc[b.rok != rok, VELIKOSTI] = pd.NA  # velikost je jen aktuální stav
        b["nazev_sekce"] = b.sekce_nace.map(NACE.nazvy).fillna(NEZJISTENO)
        b["rok"] = b.rok.astype(int)
        b["stav_k"] = b.rok.map(stav_k)
        cisla = ["subjekty_aktivni", "subjekty_vznikle", "subjekty_zanikle", "fyzicke_osoby",
                 "pravnicke_osoby", "forma_nezjistena"] + VELIKOSTI
        b[cisla] = b[cisla].astype("Int64")
        # řádky bez jediného subjektu v celé řadě se vynechají
        nenulove = b.groupby(klice + ["sekce_nace"]).subjekty_aktivni.transform("sum") + \
            b.groupby(klice + ["sekce_nace"]).subjekty_zanikle.transform("sum").fillna(0)
        return b[nenulove > 0], cisla

    n, cisla = nace(res, ["kod_okresu"])
    n["kod_okresu"] = n.kod_okresu.replace("", pd.NA)
    n = n.join(ok, on="kod_okresu")
    n["okres"] = n.okres.fillna(NEZJISTENO)
    n = n.sort_values(["rok", "kod_okresu", "sekce_nace"], na_position="last")
    n.loc[n.sekce_nace == "", "sekce_nace"] = pd.NA
    uloz(n[["rok", "stav_k", "kod_okresu", "okres", "kod_kraje", "kraj", "sekce_nace",
            "nazev_sekce"] + cisla], "subjekty_nace_okresy.csv")

    nm, _ = nace(r_m, ["kod_obce", "kod_mc"])
    nm["kod_mc"] = nm.kod_mc.replace(-1, pd.NA).astype("Int64")
    nm["nazev_obce"] = nm.kod_obce.map(NAZVY_OBCI)
    nm["nazev_mc"] = nm.kod_mc.map(mi.nazev_mc).fillna(NEZJISTENO)
    nm = nm.sort_values(["rok", "nazev_obce", "kod_mc", "sekce_nace"], na_position="last")
    nm.loc[nm.sekce_nace == "", "sekce_nace"] = pd.NA
    uloz(nm[["rok", "stav_k", "kod_obce", "nazev_obce", "kod_mc", "nazev_mc", "sekce_nace",
             "nazev_sekce"] + cisla], "subjekty_nace_mestske_casti.csv")

    # --- kontroly ---
    kontrola_souctu(obce_out, mc_out, n, ares, res, rok, stav, stav_ares, res_od, uzemi)
    kontrola_parovani(ares, res, info_res, info_ares)
    zdroje = json.loads((DATA / "zdroje.json").read_text(encoding="utf-8")) \
        if (DATA / "zdroje.json").exists() else {}
    meta = {"res_stav": stav.date().isoformat(), "ares_stav": info_ares["ares_stav"].date().isoformat(),
            "ruian_stav": pd.Timestamp(ruian_stav).date().isoformat(), "res_od": res_od,
            "prvni_rok": PRVNI_ROK, "zpracovano": date.today().isoformat(), "zdroje": zdroje}
    (VYSTUP / "stav_dat.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                          encoding="utf-8")

    # Excel jen lokálně (v GitHub Actions ho vytváří až web.py, export tabulky obcí trvá minuty)
    for jmeno in [] if os.environ.get("CI") else ["subjekty_mestske_casti.csv", "subjekty_nace_okresy.csv",
                  "subjekty_nace_mestske_casti.csv", "subjekty_obce.csv"]:
        d = pd.read_csv(VYSTUP / jmeno, dtype=str)
        cis = [c for c in d.columns if c not in ("stav_k", "nazev_obce", "okres", "kod_okresu",
                                                 "kod_kraje", "kraj", "spravni_obvod", "nazev_mc",
                                                 "sekce_nace", "nazev_sekce")]
        d[cis] = d[cis].apply(pd.to_numeric).astype("Int64")
        d.to_excel(VYSTUP / jmeno.replace(".csv", ".xlsx"), index=False, freeze_panes=(1, 0))

    import kontrola
    kontrola.main()


def kontrola_souctu(obce_out, mc_out, n, ares, res, rok, stav, stav_ares, res_od, uzemi):
    """Součty za ČR po letech: bilance stavu, součet forem, MČ proti městům, NACE proti obcím."""
    cr = obce_out.groupby("rok").sum(numeric_only=True, min_count=1)
    k = pd.DataFrame(index=cr.index)
    k["stav_k"] = [stav.date().isoformat() if r == rok else f"{r}-12-31" for r in k.index]
    for c in ["rejstrik_aktivni", "rejstrik_zapsano", "rejstrik_vymazano",
              "subjekty_aktivni", "subjekty_vznikle", "subjekty_zanikle", "fyzicke_osoby",
              "pravnicke_osoby", "forma_nezjistena"]:
        k[c] = cr[c]
    # stav = stav minulého roku + vznik − zánik (u ARES v posledním roce ke dni dat ARES)
    k["rejstrik_bilance_rozdil"] = (cr.rejstrik_aktivni - cr.rejstrik_aktivni.shift()
                                    - cr.rejstrik_zapsano + cr.rejstrik_vymazano)
    k.loc[k.index == PRVNI_ROK, "rejstrik_bilance_rozdil"] = pd.NA
    k["subjekty_bilance_rozdil"] = (cr.subjekty_aktivni - cr.subjekty_aktivni.shift()
                                    - cr.subjekty_vznikle + cr.subjekty_zanikle)
    k["rejstrik_formy_rozdil"] = cr[[f"rejstrik_{s}" for s in SKUPINY_PO]].sum(axis=1) - cr.rejstrik_aktivni
    k["subjekty_formy_rozdil"] = (cr.fyzicke_osoby + cr.pravnicke_osoby + cr.forma_nezjistena
                                  - cr.subjekty_aktivni)
    k["pravnicke_formy_rozdil"] = cr[SKUPINY_PO].sum(axis=1, min_count=1) - cr.pravnicke_osoby
    # přímý přepočet ze zdroje (nezávisle na seskupení) – musí sedět na součet obcí
    k["rejstrik_zdroj"] = [aktivni_k(ares, pd.Timestamp(f"{r}-12-31") if r < rok else stav_ares)
                           for r in k.index]
    k["subjekty_zdroj"] = [aktivni_k(res, pd.Timestamp(f"{r}-12-31") if r < rok else stav)
                           if r >= res_od else pd.NA for r in k.index]
    k["rejstrik_zdroj_rozdil"] = k.rejstrik_aktivni - k.rejstrik_zdroj
    k["subjekty_zdroj_rozdil"] = k.subjekty_aktivni - k.subjekty_zdroj
    # MČ proti řádkům měst v tabulce obcí
    mesta = obce_out[obce_out.kod_obce.isin(uzemi.mesta_s_mc)].groupby("rok").sum(numeric_only=True,
                                                                                  min_count=1)
    mcs = mc_out.groupby("rok").sum(numeric_only=True, min_count=1)
    k["mc_rejstrik_rozdil"] = mcs.rejstrik_aktivni - mesta.rejstrik_aktivni
    k["mc_subjekty_rozdil"] = mcs.subjekty_aktivni - mesta.subjekty_aktivni
    ns = n.groupby("rok").sum(numeric_only=True, min_count=1)
    k["nace_rozdil"] = ns.subjekty_aktivni - cr.subjekty_aktivni
    k["velikost_rozdil"] = ns[VELIKOSTI].sum(axis=1, min_count=1) - ns.subjekty_aktivni
    k.loc[k.index != rok, "velikost_rozdil"] = pd.NA
    k["zmena_rejstrik"] = cr.rejstrik_aktivni.pct_change().round(4)
    k["zmena_subjekty"] = cr.subjekty_aktivni.pct_change().round(4)
    k = k.reset_index()
    cele = [c for c in k.columns if c not in ("stav_k", "zmena_rejstrik", "zmena_subjekty")]
    k[cele] = k[cele].astype("Int64")
    uloz(k, "kontrola_souctu.csv")


def aktivni_k(d, t):
    return int(((d.vznik <= t) & (d.zanik.isna() | (d.zanik > t))).sum())


def kontrola_parovani(ares, res, info_res, info_ares):
    radky = []

    def pridej(zdroj, ukazatel, pocet, z):
        radky.append({"zdroj": zdroj, "ukazatel": ukazatel, "pocet": int(pocet),
                      "podil": round(pocet / z, 4) if z else None})

    na = len(ares)
    pridej("ARES", "subjekty veřejného rejstříku celkem", na, na)
    pridej("ARES", "aktivní ke dni dat", ares.zanik.isna().sum(), na)
    for metoda, pocet in ares.metoda.value_counts().items():
        pridej("ARES", f"území: {metoda}", pocet, na)
    pridej("ARES", "nalezeno v RES podle IČO", ares.v_res.sum(), na)
    akt = ares[ares.zanik.isna()]
    pridej("ARES", "aktivní nalezené v RES podle IČO", akt.v_res.sum(), len(akt))
    pridej("ARES", "bez data zápisu (nezapočítáno)", ares.vznik.isna().sum(), na)
    pridej("ARES", "výmaz před zápisem", ares.zanik_pred_vznikem.sum(), na)
    pridej("ARES", "v městě s MČ, MČ nezjištěna",
           (ares.kod_obce.isin(MESTA_S_MC) & ares.kod_mc.isna()).sum(),
           ares.kod_obce.isin(MESTA_S_MC).sum())

    nr = info_res["res_radku"]
    pridej("RES", "řádky souboru celkem", nr, nr)
    pridej("RES", "zaniklé bez údajů (jen IČO a datum zániku, v řádku nezjištěno)",
           info_res["res_bez_udaju"], nr)
    n = len(res)
    pridej("RES", "subjekty s údaji", n, n)
    pridej("RES", "aktivní ke dni dat", res.zanik.isna().sum(), n)
    for metoda, pocet in res.metoda.value_counts().items():
        pridej("RES", f"území: {metoda}", pocet, n)
    pridej("RES", "v městě s MČ, MČ nezjištěna",
           (res.kod_obce.isin(MESTA_S_MC) & res.kod_mc.isna()).sum(),
           res.kod_obce.isin(MESTA_S_MC).sum())
    pridej("RES", "nejstarší zánik v souboru (rok; řada úplná od konce tohoto roku)",
           res.zanik.min().year, 0)
    a = res[res.zanik.isna()]
    pridej("RES", "aktivní bez sekce CZ-NACE", (a.sekce_nace == "").sum(), len(a))
    pridej("RES", "aktivní bez velikostní kategorie", (a.velikost == "velikost_neuvedeno").sum(), len(a))
    pridej("RES", "bez data vzniku (nezapočítáno)", res.vznik.isna().sum(), n)
    pridej("RES", "zánik před vznikem", res.zanik_pred_vznikem.sum(), n)
    uloz(pd.DataFrame(radky), "kontrola_parovani.csv")


MESTA_S_MC = {554782, 582786, 554821, 554791, 555134, 505927, 563889, 554804}

if __name__ == "__main__":
    sys.exit(main())
