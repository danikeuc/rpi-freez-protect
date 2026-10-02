# Dial Admin Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodati mobilno admin stran na gumbu za štirimestni PIN s spletno obnovo, čas tuša 1–10 minut in rotacijo 0°/90°/180°/270°.

**Architecture:** Gumb hrani in zaščiti svoje nastavitve ter ob namernem vklopu pošlje izbrano trajanje. RPi preverja zahtevek in ostane edini lastnik odštevanja. Dostava ima dva samostojno preverljiva dela: združljiv RPi API, nato firmware, ki ta API uporablja.

**Tech Stack:** Python 3.12/FastAPI/pytest na RPi; C, ESP-IDF 5.5.5, ESP32-S3, LVGL, NVS in obstoječi HTTP strežnik na Waveshare Dial.

**Spec:** `docs/superpowers/specs/2026-10-02-dial-admin-settings-design.md` — potrjena zasnova, obvezno branje skupaj s tem načrtom.

Status: načrt pripravljen za uporabnikov pregled; nobena spodnja implementacijska naloga še ni opravljena.

## Global Constraints

- Trajanje: 1–10 celih minut, privzeto 10 minut; največ 600 sekund v manual_timed.
- Rotacija: 0°, 90°, 180° in 270°, tudi dotik in poteze.
- PIN: natanko štiri ASCII številke; začetne ničle dovoljene; določi ga uporabnik, brez privzetega PIN-a.
- Seja: 15 minut nedejavnosti; pet napačnih poskusov povzroči 60 sekund blokade na napravo, tudi čez ponovni zagon.
- Obnovitvena koda: najmanj 128 bitov naključnosti, prikaz samo ob izdaji, spletna obnova ohrani vse druge nastavitve.
- Noben obisk, shranjevanje, obnova PIN-a ali rotacija ne sproži SUPPLY in ne spremeni aktivnega roka.
- DRAIN=0 in SUPPLY=1 sta logični stanji. Dejanski BCM26/20 sta high/high za DRAIN in low/low za SUPPLY. Parni daemon ostane edini GPIO zapisovalec.
- Brez Tuya, luči, novega Roon bridge-a ali temperaturnega avtomatskega krmiljenja v tej dostavi.
- Obstoječi prazni POST ohrani 600 s. Krajši shranjeni čas ne sme ob izgubi podpore tiho postati 600 s.
- PIN in preverjevalniki, sejni identifikatorji ter povezovalni žetoni ne sodijo v dnevnike, izpis konfiguracije ali Git.
- Mobilni obrazci v slovenščini; uspeh šele po potrjenem zapisu in uporabi. Obstoječi HTTP je namenjen zaupanemu LAN.
- Izdaje v1.0.0 ostanejo obnovljive. Brez združevanja, nove izdaje, namestitve ali krmiljenja strojne opreme samo na podlagi tega načrta.

## Review Focus

1. Dvojna začetna nastavitev ali obnova z isto kodo: uspe največ en zahtevek; izgubljeni odgovor omogoča prijavo z novim PIN-om (nalogi 2, 3).
2. Izpad med zapisom ali blokado: zadnja potrjena konfiguracija ostane uporabna, ponovni zagon ne odpre novih neomejenih poskusov (naloga 2).
3. Stari API, povrnitev RPi-ja in zastarel odgovor: krajši shranjeni čas ne povzroči daljšega vklopa ali poznega predvajanja ukaza (nalogi 1, 4).
4. Rotacija med držanjem ali sprememba napajanja: ni klika/SUPPLY, lokalna izbira se ne prepiše z Roon konfiguracijo (nalogi 5, 6).
5. Nesimetričen delni izris, robovi in pomanjkanje DMA pomnilnika: pravilen položaj in dolžina, brez napačnega fallback izrisa (nalogi 5, 6).

---

## Repozitoriji, osnova in razdelitev datotek

