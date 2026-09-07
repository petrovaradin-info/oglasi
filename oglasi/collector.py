import json
import logging
import time
import re
import urllib.robotparser
from urllib.parse import urlsplit
from collections import deque
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .model import now
from .parsers import listing, detail

LOG=logging.getLogger(__name__)
AGENT='PetrovaradinJobs/0.1'

class FetchError(Exception):pass

class Client:
    def __init__(self,delay=2):
        self.session=requests.Session(); self.session.headers['User-Agent']=AGENT
        self.session.mount('https://',HTTPAdapter(max_retries=Retry(total=2,backoff_factor=1,status_forcelist=[500,502,503,504],allowed_methods=['GET'],respect_retry_after_header=False)))
        self.delay=delay; self.last={}; self.robots={}

    def request(self,url):
        host=urlsplit(url).netloc
        time.sleep(max(0,self.delay-(time.monotonic()-self.last.get(host,0))))
        try:
            response=self.session.get(url,timeout=(10,30))
            self.last[host]=time.monotonic()
            # Mjob uses HTTP 404 for a valid empty search; do not mask other 404s.
            if response.status_code==404 and host=='www.mjob.rs' and urlsplit(url).path=='/api/jobs':
                try:
                    empty=response.json()
                    if empty.get('jobs')==[] and empty.get('total')==0:return json.dumps(empty)
                except (ValueError,AttributeError):pass
            response.raise_for_status()
        except requests.RequestException as e:raise FetchError(str(e)) from e
        response.encoding='utf-8' if 'charset=' not in response.headers.get('content-type','').lower() else response.encoding
        return response.text

    def get(self,url):
        p=urlsplit(url); origin=f'{p.scheme}://{p.netloc}'
        if origin not in self.robots:
            robot=urllib.robotparser.RobotFileParser()
            try: robot.parse(self.request(origin+'/robots.txt').splitlines())
            except FetchError as e:
                if '404' in str(e):robot.parse([])
                else:raise FetchError('robots.txt unavailable: '+str(e)) from e
            self.robots[origin]=robot
        robot=self.robots[origin]
        if not robot.can_fetch(AGENT,url):raise FetchError('robots.txt disallows '+url)
        delay=robot.crawl_delay(AGENT)
        if delay:self.delay=max(self.delay,delay)
        return self.request(url)

def collect(store,config,only=None,max_details=None):
    client=Client(config.get('request_delay',2)); reports=[]
    for source in config['sources']:
        if only and source['id']!=only:continue
        started=now(); counts={'pages':0,'discovered':0,'saved':0,'cached':0,'outside_area':0,'errors':[]}
        if not source.get('enabled',True):
            store.record(source['id'],started,'pending_integration',{'reason':source.get('note','')});continue
        queue=deque(source['urls']); visited=set(); details=set(); limited=False
        while queue and len(visited)<config.get('max_pages',100):
            url=queue.popleft()
            if url in visited:continue
            visited.add(url)
            try:
                html=client.get(url)
                found,pages=listing(html,url,source)
                counts['pages']+=1
                if not found and not source.get('allow_empty',False):counts['errors'].append({'url':url,'error':'No job links found: empty results or changed/dynamic page; check source'})
                queue.extend(p for p in pages if p not in visited)
                for link in found:
                    if link in details:continue
                    details.add(link); counts['discovered']+=1
                    if source['id']!='mjob' and store.fresh(link,config.get('refresh_hours',24)):
                        store.seen(link);counts['cached']+=1;continue
                    if max_details is not None and counts['saved']+counts['outside_area']>=max_details:
                        limited=True;break
                    try:
                        fetch_url=link
                        if source['id']=='lako':
                            identifier=re.search(r'(\d+)$',link)
                            if not identifier:raise ValueError('Missing Lako posting ID')
                            fetch_url='https://prod.lakodoposla.net/api/postings/'+identifier[1]
                        content=json.dumps(found[link]) if source['id']=='mjob' else client.get(fetch_url)
                        job=detail(content,link,source)
                        if job.locations: store.save(job); counts['saved']+=1
                        else:counts['outside_area']+=1
                    except (FetchError,ValueError,TypeError,KeyError) as e:
                        counts['errors'].append({'url':link,'error':str(e)})
                    if len(counts['errors'])>=20:limited=True;break
                if limited:break
            except (FetchError,ValueError,TypeError,KeyError) as e:
                counts['errors'].append({'url':url,'error':str(e)})
        if queue or limited:counts['truncated']=True
        status='partial' if counts['errors'] or counts.get('truncated') else 'ok'
        if counts['errors'] and not counts['saved'] and not counts['cached']:status='error'
        store.record(source['id'],started,status,counts)
        LOG.info('%s: %s %s',source['id'],status,counts)
        reports.append({'source':source['id'],'status':status,**counts})
    return reports
