import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from protego import Protego

from oglasi.collector import Client, FetchError, collect
from oglasi.extra_sources import SkipJob, local_date, sbu_payload
from oglasi.parsers import listing, detail
from oglasi.model import Job
from oglasi.store import Store

CONFIG=json.loads((Path(__file__).resolve().parents[1]/'sources.json').read_text(encoding='utf-8'))
SOURCES={s['id']:s for s in CONFIG['sources']}


class ExpansionTests(unittest.TestCase):
    def test_failed_details_count_toward_smoke_limit(self):
        class FakeClient:
            def __init__(self,*args):pass
            def listing_page(self,*args):return '<a href="/job/1">One</a><a href="/job/2">Two</a>'
            def get(self,*args):raise FetchError('source unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            with patch('oglasi.collector.Client',FakeClient):
                reports=collect(store,{'sources':[{'id':'test','urls':['https://x.rs/list'],'detail_pattern':'/job/'}]},max_details=1)
            self.assertEqual(reports[0]['attempted'],1);self.assertEqual(len(reports[0]['errors']),1)
            self.assertTrue(reports[0]['truncated']);store.close()

    def test_parallel_sources_share_groups_without_sqlite_races(self):
        html='<a href="/job/1">Job</a>'
        jobhtml='<script type="application/ld+json">'+json.dumps({'@type':'JobPosting','title':'Developer','description':'Distinctive detailed description. '*10,'hiringOrganization':{'name':'Acme'},'jobLocation':{'address':{'addressLocality':'Novi Sad'}}})+'</script>'
        class FakeClient:
            def __init__(self,*args):pass
            def listing_page(self,*args):return html
            def get(self,*args):return jobhtml
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            cfg={'workers':4,'sources':[{'id':str(i),'urls':[f'https://source{i}.rs/list'],'detail_pattern':'/job/'} for i in range(4)]}
            with patch('oglasi.collector.Client',FakeClient):reports=collect(store,cfg)
            self.assertEqual([r['status'] for r in reports],['ok']*4)
            self.assertEqual(len(store.export()),1)
            self.assertEqual(len(store.export()[0]['sources']),4)
            store.close()

    def test_exclusion_cache_expires(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            store.exclude('s','url','outside_area')
            self.assertEqual(store.checked('s','url'),'outside_area')
            store.db.execute("UPDATE excluded SET checked_at='2000-01-01T00:00:00+00:00'");store.db.commit()
            self.assertIsNone(store.checked('s','url'));store.close()

    def test_report_escapes_source_content(self):
        from oglasi.report import render
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            store.save(Job('s','https://x.rs/1','<script>evil()</script>',description='<img onerror=evil()>',locations=['Novi Sad']))
            html=render(store)
            self.assertNotIn('<script>evil()',html);self.assertIn('&lt;script&gt;evil()',html)
            store.close()

    def test_original_permalink_groups_mirrors_with_incomplete_descriptions(self):
        from oglasi.dedup import match
        a=Job('a','https://a.rs/1','Prodavac','Acme','Preview',['Novi Sad'],structured={'original_url':'https://rs.jooble.org/jdp/123'},quality='description_incomplete').dict()
        b={**a,'url':'https://b.rs/2'}
        self.assertTrue(match(a,b)[0])
        b={**a,'url':'https://b.rs/2','structured':{'original_url':'https://rs.jooble.org/jdp/456'}}
        self.assertFalse(match(a,b)[0])

    def test_oglaszaposao_referral_html_fields(self):
        html='''<h1>Referent</h1><div class="ozp-job-company-info"><h2>Acme</h2></div>
        <div class="ozp-info-content"><span class="ozp-info-label">Lokacija</span><a href="/lokacija/novi-sad/">Novi Sad</a></div>
        <div class="ozp-info-content"><span class="ozp-info-label">Rok za Prijavu</span><span class="ozp-info-value">07.10.2026</span></div>
        <div class="ozp-section-box"><div class="ozp-section-content"><p>Opis posla...</p><a href="https://rs.jooble.org/jdp/123">Pogledajte originalni oglas</a></div></div>
        <span>Objavljeno: 04.09.2026.</span>'''
        job=detail(html,'https://oglaszaposao.rs/oglas/1',SOURCES['oglaszaposao'])
        self.assertEqual(job.locations,['Novi Sad']);self.assertEqual(job.posted,'2026-09-04')
        self.assertEqual(job.expires,'2026-10-07');self.assertIn('description_incomplete',job.quality)
        self.assertEqual(job.structured['original_url'],'https://rs.jooble.org/jdp/123')

    def test_sbu_robots_query_is_not_blanket_ban(self):
        robot=Protego.parse('User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\nDisallow: /?\nDisallow: */?')
        self.assertTrue(robot.can_fetch('https://sbu-poslovi.rs/oglasi-za-posao/','PetrovaradinJobs'))
        self.assertFalse(robot.can_fetch('https://sbu-poslovi.rs/oglasi-za-posao/?job_page=2','PetrovaradinJobs'))
        self.assertTrue(robot.can_fetch('https://sbu-poslovi.rs/wp-admin/admin-ajax.php','PetrovaradinJobs'))

    def test_adorio_forbidden_details_and_pagination(self):
        robot=Protego.parse('User-agent: *\nAllow: /\nDisallow: /*?\nDisallow: /oglas-za-posao/')
        self.assertTrue(robot.can_fetch(SOURCES['adorio']['urls'][0],'PetrovaradinJobs'))
        self.assertFalse(robot.can_fetch('https://www.adorio.rs/oglas-za-posao/123','PetrovaradinJobs'))
        self.assertFalse(robot.can_fetch('https://www.adorio.rs/poslovi?page=2','PetrovaradinJobs'))

    def test_redirect_checks_destination_robots(self):
        client=Client(delay=0)
        client.robots={'https://a.rs':Protego.parse(''), 'https://b.rs':Protego.parse('User-agent: *\nDisallow: /')}
        client.session.get=Mock(return_value=Mock(status_code=302,headers={'Location':'https://b.rs/private'}))
        with self.assertRaisesRegex(FetchError,'robots.txt disallows'):
            client.get('https://a.rs/job')
        self.assertEqual(client.session.get.call_count,1)

    def test_careerjet_challenge_is_not_empty_success(self):
        client=Client(delay=0);client.get=Mock(return_value='<h1>Potrebna je verifikacija</h1>')
        with self.assertRaisesRegex(FetchError,'access_verification_required'):
            client.listing_page(SOURCES['careerjet']['urls'][0],SOURCES['careerjet'])

    def test_joberty_pagination_and_allowlist(self):
        found,pages=listing(json.dumps({'items':[{'id':123}], 'totalPage':2}),SOURCES['joberty']['urls'][0],SOURCES['joberty'])
        self.assertIn('https://www.joberty.com/sr/job/123',found)
        self.assertIn('page=1',pages[0]);self.assertIn('location=Serbia',pages[0])
        job=detail(json.dumps({'id':123,'jobTitle':'Developer','companyName':'Acme','cities':['Novi Sad (Serbia)'],
                   'text':'<p>Python developer</p>','technologies':['Python'],'logo':'huge image','saved':False,
                   'applyUrl':'https://acme.rs/jobs/123','expirationDate':1791496800000}),next(iter(found)),SOURCES['joberty'])
        self.assertEqual(job.locations,['Novi Sad']);self.assertEqual(job.description,'Python developer')
        self.assertNotIn('logo',job.structured);self.assertNotIn('saved',job.structured)
        self.assertEqual(job.structured['original_url'],'https://acme.rs/jobs/123')

    def test_adorio_excerpts_are_explicit(self):
        html='<a href="/oglas-za-posao/1"><article><h2>Developer</h2><span class="g-pa-0">Acme · Novi Sad</span><div class="g-pr-25--lg">Short preview</div></article></a>'
        found,pages=listing(html,SOURCES['adorio']['urls'][0],SOURCES['adorio'])
        job=detail(json.dumps(next(iter(found.values()))),next(iter(found)),SOURCES['adorio'])
        self.assertEqual(job.locations,['Novi Sad']);self.assertEqual(job.employer,'Acme')
        self.assertIn('description_incomplete',job.quality);self.assertEqual(pages,[])

    def test_sbu_detail_location_beats_employer_and_navigation(self):
        html='''<nav>Novi Sad</nav><figure class="jobsearch-jobdetail-list"><figcaption><h1>Prodavac</h1>
        <span><a>Profil poslodavca: Novi Sad Company</a></span></figcaption></figure>
        <ul class="jobsearch-jobdetail-options"><li><i class="fa-map-marker"></i>Beograd</li>
        <li>Post Date 10. septembar 2026.</li><li>Prijavite se pre 20. septembar 2026.</li></ul>
        <div class="jobsearch-jobdetail-content"><div class="jobsearch-description">Rad u prodavnici.</div></div>'''
        job=detail(html,'https://sbu-poslovi.rs/posao/1',SOURCES['sbu'])
        self.assertEqual(job.locations,[]);self.assertEqual(job.expires,'2026-09-20')
        self.assertEqual(job.employer,'Novi Sad Company')
        job=detail(html.replace('</i>Beograd','</i>Petrovaradin'),'https://sbu-poslovi.rs/posao/1',SOURCES['sbu'])
        self.assertEqual(job.locations,['Petrovaradin'])

    def test_sbu_ajax_state_and_pagination(self):
        html='''<input id="job_page-42" name="job_page"><div id="job_arg42">abc</div><div id="job_small_arg42">def</div>
        <h2 class="jobsearch-pst-title"><a href="/posao/test/">Job</a></h2>
        <a onclick="jobsearch_job_pagenation_ajax('job_page', '3', '42', 'false', '');">3</a>'''
        self.assertEqual(sbu_payload(html)['job_arg'],'abc')
        found,pages=listing(html,SOURCES['sbu']['urls'][0]+'#sbu-page=2',SOURCES['sbu'])
        self.assertEqual(len(found),1);self.assertTrue(pages[0].endswith('#sbu-page=3'))

    def test_sbu_explicit_workplace_overrides_agency_map(self):
        html='''<h1>Promocija i prodaja – Novi Sad</h1><ul class="jobsearch-jobdetail-options">
        <li><i class="fa-map-marker"></i>Belgrade, Serbia</li></ul>
        <div class="jobsearch-jobdetail-content"><div class="jobsearch-description">Promocija proizvoda. 📍 Novi Sad. Smenski rad.</div></div>'''
        job=detail(html,'https://sbu-poslovi.rs/posao/test',SOURCES['sbu'])
        self.assertEqual(job.locations,['Novi Sad'])
        self.assertEqual(job.structured['source_map_location'],'Belgrade, Serbia')
        self.assertIn('location_conflict_review',job.quality)

    def test_sbu_removed_job_redirect_is_not_a_description(self):
        with self.assertRaisesRegex(SkipJob,'unavailable_redirected_to_listing'):
            detail('<h1>Oglasi za posao</h1><h2 class="jobsearch-pst-title">Other job</h2>',
                   'https://sbu-poslovi.rs/posao/removed',SOURCES['sbu'])

    def test_sljaka_query_identity_and_dates(self):
        html='<article><a href="/?post_type=noo_job&p=12">Posao</a></article><a class="page-numbers" href="?location%5B0%5D=novi-sad&paged=2">2</a>'
        found,pages=listing(html,SOURCES['sljaka']['urls'][0],SOURCES['sljaka'])
        self.assertEqual(len(found),1);self.assertIn('p=12',next(iter(found)))
        self.assertIn('novi-sad',pages[0])
        self.assertEqual(local_date(' - septembar 29, 2026'),'2026-09-29')
        self.assertEqual(local_date('10. septembar 2026.'),'2026-09-10')

    def test_manpower_district_is_not_novi_sad(self):
        html='<div class="job-posts-page"><h1>Radnik</h1><div class="job-city">Južnobački okrug</div><h6>Opis</h6><p>Rad u proizvodnji.</p></div>'
        job=detail(html,'https://www.manpower.rs/sr/job-posts/1',SOURCES['manpower'])
        self.assertEqual(job.locations,[]);self.assertEqual(job.employer,'')
        job=detail(html.replace('Južnobački okrug','Novi Sad'),job.url,SOURCES['manpower'])
        self.assertEqual(job.locations,['Novi Sad'])

    def test_paz_demo_and_action_links(self):
        html='<a href="/index.php?page=item&id=123">Job</a><a href="/index.php?page=item&action=item_add">Add</a>'
        found,_=listing(html,SOURCES['paz']['urls'][0],SOURCES['paz'])
        self.assertEqual(len(found),1)
        with self.assertRaises(SkipJob):
            detail('<h1>Job</h1><aside class="hua-synthetic-demo-notice">Demo</aside>',next(iter(found)),SOURCES['paz'])

    def test_oglaszaposao_pagination(self):
        found,pages=listing('<a href="/oglas/kuvar/">Kuvar</a><a href="/lokacija/novi-sad/page/2/">2</a>',SOURCES['oglaszaposao']['urls'][0],SOURCES['oglaszaposao'])
        self.assertEqual(len(found),1);self.assertTrue(pages[0].endswith('/page/2/'))

    def test_dedup_without_dates_and_recheck_existing_ad(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            def job(url,description='Long enough distinctive job description. '*10,employer='Acme d.o.o.'):
                return Job('test',url,'Python developer',employer,description,['Novi Sad'])
            a=job('https://a.rs/1');g=store.save(a)
            self.assertEqual(store.save(job('https://b.rs/1',employer='Acme DOO')),g)
            c=job('https://c.rs/1','Different job content. '*12);self.assertNotEqual(store.save(c),g)
            c.description=a.description;self.assertEqual(store.save(c),g)
            self.assertEqual(len(store.export()),1)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0],0)
            before=store.db.execute('SELECT url,fetched_at,last_seen FROM ads ORDER BY url').fetchall()
            store.reconcile()
            self.assertEqual(before,store.db.execute('SELECT url,fetched_at,last_seen FROM ads ORDER BY url').fetchall())
            store.close()

    def test_dedup_does_not_merge_reposts_or_excerpts(self):
        from oglasi.dedup import match
        a=Job('a','https://a.rs/1','Developer','Acme','Description '*40,['Novi Sad'],posted='2026-01-01').dict()
        b={**a,'url':'https://b.rs/1','posted':'2026-09-01'}
        self.assertFalse(match(a,b)[0])
        b['posted']='';b['quality']='listing_excerpt;description_incomplete'
        self.assertFalse(match(a,b)[0])
        b['quality']='html';b['employer']='Other company'
        self.assertFalse(match(a,b)[0])

    def test_title_context_and_truncated_employer(self):
        from oglasi.dedup import match,title_key
        self.assertEqual(title_key('Prodavac (m/ž), Novi Sad grad'),'prodavac')
        a=Job('a','https://a.rs/1','Prodavac','Example Company','Unique description. '*20,['Novi Sad']).dict()
        b={**a,'url':'https://b.rs/1','title':'Prodavac (m/ž), Novi Sad grad'}
        self.assertTrue(match(a,b)[0])
        b={**b,'employer':'Example Comp...','quality':'description_incomplete'}
        automatic,score,reason=match(a,b)
        self.assertFalse(automatic);self.assertGreaterEqual(score,.82);self.assertIn('truncated_employer',reason)


if __name__=='__main__':unittest.main()
