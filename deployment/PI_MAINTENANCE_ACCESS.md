# Pi: omejeni vzdrzevalni dostop za Codex

## Activation checkpoint - 2026-10-14

Limited maintenance access v1 was installed from package v2 and independently
verified through a second SSH connection, including rejected command forms.
The original four commands and exactly three maintenance forms are now allowed
for the pinned migration; no general shell or sudo access is granted.
[Activation evidence](../docs/evidence/2026-10-14-maintenance-access.md)
records the backup, temporary connection failures and subsequent successful
Hub-readiness recovery. Original failed migration receipts remain historical.
Earlier pending-activation wording below describes the pre-installation stage.


Datum: 2026-10-14. **Omejeni dodatek je namescen in preverjen.** Po prvotni spremembi dokumentacije je lastnik odobril izvedbo.
Za konkretni paket, tri dodatne ukaze in prevzem glej
[vzdrzevalni dostop v1](maintenance-access/README.md). Ta dokument opisuje tudi
sirsi nacrt; dodatek v1 omogoca samo diagnostiko in tocno doloceno migracijo GPIO.

Cilj je, da Codex po enkratni vzpostavitvi dostopa sam opravlja dovoljeno
diagnostiko, varnostno kopiranje in odobrene namestitve. Operater ostane potreben
za fizicna opravila in obnovitev dostopa, kadar omrezna pot ne deluje.

Veljajo [osnovna pravila dostopa](WORKSTATION_CODEX_COMMISSIONING.md) in
[navodila za Codex](workstation-codex/CODEX_COMMISSIONING_PROMPT.md).

## 1. Kje se izvaja

| Naprava | Vloga | Nacin dostopa |
| --- | --- | --- |
| Raspberry Pi / DietPi, dokumentirani IP `192.168.114.192` | Hub, Node-RED, releji | Obstojeca zaupanja vredna skrbniska seja za pripravo in obnovitev |
| Windows delovna postaja | Codex, izvorna koda, SSH kljuc | Omejeni racun `freezeprotect-commission` za rutinske ukaze |
| Synology / Heimdall, `192.168.111.130` | Roon bridge | Tega postopka tam ne izvajamo |

Pred uporabo preveri identiteto; naslov IP sam ni dokaz naprave. Skrbniska seja
je clovekova namestitvena/obnovitvena pot, ne nov rutinski dostop za Codex.
Racun `freezeprotect` ostane neprijavljiva identiteta storitve. Codex tece na
delovni postaji.

## 2. Izvedljivo zdaj: preverjanje Pi-ja brez sprememb

Naslednji blok je za **obstojeco skrbnisko konzolo Pi-ja**. Prebere model,
storitve in identitete namestitvenih datotek. Ne zahteva skrivnosti in ne
spreminja SSH, storitev ali GPIO. Manjkajoca datoteka se izpise kot `MISSING`;
ne ustvarjaj je rocno samo zato, da bi preverjanje uspelo.

```sh
(
set -eu
model=$(tr -d '\000' < /proc/device-tree/model)
case "$model" in
  *"Raspberry Pi"*) printf 'MODEL=%s\n' "$model" ;;
  *) printf '%s\n' 'STOP: to ni Raspberry Pi'; exit 1 ;;
esac
uname -m
id freezeprotect-commission
sudo systemctl show freeze-protect.service node-red.service freeze-protect-pair-gpio.service \
  --property=Id --property=ActiveState --property=SubState \
  --property=FragmentPath --property=DropInPaths --property=NeedDaemonReload
for artifact in \
  /usr/local/sbin/freeze-protect-commission \
  /usr/local/lib/freeze-protect-commission/ssh-dispatch \
  /usr/local/lib/freeze-protect-commission/paired_gpio_client.py \
  /etc/sudoers.d/freeze-protect-commission \
  /etc/ssh/sshd_config.d/70-freezeprotect-commission.conf
do
  if sudo test -f "$artifact"; then
    sudo stat -c '%a %U:%G %n' "$artifact"
    sudo sha256sum "$artifact"
  else
    printf 'MISSING=%s\n' "$artifact"
  fi
done
sudo /usr/sbin/sshd -t
sudo /usr/sbin/visudo -c
printf '%s\n' 'READ_ONLY_CHECK_COMPLETE; this block changes no access'
)
```

Blok preveri skladnjo celotne konfiguracije, ne dokazuje vseh efektivnih SSH
pravic ali ustreznosti za novo namestitev. Izhod primerjaj z izbranim pregledanim
paketom. Celotnih okolij, zasebnih kljucev, dnevnikov ali poverilnic ne kopiraj
v chat. Pri napaki shrani konkretno oznako in obravnavaj vzrok.

## 3. Kaj mora biti pripravljeno pred aktivacijo

**Ta del je nacrt naslednje implementacije, ne blok ukazov za izvedbo.**
Prva omejena implementacija je v `deployment/maintenance-access`; njena
aktivacija je potrjena; sirse pravice niso dodane. Splosno namescanje poljubnih paketov ni implementirano.
Obstojeci `bootstrap-freezeprotect-access.sh` vzpostavi le prvotni stirikomandni
dostop; ponovni zagon tega skripta ne doda novih vzdrzevalnih moznosti.

