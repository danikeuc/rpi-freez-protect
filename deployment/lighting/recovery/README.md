# Obnovitev luči in tuša v izklopljeno stanje — 2026-10-18

## Obseg in trenutno stanje

Paket je pripravljen za DietPi Raspberry Pi 4 Model B Rev 1.1 na
192.168.114.192. Ni paket za Synology, VM ali ESP zaslon.
Namenjen je točno obstoječi različici krmilnika luči po cooldown popravku.
Predhodna hash vrednost je zapisana v baseline.json; druga različica se zavrne.

Samostojna diagnostika prek omejenega SSH je potrjena. Oba krmilnika odgovarjata,
a sta v zaklenjeni napaki. Luč poroča clock_or_lease_fault, tuš
weather_fault_inhibited; v zgodovini tuša je pred tem relay_driver_error.
Izvor časovne spremembe in prvotne napake Node-RED še ni ugotovljen.
Ta paket je varna obnovitev in popravek poti ročnega izklopa, ne dokaz, da se
prvotna napaka ne more ponoviti. Ne spreminja nastavitev sistemske ure.

## Kaj naredi

1. Preveri točen model, različice, omejitev na weather_assisted, aktivne servise,
   potrjeno FAULT/OFF stanje luči in FAULT/DRAIN ali USER_OFF/DRAIN stanje tuša.
2. Preveri GPIO20, GPIO21 in GPIO26 kot output/high. Kratek 2-sekundni vzorec
   wall/monotonic časa mora biti stabilen; to ne dokazuje dolgoročne stabilnosti.
3. Zasede obstoječo vzdrževalno ključavnico in trajno označi en poskus.
4. Zasebno shrani zgodovino napake tuša, dosledni SQLite kopiji obeh baz,
   originalno kodo ter hashe konfiguracije. Poverilnice ostanejo na Pi-ju.
5. Ustavi samo light-controller.service. Iz shranjene baze preveri trajno FAULT
   stanje; če ga ni, se ustavi. Tako zagon ne sme takoj omogočiti kamere.
6. Atomsko zamenja samo controller.py, ohrani lastnika/dovoljenja, zažene luč.
7. Enkrat pošlje manual_off s svežo revizijo in enkrat CLEAR_FAULT za tuš,
   če je ta še v FAULT. Zahteva nove potrditve in ponovne GET preverbe.
8. Zahteva MANUAL_OFF/OK/OFF pri luči in USER_OFF/MANUAL_DRAIN/DRAIN pri tušu,
   output/high na vseh treh pinih ter nespremenjene nastavitve in okolje.

Ne spreminja GPIO lastništva, Node-RED tokov, nginx, SSH, firmware ali nastavitev
AUTO tuša. Nobena pot paketa ne pošlje ON, BEGIN, RENEW ali SUPPLY. DRAIN in OFF
sta ukaza izhodoma; nista fizična preskusa ventilov ali svetilke.

Luč ostane v ročnem izklopu za že nastavljeno trajanje (nazadnje 30 minut).
Po njegovem izteku se po obstoječem pravilu vrne v AUTO, zato jo lahko kasnejši
nov dogodek kamere vklopi. Tuš ostane v USER_OFF do ločenega namernega START.
Obstoječi dodatni 15-minutni premor po izteku ročnega VKLOPA luči ostane enak.

## Zagon

Z zaprtim drugim upravljanjem med posegom in obema napajanjema bremen odklopljenima
zaženi priloženi preverjeni blok v obstoječi skrbniški seji root@DietPi.
Po preverjenem prenosu in SHA256SUMS:

```sh
python3 -I -B recover_controllers.py --loads-disconnected
```

Uspeh je samo CONTROLLERS_RECOVERED_OFF in success.json v izpisani mapi.
Ob STOP se poskus ne ponavlja in markerja se ne briše. Ni samodejnega rollbacka;
servis luči lahko ostane ustavljen. Vzrok se preveri iz zasebne mape.
Ne objavljaj shower-events-private.json ali baz: vsebujejo zasebne podatke.
Izpis latest_relay_failure_categories je varen povzetek za nadaljnjo diagnostiko.

Paket se izvede na zaupanja vredni root konzoli, ker nameščeni omejeni SSH po
WORKSTATION_CODEX_COMMISSIONING.md dovoljuje status, ne te nove namestitve ali
odstranjevanja napak. Obstoječih maintenance prepare/install ne uporabljaj:
vezana sta na drug, točno določen GPIO migracijski paket.

## Stanja GPIO in meje dokazov

Par GPIO26/20 pripada izključno obstoječemu paired daemonu. Legalna para sta
00 (zahtevana oskrba) in 11 (zahtevan DRAIN); ta postopek zahteva samo 11.
Mešani stanji 01/10 nista dovoljeni. GPIO21 je neodvisen, aktivno nizek:
HIGH pomeni električni izhod OFF. Branje GPIO ne dokazuje položaja ventila,
stanja relejskih kontaktov ali dejanske svetlobe.

| Odpoved | Odziv/izvajalec | Čas in dokaz |
| --- | --- | --- |
| Izguba povezave krmilnik–izvajalec | Živi izvajalec ob izteku lease zahteva OFF/DRAIN; fault se ne izbriše sam | Luč 3 s lease, par 60 s lease, poleg odziva zanke/OS. Preverjeno v kodi/testih, fizični čas ni izmerjen. |
| Sesutje/zastoj procesa | Če obstane samo krmilnik, živi izvajalec izvede lease izklop. Če obstane izvajalec, ni neodvisne programske garancije izklopa | Možnost ohranjenega ON luči ob odpovedi izvajalca je lastnik že sprejel. Ne velja kot fizična garancija za ventile. |
| Ponovni zagon naprave/servisa | Zagon zahteva izhode OFF/DRAIN, trajni FAULT ostane zaklenjen. Obnovitev luči zahteva sveži OFF in preide v začasni MANUAL_OFF | Logika in testi preverjeni; celotna zagonska električna sled v tem posegu ni preizkušena. |
| Izguba in vrnitev napajanja | Dejanski kontakti/ventili so odvisni od vezave in napajanja; programski zagon zahteva OFF/DRAIN | Neodvisen strojni izklop in fizični odziv nista potrjena. Ne sklepamo iz spletnega statusa. |

## Preverjanje po izvedbi

Codex prebere obstoječi maintenance status prek omejenega SSH in preveri obe
poročili. Na Dialu mora biti prikazana potrjena povezava; luč MANUAL_OFF in tuš
USER_OFF/DRAIN. Fizično preverjanje in vklop bremen nista del tega postopka.
