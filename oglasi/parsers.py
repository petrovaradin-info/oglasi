import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit, parse_qsl, urlencode, urlunsplit
from bs4 import BeautifulSoup
from .model import Job, canonical, locations, enrich
from .extra_sources import extra_listing, extra_detail, extra_html_fields

def text(node): return node.get_text(' ',strip=True) if node else ''

def empty_listing(html,source):
    if source['id']=='lako':
        data=json.loads(html)
        return data.get('data')==[] and data.get('meta',{}).get('totalItems')==0
    if source['id']=='halo':
        soup=BeautifulSoup(html,'html.parser')
        return any(text(n)=='Trenutno nema rezultata za zadati pojam pretrage.' for n in soup.select('.no-res-header'))
    if source['id']=='infostud':
        soup=BeautifulSoup(html,'html.parser');heading=soup.select_one('h1')
        return bool(heading and re.search(r'\(0 rezultata\)',text(heading.parent)))
    return False

def sections(node):
    if not node:return {}
    result={};current='description'
    for child in node.children:
        if not getattr(child,'name',None):continue
        content=text(child)
        if not content:continue
        bold=child.find(['strong','b'])
        heading=child.name in ['h2','h3','h4'] or (child.name=='p' and bold and text(bold)==content and content.endswith(':') and len(content)<120)
        if heading:current=content.rstrip(':')
        else:result.setdefault(current,[]).append(content)
    return {key:'\n'.join(value) for key,value in result.items()}

def walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():yield from walk(child)
    elif isinstance(value,list):
        for child in value:yield from walk(child)

def schema(soup):
    for script in soup.select('script[type="application/ld+json"]'):
        try:yield from walk(json.loads(script.get_text()))
        except (ValueError,TypeError):continue

def listing(html,url,source):
    extra=extra_listing(html,url,source) if source.get('id') else None
    if extra is not None:return extra
    if source.get('id')=='mjob':
        data=json.loads(html);p=urlsplit(url);params=dict(parse_qsl(p.query))
        rows=data['jobs'];pages=[]
        page=int(params.get('page',1));limit=int(params.get('limit',50))
        if rows and page*limit<int(data['total']):
            params['page']=str(page+1);pages=[urlunsplit((p.scheme,p.netloc,p.path,urlencode(params),''))]
        return {'https://www.mjob.rs/poslovi-za-studente/informacije/'+str(row['id']):row for row in rows if row.get('active')},pages
    if source.get('id')=='lako':
        data=json.loads(html)
        found={'https://www.lakodoposla.com/oglasi/'+str(row['slug']):row['positionTitle'] for row in data['data']}
        p=urlsplit(url);params=dict(parse_qsl(p.query));pages=[]
        if data.get('meta',{}).get('hasMorePages'):
            params['page']=str(int(params.get('page',1))+1)
            pages=[urlunsplit((p.scheme,p.netloc,p.path,urlencode(params),''))]
        return found,pages
    soup=BeautifulSoup(html,'html.parser'); found={}; pages=[]
    if source.get('id')=='infostud' and text(soup.select_one('h1'))=='Posao':
        raise ValueError('Infostud returned an unfiltered search; verify the location URL')
    pattern=source['detail_pattern']
    selector=source.get('listing_selector','a[href], [onclick]')
    if source.get('id')=='infostud':selector='h2, '+selector
    for node in soup.select(selector):
        # Infostud appends nationwide suggestions and expands pagination after
        # exhausting the requested city. They are not results of this search.
        if source.get('id')=='infostud' and node.name=='h2':
            if text(node)=='Dodatna ponuda poslova':
                pages=[]
                break
            continue
        href=node.get('href','')
        if not href:
            match=re.search(r"(?:document\.)?location\.href\s*=\s*['\"]([^'\"]+)",node.get('onclick',''))
            if match:href=match[1]
        target=urljoin(url,href)
        if urlsplit(target).netloc!=urlsplit(url).netloc:continue
        if urlsplit(target).scheme not in ('http','https'):continue
        is_detail=bool(re.search(pattern,urlsplit(target).path))
        if source.get('detail_query_pattern') and re.search(source['detail_query_pattern'],urlsplit(target).query):is_detail=True
        if is_detail:
            target=canonical(target)
            found[target]=text(node)
        elif (node.get('rel') and 'next' in node.get('rel')) or (text(node).isdigit() or text(node) in ['›','»','Sledeća','Sledeca','Next']):
            same_listing=urlsplit(target).path==urlsplit(url).path
            paginated=bool(source.get('pagination_pattern') and re.search(source['pagination_pattern'],urlsplit(target).path))
            if (same_listing or paginated) and target!=url:pages.append(target)
    return found,list(dict.fromkeys(pages))

