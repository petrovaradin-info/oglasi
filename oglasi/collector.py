import json
import logging
import time
import re
from threading import Event
from protego import Protego
from urllib.parse import urlsplit, urljoin, urlunsplit
from collections import deque
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .model import now
from .parsers import listing, detail, empty_listing
from .extra_sources import SkipJob, sbu_payload

LOG=logging.getLogger(__name__)
AGENT='PetrovaradinJobs/0.1'

class FetchError(Exception):
    def __init__(self,message,status_code=None):
        super().__init__(message)
        self.status_code=status_code

class Client:
    def __init__(self,delay=2):
        self.session=requests.Session(); self.session.headers['User-Agent']=AGENT
        self.session.mount('https://',HTTPAdapter(max_retries=Retry(total=2,backoff_factor=1,status_forcelist=[500,502,503,504],allowed_methods=['GET'],respect_retry_after_header=False)))
        self.delay=delay; self.last={}; self.robots={}
        self.sbu_state=None
        self.stop_event=Event()
        self.source_id='http'

    def pause(self,seconds):
        if self.stop_event.wait(seconds):raise FetchError('Collection interrupted')

    def request(self,url,follow_redirects=True):
        host=urlsplit(url).netloc
        LOG.info('[%s] GET %s',self.source_id,url)
        self.pause(max(0,self.delay-(time.monotonic()-self.last.get(host,0))))
        try:
            response=self.session.get(url,timeout=(10,30),allow_redirects=follow_redirects)
            LOG.info('[%s] HTTP %s %s',self.source_id,response.status_code,url)
            self.last[host]=time.monotonic()
            self.final_url=url
            self.redirect_url=None
            if response.status_code in (301,302,303,307,308):
                self.redirect_url=urljoin(url,response.headers['Location'])
                return ''
            # Mjob uses HTTP 404 for a valid empty search; do not mask other 404s.
            if response.status_code==404 and host=='www.mjob.rs' and urlsplit(url).path=='/api/jobs':
                try:
                    empty=response.json()
                    if empty.get('jobs')==[] and empty.get('total')==0:return json.dumps(empty)
                except (ValueError,AttributeError):pass
            response.raise_for_status()
        except requests.RequestException as e:
            raise FetchError(str(e),e.response.status_code if e.response is not None else None) from e
        response.encoding='utf-8' if 'charset=' not in response.headers.get('content-type','').lower() else response.encoding
        return response.text

    def check_robots(self,url):
        p=urlsplit(url); origin=f'{p.scheme}://{p.netloc}'
        if origin not in self.robots:
            try: robot=Protego.parse(self.request(origin+'/robots.txt'))
            except FetchError as e:
                if '404' in str(e):robot=Protego.parse('')
                else:raise FetchError('robots.txt unavailable: '+str(e)) from e
            self.robots[origin]=robot
        robot=self.robots[origin]
        if not robot.can_fetch(url,AGENT):raise FetchError('robots.txt disallows '+url)
        delay=robot.crawl_delay(AGENT)
        if delay:self.delay=max(self.delay,delay)
    def get(self,url):
        for _ in range(10):
            self.check_robots(url)
            content=self.request(url,follow_redirects=False)
            if not self.redirect_url:return content
            url=self.redirect_url
        raise FetchError('Too many redirects')

    def listing_page(self,url,source):
        if source['id']=='sbu' and urlsplit(url).fragment.startswith('sbu-page='):
            if self.sbu_state is None:raise FetchError('SBU: missing pagination state')
            endpoint='https://sbu-poslovi.rs/wp-admin/admin-ajax.php'
            self.check_robots(endpoint)
            host=urlsplit(endpoint).netloc
            self.pause(max(0,self.delay-(time.monotonic()-self.last.get(host,0))))
            payload={**self.sbu_state,'job_page':urlsplit(url).fragment.split('=')[1]}
            LOG.info('[%s] POST %s page=%s',source['id'],endpoint,payload['job_page'])
            try:
                response=self.session.post(endpoint,data=payload,timeout=(10,30),allow_redirects=False)
                LOG.info('[%s] HTTP %s %s',source['id'],response.status_code,endpoint)
                self.last[host]=time.monotonic()
                response.raise_for_status()
                if response.is_redirect:raise FetchError('SBU: unexpected pagination redirect')
                response.encoding='utf-8'
                return response.text
            except requests.RequestException as e:raise FetchError(str(e)) from e
        html=self.get(url)
        if source['id']=='sbu':self.sbu_state=sbu_payload(html)
        if source['id']=='careerjet' and ('captcha.careerjet' in html or 'Potrebna je verifikacija' in html):
            raise FetchError('access_verification_required: Careerjet requires a permitted API/feed')
        return html

