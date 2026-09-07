import re
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

CYR = dict(zip('абвгдђежзијклљмнњопрстћуфхцчџш',
               ['a','b','v','g','d','dj','e','z','z','i','j','k','l','lj','m','n','nj','o','p','r','s','t','c','u','f','h','c','c','dz','s']))
LOCATIONS = {'petrovaradin':'Petrovaradin', 'novi sad':'Novi Sad', 'sremski karlovci':'Sremski Karlovci'}
NS_SETTLEMENTS = ('sremska kamenica','futog','veternik','rumenka','kac','budisava','kovilj','cenej','kisac','stepanovicevo','begec','bukovac','ledinci','stari ledinci')

def norm(value):
    value = ''.join(CYR.get(c,c) for c in str(value or '').lower()).replace('đ','dj')
    return ' '.join(re.sub(r'[^a-z0-9+#]+',' ', ''.join(c for c in unicodedata.normalize('NFKD',value) if not unicodedata.combining(c))).split())

def locations(value):
    text = ' ' + norm(value) + ' '
    matched={label for key,label in LOCATIONS.items() if ' '+key+' ' in text}
    if any(' '+name+' ' in text for name in NS_SETTLEMENTS):matched.add('Novi Sad')
    return sorted(matched)

def canonical(url):
    p=urlsplit(url)
    # Keep identity parameters, strip only known analytics/search context parameters.
    ignored={'city','disable_saved_search','show_more','ilist','elist','item_index','kid','dist','sort','selected_city_id'}
    q=[(k,v) for k,v in parse_qsl(p.query) if k not in ignored and not k.startswith(('utm_','trigger_','hot_slot','esource','emedium'))]
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/'),urlencode(sorted(q)),''))

def now():
    return datetime.now(timezone.utc).isoformat()

@dataclass
class Job:
    source: str
    url: str
    title: str
    employer: str = ''
    description: str = ''
    locations: list = field(default_factory=list)
    location_raw: str = ''
    posted: str = ''
    expires: str = ''
    facets: dict = field(default_factory=dict)
    structured: dict = field(default_factory=dict)
    quality: str = 'structured'

    def dict(self):
        return asdict(self)

def enrich(job):
    text=norm(job.title+' '+job.description)
    rules={
      'skills': {'Python':r'\bpython\b','SQL':r'\bsql\b','Excel':r'\bexcel\b','Java':r'\bjava\b','JavaScript':r'\bjavascript\b','React':r'\breact\b','engleski':r'\b(englesk\w*|english)\b','nemački':r'\b(nemack\w*|german)\b','vozačka B':r'\bb kategorij\w*\b','vozačka C':r'\bc kategorij\w*\b','vozačka E':r'\be kategorij\w*\b'},
      'category': {'IT':r'\b(developer|programer|software|qa engineer)\b','ugostiteljstvo':r'\b(kuvar\w*|konobar\w*|sanker\w*|pica majstor\w*)\b','trgovina':r'\b(prodava\w*|trgovac|kasir\w*|komercijalist\w*)\b','transport i logistika':r'\b(vozac\w*|magacioner\w*|viljuskar\w*)\b','zdravstvo':r'\b(medicinsk\w*|lekar\w*|stomatolos\w*)\b','obrazovanje':r'\b(nastavnik\w*|vaspitac\w*|ucitelj\w*)\b','administracija':r'\b(administracij\w*|racunovod\w*|knjigovod\w*)\b'},
      'contract_type': {'neodređeno':r'\bneodredjeno\b','određeno':r'\bodredjeno\b','privremeni i povremeni':r'\bprivremen\w* i povremen\w*\b','praksa':r'\b(praksa|internship)\b','sezonski':r'\bsezonsk\w*\b'},
      'work_time': {'puno':r'\b(puno radno vreme|full time)\b','nepuno':r'\b(nepuno radno vreme|part time)\b'},
      'work_mode': {'remote':r'\b(rad od kuce|remote|telecommute)\b','hybrid':r'\b(hibrid\w*|hybrid)\b'},
    }
    for kind, ruleset in rules.items():
        haystack=norm(job.title) if kind=='category' else text+' '+norm(job.structured.get('employmentType',''))+' '+norm(job.structured.get('workHours',''))
        values=[label for label,pattern in ruleset.items() if re.search(pattern,haystack)]
        if values: job.facets[kind]={'values':values,'method':'keyword','review_required':True}
    for key in ('employmentType','workHours','skills','qualifications','educationRequirements','experienceRequirements','baseSalary','salaryCurrency','jobBenefits','occupationalCategory','jobLocationType','responsibilities'):
        if job.structured.get(key): job.facets[key]={'value':job.structured[key],'method':'source'}
    return job
