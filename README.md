# Oglasi za zaposlenje — Petrovaradin

Python 3.10+ sakupljač za Petrovaradin, Novi Sad i Sremske Karlovce. SQLite čuva zasebne oglase po izvoru, grupe duplikata, istoriju izmena, strukturirana polja i rezultate svakog pokretanja. Nije napravljen javni sajt niti je išta objavljeno.

## Pokretanje

Iz korena projekta, u PowerShell-u:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe main.py collect
.\venv\Scripts\python.exe main.py status
.\venv\Scripts\python.exe main.py export
.\venv\Scripts\python.exe main.py candidates
.\venv\Scripts\python.exe main.py deduplicate
.\venv\Scripts\python.exe main.py report
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Podaci su u `data/oglasi.sqlite3`, JSON u `data/oglasi.json`. Putanje su vezane za projekat, ne trenutni terminal. Primer filtriranja:

Komanda `report` pravi samostalan pregled `data/oglasi-pregled.html`: otvori ga u pregledaču, pretražuj po naslovu/poslodavcu/izvoru i filtriraj lokaciju. Podrazumevano skriva grupe kojima su svi poznati rokovi istekli. Prikazuje jednu karticu po grupi i sve originalne linkove. Pregled je snimak baze; ponovi komandu posle novog sakupljanja.

```powershell
.\venv\Scripts\python.exe main.py export --location Petrovaradin
.\venv\Scripts\python.exe main.py export --facet category --value IT
.\venv\Scripts\python.exe main.py collect --source nsz --max-details 3
```

Probni limit vraća status `partial` i izlazni kod 2 jer pretraga nije kompletna. Kod 0 znači da su aktivni izvori u tom prolazu obrađeni bez prijavljenog problema; ne predstavlja garanciju da izvor prikazuje sve postojeće oglase.

Ctrl+C traži uredan prekid: radnici završavaju aktivni zahtev i čuvanje oglasa, pa prestaju da preuzimaju nove oglase i stranice. Aktivni izvori dobijaju status `interrupted`, a program izlazni kod 130. Čekanje na mrežni zahtev i njegove ograničene ponovne pokušaje može potrajati; ponovljeni Ctrl+C ne pokreće traceback. Već sačuvani podaci ostaju u bazi. Ručno `collect` radi i posle 18h; raspored 06–18h određuje termine automatskog pokretanja.

## Izvori i obuhvat

### Osnovne informacije za platformu

```powershell
.\venv\Scripts\python.exe main.py export --format platform-json
.\venv\Scripts\python.exe main.py export --format csv
```

Izlazi su `data/poslovi-platforma.json` i `data/poslovi-platforma.csv` (UTF-8 sa BOM, separator `;`, za Excel). Jedan zapis predstavlja jednu grupu oglasa, uz sve izvorne linkove u `izvori`. Polja su `id`, `naslov`, `kategorija` (Posao), `poslodavac`, `lokacija`, `opis` (izvod do 280 znakova), `plata`, `tip_zaposlenja`, `link`, `datum_objave`, `rok_prijave`, `status`, `slika_url`, `kontakt_ime`, `kontakt_email`, `kontakt_tel`, `izvori`. Plata se prenosi samo iz strukturiranih podataka izvora. Slika i kontakt ostaju prazni; ne preuzimaju se nagađanjem. Puni oglas se čita preko `link` na izvornom sajtu. Ovo nije konačan ugovor sa odredišnom platformom — Paja treba da potvrdi nazive polja za uvoz.

Podrazumevano se izvoze svi sakupljeni zapisi, uključujući istekle. Dodaj `--exclude-expired` da izostaviš grupe čiji su svi poznati rokovi istekli; nepoznat rok nije potvrda aktivnog oglasa. Filter `--location "Novi Sad"` i `--output PUTANJA` rade i za ove formate. Postojeća komanda `export` i dalje pravi puni JSON `data/oglasi.json`. CSV neutralizuje početne oznake formula iz teksta oglasa; JSON čuva originalni tekst.

### Rokovi, arhiva i izbor izvora

`tip_zaposlenja` se dopunjava iz svih izvora grupe. `tip_zaposlenja_poreklo` razlikuje objavljen podatak (`izvor`) od ključnih reči prepoznatih u tekstu (`prepoznato_u_tekstu`). Različite objavljene vrednosti se čuvaju, ne bira se proizvoljno jedna. Datum objave može se dopuniti iz drugog izvora; datum prikupljanja ne predstavlja se kao datum objave.

