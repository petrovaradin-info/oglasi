"""Conservative cross-source matching. Uncertain pairs remain review candidates."""
import re
from datetime import datetime
from difflib import SequenceMatcher
from .model import canonical, norm


def employer_key(value):
    value = norm(value)
    return re.sub(r'\b(d o o|doo|d d|a d|ad|llc|ltd)\b', '', value).strip()


def title_key(value):
    value=re.sub(r'\s*\((?:m[ /-](?:ž|z|f)(?:[ /-]d)?)\)\s*',' ',value,flags=re.I)
    value=re.sub(r'\s*(?:,|[–—]| - )\s*(?:Novi Sad|Petrovaradin|Sremski Karlovci)(?:\s+grad)?\s*$','',value,flags=re.I)
    return norm(value)


def match(a, b):
    """Return (automatic, score, reason). Never infer a duplicate from title alone."""
    a_original = a.get('structured', {}).get('original_url')
    b_original = b.get('structured', {}).get('original_url')
    # A declared original pointing to the other actual ad is strongest evidence.
    if (a_original and canonical(a_original) == canonical(b['url'])) or (b_original and canonical(b_original) == canonical(a['url'])):
        return True, 1.0, 'same_original_url'
    if a_original and b_original and canonical(a_original)==canonical(b_original):
        # Publisher permalinks, as opposed to shared /careers application forms.
        if re.search(r'/(?:jdp|job|oglas|posao|informacije)/.+',canonical(a_original)) and title_key(a['title'])==title_key(b['title']):
            return True,1.0,'same_original_job_permalink'
    if not a.get('locations') or set(a['locations']) != set(b['locations']):
        return False, 0, ''
    employer_a, employer_b = employer_key(a.get('employer')), employer_key(b.get('employer'))
    if not employer_a or not employer_b:
        return False, 0, ''
    if employer_a != employer_b:
        for short,full,key in ((a,b,employer_a),(b,a,employer_b)):
            if short.get('employer','').endswith(('...','…')) and len(key)>=12 and employer_key(full.get('employer')).startswith(key):
                score=SequenceMatcher(None,title_key(a['title']),title_key(b['title']),autojunk=False).ratio()
                if score>=.82:return False,score,'truncated_employer_similar_title_location; needs_review'
        return False,0,''
    title_score = SequenceMatcher(None, title_key(a['title']), title_key(b['title']), autojunk=False).ratio()
    if title_score < .82:
        return False, 0, ''
    try:
        nearby = abs((datetime.fromisoformat(a['posted'][:10]) - datetime.fromisoformat(b['posted'][:10])).days) <= 30
    except (ValueError, TypeError, KeyError):
        nearby = None
    if nearby is False:
        return False, title_score, 'similar_job_different_dates'
    desc_a, desc_b = norm(a.get('description')), norm(b.get('description'))
    incomplete = any('incomplete' in j.get('quality', '') or 'missing' in j.get('quality', '') and not j.get('description') for j in (a,b))
    if title_score == 1 and not incomplete and min(len(desc_a), len(desc_b)) >= 160:
        if desc_a == desc_b:
            return True, 1, 'same_employer_title_location_and_description'
        if nearby and SequenceMatcher(None, desc_a, desc_b).ratio() >= .9:
            return True, .9, 'same_employer_title_location_date_and_similar_description'
    # Common application landing pages are not sufficient evidence of identity.
    if a_original and b_original and canonical(a_original) == canonical(b_original) and title_score == 1 and nearby is not False and not incomplete:
        if min(len(desc_a), len(desc_b)) >= 160 and SequenceMatcher(None, desc_a, desc_b).ratio() >= .9:
            return True, .99, 'same_application_url_and_content'
    return False, title_score, 'same_employer_location_similar_title; needs_review'