Pripravljen in pregledan paket mora vsebovati:

- tocno razlicico, pricakovani SHA-256 iz zaupanja vrednega vira, manifest in
  preverjanje obstojece namestitve; prenos in razsirjanje sta del preverjenega
  namestitvenega postopka, ne izvajanje poljubne datoteke z omrezja;
- omejeni izvajalnik, SSH dispatcher in ustrezna pravila sudo, ki se ujemajo
  glede dovoljenih operacij, argumentov in poti;
- diagnostiko s fiksnimi viri in odstranjenimi skrivnostmi; namestitev samo
  konkretno odobrenega paketa ter ponovni zagon samo zahtevanih imenovanih storitev;
- zasebno varnostno kopijo, preverjanje obnovljivosti, kontrolne tocke in
  postopek obnove ob delni namestitvi ali izgubi povezave;
- teste dovoljenih in zavrnjenih ukazov, preverjanje fizicnih varoval ter
  jasna potrdila uspeha in napake brez skrivnosti.

Racun ne dobi splosne lupine, poljubnega sudo, dostopa do poljubnih datotek,
clanstva v skupinah GPIO ali preusmerjanja vrat. Izvajalne datoteke in nadrejene
poti ostanejo pod nadzorom root in niso zapisljive commissioning racunu.

## 4. Zaporedje prihodnje namestitve na Pi

Izvede se sele z zgoraj pripravljenim paketom in odobreno aktivacijo.

1. Preveri pravi Pi, zaupanje SSH kljucu in izhodno stanje storitev. Ohrani
   skrbnisko obnovitveno sejo odprto; ne menjaj kljucev ali zapiraj dostopa med
   preverjanjem druge seje.
2. Za spremembe, ki posegajo v storitve relejev, potrdi odklop 24 V ventilov in
   omreznega napajanja luci. Zabelezi `USER_OFF` / `DRAIN` in stanje luci OFF,
   ce je njen krmilnik ze namescen. Ne omogocaj luci samo zaradi preizkusa dostopa.
3. Namestitveni postopek ustvari zasebno kopijo dejanskih SSH/sudo pravil,
   dispatcherja, helperja, dovoljenj in metapodatkov. Zabelezi prisotne in
   manjkajoce poti; za servisni paket shrani tudi njegove nastavitve in podatke.
   Kopija mora biti celovita in preverjena pred prvo spremembo.
4. Preveri paket in osnovo namestitve. Namesti pregledane datoteke z dolocenim
   lastnistvom in dovoljenji. Ob prehodu ne sme nastati zacasna splosna pravica.
5. Preveri `sshd` in `sudoers` skladnjo ter efektivna pravila za konkretni racun
   in izvorni naslov. Ce je sprememba SSH konfiguracije potrebna, uporabi samo
   preverjeni postopek aktivacije; napaka ne sme zapreti obnovitvene seje.
6. Iz druge seje delovne postaje preveri dovoljene in zavrnjene zahteve ter
   ohranjeno omejitev na zasebno omrezje. Preizkus zavrnitve ne sme vsebovati
   potencialno nevarnega ukaza, ki bi ob napacni konfiguraciji vklopil rele.
7. Zabelezi razlicico, hashe, rezultat preverjanj, lokacijo kopije in dejansko
   omogocene operacije. Sele nato oznaci dostop kot aktiven in uskladi
   `AGENTS.md`, navodila ter evidenco projekta.

Ob neuspehu se postopek ustavi s potrdilom zadnje uspesne kontrolne tocke.
Preko ohranjene skrbniske seje se preveri dejansko stanje in izbere pregledani
obnovitveni korak. Ni samodejnega ponavljanja namestitve, slepe obnove ali
predpostavke, da izgubljena povezava pomeni uspesno namestitev.

## 5. Preverjanje trenutnega omejenega dostopa z Windows

Naslednji obstojeci ukaz je za **PowerShell na delovni postaji**. Uporablja
ze vzpostavljeno zaupanje gostitelju; ce manjka ali se je kljuc spremenil,
najprej uporabi preverjanje prstnega odtisa iz osnovnega vodica.

```powershell
ssh -i "$env:USERPROFILE\.ssh\freezeprotect_commission" -o BatchMode=yes freezeprotect-commission@192.168.114.192 sudo -n /usr/local/sbin/freeze-protect-commission inventory
```

Uspeh potrjuje samo ta trenutni ukaz. Dodatni vzdrzevalni ukazi so opisani v
README dodatka v1 in se uporabijo sele po potrjeni aktivaciji. Do takrat veljajo le `inventory`,
`status`, `diagnose-pair-gpio` in `drain`; zadnji zahteva DRAIN in ni zgolj branje.

## 6. Meja med vzdrzevanjem in fizicnim preizkusom

Vzdrzevalni dostop sam ne dovoljuje vklopa ventilov ali luci. Zagon storitve
mora ohraniti zahtevano varno stanje in ne sme nenamerno obnoviti AUTO ali
prejsnjega vklopa. Priklop bremen in preizkus relejev ostaneta locena odobrena
koraka. Izpis GPIO dokazuje le elektronski odcitek, ne polozaja ventilov ali
svetenja luci.
