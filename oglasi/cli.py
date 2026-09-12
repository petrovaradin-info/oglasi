import argparse
import json
import logging
import os
import sys
import signal
from threading import Event
from pathlib import Path
from datetime import datetime
from .store import Store
from .collector import collect

ROOT=Path(__file__).resolve().parent.parent

def main():
    parser=argparse.ArgumentParser(description='Oglasi: Petrovaradin, Novi Sad, Sremski Karlovci')
    parser.add_argument('--db',type=Path,default=ROOT/'data'/'oglasi.sqlite3')
    sub=parser.add_subparsers(dest='command',required=True)
    run=sub.add_parser('collect');run.add_argument('--source',action='append');run.add_argument('--max-details',type=int)
    run.add_argument('--workers',type=int,choices=range(1,9))
    run.add_argument('--refresh',action='store_true',help='Recheck known and excluded ads regardless of their cache age')
    export=sub.add_parser('export');export.add_argument('--location');export.add_argument('--facet');export.add_argument('--value');export.add_argument('--output',type=Path)
    export.add_argument('--format',choices=['full-json','platform-json','csv'],default='full-json')
    export.add_argument('--exclude-expired',action='store_true',help='Exclude groups with all known deadlines expired; unknown deadlines remain')
    export.add_argument('--archive-only',action='store_true',help='Export only expired groups')
    sub.add_parser('status');sub.add_parser('sources');sub.add_parser('candidates')
    sub.add_parser('deduplicate')
    report=sub.add_parser('report');report.add_argument('--output',type=Path,default=ROOT/'data'/'oglasi-pregled.html')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,stream=sys.stdout,format='%(asctime)s %(levelname)s %(message)s')
    config=json.loads((ROOT/'sources.json').read_text(encoding='utf-8'))
    if args.command=='sources':print(json.dumps(config,ensure_ascii=False,indent=2));return
    store=Store(args.db)
    file_handler=None
    try:
        if args.command=='collect':
            log_path=args.log_file or ROOT/'logs'/('collect-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-'+str(os.getpid())+'.log')
            log_path.parent.mkdir(parents=True,exist_ok=True)
            file_handler=logging.FileHandler(log_path,encoding='utf-8')
            file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            logging.getLogger().addHandler(file_handler)
            logging.info('LOG FILE: %s',log_path.resolve())
        if args.command in ('collect','deduplicate'):
            if args.command=='collect':
                if args.source and set(args.source)-{s['id'] for s in config['sources']}:parser.error('Unknown source')
                if args.max_details is not None and args.max_details<1:parser.error('--max-details must be positive')
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
                if args.command=='deduplicate':print(json.dumps(store.reconcile(),ensure_ascii=False,indent=2))
                else:
                    if args.workers:config['workers']=args.workers
                    if args.refresh:config['refresh_hours']=0
                    stop_event=Event()
                    def interrupt(signum,frame):
                        if not stop_event.is_set():
                            logging.warning('Prekid zatrazen. Cekam aktivne zahteve; sacuvani oglasi ostaju u bazi.')
                        stop_event.set()
                    previous=signal.signal(signal.SIGINT,interrupt)
                    try:reports=collect(store,config,args.source,args.max_details,stop_event=stop_event)
                    finally:signal.signal(signal.SIGINT,previous)
                    print(json.dumps(reports,ensure_ascii=False,indent=2))
                    if stop_event.is_set():raise SystemExit(130)
                    if any(r['status']!='ok' for r in reports):raise SystemExit(2)
        elif args.command=='report':
            from .report import render
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(render(store),encoding='utf-8')
            print(args.output)
        elif args.command=='export':
            if bool(args.facet)!=bool(args.value):parser.error('--facet and --value must be used together')
            from .platform_export import cards, write_csv
            from .lifecycle import group_state
            if args.exclude_expired and args.archive_only:parser.error('Choose either --exclude-expired or --archive-only')
            args.output=args.output or ROOT/'data'/({'full-json':'oglasi.json','platform-json':'poslovi-platforma.json','csv':'poslovi-platforma.csv'}[args.format])
            args.output.parent.mkdir(parents=True,exist_ok=True)
            groups=store.export(args.location,args.facet,args.value)
            if args.exclude_expired:groups=[g for g in groups if group_state(g['sources'])[0]!='istekao']
            if args.archive_only:groups=[g for g in groups if group_state(g['sources'])[0]=='istekao']
            rows=groups if args.format=='full-json' else cards(groups)
            if args.format=='csv':write_csv(args.output,rows)
            else:args.output.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
            print(args.output)
        elif args.command=='candidates':
            rows=store.db.execute('SELECT url_a,url_b,score,reason FROM candidates ORDER BY score DESC').fetchall()
            print(json.dumps([dict(zip(('url_a','url_b','score','reason'),r)) for r in rows],ensure_ascii=False,indent=2))
        else:
            rows=store.db.execute('SELECT source,finished,status,details FROM runs WHERE id IN (SELECT MAX(id) FROM runs GROUP BY source)').fetchall()
            print(json.dumps([dict(zip(('source','finished','status','details'),r)) for r in rows],ensure_ascii=False,indent=2))
    finally:
        store.close()
        if file_handler:
            logging.getLogger().removeHandler(file_handler)
            file_handler.close()
