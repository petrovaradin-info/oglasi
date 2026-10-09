import csv
import tempfile
import unittest
from pathlib import Path
from oglasi.platform_export import cards, salary, write_csv


class PlatformExportTests(unittest.TestCase):
    def test_card_is_small_and_keeps_all_sources(self):
        ad=dict(title='Developer',employer='Acme',locations=['Novi Sad'],description='Opis posla. '*80,
                quality='structured',posted='2026-09-01',expires='',expired=False,
                source='a',url='https://a.rs/job/1',structured={'original_url':'javascript:alert(1)'})
        group={'group_id':12,'sources':[ad,{**ad,'source':'b','url':'https://b.rs/job/1'}]}
        row=cards([group])[0]
        self.assertEqual(row['kategorija'],'Posao');self.assertEqual(row['link'],ad['url'])
        self.assertLessEqual(len(row['opis']),280);self.assertEqual(len(row['izvori']),2)
        self.assertEqual(row['kontakt_email'],'');self.assertEqual(row['slika_url'],'')
        self.assertEqual(len(cards([group],exclude_expired=True)),1)
        for a in group['sources']:a['expired']=True;a['expires']='2000-01-01'
        self.assertEqual(cards([group],exclude_expired=True),[])

    def test_salary_keeps_currency_and_period_and_does_not_invent_values(self):
        self.assertEqual(salary({}),'')
        self.assertEqual(salary({'baseSalary':{'currency':'RSD','value':{'minValue':80000,'maxValue':100000,'unitText':'MONTH'}}}),'80000–100000 RSD MONTH')

    def test_csv_round_trip_and_formula_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'test.csv'
            write_csv(p,[{'naslov':'=1+1','opis':'č;ć\nž','izvori':[]}])
            with p.open(encoding='utf-8-sig',newline='') as handle:row=next(csv.DictReader(handle,delimiter=';'))
            self.assertEqual(row['naslov'],"'=1+1");self.assertEqual(row['opis'],'č;ć\nž')
