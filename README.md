# Ekonomické subjekty v obcích ČR

Počty ekonomických subjektů (firem, spolků, SVJ, OSVČ a dalších) v obcích ČR a v městských částech
statutárních měst, s počty vzniklých a zaniklých subjektů po letech. Sada vzniká jen z otevřených dat:

- **ARES – veřejný rejstřík** (Ministerstvo financí): všechny subjekty, které kdy byly v obchodním,
  spolkovém, nadačním rejstříku, rejstříku ústavů, SVJ a o. p. s., včetně vymazaných → řada **od roku 1990**.
- **RES – Registr ekonomických subjektů** (ČSÚ): všechny ekonomické subjekty včetně OSVČ, s oborem
  (CZ-NACE 2025) a velikostí → řada **od konce roku 2022** (víc zaniklých subjektů ČSÚ nezveřejňuje).
- **RÚIAN** (ČÚZK): adresní místo sídla → obec a městská část.

- **Web s daty ke stažení:** https://opendatabrno.github.io/subjekty/
- **Zdroje:** [ARES hromadná data](https://ares.gov.cz/otevrena-data/ares_vreo_all.tar.gz) ·
  [RES – otevřená data ČSÚ](https://opendata.czso.cz/data/od_org03/res_data.csv) ·
  [RÚIAN – adresní místa](https://vdp.cuzk.cz/vymenny_format/csv/)

**Obsah:** [Datové sady](#datové-sady) · [Sloupce](#sloupce) · [Na co si dát pozor](#na-co-si-dát-pozor) ·
[Aktualizace dat](#aktualizace-dat) · [Kontroly](#kontroly) · [Soubory v repozitáři](#soubory-v-repozitáři) ·
[Jak se data zpracovávají](#jak-se-data-zpracovávají)

---

## Datové sady

| Soubor | Co obsahuje | Jeden řádek | Klíč |
|---|---|---|---|
| [`vystup/subjekty_obce.csv`](vystup/subjekty_obce.csv) | všechny obce ČR (~6 250) + „nezjištěno“ za okres | obec × rok | `rok` + `kod_obce` (+ `kod_okresu` u nezjištěných) |
| [`vystup/subjekty_mestske_casti.csv`](vystup/subjekty_mestske_casti.csv) | MČ 8 měst: Praha, Brno, Ostrava, Plzeň, Pardubice, Opava, Liberec, Ústí nad Labem | MČ × rok | `rok` + `kod_mc` |
| [`vystup/subjekty_nace_okresy.csv`](vystup/subjekty_nace_okresy.csv) | jen RES, obory podle CZ-NACE 2025 | okres × sekce × rok | `rok` + `kod_okresu` + `sekce_nace` |
| [`vystup/subjekty_nace_mestske_casti.csv`](vystup/subjekty_nace_mestske_casti.csv) | jen RES, obory v MČ | MČ × sekce × rok | `rok` + `kod_mc` + `sekce_nace` |

- Formát: CSV, UTF-8 s BOM, oddělovač čárka. Na [webu](https://opendatabrno.github.io/subjekty/)
  jsou sady ke stažení i jako Excel (`.xlsx`), lokálně vzniká `.xlsx` při zpracování.
- Kódy obcí a MČ jsou kódy ČSÚ, dají se spojit s dalšími sadami
  ([obyvatele](https://opendatabrno.github.io/obyvatele/), hranice MČ na [data.brno.cz](https://data.brno.cz)).
  Okres Brno-město = `CZ0642`, Brno-venkov = `CZ0643`.
- **Řádky tabulek obcí a MČ nesčítej dohromady.** MČ jsou části měst, která jsou v tabulce obcí jako celek.
- `stav_k` je 31. 12. daného roku, v posledním (neúplném) roce den, ke kterému jsou data RES.

## Sloupce

| Sloupec | Význam | Tabulka |
|---|---|---|
| `rok`, `stav_k` | rok a den, ke kterému platí stav | všechny |
| `kod_obce`, `nazev_obce` | kód ČSÚ a název obce (u MČ města); řádek `nezjištěno` = bez zjištěné obce | obce, MČ |
| `kod_okresu`, `okres`, `kod_kraje`, `kraj` | okres a kraj (NUTS) podle aktuálního číselníku obcí | obce, NACE okresy |
| `spravni_obvod`, `kod_mc`, `nazev_mc` | správní obvod Prahy, kód ČSÚ a název MČ; `nezjištěno` = MČ neurčena | MČ |
| `rejstrik_aktivni` | subjekty zapsané ve veřejném rejstříku a dosud nevymazané (ARES) | obce, MČ |
| `rejstrik_zapsano`, `rejstrik_vymazano` | zápisy a výmazy v roce | obce, MČ |
| `rejstrik_sro`, `rejstrik_akciove_spolecnosti`, `rejstrik_druzstva`, `rejstrik_spolky`, `rejstrik_svj`, `rejstrik_ostatni_pravnicke` | aktivní subjekty rejstříku podle právní formy | obce, MČ |
| `subjekty_aktivni` | všechny aktivní (nezaniklé) subjekty RES včetně OSVČ; prázdné před rokem 2022 | všechny |
| `subjekty_vznikle`, `subjekty_zanikle` | vzniklé a zaniklé subjekty v roce (RES); prázdné v prvním roce řady | všechny |
| `fyzicke_osoby`, `pravnicke_osoby`, `forma_nezjistena` | aktivní subjekty RES podle typu osoby | všechny |
| `sro`, `akciove_spolecnosti`, `druzstva`, `spolky`, `svj`, `ostatni_pravnicke` | právnické osoby v RES podle právní formy | obce, MČ |
| `sekce_nace`, `nazev_sekce` | sekce CZ-NACE 2025 hlavní činnosti (A–V); prázdná = obor neuveden | NACE |
| `velikost_0`, `velikost_1_9`, `velikost_10_49`, `velikost_50_249`, `velikost_250_plus`, `velikost_neuvedeno` | aktivní subjekty podle počtu zaměstnanců (ČSÚ), jen poslední rok | NACE |

**Jak se sloupce sčítají:**

```
rejstrik_aktivni = rejstrik_sro + rejstrik_akciove_spolecnosti + rejstrik_druzstva
                 + rejstrik_spolky + rejstrik_svj + rejstrik_ostatni_pravnicke
rejstrik_aktivni(rok) = rejstrik_aktivni(rok − 1) + rejstrik_zapsano − rejstrik_vymazano
subjekty_aktivni = fyzicke_osoby + pravnicke_osoby + forma_nezjistena
pravnicke_osoby  = sro + akciove_spolecnosti + druzstva + spolky + svj + ostatni_pravnicke
subjekty_aktivni(rok) = subjekty_aktivni(rok − 1) + subjekty_vznikle − subjekty_zanikle
velikost_0 + … + velikost_neuvedeno = subjekty_aktivni                      (jen poslední rok)
```

Skupiny právních forem (kódy ČSÚ): `sro` 112 · `akciove_spolecnosti` 121, 932 · `druzstva` 205, 933 ·
`spolky` 706, 736, 701, 906, 936 · `svj` 145 · fyzické osoby 101–108, 424, 425 · ostatní vše ostatní
(v.o.s., k.s., nadace, o. p. s., ústavy, obce, příspěvkové organizace, odštěpné závody…). Fyzické osoby
zapsané v obchodním rejstříku jsou ve sloupcích rejstříku v `rejstrik_ostatni_pravnicke`.

## Na co si dát pozor

- **Jen poslední sídlo.** ARES i RES uvádějí jen současné sídlo (u zaniklých poslední). Subjekt, který se
  přestěhoval, se ve všech letech počítá v obci, kde sídlí dnes. Historické rozložení po obcích a MČ je
  proto přibližné, součty za ČR ne.
- **Veřejný rejstřík není všechno.** `rejstrik_*` nezahrnuje OSVČ ani subjekty mimo rejstřík (obce,
  příspěvkové organizace, státní instituce). Úplný počet je `subjekty_aktivni` z RES.
- **RES je úplný až od konce roku 2022.** Otevřený RES obsahuje zaniklé subjekty jen zhruba za poslední
  čtyři roky (nejstarší zánik v souboru 1. 11. 2022), proto starší roky RES chybí. Až ČSÚ okno posune,
  první rok řady se posune také (viz [Co zbývá](#co-zbývá)).
- **Zaniklé fyzické osoby jsou v RES anonymizované** (jen IČO a datum zániku, ~500 tis. subjektů). Jsou
  v řádku „nezjištěno“ bez okresu, se sloupcem `forma_nezjistena`. Součty za ČR jsou úplné, ale v obcích
  v letech 2022–2025 chybí OSVČ, které později zanikly, a počty v obcích proto rostou rychleji, než
  odpovídá skutečnosti. Na úrovni obcí je spolehlivý hlavně poslední rok.
- **Rok 2023** má v RES hromadný zánik neaktivních subjektů (únor a březen, ~190 tis.).
- **Výmaz z rejstříku je opožděný** oproti faktickému konci činnosti, často o roky (likvidace, insolvence).
- **Zlom v roce 2014:** s novým občanským zákoníkem přešly do veřejného rejstříku spolky a SVJ
  (+150 tis. zápisů za ČR). V roce 2016 byla vlna výmazů nepřevedených spolků.
- **Obor a velikost** jsou podle současného stavu RES, ne historického. Velikost je jen za poslední rok,
  u poloviny subjektů ji ČSÚ neuvádí (`velikost_neuvedeno`).
- **Poslední rok je neúplný** a ARES bývá o měsíc starší než RES (oba dny jsou ve `vystup/stav_dat.json`
  a na webu).
- **Fyzické osoby jen v souhrnných počtech.** Výstupy neobsahují údaje o jednotlivých osobách ani
  seznamy subjektů.

---

## Aktualizace dat

### Automaticky (GitHub Actions)

Workflow [**Aktualizace dat o subjektech**](.github/workflows/aktualizace.yml) běží 6. den v měsíci
(a ručně přes *Actions → Aktualizace dat o subjektech → Run workflow*). Velká data drží v cache Actions
a stahuje jen to, co je na serveru novější (ARES ~870 MB, RES ~550 MB, RÚIAN ~65 MB).

| Co se stane | Co udělá workflow | Co uděláš ty |
|---|---|---|
| Zdroje se nezměnily | zpracuje stejná data, PR nevznikne (CSV beze změny) | nic |
| Nová data | založí **pull request** `aktualizace-dat` se souhrnem kontrol | projdi souhrn a přehled kontrol (artefakt `kontrola`) a PR slouč |
| Data se načetla, ale kontrola nesedí | PR s názvem začínajícím **„⚠️ Kontrola nesedí“** | zjisti příčinu v přehledu kontrol, PR neslučuj bez opravy |
| Zpracování selhalo | založí **issue** `zmena-struktury` s logem | upravit `zpracuj_data.py` / `ares_vr.py` |

Po sloučení PR workflow [**GitHub Pages**](.github/workflows/pages.yml) aktualizuje web.

**Jednorázové nastavení na GitHubu:**
1. *Settings → Pages → Source:* **GitHub Actions**
2. *Settings → Actions → General → Workflow permissions:* **Read and write permissions**
   a zaškrtnout **Allow GitHub Actions to create and approve pull requests**

> GitHub vypíná plánované workflows po 60 dnech bez aktivity v repozitáři (pošle e-mail).

### Ručně

```bash
pip install -r requirements.txt   # jen poprvé
python stahni_data.py             # stáhne nová data do data/ a číselníky do ciselniky/
python zpracuj_data.py            # zpracuje vše do vystup/ a vytvoří přehled kontrol
python web.py                     # volitelně: web do _site/
```

První extrakce ARES (přes milion XML) trvá asi 10 minut, celé zpracování dalších asi 5 minut
(lokálně ještě export do Excelu).

## Kontroly

Hlavní je stránka **`vystup/kontrola.html`** (lokálně po zpracování, online na webu).

| Kontrola | Co hlídá | Podklad |
|---|---|---|
| Součty rejstříku | bilance stav/zápisy/výmazy, součet forem, přímý přepočet ze zdroje = součet obcí; meziroční skok nad 10 % mimo známé zlomy | `vystup/kontrola_souctu.csv` |
| Součty RES | totéž pro RES + součet sekcí CZ-NACE a velikostí | `vystup/kontrola_souctu.csv` |
| MČ proti obcím | součet MČ (včetně „nezjištěno“) = řádky měst v tabulce obcí | `vystup/kontrola_souctu.csv` |
| Přiřazení k území | jak se subjekty přiřadily k obci, podíl nezjištěných, chybějící NACE a velikost | `vystup/kontrola_parovani.csv` |

**Známý rozdíl:** asi 2,5 % subjektů rejstříku nemá zjištěnou obec – většinou dávno vymazané subjekty,
jejichž adresa v RÚIAN už neexistuje a nejsou ani v RES. Jsou v řádcích „nezjištěno“ (s okresem, když je znám).

## Soubory v repozitáři

| Soubor | Účel |
|---|---|
| `stahni_data.py` | stažení ARES, RES, RÚIAN a číselníků |
| `ares_vr.py` | extrakce veřejného rejstříku z archivu ARES do `data/ares_vr.csv` |
| `zpracuj_data.py` | přiřazení k území, bilance po letech, výstupy a kontrolní CSV; spouští `kontrola.py` |
| `kontrola.py` | přehled kontrol `vystup/kontrola.html` a souhrn pro PR |
| `web.py` | web pro GitHub Pages do `_site/` |
| `ciselniky/pscoco.csv`, `cnumnuts.csv` | obce s okresy a kraji, vazba MČ → obec (volby.gov.cz) |
| `ciselniky/mestske_casti.csv` | MČ s kódy ČSÚ a správními obvody Prahy (vzniká při zpracování) |
| `ciselniky/pravni_formy.csv`, `velikost.csv` | číselníky ČSÚ 56 a 579 |
| `ciselniky/nace_2025.csv` | oddíly a sekce CZ-NACE 2025 (ČSÚ, verze s opravami 12/2025) |
| `vystup/` | datové sady, kontrolní soubory, `stav_dat.json` (k jakému dni jsou zdroje) |
| `data/` | stažená data a mezivýsledky (není v repozitáři) |

## Jak se data zpracovávají

1. **ARES** (`ares_vr.py`): z každého XML se vezme hlavní záznam subjektu (bez odštěpných závodů)
   s datem zápisu, výmazu, právní formou a posledním sídlem včetně kódu adresního místa RÚIAN.
2. **Přiřazení k obci a MČ.** RES: kód obce/MČ (`ICZUJ`, u statutárních měst je to přímo kód MČ),
   jinak adresní místo. ARES postupně: adresní místo RÚIAN (95 %), stejné IČO v RES, název obce
   a okresu (u MČ název MČ). Kódy MČ se převádějí na obce podle číselníku voleb.
3. **Bilance po letech:** subjekt je aktivní ke dni *t*, když vznikl (byl zapsán) nejpozději *t* a nezanikl
   (nebyl vymazán) do *t*. Vzniklé a zaniklé se počítají podle roku data. Zánik před vznikem (chyba ve
   zdroji, jednotky případů) se bere jako vznik a zánik týž den.
4. **RES:** první rok řady se odvozuje z nejstaršího zániku v souboru. Anonymizované zaniklé subjekty
   (jen IČO a datum zániku) se počítají jako aktivní od začátku řady do zániku, v řádku „nezjištěno“.
5. **Obory:** sekce CZ-NACE 2025 podle prvních dvou číslic hlavní činnosti (`NACE2025`).

## Co zbývá

- **Uchovávat roky RES, které z okna ČSÚ vypadnou** (teď se řada RES při posunu okna zkrátí), případně
  sbírat měsíční snímky RES a tím zpřesnit i historické sídlo.
- Napojit sadu na [vizualizace](https://github.com/opendatabrno/vizualizace) (mapa a graf obce).
- Historická data.brno 2017 (firmy s 5+ zaměstnanci) jako srovnání – zatím nezapracováno.
