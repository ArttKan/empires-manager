# Mega Empires -peliseuranta

## 1. Projektin tarkoitus

Toteutetaan paikalliseen käyttöön Python-ohjelma Mega Empires -lautapelin
suuren yhdistelmäpelin seurantaan. Käytössä ovat Mega Empires: The West ja
Mega Empires: The East. Ohjelma tukee pelaajamääriä 3–18. Pelaajamäärillä
3–4 pelaajalla käytetään käyttäjän valinnan mukaan The Westin tai The Eastin
erikoisskenaariota.
Tämän peliporukan tavallinen pelaajamäärä on 14–16.

Tietokone liitetään suureen televisioon. Kaikkien pelaajien pitää pystyä
näkemään yhdestä graafisesta näkymästä, kuka johtaa ja mistä pisteet
muodostuvat. Käyttöliittymä suunnitellaan enintään Full HD -resoluutiolle
(1920 × 1080). Kaikkien pelaajien yhteenveto pitää saada näkyviin samalla
ruudulla ilman vaaka- tai pystysuuntaista vieritystä normaalissa
pistenäkymässä.

Ohjelmaa ei ole tarkoitus julkaista tai jakaa. Se saa olla käytännöllinen
paikallinen apuväline eikä sen tarvitse puolustautua kaikkia teoreettisia
virhesyötteitä vastaan. Selkeä käyttö pelin aikana, tietojen säilyminen ja
väärän pelaajan tietojen muuttamisen välttäminen ovat tärkeämpiä kuin raskas
validointi tai yleiskäyttöinen arkkitehtuuri.

## 2. Lähdeaineisto ja rajaus

Suunnitelma perustuu hakemiston kolmeen englanninkieliseen ohjekirjaan:

- `MEEM001-MegaEmpires-TheWest-Rulebook-EN-downloaded-from-mega-empires-2025.pdf`
- `MEEM002-MegaEmpires-TheEast-Rulebook-EN-downloaded-from-mega-empires-2025.pdf`
- `MEEM002-MegaEmpires-TheEast-Rulebook-Scenarios-EN-downloaded-from-mega-empires-2025-1.pdf`
- `AST_1.jpg`, `AST_2.jpg` ja `AST_3.jpg`
- `MegaEmpires_AdvancementReference_v3.pdf`

West- ja East-perussääntöjen pelijärjestys ja pistelasku ovat keskenään
vastaavat. Skenaario-oppaan luku 5 kuvaa 10–18 pelaajan yhdistelmäpelin ja
sen poikkeukset. Ohjelma tehdään ensisijaisesti Basic Game -säännöille.
Pelaajamäärä valitaan pelin alussa, eikä näkymään luoda tyhjiä kilpailijoita.

3–4 pelaajan pelissä käyttäjä valitsee The West- tai The East
-erikoisskenaarion. 5–9 pelaajan pelissä käyttäjä valitsee joko The West- tai The East
-pelilaatikon. 10–18 pelaajan pelissä molemmat laatikot ovat pakollisia.
Ohjelma valitsee ohjekirjojen kartta-asettelujen mukaiset sivilisaatiot
automaattisesti pelaajamäärän ja pelilaatikon perusteella.

Yhdistelmäpelissä 12–18 pelaajan sivilisaatiot kuuluvat WEST- tai
EAST-kauppalohkoon. Lohko on tallennettava pelaajan/sivilisaation tietoihin,
koska se vaikuttaa AST-bonukseen ja myöhemmin mahdolliseen
Sequence of Play -avustukseen. Ohjelman ei tarvitse hallita kauppakorttipakkoja
eikä ratkaista calamityjen vaikutuksia.

AST-kuvista saadaan 18 pelaajan Basic AST:n sivilisaatiot, niiden kiinteä
AST-ranking, etenemisruudut, aikakaudet ja pisteasteikko. Advancement
Reference -tiedostossa on 51 Civilization Advancea. Siitä saadaan korttien
nimet, hinnat, 1/3/6 VP -arvot, väriryhmät, krediittisuhteet sekä eri
pelivaiheisiin ja calamityihin vaikuttavat ominaisuudet.

