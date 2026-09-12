"""Self-contained, read-only HTML view of the local SQLite snapshot."""
from html import escape
import json
from urllib.parse import urlsplit
from .model import now
from .lifecycle import group_state, deadline_instant, deadline_state
from .platform_export import employment


def link(url, label):
    if urlsplit(url).scheme not in ('https','http'):
        return escape(label)
    return '<a target="_blank" rel="noopener noreferrer" href="'+escape(url,quote=True)+'">'+escape(label)+'</a>'


def render(store):
    groups=store.export()
    cards=[]
    for group in sorted(groups,key=lambda g:max(j['posted'] or j['first_seen'] for j in g['sources']),reverse=True):
        ads=group['sources']
        best=max(ads,key=lambda j:(not j['expired'],'incomplete' not in j['quality'],len(j['description'])))
        state,deadline=group_state(ads)
        expired=state=='istekao'
        instant=deadline_instant(deadline)
        expiry_ms=int(instant.timestamp()*1000) if instant else 0
        kind,kind_origin=employment(ads)
        posted=best['posted'] or next((j['posted'] for j in ads if j['posted']),'')
        places=', '.join(sorted({p for j in ads for p in j['locations']}))
        sources=', '.join(sorted({j['source'] for j in ads}))
        links=' · '.join(link(j['url'],j['source'])+' ['+escape(j['expires'] or 'rok nije naveden')+('; rok prošao' if j['expired'] else '')+']'+(' ('+link(j['structured']['original_url'],'original')+')' if j['structured'].get('original_url') and j['structured']['original_url']!=j['url'] else '') for j in ads)
        warning='Izvod sa liste — opis nije kompletan.' if 'incomplete' in best['quality'] else ''
        search=escape(' '.join([best['title'],best['employer'],places,sources]).lower(),quote=True)
        cards.append(f'''<article data-search="{search}" data-expired="{int(expired)}" data-deadline="{expiry_ms}" data-location="{escape(places,quote=True)}">
<h2>{escape(best['title'])}</h2><p><strong>{escape(best['employer'] or 'Poslodavac nije naveden')}</strong> · {escape(places)}</p>
<p>Tip zaposlenja: <strong>{escape(kind or 'nije naveden')}</strong>{' (prepoznato iz teksta)' if kind_origin=='prepoznato_u_tekstu' else ''}</p>
<p class="meta">Grupa {group['group_id']} · {len(ads)} izvornih objava · <span class="deadline-state">{'Istekao rok — arhiva' if expired else 'Rok nije istekao ili nije poznat'}</span> · Objavljeno: {escape(posted[:10] or 'nije navedeno')} · Rok: {escape(deadline or 'nije naveden')}</p>
<p>Izaberi gde čitaš oglas: {links}</p><p class="warning">{warning}</p><details><summary>Opis i podaci</summary>
<pre>{escape(best['description'])}</pre><p class="meta">Prvi put viđen: {escape(best['first_seen'][:10])} · Poslednji put viđen: {escape(best['last_seen'][:10])} · Kvalitet: {escape(best['quality'])}</p></details></article>''')
    runs=[]
    for source,finished,status,raw in store.db.execute('SELECT source,finished,status,details FROM runs WHERE id IN (SELECT MAX(id) FROM runs GROUP BY source) ORDER BY source'):
        data=json.loads(raw)
        issues='; '.join(e.get('error','') for e in data.get('errors',[])[:2]) or data.get('coverage_note','')
        runs.append('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in [source,status,finished[:19],data.get('saved',0),data.get('cached',0),data.get('outside_area',0),data.get('skipped',0),issues])+'</tr>')
    pairs=[]
    for a,b,score,reason in store.db.execute('SELECT url_a,url_b,score,reason FROM candidates ORDER BY score DESC'):
        pairs.append('<li>'+link(a,a)+'<br>'+link(b,b)+'<br>'+escape(reason)+f' ({score:.0%})</li>')
    total=sum(len(g['sources']) for g in groups)
    return '''<!doctype html><html lang="sr-Latn"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oglasi — pregled lokalne baze</title><style>
body{font:16px/1.55 system-ui,sans-serif;background:#f4f6f8;color:#172c3b;max-width:1150px;margin:35px auto;padding:0 20px}h1{font-size:30px}h2{font-size:20px;margin:0}article{background:white;padding:22px;margin:14px 0;border:1px solid #d9e1e6;border-radius:10px}a{color:#126b8a;overflow-wrap:anywhere}p{margin:7px 0}.meta{color:#5c6975;font-size:14px}pre{white-space:pre-wrap;font:inherit}.warning{color:#865900}input,select{font:inherit;padding:9px;border:1px solid #bbc8d0;border-radius:5px}input[type=search]{width:min(440px,90%)}table{border-collapse:collapse;font-size:13px}td,th{padding:8px;border-bottom:1px solid #d9e1e6;text-align:left;vertical-align:top}td:last-child{max-width:430px;overflow-wrap:anywhere}.scroll{overflow:auto}li{margin:15px 0}[hidden]{display:none!important}summary{cursor:pointer}label{display:inline-block;margin:6px}
</style><h1>Oglasi za posao</h1><p>Lokalna baza · Petrovaradin, Novi Sad i Sremski Karlovci</p>
<p>'''+f'{total} izvornih objava → {len(groups)} grupa · {total-len(groups)} spojenih duplikata · {len(pairs)} parova za proveru</p>'+'''
<p class="meta">Ovo je sačuvan pregled, ne živa veza sa bazom. Obnovi komandom <code>python main.py report</code>. Nepoznat rok ne potvrđuje da je posao još otvoren. Svi izvorni linkovi su sačuvani.</p>
<p class="meta">Generisano: '''+escape(now())+'''</p><details><summary>Poslednji rezultati izvora</summary><div class="scroll"><table><thead><tr><th>Izvor</th><th>Status</th><th>Vreme UTC</th><th>Sačuvano</th><th>Keš</th><th>Van područja</th><th>Preskočeno</th><th>Napomena</th></tr></thead><tbody>'''+''.join(runs)+'''</tbody></table></div></details>
<section><label><input id="q" type="search" placeholder="Naslov, poslodavac ili izvor" aria-label="Pretraga oglasa"></label>
<label><select id="location" aria-label="Lokacija"><option value="">Sve lokacije</option><option>Petrovaradin</option><option>Novi Sad</option><option>Sremski Karlovci</option></select></label>
<label><select id="view" aria-label="Vidljivost oglasa"><option value="visible">Vidljivi oglasi</option><option value="archive">Arhiva — istekao rok</option><option value="all">Svi oglasi</option></select></label><p id="count" aria-live="polite"></p></section>
<main>'''+''.join(cards)+'''</main><details><summary>Parovi koji zahtevaju proveru</summary><p>Ovi oglasi nisu automatski spojeni jer dokaz nije dovoljno pouzdan.</p><ul>'''+''.join(pairs)+'''</ul></details>
<script>
const q=document.querySelector('#q'),place=document.querySelector('#location'),view=document.querySelector('#view');
function filter(){let visible=0;document.querySelectorAll('article').forEach(card=>{const deadline=Number(card.dataset.deadline),ended=deadline>0&&deadline<=Date.now();card.dataset.expired=ended?'1':'0';card.querySelector('.deadline-state').textContent=ended?'Istekao rok — arhiva':(deadline?'Rok nije istekao':'Rok nije poznat');card.hidden=(view.value==='visible'&&ended)||(view.value==='archive'&&!ended)||!card.dataset.search.includes(q.value.toLowerCase().trim())||(place.value&&!card.dataset.location.includes(place.value));if(!card.hidden)visible++});document.querySelector('#count').textContent='Prikazano grupa: '+visible;}
[q,place,view].forEach(el=>el.addEventListener('input',filter));filter();setInterval(filter,60000);
</script></html>'''
