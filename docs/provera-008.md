# Provera pre objave — 9. oktobar 2026.

Grana fix/oglasi-008 nastavlja commit 5be054d sa fix/oglasi-007.
Lokalni master u trenutku početka nije sadržao taj commit.

Na sačuvanoj bazi, bez novog sakupljanja i bez menjanja grupa:

- 881 oglas u javnom izvozu.
- 55 neisteklih grupa zahteva proveru spajanja.
- 85 grupa bez roka nema dovoljno svež pronalazak.
- 216 kandidatskih parova između izvora uključuje bar jednu neisteklu grupu.

U 55 spornih grupa postoje 95 problematičnih parova: 87 mogućih ponovljenih
konkursa istog izvora i 8 parova sa datumima udaljenim više od 30 dana.
Primer je grupa 31: Mjob „Rad u magacinu“, objave 3. septembra,
17. septembra i 8. oktobra. Jednak tekst ne potvrđuje isti konkurs.

Među 216 međusobno nespojenih kandidata između izvora: 121 par ima sličan
naslov i poslodavca ali nedovoljno dokaza, 70 ima udaljene datume, a 25 skraćen
naziv poslodavca. Najviše parova je NSZ/OglasZaPosao (42),
Infostud/OglasZaPosao (27), Infostud/Poslovi (16), HelloWorld/Infostud (14).
Ovo su prioriteti za pregled, ne potvrđeni duplikati.

Novi `main.py review` pravi HTML i JSON sa izvornim linkovima, datumima,
punim opisima i razlozima. Automatsko razdvajanje ili spajanje nije izvršeno.
Nije sprovedena pojedinačna potvrda svih ovih parova na živim sajtovima.

Validacija: 65 testova prolazi, uključujući letnje/zimsko vreme i dane promene
sata, tačnu granicu roka, korišćenje jednog vremena za javni izvoz, neizmenjivost
baze tokom pregleda i HTML escaping sadržaja izvora. Generisani su javni JSON,
HTML baze i novi pregled. Brojevi važe za ovaj snimak i mogu se promeniti
nakon sakupljanja ili isteka rokova.


## Završna provera — 10. oktobar 2026.

Sve izmene fix/oglasi-008 su sačuvane i još nisu commitovane. Ponovo je prošlo
65 testova; pip check i git diff --check nemaju grešaka. Obnovljeni su javni
JSON, HTML baze i HTML/JSON za proveru, bez novog sakupljanja.

Današnji snimak: 850 javnih oglasa, 48 spornih grupa, 85 grupa
bez svežeg pronalaska i 210 kandidatskih parova između izvora. Brojevi iz
prethodnog odeljka ostaju istorijski snimak od 9. oktobra. Proverena je
jedinstvenost javnih ID-jeva i slaganje broja HTML kartica sa JSON pregledom.
