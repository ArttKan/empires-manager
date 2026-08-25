# Palvelinasennus ja päivitys

Ohjeet `olohuone-ubuntu`-koneelle (Ubuntu 22.04, Python 3.10). Kirjoitettu Phase A
-vaiheen jälkeen, kun tunneli, TLS ja systemd on jo todettu toimiviksi.

Hakemistojako asennuksen jälkeen:

| Polku | Sisältö | Omistaja |
|---|---|---|
| `/home/megaempires/mega-empires-backend/` | git-työhakemisto | `megaempires` |
| `/home/megaempires/venv/` | virtualenv, checkoutin ulkopuolella | `megaempires` |
| `/var/lib/mega-empires/` | pelitallennukset, systemd luo | `megaempires` |

Venv on tarkoituksella checkoutin ulkopuolella, jotta git-operaatiot eivät voi
osua siihen. Tallennukset ovat `/var/lib`-hakemistossa samasta syystä: git-päivitys
korvaa työhakemiston sisällön eikä saa hävittää pelejä.

---

## Asennus tyhjälle koneelle

Nykyinen palvelin on jo pystyssä; nämä ohjeet ovat sen varalle että se pitää
rakentaa uudelleen. Vaiheen A skeleton ja siihen liittynyt käsin kopiointi on
poistettu — koko sovellus tulee nyt gitistä.

### 1. Deploy-avain GitHubiin

Repo on yksityinen, joten palvelin tarvitsee oman lukuoikeudellisen avaimen.

```bash
sudo -u megaempires ssh-keygen -t ed25519 -C "olohuone-ubuntu deploy" \
    -f /home/megaempires/.ssh/id_ed25519 -N ""
sudo -u megaempires cat /home/megaempires/.ssh/id_ed25519.pub
```

Lisää julkinen avain GitHubissa: repo → Settings → Deploy keys → Add deploy key.
**Älä** rastita "Allow write access". Testaa:

```bash
sudo -u megaempires ssh -T git@github.com
```

### 2. Kloonaus ja venv

```bash
sudo -u megaempires git clone \
    git@github.com:ArttKan/mega-empires-manager.git \
    /home/megaempires/mega-empires-backend
sudo -u megaempires python3 -m venv /home/megaempires/venv
sudo -u megaempires /home/megaempires/venv/bin/pip install --upgrade pip
sudo -u megaempires /home/megaempires/venv/bin/pip install -r \
    /home/megaempires/mega-empires-backend/requirements.txt
```

### 3. Token, systemd ja sudo-sääntö

Unit ei sisällä salaisuuksia, joten se kopioidaan sellaisenaan. Token luetaan
`/etc/mega-empires-backend.env`-tiedostosta, joka on luotava **ennen**
käynnistystä tai palvelu ei käynnisty lainkaan.

```bash
cd /home/megaempires/mega-empires-backend
sudo install -m 0600 -o root -g root /dev/null /etc/mega-empires-backend.env
printf 'ECHO_TOKEN=%s\n' '<token>' | sudo tee /etc/mega-empires-backend.env >/dev/null
sudo cp deploy/mega-empires-backend.service /etc/systemd/system/
sudo install -m 0440 -o root -g root \
    deploy/megaempires-deploy.sudoers /etc/sudoers.d/megaempires-deploy
sudo visudo -c
sudo systemctl daemon-reload
sudo systemctl enable --now mega-empires-backend.service
```

Muuttujan nimi on historiallinen (`ECHO_TOKEN`, Phase A:n ajoilta). `main.py`
lukee myös `MEGA_EMPIRES_TOKEN`-nimen, jos se halutaan joskus vaihtaa.

### 4. Tarkistukset

```bash
systemctl status mega-empires-backend.service
ls -ld /var/lib/mega-empires            # systemd loi, omistaja megaempires
curl -s http://127.0.0.1:8000/health    # paikallisesti
curl -s https://empiresmanager.com/health   # tunnelin läpi
```

Lopuksi puhelimella mobiilidatalla, wifi pois — se on oikea reitti. Peli
luodaan työpöytäsovelluksen velholla etätilassa; palvelimelle ei tarvitse
kopioida tallennuksia käsin.

## Päivitys jatkossa

Kehityskoneelta ensin GitHubiin:

```bash
git push origin main
```

Sitten palvelimella:

```bash
ssh arttu@<tailscale-ip>
sudo -u megaempires /home/megaempires/mega-empires-backend/deploy/deploy.sh
```

Skripti hakee muutokset, asentaa riippuvuudet vain jos `requirements.txt` on
muuttunut, ajaa testit ja käynnistää palvelun uudelleen vain jos testit menivät
läpi. `tests/test_ui.py` ohittaa itsensä automaattisesti, koska palvelimella ei
ole `python3-tk`-pakettia.

Oletukset voi ohittaa ympäristömuuttujilla, esimerkiksi kokeiluhaaraa varten:

```bash
BRANCH=jokin-haara sudo -u megaempires .../deploy.sh
```

## systemd-unit ja salaisuudet

Unit ei sisällä salaisuuksia, joten `deploy/mega-empires-backend.service` on
tavallinen gitin seuraama tiedosto: repon versio on ainoa versio, ja se päivittyy
palvelimelle normaalisti. Token luetaan repon ulkopuolisesta tiedostosta:

```ini
EnvironmentFile=/etc/mega-empires-backend.env
```

Tiedosto on `root:root 0600`. systemd lukee sen ennen kuin se vaihtaa prosessin
`megaempires`-käyttäjäksi, joten sovelluskäyttäjän ei tarvitse päästä siihen
käsiksi lainkaan.

