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

## Ensimmäinen käyttöönotto

> **Tämä vaihe on tehty.** Pipeline on pystyssä ja push-to-live on todettu
> toimivaksi oikealla koodimuutoksella. Ohjeet on säilytetty siltä varalta, että
> palvelin pitää joskus rakentaa uudelleen tyhjästä. Jatkuvaa päivitystä varten
> katso "Päivitys jatkossa".

Sovellushakemisto on jo olemassa ja sisältää käsin sijoitetun Phase A -skeletonin,
joka **ei ole gitissä**. Ensimmäinen käyttöönotto on siis muunnos, ei puhdas
asennus. Vanha hakemisto säilytetään varmuuskopiona kunnes uusi on todettu
toimivaksi.

### 0. Kehityskoneella: skeleton gittiin

Ilman tätä git-checkout tuottaa hakemiston, jossa ei ole `main.py`-tiedostoa ja
`ExecStart` epäonnistuu.

Palvelimella on kolme tiedostoa, jotka kuuluvat gittiin: `main.py`,
`requirements.txt` ja `sse-test.html`. `__pycache__` jää pois — se on jo
`.gitignore`ssa.

```bash
# SSH toimii vain Tailscalen kautta.
REMOTE=arttu@<tailscale-ip>:/home/megaempires/mega-empires-backend
scp "$REMOTE/main.py" "$REMOTE/requirements.txt" "$REMOTE/sse-test.html" .
```

Tarkista `requirements.txt`: jos se on käsin kirjoitettu ilman versioita, korvaa
se palvelimen todellisilla versioilla, koska Python 3.10 on se ympäristö jolla on
merkitystä:

```bash
ssh arttu@<tailscale-ip> \
    'sudo -u megaempires <venv>/bin/pip freeze' > requirements.txt
```

```bash
git add main.py requirements.txt sse-test.html
git commit -m "Lisää Phase A -skeleton ja riippuvuudet"
git push origin backend-sekoilu
```

`sse-test.html` tarvitaan mukaan, koska `main.py` palvelee sen `/sse-test`
-reitiltä suhteellisella polulla. Ilman sitä reitti hajoaa.

**Haara:** koko backend-työ tehdään `backend-sekoilu`-haarassa ja `master`
jätetään koskematta, kunnes ketju on todettu kokonaisuudessaan toimivaksi.
`deploy.sh` käyttää tätä haaraa oletuksena.

### 1. Palvelu alas ja vanha hakemisto talteen

Selvitä ensin, missä nykyinen venv on. Käytössä oleva unit tietää sen:

```bash
ssh arttu@<tailscale-ip>
systemctl cat mega-empires-backend.service | grep -E 'ExecStart|Environment'
ls -a /home/megaempires/mega-empires-backend
```

Jos venv on **sovellushakemiston sisällä** (esim. `.venv`), se katoaa kun hakemisto
siirretään — mikä on tässä hyväksyttävää, koska uusi venv luodaan joka tapauksessa
kohdassa 3. Varmista vain, että talteen otetut `Environment=`-rivit, erityisesti
bearer-token, ovat tiedossa ennen kuin unit korvataan.

```bash
sudo systemctl stop mega-empires-backend.service
sudo -u megaempires mv /home/megaempires/mega-empires-backend \
                       /home/megaempires/mega-empires-backend.bak
```

### 2. Deploy-avain GitHubiin

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

### 3. Kloonaus ja venv

Kloonaus ottaa suoraan oikean haaran. Ilman `--branch`-valitsinta työhakemistoon
jäisi `master`, jossa skeletonia ei ole, eikä palvelu käynnistyisi.

```bash
sudo -u megaempires git clone --branch backend-sekoilu \
    git@github.com:ArttKan/mega-empires-manager.git \
    /home/megaempires/mega-empires-backend
sudo -u megaempires python3 -m venv /home/megaempires/venv
sudo -u megaempires /home/megaempires/venv/bin/pip install --upgrade pip
sudo -u megaempires /home/megaempires/venv/bin/pip install -r \
    /home/megaempires/mega-empires-backend/requirements.txt
```

### 4. systemd ja sudo-sääntö