def detail(html,url,source):
    extra=extra_detail(html,url,source)
    if extra is not None:return extra
    if source['id']=='mjob':return mjob_detail(json.loads(html),url)
    if source['id']=='lako':return lako_detail(json.loads(html)['data'],url)
    soup=BeautifulSoup(html,'html.parser')
    jobdata=next((d for d in schema(soup) if d.get('@type')=='JobPosting' or isinstance(d.get('@type'),list) and 'JobPosting' in d['@type']),{})
    extra_html_fields(soup,source,jobdata)
    for tag in soup.select('script, style, nav, footer, .hidden'):tag.decompose()
    title=text(soup.select_one(source.get('title_selector','h1'))) or jobdata.get('title','')
    if not title: raise ValueError('Missing job title; page changed or unavailable')
    description_node=soup.select_one(source.get('description_selector','[itemprop="description"], .__mtc-description, .job-description'))
    description=text(description_node) or text(BeautifulSoup(jobdata.get('description',''),'html.parser'))
    extracted_sections=sections(description_node)
    if extracted_sections:jobdata['sections']=extracted_sections
    employer=jobdata.get('hiringOrganization') or {}
    employer=employer.get('name','') if isinstance(employer,dict) else str(employer)
    if not employer and source.get('employer_selector'):employer=text(soup.select_one(source['employer_selector']))
    if source['id']=='sbu':employer=employer.removeprefix('Profil poslodavca:').strip()
    if source['id']=='nsz':
        labels={}
        for row in soup.select('.job-requirements .table-row'):
            cells=row.select('.table-col')
            if len(cells)==2:labels[text(cells[0])]=text(cells[1])
        jobdata['source_fields']=labels
        for label,key in [('Врста рада:','employmentType'),('Радно искуство:','experienceRequirements'),('Степен образовања:','educationRequirements'),('Језик:','skills')]:
            jobdata[key]=labels.get(label,'')
        dates=re.findall(r'\d{2}\.\d{2}\.\d{4}',labels.get('Временско трајање огласа за посао:',''))
        if len(dates)==2:
            jobdata['datePosted'],jobdata['validThrough']=[datetime.strptime(d,'%d.%m.%Y').date().isoformat() for d in dates]
    if source['id']=='poslovi':
        # The title contains explicit employer/city fields, unlike a URL slug.
        parts=text(soup.title).split(' | ')
        if len(parts)>=4:employer=parts[-3]
        for heading in soup.select('.job-positions h6'):
            sibling=heading.find_next_sibling()
            if sibling:jobdata.setdefault('source_fields',{})[text(heading)]=text(sibling)
    location_parts=[]
    places=jobdata.get('jobLocation',[])
    if isinstance(places,dict): places=[places]
    for place in places if isinstance(places,list) else []:
        if not isinstance(place,dict):continue
        address=place.get('address',{})
        if isinstance(address,str):location_parts.append(address)
        elif isinstance(address,dict):
            locality=address.get('addressLocality',[])
            location_parts.extend(locality if isinstance(locality,list) else [locality])
        if place.get('name'):location_parts.append(place['name'])
    if not location_parts and source.get('location_selector'):
        location_parts=[text(n) for n in soup.select(source['location_selector'])]
    # Only job-scoped text is used, never navigation/footer or an employer's headquarters.
    location_raw=', '.join(str(v) for v in location_parts if v)
    area=locations(location_raw)
    quality='structured' if jobdata else 'html'
    if jobdata.get('description_incomplete'):quality+=';description_incomplete;referral'
    if not location_raw:
        area=locations(title+' '+description); quality+=';location_from_text'
    job=Job(source['id'],canonical(url),title,employer,description,area,location_raw,
            str(jobdata.get('datePosted') or ''),str(jobdata.get('validThrough') or ''),structured=jobdata,quality=quality)
    if source['id']=='sbu':
        # Some SBU ads put the agency's Belgrade office in the map metadata.
        # A job-scoped explicit workplace, or agreeing title AND description,
        # takes precedence while retaining the conflicting map value for review.
        explicit=re.search(r'(?:mesto rada|lokacija(?: posla)?|📍)\s*[:\-]?\s*(Novi Sad|Petrovaradin|Sremski Karlovci)\b',description,re.I)
        stated=locations(explicit[1]) if explicit else sorted(set(locations(title)) & set(locations(description)))
        if stated and set(stated)!=set(job.locations):
            job.structured['source_map_location']=location_raw
            job.locations=stated
            job.location_raw=', '.join(stated)
            job.quality+=';location_from_text;location_conflict_review'
    if source['id']=='bulevar':
        job.employer='Omladinska zadruga Bulevar'
        conditions=text(soup.select_one('#comp-mkaxx06g'))
        job.description+='\n\n'+conditions
        job.structured['sections']={'description':description,'conditions':conditions}
        job.structured['baseSalary']=text(soup.select_one('#comp-mkaxvimw'))
    if source['id']=='kariera' and not description:
        target=soup.select_one('.apply a[href]')
        if target:
            job.structured['original_url']=urljoin(url,target['href'])
            job.quality='referral;description_missing'
            return enrich(job)
    if not job.description:raise ValueError('Missing job description; parser needs attention')
    return enrich(job)