Izvoz ima `vidljiv` i `arhiviran`, uz `status`. Istek se računa svaki put iz roka, bez brisanja baze. Rok bez sata važi do kraja navedenog dana u lokalnoj zoni računara (ovde Europe/Belgrade); rok sa vremenskom zonom poštuje tu zonu. Neispravan ili nepoznat rok ostaje nepoznat. Ako postoje samo istekli poznati rokovi, grupa ide u arhivu čak i kad drugi izvor ne navodi rok. Ako postoji neistekao rok, grupa ostaje vidljiva do najkasnijeg poznatog roka. Grupa bez ijednog poznatog roka ostaje vidljiva uz oznaku da rok nije poznat.

Svaki element `izvori` sadrži `naziv`, `link`, `originalni_link`, `datum_objave`, `rok_prijave` i sopstveni `status`. Platforma može prikazati listu dugmadi „Čitaj na Infostudu / Čitaj na drugom izvoru“. Lokalni HTML pregled već prikazuje sve te linkove, tip zaposlenja, datum i rok, uz izbor Vidljivi / Arhiva / Svi. Dok je pregled otvoren, proverava istek svakog minuta.

```powershell
.\venv\Scripts\python.exe main.py export --format platform-json --exclude-expired --output data\poslovi-vidljivi.json
.\venv\Scripts\python.exe main.py export --format platform-json --archive-only --output data\poslovi-arhiva.json
.\venv\Scripts\python.exe main.py report
```

Zakazani `scripts/run-collector.ps1` sada obnavlja puni izvoz, platformski izvoz, vidljive oglase, arhivu i HTML posle sakupljanja, uključujući delimično uspešan prolaz. JSON je snimak vremena izvoza: odredišna platforma treba i sama da proverava rok pri prikazu, jer se datoteka ne menja između pokretanja. Komanda `collect` sama ne pokreće izvoze; pri ručnom radu koristi gornje komande.

`sources.json` je proširiv registar. Uključeni su svi početno zadati portali, uz NSZ, KlikDoPosla, Kariera, Bulevar i Mjob. Dodatni kandidati su Startuj, javni/interni konkursi Novog Sada i NSZ PDF publikacija. Njihovi posebni adapteri još nisu urađeni; spisak nije tvrdnja da su svi relevantni izvori na internetu obuhvaćeni.

- HelloWorld, Infostud, Halo oglasi, Oglasi.rs, Poslovi.rs: HTML/JobPosting adapteri.
- NSZ: posebna struktura oglasa, filter mesta 155 (Novi Sad) i 167 (Sremski Karlovci), uključujući ćirilicu.
- Lako do posla: javni API koji koristi njihov sajt. Preuzimaju se isključivo potrebna polja oglasa; podaci o korisničkim nalozima se ne čuvaju.
- KlikDoPosla: JobPosting; Kariera: JobPosting ili zapis sa linkom ka originalu i oznakom da opis nedostaje.
- Bulevar: adapter javnog Wix šablona. Izmena šablona zahteva ažuriranje selektora.
- Jooble: robots.txt odbija pretragu, a direktna provera vraća 403. Za aktivno prikupljanje potreban je dozvoljeni API/feed.
- Mjob: javni API sa paginacijom, opisom, potrebnim veštinama, satnicom, smenama i odvojenim gradom/mestom rada. Originalni link vodi na stranicu oglasa.
- Proširenje: Joberty (javni API, sve stranice), Šljaka (HTML i paginacija), OglasZaPosao (puni oglasi i označeni izvodi sa originalnim linkom), Manpower (Novi Sad i Južnobački okrug uz konačni lokalni filter), SBU (javna AJAX paginacija i filter mesta rada), PAZ (preskače demo oglase).
- Adorio: samo izvodi sa dozvoljene početne liste; detalji i query paginacija su zabranjeni robots pravilima. Status je `partial`, opis je označen kao nepotpun. Careerjet: detektuje verifikacionu stranicu i prijavljuje grešku; za pouzdan pristup potreban je dozvoljen API/feed.

Detalji proširenja, ograničenja i predlozi poboljšanja: [docs/prosirenje.md](docs/prosirenje.md).

