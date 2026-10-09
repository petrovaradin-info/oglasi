import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from oglasi.publication import publication_state, atomic_text, public_document
from oglasi.dedup import match

class PublicationTests(unittest.TestCase):
    def ad(self, **kw):
        value=dict(source='a',url='https://a.rs/1',title='Developer',employer='Acme',
                   locations=['Novi Sad'],description='Detailed description. '*30,
                   posted='2026-10-01',expires='',expired=False,quality='structured',
                   structured={},last_seen='2026-10-09T10:00:00+00:00')
        value.update(kw)
        return value

    def test_freshness_boundary_missing_invalid_future(self):
        at=datetime(2026,10,9,12,tzinfo=timezone.utc)
        for value in ('', 'broken', (at+timedelta(days=1)).isoformat(), (at-timedelta(days=14)).isoformat()):
            self.assertFalse(publication_state([self.ad(last_seen=value)],at)['vidljiv'])
        self.assertTrue(publication_state([self.ad(last_seen=(at-timedelta(days=14)+timedelta(seconds=1)).isoformat())],at)['vidljiv'])

    def test_expired_is_not_revived_by_recent_discovery(self):
        self.assertFalse(publication_state([self.ad(expires='2000-01-01')])['vidljiv'])
        self.assertTrue(publication_state([self.ad(expires='2099-01-01',last_seen='')])['vidljiv'])

    def test_reposts_are_reviewed_without_splitting_history(self):
        a=self.ad();b=self.ad(url='https://a.rs/2',posted='2026-10-02')
        self.assertFalse(match(a,b)[0])
        self.assertIn('proveriti_spajanje',publication_state([a,b])['razlozi'])
        b['source']='b'
        self.assertTrue(match(a,b)[0])

    def test_public_contract(self):
        groups=[{'group_id':4,'sources':[self.ad(expires='2099-01-01')]},
                {'group_id':5,'sources':[self.ad(last_seen='')]}]
        doc,review=public_document(groups)
        self.assertEqual(doc['count'],1)
        self.assertEqual(doc['oglasi'][0]['id'],'4')
        self.assertEqual(review[0]['id'],'5')
        self.assertIn('vidljiv_do',doc['oglasi'][0])
        self.assertEqual(doc['schema_version'],'1.0')

    def test_failed_replace_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'public.json';atomic_text(p,'old')
            with patch('oglasi.publication.os.replace',side_effect=OSError('busy')):
                with self.assertRaises(OSError):atomic_text(p,'new')
            self.assertEqual(p.read_text(),'old')
            self.assertEqual(list(Path(tmp).iterdir()),[p])
            atomic_text(p,'new');self.assertEqual(p.read_text(),'new')
