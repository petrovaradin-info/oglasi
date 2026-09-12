import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from oglasi.cli import main
from oglasi.collector import collect, FetchError
from oglasi.model import Job
from oglasi.store import Store


class LoggingTests(unittest.TestCase):
    def test_cli_writes_utf8_file_and_closes_handler_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'logs'/'run.log'
            def fake_collect(*args,**kwargs):
                logging.info('[test] GET https://example.com/posao/čistač')
                return [{'source':'test','status':'partial'}]
            with patch('sys.argv',['main.py','--db',str(Path(tmp)/'test.db'),'collect','--log-file',str(path)]),patch('oglasi.cli.collect',fake_collect),patch('builtins.print'):
                with self.assertRaises(SystemExit) as result:main()
                self.assertEqual(result.exception.code,2)
            self.assertIn('https://example.com/posao/čistač',path.read_text(encoding='utf-8'))
            self.assertFalse(any(isinstance(h,logging.FileHandler) and Path(h.baseFilename)==path for h in logging.getLogger().handlers))
            path.unlink()  # Windows rejects this if our FileHandler still owns it.

    def test_each_ad_logs_url_and_outcome_including_cache_and_errors(self):
        urls=['https://example.com/job/'+str(i) for i in range(3)]
        class Client:
            def __init__(self,*args):pass
            def listing_page(self,*args):return 'listing'
            def get(self,url):
                if url==urls[2]:raise FetchError('Server unavailable',503)
                return url
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            store.save(Job('test',urls[0],'Cached job','Acme','Description',['Novi Sad']))
            cfg={'sources':[{'id':'test','urls':['https://example.com/list']} ]}
            with patch('oglasi.collector.Client',Client),patch('oglasi.collector.listing',return_value=(dict.fromkeys(urls,''),[])),patch('oglasi.collector.detail',side_effect=lambda html,url,source:Job('test',url,'New job','Acme','Description',['Novi Sad'])),self.assertLogs('oglasi.collector',level='INFO') as logged:
                collect(store,cfg)
            messages='\n'.join(logged.output)
            for url in urls:self.assertIn(url,messages)
            for event in ['SOURCE START','LIST page=1','LIST RESULT links=3','AD 1/3','CACHED','SAVED group=','ERROR']:self.assertIn(event,messages)
            store.close()
