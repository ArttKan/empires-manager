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

Sovellushakemisto on jo olemassa ja sisältää käsin sijoitetun Phase A -skeletonin,
joka **ei ole gitissä**. Ensimmäinen käyttöönotto on siis muunnos, ei puhdas
asennus. Vanha hakemisto säilytetään varmuuskopiona kunnes uusi on todettu
toimivaksi.

### 0. Kehityskoneella: skeleton gittiin

Ilman tätä git-checkout tuottaa hakemiston, jossa ei ole `server.py`-tiedostoa ja
`ExecStart` epäonnistuu.

```bash
# Hae skeleton ja sen riippuvuudet palvelimelta (SSH vain Tailscalen kautta).
scp arttu@<tailscale-ip>:/home/megaempires/mega-empires-backend/server.py .
ssh arttu@<tailscale-ip> \
    'sudo -u megaempires /home/megaempires/venv/bin/pip freeze' > requirements.txt
```

Karsi `requirements.txt` suoriin riippuvuuksiin (fastapi, uvicorn) tai jätä koko
freeze sellaisenaan. Versiot on poimittu palvelimen Python 3.10:stä, joka on se
ympäristö jolla on merkitystä.

```bash
git add server.py requirements.txt
git commit -m "Lisää Phase A -skeleton ja riippuvuudet"
git push origin backend-sekoilu
```

**Haara:** koko backend-työ tehdään `backend-sekoilu`-haarassa ja `master`
jätetään koskematta, kunnes ketju on todettu kokonaisuudessaan toimivaksi.
`deploy.sh` käyttää tätä haaraa oletuksena.

### 1. Palvelu alas ja vanha hakemisto talteen

```bash
ssh arttu@<tailscale-ip>
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
    git@github.com:rautiaik/Mega-Empires.git \
    /home/megaempires/mega-empires-backend
sudo -u megaempires python3 -m venv /home/megaempires/venv
sudo -u megaempires /home/megaempires/venv/bin/pip install --upgrade pip
sudo -u megaempires /home/megaempires/venv/bin/pip install -r \
    /home/megaempires/mega-empires-backend/requirements.txt
```

### 4. systemd ja sudo-sääntö

Sovita `mega-empires-backend.service` nykyiseen unitiin — älä korvaa sokkona.
Olennaiset lisäykset ovat `StateDirectory=mega-empires` ja
`Environment=MEGA_EMPIRES_DATA_DIR=…`. Tarkista myös, että `ExecStart` osoittaa
uuteen venviin ja että bearer-token siirtyy vanhasta unitista mukana.

```bash
cd /home/megaempires/mega-empires-backend
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
