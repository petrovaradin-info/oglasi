from datetime import datetime,timezone,timedelta
import unittest
from oglasi.lifecycle import deadline_state, deadline_instant, group_state
from oglasi.platform_export import cards


class LifecycleTests(unittest.TestCase):
    def test_date_only_includes_whole_local_day(self):
        end=deadline_instant('2026-09-12')
        self.assertEqual(deadline_state('2026-09-12',end-timedelta(seconds=1)),'rok_nije_istekao')
        self.assertEqual(deadline_state('2026-09-12',end),'istekao')

    def test_timestamp_and_unknown(self):
        at=datetime(2026,9,12,12,tzinfo=timezone.utc)
        self.assertEqual(deadline_state('2026-09-12T13:00:00+02:00',at),'istekao')
        for value in ('','not a date','2026-13-40'):
            self.assertEqual(deadline_state(value,at),'rok_nije_poznat')

    def test_unknown_copy_does_not_keep_expired_group_visible(self):
        self.assertEqual(group_state([{'expires':'2000-01-01'},{'expires':''}]),('istekao','2000-01-01'))
        self.assertEqual(group_state([{'expires':'2000-01-01'},{'expires':'2099-01-01'}]),('rok_nije_istekao','2099-01-01'))

    def test_secondary_source_enriches_card_and_keeps_own_deadline(self):
        ad=dict(title='Job',employer='Acme',description='Full description '*30,locations=['Novi Sad'],
                url='https://a.rs/job',source='a',quality='structured',expired=False,expires='',posted='',structured={})
        other={**ad,'url':'https://b.rs/job','source':'b','description':'Excerpt','expires':'2000-01-01','expired':True,
               'posted':'1999-12-01','structured':{'employmentType':['FULL_TIME','TEMPORARY']}}
        row=cards([{'group_id':1,'sources':[ad,other]}])[0]
        self.assertEqual(row['datum_objave'],'1999-12-01')
        self.assertEqual(row['tip_zaposlenja'],'Puno radno vreme, Privremeni posao')
        self.assertEqual(row['tip_zaposlenja_poreklo'],'izvor')
        self.assertTrue(row['arhiviran']);self.assertFalse(row['vidljiv'])
        self.assertEqual(row['izvori'][0]['status'],'rok_nije_poznat')
        self.assertEqual(row['izvori'][1]['status'],'istekao')

    def test_inferred_contract_is_marked(self):
        from oglasi.platform_export import employment
        self.assertEqual(employment([{'facets':{'contract_type':{'values':['određeno']}}}]),('određeno','prepoznato_u_tekstu'))
