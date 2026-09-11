# Izvori i kandidati — pregled pre proširenja

Ovo je istorijski pregled napravljen pre integracije druge grupe izvora. Registar sada ima 20 izvora; aktuelni obuhvat i ograničenja opisani su u [prosirenje.md](prosirenje.md).

Provera: 11.09.2026. Aktivni registar `sources.json` ima 12 izvora. Sakupljač pokušava da obradi svaki od njih, ali unos u registru ne znači da pristup i parser trenutno rade bez greške. Oglasi se filtriraju na Petrovaradin, Novi Sad i Sremske Karlovce (uz naselja grada Novog Sada).

Za svaki postojeći izvor ispod je jedan novi, različit sajt koji nije bio ni u aktivnom registru ni među ranije navedenim kandidatima. Sličnost je po tipu oglasa ili ciljnoj grupi; nije tvrdnja da su sadržaj ili pokrivenost jednaki.

| Postojeći izvor | Novi kandidat | Sličnost i nalaz |
| --- | --- | --- |
| HelloWorld (`helloworld`) | [Joberty](https://www.joberty.com/sr/IT-jobs?location=Serbia&page=4&sort=created&trk=public_post-text) | IT poslovi; u rezultatima su i pozicije za Novi Sad. Potrebna provera javnog pristupa i dinamičkog učitavanja. |
| Infostud (`infostud`) | [Adorio](https://www.adorio.rs/posao/novi-sad) | Više zanimanja, posebna lista za Novi Sad; prenosi i oglase drugih izvora, pa očekivati duplikate. |
| Jooble (`jooble`) | [Careerjet](https://www.careerjet.rs/about-us) | Pretraživač/agregator poslova; pre integracije proveriti lokalnu pretragu i dozvoljen API/feed. |
| Halo oglasi (`halo`) | [KupujemProdajem – Poslovi](https://www.kupujemprodajem.com/poslovi/kategorija/2546) | Opšti oglasnik sa poslovima i izborom mesta; ima oglase za Novi Sad. |
| Lako do posla (`lako`) | [Šljaka](https://sljaka.com/) | Portal za različite struke; prikazuje i oglase za Novi Sad. |
| Oglasi.rs (`oglasi`) | [OglasZaPosao](https://oglaszaposao.rs/lokacija/novi-sad/) | Lokalni oglasi, uključujući zanatske poslove; posebna stranica za Novi Sad. |
| Poslovi.rs (`poslovi`) | [Manpower Srbija](https://www.manpower.rs/sr/job-posts?job_list_type=&page=1) | Oglasi za različita zanimanja preko agencije; Novi Sad među lokacijama. |
| NSZ (`nsz`) | [SUK – Kutak za kandidate](https://kutak.suk.gov.rs/karijera) | Državni konkursi, uži obuhvat od NSZ. Potrebni filter mesta rada i obrada uslova konkursa/dokumenata. |
| KlikDoPosla (`klikdoposla`) | [PAZ.rs](https://paz.rs/sr-latn/poslovi/novi-sad/) | Poslovi u više delatnosti kod lokalnih i kineskih kompanija; lokalna lista za Novi Sad. |
| Kariera (`kariera`) | [Adecco](https://www.adecco.com/sr-rs/poslovi/menader-prodaje-industrijske-opreme-novi-sad-/jn-022026-974350) | Profesionalne pozicije i agencijsko zapošljavanje; pronađen primer oglasa za Novi Sad. Primer nije garancija da je konkurs još otvoren. |
| Bulevar (`bulevar`) | [OZ Tragač](https://oztragac.com/ponuda) | Omladinska zadruga, navodi pokrivanje Novog Sada. Proveriti aktuelnu listu i dostupnost pojedinačnih oglasa. |
| Mjob (`mjob`) | [SBU Poslovi](https://sbu-poslovi.rs/oglasi-za-posao/) | Studentski/omladinski poslovi; navodi i poslodavca iz Novog Sada. |

Ovo su pronađeni kandidati, **nisu novi aktivni adapteri**. Pre uključivanja proveriti robots.txt/dozvoljeni pristup, paginaciju, originalni URL, stvarno mesto rada, rok i opis, zatim testirati parser. Za prve integracije predlog su Šljaka, OglasZaPosao i SBU zbog lokalnih oglasa, a potom Joberty za IT. Agregatori mogu dati mnogo već postojećih oglasa.

Raniji kandidati ostaju: Startuj Infostud, Skupština Novog Sada, Gradska poreska uprava Novi Sad i NSZ PDF publikacija „Poslovi“. Za njih još nema posebnih adaptera.

## Zatečeno stanje lokalne baze

Poslednji zabeleženi rezultati pregledani 11.09.2026. nisu novi kompletni test svih portala. Većina je iz 09.09, HelloWorld iz 11.09. Uspeh (`ok`) imaju HelloWorld, Oglasi.rs, Poslovi.rs, NSZ, KlikDoPosla, Bulevar i Mjob. Infostud, Lako do posla i Kariera imaju delimične rezultate; Halo i Jooble imaju greške. Zabeleženi problemi uključuju DNS nedostupnost, HTTP 404 i blokadu pristupa. Raspored sam po sebi ne otklanja ove probleme.

Na svakom prolazu se proveravaju liste. Poznati oglasi se detaljno osvežavaju na 24 sata (`refresh_hours`), uz ažuriranje prisustva na svakom prolazu; Mjob koristi podatke iz liste i osvežava ih na svakom prolazu. SQLite čuva podatke i status po izvoru. `main.py status` prikazuje poslednje rezultate.
