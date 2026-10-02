# Admin stran gumba: PIN, čas tuša in rotacija

Datum: 2026-10-02  
Status: zasnova potrjena v pogovoru 2026-10-02, vključno s spletno obnovo PIN-a z obnovitveno kodo. Izvedbeni načrt sledi ločeno; implementacija še ni izvedena.

## 1. Namen in potrjeni obseg

Uporabnik na telefonu odpre lokalni spletni naslov Waveshare ESP32-S3 gumba in nastavi njegovo delovanje. Prva različica vključuje:

- štirimestni PIN, ki ga uporabnik določi ob prvi nastavitvi;
- trajanje tuša 1–10 celih minut, privzeto 10 minut;
- rotacijo 0°, 90°, 180° in 270°, vključno z dotikom in potezami;
- trajno shranjevanje nastavitev in jasen rezultat shranjevanja.

Nastavitev trajanja velja za naslednji namerni vklop. Shranjevanje ali obisk admin strani ne sproži tuša in ne podaljša aktivnega odštevanja. Trenutni sistem ostane v načinu manual_timed. Luči/Tuya, dodatni zasloni, preimenovanje con in samodejno krmiljenje po temperaturi niso del te prve različice. Roon bridge ne potrebuje sprememb.

## 2. Umestitev in alternative

**Izbrani predlog:** razširimo obstoječi spletni konfiguracijski strežnik na gumbu. PIN in uporabniške nastavitve ostanejo na gumbu; RPi preverja zahtevano trajanje in sam izvaja odštevanje ter izklop. To sledi uporabnikovi izbiri admin strani »pri gumbu«.

Alternativa na RPi-ju bi centralizirala prijavo, vendar bi zahtevala novo povezavo za nastavljanje lokalne rotacije. Alternativa na Synology bridge-u bi dodala odvisnost nastavitev tuša od Roon infrastrukture. Za dve izbrani nastavitvi ti možnosti nista priporočeni.

Spremembe so omejene na roon-knob in rpi-freez-protect. Obstoječe izdaje ostanejo obnovljive; projektne zahteve za pregled, odobritev združitve in strojno preverjanje ostanejo v veljavi.

## 3. Uporabniški tok in PIN

1. Prvi obisk pokaže »Nastavi PIN« z dvema vnosoma. PIN je natanko štiri številke; začetne ničle so dovoljene. Vnaprej nastavljenega PIN-a ni.
2. Prva nastavitev je dovoljena samo, dokler PIN še ne obstaja. Sočasna zahtevka ne smeta prepisati že ustvarjenega PIN-a.
3. Poznejši obisk pokaže prijavo. Uspešna prijava ustvari sejo; po 15 minutah nedejavnosti se zahteva ponoven PIN. Na voljo je Odjava.
4. Po petih napačnih poskusih sledijo 60 sekund blokade. Omejitev velja za napravo, ne samo posamezen IP. Ponovni zagon ne sme omogočati neomejenega ponavljanja poskusov.
5. PIN se shrani kot soljen preverjevalnik, ne kot izvorne štiri številke. PIN, sejni identifikatorji in obstoječi API žetoni se ne izpisujejo v dnevnik ali vračajo v odgovorih.
6. Sprememba PIN-a zahteva trenutno prijavo in ponovljen vnos novega PIN-a; obstoječe seje se razveljavijo.

**Obnova pozabljenega PIN-a na admin strani:** uporabnik želi spletno ponastavitev namesto postopka na fizičnem gumbu. Na prijavni strani je povezava »Pozabljen PIN«.

**Potrjeni način preverjanja:** ob prvi nastavitvi sistem ustvari naključno obnovitveno kodo z najmanj 128 biti entropije, jo enkrat pokaže in uporabnika pozove, naj jo shrani. Na napravi ostane samo soljen preverjevalnik kode. Veljavna koda skupaj z dvojnim vnosom novega štirimestnega PIN-a omogoči ponastavitev. Zahtevki so omejeni glede pogostosti; odgovor pri napačni kodi ne razkriva shranjenih podatkov. Ponastavitev je atomska: nastavi novi PIN, razveljavi obstoječe seje in porabljeno kodo ter ustvari novo obnovitveno kodo, ki se znova pokaže samo enkrat. Sočasna uporaba iste kode lahko uspe največ enkrat. Ob izgubljenem odgovoru se uporabnik lahko prijavi z novim PIN-om in po ponovnem preverjanju PIN-a ustvari nadomestno kodo.

