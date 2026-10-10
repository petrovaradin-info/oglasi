import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from oglasi.model import Job
from oglasi.store import Store
from oglasi.review import review_document, render_review
from oglasi.lifecycle import deadline_instant, group_state
from oglasi.publication import publication_state, public_document

class ReviewTests(unittest.TestCase):
    def test_belgrade_winter_summer_and_dst(self):
        for date, expected in (
            ('2026-01-15','2026-01-15T23:00:00+00:00'),
            ('2026-07-15','2026-07-15T22:00:00+00:00'),
            ('2026-03-29','2026-03-29T22:00:00+00:00'),
            ('2026-10-25','2026-10-25T23:00:00+00:00'),
            ('2026-07-15T12:00:00','2026-07-15T10:00:00+00:00'),
            ('2026-07-15T12:00:00-04:00','2026-07-15T16:00:00+00:00')):
            self.assertEqual(deadline_instant(date).isoformat(),expected)
        for bad in (123, {}, None, '9999-12-31'):
            self.assertIsNone(deadline_instant(bad))

    def test_supplied_time_controls_deadline_and_public_card(self):
        ad=Job('a','https://a.rs/1','Job','Acme','Description',['Novi Sad'],expires='2026-01-01').dict()
        ad['expired']=True
        before=datetime(2026,1,1,22,tzinfo=timezone.utc)
        end=datetime(2026,1,1,23,tzinfo=timezone.utc)
        self.assertTrue(publication_state([ad],before)['vidljiv'])
        self.assertEqual(group_state([ad],end)[0],'istekao')
        document,_=public_document([{'group_id':1,'sources':[ad]}],before)
        self.assertEqual(document['count'],1)
        self.assertEqual(document['oglasi'][0]['status'],'rok_nije_istekao')
        self.assertEqual(public_document([{'group_id':1,'sources':[ad]}],end)[0]['count'],0)

    def test_review_is_read_only_and_explains_existing_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            try:
                a=Job('a','https://a.rs/1','Developer','Acme','Long description '*30,['Novi Sad'],posted='2026-10-01')
                b=Job('a','https://a.rs/2','Developer','Acme','Long description '*30,['Novi Sad'],posted='2026-10-02')
                ga=store.save(a);gb=store.save(b)
                with store.db:store.db.execute('UPDATE ads SET group_id=? WHERE group_id=?',(ga,gb))
                before=list(store.db.iterdump())
                document=review_document(store)
                self.assertEqual(document['counts']['blocked_groups'],1)
                self.assertIn('possible_reposted_job',document['blocked_groups'][0]['conflicts'][0]['reason'])
                self.assertEqual(list(store.db.iterdump()),before)
            finally:store.close()

    def test_cross_source_candidates_and_expired_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            try:
                for source in ('a','b'):
                    store.save(Job(source,'https://'+source+'.rs/1','Developer','Acme',source+' unique text',['Novi Sad'],expires='2099-01-01'))
                self.assertEqual(review_document(store)['counts']['cross_source_pairs'],1)
                for source in ('a','b'):
                    store.save(Job(source,'https://'+source+'.rs/1','Developer','Acme',source+' unique text',['Novi Sad'],expires='2000-01-01'))
                self.assertEqual(review_document(store)['counts']['cross_source_pairs'],0)
            finally:store.close()

    def test_untrusted_content_is_escaped(self):
        ad={'source':'x','url':'javascript:alert(1)','title':'<script>alert(1)</script>',
            'employer':'X','locations':['Novi Sad'],'description':'<img src=x onerror=alert(1)>'}
        document={'generated_at':'now','blocked_groups':[],'cross_source_pairs':[],
                  'stale_groups':[{'group_id':1,'sources':[ad]}]}
        html=render_review(document)
        self.assertNotIn('<script>',html)
        self.assertNotIn('<img',html)
        self.assertNotIn('href="javascript:',html)
        self.assertIn('&lt;script&gt;',html)
