import tempfile
import unittest
from pathlib import Path
from oglasi.store import Store
from oglasi.progress import Progress

class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'test.db')
        self.store.record('large','2026-01-01','ok',{'discovered':990,'pages':10})
        self.store.record('small','2026-01-01','ok',{'discovered':9,'pages':1})
        self.time=0
        self.p=Progress(self.store,[{'id':'large'},{'id':'small'}],clock=lambda:self.time)
    def tearDown(self):
        self.store.close();self.tmp.cleanup()
    def test_large_source_is_weighted_and_eta_uses_elapsed(self):
        self.p.update('small',10,status='ok',active=False)
        self.p.update('large',495)
        self.time=100
        s=self.p.snapshot()
        self.assertEqual(s['percent'],50)
        self.assertAlmostEqual(s['eta'],100)
        self.assertEqual(s['active'],['large'])
    def test_discovery_expands_estimate_and_never_finishes_early(self):
        self.p.update('large',1000,discovered=2000)
        self.assertLess(self.p.snapshot()['percent'],60)
        self.p.update('small',10,status='ok',active=False)
        self.assertLess(self.p.snapshot()['percent'],100)
    def test_complete_with_errors_is_not_success_claim(self):
        for source in ('large','small'):self.p.update(source,status='error',active=False)
        s=self.p.snapshot()
        self.assertEqual(s['percent'],100)
        self.assertEqual(s['eta'],0)
        self.assertEqual(s['issues'],2)
    def test_interrupt_does_not_show_100(self):
        for source in ('large','small'):self.p.update(source,status='interrupted',active=False)
        self.assertLess(self.p.snapshot()['percent'],100)