Ponastavi se samo dostop. Ohranijo se Wi-Fi, Roon, povezava z RPi-jem, čas tuša in rotacija. Ponastavitev PIN-a ne sproži relejev in ne spremeni odštevanja. Brez pravilnega PIN-a ali obnovitvene kode spletna stran ne omogoča ponastavitve. Ta prva različica ne dodaja drugega spletnega obvoda za primer izgube obeh podatkov.

Prijava mora zaščititi tudi obstoječe spletne konfiguracijske poti, da sprememb ni mogoče opraviti prek starega obrazca. Redno upravljanje Roon-a in tuša na fizičnem gumbu ne zahteva PIN-a. Spletne spremembe zahtevajo veljavno sejo, zaščito pred ponarejenimi medstranskimi zahtevki in preverjanje izvora. Seja ima HttpOnly in SameSite zaščito. Uporaba ostaja na zaupanem lokalnem omrežju; PIN sam ne zagotavlja šifriranja obstoječega HTTP prenosa.

## 4. Stran z nastavitvami

Mobilna stran v slovenščini ima dva ločena sklopa in jasno označene shranjene vrednosti:

- **Tuš:** izbirnik 1–10 minut, po koraku 1 minuta, in gumb Shrani.
- **Zaslon:** štiri možnosti 0°, 90°, 180°, 270° z jasno označenim položajem in gumbom Shrani.

Ločena gumba omogočata nedvoumen rezultat vsake spremembe. Med shranjevanjem je ponovitev onemogočena. »Shranjeno« se pokaže šele po uspešnem zapisu in povratnem preverjanju. Napaka ohrani zadnjo potrjeno vrednost. Nastavitve trajanja ne ponujajo gumba za vklop vode.

Trajanje in rotacija se shranita v NVS z verzionirano strukturo. Ob nadgradnji se ohranijo obstoječe povezave in obstoječa veljavna rotacija 0°/180°. Če trajanje še ne obstaja, se uporabi 10 minut. PIN se zaradi običajne nadgradnje ne izbriše.

## 5. Pogodba z RPi-jem

Čas je nastavitev tega gumba. Ob novem namernem vklopu gumb pošlje izbrano trajanje, RPi pa ostane edini lastnik časovne omejitve in relejnih ukazov.

Predlagana združljiva razširitev:

- GET /api/v1/display/status dobi logični podatek `timed_shower_duration_supported`; true pomeni podporo izbirnim celim minutam 1–10 v manual_timed načinu. Manjkajoče polje pomeni starejši strežnik.
- POST /api/v1/display/actions/timed-shower z obstoječim praznim telesom ohrani starih 600 sekund.
- Novi odjemalec lahko pošlje JSON `{"duration_seconds": 300}`. V manual_timed načinu so dovoljeni samo pravi JSON integerji 60, 120, …, 600. Booleans, decimalke, besedilo, neznana ali podvojena polja ter vrednosti izven razpona se zavrnejo pred gibanjem relejev. Eksplicitno trajanje v drugih načinih se zavrne.
- Avtentikacija ostane obstoječi X-Display-Token. PIN je za lokalno administracijo gumba; na RPi se ne prenaša in gumb ne dobi splošnega administratorskega žetona RPi-ja.
- Ob aktivnem tušu ponovljen vklop, tudi z drugo vrednostjo, ne spremeni že sprejetega roka. RPi uporablja monotono uro. Vrnitev v DRAIN ostane enaka.

Gumb preveri podporo pred omogočanjem izbire krajšega trajanja. Pri starem strežniku ostane jasno prikazan fiksni čas 10 minut. Če podpora kasneje izgine in je shranjen krajši čas, je vklop onemogočen z razlago; odjemalec ne sme tiho zagnati 10 minut namesto izbranega krajšega časa. Povezave in ponovljene zahteve ne ustvarjajo čakalne vrste kasnejših vklopov.

## 6. Vse štiri rotacije

Pregledani gonilnik trenutno namenoma podpira le 0°/180°. Dokumentirana omejitev 90°/270° je počasna preslikava medpomnilnika. Zahteva zato vključuje dopolnitev gonilnika, ne samo dodajanja dveh izbirnikov.

