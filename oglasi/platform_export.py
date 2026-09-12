"""Small job cards for downstream platforms; original ads retain full content."""
import csv
import json
from urllib.parse import urlsplit
from .lifecycle import deadline_state, group_state


FIELDS=('id','naslov','kategorija','poslodavac','lokacija','opis','tip_zaposlenja','tip_zaposlenja_poreklo','plata',
        'link','datum_objave','rok_prijave','status','vidljiv','arhiviran',
        'slika_url','kontakt_ime','kontakt_email','kontakt_tel','izvori')


def web_url(value):
    return value if isinstance(value,str) and urlsplit(value).scheme in ('http','https') and urlsplit(value).netloc else ''


def label(value):
    if isinstance(value,str):return value
    if isinstance(value,list):return ', '.join(filter(None,(label(v) for v in value)))
    if isinstance(value,dict):return str(value.get('name') or '')
    return ''


def salary(data):
    value=data.get('baseSalary')
    if isinstance(value,str):return value
    if isinstance(value,(int,float)):return str(value)+' '+str(data.get('salaryCurrency') or '')
    if not isinstance(value,dict):return ''
    currency=value.get('currency') or data.get('salaryCurrency') or ''
    amount=value.get('value')
    unit=''
    if isinstance(amount,dict):
        unit=amount.get('unitText') or ''
        low,high=amount.get('minValue'),amount.get('maxValue')
        amount=amount.get('value')
        if amount is None:
            amount=f'{low}–{high}' if low is not None and high is not None else (f'od {low}' if low is not None else (f'do {high}' if high is not None else None))
    if amount is None:return ''
    return ' '.join(str(v) for v in (amount,currency,unit) if v!='')


def employment(ads):
    mapping={'FULL_TIME':'Puno radno vreme','PART_TIME':'Nepuno radno vreme',
             'CONTRACTOR':'Ugovorni angažman','TEMPORARY':'Privremeni posao',
             'INTERN':'Praksa','VOLUNTEER':'Volontiranje','PER_DIEM':'Dnevnica','OTHER':'Drugo'}
    values=[]
    for ad in ads:
        raw=(ad.get('structured') or {}).get('employmentType')
        for value in raw if isinstance(raw,list) else [raw]:
            value=label(value)
            if value:values.append(mapping.get(value.upper(),value))
    if values:return ', '.join(dict.fromkeys(values)),'izvor'
    for ad in ads:
        values.extend(ad.get('facets',{}).get('contract_type',{}).get('values',[]))
    return ', '.join(dict.fromkeys(values)),('prepoznato_u_tekstu' if values else '')


def cards(groups,exclude_expired=False):
    result=[]
    for group in groups:
        ads=group['sources']
        status,deadline=group_state(ads)
        expired=status=='istekao'
        if exclude_expired and expired:continue
        best=max(ads,key=lambda a:(deadline_state(a.get('expires',''))=='rok_nije_istekao',not a['expired'],bool(a['employer']),'incomplete' not in a['quality'],len(a['description'])))
        kind,kind_origin=employment([best]+[a for a in ads if a is not best])
        data=best.get('structured') or {}
        description=' '.join(best['description'].split())
        if len(description)>280:description=description[:277].rsplit(' ',1)[0]+'…'
        row=dict.fromkeys(FIELDS,'')
        row.update(id=str(group['group_id']),naslov=best['title'],kategorija='Posao',
                   poslodavac=best['employer'],lokacija=', '.join(sorted({p for a in ads for p in a['locations']})),
                   opis=description,plata=salary(data),tip_zaposlenja=kind,tip_zaposlenja_poreklo=kind_origin,
                   link=web_url(data.get('original_url')) or web_url(best['url']),
                   datum_objave=best['posted'] or next((a['posted'] for a in ads if a.get('posted')),''),rok_prijave=deadline,
                   status=status,vidljiv=not expired,arhiviran=expired,
                   izvori=[{'naziv':a['source'],'link':web_url(a['url']),
                            'originalni_link':web_url(a.get('structured',{}).get('original_url')),
                            'datum_objave':a.get('posted',''),'rok_prijave':a.get('expires',''),
                            'status':deadline_state(a.get('expires',''))} for a in ads])
        result.append(row)
    return result


def write_csv(path,rows):
    # BOM and semicolon make Serbian Excel imports straightforward. Neutralize
    # formulas from third-party ad text without altering the JSON export.
    def cell(value):
        if isinstance(value,list):value=json.dumps(value,ensure_ascii=False)
        value=str(value)
        return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
    with path.open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=FIELDS,delimiter=';')
        writer.writeheader()
        writer.writerows({k:cell(v) for k,v in row.items()} for row in rows)
