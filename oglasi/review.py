"""Read-only review of publication exclusions and cross-source candidate pairs."""
from datetime import datetime, timezone
from html import escape
from itertools import combinations
from .dedup import match
from .lifecycle import group_state
from .platform_export import web_url
from .publication import publication_state

REASONS = {
    'nije_skoro_pronadjen': 'Nije skoro pronađen na izvoru',
    'proveriti_spajanje': 'Proveriti postojeće spajanje',
    'possible_reposted_job; needs_review': 'Moguć ponovljen konkurs istog izvora',
    'similar_job_different_dates': 'Datumi objave udaljeni više od 30 dana',
    'same_employer_location_similar_title; needs_review': 'Sličan naslov i poslodavac; nedovoljno dokaza',
    'truncated_employer_similar_title_location; needs_review': 'Skraćen naziv poslodavca',
}

def source_card(ad):
    return {key: ad.get(key, '') for key in (
        'source', 'url', 'title', 'employer', 'locations', 'posted', 'expires',
        'last_seen', 'fetched_at', 'description', 'quality')}

def review_document(store, at=None):
    at = at or datetime.now(timezone.utc)
    groups = store.export()
    by_url = {ad['url']: (g['group_id'], ad) for g in groups for ad in g['sources']}
    states = {g['group_id']: group_state(g['sources'], at)[0] for g in groups}
    blocked, stale, candidates = [], [], []
    for group in groups:
        ads = group['sources']
        if states[group['group_id']] == 'istekao': continue
        policy = publication_state(ads, at)
        if 'proveriti_spajanje' in policy['razlozi']:
            conflicts = []
            for a, b in combinations(ads, 2):
                automatic, score, reason = match(a, b)
                if not automatic:
                    conflicts.append({'url_a': a['url'], 'url_b': b['url'],
                                      'reason': reason or 'insufficient_evidence', 'score': score})
            blocked.append({'group_id': group['group_id'], 'reasons': policy['razlozi'],
                            'sources': [source_card(a) for a in ads], 'conflicts': conflicts})
        if 'nije_skoro_pronadjen' in policy['razlozi']:
            stale.append({'group_id': group['group_id'], 'last_seen': policy['poslednji_pronalazak'],
                          'sources': [source_card(a) for a in ads]})
    for a, b, _, _ in store.db.execute('SELECT url_a,url_b,score,reason FROM candidates ORDER BY score DESC,url_a,url_b'):
        if a not in by_url or b not in by_url: continue
        ga, aa = by_url[a]; gb, bb = by_url[b]
        if ga == gb or aa['source'] == bb['source']: continue
        if states[ga] == states[gb] == 'istekao': continue
        automatic, score, reason = match(aa, bb)
        if not automatic and score < .82: continue
        candidates.append({'group_ids': [ga, gb], 'sources': [source_card(aa), source_card(bb)],
                           'automatic_match': automatic, 'reason': reason, 'score': score})
    return {'schema_version': '1.0', 'generated_at': at.isoformat(),
            'counts': {'blocked_groups': len(blocked), 'stale_groups': len(stale),
                       'cross_source_pairs': len(candidates)},
            'blocked_groups': blocked, 'stale_groups': stale, 'cross_source_pairs': candidates}

def render_review(document):
    def text(value): return escape(str(value))
    def source(ad):
        url = web_url(ad['url'])
        title = text(ad['title'])
        anchor = '<a target="_blank" rel="noopener noreferrer" href="'+escape(url, quote=True)+'">'+title+'</a>' if url else title
        return '<section><h3>'+anchor+'</h3><p>'+text(ad['source'])+' · '+text(ad['employer'])+'</p><p>'+text(', '.join(ad['locations']))+'</p><dl>'+''.join(
            '<dt>'+label+'</dt><dd>'+text(ad.get(key) or 'nije navedeno')+'</dd>' for key, label in (
                ('posted','Datum objave'), ('expires','Rok prijave'),
                ('last_seen','Poslednji pronalazak'), ('fetched_at','Uspešno čitanje'))
        )+'</dl><details><summary>Uporedi pun opis</summary><pre>'+text(ad['description'])+'</pre></details></section>'
    blocks = []
    for key, heading in (('blocked_groups', 'Postojeće grupe za proveru'),
                         ('cross_source_pairs', 'Mogući duplikati sa različitih izvora'),
                         ('stale_groups', 'Oglasi bez roka koji nisu skoro pronađeni')):
        blocks.append('<h2>'+heading+' ('+str(len(document[key]))+')</h2>')
        for item in document[key]:
            identity = item.get('group_id', item.get('group_ids'))
            reasons = item.get('reasons', [item.get('reason', 'nije_skoro_pronadjen')])
            conflicts = item.get('conflicts', [])
            blocks.append('<article><h3>Grupa '+text(identity)+'</h3><p>'+text('; '.join(REASONS.get(r,r) for r in reasons))+'</p>')
            for conflict in conflicts:
                blocks.append('<p>'+text(REASONS.get(conflict['reason'],conflict['reason']))+'<br>'+text(conflict['url_a'])+'<br>'+text(conflict['url_b'])+'</p>')
            blocks.append('<div class="compare">'+''.join(source(a) for a in item['sources'])+'</div></article>')
    return """<!doctype html><html lang="sr-Latn"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Provera oglasa</title>
<style>body{font:16px/1.5 system-ui;max-width:1200px;margin:30px auto;padding:0 20px;background:#f5f7f8;color:#172c3b}article{background:white;border:1px solid #cbd5df;padding:20px;margin:16px 0;border-radius:8px}.compare{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:24px}a{color:#126b8a}pre{white-space:pre-wrap;font:inherit}p,a,dd{overflow-wrap:anywhere}dt{font-weight:bold}dd{margin-left:0}summary{cursor:pointer}</style>
<h1>Provera oglasa pre objave</h1><p>Ovaj pregled ne menja bazu. Uporedi poslodavca, lokaciju, datume i sadržaj.
Sličan naslov nije dokaz istog konkursa. Neproveren par nije automatski duplikat.
Grupe se mogu pojaviti u više odeljaka. Istekle grupe su izostavljene, osim kada su deo para sa neisteklom grupom.</p>
<p>Generisano: """+text(document['generated_at'])+'</p>'+''.join(blocks)+'</html>'
