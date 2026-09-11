"""Adapters for the second batch of public job sources."""
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, parse_qsl, urlencode, urlunsplit

from bs4 import BeautifulSoup
from .model import Job, canonical, enrich, locations


class SkipJob(ValueError):
    """An explicit demo or unavailable listing, not a parser failure."""


def text(node):
    return node.get_text(' ', strip=True) if node else ''


def local_date(value):
    months = 'januar februar mart april maj jun jul avgust septembar oktobar novembar decembar'.split()
    value = value.lower()
    match = re.search(r'(\d{1,2})\.\s*(' + '|'.join(months) + r')\s+(\d{4})', value)
    if match:
        day, month, year = match.groups()
    else:
        match = re.search(r'(' + '|'.join(months) + r')\s+(\d{1,2}),?\s+(\d{4})', value)
        if not match:
            return ''
        month, day, year = match.groups()
    return datetime(int(year), months.index(month) + 1, int(day)).date().isoformat()


def extra_listing(html, url, source):
    sid = source['id']
    if sid == 'joberty':
        data = json.loads(html)
        found = {'https://www.joberty.com/sr/job/' + str(row['id']): row for row in data['items']}
        p = urlsplit(url)
        params = dict(parse_qsl(p.query))
        page = int(params.get('page', 0))
        pages = []
        if page + 1 < data['totalPage']:
            params['page'] = str(page + 1)
            pages.append(urlunsplit((p.scheme, p.netloc, p.path, urlencode(params), '')))
        return found, pages
    if sid == 'adorio':
        soup = BeautifulSoup(html, 'html.parser')
        found = {}
        for a in soup.select('a[href*="/oglas-za-posao/"]'):
            if not a.select_one('h2'):
                continue
            company_place = text(a.select_one('span.g-pa-0'))
            company, _, place = company_place.rpartition(' · ')
            found[canonical(urljoin(url, a['href']))] = {
                'title': text(a.select_one('h2')), 'employer': company,
                'location': place, 'description': text(a.select_one('div.g-pr-25--lg')),
            }
        # Query pagination and redirect detail routes are explicitly disallowed.
        # Only public landing-page excerpts are collected; report partial coverage.
        return found, []
    if sid == 'sbu':
        soup = BeautifulSoup(html, 'html.parser')
        found = {canonical(urljoin(url, a['href'])): text(a)
                 for a in soup.select('.jobsearch-pst-title a[href]')}
        page = int(urlsplit(url).fragment.removeprefix('sbu-page=') or 1)
        numbers = [int(m[1]) for node in soup.select('[onclick]')
                   if (m := re.search(r"jobsearch_job_pagenation_ajax\('job_page',\s*'(\d+)'", node['onclick']))]
        next_page = min((n for n in numbers if n > page), default=None)
        return found, [source['urls'][0] + '#sbu-page=' + str(next_page)] if next_page else []
    return None