def collect(store,config,only=None,max_details=None,stop_event=None):
    stop_event=stop_event if stop_event is not None else Event()
    selected={only} if isinstance(only,str) else set(only or [])
    sources=[s for s in config['sources'] if not selected or s['id'] in selected]
    workers=max(1,min(int(config.get('workers',1)),8))
    if workers>1 and len(sources)>1:
        from .store import Store
        def worker(source):
            local=Store(store.path)
            try:return collect(local,{**config,'workers':1,'sources':[source]},max_details=max_details,stop_event=stop_event)
            finally:local.close()
        reports=[]
        LOG.info('COLLECT START: sources=%s workers=%s refresh_hours=%s',len(sources),workers,config.get('refresh_hours',24))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(worker,s) for s in sources]
            for completed,future in enumerate(as_completed(futures),1):
                reports.extend(future.result())
                LOG.info('SOURCES FINISHED: %s/%s',completed,len(sources))
        order={s['id']:i for i,s in enumerate(sources)}
        return sorted(reports,key=lambda r:order[r['source']])
    client=Client(config.get('request_delay',2)); reports=[]
    client.stop_event=stop_event
    for source_number,source in enumerate(sources,1):
        if stop_event.is_set():break
        client.source_id=source['id']
        if len(sources)>1:LOG.info('SOURCE %s/%s',source_number,len(sources))
        LOG.info('[%s] SOURCE START',source['id'])
        started=now(); counts={'pages':0,'discovered':0,'attempted':0,'saved':0,'cached':0,'outside_area':0,'skipped':0,'excluded_cached':0,'errors':[]}
        if not source.get('enabled',True):
            store.record(source['id'],started,'pending_integration',{'reason':source.get('note','')});continue
        queue=deque(source['urls']); visited=set(); details=set(); limited=False
        page_limit=source.get('max_pages',config.get('max_pages',100))
        while queue and len(visited)<page_limit and not stop_event.is_set():
            url=queue.popleft()
            if url in visited:continue
            visited.add(url)
            LOG.info('[%s] LIST page=%s limit=%s %s',source['id'],len(visited),page_limit,url)
            try:
                html=client.listing_page(url,source)
                found,pages=listing(html,url,source)
                counts['pages']+=1
                if counts['pages']%10==0:LOG.info('%s: %s pages, %s saved, %s cached',source['id'],counts['pages'],counts['saved'],counts['cached'])
                if not found and not source.get('allow_empty',False) and not empty_listing(html,source):counts['errors'].append({'url':url,'error':'No job links found: empty results or changed/dynamic page; check source'})
                queue.extend(p for p in pages if p not in visited)
                LOG.info('[%s] LIST RESULT links=%s pending_pages=%s %s',source['id'],len(found),len(set(queue)-visited),url)
                for position,link in enumerate(found,1):
                    if stop_event.is_set():break
                    if link in details:continue
                    details.add(link); counts['discovered']+=1
                    LOG.info('[%s] AD %s/%s on page; discovered=%s %s',source['id'],position,len(found),counts['discovered'],link)
                    if source['id'] not in ('mjob','adorio') and store.fresh(link,config.get('refresh_hours',24)):
                        store.seen(link);counts['cached']+=1;LOG.info('[%s] CACHED %s',source['id'],link);continue
                    if source['id'] not in ('mjob','adorio') and store.checked(source['id'],link,config.get('refresh_hours',24)):
                        counts['excluded_cached']+=1;LOG.info('[%s] EXCLUDED CACHED %s',source['id'],link);continue
                    if max_details is not None and counts['attempted']>=max_details:
                        limited=True;break
                    counts['attempted']+=1
                    try:
                        fetch_url=link
                        if source.get('detail_trailing_slash'):
                            parts=urlsplit(link)
                            if not parts.query:fetch_url=urlunsplit((parts.scheme,parts.netloc,parts.path.rstrip('/')+'/',parts.query,''))
                        if source['id']=='lako':
                            identifier=re.search(r'(\d+)$',link)
                            if not identifier:raise ValueError('Missing Lako posting ID')
                            fetch_url='https://prod.lakodoposla.net/api/postings/'+identifier[1]
                        if source['id']=='joberty':fetch_url='https://backend.joberty.com/api/v1/jobs/'+link.rsplit('/',1)[1]
                        content=json.dumps(found[link]) if source['id'] in ('mjob','adorio') else client.get(fetch_url)
                        job=detail(content,link,source)
                        if job.locations:
                            group=store.save(job);counts['saved']+=1
                            LOG.info('[%s] SAVED group=%s %s',source['id'],group,link)
                        else:
                            store.exclude(source['id'],link,'outside_area');counts['outside_area']+=1
                            LOG.info('[%s] OUTSIDE AREA %s',source['id'],link)
                    except SkipJob as e:
                        store.exclude(source['id'],link,str(e))
                        counts['skipped']+=1
                        LOG.info('[%s] SKIPPED %s %s',source['id'],str(e),link)
                    except FetchError as e:
                        if source['id']=='lako' and e.status_code in (404,410):
                            store.exclude(source['id'],link,'detail_unavailable_'+str(e.status_code));counts['skipped']+=1
                            LOG.info('[%s] SKIPPED HTTP %s %s',source['id'],e.status_code,link)
                        elif not stop_event.is_set():
                            counts['errors'].append({'url':link,'error':str(e)})
                            LOG.warning('[%s] ERROR %s %s',source['id'],link,str(e))
                    except (FetchError,ValueError,TypeError,KeyError,AttributeError) as e:
                        if not stop_event.is_set():
                            counts['errors'].append({'url':link,'error':str(e)})
                            LOG.warning('[%s] ERROR %s %s',source['id'],link,str(e))
                    if len(counts['errors'])>=20:limited=True;break
                    if counts['discovered']%25==0:LOG.info('%s: %s checked, %s saved, %s errors',source['id'],counts['discovered'],counts['saved'],len(counts['errors']))
                if limited:break
            except (FetchError,ValueError,TypeError,KeyError,AttributeError) as e:
                if not stop_event.is_set():
                    counts['errors'].append({'url':url,'error':str(e)})
                    LOG.warning('[%s] LIST ERROR %s %s',source['id'],url,str(e))
        pending=set(queue)-visited
        if pending or limited:
            counts['truncated']=True
            counts['remaining_pages']=len(pending)
            counts['limit_reason']='detail_or_error_limit' if limited else 'page_limit'
        if source.get('coverage_note'):counts['coverage_note']=source['coverage_note']
        status='partial' if counts['errors'] or counts.get('truncated') else 'ok'
        if source.get('coverage_note') and status=='ok':status='partial'
        if counts['errors'] and not counts['saved'] and not counts['cached']:status='error'
        if stop_event.is_set():status='interrupted'
        store.record(source['id'],started,status,counts)
        LOG.info('%s: %s %s',source['id'],status,counts)
        reports.append({'source':source['id'],'status':status,**counts})
    return reports
