import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from oglasi.collector import collect, FetchError
from oglasi.parsers import empty_listing, listing
from oglasi.store import Store
from oglasi.model import Job
from oglasi.report import render


class ReliabilityTests(unittest.TestCase):
    def test_infostud_stops_before_unfiltered_suggestions(self):
        source={'id':'infostud','detail_pattern':'/posao/'}
        with self.assertRaisesRegex(ValueError,'unfiltered'):
            listing('<h1>Posao</h1><a href="/posao/other/2">Job</a>','https://x.rs/petrovaradin',source)
        html='<h1>Posao Novi Sad</h1><h2>Local job</h2><a href="/posao/local/1">Local</a><h2><span>Dodatna ponuda poslova</span></h2><a href="/posao/other/2">Other city</a><a href="?page=79">79</a>'
        found,pages=listing(html,'https://x.rs/list?page=20',source)
        self.assertEqual(list(found),['https://x.rs/posao/local/1']);self.assertEqual(pages,[])
        found,pages=listing('<h2>Local job</h2><a href="/posao/local/1">Job</a><a href="?page=2">2</a>','https://x.rs/list',source)
        self.assertEqual(len(found),1);self.assertEqual(pages,['https://x.rs/list?page=2'])
        self.assertTrue(empty_listing('<div><h1>Posao</h1><p>(0 rezultata)</p></div>',source))

    def test_review_shows_both_ads_without_rendering_their_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(Path(tmp)/'test.db')
            for source,desc in [('one','First <script>alert(1)</script>'),('two','Second description')]:
                s.save(Job(source,'https://'+source+'.rs/job','Developer','Acme',desc,['Novi Sad'],posted='2026-09-11'))
            html=render(s)
            self.assertIn('Uporedi opis',html);self.assertIn('Objavljeno: 2026-09-11',html)
            self.assertIn('nije verovatnoća duplikata',html)
            self.assertNotIn('<script>alert(1)</script>',html)
            s.close()

    def test_empty_search_requires_explicit_evidence(self):
        self.assertTrue(empty_listing('<p class="no-res-header">Trenutno nema rezultata za zadati pojam pretrage.</p>',{'id':'halo'}))
        self.assertFalse(empty_listing('<h1>Service unavailable</h1>',{'id':'halo'}))
        self.assertTrue(empty_listing(json.dumps({'data':[],'meta':{'totalItems':0}}),{'id':'lako'}))
        self.assertFalse(empty_listing(json.dumps({'data':[],'meta':{'totalItems':5}}),{'id':'lako'}))

    def test_source_page_limit_overrides_default(self):
        class Client:
            def __init__(self,*args):pass
            def listing_page(self,url,source):
                return '<a rel="next" href="?page=2">Next</a>' if 'page=2' not in url else ''
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(Path(tmp)/'test.db')
            cfg={'max_pages':1,'sources':[{'id':'test','urls':['https://x.rs/list'],'detail_pattern':'/job/','allow_empty':True,'max_pages':2}]}
            with patch('oglasi.collector.Client',Client):r=collect(s,cfg)[0]
            self.assertEqual(r['pages'],2);self.assertEqual(r['status'],'ok')
            cfg['sources'][0]['max_pages']=1
            with patch('oglasi.collector.Client',Client):r=collect(s,cfg)[0]
            self.assertEqual(r['status'],'partial');self.assertEqual(r['limit_reason'],'page_limit');self.assertEqual(r['remaining_pages'],1)
            s.close()

    def test_missing_lako_detail_is_cached_but_server_error_is_not(self):
        class Client:
            code=404
            def __init__(self,*args):pass
            def listing_page(self,*args):return json.dumps({'data':[{'slug':'job-1','positionTitle':'Job'}],'meta':{}})
            def get(self,*args):raise FetchError('Unavailable',self.code)
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(Path(tmp)/'test.db');cfg={'sources':[{'id':'lako','urls':['https://x.rs/list']}]}
            with patch('oglasi.collector.Client',Client):
                r=collect(s,cfg)[0];self.assertEqual(r['skipped'],1);self.assertEqual(r['errors'],[])
                self.assertEqual(collect(s,cfg)[0]['excluded_cached'],1)
                s.db.execute('delete from excluded');s.db.commit();Client.code=503
                self.assertEqual(len(collect(s,cfg)[0]['errors']),1)
                self.assertEqual(s.db.execute('select count(*) from excluded').fetchone()[0],0)
            s.close()
