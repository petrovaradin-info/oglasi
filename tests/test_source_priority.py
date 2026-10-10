import unittest
from datetime import datetime, timezone
from oglasi.model import Job
from oglasi.platform_export import cards
from oglasi.publication import publication_state
from oglasi.lifecycle import group_state

class SourcePriorityTests(unittest.TestCase):
    def ad(self, source, expires='2099-01-01', **values):
        ad=Job(source,'https://'+source+'.rs/job/1',source,'Acme','Description '*30,['Novi Sad'],expires=expires).dict()
        ad.update(expired=False,last_seen='2026-10-10T05:00:00+00:00')
        ad.update(values)
        return ad

    def test_infostud_wins_and_links_are_ordered(self):
        a=self.ad('infostud',structured={'employmentType':'FULL_TIME','original_url':'https://other.rs/1'})
        b=self.ad('helloworld',structured={'employmentType':'PART_TIME'})
        c=self.ad('other',description='Long description '*100)
        row=cards([{'group_id':1,'sources':[c,b,a]}])[0]
        self.assertEqual(row['naslov'],'infostud')
        self.assertEqual(row['link'],a['url'])
        self.assertEqual(row['tip_zaposlenja'],'Puno radno vreme')
        self.assertEqual([x['naziv'] for x in row['izvori']],['infostud','helloworld','other'])
        self.assertEqual(cards([{'group_id':1,'sources':[a,c,b]}])[0],row)

    def test_helloworld_is_second_choice(self):
        row=cards([{'group_id':1,'sources':[self.ad('other'),self.ad('helloworld')]}])[0]
        self.assertEqual(row['naslov'],'helloworld')

    def test_secondary_deadlines_do_not_close_or_extend_favorite(self):
        a=self.ad('infostud');b=self.ad('other','2000-01-01')
        self.assertEqual(group_state([b,a])[0],'rok_nije_istekao')
        a['expires']='2000-01-01';b['expires']='2099-01-01'
        self.assertEqual(group_state([b,a])[0],'istekao')
        self.assertFalse(publication_state([b,a])['vidljiv'])

    def test_secondary_does_not_refresh_stale_favorite(self):
        a=self.ad('infostud','',last_seen='2020-01-01T00:00:00+00:00')
        b=self.ad('other')
        at=datetime(2026,10,10,6,tzinfo=timezone.utc)
        self.assertFalse(publication_state([a,b],at)['vidljiv'])
        a['last_seen']=b['last_seen']
        self.assertTrue(publication_state([a,b],at)['vidljiv'])

    def test_conflicting_favorite_reposts_still_require_review(self):
        a=self.ad('infostud',posted='2026-10-01')
        b=self.ad('infostud',posted='2026-10-02',url='https://infostud.rs/job/2')
        self.assertIn('proveriti_spajanje',publication_state([a,b])['razlozi'])

    def test_missing_employment_can_be_supplemented(self):
        a=self.ad('infostud');b=self.ad('helloworld',structured={'employmentType':'PART_TIME'})
        self.assertEqual(cards([{'group_id':1,'sources':[a,b]}])[0]['tip_zaposlenja'],'Nepuno radno vreme')