Tarkista, että `ExecStart` osoittaa oikeaan venviin. Unit ei sisällä
salaisuuksia, joten se voidaan kopioida sellaisenaan — token luetaan
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
sudo systemctl start mega-empires-backend.service
```

### 5. Tarkistukset

```bash
systemctl status mega-empires-backend.service
ls -ld /var/lib/mega-empires            # systemd loi, omistaja megaempires
curl -s http://127.0.0.1:8000/health    # paikallisesti
curl -s https://empiresmanager.com/health   # tunnelin läpi
```

Lopuksi puhelimella mobiilidatalla, wifi pois — se on oikea reitti.

### 6. Deploy-silmukan testaus

Todista silmukka nyt, kun mikään ei vielä riipu siitä. Tee kehityskoneella pieni
muutos, pushaa, ja aja palvelimella:

```bash
sudo -u megaempires /home/megaempires/mega-empires-backend/deploy/deploy.sh
```

Skriptin pitää hakea muutos, ajaa testit ja käynnistää palvelu uudelleen.

### 7. Varmuuskopion poisto

Vasta kun kaikki yllä toimii:

```bash
sudo -u megaempires rm -rf /home/megaempires/mega-empires-backend.bak
```

### Peruutus

Jos jokin menee pieleen, vanha tila palautuu suoraan:

```bash
sudo systemctl stop mega-empires-backend.service
sudo -u megaempires rm -rf /home/megaempires/mega-empires-backend
sudo -u megaempires mv /home/megaempires/mega-empires-backend.bak \
                       /home/megaempires/mega-empires-backend
sudo systemctl start mega-empires-backend.service
```

---

## Päivitys jatkossa

Kehityskoneelta ensin GitHubiin:

```bash
git push origin backend-sekoilu
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

Oletukset voi ohittaa ympäristömuuttujilla. Tätä tarvitaan vasta kun backend-työ
lopulta yhdistetään masteriin:

```bash
BRANCH=master sudo -u megaempires .../deploy.sh
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
jonka `/echo` vastaa hiljaa virheellisesti.

### Siirtymä skip-worktreestä — kertaluontoinen

Aiemmin unitin repoversio oli pelkkä malli: palvelimen kopioon oli kirjoitettu
oikea token, ja `git update-index --skip-worktree` esti sen näkymisen likaisena.
Sivuvaikutus oli ikävä — repon unit-muutokset eivät koskaan päätyneet
palvelimelle, ja deploy näytti onnistuvan vaikka palvelu jäi vanhaan unitiin.

Aja nämä kerran palvelimella. **Järjestys on olennainen:** token on luettava
talteen ennen kuin paikallinen muokkaus hylätään, ja env-tiedoston on oltava
olemassa ennen kuin uusi unit otetaan käyttöön.

```bash
# 1. Lue nykyinen token talteen ENNEN kuin mitään hylätään.
sudo systemctl cat mega-empires-backend.service | grep ECHO_TOKEN

# 2. Luo env-tiedosto repon ulkopuolelle.
sudo install -m 0600 -o root -g root /dev/null /etc/mega-empires-backend.env
printf 'ECHO_TOKEN=%s\n' '<vaiheessa 1 luettu token>' \
    | sudo tee /etc/mega-empires-backend.env >/dev/null

# 3. Vapauta tiedosto gitin normaaliin hallintaan ja hae uusi malli.
cd /home/megaempires/mega-empires-backend
sudo -u megaempires git update-index --no-skip-worktree \
    deploy/mega-empires-backend.service
sudo -u megaempires git checkout -- deploy/mega-empires-backend.service
sudo -u megaempires git pull

# 4. Ota uusi unit käyttöön.
sudo cp deploy/mega-empires-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart mega-empires-backend.service
```

Tarkista, että token todella välittyi — tämä on ainoa asia jota siirtymä voi
rikkoa hiljaisesti:

```bash
systemctl status mega-empires-backend.service
curl -s -X POST https://empiresmanager.com/echo \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message":"env-file test"}'
```

Vastauksen pitää olla `{"you_sent":"env-file test",...}`. HTTP 500 tarkoittaa,
ettei `ECHO_TOKEN` päätynyt prosessille; HTTP 401 tarkoittaa, että token on eri
kuin curlissa annettu.

Tämän jälkeen `git status` on palvelimella puhdas ilman skip-worktree-kikkaa, ja
repon unit-muutokset menevät perille tavallisella deployllä.

**Varmuuskopiot:** `/etc/mega-empires-backend.env` sisältää salaisuuden. Jos
palvelimelta otetaan varmuuskopioita, tämä tiedosto ei kuulu samaan paikkaan
pelitallennusten kanssa.

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