Basic A.S.T.:n aikakausirajat luetaan sivilisaatiokohtaisesti, koska rajat
eivät ole kaikilla riveillä samat. Ensimmäinen versio käyttää vain Basic
A.S.T.:ta. Pelitilaan varataan silti Basic/Expert-asetus, jotta Expert
A.S.T. voidaan lisätä myöhemmin omine rajoineen ja vaatimuksineen.

## 3. Tavoitteiden toteutusjärjestys

### Minimitavoite: pistetilanteen seuranta

Ensimmäinen käyttökelpoinen versio ylläpitää 5–18 pelaajan tilannetta,
laskee pisteet automaattisesti ja näyttää kaikki pelaajat yhdellä
1920 × 1080 -ruudulla. Seuraavat tiedot voidaan päivittää helposti vähintään
kierroksen lopussa ja tarvittaessa kesken kierroksen:

1. kaupunkien lukumäärä;
2. AST-radan nykyinen askel/sarake;
3. pelaajan hankkimat Civilization Advance -kortit;
4. pelaajan nimi, sivilisaatio ja WEST/EAST-lohko.

Ohjelman pitää tuntea molempien pelilaatikoiden Civilization Advance -kortit.
Kortti valitaan nimellä, jolloin ohjelma tietää sen hinnan ja pistearvon.
Kortin lisääminen ja tarvittaessa poistaminen pitää onnistua nopeasti ilman
vapaan tekstin pistekirjausta. Jos samannimisiä kortteja tai eri laitosten
kortteja täytyy erottaa, tunnisteessa säilytetään myös WEST/EAST-laitos.

Pistenäkymässä pelaajat lajitellaan ensisijaisesti tämänhetkisen
kokonaispistemäärän mukaan. Jokaisesta pelaajasta näytetään vähintään:

- sijoitus sekä tunniste muodossa `Sivilisaatio (etunimi tai lempinimi)`,
  esimerkiksi `Hellas (Matti)`;
- kokonaispisteet suurena;
- kaupunkien määrä ja niiden pisteet;
- AST-askel ja sen pisteet;
- Advance-korttien määrä ja niiden yhteispisteet;
- mahdollinen AST-bonus erillisenä tietona.

Tasapisteissä näkymän tulee olla vakaa ja mielellään käyttää sääntöjen
tasatilanteen ratkaisuperusteita siltä osin kuin tallennetut tiedot riittävät.
Jos kaikkia tasatilanteen tietoja ei vielä tallenneta, pelaajat voidaan näyttää
tasatilanteessa samalla sijoituksella ja AST-edistyminen seuraavana
lajitteluperusteena. Ohjelma ei saa väittää lopullista tasatilannetta
ratkaistuksi puutteellisilla tiedoilla.

### Lisätavoite: Sequence of Play -avustus

Kun pisteseuranta on toimiva ja testattu, ohjelmaan lisätään kierrosavustin.
Se näyttää nykyisen kierroksen ja vaiheen, lyhyen muistilistan, tarvittavan
pelaajajärjestyksen sekä Edellinen/Seuraava-tyyppiset ohjaimet. Vaiheen
vaihtaminen ei saa peittää kaikkien pelaajien pistetilannetta kokonaan;
avustin voidaan näyttää samassa näkymässä sivu- tai alapaneelina.

Lisätavoitteessa pelaajille tallennetaan myös Census eli pelilaudalla olevien
väestömerkkien määrä. Census ei sisällä kaupunkeja eikä laivoja. Census,
kaupunkimäärä ja AST-tilanne on voitava päivittää nopeasti oikeissa pelin
vaiheissa, minkä jälkeen ohjelma laskee seuraavissa vaiheissa tarvittavat
järjestykset automaattisesti.

## 4. Pisteytyssäännöt

Perussääntöjen kohdan 13c mukaan lopputulos muodostuu seuraavasti:

- 1 VP jokaisesta laudalla olevasta kaupungista;
- 1 VP jokaisesta alle 100 maksavasta Civilization Advancesta;
- 3 VP jokaisesta 100–200 maksavasta Civilization Advancesta;
- 6 VP jokaisesta yli 200 maksavasta Civilization Advancesta;
- 5 VP jokaisesta AST-radalla otetusta askeleesta;
- mahdollinen 5 VP:n AST-bonus.

