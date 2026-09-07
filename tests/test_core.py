import json
import tempfile
import unittest
from unittest.mock import Mock
from pathlib import Path
from oglasi.model import Job, norm, locations, canonical, enrich
from oglasi.parsers import listing, detail, lako_detail, mjob_detail
from oglasi.store import Store
from oglasi.collector import Client

class CoreTests(unittest.TestCase):
    def test_serbian_locations(self):
        self.assertEqual(locations('Петроварадин; Нови Сад; Сремски Карловци'),['Novi Sad','Petrovaradin','Sremski Karlovci'])
        self.assertEqual(locations('Novi Beograd'),[])
        self.assertEqual(locations('Ветерник; Футог'),['Novi Sad'])
        self.assertEqual(norm('Đorđe'),norm('Ђорђе'))

    def test_url_identity(self):
        self.assertEqual(canonical('https://x.rs/job?id=12&utm_source=a#x'),'https://x.rs/job?id=12')
        self.assertNotEqual(canonical('https://x.rs/job?id=12'),canonical('https://x.rs/job?id=13'))

    def test_listing_onclick_pagination(self):
        html='''<div onclick="document.location.href='https://x.rs/preview/123'">Job</div><a href="?place=155&page=2">2</a><a href="https://evil.rs/preview/456">bad</a>'''
        jobs,pages=listing(html,'https://x.rs/search?place=155&page=1',{'detail_pattern':r'/preview/\d+'})
        self.assertEqual(list(jobs),['https://x.rs/preview/123'])
        self.assertEqual(pages,['https://x.rs/search?place=155&page=2'])

    def test_structured_location_excludes_headquarters(self):
        schema={'@type':'JobPosting','title':'Developer','description':'Python developer needed','jobLocation':{'address':{'addressLocality':'Beograd'}},'hiringOrganization':{'name':'Acme','address':{'addressLocality':'Novi Sad'}}}
        html='<script type="application/ld+json">'+json.dumps(schema)+'</script><footer>Novi Sad</footer>'
        job=detail(html,'https://x.rs/job/1',{'id':'test'})
        self.assertEqual(job.locations,[])
        self.assertEqual(job.facets['skills']['values'],['Python'])

    def test_full_description_over_schema_teaser(self):
        html='<h1>Developer</h1><div class="body">Python SQL Novi Sad full description</div><script type="application/ld+json">{"@type":"JobPosting","title":"Truncated...","description":"Teaser"}</script>'
        job=detail(html,'https://x.rs/1',{'id':'test','description_selector':'.body'})
        self.assertIn('full description',job.description)
        self.assertEqual(job.title,'Developer')

    def test_description_sections(self):
        html='<h1>Kuvar</h1><div class="body"><p><strong>Uslovi:</strong></p><ul><li>Iskustvo</li></ul><h3>Nudimo</h3><p>Obuku</p></div>'
        job=detail(html,'https://x.rs/1',{'id':'test','description_selector':'.body'})
        self.assertEqual(job.structured['sections'],{'Uslovi':'Iskustvo','Nudimo':'Obuku'})

    def test_contract_types_do_not_confuse_substrings(self):
        job=enrich(Job('s','url','Kuvar',description='Ugovor na neodređeno.'))
        self.assertEqual(job.facets['contract_type']['values'],['neodređeno'])

    def test_lako_allowlist_and_sections(self):
        data={'positionTitle':'Prodavac','employerName':'Acme','employer':{'password':'must-never-be-stored'},'locationName':'Novi Sad','jobDescription':'<p>Opis</p>','conditionsDescription':'Excel','date':'01.09.2026','expiryDate':'30.09.2026'}
        j=lako_detail(data,'https://www.lakodoposla.com/oglasi/test-1')
        self.assertEqual(j.expires,'2026-09-30')
        self.assertNotIn('password',json.dumps(j.dict()))
        self.assertEqual(j.structured['sections']['conditionsDescription'],'Excel')

    def test_lako_pagination_keeps_location(self):
        data={'data':[{'slug':'test-1','positionTitle':'Test'}],'meta':{'hasMorePages':True}}
        jobs,pages=listing(json.dumps(data),'https://prod.lakodoposla.net/api/postings?locations=99&page=1',{'id':'lako'})
        self.assertEqual(pages,['https://prod.lakodoposla.net/api/postings?locations=99&page=2'])
        self.assertIn('https://www.lakodoposla.com/oglasi/test-1',jobs)

    def test_missing_description_is_not_silent_success(self):
        with self.assertRaises(ValueError):detail('<h1>Job</h1>','https://x/1',{'id':'test'})

    def test_mjob_city_and_salary(self):
        j=mjob_detail({'title':'Prodavac','company':{'name':'Zadruga'},'information':{'location':'TC Big','workPlace':{'item':{'name':'Novi Sad'}},'payment':{'netHourlyRate':430},'description':'Rad u butiku'}},'https://www.mjob.rs/poslovi-za-studente/informacije/1')
        self.assertEqual(j.locations,['Novi Sad'])
        self.assertEqual(j.structured['baseSalary'],{'netHourlyRate':430})

    def test_mjob_empty_404(self):
        client=Client(delay=0)
        response=Mock(status_code=404)
        response.json.return_value={'jobs':[],'total':0,'page':1}
        client.session.get=Mock(return_value=response)
        data=json.loads(client.request('https://www.mjob.rs/api/jobs?search=Petrovaradin'))
        self.assertEqual(data['total'],0)
        response.raise_for_status.assert_not_called()

    def test_failed_source_does_not_expire_ads(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            store.save(Job('s','https://x/1','Job',locations=['Novi Sad']))
            store.record('s','2026-09-01','error',{'error':'HTTP 403'})
            self.assertFalse(store.export()[0]['sources'][0]['expired'])
            store.close()

    def test_dedup_history_and_missing_employer(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            def job(url,employer='Acme',posted='2026-09-01'):
                return Job('test',url,'Python developer',employer,'A detailed job description. '*12,['Novi Sad'],posted=posted)
            a=job('https://a/1');g=store.save(a)
            self.assertEqual(store.save(job('https://b/1')),g)
            self.assertNotEqual(store.save(job('https://c/1','Other')),g)
            self.assertNotEqual(store.save(job('https://d/1','')),g)
            self.assertNotEqual(store.save(job('https://e/1',posted='2025-01-01')),g)
            store.save(a)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM versions WHERE url=?',(a.url,)).fetchone()[0],1)
            a.description+='Changed';store.save(a)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM versions WHERE url=?',(a.url,)).fetchone()[0],2)
            self.assertTrue(store.fresh(a.url))
            store.close()

if __name__=='__main__':unittest.main()
