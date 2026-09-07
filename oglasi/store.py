import hashlib
import json
import sqlite3
from datetime import datetime
from difflib import SequenceMatcher
from .model import norm, now

def dump(value): return json.dumps(value,ensure_ascii=False,sort_keys=True)

class Store:
    def __init__(self,path):
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS groups(id INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS ads(url TEXT PRIMARY KEY, source TEXT, group_id INTEGER REFERENCES groups(id), payload TEXT, hash TEXT, first_seen TEXT, last_seen TEXT, fetched_at TEXT);
        CREATE INDEX IF NOT EXISTS ads_group ON ads(group_id);
        CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY, url TEXT, captured_at TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS candidates(url_a TEXT, url_b TEXT, score REAL, reason TEXT, PRIMARY KEY(url_a,url_b));
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, source TEXT, started TEXT, finished TEXT, status TEXT, details TEXT);
        CREATE TABLE IF NOT EXISTS facets(url TEXT, kind TEXT, value TEXT, method TEXT, PRIMARY KEY(url,kind,value));
        ''')
        self.db.commit()

    def close(self): self.db.close()

    def fresh(self,url,hours=24):
        row=self.db.execute('SELECT fetched_at FROM ads WHERE url=?',(url,)).fetchone()
        return bool(row and (datetime.fromisoformat(now())-datetime.fromisoformat(row[0])).total_seconds()<hours*3600)

    def seen(self,url):
        with self.db: self.db.execute('UPDATE ads SET last_seen=? WHERE url=?',(now(),url))

    def save(self,job):
        data=job.dict(); payload=dump(data); digest=hashlib.sha256(payload.encode()).hexdigest(); stamp=now()
        with self.db:
            old=self.db.execute('SELECT group_id,hash FROM ads WHERE url=?',(job.url,)).fetchone()
            group=old[0] if old else None
            candidates=[]
            if not old:
                for url,gid,raw in self.db.execute('SELECT url,group_id,payload FROM ads'):
                    other=json.loads(raw)
                    if not job.employer or norm(job.employer)!=norm(other['employer']): continue
                    if set(job.locations)!=set(other['locations']) or not job.locations: continue
                    score=SequenceMatcher(None,norm(job.title),norm(other['title'])).ratio()
                    try: nearby=abs((datetime.fromisoformat(job.posted[:10])-datetime.fromisoformat(other['posted'][:10])).days)<=30
                    except (ValueError,TypeError): nearby=False
                    similarity=SequenceMatcher(None,norm(job.description),norm(other['description'])).ratio()
                    same_place=not (job.location_raw and other.get('location_raw')) or norm(job.location_raw)==norm(other['location_raw'])
                    if score==1 and nearby and same_place and similarity>=0.85 and len(job.description)>80:
                        group=gid; break
                    if score>=0.82: candidates.append((url,score))
            if group is None: group=self.db.execute('INSERT INTO groups DEFAULT VALUES').lastrowid
            if not old or old[1]!=digest:
                self.db.execute('INSERT INTO versions(url,captured_at,payload) VALUES(?,?,?)',(job.url,stamp,payload))
            self.db.execute('''INSERT INTO ads VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET
                payload=excluded.payload,hash=excluded.hash,last_seen=excluded.last_seen,fetched_at=excluded.fetched_at''',
                (job.url,job.source,group,payload,digest,stamp,stamp,stamp))
            self.db.execute('DELETE FROM facets WHERE url=?',(job.url,))
            for kind,facet in job.facets.items():
                for val in facet.get('values',[facet.get('value')]):
                    self.db.execute('INSERT OR IGNORE INTO facets VALUES(?,?,?,?)',(job.url,kind,dump(val),facet['method']))
            for url,score in candidates:
                a,b=sorted((url,job.url))
                self.db.execute('INSERT OR REPLACE INTO candidates VALUES(?,?,?,?)',(a,b,score,'same employer/location; title similar; needs review'))
        return group

    def record(self,source,started,status,details):
        with self.db:self.db.execute('INSERT INTO runs(source,started,finished,status,details) VALUES(?,?,?,?,?)',(source,started,now(),status,dump(details)))

    def export(self,location=None,facet=None,value=None):
        groups={}
        for url,gid,raw,first,last in self.db.execute('SELECT url,group_id,payload,first_seen,last_seen FROM ads ORDER BY group_id'):
            job=json.loads(raw)
            if location and location not in job['locations']:continue
            selected=job['facets'].get(facet,{})
            values=selected.get('values',selected.get('value',[]))
            if not isinstance(values,list):values=[values]
            if facet and not any(norm(value)==norm(v) for v in values):continue
            groups.setdefault(gid,[]).append({**job,'first_seen':first,'last_seen':last,'expired':bool(job['expires'] and job['expires'][:10]<now()[:10])})
        return [{'group_id':gid,'sources':ads} for gid,ads in groups.items()]