Korttien painettu 1/3/6 VP vastaa yllä olevaa hintaluokkaa. Ohjelma laskee
korttipisteet korttiluettelosta eikä pyydä käyttäjää syöttämään niitä
erikseen.

12–18 pelaajan pelissä noudatetaan skenaario-oppaan 12–18 pelaajan
AST-bonussääntöä:

- jos vain yksi pelaaja siirtyy Late Iron Ageen, hän saa 5 VP;
- jos täsmälleen kaksi pelaajaa siirtyy sinne samalla kierroksella ja he ovat
  eri kauppalohkoissa, molemmat saavat 5 VP;
- jos siirtyjiä on enemmän kuin kaksi, bonusta ei anneta;
- kahdelle saman lohkon pelaajalle bonusta ei anneta.

Koska tämä bonus riippuu juuri pelin päättävästä siirtymisestä, ohjelman tulee
erottaa varmat pisteet ja ehdollinen AST-bonus. Bonus vahvistetaan
kierroksen AST-vaiheessa eikä sitä päätellä pysyvästi pelkästä nykyisestä
Late Iron Age -sijainnista.

Lopullisen tasatilanteen virallinen ratkaisujärjestys on:

1. pidemmälle edennyt AST-merkki (pelkkä AST-ranking ei vielä ratkaise);
2. ensin 6 VP:n Advance-korttien määrä, sitten 3 VP:n korttien määrä;
3. kaikkien Advance-korttien yhteenlaskettu hinta;
4. suurin yhdenväristen credit-merkkien yhteisarvo;
5. kaikkien credit-merkkien yhteisarvo;
6. kaupunkien määrä;
7. laudalla olevien väestömerkkien määrä;
8. AST-ranking.

Minimiversioon ei tarvitse lisätä credit-merkkien seurantaa. Lopullinen
tasatilanne voidaan siksi merkitä ratkaisemattomaksi, jos ratkaisu etenisi
kohtiin 4 tai 5. Advance-korttien hinnat kannattaa tallentaa heti, jotta
kohdat 2 ja 3 voidaan laskea automaattisesti.

## 5. Syöttämisen työnkulku

Pelin alussa luodaan uusi peli:

- ohjelma kysyy ensin käytettävät pelilaatikot ja pelaajamäärän 5–18;
- 5–9 pelaajalla sallitaan vain West tai East ja 10–18 pelaajalla
  valitaan automaattisesti West + East;
- ohjelma valitsee viralliseen kartta-asetteluun kuuluvat sivilisaatiot
  automaattisesti;
- tämän jälkeen ohjelma kysyy vuorotellen jokaisen mukana olevan
  sivilisaation pelaajan etunimen tai lempinimen;
- asetetaan skenaarion mukainen WEST/EAST-lohko;
- AST-ranking eli sivilisaatioiden pystysuuntainen järjestys haetaan
  ensisijaisesti sivilisaatioluettelosta automaattisesti;
- asetetaan alkutilanteet tai hyväksytään oletusarvot.

Sivilisaatiot haetaan pelaajamääräkohtaisesta valmiista
skenaarioluettelosta. Tarvittaessa mukana pitää kuitenkin olla mahdollisuus
korjata WEST/EAST-lohko ja muut sivilisaation perustiedot käsin, jos
peliporukka käyttää ohjekirjan vaihtoehtoista kartta-asettelua.

Pelaajan etunimi tai lempinimi on lyhyt vapaatekstikenttä. Yhteenveto- ja
AST-näkymissä sivilisaatio on ensisijainen nimi ja pelaajan nimi näytetään
aina sen perässä suluissa. Tätä esitystapaa käytetään johdonmukaisesti myös
automaattisissa pelaajajärjestyksissä.

Pelin aikana pääkäyttäjä valitsee pelaajan näkyvästä pistetaulukosta ja
muuttaa vain tarvittavat tiedot:

- kaupungeille selkeä vähennys-/lisäyspainike tai suora pieni numerokenttä;
- AST:lle edellinen/seuraava askel tai selkeä sarakevalinta;
- Advance-korteille haettava tai ryhmitelty valintalista, jossa jo ostetut
  kortit näkyvät valittuina;
- lisätavoitteessa Census-arvolle suoraan kirjoitettava numerokenttä
  Scoreboard-näkymässä.