- Rotacija se izvede v plasti prikaza; aplikacijska logika Roon-a in tuša ostane skupna.
- Prikazani položaj, LVGL dotik in preslikava potez uporabljajo isto potrjeno orientacijo; dvojna rotacija koordinat ni dovoljena.
- Ob spremembi se prekine trenutni dotik/držanje, nato se na UI opravilu uporabi nova orientacija in zahteva celotna osvežitev. Vrtenje zaslona ne sme ustvariti klika ali ukaza za tuš.
- Preslikava 90°/270° upošteva pravokotne delne izrise, robove zaslona, RGB565 byte order, velikost in življenjsko dobo DMA medpomnilnika. Prednost ima preslikava po majhnih blokih za bolj zaporeden dostop do pomnilnika. Ne predpostavljamo podpore strojnega pospeševalnika.
- Varnostne kontrole velikosti medpomnilnika ne smejo ob napaki tiho prikazati napačne orientacije. Ob neuspešni uporabi ostane zadnja potrjena orientacija; UI poroča neuspeh.
- Odzivnost 90°/270° se na isti napravi primerja z 0°/180° med Roon osvežitvami, potezami in prikazom tuša. Brez tega preizkusa vseh štirih položajev ne označimo kot strojno potrjenih.

## 7. Obstoječe meje krmiljenja ob izpadih

Logična SUPPLY=1 / DRAIN=0 sta različna od aktivno nizkih GPIO nivojev: dovoljena para BCM26/20 sta low/low za SUPPLY in high/high za DRAIN. Edini zapisovalec GPIO ostane parni daemon. PIN, rotacija in shranjevanje nastavitev ne pišejo GPIO.

| Izpad | Zahtevano obnašanje | Mehanizem in meja preverjanja |
| --- | --- | --- |
| Povezava gumba/telefona | Aktivni rok na RPi se ne podaljša; po ponovni povezavi ni samodejnega vklopa. | RPi odštevanje, največ 600 s od sprejetega vklopa; test z nadzorovano uro in odklopljenim odjemalcem. |
| Proces gumba ali Hub se ustavi/obvisi | Gumb ne obnavlja vklopa. Ob izpadu Hub-a parni daemon preneha ohranjati SUPPLY po izteku svoje najemne dobe. | Obstoječa doba največ 60 s od zadnje obnove, če daemon in njegova oskrba preživita. Izpad samega daemona ostaja ločena strojna meja. |
| Ponovni zagon | RPi začne v DRAIN; shranjene nastavitve gumba ne pomenijo obnovitve prejšnjega vklopa. | Test zagona in odjemalca; stanje pinov pred prevzemom programske opreme ni dokazano samo s tem testom. |
| Izpad in vrnitev napajanja | Brez samodejnega ponovnega vklopa. Dejanski mehanski izpust mora slediti obstoječi napeljavi. | Ločeno se obravnavajo napajanja ESP32, RPi in ventilov. Fizična lega ter čas odziva pri izgubi energije s to spremembo nista dokazana. |

Ti testi ne nadomeščajo fizičnega pregleda ventilov. Vsak preizkus s krmiljenjem relejev sledi obstoječim pravilom commissioning-a in svoji odobritvi.

## 8. Preverjanje in dostava

1. Testi PIN-a: prvi vnos, tekmujoča začetna nastavitev, napačni formati, začetne ničle, napačni poskusi, sejni iztek, sprememba in spletna ponastavitev z obnovitveno kodo, zavrnitev napačne ali že uporabljene kode, tekmujoča ponastavitev, napaka zapisa in izgubljeni odgovor; zavrnjene neposredne stare konfiguracijske poti.
2. Testi dejanske RPi logike: vse dovoljene minute, neveljavni vnosi, največ 600 sekund, prazno telo starega odjemalca, ponovljen ukaz brez podaljšanja in monoton rok.
3. Testi shranjevanja: napaka zapisa/povratnega branja in ponovni zagon; podatki in skrivnosti se ne izpisujejo.
4. Testi preslikave: vsi koti, točke na robovih, delni izrisi, poteze in preklic držanja ob spremembi orientacije.
5. Kompletni obstoječi testi in gradnja za točen Waveshare cilj; nato strojni preizkus telefonske strani, vseh orientacij, Roon-a in pravilnega prikaza časa.
6. Najprej se pripravi združljiv RPi API; stari gumb ostane uporaben z 10 minutami. Nato se preizkusi novi firmware. Pred vsako namestitvijo se ohranijo točni artefakti in konfiguracija za povrnitev. Povrnitev RPi-ja na stari API pri krajšem času ne sme povzročiti tihega daljšega vklopa.

Ta dokument je zasnova. V tej fazi ni bilo nameščeno ali spremenjeno nič na RPi-ju, gumbu ali Synologyju. Zasnovo dopolnjuje izvedbeni načrt `docs/superpowers/plans/2026-10-02-dial-admin-settings.md`; po njegovem pregledu sledi implementacija po Superpowers postopku.