def extra_detail(html, url, source):
    sid = source['id']
    if sid == 'adorio':
        row = json.loads(html)
        return enrich(Job(sid, canonical(url), row['title'], row['employer'], row['description'],
                          locations(row['location']), row['location'],
                          quality='listing_excerpt;description_incomplete;date_missing',
                          structured={'coverage': 'public landing-page excerpt; detail disallowed by robots.txt'}))
    if sid == 'joberty':
        data = json.loads(html)
        place = ', '.join(data.get('cities') or [])
        expires = data.get('expirationDate')
        expires = datetime.fromtimestamp(expires / 1000, timezone.utc).isoformat() if expires else ''
        structured = {key: data[raw] for raw, key in [('technologies', 'skills'), ('domains', 'occupationalCategory'),
                      ('seniority', 'experienceRequirements')] if data.get(raw)}
        if data.get('applyUrl'):
            structured['original_url'] = data['applyUrl']
        description = text(BeautifulSoup(data.get('text') or '', 'html.parser'))
        if not description:
            raise ValueError('Joberty: missing description')
        return enrich(Job(sid, canonical(url), data['jobTitle'], data.get('companyName') or '',
                          description, locations(place), place, expires=expires,
                          structured=structured, quality='api;date_missing'))
    if sid == 'manpower':
        soup = BeautifulSoup(html, 'html.parser')
        node = soup.select_one('.job-posts-page')
        if not node or not node.select_one('h1'):
            raise ValueError('Manpower: missing job container')
        title = text(node.select_one('h1'))
        place = text(node.select_one('.job-city'))
        content = []
        for child in node.find_all(['h6', 'p', 'ul'], recursive=False):
            content.append(text(child))
        description = '\n'.join(content)
        if not description:
            raise ValueError('Manpower: missing description')
        # The end employer is often unnamed. The agency is not its identity.
        return enrich(Job(sid, canonical(url), title, description=description,
                          locations=locations(place), location_raw=place,
                          structured={'agency': 'Manpower Srbija'}, quality='html;employer_missing;date_missing'))
    if sid == 'paz':
        soup = BeautifulSoup(html, 'html.parser')
        if soup.select_one('.hua-synthetic-demo-notice'):
            raise SkipJob('demo_listing')
    if sid == 'sbu':
        soup=BeautifulSoup(html,'html.parser')
        if not soup.select_one('.jobsearch-jobdetail-list') and soup.select_one('.jobsearch-pst-title'):
            raise SkipJob('unavailable_redirected_to_listing')
    return None


def extra_html_fields(soup, source, data):
    """Populate job-scoped HTML metadata before the common detail parser."""
    sid = source['id']
    if sid == 'oglaszaposao':
        for node in soup.select('.ozp-info-content'):
            label=text(node.select_one('.ozp-info-label'))
            value=text(node.select_one('.ozp-info-value, .ozp-info-value-link'))
            if label=='Rok za Prijavu':
                try:data.setdefault('validThrough',datetime.strptime(value,'%d.%m.%Y').date().isoformat())
                except ValueError:pass
            elif label=='Tip Zaposlenja':data.setdefault('employmentType',value)
        original=next((a for a in soup.select('.ozp-section-content a[href]') if 'originalni oglas' in text(a).lower()),None)
        if original:
            data['original_url']=original['href']
            data['description_incomplete']=True
            original.decompose()
        for node in soup.find_all(string=re.compile(r'Objavljeno:')):
            match=re.search(r'\d{2}\.\d{2}\.\d{4}',str(node))
            if match:data.setdefault('datePosted',datetime.strptime(match[0],'%d.%m.%Y').date().isoformat())
    elif sid == 'sljaka':
        stamp = soup.select_one('.page-sub-heading-info time[datetime]')
        if stamp:
            data['datePosted'] = stamp['datetime']
        data['validThrough'] = local_date(text(soup.select_one('.page-sub-heading-info .job-date__closing')))
        data['employmentType'] = text(soup.select_one('.page-sub-heading-info .job-type'))
    elif sid == 'sbu':
        for li in soup.select('.jobsearch-jobdetail-options li'):
            value = text(li)
            if 'Post Date' in value:
                data['datePosted'] = local_date(value)
            elif 'Prijavite se pre' in value:
                data['validThrough'] = local_date(value)
        data['employmentType'] = text(soup.select_one('.jobsearch-jobdetail-type'))
    return data


def sbu_payload(html):
    soup = BeautifulSoup(html, 'html.parser')
    field = soup.select_one('input[name="job_page"]')
    if not field:
        raise ValueError('SBU: pagination state missing')
    counter = field['id'].removeprefix('job_page-')
    args = soup.select_one('#job_arg' + counter)
    small = soup.select_one('#job_small_arg' + counter)
    if not args:
        raise ValueError('SBU: job arguments missing')
    return {'action': 'jobsearch_jobs_content', 'view_type': '', 'ajax_filter': 'true',
            'job_arg': args.decode_contents(), 'smjob_arg': small.decode_contents() if small else ''}