`EnvironmentFile` on tahallisesti pakollinen (ei `-`-etuliitettä): jos tiedosto
puuttuu, palvelu ei käynnisty ollenkaan. Se on parempi kuin käynnistyvä palvelu,
joka hylkää kaikki tunnistautuneet pyynnöt.

Aiemmin unitin repoversio oli pelkkä malli ja palvelimen kopioon kirjoitettiin
token käsin, `git update-index --skip-worktree` piilottamana. Siitä luovuttiin:
se esti unit-muutosten päätymisen palvelimelle hiljaisesti. **Älä palauta
salaisuutta unitiin.**

Tokenin vaihtaminen käy nyt suoraan:

```bash
sudo printf 'ECHO_TOKEN=%s\n' '<uusi token>' | sudo tee /etc/mega-empires-backend.env >/dev/null
sudo systemctl restart mega-empires-backend.service
curl -s -o /dev/null -w '%{http_code}\n' https://empiresmanager.com/state \
  -H "Authorization: Bearer <uusi token>"
```

200 tarkoittaa että token välittyi, 401 että se on eri kuin curlissa annettu.

## Tokenin vaihtaminen

Unit ei sisällä salaisuuksia, joten token vaihdetaan pelkästään env-tiedostosta.
Aiemmin token kirjoitettiin unitiin käsin ja piilotettiin
`git update-index --skip-worktree`lla; siitä luovuttiin, koska se esti
unit-muutosten päätymisen palvelimelle hiljaisesti. **Älä palauta salaisuutta
unitiin.**

```bash
printf 'ECHO_TOKEN=%s\n' '<uusi token>' | sudo tee /etc/mega-empires-backend.env >/dev/null
sudo systemctl restart mega-empires-backend.service
curl -s -o /dev/null -w '%{http_code}\n' https://empiresmanager.com/state \
  -H "Authorization: Bearer <uusi token>"
```

200 tarkoittaa että token välittyi, 401 että se on eri kuin curlissa annettu.
Muista päivittää myös kannettavan `~/.config/mega-empires/config.json`.

## Reittien tarkistus deployn jälkeen

`/health` ei vaadi tokenia ja kertoo myös onko peli ladattu:

```bash
curl -s https://empiresmanager.com/health
```

Loput vaativat tokenin:

```bash
TOKEN=<oikea token>
curl -s https://empiresmanager.com/state -H "Authorization: Bearer $TOKEN"
```

**HTTP 503 tarkoittaa, ettei palvelimella ole peliä** hakemistossa
`/var/lib/mega-empires/nykyinen_peli.json`. Se ei ole vika: peliä ei vielä voi
luoda HTTP:n yli, se tulee `RemoteGameService`-vaiheessa. Testipelin saa paikalleen
kehityskoneelta:

```bash
scp tallennukset/testipeli.json \
    megaempires@100.107.240.83:/var/lib/mega-empires/nykyinen_peli.json
sudo systemctl restart mega-empires-backend.service
```

Uudelleenkäynnistys on tarpeen, koska palvelu lukee tallennuksen kerran ja pitää
sen muistissa.

Komennon läpimeno päästä päähän:

```bash
curl -s -X POST https://empiresmanager.com/players/Minoa/cities \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"value": 4}'
```

Vastauksessa palautuu uusi `state_version` ja pelaajan tila. Odotetut virhekoodit:
401 väärä token, 404 tuntematon sivilisaatio, 409 vanhentunut `expected_version`
(vastaus kertoo nykyisen), 422 sääntörikkomus.

SSE-virta ei vaadi tokenia, koska se ei kuljeta pelidataa — vain versionumeron:

```bash
curl -N https://empiresmanager.com/events
```

## Miksi restart jumitti

`systemctl restart` jäi useimmiten roikkumaan. Syy ei ollut systemd vaan `/events`:
se on ääretön vastaus, ja uvicorn odottaa kesken olevien vastausten valmistumista
ennen kuin se poistuu. Yksikin auki oleva puhelin tai `curl -N`
piti prosessin hengissä, kunnes systemd tappoi sen `TimeoutStopSec`in (oletus 90 s)
kuluttua. "Ei joka kerta mutta useimmiten" selittyy tällä: se riippui siitä oliko
virtoja auki.

**Sovelluksesta tätä ei voi korjata.** uvicorn ajaa lifespan-sammutuksen vasta
pyyntöjen valuttamisen jälkeen, joten käsittelijä joka sulkisi virrat odottaa itse
niiden sulkeutumista. Kokeiltu ja mitattu: prosessi ei poistunut 40 sekunnissakaan.

Ratkaisu on unitissa:

```ini
ExecStart=… --timeout-graceful-shutdown 5
TimeoutStopSec=20
```

Mitattuna poistuminen kestää tällöin ~5 s myös kolmella avoimella virralla.
`TimeoutStopSec` on varmistus siltä varalta että prosessi ei silti poistu.

**Tämä muutos on unitissa, joten se vaatii unitin kopioinnin palvelimelle** —
pelkkä `deploy.sh` ei riitä:

```bash
cd /home/megaempires/mega-empires-backend
sudo cp deploy/mega-empires-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart mega-empires-backend.service
```

## Vianetsintä

```bash
journalctl -u mega-empires-backend.service -n 50 --no-pager
systemctl cat mega-empires-backend.service
curl -s http://127.0.0.1:8000/health
```

Jos git valittaa hakemiston omistajuudesta, komento ajetaan väärällä käyttäjällä —
tarkista `sudo -u megaempires`.

Tallennukset varmuuskopioidaan hakemistosta `/var/lib/mega-empires/`. Ne ovat
kilotavuja, joten öinen rsync riittää.
