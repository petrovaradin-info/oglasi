"""Approximate workload progress; completion is distinct from source success."""
import json
import logging
import time
from threading import Event, Lock, Thread

LOG = logging.getLogger(__name__)

def duration(seconds):
    if seconds < 60:return f'{max(0,round(seconds))}s'
    minutes = round(seconds / 60)
    return f'{minutes // 60}h {minutes % 60:02d}m' if minutes >= 60 else f'{minutes}m'

class Progress:
    def __init__(self, store, sources, clock=time.monotonic):
        self.clock=clock; self.started=clock(); self.lock=Lock(); self.stop=Event()
        self.states={}
        for source in sources:
            row=store.db.execute("SELECT details FROM runs WHERE source=? AND status IN ('ok','partial') ORDER BY id DESC LIMIT 1",(source['id'],)).fetchone()
            try: history=json.loads(row[0]) if row else {}
            except (ValueError,TypeError): history={}
            self.states[source['id']]={'expected':max(1,history.get('discovered',0)+history.get('pages',0)) if history else 50,
                                      'done':0,'active':False,'status':None}
        self.thread=Thread(target=self.run,daemon=True)

    def update(self, source, done=0, discovered=0, active=True, status=None):
        with self.lock:
            s=self.states[source]
            s.update(done=done,active=active,status=status)
            s['expected']=max(s['expected'],discovered,done+1 if status is None else done)

    def snapshot(self):
        with self.lock:
            states=list(self.states.values())
            total=sum(s['expected'] for s in states)
            complete=sum(s['status'] is not None for s in states)
            work=sum(s['expected'] if s['status'] is not None else min(s['done'],s['expected']*.99) for s in states)
            ratio=work/total if total else 1
            elapsed=max(0,self.clock()-self.started)
            eta=0 if complete==len(states) else (elapsed*(1-ratio)/ratio if elapsed>=30 and ratio>0 else None)
            return {'percent':min(99,round(ratio*100)) if complete<len(states) or any(s['status']=='interrupted' for s in states) else 100,
                    'elapsed':elapsed,'eta':eta,'finished':complete,'total':len(states),
                    'active':[k for k,v in self.states.items() if v['active'] and v['status'] is None],
                    'issues':sum(s['status'] not in (None,'ok') for s in states)}

    def emit(self, label='NAPREDAK'):
        s=self.snapshot()
        LOG.info('%s ~%s%% | izvori %s/%s | proteklo %s | preostalo ~%s | aktivni: %s | izvori sa problemom: %s',
                 label,s['percent'],s['finished'],s['total'],duration(s['elapsed']),
                 duration(s['eta']) if s['eta'] is not None else 'racunam...',
                 ', '.join(s['active']) or '-',s['issues'])

    def run(self):
        while not self.stop.wait(30):self.emit()

    def start(self):
        self.emit();self.thread.start()

    def finish(self, interrupted=False):
        self.stop.set();self.thread.join()
        self.emit('PREKINUTO' if interrupted else 'KRAJ POKUSAJA')