Muutoksen jälkeen pisteet, sijoitukset ja järjestyslistat päivittyvät heti.
Valittu pelaaja ja muutettu arvo korostetaan hetkeksi, jotta TV:tä katsovat
pelaajat pystyvät tarkistamaan kirjauksen. Vaarallisin tavallinen virhe on
tiedon syöttäminen väärälle pelaajalle, joten pelaajan nimi, väri ja
sivilisaatio pidetään muokkaustilassa erityisen näkyvinä.

Tilanne tallennetaan automaattisesti käyttäjän nimeämään paikalliseen
tiedostoon jokaisen muutoksen jälkeen. Käynnistyksessä käyttäjä valitsee
jatkettavan tallennuksen tai aloittaa uuden pelin. Yksi askel taaksepäin / viimeisimmän muutoksen
kumoaminen on hyödyllinen, jos se voidaan toteuttaa pienellä vaivalla.

## 6. Sequence of Play ja pelaajajärjestykset

Kierrosavustimen vaiheet ovat perussääntöjen mukaisesti:

1. Tax Collection
2. Population Expansion
3. Movement
4. Conflict
5. City Construction
6. Trade Cards Acquisition
7. Trade
8. Calamity Selection
9. Calamity Resolution
10. Special Abilities
11. Surplus Population & City Support
12. Civilization Advances Acquisition
13. AST-Alteration

10–18 pelaajan yhdistelmäpelissä vaiheet 1–5 toimivat kuten tavallisessa
5–9 pelaajan pelissä. Kaikki sivilisaatiot voivat oletuksena toimia
samanaikaisesti, mutta fyysisen tilan vuoksi avustin näyttää myös sääntöjen
mukaisen järjestyksen silloin, kun pelaajat haluavat vuorotella.

Automaattisten järjestysten perusteet:

- **AST-ranking:** AST-taululle painettu sivilisaatioiden pystysuuntainen
  järjestys ylhäältä alas. Tämä on usein viimeinen tasatilanteen ratkaisija.
- **AST-progress:** AST-radalla pisimmällä oleva ensin; tasatilanteessa
  AST-ranking.
- **Census-järjestys:** suurin laudalla oleva väestömäärä ensin;
  tasatilanteessa AST-ranking.
- **City count -järjestys:** vähiten kaupunkeja ensin; tasatilanteessa
  AST-ranking.

Vaihekohtainen pääjärjestys:

| Vaihe | Oletustapa / järjestys |
|---|---|
| 1 Tax Collection | samanaikainen |
| 2 Population Expansion ja Census | samanaikainen; tarvittaessa AST-ranking |
| 3 Movement | Census laskevasti, AST-ranking ratkaisee tasan; Militaryn omistajat kaikkien muiden jälkeen ja keskenään jälleen Census-järjestyksessä |
| 4 Conflict | token-konfliktit ennen kaupunki-iskuja; useimmiten samanaikainen, tarvittaessa AST-ranking |
| 5 City Construction | samanaikainen; päivitä tämän jälkeen kaupunkimäärät |
| 6 Trade Cards Acquisition | kaupunkeja vähiten omaava ensin, AST-ranking ratkaisee tasan; WEST/EAST-pakat erillään |
| 7 Trade | samanaikainen ja ajastettu |
| 8 Calamity Selection | samanaikainen |
| 9 Calamity Resolution | sääntöjen calamity-järjestys; saman calamityn erityistilanteissa AST-ranking |
| 10 Special Abilities | vain seitsemän Special Ability -kortin omistajat AST-progress-järjestyksessä, pisimmällä oleva ensin; tasan AST-ranking |
| 11 Surplus Population & City Support | samanaikainen; päivitä kaupunkimäärät tarvittaessa |
| 12 Civilization Advances Acquisition | samanaikainen; vaadittaessa AST-progress; päivitä ostetut kortit |
| 13 AST-Alteration | AST-ranking; päivitä AST-askeleet ja vahvista mahdollinen loppu/bonus |

Vaiheen muistilista ei korvaa ohjekirjaa. Sen tulee näyttää vain tiivis
pelipöytämuistutus ja tarvittaessa ohjekirjan nimi sekä sivu, josta poikkeus
voidaan tarkistaa.

## 7. Tietomalli

Vähimmäistiedot:

### Peli

