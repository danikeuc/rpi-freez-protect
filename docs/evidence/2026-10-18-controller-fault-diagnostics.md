# Nadaljnja diagnostika izpadov — 18. oktober 2026

## Potrjeno

- Po obnovitvi sta prek omejenega SSH dosegljiva oba krmilnika: tuš MANUAL_DRAIN/user_off,
  luč MANUAL_OFF/OK, GPIO luči OFF. Med tem pregledom ni bil poslan noben aktuatorski ukaz.
- Izvorna napaka tuša je bila HTTP503 iz lokalnega Node-RED mostu. Njegov odgovor
  vsebuje podrobnejši razlog, vendar ga obstoječi adapter pri HTTPError ne shrani.
- Node-RED lahko 503 vrne zaradi nepripravljenega mostu, zavrnjenega/pretečenega
  dovoljenja, neujemanja povratne informacije GPIO ali napake izvajalca.
  Sam status503 med temi vzroki ne razlikuje.
- LightController.tick združi napako časa, shranjevanja pri izteku in podaljševanja
  dovoljenja v clock_or_lease_fault. Ta oznaka sama ne dokazuje, da je bila težava
  v URI/omrežni povezavi ali v sistemski uri.
- Šest neavtentificiranih GET zahtev v 25 sekundah je prejelo pričakovano zavrnitev
  dostopa403 na Pi gatewayu. RTT15–47ms; časovna glava je bila največ približno
  0,51 sekunde oddaljena od računalnika. Glava ima sekundno ločljivost. To je
  kratkotrajen vzorec ure HTTP strežnika, ne dokaz NTP sinhronizacije ali stabilnosti
  skozi pretekli dogodek. Zahteve niso vsebovale poverilnic in niso upravljale izhodov.

## Pripravljene spremembe kode

1. Adapter Node-RED ob HTTP napaki shrani numerični status in razlog iz fiksnega
   dovoljenega seznama. Neznani, predolgi in neveljavni odgovori postanejo unclassified.
   Surovi odgovor, URL, poljubna sporočila napake in poverilnice se ne beležijo.
   Branje odgovora je omejeno na4097 bajtov; uporablja obstoječi socket timeout.
   To ni nova garancija celotnega trajanja HTTP zahteve.
2. Luč ob zaznanem časovnem preskoku zapiše razliko wall in monotonic časa.
   Zanka ob napaki loči stopnje clock/expiry/renewal in shranjevanje od I/O/validacije,
   ne da bi zapisala surovo izjemo. Po zaklepu napake ne ponavlja zapisa vsako iteracijo.
3. Javni statusi, prag5s, dovoljeni ukazi, lease in samodejno odstranjevanje napak se
   ne spreminjajo. Testi preverjajo enak FAULT/OFF odziv.

## Namestitev in meje

Spremembe so lokalni diagnostični kandidat. Na Pi še NISO nameščene; obstoječi
recovery paket je nespremenjen in ga ni treba ponovno izvajati. Paket izvornih
sprememb vsebuje manifest, diff in kontrolne vsote; ni root namestitveni paket.

Predhodni nameščeni light controller SHA256:
34b153c78493711199b74d42a856fb644fcbf225239c950c2885e423a40d8c5f.
Prvotnega vzroka HTTP503 ali časovne napake s temi ugotovitvami ne razglašamo za
odpravljenega. Za naslednjo dejansko odpoved potrebujemo zabeležen razlog mostu
in časovno razliko; zgodovinskega izgubljenega odgovora ni mogoče rekonstruirati.

Obstoječi SSH helper iz dnevnika že prepozna clock discontinuity in actuator_failure;
novih podrobnih polj še ne vrača. Njegova dovoljenja v tem posegu niso spremenjena.
Namestitev in ponovni zagon sta po WORKSTATION_CODEX_COMMISSIONING.md ločen
zaupanja vreden root-console korak. Rutinski SSH tega ne omogoča.

## Izhodi in odpovedi ostanejo po obstoječi pogodbi

- Par GPIO26/20 ima enega lastnika; dovoljena para sta00 in11. Obnovitev je zahtevala11/DRAIN.
- Neodvisen GPIO21 je aktivno nizek; HIGH je električni OFF, ne dokaz stanja kontaktov.
- Izguba komunikacije: živ izvajalec uporablja obstoječi lease (luč3s, par60s),
  z dodatnim odzivom zanke/OS; fizični čas izklopa ni izmerjen.
- Sesutje/zastoj krmilnika: lease velja le, če izvajalec še deluje. Odpoved izvajalca
  nima neodvisne programske garancije; zadržani ON luči je lastnik že sprejel.
- Ponovni zagon: zahtevan OFF/DRAIN, zaklenjen FAULT se ne odstrani sam.
- Izguba/vrnitev napajanja: fizikalni odziv vezave ni potrjen; ni nove strojne garancije.

Za vzrok ne spreminjamo pragov, trajanja dovoljenj ali časovne sinhronizacije na slepo.

## Preverjanje kandidata

1.132 celotnih pytest testov je uspešnih; Ruff in git diff --check sta uspešna.
13 novih regresijskih primerov je pred spremembo padlo in po spremembi prestalo.
Ostaja obstoječe Starlette/httpx opozorilo o zastareli odvisnosti.

## Namestitveni kandidat pripravljen

Prvotni source-only paket je zgodovinski artefakt. Ločen pregledljiv
[namestitveni postopek](../../deployment/lighting/diagnostics/README.md) zdaj
vsebuje omejeno namestitev obeh diagnostičnih datotek. 16 dodatnih testov preverja
namestitvene zavrnitve in kopije. Skupaj 1.132 testov PASS. Še NI nameščeno na Pi.

Zadnji omejeni SSH pregled: tuš USER_OFF/MANUAL_DRAIN, luč MANUAL_OFF/OK/OFF,
809 s preostanka. Ta podatek je trenutni posnetek in ne podaljša ročnega izklopa.

## Installation receipt and independent status — 2026-10-18

Operator supplied CONTROLLER_FAULT_DIAGNOSTICS_INSTALLED, backup
/root/controller-fault-diagnostics.3xvxe5ia. Continuation reviewed the exact
pre-stop attempt asf8pjxk and preserved its backup. Installed hashes reported:

- light_controller.py: 21795415098d09e294c0e0aa486b7f675f26d786e4b08a07693213d49c2a9ce9
- node_red.py: a7be7bafdd890db267035d0273c8a2ea874d5c1bc762ad7620c4b3f84c19ede1

Both match the prepared package. These file hashes and GPIO20/21/26 HIGH are
installer evidence, not an independent SSH file read or physical acceptance.
The installer reports zero API writes; normal startup issued OFF/DRAIN.

A subsequent independent restricted SSH status succeeded: shower
weather_assisted/MANUAL_DRAIN/user_off; light health OK, MANUAL_OFF, desired_on
false, gpio_on false, restart_manual_inhibited, revision78, 1581 seconds
remaining. Hub PID5599 active; paired GPIO PID436 and Node-RED PID627 remained
active. All three reported NeedDaemonReload=no. Categorized journal summary
had zero matches within its bounded window; this does not prove the absence of
all faults or a permanent fix. No actuator command was sent through SSH.

This supersedes NOT_INSTALLED wording above. Diagnostics are installed; the
original cause remains NOT_RESOLVED and physical acceptance NOT_TESTED. Manual
light inhibition expires under existing policy; shower USER_OFF remains until
an intentional START. No automatic monitoring task was created.
