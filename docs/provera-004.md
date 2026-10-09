# Provera fix/oglasi-004 — 11.09.2026.

Završni prolazi na lokalnoj bazi. Broj sačuvanih zapisa uključuje osvežavanje, nije broj novih oglasa.

| Izvor | Status | Stranice | Upisi | Keš | Preskočeni |
|---|---|---:|---:|---:|---:|
| halo | ok | 2 | 0 | 23 | 0 |
| infostud | ok | 25 | 7 | 464 | 0 |
| kariera | ok | 2 | 9 | 10 | 0 |
| lako | ok | 4 | 0 | 8 | 12 |

Baza: 2361 izvornih zapisa, 2328 grupa. SQLite integrity_check: ok. Testovi: 45 prolazi.

Pregledano je 616 kandidatskih parova prema postojećim pravilima. To nisu potvrđeni duplikati:
- same_employer_location_similar_title; needs_review: 385
- similar_job_different_dates: 207
- truncated_employer_similar_title_location; needs_review: 24

Nisu masovno spojeni kandidati sa različitim datumima ili nepotpunim opisima. HTML pregled sada prikazuje naslove, poslodavce, lokacije, datume i oba opisa; procenat sličnosti nije verovatnoća duplikata.

Infostud: uklonjena nevažeća putanja Petrovaradina koja vraća opštu pretragu; obuhvat Petrovaradina ostaje kroz Novi Sad + 15 km. Parser prestaje na dodatnoj ponudi bez filtera i odbija opšti naslov Posao. Završena lokalna pretraga na 25 stranica, bez povećavanja opšteg limita.

LakoDoPosla: HTTP 404/410 na detaljima označava nedostupan oglas i kešira se 24h; ostale greške ostaju prijavljene. Halo priznaje eksplicitnu praznu pretragu. Kariera koristi javni formular umesto nepostojeće gradske putanje.

Jooble i Careerjet i dalje zahtevaju dozvoljen pristup. Adorio ostaje delimičan izvor. Istorijski oglasi nisu brisani.

Grana je krenula od starije verzije: prenet je sadržaj a10b461 bez commita. Pri commitovanju uključiti i nove (untracked) module, dokumentaciju i testove.