Svi pronađeni oglasi ponovo prolaze filter stvarnog mesta rada. Naziv grada u navigaciji i adresa sedišta poslodavca iz JobPosting-a ne koriste se kao mesto rada. Kada strukturirana lokacija nedostaje, lokacija se izvodi iz naslova/opisa i označava `location_from_text`; to je manje pouzdano. Naselja grada Novog Sada (Futog, Veternik, Sremska Kamenica, itd.) mapiraju se na filter Novi Sad uz očuvanu izvornu lokaciju, prema [spisku JKP Informatika](https://www.novisadinvest.rs/cyr/broj-stanovnika-po-naseljima). Petrovaradin ostaje poseban filter. Remote oglasi bez lokalne lokacije trenutno se ne uključuju.

## Polja i grupisanje

Naslov, poslodavac, opis, izvorni URL, lokacije, datum objave, rok, prvi/poslednji put viđen i vreme poslednjeg preuzimanja čuvaju se za svaki izvor. Izvorna strukturirana polja obuhvataju ugovor, radno vreme, model rada, kategoriju, veštine, obrazovanje, iskustvo, benefite, platu i broj izvršilaca kada ih izvor daje. NSZ/Poslovi dodatna polja ostaju u `structured.source_fields`. Lako do posla i Bulevar imaju odvojene sekcije uslova/opisa/ponude gde postoje.

Izvedene kategorije, veštine i tipovi rada nose `method: keyword` i `review_required: true`; mogu imati greške, naročito kod negacija. Nepoznato ostaje prazno. Novac se ne pretvara u izmišljenu mesečnu zaradu: čuvaju se izvorna vrednost, valuta/jedinica kada postoje.

Isti URL se ažurira bez novog oglasa. Isti potvrđeni originalni link povezuje objave; za sadržajno poklapanje traže se isti normalizovani poslodavac, naslov i skup lokalnih lokacija. Potpuno isti opis od najmanje 160 normalizovanih znakova može se spojiti i bez datuma; različiti poznati datumi udaljeni preko 30 dana ostaju odvojeni. Ako se opisi razlikuju, potrebni su datumi unutar 30 dana i najmanje 90% sličnosti. Nepotpuni izvodi ne spajaju se samo po sličnosti sadržaja. Slični naslovi i skraćeni nazivi poslodavaca idu na proveru. Oglasi bez poslodavca spajaju se samo uz potvrđen originalni link. Svaka verzija i izvorni link ostaju sačuvani. Komanda `deduplicate` poredi i ranije sačuvane oglase bez menjanja njihovih datuma preuzimanja. Grupisanje ne garantuje prepoznavanje svih duplikata, posebno kod agencija i skraćenih opisa.

Istek se prikazuje samo na osnovu objavljenog roka. Nestanak iz liste ili neuspeh sajta ne briše i ne proglašava oglas isteklim. Za oglase bez roka pogledati `last_seen`.

## Svaki pun sat

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-schedule.ps1
Get-ScheduledTaskInfo -TaskName Petrovaradin-Oglasi-Hourly
```

Windows Task Scheduler pokreće lokalni program svakog punog sata, svakog dana, počev od narednog sata u vremenskoj zoni računara. Nema lozinke u skripti. Trenutna postavka radi dok je korisnik prijavljen i računar uključen; posle propuštenog termina koristi `StartWhenAvailable`. Za neprekidan rad i kada je računar isključen potreban je stalno dostupan server.

Preklapanje sprečavaju Task Scheduler i procesna blokada baze; ista blokada štiti i komandu `deduplicate`. Maksimalno trajanje raspoređenog zadatka je 55 minuta. Potpun prvi prolaz velikih izvora može zahtevati više vremena; pratiti status i limit `max_pages` (100 po izvoru). Četiri izvora se obrađuju paralelno (`workers`), a upisi u bazu serijalizuju. Jedan sajt ne zaustavlja obradu ostalih. Poznati oglasi se osvežavaju na 24h, a prisustvo u listi na svakom prolazu. Uspešno provereni oglasi van područja i demo oglasi takođe se keširaju na 24h; greške se ne keširaju kao uspeh. Razmak zahteva prema izvoru je najmanje 2 sekunde, uz robots.txt crawl delay. Protego pravilno tumači wildcard/query robots pravila, a preusmeravanja proveravaju i pravila odredišta. Nedostupni izvori i promene parsera beleže se u bazi i dnevnom logu `logs/YYYY-MM-DD.log`. U ovoj verziji nema automatskog slanja obaveštenja.

Isključivanje rasporeda:

```powershell
Disable-ScheduledTask -TaskName Petrovaradin-Oglasi-Hourly
```

## Razvoj

Prva grana je `add/oglasi`. Naredne popravke redom: `fix/oglasi-001`, `fix/oglasi-002`, itd. Baza, logovi i virtuelno okruženje nisu za Git.