def lako_detail(data,url):
    # Explicit allowlist: the upstream response contains unrelated account fields.
    def label(value):
        if isinstance(value,list):return [label(x) for x in value]
        return value.get('name',value.get('label','')) if isinstance(value,dict) else value
    structured={}
    for raw,key in [('contractType','employmentType'),('categories','occupationalCategory'),('educationLevel','educationRequirements'),('careerLevels','experienceRequirements'),('salaryRange','baseSalary'),('workModel','jobLocationType'),('keywords','skills')]:
        if data.get(raw):structured[key]=label(data[raw])
    sections={k:text(BeautifulSoup(data.get(k) or '','html.parser')) for k in ['jobDescription','conditionsDescription','offersDescription','additionalDescription']}
    structured['sections']=sections
    def date(value):
        try:return datetime.strptime(value,'%d.%m.%Y').date().isoformat()
        except (ValueError,TypeError):return ''
    location_raw=data.get('locationName') or ', '.join(label(data.get('locations',[])))
    job=Job('lako',canonical(url),data['positionTitle'],data.get('employerName',''), '\n\n'.join(v for v in sections.values() if v),locations(location_raw),location_raw,date(data.get('date')),date(data.get('expiryDate')),structured=structured,quality='api')
    if not job.description:job.quality='api;description_missing'
    return enrich(job)

def mjob_detail(data,url):
    info=data.get('information') or {};requirements=data.get('requirements') or {}
    place=info.get('workPlace') or {};city=place.get('item') or {}
    location_raw=', '.join(str(x) for x in [city.get('name'),info.get('location')] if x)
    sections={key:info.get(key) or '' for key in ['description','requiredSkills','companyOffers','additionalConditions','note']}
    structured={'sections':sections,'datePosted':data.get('publishDate')}
    for raw,key in [('payment','baseSalary'),('workShift','workHours'),('workType','occupationalCategory'),('requiredSkills','skills'),('numberOfPositions','totalJobOpenings')]:
        value=info.get(raw)
        if isinstance(value,dict) and 'name' in value:value=value['name']
        if value:structured[key]=value
    if requirements.get('educationalLevel'):structured['educationRequirements']=requirements['educationalLevel']
    job=Job('mjob',canonical(url),data['title'],(data.get('company') or {}).get('name','').strip(),'\n\n'.join(v for v in sections.values() if v),locations(location_raw),location_raw,str(data.get('publishDate') or ''),structured=structured,quality='api')
    return enrich(job)
