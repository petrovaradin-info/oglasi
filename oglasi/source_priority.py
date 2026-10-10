"""Preferred publishers within an already matched job group."""
PRIORITY = {'infostud': 0, 'helloworld': 1}

def ordered(ads):
    return sorted(ads, key=lambda ad: PRIORITY.get(ad.get('source'), 2))

def authoritative(ads):
    preferred = [ad for ad in ads if ad.get('source') in PRIORITY]
    if not preferred:
        return ads
    rank = min(PRIORITY[ad['source']] for ad in preferred)
    return [ad for ad in preferred if PRIORITY[ad['source']] == rank]

def best_ad(ads, at=None):
    from .lifecycle import deadline_state
    return max(authoritative(ads), key=lambda a: (
        deadline_state(a.get('expires',''), at) == 'rok_nije_istekao',
        deadline_state(a.get('expires',''), at) != 'istekao',
        bool(a.get('employer')), 'incomplete' not in a.get('quality',''),
        len(a.get('description',''))))
