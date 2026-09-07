import argparse
import json
import logging
import os
import sys
from pathlib import Path
from .store import Store
from .collector import collect

ROOT=Path(__file__).resolve().parent.parent

def main():
    parser=argparse.ArgumentParser(description='Oglasi: Petrovaradin, Novi Sad, Sremski Karlovci')
    parser.add_argument('--db',type=Path,default=ROOT/'data'/'oglasi.sqlite3')
    sub=parser.add_subparsers(dest='command',required=True)
    run=sub.add_parser('collect');run.add_argument('--source');run.add_argument('--max-details',type=int)
    export=sub.add_parser('export');export.add_argument('--location');export.add_argument('--facet');export.add_argument('--value');export.add_argument('--output',type=Path,default=ROOT/'data'/'oglasi.json')
    sub.add_parser('status');sub.add_parser('sources');sub.add_parser('candidates')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,stream=sys.stdout,format='%(asctime)s %(levelname)s %(message)s')
    config=json.loads((ROOT/'sources.json').read_text(encoding='utf-8'))
    if args.command=='sources':print(json.dumps(config,ensure_ascii=False,indent=2));return
    store=Store(args.db)
    try:
        if args.command=='collect':
            if args.source and args.source not in {s['id'] for s in config['sources']}:parser.error('Unknown source')
            # Kernel lock is released even after a crash; prevents overlapping manual/scheduled runs.
            lock_path=args.db.with_suffix('.lock')
            with lock_path.open('a+b') as lock:
                lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
                try:
                    if os.name=='nt':
                        import msvcrt
                        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except OSError:raise SystemExit('Another collector is running')
                reports=collect(store,config,args.source,args.max_details)
                print(json.dumps(reports,ensure_ascii=False,indent=2))
                if any(r['status']!='ok' for r in reports):raise SystemExit(2)
        elif args.command=='export':
            if bool(args.facet)!=bool(args.value):parser.error('--facet and --value must be used together')
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(store.export(args.location,args.facet,args.value),ensure_ascii=False,indent=2),encoding='utf-8')
            print(args.output)
        elif args.command=='candidates':
            rows=store.db.execute('SELECT url_a,url_b,score,reason FROM candidates ORDER BY score DESC').fetchall()
            print(json.dumps([dict(zip(('url_a','url_b','score','reason'),r)) for r in rows],ensure_ascii=False,indent=2))
        else:
            rows=store.db.execute('SELECT source,finished,status,details FROM runs WHERE id IN (SELECT MAX(id) FROM runs GROUP BY source)').fetchall()
            print(json.dumps([dict(zip(('source','finished','status','details'),r)) for r in rows],ensure_ascii=False,indent=2))
    finally:store.close()
