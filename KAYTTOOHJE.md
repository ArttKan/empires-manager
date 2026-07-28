# Mega Empires -peliseuranta

## Käynnistäminen

Ohjelma toimii Python 3.12:lla eikä tarvitse ulkopuolisia kirjastoja.

Käynnistä PowerShellissä tästä hakemistosta:

```powershell
python app.py
```

Ohjelma avautuu 1920 × 1080 -kokoisena. Ikkunaa voi käyttää myös
pienemmässä koossa, mutta television kanssa suositus on Full HD.

## Uusi peli

1. Valitse pelaajamäärä väliltä 5–18.
2. Kun pelaajia on 5–9, valitse käytetäänkö The West- vai The East
   -pelilaatikkoa. Kun pelaajia on 10–18, ohjelma valitsee automaattisesti
   The West + The East -yhdistelmäpelin.
3. Ohjelma valitsee pelaajamäärän mukaisen virallisen
   sivilisaatiokokoonpanon.
4. Kirjoita jokaisen sivilisaation pelaajan etunimi tai lempinimi.
5. Viimeisen pelaajan jälkeen pistenäkymä avautuu automaattisesti.

Pelaaja näkyy ohjelmassa muodossa `Sivilisaatio (nimi)`.

## Pistetilanteen päivittäminen

- **Cities:** muuta määrää pelaajan rivin −/+ -painikkeilla.
- **A.S.T.:** muuta askelta pelaajan rivin −/+ -painikkeilla tai napsauta
  haluttua ruutua A.S.T.-taulussa.
- **Census:** kirjoita väestömäärä suoraan pelaajan rivin Census-kenttään
  (0–55).
- **Civilization Advances:** avaa **Advances**, valitse kaikki pelaajan hankkimat
  kortit ja tallenna.
- **Nimi, kauppalohko ja A.S.T.-bonus:** avaa **Details**.

Advances-ikkunassa korttien taustavärit näyttävät niiden ryhmät: Arts,
Civics, Crafts, Religions ja Sciences. Kahteen ryhmään kuuluvan kortin rivi on
kaksivärinen. Valittu kortti merkitään lisäksi rastilla ja kultaisella
reunuksella. **Save Advances** hyväksyy muutokset ja **Cancel** hylkää ne.

Ikkunan yläosan viisi värikenttää näyttävät pelaajan aiemmin tallennetuista
korteista kertyneet pysyvät krediitit. Viiden pelaajan pelin 10 ja kuuden
pelaajan pelin 5 aloituskrediittiä per väri lisätään automaattisesti.
Written Recordin ja Monumentin vapaasti jaettavat krediitit voidaan kohdistaa
värikenttien **Flexible**-arvoilla sen jälkeen, kun kortit on tallennettu.

Ostamattoman kortin oikeassa reunassa näkyy automaattisesti joko sen hinta tai
muutos muodossa `120 → 90`. Kaksivärisellä kortilla käytetään vain suurempaa
kahdesta värikrediitistä. Referenssin jokainen vaakarivi on ketju
**1 VP → 3 VP → 6 VP**: aiemmin ostettu 1 VP -kortti antaa saman rivin
3 VP -korttiin 10 lisäalennusta ja 3 VP -kortti saman rivin 6 VP -korttiin
20 lisäalennusta. Valinnaisia kertaluonteisia vaikutuksia, kuten Libraryn
40 pisteen alennusta yhteen samalla kierroksella ostettavaan korttiin, ei
sisällytetä automaattiseen hintaan.

Pisteet ja sijoitukset päivittyvät heti. Piste-erittely näkyy järjestyksessä:

```text
kaupungit + AST + Advance-kortit + AST-bonus
```

Scoreboardin pelaajarivit pysyvät samassa sivilisaatioiden A.S.T.-järjestyksessä
kuin A.S.T.-taululla. Rivin vasemman reunan suuri numero näyttää pelaajan
senhetkisen pistesijoituksen.

