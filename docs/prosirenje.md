# Proširenje sakupljača poslova — 11.09.2026.

Osam traženih izvora dodato je u registar. Svaki zapis sadrži originalni URL, kvalitet podataka i rezultat obrade. Novi adapteri automatski ulaze u postojeći raspored.

| Izvor | Pristup i obuhvat |
| --- | --- |
| Adorio | Dozvoljena lista `https://www.adorio.rs/posao/novi-sad`. Robots.txt zabranjuje `/oglas-za-posao/` i sve query URL-ove. Čuvaju se samo dostupni izvodi prve liste, sa oznakom `description_incomplete`; obuhvat je `partial`. |
| Joberty | Javni API koji koristi sajt: `https://backend.joberty.com/api/v1/jobs`. Paginacija počinje od 0; korisnikov link ka četvrtoj stranici nije početak sakupljanja. Za svaki oglas preuzima se opis iz API detalja i proverava lista gradova. Slike, korisnički podaci i zastavice naloga se ne čuvaju. |
| Careerjet | Korisnikova pretraga vraća verifikacionu stranicu. Adapter prepoznaje blokadu kao `access_verification_required`; ne proglašava je praznom uspešnom pretragom i ne pokušava da zaobiđe verifikaciju. |
| Šljaka | HTML lista sa lokalnim filterom; podržani su slug URL-ovi i WordPress `post_type=noo_job&p=...` URL-ovi. Datumi i lokacija uzimaju se iz metapodataka samog oglasa, ne iz spiska sličnih poslova. |
| OglasZaPosao | Sve dostupne stranice lokalne liste. Obrađuju se i JobPosting i HTML varijanta; preneti izvodi imaju oznaku nepotpunog opisa i link na original. |
| Manpower | Korisnikov `location=68803` je Južnobački okrug. Dodat je `68827` za Novi Sad. Sama oznaka okruga nije dovoljna za čuvanje; proverava se stvarno mesto rada. Ako krajnji poslodavac nije naveden, ne izmišlja se ime poslodavca. |
| PAZ | Javni oglasi iz lokalne liste. Oznaka `.hua-synthetic-demo-notice` isključuje demonstracione oglase iz baze. |
| SBU | Lista nije lokalno filtrirana. Paginacija prati javni `jobsearch_jobs_content` zahtev na izričito dozvoljenom `wp-admin/admin-ajax.php`. Zahtev samo pretražuje oglase; ne šalje prijave ni poruke. Mesto rada proverava se u svakom detalju. Ako mapa prikazuje adresu agencije, a naslov i opis se slažu oko lokalnog mesta rada (ili opis izričito navodi mesto rada), koristi se navedeno mesto i čuva oznaka `location_conflict_review` sa originalnim podatkom mape. |

Biblioteka Protego zamenjuje `urllib.robotparser`, koji je pogrešno tretirao SBU pravilo `Disallow: /?` kao opštu zabranu. Prava zabrana Adorio detalja i paginacije ostaje poštovana. Referenca: [Protego](https://github.com/scrapy/protego).

## Pokretanje i pregled

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe main.py collect --source adorio --source joberty --source careerjet --source sljaka --source oglaszaposao --source manpower --source paz --source sbu --workers 4
.\venv\Scripts\python.exe main.py deduplicate
.\venv\Scripts\python.exe main.py export
.\venv\Scripts\python.exe main.py report
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

`--source` se može ponoviti; bez njega rade svi registrovani izvori. `--max-details N` je samo probni limit po izvoru i daje `partial` ako je obrada skraćena. Četiri paralelna izvora koriste zasebne konekcije, uz serijalizovane upise i jednu procesnu blokadu baze. Obrada iste stranice se ne deli na paralelne zahteve.

`--refresh` zanemaruje starost keša za izabrane izvore, korisno posle popravke parsera. Primer: `python main.py collect --source sbu --refresh`.

SQLite: `data/oglasi.sqlite3`. Pregled: `data/oglasi-pregled.html`, samostalan lokalni fajl sa pretragom, filterima, grupama i parovima za proveru. JSON: `data/oglasi.json`, jedna stavka po grupi sa svim izvornim objavama. HTML je snimak; obnoviti ga komandom `report`. Za direktne SQL upite u PyCharm Database prozoru izabrati SQLite i ovu bazu (ako izdanje PyCharm-a podržava tu funkciju).

Primeri SQL upita:

```sql
SELECT source, COUNT(*) AS oglasi FROM ads GROUP BY source ORDER BY oglasi DESC;
SELECT COUNT(*) AS izvorne_objave, COUNT(DISTINCT group_id) AS grupe FROM ads;
SELECT group_id, COUNT(*) AS objave FROM ads GROUP BY group_id HAVING COUNT(*) > 1;
SELECT url_a, url_b, score, reason FROM candidates ORDER BY score DESC;
```

Pre izmene lokalne baze napravljena je SQLite backup kopija `data/oglasi-before-expansion-20260911-134942.sqlite3`. Baza, kopije, probni HTML i logovi nisu za Git. Commit i push radi korisnik.

## Duplikati

Svi novi/izmenjeni oglasi porede se sa postojećim zapisima. `deduplicate` ponavlja poređenje i za prethodno sačuvane objave bez menjanja sadržaja, istorije i vremena preuzimanja. Pouzdana poklapanja dobijaju istu grupu; ne brišu se izvorne objave. Izvoz i pregled prikazuju grupu samo jednom.

Pored sadržaja koristi se originalni link prenetog oglasa. Isti naslov sam po sebi nije dokaz duplikata: dve firme mogu tražiti „Prodavca“, a isti poslodavac može ponoviti konkurs mesecima kasnije. Skraćeni nazivi poslodavca i opisi ostaju parovi za proveru. Ručna provera je potrebna za preostale neizvesne duplikate.

## Predlozi narednih poboljšanja

1. **Pregled kandidata za spajanje** sa akcijama „isti oglas“ / „različiti oglasi“, trajnim odlukama i mogućnošću poništavanja. To je najvažnije za Adorio i agencijske oglase.
2. **Dogovoren API/feed** za Careerjet i potpun Adorio obuhvat. Dodavanje URL-a u registar ne otklanja zabranu ili verifikaciju.
3. **Nastavak prekinutog prolaza i status u toku**. Sačuvati red neobrađenih URL-ova i evidentirati prekid zadatka da poslednji stari uspešan rezultat ne izgleda kao trenutni rezultat. Važno zbog Windows ograničenja od 55 minuta.
4. **Jasan prikaz starosti i rokova**: odvojiti potvrđeno aktivne, istekle i oglase nepoznatog roka; nestanak ili mrežna greška ne smeju automatski obrisati oglas.
5. **Upozorenje kada se izvor pokvari**, npr. nagli pad pronađenih oglasa ili ponovljene parser greške. Ne slati obaveštenja pri svakom rutinskom prolazu.
6. **Više radnih mesta u jednom konkursu**: sačuvati roditeljski konkurs i povezati pojedinačne pozicije, umesto da se višepozicijski NSZ/Šljaka konkurs prikazuje kao jedan ogroman naslov.