- pelaajamäärä;
- kierrosnumero;
- nykyinen vaihe (lisätavoite);
- Basic/Expert-asetus, vaikka ensimmäinen versio tukee Basic-peliä;
- tallennusaika;
- AST-bonuksen tila ja pelaajat, joille bonus on vahvistettu.

### Pelaaja

- nimi;
- sivilisaatio ja näyttöväri;
- WEST/EAST-lohko;
- kiinteä AST-ranking;
- kaupunkien määrä;
- AST-askel/sarake;
- ostettujen Civilization Advance -korttien tunnisteet;
- Written Recordin ja Monumentin vapaasti jaettujen krediittien värijako;
- Census (lisätavoite);
- laskennalliset piste-erittelyt.

### Civilization Advance

- yksilöllinen tunniste;
- nimi;
- laitos (WEST/EAST);
- hinta;
- VP-arvo (1, 3 tai 6);
- ryhmä tai ryhmät, jos niitä käytetään valintalistan suodattamiseen.
- krediittisuhteet muihin Advance-kortteihin;
- kortin antamat pysyvät värikrediitit sekä referenssitaulukon
  1 VP → 3 VP → 6 VP -rivialennusketju;
- ominaisuusteksti sekä pelivaihe- ja calamity-tunnisteet myöhempää
  Sequence of Play -avustusta varten.

Tieto tallennetaan yksinkertaisessa paikallisessa muodossa, esimerkiksi
JSON-tiedostoon. Erillistä tietokantapalvelinta ei tarvita.

### AST:n perustiedot

Basic AST:n kiinteä ranking on kuvien perusteella:

1. Minoa
2. Saba
3. Assyria
4. Maurya
5. Celt
6. Babylon
7. Carthage
8. Dravidia
9. Hatti
10. Kushan
11. Rome
12. Persia
13. Iberia
14. Nubia
15. Hellas
16. Indus
17. Egypt
18. Parthia

AST:n etenemisruutujen pisteet ovat 5, 10, 15, 20, 25, 30, 35, 40, 45,
50, 55, 60, 65, 70 ja 75 VP. Ohjelman sisäinen arvo voidaan tallentaa
askelnumerona 0–15, jossa lähtöruutu on 0 VP ja jokainen edetty askel lisää
5 VP.

Basic AST:n aikakausivaatimukset:

- SA: ei vaatimuksia;
- EBA: vähintään 2 kaupunkia;
- MBA: vähintään 3 kaupunkia ja 3 Civilization Advancea;
- LBA: vähintään 3 kaupunkia ja 3 Advancea, joiden hinta on vähintään 100;
- EIA: vähintään 4 kaupunkia ja 2 Advancea, joiden hinta on vähintään 200;
- LIA: vähintään 5 kaupunkia ja 3 Advancea, joiden hinta on vähintään 200.

Basic-pelissä vaatimusten menettäminen estää etenemisen mutta ei itsessään
siirrä markkeria taaksepäin. Käyttöliittymä erottaa seuraavan aikakauden
vaatimusten täyttymisen, täyttymättömyyden ja nykyisen aikakauden vaatimusten
menettämisen eri symboleilla.

## 8. Käyttöliittymän periaatteet

- Suunnitteluresoluutio on 1920 × 1080; käyttöliittymä ei saa vaatia 4K:ta.
- Pistenäkymä käyttää koko ruudun tehokkaasti ja näyttää 18 pelaajaa yhtä
  aikaa esimerkiksi kahtena yhdeksän pelaajan sarakkeena tai tiiviinä
  korttiruudukkona.
- Pisteet, sijoitus ja pelaajan tunniste ovat luettavissa television
  katseluetäisyydeltä.
- Väri ei ole ainoa tunniste: nimi, sivilisaatio ja sijoitus ovat aina
  tekstinä.
- Pelaajan näkyvä tunniste on kaikkialla ensisijaisesti
  `Sivilisaatio (etunimi tai lempinimi)`.
- Johtaja ja tasatilanteet erotetaan selvästi, mutta muiden pelaajien
  piste-erittelyä ei piiloteta.
- AST-näkymässä näytetään ainoastaan nykyiseen peliin valitut sivilisaatiot.
  Pois jääneille sivilisaatioille ei varata tyhjiä rivejä. Mukana olevat
  sivilisaatiot säilyttävät silti pelikomponenttiin painetun keskinäisen
  AST-ranking-järjestyksensä.