A.S.T.-loppubonus vahvistetaan käsin **Details**-ikkunassa vasta pelin
päättävällä A.S.T.-vaiheella. Ohjelma estää bonuksen antamisen yli kahdelle
pelaajalle ja kahdelle saman kauppalohkon pelaajalle.

## A.S.T.-näkymä

Näkymä käyttää Basic A.S.T.:ta ja näyttää jokaiselle mukana olevalle
sivilisaatiolle sen omat SA-, EBA-, MBA- ja LBA-rajat. Kaikilla
sivilisaatioilla EIA on askel 14 (70 pistettä) ja LIA askel 15 (75 pistettä).
Aikakaudet on erotettu väreillä, lyhenteillä ja korostetuilla rajaviivoilla.
Oikean reunan paneeli näyttää kaikkien kuuden aikakauden vaatimukset.

Pelaajan markkerissa näkyvä symboli kertoo vaatimustilanteen:

- vihreä **✓:** seuraavan aikakauden vaatimukset täyttyvät;
- punainen **X:** seuraavan aikakauden vaatimukset eivät vielä täyty;
- oranssi **!:** nykyisen aikakauden vaatimukset eivät enää täyty;
- kultainen **★:** A.S.T.:n loppuruutu on saavutettu.

Basic-pelissä nykyisen aikakauden vaatimusten menettäminen estää etenemisen,
mutta ei itsessään siirrä markkeria taaksepäin. Expert-pelissä nollaan
kaupunkiin jäänyt pelaaja siirtyy yhden askeleen taakse, paitsi Stone Agessa.
Expert A.S.T. lisätään myöhemmin erillisenä aloitusvalintana.

Ikkunan yläreunan **TURN −/+** -säätimillä kierrosnumeroa voi korjata käsin.
Sequence of Play -välilehti kasvattaa kierrosnumeroa automaattisesti, kun
vaiheesta 13 siirrytään seuraavan kierroksen vaiheeseen 1.

## Sequence of Play -avustin

Kolmas välilehti näyttää kaikki pelin 13 vaihetta. Nykyinen vaihe on korostettu,
ja oikealla näkyvät sen tiivistetyt pääsäännöt sekä tarvittaessa automaattisesti
laskettu pelaajajärjestys.

- Vaiheen voi valita suoraan vasemman reunan listasta.
- **Previous Phase** ja **Next Phase** siirtävät aktiivista vaihetta.
- Vaiheen 13 jälkeen **Next Phase** kasvattaa kierrosnumeroa ja siirtyy
  seuraavan kierroksen vaiheeseen 1.
- Vaihe ja kierros tallentuvat automaattisesti.

Avustin käyttää seuraavia pelitietoja:

- **Movement:** Census laskevasti; A.S.T.-Ranking ratkaisee tasatilanteet.
  Militaryn omistajat liikkuvat kaikkien muiden jälkeen.
- **Trade Cards Acquisition:** vähiten kaupunkeja ensin; pelaajat, joilla ei
  ole kaupunkeja, eivät saa kortteja.
- **Special Abilities:** vain kyseisten Advance-korttien omistajat
  A.S.T.-Progress-järjestyksessä.
- **Civilization Advances Acquisition:** A.S.T.-Progress-järjestys.
- **A.S.T.-Alteration:** kiinteä A.S.T.-Ranking.

Conflict- ja Calamity-vaiheissa ei aina ole yhtä yleistä pelaajajärjestystä.
Niissä avustin näyttää tilanteeseen sovellettavan säännön ja
A.S.T.-Ranking-vertailulistan.

## Tallennus

Ohjelma tallentaa jokaisen muutoksen automaattisesti tiedostoon:

```text
tallennukset/nykyinen_peli.json
```

Seuraavalla käynnistyskerralla ohjelma kysyy, jatketaanko tallennettua peliä.
Uuden pelin aloittaminen korvaa tämän tallennuksen, kun ensimmäinen uusi peli
on perustettu.

## Testien ajaminen

```powershell
python -m unittest discover -v
```
