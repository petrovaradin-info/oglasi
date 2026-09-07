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
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Podaci su u `data/oglasi.sqlite3`, JSON u `data/oglasi.json`. Putanje su vezane za projekat, ne trenutni terminal. Primer filtriranja:

```powershell
.\venv\Scripts\python.exe main.py export --location Petrovaradin
.\venv\Scripts\python.exe main.py export --facet category --value IT
.\venv\Scripts\python.exe main.py collect --source nsz --max-details 3
```

Probni limit vraća status `partial` i izlazni kod 2 jer pretraga nije kompletna. Kod 0 znači da su aktivni izvori u tom prolazu obrađeni bez prijavljenog problema; ne predstavlja garanciju da izvor prikazuje sve postojeće oglase.

## Izvori i obuhvat

`sources.json` je proširiv registar. Uključeni su svi početno zadati portali, uz NSZ, KlikDoPosla, Kariera, Bulevar i Mjob. Dodatni kandidati su Startuj, javni/interni konkursi Novog Sada i NSZ PDF publikacija. Njihovi posebni adapteri još nisu urađeni; spisak nije tvrdnja da su svi relevantni izvori na internetu obuhvaćeni.

- HelloWorld, Infostud, Halo oglasi, Oglasi.rs, Poslovi.rs: HTML/JobPosting adapteri.
- NSZ: posebna struktura oglasa, filter mesta 155 (Novi Sad) i 167 (Sremski Karlovci), uključujući ćirilicu.
- Lako do posla: javni API koji koristi njihov sajt. Preuzimaju se isključivo potrebna polja oglasa; podaci o korisničkim nalozima se ne čuvaju.
- KlikDoPosla: JobPosting; Kariera: JobPosting ili zapis sa linkom ka originalu i oznakom da opis nedostaje.
- Bulevar: adapter javnog Wix šablona. Izmena šablona zahteva ažuriranje selektora.
- Jooble: robots.txt odbija pretragu, a direktna provera vraća 403. Za aktivno prikupljanje potreban je dozvoljeni API/feed.
- Mjob: javni API sa paginacijom, opisom, potrebnim veštinama, satnicom, smenama i odvojenim gradom/mestom rada. Originalni link vodi na stranicu oglasa.

Svi pronađeni oglasi ponovo prolaze filter stvarnog mesta rada. Naziv grada u navigaciji i adresa sedišta poslodavca iz JobPosting-a ne koriste se kao mesto rada. Kada strukturirana lokacija nedostaje, lokacija se izvodi iz naslova/opisa i označava `location_from_text`; to je manje pouzdano. Naselja grada Novog Sada (Futog, Veternik, Sremska Kamenica, itd.) mapiraju se na filter Novi Sad uz očuvanu izvornu lokaciju, prema [spisku JKP Informatika](https://www.novisadinvest.rs/cyr/broj-stanovnika-po-naseljima). Petrovaradin ostaje poseban filter. Remote oglasi bez lokalne lokacije trenutno se ne uključuju.

## Polja i grupisanje

Naslov, poslodavac, opis, izvorni URL, lokacije, datum objave, rok, prvi/poslednji put viđen i vreme poslednjeg preuzimanja čuvaju se za svaki izvor. Izvorna strukturirana polja obuhvataju ugovor, radno vreme, model rada, kategoriju, veštine, obrazovanje, iskustvo, benefite, platu i broj izvršilaca kada ih izvor daje. NSZ/Poslovi dodatna polja ostaju u `structured.source_fields`. Lako do posla i Bulevar imaju odvojene sekcije uslova/opisa/ponude gde postoje.

Izvedene kategorije, veštine i tipovi rada nose `method: keyword` i `review_required: true`; mogu imati greške, naročito kod negacija. Nepoznato ostaje prazno. Novac se ne pretvara u izmišljenu mesečnu zaradu: čuvaju se izvorna vrednost, valuta/jedinica kada postoje.

Isti URL se ažurira bez novog oglasa. Automatska grupa zahteva istog normalizovanog poslodavca i naslov, isti skup lokalnih lokacija, datume objave unutar 30 dana i najmanje 85% sličnosti dovoljno dugog opisa. Slični naslovi sa istim poslodavcem/lokacijom dobijaju kandidata za proveru. Oglasi bez poslodavca se ne spajaju automatski. Svaka verzija i originalni link ostaju sačuvani. Grupisanje je namerno konzervativno i neće pronaći sve duplikate, posebno oglase agencija bez identiteta krajnjeg poslodavca.

Istek se prikazuje samo na osnovu objavljenog roka. Nestanak iz liste ili neuspeh sajta ne briše i ne proglašava oglas isteklim. Za oglase bez roka pogledati `last_seen`.

## Svaki pun sat

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-schedule.ps1
Get-ScheduledTaskInfo -TaskName Petrovaradin-Oglasi-Hourly
```

Windows Task Scheduler pokreće lokalni program svakog punog sata, svakog dana, počev od narednog sata u vremenskoj zoni računara. Nema lozinke u skripti. Trenutna postavka radi dok je korisnik prijavljen i računar uključen; posle propuštenog termina koristi `StartWhenAvailable`. Za neprekidan rad i kada je računar isključen potreban je stalno dostupan server.

Preklapanje sprečavaju Task Scheduler i procesna blokada baze. Maksimalno trajanje zadatka je 55 minuta. Potpun prvi prolaz velikih izvora može zahtevati više vremena; pratiti status i limit `max_pages` (100 po izvoru). Jedan sajt ne zaustavlja obradu ostalih. Poznati oglasi se osvežavaju na 24h, a prisustvo u listi na svakom prolazu. Razmak zahteva je najmanje 2 sekunde, uz robots.txt crawl delay. Nedostupni izvori i promene parsera beleže se u bazi i dnevnom logu `logs/YYYY-MM-DD.log`. U ovoj verziji nema automatskog slanja obaveštenja.

Isključivanje rasporeda:

```powershell
Disable-ScheduledTask -TaskName Petrovaradin-Oglasi-Hourly
```

## Razvoj

Prva grana je `add/oglasi`. Naredne popravke redom: `fix/oglasi-001`, `fix/oglasi-002`, itd. Baza, logovi i virtuelno okruženje nisu za Git.
