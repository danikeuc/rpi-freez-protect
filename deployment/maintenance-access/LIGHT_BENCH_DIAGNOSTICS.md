# Navodila: oddaljena diagnostika preizkusa GPIO21

Datum: 2026-10-15
Status: NAMEŠČENO; druga omejena SSH povezava in zavrnitev dodatnih argumentov preverjeni. Diagnostiko lahko Codex bere sam. Spodnji koraki so zapis že opravljenega postopka.

## Kaj želimo doseči

Codex naj sam prebere rezultat preizkusa tretjega releja prek obstoječega ukaza:

```text
sudo -n /usr/local/sbin/freeze-protect-maintenance status
```

Dopolnimo njegov izpis s poljem `light_gpio21_bench`. Ime ukaza ostane enako.
Ne dodajamo splošne lupine, poljubnega branja datotek, sudo dovoljenj ali možnosti
oddaljenega zagona relejnega preizkusa. Obstoječi `prepare` in `install` ostaneta
vezana izključno na prejšnji paket migracije; za to dopolnitev ju ne uporabljamo.

## Trenutno preverjeno stanje

Uporabnik je vrnil rezultat preizkusa:

- `result=LIGHT_LEVEL_MISMATCH`
- `attempted_gpio21=true`
- `final_off_readback=true`
- `physical_acceptance=NOT_VERIFIED`
- `automation_enabled=false`
- dokazi: `/root/light-gpio21-bench.ehy6qh3b`

Končna obnovitev OFF je uspela. Prva napaka je v fazi crash_release: GPIO21 je ob prvi meritvi po prekinitvi procesa še output/LOW. GPIO20/26 sta v vseh shranjenih meritvah output/HIGH.
Ne brišemo označevalnika `/root/light-gpio21-commissioning.started`, ne ponavljamo
preizkusa in ne vključujemo povezave kamera–rele pred razlago rezultata.
GPIO odčitek ne potrjuje fizičnega položaja releja ali ventilov.

## 1. Kaj pripravi Codex

1. Dopolni `deployment/maintenance-access/maintenance.py`, da `status` prebere
   samo dokazila preizkusa, na katerega kaže obstoječi root označevalnik.
2. Preveri pot, lastništvo, pravice, omejitve velikosti in vsebino. Ne sledi
   simbolnim povezavam; napačna ali manjkajoča dokazila vrnejo omejeno oznako
   napake v novem polju, ostali status pa ostane uporaben.
3. Vrne rezultat, potrjenost končnega OFF, prvo neskladno meritev in kratek
   povzetek po fazah. Ne vrne surovih dnevnikov, okolja, poverilnic ali poljubnih
   besedil iz datotek. Odčitki so zgodovinski, ne trenutno stanje GPIO.
4. Doda teste za veljavna, manjkajoča, poškodovana in nedovoljena dokazila.
5. Pripravi ločen pregledan namestitveni paket z manifestom in SHA256. Paket
   vsebuje samo dopolnitev diagnostike, namestitveni program in navodila.
6. Pred namestitvijo določi pričakovani SHA256 dejansko nameščenega pomočnika.
   Stari hash iz prejšnjega namestitvenega programa ni dokaz trenutne različice.

## 2. Kaj enkrat izvedeš ti

Ko je paket pripravljen, Codex poda en dokončen blok za obstoječo sejo
`root@DietPi`. Uporabi samo novi blok, objavljen s preverjenim paketom; ne uporabljaj starega paketa
`access.tar.gz` ali `update_diagnostics.py` kot nadomestilo.

Blok mora:

1. Prenesti konkretni paket in preveriti objavljeni SHA256 ter vse člane.
2. Preveriti Raspberry Pi in pričakovano različico obstoječega pomočnika.
3. Shraniti zasebno varnostno kopijo trenutne kode in pravic.
4. Preveriti novi diagnostični izpis pred zamenjavo.
5. Atomsko zamenjati samo kodo pomočnika in trajno zapisati rezultat.
6. Preveriti delovanje dejanskega ukaza `maintenance status`.

Namestitev ne spreminja SSH nastavitev, ključev, sudoers, dispatcherja, GPIO,
Node-RED, sistemskih storitev ali načina upravljanja tuša. Root seja ostane
odprta do potrditve druge omejene SSH povezave.

## 3. Kaj nato sam izvede Codex

Iz ločene povezave z obstoječim ključem in preverjanjem identitete gostitelja:

```powershell
ssh -i "$env:USERPROFILE\.ssh\freezeprotect_commission" `
  -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes `
  -o ConnectTimeout=10 freezeprotect-commission@192.168.114.192 `
  sudo -n /usr/local/sbin/freeze-protect-maintenance status
```

Pričakovano: obstoječa statusna polja in novo polje `light_gpio21_bench` s
prebranim rezultatom. Codex preveri, da dodatni argument še vedno ni dovoljen,
in zabeleži hash nameščene kode ter dejanski rezultat. Za ta preverjanja ne
potrebuješ ponovno prepisovati izpisov iz root seje.

Če drugo preverjanje ne uspe, ne širimo dovoljenj in ne ponavljamo namestitve
na slepo. Iz varnostne kopije in namestitvenega potrdila se določi potrebna
obnovitev samo diagnostične kode; podatki in dokazila se ohranijo.

## 4. Nadaljevanje povezave kamere

Po razlagi neskladja GPIO21 sledi popravek ugotovljenega vzroka in ustrezen
preizkus. Uspešna namestitev diagnostike sama ne pomeni sprejetega GPIO gonilnika,
nameščene storitve luči ali delujočega proženja iz kamere G4 Pro.

Tehnični načrt: `docs/superpowers/plans/2026-10-15-light-bench-diagnostics.md`.
