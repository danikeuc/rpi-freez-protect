# Namestitev diagnostike izpadov krmilnikov

Status: PREPARED, NOT INSTALLED. Izvirni vzrok napak še ni odpravljen.

## Obseg

Dve datoteki: adapter Node-RED (dovoljene kategorije HTTP napak) in krmilnik luči
(stopnja napake ter številčna razlika sistemske in monotone ure). Brez spremembe
pragov, dovoljenj, GPIO lastnikov, Node-RED tokov ali nastavitev. Izvorne datoteke
morajo ustrezati baseline.json; druga različica se zavrne pred ustavitvijo.

## Pred začetkom

Uporabi obstoječo zaupanja vredno sejo **root@DietPi na 192.168.114.192**.
Ni za Synology in ni za PowerShell. 24 V ventilov in napajanje luči naj ostaneta
odklopljena za ta poseg. V času namestitve ne uporabljaj krmilnikov.
Tuš mora biti USER_OFF/DRAIN; luč zdrava MANUAL_OFF, izhod OFF, vsaj 5 minut
preostanka. Če je ročni izklop potekel, v adminu luči najprej izberi
»Ročni izklop · 30 min«. To prekine delovanje kamere do izteka ročnega načina.
Če ni zdravega potrjenega stanja, postopka ne ponavljaj na slepo.

Namestitev izvede samo korak v preverjenem prenosnem bloku. Flag
--loads-disconnected potrjuje že zahtevano fizično stanje; ni programski odklop.
Omejeni SSH po WORKSTATION_CODEX_COMMISSIONING.md nima pravice nameščati tega
paketa. Priloženi recovery modul je uporabljen samo za branje, varnostne kopije
in preverjanja; njegov recover()/main() se NE izvaja.

## Zaporedje

1. Pi model, root, operacijski zaklep, nespremenjene datoteke, zdrava storitvena
   stanja, kratek vzorec ure in GPIO20/21/26 output HIGH.
2. Root-private varnostne kopije obeh SQLite baz, identitete weather baze in
   obeh spremenjenih virov; zabeležene nastavitve in hashi okolij brez izpisa gesel.
3. Ustavitev samo light-controller.service in freeze-protect.service. Parni
   izvajalec, izvajalec luči in Node-RED ostanejo aktivni. Dodatni mirujoči kopiji baz.
4. Preverjanje trajnega MANUAL_OFF in USER_OFF; atomska zamenjava dveh datotek.
   Pred zagonom največ 90 s vzdrževalnega okna, dovolj časa ročnega izklopa in
   nespremenjeno okolje/identiteta. Baze se ne prepisujejo.
5. Zagon Hub-a in krmilnika luči, samo GET preverjanja API, ponovno preverjanje
   zdravja, stanj, GPIO, nastavitev in okolij. Običajen startup pošlje OFF/DRAIN;
   nič ON/SUPPLY in nič ukazov API POST.

Uspeh je šele CONTROLLER_FAULT_DIAGNOSTICS_INSTALLED in success.json.
Namestitev ne dokazuje fizičnega položaja relejev/ventilov in ne odpravi
izvornega vzroka. Za potrditev namestitve sledi neodvisni omejeni SSH pregled.
Ročni izklop luči po obstoječem času poteče; USER_OFF tuša ostane.

## Napaka in obnovitev

Vsaka napaka se ustavi; brez samodejne ponovitve ali rollbacka. Od začetka
varnostne kopije je trajni marker /root/controller-fault-diagnostics-v1.started
in imenik /root/controller-fault-diagnostics.*. Ne briši markerja. Če se ustavi po
stop-started.json, lahko storitvi ostaneta ustavljeni; ne zaženi ju na slepo.
Ohrani odklopljeni bremeni, sporoči kodo in BACKUP_DIRECTORY, nato pregledaš
zasebno dokazilo. Obnovitev potrebuje pregled dejansko zamenjanih datotek,
trajnega izklopa in ure. Prednost ima ohranitev sedanjih baz; stare kopije ni
varno avtomatsko povrniti (zgodovina, revizije, časovni roki).

## Preverjanje

1.132 pytest testov PASS; Ruff PASS. Namestitveni testi uporabljajo začasne baze
in simuliran systemd/API: preverijo kopije zgodovine, samo GET, le dve dovoljeni
storitvi, zavrnitev drugačne kode, napake kopiranja/pisanja ter potekel ali
nevaren trajni način. To niso preizkusi fizičnih bremen.
