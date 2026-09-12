import hashlib
import json
import sqlite3
import threading
from functools import wraps
from datetime import datetime
from difflib import SequenceMatcher
from .model import norm, now
from .dedup import match
from .lifecycle import deadline_state

_write_lock=threading.RLock()

def write_locked(method):
    @wraps(method)
    def wrapped(*args,**kwargs):
        with _write_lock:return method(*args,**kwargs)
    return wrapped

def dump(value): return json.dumps(value,ensure_ascii=False,sort_keys=True)

class Store:
    @write_locked
    def __init__(self,path):
        self.path=path
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
        CREATE TABLE IF NOT EXISTS excluded(source TEXT, url TEXT, checked_at TEXT, reason TEXT, PRIMARY KEY(source,url));
        ''')
        self.db.commit()

    def close(self): self.db.close()

    def fresh(self,url,hours=24):
        row=self.db.execute('SELECT fetched_at FROM ads WHERE url=?',(url,)).fetchone()
        return bool(row and (datetime.fromisoformat(now())-datetime.fromisoformat(row[0])).total_seconds()<hours*3600)

    @write_locked
    def seen(self,url):
        with self.db: self.db.execute('UPDATE ads SET last_seen=? WHERE url=?',(now(),url))

    @write_locked
    def save(self,job):
        data=job.dict(); payload=dump(data); digest=hashlib.sha256(payload.encode()).hexdigest(); stamp=now()
        with self.db:
            old=self.db.execute('SELECT group_id,hash FROM ads WHERE url=?',(job.url,)).fetchone()
            group=old[0] if old else None
            candidates=[]
            matched_groups=set()
            for url,gid,raw in self.db.execute('SELECT url,group_id,payload FROM ads WHERE url<>?',(job.url,)):
                automatic,score,reason=match(data,json.loads(raw))
                if automatic:matched_groups.add(gid)
                elif score>=.82:candidates.append((url,score,reason))
            if group is not None:matched_groups.add(group)
            if matched_groups:
                group=min(matched_groups)
                for gid in matched_groups:
                    self.db.execute('UPDATE ads SET group_id=? WHERE group_id=?',(group,gid))
            if group is None: group=self.db.execute('INSERT INTO groups DEFAULT VALUES').lastrowid
            if not old or old[1]!=digest:
                self.db.execute('INSERT INTO versions(url,captured_at,payload) VALUES(?,?,?)',(job.url,stamp,payload))
            self.db.execute('''INSERT INTO ads VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET
                group_id=excluded.group_id,payload=excluded.payload,hash=excluded.hash,last_seen=excluded.last_seen,fetched_at=excluded.fetched_at''',
                (job.url,job.source,group,payload,digest,stamp,stamp,stamp))
            self.db.execute('DELETE FROM facets WHERE url=?',(job.url,))
            for kind,facet in job.facets.items():
                for val in facet.get('values',[facet.get('value')]):
                    self.db.execute('INSERT OR IGNORE INTO facets VALUES(?,?,?,?)',(job.url,kind,dump(val),facet['method']))
            self.db.execute('DELETE FROM candidates WHERE url_a=? OR url_b=?',(job.url,job.url))
            for url,score,reason in candidates:
                a,b=sorted((url,job.url))
                self.db.execute('INSERT OR REPLACE INTO candidates VALUES(?,?,?,?)',(a,b,score,reason))
            self.db.execute('DELETE FROM candidates WHERE (SELECT group_id FROM ads WHERE url=url_a)=(SELECT group_id FROM ads WHERE url=url_b)')
        return group

    @write_locked
    def reconcile(self):
        """Compare existing ads without modifying content timestamps or versions."""
        rows=[(url,gid,json.loads(raw)) for url,gid,raw in self.db.execute('SELECT url,group_id,payload FROM ads ORDER BY url')]
        parent={gid:gid for _,gid,_ in rows}
        def root(gid):
            while parent[gid]!=gid:
                parent[gid]=parent[parent[gid]];gid=parent[gid]
            return gid
        pairs=[];merged=0
        for index,(url,gid,job) in enumerate(rows):
            for other_url,other_gid,other in rows[:index]:
                automatic,score,reason=match(job,other)
                if automatic:
                    a,b=root(gid),root(other_gid)
                    if a!=b:parent[max(a,b)]=min(a,b);merged+=1
                elif score>=.82:pairs.append((*sorted((url,other_url)),score,reason))
        with self.db:
            for gid in parent:self.db.execute('UPDATE ads SET group_id=? WHERE group_id=?',(root(gid),gid))
            self.db.execute('DELETE FROM candidates')
            self.db.executemany('INSERT OR REPLACE INTO candidates VALUES(?,?,?,?)',pairs)
            self.db.execute('DELETE FROM candidates WHERE (SELECT group_id FROM ads WHERE url=url_a)=(SELECT group_id FROM ads WHERE url=url_b)')
        return {'merged_groups':merged,'review_pairs':self.db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0]}

    def checked(self,source,url,hours=24):
        row=self.db.execute('SELECT checked_at,reason FROM excluded WHERE source=? AND url=?',(source,url)).fetchone()
        if row and (datetime.fromisoformat(now())-datetime.fromisoformat(row[0])).total_seconds()<hours*3600:return row[1]
        return None

    @write_locked
    def exclude(self,source,url,reason):
        with self.db:self.db.execute('INSERT OR REPLACE INTO excluded VALUES(?,?,?,?)',(source,url,now(),reason))

    @write_locked
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
            groups.setdefault(gid,[]).append({**job,'first_seen':first,'last_seen':last,'expired':deadline_state(job.get('expires',''))=='istekao'})
        return [{'group_id':gid,'sources':ads} for gid,ads in groups.items()]
