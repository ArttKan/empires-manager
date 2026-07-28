# Mega Empires -peliseuranta

## Käynnistäminen

Ohjelma toimii Python 3.12:lla eikä tarvitse ulkopuolisia kirjastoja.

Käynnistä PowerShellissä tästä hakemistosta:

```powershell
python app.py
```

Ohjelma avautuu 1920 × 1080 -kokoisena. Ikkunaa voi käyttää myös
pienemmässä koossa, mutta television kanssa suositus on Full HD.

## Pelin valinta ja uusi peli

Kun ohjelma käynnistyy ja tallennuksia on olemassa, se näyttää tallennettujen
pelien luettelon. Valitse peli ja paina **Continue**, tai aloita uusi peli
painamalla **New Game**.

1. Anna tallennettavalle pelille yksilöllinen nimi. Samannimistä aiempaa
   tallennusta ei korvata vahingossa.
2. Valitse pelaajamäärä väliltä 3–18.
3. Kun pelaajia on 3–4, valitse The West- tai The East -kartalla pelattava
   erikoisskenaario. Kun pelaajia on 5–9, valitse käytetäänkö The West- vai The East
   -pelilaatikkoa. Kun pelaajia on 10–18, ohjelma valitsee automaattisesti
   The West + The East -yhdistelmäpelin.
4. Ohjelma valitsee pelaajamäärän mukaisen virallisen
   sivilisaatiokokoonpanon.
5. Kirjoita jokaisen sivilisaation pelaajan etunimi tai lempinimi.
6. Viimeisen pelaajan jälkeen pistenäkymä avautuu automaattisesti.

Kolmen pelaajan West-kokoonpano on Hellas, Minoa ja Hatti; neljän pelaajan
kokoonpano lisää Assyrian. East-kokoonpano on kolmella pelaajalla Indus,
Kushan ja Parthia ja neljällä pelaajalla lisäksi Persia. Ohjelma huomioi
skenaarion alkukrediitit, Eastin Parthian kolmen pelaajan Basic A.S.T.
-poikkeuksen sekä molempien karttojen Market board -muistutukset.

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
Kun Written Record tai Monument valitaan uutena ostoksena, ohjelma avaa
automaattisesti kohdistusikkunan. Written Recordin 10 tai Monumentin 20
krediittipistettä on jaettava kokonaan viiden värin kesken viiden pisteen
askelin ennen kuin kortti merkitään ostetuksi. Jako tallentuu pelaajan
**Flexible**-arvoihin.

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
ja keskellä näkyy vaiheen toimintajärjestys sekä tarvittaessa automaattisesti
laskettu pelaajajärjestys. Oikean reunan **Default Rules / Values** -paneeli
näyttää suurella tekstillä vain aktiivisen vaiheen tärkeimmät sääntöarvot.

- Vaiheen voi valita suoraan vasemman reunan listasta.
- **Previous Phase** ja **Next Phase** siirtävät aktiivista vaihetta.
- Vaiheen 13 jälkeen **Next Phase** kasvattaa kierrosnumeroa ja siirtyy
  seuraavan kierroksen vaiheeseen 1.
- Vaihe ja kierros tallentuvat automaattisesti.

Avustin käyttää seuraavia pelitietoja:

- **Movement:** Census laskevasti; A.S.T.-Ranking ratkaisee tasatilanteet.
  Militaryn omistajat liikkuvat kaikkien muiden jälkeen. Vaiheen ohjeissa
  muistutetaan myös alusten liikerajasta, kapasiteetista, rakentamismaksusta,
  ylläpitomaksusta ja pakollisesta maihinnoususta. Affecting Advances
  -kolumni ja oikea paneeli näyttävät Astronavigation-, Cloth Making-,
  Naval Warfare-, Roadbuilding-, Military-, Diplomacy-, Cultural Ascendancy-
  ja Advanced Military -kortit.
- **Tax Collection:** A.S.T.-järjestyslistan erillinen **Affecting Advances**
  -kolumni näyttää värillisin lyhentein Coinagen, Democracyn ja Monarchyn
  omistajat. Samat kortit luetellaan korttiryhmän väreillä oikean paneelin
  **Affecting Advances** -osiossa.
- **Conflict:** Affecting Advances -osio näyttää Advanced Military-,
  Agriculture-, Cultural Ascendancy-, Engineering-, Metalworking- ja
  Naval Warfare -kortit.
- **City Construction:** muistuttaa rakentamisrajoista, excess populationin
  tarkistuksesta ja city supportista. Affecting Advances -osio näyttää
  Urbanism-, Architecture-, Agriculture-, Cultural Ascendancy- ja
  Public Works -kortit.
- **Trade Cards Acquisition:** Affecting Advances -osio näyttää Rhetoric-,
  Cartography-, Mining- ja Wonder of the World -kortit.
- **Calamity Selection:** keskipaneeli näyttää kaikki Major Calamityt niiden
  ratkaisemisjärjestyksessä. Non-Tradeable- ja Tradeable-kortit erotetaan
  toisistaan eri taustaväreillä. Oikea paneeli näyttää pakkojen 2–9 kaikki
  Minor Calamityt ja niiden vaikutukset. Kaikkia Major Calamity -rivejä
  (Stackit 2–9) painamalla avautuvat niiden ratkaisuohjeet. Popupit
  näyttävät perusvaikutuksen, vaikuttavat Advancet ja niiden nykyiset
  omistajat sekä tarvittavat ratkaisemisen lisäsäännöt. Volcanic Eruption
  erottaa Volcanic Eruption- ja Earthquake-vaikutukset. Civil War näyttää
  lisäksi beneficiaryn valinnan ja yksiköiden valintaprioriteetit.
  12–18 pelaajan pelissä popupit huomioivat Non-Tradeable Calamityjen oman
  blockin valintasäännön ja Tradeable Calamityjen mahdollisuuden valita
  kummasta tahansa blockista.
- **Special Abilities:** oikea paneeli näyttää kaikki seitsemän Special
  Ability -korttia. Keskipaneeli näyttää vain niiden omistajat
  A.S.T.-Progress-järjestyksessä ja pelaajakohtaiset korttibadget.
- **Surplus Population & City Support:** keskipaneeli näyttää muistutuksena
  vain Agriculture-, Cultural Ascendancy- tai Public Works -kortin omistavat
  sivilisaatiot A.S.T.-järjestyksessä sekä heidän korttibadgensa.
- **Civilization Advances Acquisition:** Affecting Advances -osio näyttää
  Mining-, Roadbuilding- ja Trade Empire -kortit. Erillinen **Upon Purchase**
  -osio muistuttaa Anatomy-, Library-, Monument- ja Written Record -korttien
  kertaluonteisista ostohetken vaikutuksista.
- **A.S.T.-Alteration:** Wonder of the World näytetään vaikuttavana korttina,
  koska se lasketaan tämän vaiheen aikana kaupungiksi.
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

Ohjelma tallentaa jokaisen muutoksen automaattisesti käyttäjän nimeämään
JSON-tiedostoon:

```text
tallennukset/<pelin nimi>.json
```

Seuraavalla käynnistyskerralla peli voidaan valita kaikkien tallennusten
luettelosta. Uuden pelin aloittaminen ei korvaa muita tallennettuja pelejä.

## Testien ajaminen

```powershell
python -m unittest discover -v
```