- AST-näkymän pitää näyttää kunkin mukana olevan sivilisaation nykyinen askel,
  sivilisaatiokohtaiset aikakausirajat, seuraavan aikakauden vaatimukset ja
  AST:stä kertyvät pisteet. Näkymän ei tarvitse olla pelilaudan valokuvan
  kopio, vaan se voidaan piirtää television katseluetäisyydelle sopivaksi.
- Muokkausnäkymä saa käyttää peittävää paneelia, kunhan palaaminen
  yhteisnäkymään on välitöntä.
- Graafisen käyttöliittymän kaikki käyttäjälle näkyvät tekstit ovat
  englanniksi, jotta termit vastaavat sääntökirjoja, pelaajareferenssejä ja
  pelikomponentteja. Hakemiston keskustelut ja dokumentaatio ovat suomeksi.

## 9. Ei kuulu ensimmäiseen versioon

- kauppakorttien käsien tai kauppojen seuranta;
- calamityjen automaattinen ratkaiseminen;
- erillinen Calamity Resolution -avustin omalla välilehdellään; tämä jätetään
  myöhempään jatkokehitykseen, koska vaiheeseen vaikuttavia kortteja ja
  calamitykohtaisia poikkeuksia on paljon;
- kartan, väestömerkkien alueiden tai laivojen seuranta;
- verkkomoninpeli tai usean laitteen synkronointi;
- käyttäjätilit, käyttöoikeudet tai pilvitallennus;
- täydellinen suojaus vioittuneita tai käsin muokattuja tallennustiedostoja
  vastaan;
- alle 5 tai yli 18 pelaajan pelit.

## 10. Hyväksymiskriteerit

Minimitavoite on valmis, kun:

1. uusi 5–18 pelaajan peli voidaan perustaa;
2. ohjelma kysyy pelilaatikot ja pelaajamäärän, pakottaa yhdistelmäpelin
   10–18 pelaajalla ja valitsee oikeat sivilisaatiot automaattisesti;
3. ohjelma kysyy jokaiselle valitulle sivilisaatiolle pelaajan etunimen tai
   lempinimen;
4. AST-näkymässä näkyvät vain peliin valitut sivilisaatiot oikeassa
   keskinäisessä AST-ranking-järjestyksessä;
5. kaikkien pelaajien nimet, sivilisaatiot, kaupunkimäärät, AST-askeleet,
   Advance-kortit ja piste-erittely näkyvät yhdellä 1920 × 1080 -ruudulla;
6. kaupunki-, AST- ja korttitietoja voidaan muuttaa nopeasti;
7. pisteet ja sijoitukset päivittyvät sääntöjen mukaan välittömästi;
8. yhdistelmäpelin ehdollinen AST-bonus käsitellään oikein;
9. tallennettu peli palautuu ohjelman uudelleenkäynnistyksen jälkeen;
10. muutokset on kokeiltu 5-, 9-, 10- ja 18-pelaajan esimerkkitilanteilla.

Lisätavoite on valmis, kun:

1. kaikki 13 vaihetta voidaan käydä järjestyksessä läpi;
2. Census voidaan kirjoittaa suoraan Scoreboard-näkymässä ja Census-järjestys
   lasketaan oikein;
3. City count-, AST-progress- ja AST-ranking-järjestykset muodostuvat
   tallennetuista tiedoista;
4. ohjelma näyttää kullekin vaiheelle oikean toimintatavan tai
   pelaajajärjestyksen;
5. kierroksen vaihto säilyttää piste- ja pelaajatiedot sekä palauttaa
   avustimen ensimmäiseen vaiheeseen.

## 11. Sääntöviitteet

- West Basic Rulebook: Sequence of Play s. 16–25, pistelasku ja
  tasatilanteet s. 25, yhteenvetotaulukko viimeisellä sivulla.
- East Basic Rulebook: vastaavat Sequence of Play -säännöt s. 16–25 ja
  yhteenvetotaulukko viimeisellä sivulla.
- Scenarios Rulebook: West & East 10–18 players s. 16–25, erityisesti
  yhdistelmäpelin Sequence of Play s. 23 ja AST-bonus s. 25.