- RPi issue [#21](https://github.com/danikeuc/rpi-freez-protect/issues/21), veja `codex/dial-admin-settings`, osnova `0a8f794e6e04ec09524d77f34d1286d0e893c56b`. Delovni imenik načrta: `/home/danik/.codex/worktrees/knob-valves-design/rpi-freez-protect`.
- Knob issue [#9](https://github.com/danikeuc/roon-knob/issues/9), izhodišče izdaje `b39d75278793cbec73e53fd51326626837822ca7`. Pred izvedbo preveri aktualni HEAD, AGENTS.md, lokalne spremembe in pripete worktree-e; uporabi ustrezen prost checkout in vejo `codex/dial-admin-settings`. Pregledani checkout: `/mnt/c/users/danik/projects/roon-knob-valves`.
- Ukazi spodaj tečejo v navedenem repozitoriju, Python ukazi v njegovem razvojnem okolju. Ne izvajaj skripte `build_flash_idf.sh` za samo gradnjo: vsebuje flash.
- RPi: razširi obstoječa service/API modula in njune teste. Knob: nove majhne enote `admin_store_dial`, `admin_auth_dial`, `admin_server_dial`, `admin_settings_dial`, `display_rotation_dial`; obstoječi config server le poveže prijavo/varovala.
- Nove C enote in njihovi headerji so v `idf_app/main/`, gostiteljski testi v `tests/admin_dial/`, runner `scripts/test_admin_dial.sh`. `idf_app/main/CMakeLists.txt` se dopolni ob vsaki vključeni enoti.
- Naloga 1 je ločen API deliverable. Naloge 2–6 skupaj tvorijo firmware deliverable. Nalogi 2 in 5 sta neodvisni; naloge 3/4/6 uporabljajo njune spodaj določene vmesnike.

## Task 1: Strogo omejeno trajanje na RPi

**Files:** Modify `src/freeze_protect/application/service.py`, `src/freeze_protect/api/app.py`; Test `tests/unit/test_m1_service.py`, `tests/integration/test_m1_api.py`.

**Interfaces:**
- Produces `ControlService.start_timed_shower(self, duration_seconds: int | None = None) -> Decision`.
- Produces `timed_shower_duration_supported: bool` v display statusu: true za manual_timed z novo podporo, sicer false.
- Consumes obstoječo monotono uro, Settings in parni actuator; ne dodaja zapisovalca GPIO.

- [ ] **RED testi:** `test_manual_duration_accepts_whole_minutes` parametrizira `range(60, 601, 60)` in preveri `deadline == now + seconds`; `test_duration_body_rejects_invalid_without_actuation` pokrije true, 60.0, "60", null, manjkajoče/odvečne/podvojene ključe, 0, 59, 61, 601, ogromno telo in JSON array. Zahtevaj zavrnitev in nespremenjeno število actuator klicev. Dodaj `test_explicit_duration_rejected_outside_manual`, `test_duration_respects_configured_max`, `test_duration_retry_does_not_extend_deadline` ter `test_short_duration_expires_with_disconnected_client`.
- [ ] **RED ukaz:** `python -m pytest tests/unit/test_m1_service.py tests/integration/test_m1_api.py -q`; novi primeri morajo odpovedati zaradi nepodprtega trajanja/polja, ne zaradi okolja.
- [ ] **Implementacija:** prazen body preslikaj v None; sicer omeji body na 256 bajtov in dekodiraj JSON z zavrnitvijo podvojenih ključev. Sprejmi natanko `{"duration_seconds": int}` in `type(value) is int`, 60–600 z deljivostjo 60. Tudi service neposredno preverja tip/meje. Eksplicitno trajanje zunaj manual_timed zavrni; preseganje configured max zavrni brez clamp-a. Prazno telo ohrani prejšnje obnašanje, tudi v drugih načinih. Aktivni ali pravkar potekli rok ohrani obstoječo semantiko brez samodejnega novega SUPPLY. Drain endpoint ostane samo s praznim telesom.
- [ ] **GREEN:** isti ukaz; ohrani teste praznega POST, konflikta pri max pod 600, exact expiry, shutdown DRAIN ter odsotnosti skrivnosti. Nato `python -m ruff check .` in `python -m mypy src`.
- [ ] **Commit:** vključi zgornje štiri datoteke, `feat(api): accept bounded manual shower durations`.

## Task 2: Trajna konfiguracija in PIN politika gumba

**Files:** Create `idf_app/main/admin_store_dial.[ch]`, `admin_auth_dial.[ch]`, `tests/admin_dial/test_admin_store.c`, `test_admin_auth.c`, `scripts/test_admin_dial.sh`; Modify `idf_app/main/CMakeLists.txt`.

**Interfaces:**
- `admin_settings_t { uint16_t duration_seconds; uint16_t rotation_degrees; bool rotation_override; uint32_t generation; }`.
- `esp_err_t admin_store_load(admin_settings_t *out)` in `esp_err_t admin_store_save(const admin_settings_t *candidate, uint32_t expected_generation)`; stale generation vrne konflikt prek imenovane napake `ADMIN_ERR_CONFLICT`.
- `admin_auth_setup(pin, repeated_pin, recovery_out)`, `admin_auth_login(pin, session_out)`, `admin_auth_recover(code, new_pin, repeated_pin, recovery_out)`, `admin_auth_change_pin(session, new_pin, repeated_pin)`, `admin_auth_reissue_recovery(session, pin, recovery_out)` vračajo `admin_result_t` (OK, INVALID, DENIED, LOCKED, CONFLICT, STORAGE_ERROR). Vsi vhodi so `const char *`; izhodna koda `char[33]` in seja `char[65]`.
- `bool admin_auth_session_valid(const char *session, bool touch)`; `void admin_auth_logout(const char *session)`. Seje so samo v RAM, po restartu neveljavne.

- [ ] **RED testi:** `test_pin_leading_zero_and_exact_ascii_length`, `test_setup_race_has_one_winner`, `test_recovery_is_single_use`, `test_lost_recovery_response_new_pin_works`, `test_lockout_survives_reboot`, `test_session_idle_900_seconds`, `test_storage_failure_preserves_confirmed_state`. Preveri pet zavrnitev → blokada pri t+59, dovoljenje pri t+60; restart med blokado zahteva novih 60 s. Preostali števec manj kot pet preživi restart. Fault injection naj prekine vsak commit/readback, ne samo simulira vračanja uspeha.
- [ ] **RED ukaz:** dodaj runner, ki prevede dejanske nove module z injiciranimi storage/clock/crypto adapterji; `sh scripts/test_admin_dial.sh` mora pokazati konkretne nove neuspele assertione pred implementacijo.
- [ ] **Implementiraj store:** ločena verzionirana NVS namespace in atomski blob za avtentikacijo, ločen blob za nastavitve; mutex za read-modify-write, generation in povratno branje pred uspehom. Ne spreminjaj obstoječih povezovalnih namespace-ov. Manjkajoč duration = 600; manjkajoč rotation override = false, ohrani obstoječe veljavne 0/180 nastavitve. Poškodovan auth record ne pomeni odprte prve namestitve. Če zapis uspe, readback pa odpove, zapri nadaljnje mutacije do uspešne ponovne uskladitve z NVS.
- [ ] **Implementiraj auth:** ESP RNG za 16-byte salt/recovery ter 32-byte session; mbedTLS PBKDF2-HMAC-SHA256 (100000 iteracij, 32-byte verifier, format/version shranjena), konstantnočasovna primerjava. Težko preverjanje na workerju, ne na UI opravilu. Omejena čakalna vrsta, največ ena aktivna seja. Števec napačnih poskusov trajno zapiši pred odgovorom; ob storage napaki zavrni. Obnova atomarno zamenja oba verifierja in razveljavi seje; sprememba PIN-a razveljavi seje. Ponovna izdaja kode zahteva veljavno sejo in PIN. Ostale nastavitve ostanejo enake.
- [ ] **GREEN:** `sh scripts/test_admin_dial.sh`; dodaj znani PBKDF2 testni vektor za dejanski crypto adapter in preveri, da runner ne izpisuje testnih PIN-ov/kod/sej. V boot/readback testu potrdi, da migracija ne spreminja povezav ali pošilja ukazov.
- [ ] **Commit:** nove module, runner, teste in CMake, `feat(admin): persist PIN recovery and dial settings`.

## Task 3: Mobilna admin stran in zaščita konfiguracijskih poti

**Files:** Create `idf_app/main/admin_server_dial.[ch]`, `admin_page_dial.h`, `tests/admin_dial/test_admin_http.c`; Modify `idf_app/main/config_server.c`, `idf_app/main/CMakeLists.txt`, `scripts/test_admin_dial.sh`.

**Interfaces:**
- Consumes Task 2 auth; `esp_err_t admin_server_register(httpd_handle_t server)` registrira poti; `bool admin_http_authorize(httpd_req_t *req, bool mutation)` varuje tudi stare handlerje.
- Public shell `/admin`; GET `/admin/api/session` vrne samo setup-required/authenticated in seji pripadajoči CSRF token. POST `/admin/api/setup`, `/login`, `/recover` so javni z omejitvijo poskusov; ostali spodnji POST-i zahtevajo sejo/CSRF.
- POST `/admin/api/logout`, `/pin`, `/recovery-code`; GET `/admin/api/settings` in POST `/admin/api/shower`, `/rotation` uporabljajo Task 6 settings adapter. Nobena pot ne izvaja vklopa vode.

- [ ] **RED testi:** `test_old_config_routes_require_session`, `test_cross_origin_mutation_denied`, `test_session_cookie_and_expiry`, `test_recovery_form_preserves_settings`, `test_setup_requires_matching_pin`. Dejanski registrirani handlerji morajo vrniti 401 brez seje, 403 ob napačnem CSRF/izvoru, 409 ob tekmovanju in 503 ob storage napaki. Noben odgovor/dnevnik ne vsebuje verifierjev ali obstoječih žetonov.
- [ ] **RED ukaz:** `sh scripts/test_admin_dial.sh` z HTTP fake adapterjem za dejanske handlerje, ne zgolj grep preverjanjem izvorne kode.
- [ ] **Implementacija:** majhen slovenski mobile HTML brez zunanjih CDN. Ločeni obrazci za Tuš/Zaslon, prikaz potrjene vrednosti, onemogočen dvojni save, napaka ob izgubljenem odgovoru s ponovnim GET. PIN input numeric/password, maxlength=4; koda prikazana enkrat z navodilom za shranitev. `Cache-Control: no-store`; cookie `HttpOnly; SameSite=Strict; Path=/`, sejni ID samo v cookie. Izvor preveri proti dovoljenemu lokalnemu naslovu/Host, ne reflektiraj poljubnega Host-a; za prijavo/setup/recover uporabi tudi preverjen Origin in JSON content type. Za sejne mutacije zahtevaj CSRF header. Brez CORS dovoljenja.
- [ ] **Zaščiti obstoječe poti:** `/`, `/config`, `/valves-config`, `/wifi-add`, `/wifi-remove`, `/ble`, `/ble-enable`, `/ble-scan`, `/ble-pair`, `/ble-forget`. Pred PIN setup dovoli samo setup shell; obstoječe obrazce dopolni s CSRF in ustrezno prijavo. Najprej preveri sejo, šele nato beri/spremeni konfiguracijo. Če stari credential GET obstaja, ne sme razkriti vrednosti pred prijavo.
- [ ] **GREEN:** `sh scripts/test_admin_dial.sh` in `sh scripts/test_valve_dial.sh`. Settings handlerji do Task 6 lahko vračajo preverjeni 503; firmware deliverable ni zaključen, dokler niso povezani. Browser test s simuliranim transportom preveri mobile obrazce, slovenščino, napake in one-time recovery prikaz.
- [ ] **Commit:** samo naštete spremembe, `feat(admin): add mobile login recovery and protected forms`.

## Task 4: Izbrano trajanje v fizičnem toku tuša

**Files:** Modify `idf_app/main/valve_logic.[ch]`, `valve_client_dial.[ch]`, `valve_ui_dial.c`, `tests/valve_dial/test_valve_logic.c`, `test_valve_integration.c`, `test_valve_ui_sequence.c`, `scripts/test_valve_dial.sh`.

**Interfaces:**
- Consumes `admin_store_load` iz Task 2 in Pi pogodbo iz Task 1.
- `valve_status_t` dobi `bool timed_shower_duration_supported` (manjkajoče/nepravilno polje = false).
- Dodaj `valve_request_t { valve_action_t action; uint16_t duration_seconds; }`; START enum preimenuj iz `VALVE_ACTION_START_600S` v `VALVE_ACTION_START`, zamenjaj vse uporabe in fake adapterje.
- `valve_client_post(const valve_request_t *request, valve_status_t *out)` in `valve_client_request_post_for_config(const valve_request_t *request, uint32_t generation, uint32_t *request_id)`; transport callbacku dodaj `const char *body, size_t body_len` pred `int *http_status`.

- [ ] **RED testi:** `test_start_captures_selected_duration`, `test_legacy_server_uses_empty_600_request`, `test_short_setting_with_missing_capability_blocks_start`, `test_stale_status_cannot_enable_start`, `test_disconnect_does_not_replay_start`, `test_settings_change_does_not_extend_active_shower`. Assert natanko JSON 300 za izbranih pet minut; brez POST pri krajši nastavitvi in manjkajoči podpori; DRAIN vedno ostane mogoč po obstoječih pravilih.
- [ ] **RED ukaz:** `sh scripts/test_valve_dial.sh` — novi transport/UI testi morajo odpovedati pred spremembo produkcijske kode.
- [ ] **Implementacija:** duration kopiraj v request ob potrjenem fizičnem namenu; ohrani request ID, Wi-Fi session in config-generation varovala. Podporo upoštevaj samo iz svežega odgovora iste povezave/konfiguracije. Za novejši API pošlji JSON tudi pri 600; za stari API dovoli samo prazen 600. Če strežnik zamenjamo med preverjanjem in POST, invalid body/404/400 ne sproži fallback POST-a. Worker ne ponavlja start-a po reconnect-u. Idle UI prikazuje shranjene minute, active UI čas iz Pi statusa.
- [ ] **GREEN:** oba host runnerja; obstoječi hold-to-start, short-touch DRAIN in Roon input-route testi ostanejo zeleni. Za stare source assertions, ki se morajo spremeniti, dodaj vedenjski test nove poti.
- [ ] **Commit:** `feat(dial): send selected shower duration with capability checks`.

## Task 5: Preverljiva preslikava štirih rotacij

**Files:** Create `idf_app/main/display_rotation_dial.[ch]`, `tests/admin_dial/test_display_rotation.c`; Modify `scripts/test_admin_dial.sh`, `idf_app/main/CMakeLists.txt`.

**Interfaces:**
- `dial_point_t { int x; int y; }`, `dial_rect_t { int x; int y; int width; int height; }`.
- `bool dial_rotation_rect(uint16_t degrees, int screen_width, int screen_height, dial_rect_t source, dial_rect_t *destination)`.
- `bool dial_rotation_pixels(uint16_t degrees, const uint16_t *source, size_t width, size_t height, uint16_t *destination, size_t destination_pixels)`; nepokrivajoča se bufferja, output tesno pakiran, brez byte swap.
- `bool dial_rotation_touch(uint16_t degrees, int screen_width, int screen_height, dial_point_t physical, dial_point_t *logical)`; inverse prikaza. Vsi vrnejo false ob invalid kotu/obsegu/velikosti.

- [ ] **RED testi:** `test_rotation_non_square_rgb565`, `test_rotation_rect_at_all_edges`, `test_touch_inverse_matches_pixels`, `test_rotation_rejects_small_buffer`. Za matriko `[1,2,3;4,5,6]` mora clockwise90 vrniti `[4,1;5,2;6,3]`, 180 `[6,5,4;3,2,1]`, 270 `[3,6;2,5;1,4]`; sentinel za bufferjem ostane enak. Preveri 1xN, Nx1, neenake delne izrise in vse kote.
- [ ] **RED ukaz:** `sh scripts/test_admin_dial.sh`; memory sanitizer različica istega testa naj ujame out-of-bounds na gostitelju.
- [ ] **Implementacija:** blokovna preslikava 90/270 za boljši dostop do PSRAM, brez predpostavke PPA. Clockwise90 preslika globalno (x,y) v (H-1-y,x); touch je inverse. Geometrija pravokotnika in lokalni pixel order sta ločena. Byte swap ostane samo enkrat v adapterju gonilnika.
- [ ] **GREEN:** isti runner, brez sanitizer poročil; test kompozicije rotation in inverse za vsak vogal. Ta test ne dokazuje hitrosti na napravi.
- [ ] **Commit:** `feat(display): add bounded four-way rotation primitives`.

## Task 6: Povezava nastavitev, UI opravila in gonilnika

**Files:** Create `idf_app/main/admin_settings_dial.[ch]`, `tests/admin_dial/test_admin_settings.c`; Modify `idf_app/main/admin_server_dial.c`, `platform_display_idf.[ch]`, `platform_input_idf.c`, `valve_logic.[ch]`, `valve_ui_dial.c`, `common/platform/platform_display.h`, `idf_app/main/CMakeLists.txt`, host fake headerji in runnerja.

**Interfaces:**
- Consumes Task 2 store, Task 4 fresh capability in Task 5 geometrijo.
- `admin_result_t admin_settings_set_duration(uint16_t seconds, uint32_t expected_generation)`.
- `admin_result_t admin_settings_set_rotation(uint16_t degrees, uint32_t expected_generation)`; sinhroni odgovor HTTP workerju šele po UI worker ACK + NVS readback.
- `bool platform_display_try_rotation(uint16_t degrees)` je Dial notranja uporaba na UI opravilu. Obstoječi `void platform_display_set_rotation(uint16_t degrees)` ostane združljiv wrapper za bridge in ob aktivnem lokalnem override ne prepiše lokalne izbire.

- [ ] **RED testi:** `test_rotation_cancels_hold_without_supply`, `test_saved_rotation_survives_charger_and_bridge_poll`, `test_rotation_failure_restores_previous_value`, `test_duration_save_leaves_active_deadline`, `test_restart_never_enqueues_start`. Dve sočasni shranjevanji iste generacije: drugo vrne konflikt. HTTP uspeh zahteva ujemajočo applied+durable vrednost.
- [ ] **RED ukaz:** `sh scripts/test_admin_dial.sh` in `sh scripts/test_valve_dial.sh`.
- [ ] **Implementacija settings:** validiraj minute in svežo podporo Pi-ja; kratek čas brez podpore zavrni, saved krajše vrednosti pa ne prepisuj samodejno. UI pokaže razlog in onemogoči start. Rotacijo serializiraj na UI opravilu: rezervacija/validacija bufferja, preklic dotika/hold, apply/redraw, NVS commit/readback, ACK. Ob napaki zapisa povrni prejšnjo uporabljeno rotacijo; med transakcijo blokiraj nov touch intent. Če stanje NVS ni dokazljivo, vrni 503 in uskladi pred naslednjim save.
- [ ] **Implementacija driver/input:** uporabljaj eno potrjeno orientacijo za flush, touch in gesture. Preglej LVGL lastno transformacijo in odstrani dvojno preslikavo; scalar `valve_touch_coordinate` zamenjaj s parom koordinat. Rotate scratch ne predajaj DMA, če ni DMA-capable; počakaj na completion pred ponovno uporabo bufferja. Prevelik partial razdeli na veljavne bloke, ne uporabi `skip_rotation` fallback-a. Rotacija pred readiness se ne potrdi. Lokalni override velja pri obeh stanjih napajanja; pred prvim admin save ohrani legacy izbiro.
- [ ] **GREEN:** oba runnerja; preveri Roon screen gestures, zone/settings overlay in valve modal pri vseh kotih ter cancel/release zaporedja. Settings endpoint vrne samo javne vrednosti/generation/capability, ne credential blob-a.
- [ ] **Commit:** `feat(dial): apply durable admin settings on the UI task`.

## Task 7: Integracijsko preverjanje in pregled dostave

**Files:** Modify RPi `README.md`; Create RPi `docs/operations/dial-admin-settings.md`; Create Knob `docs/operations/dial-admin-settings.md`; Modify Knob `docs/meta/decisions/2025-12-20_DECISION_ROTATION.md`; obstoječe release evidence dopolni samo z dejansko izvedenimi preverjanji.

**Interfaces:** Consumes pogodbo in artefakte Tasks 1–6. Produces dve draft PR z exact HEAD SHA, testnimi rezultati in matriko implementirano/testirano/nameščeno; brez novih releasov.

- [ ] **Regresija RPi:** `python -m pytest -q`, `python -m ruff check .`, `python -m mypy src`, `python -m build`. Rezultate zabeleži; ni dovolj samo uspešna gradnja.
- [ ] **Regresija Knob:** oba host runnerja ter obstoječi controller-config/input testi iz CI. V ESP-IDF 5.5.5 okolju, target esp32s3, iz `idf_app` zaženi `idf.py build`; zahtevaj produkcijski PERF profil in iste stack/PSRAM/LVGL/BLE nastavitve kot trenutni Dial CI. Primerjaj velikost z app particijo ter prosti heap/stack na testni napravi. Ne uporabi flash skripte v tem koraku.
- [ ] **Pregled:** po izbranem subagent-driven postopku neodvisni pregled kode in dissent za auth/persistence, trajanje/legacy ter DMA/input. Popravi ugotovitve in ponovi samo prizadete teste; dokumentiraj dejanske omejitve. Izvedeni pregled ni trditev o fizičnem testu.
- [ ] **Dokumentacija:** opiši lokalni URL, prvo izbiro PIN-a, varno shranitev/rotacijo recovery kode, 1–10 minut, vse kote, izgubo obeh podatkov brez spletnega obvoda, lokalni rotation override in trusted LAN. Dodaj matriko izpadov iz spec: komunikacija, proces/hang, restart, napajanje; ohrani obstoječe nepreverjene fizične meje.
- [ ] **Pripravi namestitev:** točni SHA/checksums novega Pi wheel-a in firmware-a, baseline paketi ter backup navodila za config/NVS. Najprej združljiv API, nato firmware. Starega firmware-a ne obnovi z avtomatskim brisanjem NVS; ob downgrade-u lahko izgubiš novo spletno PIN zaščito, zato staro admin površino omeji na zaupan LAN in to izrecno navedi. Pi rollback pri saved krajšem času mora varno blokirati START.
- [ ] **Commit dokumentacije:** `docs(admin): document setup verification and rollback` v ustreznem repozitoriju; ustvari draft PR za #21 in #9 ter obe pripni chatu. V opisu loči automated-pass, hardware-pending, merged in deployed.

### Strojni sprejem pred odstranitvijo draft oznake

Ti koraki se izvedejo po pregledu artefaktov in dovoljenju za konkretno namestitev/test; do takrat ostanejo pending, ne »passed«.

- [ ] Telefon: prvi PIN z začetno ničlo, prijava/odjava, iztek seje, blokada in restart, recovery enkratna uporaba/izgubljeni odgovor; ostale povezave in nastavitve ohranjene.
- [ ] Pri vseh 0/90/180/270: Roon/slike, poteze, dotik, hold cancel, overlay, polnilnik; primerjaj odzivnost in flush čas 90/270 z 0/180 ter zabeleži dejanske meritve in uporabniški sprejem. Če UI zmrzuje ali memory gate odpove, ne potrdi kandidata.
- [ ] Tuš: najmanj 1-minutni in 10-minutni sprejeti interval na Pi, ponovljeni vklop ne podaljša, sprememba nastavitve velja naslednjič, zgodnji DRAIN deluje; posnetki API/deadline in GPIO dokazujejo samo opaženo stanje, ne nepreverjene hidravlike.
- [ ] Izpad Wi-Fi/restart gumba brez replay; kompatibilnost stari gumb/novi Pi in novi gumb/stari Pi, tudi rollback s saved kratkim časom. Vsak hardware test, ki ni mogoč, ostane jasno pending.

## Samopregled načrta

Pokritost: spec 1–2 → obseg/dve dostavi; 3 → Tasks 2–3; 4 → Tasks 2/3/6; 5 → Tasks 1/4; 6 → Tasks 5/6; 7–8 → Tasks 1/4/7 in ločeni strojni sprejem. Vseh pet Review Focus točk ima imenovan test. Vmesniki med nalogami so določeni zgoraj; nove javne vrste se deklarirajo v pripadajočem headerju. Načrt ne dokazuje delovanja in ne spreminja statusa še neizvedenih testov.
