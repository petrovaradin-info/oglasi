import json
import signal
import tempfile
import unittest
from pathlib import Path
from threading import Barrier, Event
from unittest.mock import patch

from oglasi.cli import main
from oglasi.collector import Client, FetchError, collect
from oglasi.store import Store


class InterruptTests(unittest.TestCase):
    def test_parallel_stop_preserves_saved_ads_and_records_interruption(self):
        stop=Event()
        barrier=Barrier(2)
        class FakeClient:
            def __init__(self,*args):pass
            def listing_page(self,*args):
                return '<a href="/job/1">One</a><a href="/job/2">Two</a>'
            def get(self,*args):
                barrier.wait(timeout=5)
                stop.set()
                return '<script type="application/ld+json">'+json.dumps({
                    '@type':'JobPosting','title':'Developer','description':'Job description',
                    'jobLocation':{'address':{'addressLocality':'Novi Sad'}}})+'</script>'
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            config={'workers':2,'sources':[
                {'id':name,'urls':[f'https://{name}.rs/list'],'detail_pattern':'/job/'}
                for name in ('one','two','queued')]}
            with patch('oglasi.collector.Client',FakeClient):
                reports=collect(store,config,stop_event=stop)
            self.assertEqual(len(reports),2)
            self.assertTrue(all(r['status']=='interrupted' and r['attempted']==1 for r in reports))
            self.assertEqual(store.db.execute('select count(*) from ads').fetchone()[0],2)
            self.assertEqual(store.db.execute('select count(*) from runs where status="interrupted"').fetchone()[0],2)
            store.close()

    def test_cancelled_delay_never_starts_request(self):
        client=Client()
        client.stop_event.set()
        with patch.object(client.session,'get') as get:
            with self.assertRaises(FetchError):client.request('https://example.com')
            get.assert_not_called()
        client.session.close()

    def test_cli_handles_repeated_interrupt_and_restores_signal_handler(self):
        previous=signal.getsignal(signal.SIGINT)
        def fake_collect(*args,stop_event):
            handler=signal.getsignal(signal.SIGINT)
            handler(signal.SIGINT,None)
            handler(signal.SIGINT,None)
            self.assertTrue(stop_event.is_set())
            return []
        with tempfile.TemporaryDirectory() as tmp:
            with patch('sys.argv',['main.py','--db',str(Path(tmp)/'test.db'),'collect']), patch('oglasi.cli.collect',side_effect=fake_collect), patch('builtins.print'):
                with self.assertRaises(SystemExit) as raised:main()
                self.assertEqual(raised.exception.code,130)
        self.assertEqual(signal.getsignal(signal.SIGINT),previous)
